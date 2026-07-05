"""
AI Validación — Revisión por lotes con consenso

Las sugerencias de la cuenta AI_expert se agrupan en lotes taxonómicos.
Los expertos aprueban/rechazan lotes completos (pudiendo excluir excepciones).
Un cambio se aplica solo cuando DOS expertos distintos lo aprueban (consenso).
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
    MIN_CONSENSUS,
    expert_name_from_auth,
)

st.set_page_config(page_title="AI Validación", page_icon="🤖", layout="wide")

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

st.title("🤖 AI Validación")
st.caption(
    f"Sugerencias de **AI_expert**, agrupadas en lotes. Un cambio se aplica cuando "
    f"**{MIN_CONSENSUS} expertos distintos** lo aprueban (consenso)."
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

# ── Filters ─────────────────────────────────────────────────────────────────────
f1, f2 = st.columns([1.4, 1.4])
with f1:
    status_filter = st.selectbox(
        "Mostrar lotes con estado:", ["Todos", "Pendientes", "Esperando 2º voto", "Aplicadas", "Rechazadas"]
    )
with f2:
    only_unvoted = st.checkbox("Solo sugerencias que aún no he votado", value=False)

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
        waiting = int((pending["n_approve"] >= 1).sum())  # has 1 approval, needs 1 more
        my_pending_approved = int((pending["my_vote"] == "approve").sum())

        # Status-level filter on the batch
        if status_filter == "Pendientes" and len(pending) == 0:
            continue
        if status_filter == "Esperando 2º voto" and waiting == 0:
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

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("✅ Aplicadas", applied)
            c2.metric("🟡 Esperando 2º", waiting)
            c3.metric("⚪ Sin votos", int((pending["n_approve"] == 0).sum()))
            c4.metric("❌ Rechazadas", rejected)

            if applied + rejected > 0:
                st.progress((applied + rejected) / total, text=f"{applied + rejected}/{total} resueltas")

            # Sample of taxa
            sample = [t for t in batch["taxon"].dropna().head(10)]
            if sample:
                st.caption("**Ejemplos:** " + ", ".join(f"*{t}*" for t in sample)
                           + (" …" if total > len(sample) else ""))

            # My status in this batch
            if my_pending_approved:
                st.caption(f"👤 Ya aprobaste **{my_pending_approved}** sugerencias pendientes de este lote "
                           "(esperando el voto de otro experto).")

            # Drill-down: full list + exclude exceptions
            with st.expander(f"🔍 Ver especies del lote y excluir excepciones ({total})"):
                show = batch.copy()
                show["estado"] = show["status"].map(STATUS_BADGE)
                show["aprobaciones"] = show["n_approve"].astype(str) + f"/{MIN_CONSENSUS}"
                show["tu voto"] = show["my_vote"].fillna("—")
                st.dataframe(
                    show[["taxon", "estado", "aprobaciones", "tu voto"]].rename(
                        columns={"taxon": "Especie", "estado": "Estado",
                                 "aprobaciones": "Aprob.", "tu voto": "Tu voto"}),
                    use_container_width=True, hide_index=True, height=280,
                )
                exclude = st.multiselect(
                    "Excluir estas especies de mi voto (excepciones):",
                    options=sorted(pending["taxon"].dropna().unique()),
                    key=f"excl_{cat}",
                )

            # Votable set: pending, not already approved by me, minus exclusions
            excluded = set(st.session_state.get(f"excl_{cat}", []))
            votable = pending[(pending["my_vote"] != "approve") & (~pending["taxon"].isin(excluded))]
            votable_ids = [int(i) for i in votable["id"]]

            bc1, bc2 = st.columns(2)
            if bc1.button(f"✅ Aprobar lote ({len(votable_ids)})", key=f"appr_{cat}",
                          type="primary", use_container_width=True, disabled=not votable_ids):
                res = cast_ai_votes(votable_ids, expert, "approve", db)
                get_ai_suggestions(db, force=True)
                st.success(f"Registrado tu voto en {res['voted']} sugerencias · "
                           f"{res['applied']} alcanzaron consenso y se aplicaron.")
                st.rerun()
            if bc2.button(f"❌ Rechazar lote ({len(votable_ids)})", key=f"rej_{cat}",
                          use_container_width=True, disabled=not votable_ids):
                res = cast_ai_votes(votable_ids, expert, "reject", db)
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
                        add_batch_comment(cat, expert, new_c.strip(), db)
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
        show[["id", "category", "suggestion_type", "taxon", "to_code", "estado", "aprob", "my_vote"]].rename(
            columns={"category": "Lote", "suggestion_type": "Tipo", "taxon": "Especie",
                     "to_code": "Destino", "estado": "Estado", "aprob": "Aprob.", "my_vote": "Tu voto"}),
        use_container_width=True, hide_index=True,
    )
