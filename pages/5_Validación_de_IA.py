"""
AI Validación — Revisión por lotes con consenso

Las sugerencias de la cuenta AI_expert se agrupan en lotes taxonómicos.
Los expertos aprueban/rechazan lotes completos (pudiendo excluir excepciones).
Un cambio se aplica en cuanto UN experto lo aprueba.
"""

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import streamlit as st
import pandas as pd
from sql_client import (
    get_db,
    get_ai_suggestions,
    get_ai_suggestions_stats,
    get_ai_votes,
    cast_ai_votes,
    add_batch_comment,
    get_batch_comments,
    get_all_species,
    MIN_CONSENSUS,
    expert_name_from_auth,
)
from ui_helpers import run_db_action

st.set_page_config(page_title="Validación de IA", page_icon="🤖", layout="wide")

if not st.session_state.get("auth"):
    st.warning("⚠️ Debes iniciar sesión primero. Ve a la página de **Inicio**.")
    st.stop()

expert = expert_name_from_auth(st.session_state.auth)
db = get_db()

CATEGORY_ICON = {
    "Plantas terrestres": "🌱",
    "Artrópodos terrestres": "🐛",
    "Tetrápodos terrestres": "🦎",
    "Hongos y líquenes": "🍄",
    "Gasterópodos → GAS": "🐌",
    "Cangrejos bentónicos → BEC": "🦀",
    "Poliquetos → PWO": "🪱",
    "Tunicados → SPO": "🧽",
}
TYPE_LABEL = {
    "move_species": "Mover especie",
    "new_group": "Nuevo grupo",
    "modify_group": "Modificar grupo",
    "remove_species": "Quitar especie",
}
STATUS_BADGE = {"pending": "⏳ Pendiente", "approved": "✅ Aplicada", "rejected": "❌ Rechazada"}
LEVEL_COL = {"Género": "genero", "Familia": "familia", "Orden": "orden", "Clase": "clase", "Filum": "filum"}

st.title("🤖 Validación de IA")
_consensus_txt = (
    "**1 experto** lo aprueba" if MIN_CONSENSUS == 1
    else f"**{MIN_CONSENSUS} expertos distintos** lo aprueban (consenso)"
)
st.caption(
    f"Sugerencias de **AI_expert**, agrupadas en lotes. Un cambio se aplica cuando {_consensus_txt}."
)

if st.button("🔄 Recargar", use_container_width=False):
    get_ai_suggestions(db, force=True)
    st.rerun()

# ── Data ────────────────────────────────────────────────────────────────────────
df = get_ai_suggestions(db)
votes = get_ai_votes(db)
batch_comments = get_batch_comments(db)
stats = get_ai_suggestions_stats(db)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total sugerencias", stats["total"])
m2.metric("✅ Aplicadas", stats["approved"])
m3.metric("⏳ Pendientes", stats["pending"])
m4.metric("❌ Rechazadas", stats["rejected"])
st.divider()

if df.empty:
    st.info("Aún no hay sugerencias de la IA.")
    st.stop()

# Per-suggestion vote tallies (distinct experts)
appr = votes[votes["vote"] == "approve"].groupby("suggestion_id")["expert"].nunique()
rej = votes[votes["vote"] == "reject"].groupby("suggestion_id")["expert"].nunique()
my_votes = votes[votes["expert"] == expert].set_index("suggestion_id")["vote"].to_dict()
df = df.copy()
df["n_approve"] = df["id"].map(appr).fillna(0).astype(int)
df["n_reject"] = df["id"].map(rej).fillna(0).astype(int)
df["my_vote"] = df["id"].map(my_votes)

# Taxonomic grouping helpers — genus from the taxon string, family/order from the species table
df["genero"] = df["taxon"].fillna("").str.strip().str.split().str[0].replace("", "—")
species_df = get_all_species(db)


def _taxon_map(col: str) -> dict:
    if not species_df.empty and col in species_df.columns:
        return species_df.dropna(subset=["taxon"]).set_index("taxon")[col].to_dict()
    return {}


df["familia"] = df["taxon"].map(_taxon_map("family")).fillna("—")
df["orden"] = df["taxon"].map(_taxon_map("order_taxon")).fillna("—")
df["clase"] = df["taxon"].map(_taxon_map("class_taxon")).fillna("—")
df["filum"] = df["taxon"].map(_taxon_map("phylum")).fillna("—")

# Human-readable action per row (used by both tabs)
df["accion"] = df["suggestion_type"].map(TYPE_LABEL).fillna(df["suggestion_type"])
_move_mask = df["suggestion_type"] == "move_species"
df.loc[_move_mask, "accion"] = "Mover → " + df.loc[_move_mask, "to_code"].fillna(df.loc[_move_mask, "to_name"]).fillna("?")
df["criterio"] = df["rationale"].fillna(df["title"]).fillna("—")

