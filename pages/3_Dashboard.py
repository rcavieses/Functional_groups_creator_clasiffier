"""
Dashboard de Estadísticas y Comentarios

Vista general de:
- Comentarios recientes de otros expertos
- Grupos más comentados
- Propuestas en evaluación
- Actividad general de la plataforma
"""

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import streamlit as st
import pandas as pd
from sql_client import (
    get_db,
    get_recent_comments,
    get_most_commented_groups,
    get_proposals_summary,
    get_pending_proposals,
    get_expert_activity,
    get_group_rating_stats,
    get_recent_activity,
)

st.set_page_config(page_title="Dashboard", page_icon="📈", layout="wide")

# ── Verificar auth ─────────────────────────────────────────────────────────────
if not st.session_state.get("auth"):
    st.warning("⚠️ Debes iniciar sesión primero. Ve a la página de **Inicio**.")
    st.stop()

auth = st.session_state.get("auth", {})
expert_name = st.session_state.get("expert_name", "")
expert_email = auth.get("email", "").lower()
db = get_db()

st.title("📈 Dashboard de Estadísticas")
st.caption(f"Experto: **{expert_name}** · Vista general de la plataforma")

# ── Refresh button ─────────────────────────────────────────────────────────────
col_refresh, _, _ = st.columns([1, 2, 3])
with col_refresh:
    if st.button("🔄 Recargar", use_container_width=True,
                 help="Actualizar datos desde Azure SQL"):
        st.rerun()

st.markdown("---")

# ── Load analytics data ────────────────────────────────────────────────────────
with st.spinner("Cargando estadísticas…"):
    recent_comments = get_recent_comments(db)
    most_commented = get_most_commented_groups(db)
    proposals_summary = get_proposals_summary(db)
    pending_proposals = get_pending_proposals(db)
    expert_activity = get_expert_activity(db)
    group_ratings = get_group_rating_stats(db)
    recent_activity = get_recent_activity(db)

# ── KPIs principales ───────────────────────────────────────────────────────────
st.markdown("### 📊 Resumen General")
col1, col2, col3, col4 = st.columns(4)

with col1:
    total_comments = len(recent_comments)
    st.metric("💬 Comentarios Totales", total_comments)

with col2:
    new_proposals = proposals_summary.get("new_group", 0)
    st.metric("✨ Nuevos Grupos Propuestos", new_proposals)

with col3:
    mod_proposals = proposals_summary.get("modification", 0)
    st.metric("🔄 Modificaciones Propuestas", mod_proposals)

with col4:
    del_proposals = proposals_summary.get("deletion", 0)
    st.metric("🗑️ Eliminaciones Propuestas", del_proposals)

st.markdown("---")

# ── Main tabs ──────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "💬 Comentarios Recientes",
    "⭐ Grupos Más Comentados",
    "💡 Propuestas Pendientes",
    "👥 Actividad de Expertos",
    "📋 Actividad Reciente"
])

# ── TAB 1: Comentarios Recientes ───────────────────────────────────────────────
with tab1:
    st.markdown("### Comentarios Recientes (últimas 20)")

    if recent_comments.empty:
        st.info("No hay comentarios aún.")
    else:
        for idx, row in recent_comments.iterrows():
            with st.container(border=True):
                col_left, col_right = st.columns([4, 1])

                with col_left:
                    st.markdown(f"**{row['group_name']}** (`{row['group_code']}`)")
                    st.markdown(f"💬 {row['comment']}")

                with col_right:
                    expert = row.get('expert', 'Desconocido')
                    st.caption(f"👤 {expert}")
                    timestamp = row.get('timestamp', 'Sin fecha')
                    st.caption(f"🕐 {timestamp}")


# ── TAB 2: Grupos Más Comentados ───────────────────────────────────────────────
with tab2:
    st.markdown("### Top 10 Grupos Más Comentados")

    if most_commented.empty:
        st.info("No hay comentarios registrados.")
    else:
        # Mostrar tabla con gráfico
        display_df = most_commented.copy()
        display_df = display_df.rename(columns={
            "comment_count": "Comentarios",
            "expert_count": "Expertos únicos",
            "group_name": "Nombre",
            "group_code": "Código"
        })

        col_chart, col_table = st.columns([1, 1])

        with col_chart:
            st.markdown("#### Comentarios por Grupo")
            chart_data = display_df[["Nombre", "Comentarios"]].set_index("Nombre")
            st.bar_chart(chart_data, use_container_width=True)

        with col_table:
            st.markdown("#### Detalles")
            st.dataframe(
                display_df[["Código", "Nombre", "Comentarios", "Expertos únicos"]],
                use_container_width=True,
                hide_index=True
            )

        # Tarjetas detalladas
        st.markdown("#### Análisis Detallado")
        with st.expander("Ver comentarios de cada grupo"):
            for idx, row in most_commented.iterrows():
                group_code = row['group_code']
                st.markdown(f"**{row['group_name']}** ({group_code})")

                # Obtener comentarios específicos de este grupo
                group_comments = recent_comments[
                    recent_comments['group_code'] == group_code
                ].head(3)

                if not group_comments.empty:
                    for _, comment_row in group_comments.iterrows():
                        st.markdown(
                            f"- **{comment_row['expert']}** ({comment_row['timestamp']}): "
                            f"_{comment_row['comment']}_"
                        )
                st.divider()


