"""
AI Validación — Bandeja de revisión de sugerencias del experto IA

Muestra los cambios de grupos funcionales / asignación de especies que
propone la cuenta AI_expert. Los expertos humanos aprueban, rechazan
y comentan cada sugerencia; todo queda registrado en la base de datos.
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
    get_ai_suggestion_comments,
    add_ai_suggestion_comment,
    approve_ai_suggestion,
    reject_ai_suggestion,
    expert_name_from_auth,
)

st.set_page_config(page_title="AI Validación", page_icon="🤖", layout="wide")

# ── Auth guard ─────────────────────────────────────────────────────────────────
if not st.session_state.get("auth"):
    st.warning("⚠️ Debes iniciar sesión primero. Ve a la página de **Inicio**.")
    st.stop()

expert = expert_name_from_auth(st.session_state.auth)
db = get_db()

TYPE_ICON = {
    "move_species": "↔️",
    "new_group": "✨",
    "modify_group": "✏️",
    "remove_species": "🗑️",
}
TYPE_LABEL = {
    "move_species": "Mover especie",
    "new_group": "Nuevo grupo",
    "modify_group": "Modificar grupo",
    "remove_species": "Quitar especie",
}
STATUS_BADGE = {
    "pending": "⏳ Pendiente",
    "approved": "✅ Aprobada",
    "rejected": "❌ Rechazada",
}

st.title("🤖 AI Validación")
st.caption("Sugerencias propuestas por la cuenta **AI_expert** — revisa, comenta y aprueba/rechaza.")

if st.button("🔄 Recargar", use_container_width=False):
    get_ai_suggestions(db, force=True)
    st.rerun()

# ── Metrics ────────────────────────────────────────────────────────────────────
stats = get_ai_suggestions_stats(db)
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total", stats["total"])
m2.metric("⏳ Pendientes", stats["pending"])
m3.metric("✅ Aprobadas", stats["approved"])
m4.metric("❌ Rechazadas", stats["rejected"])
st.divider()

df = get_ai_suggestions(db)

if df.empty:
    st.info("Aún no hay sugerencias de la IA. Cuando AI_expert proponga cambios, aparecerán aquí.")
    st.stop()

# ── Filters ────────────────────────────────────────────────────────────────────
f1, f2, f3 = st.columns([1.2, 1.5, 2])
with f1:
    status_filter = st.selectbox("Estado:", ["Todos", "Pendientes", "Aprobadas", "Rechazadas"])
with f2:
    type_options = sorted(df["suggestion_type"].dropna().unique())
    type_filter = st.multiselect(
        "Tipo de cambio:", options=type_options,
        format_func=lambda t: f"{TYPE_ICON.get(t, '')} {TYPE_LABEL.get(t, t)}",
    )
with f3:
    search = st.text_input("Buscar por taxón, grupo o texto:", placeholder="Ej. Sardinops, PROD, sardina…")

filtered = df.copy()
status_map = {"Pendientes": "pending", "Aprobadas": "approved", "Rechazadas": "rejected"}
if status_filter != "Todos":
    filtered = filtered[filtered["status"] == status_map[status_filter]]
if type_filter:
    filtered = filtered[filtered["suggestion_type"].isin(type_filter)]
if search.strip():
    q = search.strip().lower()
    searchable = filtered[["taxon", "from_code", "from_name", "to_code", "to_name", "title", "rationale"]].fillna("")
    mask = searchable.apply(lambda col: col.str.lower().str.contains(q, regex=False)).any(axis=1)
    filtered = filtered[mask]

st.caption(f"**{len(filtered)}** de {len(df)} sugerencias")
st.divider()

view_cards, view_table = st.tabs(["🗂️ Tarjetas", "📊 Tabla"])


def _render_review_controls(row, ctx: str = "card"):
    sid = int(row["id"])
    if row["status"] == "pending":
        c1, c2 = st.columns(2)
        if c1.button("✅ Aprobar", key=f"appr_{ctx}_{sid}", type="primary", use_container_width=True):
            approve_ai_suggestion(sid, row, expert, db)
            st.rerun()
        if c2.button("❌ Rechazar", key=f"rej_{ctx}_{sid}", use_container_width=True):
            reject_ai_suggestion(sid, expert, db)
            st.rerun()
    else:
        reviewer = row.get("reviewed_by") or "—"
        st.caption(f"Revisado por **{reviewer}**")

    with st.expander("💬 Comentarios"):
        comments = get_ai_suggestion_comments(sid, db)
        if comments.empty:
            st.caption("Sin comentarios todavía.")
        else:
            for _, c in comments.iterrows():
                ts = pd.to_datetime(c["created_at"]).strftime("%Y-%m-%d %H:%M")
                st.markdown(f"**{c['expert']}** · _{ts}_")
                st.markdown(f"> {c['comment']}")
        new_comment = st.text_area("Agregar comentario:", key=f"comment_{ctx}_{sid}", height=70)
        if st.button("Enviar comentario", key=f"send_{ctx}_{sid}"):
            if new_comment.strip():
                add_ai_suggestion_comment(sid, expert, new_comment.strip(), db)
                st.rerun()
            else:
                st.warning("Escribe un comentario antes de enviarlo.")


with view_cards:
    if filtered.empty:
        st.info("No hay sugerencias con estos filtros.")
    else:
        cols = st.columns(2)
        for idx, (_, row) in enumerate(filtered.iterrows()):
            col = cols[idx % 2]
            with col:
                with st.container(border=True):
                    icon = TYPE_ICON.get(row["suggestion_type"], "🔹")
                    label = TYPE_LABEL.get(row["suggestion_type"], row["suggestion_type"])
                    st.markdown(f"### {icon} {row['title'] or label}")
                    st.caption(f"{label} · {STATUS_BADGE.get(row['status'], row['status'])}")

                    if row["suggestion_type"] == "move_species":
                        st.markdown(f"**Especie:** *{row['taxon']}*")
                        st.markdown(f"`{row['from_code']}` → `{row['to_code']}` — {row['to_name']}")
                    elif row["suggestion_type"] == "remove_species":
                        st.markdown(f"**Especie:** *{row['taxon']}*")
                        st.markdown(f"Grupo actual: `{row['from_code']}` — {row['from_name']}")
                    elif row["suggestion_type"] == "new_group":
                        st.markdown(f"**Grupo propuesto:** `{row['to_code']}` — {row['to_name']}")
                        if row.get("taxon"):
                            st.caption(f"Especie origen: *{row['taxon']}* (`{row['from_code']}`)")
                    elif row["suggestion_type"] == "modify_group":
                        st.markdown(f"**Grupo:** `{row['from_code']}` — {row['from_name']}")

                    if row.get("rationale"):
                        st.markdown(f"_{row['rationale']}_")

                    proposed_at = row.get("proposed_at")
                    if pd.notna(proposed_at):
                        st.caption(f"Propuesto por {row['proposed_by']} · {pd.to_datetime(proposed_at).strftime('%Y-%m-%d %H:%M')}")

                    _render_review_controls(row)

with view_table:
    if filtered.empty:
        st.info("No hay sugerencias con estos filtros.")
    else:
        table_df = filtered.copy()
        table_df["tipo"] = table_df["suggestion_type"].map(lambda t: f"{TYPE_ICON.get(t, '')} {TYPE_LABEL.get(t, t)}")
        table_df["estado"] = table_df["status"].map(STATUS_BADGE)
        display_cols = ["id", "tipo", "taxon", "from_code", "to_code", "to_name", "title", "estado", "proposed_by", "proposed_at"]
        st.dataframe(table_df[display_cols], use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("#### Revisar una sugerencia por ID")
        sel_id = st.number_input("ID:", min_value=int(filtered["id"].min()), max_value=int(filtered["id"].max()), step=1)
        match = filtered[filtered["id"] == sel_id]
        if not match.empty:
            _render_review_controls(match.iloc[0], ctx="table")