# ── Filters ─────────────────────────────────────────────────────────────────────
f0, f1, f2 = st.columns([1.4, 1.4, 1.4])
with f0:
    groups = sorted(df["from_code"].dropna().unique())
    group_filter = st.selectbox("Grupo de origen:", ["Todos"] + list(groups))
with f1:
    status_filter = st.selectbox(
        "Mostrar lotes con estado:", ["Todos", "Pendientes", "Aplicadas", "Rechazadas"]
    )
with f2:
    only_unvoted = st.checkbox("Solo sugerencias que aún no he votado", value=False)

# Scope the whole view to one origin group when selected
if group_filter != "Todos":
    df = df[df["from_code"] == group_filter]

tab_batches, tab_table = st.tabs(["📦 Revisión por lotes", "📊 Tabla detallada"])

# ── Batch review ────────────────────────────────────────────────────────────────
with tab_batches:
    categories = list(df["category"].dropna().unique())
    # Order: most pending first
    order = df[df["status"] == "pending"]["category"].value_counts()
    categories = list(order.index) + [c for c in categories if c not in order.index]

    for cat in categories:
        batch = df[df["category"] == cat]
        total = len(batch)
        applied = int((batch["status"] == "approved").sum())
        rejected = int((batch["status"] == "rejected").sum())
        pending = batch[batch["status"] == "pending"]

        # Status-level filter on the batch
        if status_filter == "Pendientes" and len(pending) == 0:
            continue
        if status_filter == "Aplicadas" and applied == 0:
            continue
        if status_filter == "Rechazadas" and rejected == 0:
            continue

        sample_type = TYPE_LABEL.get(batch.iloc[0]["suggestion_type"], "—")
        icon = CATEGORY_ICON.get(cat, "🔹")

        with st.container(border=True):
            st.markdown(f"## {icon} {cat}")
            st.caption(f"{sample_type} · {total} sugerencias en el lote")

            total_votes = int((batch["n_approve"] + batch["n_reject"]).sum())

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("✅ Aplicadas", applied)
            c2.metric("🗳️ Votos registrados", total_votes)
            c3.metric("⚪ Sin votos", int((pending["n_approve"] + pending["n_reject"] == 0).sum()))
            c4.metric("❌ Rechazadas", rejected)

            if applied + rejected > 0:
                st.progress((applied + rejected) / total, text=f"{applied + rejected}/{total} resueltas")

            # Sample of taxa
            sample = [t for t in batch["taxon"].dropna().head(10)]
            if sample:
                st.caption("**Ejemplos:** " + ", ".join(f"*{t}*" for t in sample)
                           + (" …" if total > len(sample) else ""))

            # Drill-down: full list + exclude exceptions
            with st.expander(f"🔍 Ver especies del lote y excluir excepciones ({total})"):
                level = st.radio(
                    "Agrupar por:", ["Especie", "Género", "Familia", "Orden", "Clase", "Filum"],
                    horizontal=True, key=f"level_{cat}",
                )
                show = batch.copy()
                show["estado"] = show["status"].map(STATUS_BADGE)
                show["aprobaciones"] = show["n_approve"].astype(str) + f"/{MIN_CONSENSUS}"
                show["tu voto"] = show["my_vote"].fillna("—")

                checkbox_col = st.column_config.CheckboxColumn("Excluir", help="Excluir de mi voto")

                if level == "Especie":
                    tbl = show[["taxon", "accion", "criterio", "estado", "aprobaciones", "tu voto"]].rename(
                        columns={"taxon": "Especie", "accion": "Acción", "criterio": "Criterio",
                                 "estado": "Estado", "aprobaciones": "Aprob.", "tu voto": "Tu voto"}
                    ).reset_index(drop=True)
                    tbl.insert(0, "Excluir", False)
                    edited = st.data_editor(
                        tbl, use_container_width=True, hide_index=True, height=280,
                        key=f"editor_{cat}_{level}",
                        disabled=[c for c in tbl.columns if c != "Excluir"],
                        column_config={"Excluir": checkbox_col},
                    )
                    excluded_keys = set(edited.loc[edited["Excluir"], "Especie"])
                else:
                    group_col = LEVEL_COL[level]
                    grouped = show.groupby(group_col).agg(
                        Especies=("taxon", "count"),
                        Acción=("accion", lambda s: ", ".join(sorted(s.unique()))),
                        Criterio=("criterio", lambda s: " | ".join(sorted(set(s.dropna()))[:2])),
                        Aplicadas=("status", lambda s: int((s == "approved").sum())),
                        Pendientes=("status", lambda s: int((s == "pending").sum())),
                        Rechazadas=("status", lambda s: int((s == "rejected").sum())),
                        Ejemplos=("taxon", lambda s: ", ".join(s.head(3))),
                    ).reset_index().rename(columns={group_col: level})
                    grouped.insert(1, "Excluir", False)
                    edited = st.data_editor(
                        grouped, use_container_width=True, hide_index=True, height=280,
                        key=f"editor_{cat}_{level}",
                        disabled=[c for c in grouped.columns if c != "Excluir"],
                        column_config={"Excluir": checkbox_col},
                    )
                    excluded_keys = set(edited.loc[edited["Excluir"], level])

            # Votable set: pending, not already approved by me, minus exclusions
            if level == "Especie":
                excluded = excluded_keys
            else:
                group_col = LEVEL_COL[level]
                excluded = set(batch[batch[group_col].isin(excluded_keys)]["taxon"])
            votable = pending[(pending["my_vote"] != "approve") & (~pending["taxon"].isin(excluded))]
            votable_ids = [int(i) for i in votable["id"]]

            bc1, bc2 = st.columns(2)
            if bc1.button(f"✅ Aprobar lote ({len(votable_ids)})", key=f"appr_{cat}",
                          type="primary", use_container_width=True, disabled=not votable_ids):
                holder = {}
                if run_db_action(
                    lambda: holder.update(res=cast_ai_votes(votable_ids, expert, "approve", db)),
                    spinner="Registrando tu voto…",
                ):
                    res = holder["res"]
                    get_ai_suggestions(db, force=True)
                    st.success(f"Registrado tu voto en {res['voted']} sugerencias · "
                               f"{res['applied']} alcanzaron consenso y se aplicaron.")
                    st.rerun()
            if bc2.button(f"❌ Rechazar lote ({len(votable_ids)})", key=f"rej_{cat}",
                          use_container_width=True, disabled=not votable_ids):
                holder = {}
                if run_db_action(
                    lambda: holder.update(res=cast_ai_votes(votable_ids, expert, "reject", db)),
                    spinner="Registrando tu rechazo…",
                ):
                    res = holder["res"]
                    get_ai_suggestions(db, force=True)
                    st.warning(f"Registrado tu rechazo en {res['voted']} sugerencias · "
                               f"{res['rejected']} alcanzaron consenso de rechazo.")
                    st.rerun()

            # Batch comments
            with st.expander("💬 Comentarios del lote"):
                cat_comments = batch_comments[batch_comments["category"] == cat]
                if cat_comments.empty:
                    st.caption("Sin comentarios.")
                else:
                    for _, cm in cat_comments.iterrows():
                        ts = pd.to_datetime(cm["created_at"]).strftime("%Y-%m-%d %H:%M")
                        st.markdown(f"**{cm['expert']}** · _{ts}_")
                        st.markdown(f"> {cm['comment']}")
                new_c = st.text_area("Agregar comentario al lote:", key=f"cmt_{cat}", height=70)
                if st.button("Enviar comentario", key=f"sendc_{cat}"):
                    if new_c.strip():
                        if run_db_action(
                            lambda: add_batch_comment(cat, expert, new_c.strip(), db),
                            success="Comentario agregado.",
                        ):
                            st.rerun()
                    else:
                        st.warning("Escribe un comentario primero.")