# ── TAB 3: Propuestas Pendientes ───────────────────────────────────────────────
with tab3:
    st.markdown("### 💡 Propuestas Pendientes de Evaluación")

    # Resumen visual
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Nuevos Grupos", proposals_summary.get("new_group", 0))
    with col2:
        st.metric("Modificaciones", proposals_summary.get("modification", 0))
    with col3:
        st.metric("Eliminaciones", proposals_summary.get("deletion", 0))

    st.markdown("---")

    if pending_proposals.empty:
        st.success("✅ No hay propuestas pendientes.")
    else:
        # Clasificar por tipo
        new_groups = pending_proposals[pending_proposals['type'] == 'new_group']
        modifications = pending_proposals[pending_proposals['type'] == 'modification']
        deletions = pending_proposals[pending_proposals['type'] == 'deletion']

        # Nuevos grupos
        if not new_groups.empty:
            st.markdown("#### ✨ Nuevos Grupos Propuestos")
            for idx, row in new_groups.iterrows():
                with st.container(border=True):
                    st.markdown(f"**{row['group_name']}** (`{row['group_code']}`)")
                    if pd.notna(row.get('description')) and row['description']:
                        st.markdown(f"📝 Descripción: {row['description']}")
                    col_a, col_b = st.columns([3, 1])
                    with col_a:
                        if pd.notna(row.get('reason')) and row['reason']:
                            st.markdown(f"💭 Justificación: {row['reason']}")
                    with col_b:
                        st.caption(f"👤 {row['proposed_by']}\n🕐 {row['proposed_at']}")

        # Modificaciones
        if not modifications.empty:
            st.markdown("#### 🔄 Modificaciones Propuestas")
            for idx, row in modifications.iterrows():
                with st.container(border=True):
                    st.markdown(f"**{row['group_name']}** (`{row['group_code']}`)")
                    st.markdown(f"💬 Sugerencia: {row['reason']}")
                    col_a, col_b = st.columns([3, 1])
                    with col_b:
                        st.caption(f"👤 {row['proposed_by']}\n🕐 {row['proposed_at']}")

        # Eliminaciones
        if not deletions.empty:
            st.markdown("#### 🗑️ Eliminaciones Propuestas")
            for idx, row in deletions.iterrows():
                with st.container(border=True):
                    st.markdown(f"**{row['group_name']}** (`{row['group_code']}`)")
                    st.markdown(f"❌ Razón: {row['reason']}")
                    col_a, col_b = st.columns([3, 1])
                    with col_b:
                        st.caption(f"👤 {row['proposed_by']}\n🕐 {row['proposed_at']}")


# ── TAB 4: Actividad de Expertos ───────────────────────────────────────────────
with tab4:
    st.markdown("### 👥 Actividad por Experto")

    if expert_activity.empty:
        st.info("No hay actividad registrada.")
    else:
        col_chart, col_table = st.columns([1, 1])

        with col_chart:
            st.markdown("#### Acciones por Experto")
            chart_data = expert_activity.set_index("expert")
            st.bar_chart(chart_data, use_container_width=True)

        with col_table:
            st.markdown("#### Ranking")
            st.dataframe(
                expert_activity.rename(columns={"expert": "Experto", "actions_count": "Acciones"}),
                use_container_width=True,
                hide_index=True
            )


# ── TAB 5: Actividad Reciente ──────────────────────────────────────────────────
with tab5:
    st.markdown("### 📋 Últimas Acciones (últimas 30)")

    if recent_activity.empty:
        st.info("No hay actividad registrada.")
    else:
        # Agrupar por tipo de acción
        actions_df = recent_activity.copy()

        # Crear representación visual
        action_map = {
            "validate": "✅",
            "move": "↔️",
            "remove": "🗑️",
            "restore": "↩️",
            "propose_group": "✨",
            "rate": "⭐"
        }

        actions_df["emoji"] = actions_df["action"].map(action_map).fillna("•")

        col_table, col_stats = st.columns([2, 1])

        with col_table:
            for idx, row in actions_df.iterrows():
                emoji = action_map.get(row['action'], "•")

                # Construir mensaje según acción
                if row['action'] == "move":
                    msg = f"{emoji} **{row['expert']}** movió `{row['taxon']}` de {row['from_code']} a {row['to_code']}"
                elif row['action'] == "remove":
                    msg = f"{emoji} **{row['expert']}** removió `{row['taxon']}` de {row['from_code']}"
                elif row['action'] == "validate":
                    msg = f"{emoji} **{row['expert']}** validó `{row['taxon']}`"
                else:
                    msg = f"{emoji} **{row['expert']}** — {row['action']} en `{row['taxon']}`"

                st.caption(f"{msg} · {row['timestamp']}")

        with col_stats:
            st.markdown("#### Resumen de Acciones")
            actions_count = recent_activity["action"].value_counts()
            for action, count in actions_count.items():
                emoji = action_map.get(action, "•")
                st.metric(f"{emoji} {action.replace('_', ' ').title()}", count)