# ── Detailed table (for edge cases / search) ────────────────────────────────────
with tab_table:
    st.caption("Vista plana para búsqueda o auditoría. La aprobación se hace en la pestaña de lotes.")
    search = st.text_input("Buscar por taxón, grupo o texto:", placeholder="Ej. Homo, GAS, insecto…")
    view = df
    if only_unvoted:
        view = view[view["my_vote"].isna() & (view["status"] == "pending")]
    if search.strip():
        q = search.strip().lower()
        cols = ["taxon", "from_code", "to_code", "to_name", "title", "rationale", "category"]
        mask = view[cols].fillna("").apply(lambda c: c.str.lower().str.contains(q, regex=False)).any(axis=1)
        view = view[mask]
    show = view.copy()
    show["estado"] = show["status"].map(STATUS_BADGE)
    show["aprob"] = show["n_approve"].astype(str) + f"/{MIN_CONSENSUS}"
    st.caption(f"{len(show)} sugerencias")
    st.dataframe(
        show[["id", "category", "filum", "clase", "orden", "familia", "genero", "taxon",
              "accion", "estado", "aprob", "my_vote", "criterio"]]
        .rename(columns={"category": "Lote", "filum": "Filum", "clase": "Clase", "orden": "Orden",
                          "familia": "Familia", "genero": "Género", "taxon": "Especie", "accion": "Acción",
                          "estado": "Estado", "aprob": "Aprob.", "my_vote": "Tu voto", "criterio": "Criterio"}),
        use_container_width=True, hide_index=True,
    )
