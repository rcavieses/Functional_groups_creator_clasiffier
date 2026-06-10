"""
Validar Grupos Funcionales — Vista de Fichas

Interfaz principal para validar grupos completos:
- Ver estadísticas de cada grupo
- Calificar grupos (1-5 estrellas)
- Proponer eliminación con argumento
- Proponer nuevo grupo con descripción
"""

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import streamlit as st
import pandas as pd
from firebase_client import (
    get_db,
    load_species,
    get_groups_summary,
    rate_group,
    propose_group_deletion,
    propose_new_group_detailed,
    get_group_rating_summary,
)

st.set_page_config(
    page_title="Validar Grupos",
    page_icon="📊",
    layout="wide",
)

# ── Verificar auth ─────────────────────────────────────────────────────────────
if not st.session_state.get("auth"):
    st.warning("Por favor inicia sesión en la página principal")
    st.stop()

expert_name = st.session_state.get("expert_name", "")
db = get_db()

st.title("📊 Validación de Grupos Funcionales")
st.caption(f"Experto: **{expert_name}**")

# ── Cargar datos ───────────────────────────────────────────────────────────────
with st.spinner("Cargando datos…"):
    species_df = load_species(db)
    groups_summary = get_groups_summary(db)
    ratings_summary = get_group_rating_summary(db)

if species_df.empty:
    st.error("No hay datos disponibles")
    st.stop()

# ── Tabs principales ───────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["🎯 Validar Grupos", "💡 Propuestas", "📊 Estadísticas"])

# ── TAB 1: Validar Grupos (Fichas) ─────────────────────────────────────────────
with tab1:
    st.markdown("### Fichas de Grupos Funcionales")
    st.caption("Revisa cada grupo, califica, propón cambios")

    if not groups_summary:
        st.info("No hay grupos para validar")
    else:
        # Crear columnas para las fichas
        cols = st.columns(3)
        col_idx = 0

        for group_code, group_info in sorted(groups_summary.items()):
            col = cols[col_idx % 3]
            col_idx += 1

            with col:
                with st.container(border=True):
                    # Encabezado
                    st.markdown(f"### {group_code}")
                    st.markdown(f"**{group_info['name']}**")

                    # Estadísticas principales
                    species_count = group_info["total"]
                    validated_count = group_info["validated"]

                    st.metric(
                        "Especies",
                        f"{species_count}",
                        f"{validated_count} validadas"
                    )

                    # Rating
                    if group_code in ratings_summary:
                        avg_rating = ratings_summary[group_code]["avg_rating"]
                        count = ratings_summary[group_code]["count"]
                        st.markdown(f"⭐ **{avg_rating:.1f}/5** ({count} calificaciones)")
                    else:
                        st.markdown("⭐ **Sin calificaciones aún**")

                    st.divider()

                    # Acciones
                    st.markdown("**Acciones:**")

                    col_a, col_b = st.columns(2)

                    # Calificar
                    with col_a:
                        rating = st.selectbox(
                            "Calificación",
                            [1, 2, 3, 4, 5],
                            key=f"rating_{group_code}",
                            label_visibility="collapsed",
                        )

                    with col_b:
                        if st.button("⭐ Calificar", key=f"btn_rate_{group_code}", use_container_width=True):
                            st.session_state[f"show_comment_{group_code}"] = True

                    # Comentario (si se clickeó calificar)
                    if st.session_state.get(f"show_comment_{group_code}"):
                        comment = st.text_area(
                            "Comentario (opcional)",
                            key=f"comment_{group_code}",
                            height=60,
                        )
                        if st.button("💾 Guardar calificación", key=f"save_rate_{group_code}", use_container_width=True):
                            try:
                                rate_group(
                                    group_code,
                                    group_info["name"],
                                    rating,
                                    comment,
                                    expert_name,
                                    db
                                )
                                st.success("✅ Calificación guardada")
                                st.session_state[f"show_comment_{group_code}"] = False
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")

                    st.divider()

                    # Proponer eliminación
                    if st.button("🗑️ Proponer eliminar", key=f"btn_delete_{group_code}", use_container_width=True):
                        st.session_state[f"show_delete_{group_code}"] = True

                    if st.session_state.get(f"show_delete_{group_code}"):
                        reason = st.text_area(
                            "¿Por qué eliminar este grupo?",
                            key=f"delete_reason_{group_code}",
                            height=80,
                        )
                        if st.button("✓ Enviar propuesta", key=f"send_delete_{group_code}", use_container_width=True):
                            if reason.strip():
                                try:
                                    propose_group_deletion(
                                        group_code,
                                        group_info["name"],
                                        reason,
                                        expert_name,
                                        db
                                    )
                                    st.success("✅ Propuesta enviada")
                                    st.session_state[f"show_delete_{group_code}"] = False
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error: {e}")
                            else:
                                st.warning("Ingresa un argumento")

# ── TAB 2: Proponer Nuevos Grupos ──────────────────────────────────────────────
with tab2:
    st.markdown("### 💡 Proponer Nuevo Grupo")

    col1, col2 = st.columns(2)

    with col1:
        new_code = st.text_input(
            "Código del grupo",
            placeholder="ej: BIO, MAR, etc.",
            max_chars=10,
        ).upper()

    with col2:
        new_name = st.text_input(
            "Nombre del grupo",
            placeholder="ej: Organismos bentónicos",
        )

    new_description = st.text_area(
        "Descripción del grupo",
        placeholder="¿Qué características define a este grupo? ¿Qué especies lo componen?",
        height=100,
    )

    new_justification = st.text_area(
        "Justificación / Argumento",
        placeholder="¿Por qué es necesario este nuevo grupo? ¿Qué gap deja cubierto?",
        height=120,
    )

    if st.button("✅ Proponer nuevo grupo", use_container_width=True, type="primary"):
        if not all([new_code, new_name, new_description, new_justification]):
            st.error("Completa todos los campos")
        else:
            try:
                propose_new_group_detailed(
                    new_code,
                    new_name,
                    new_description,
                    new_justification,
                    expert_name,
                    db
                )
                st.success("✅ Propuesta de nuevo grupo enviada")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    st.divider()

    # Ver propuestas pendientes
    st.markdown("### 📋 Propuestas Pendientes")
    try:
        proposals = db.collection("groups_proposals").stream()
        proposals_list = [p.to_dict() for p in proposals]

        if not proposals_list:
            st.info("No hay propuestas aún")
        else:
            for prop in proposals_list:
                status_color = "🟡" if prop.get("status") == "pending" else "✅"
                st.markdown(f"{status_color} **{prop.get('group_code')} - {prop.get('group_name', 'N/A')}**")
                st.caption(f"Propuesto por: {prop.get('proposed_by')}")

                if prop.get("type") == "deletion":
                    st.markdown(f"**Razón para eliminar:** {prop.get('reason')}")
                else:
                    st.markdown(f"**Descripción:** {prop.get('description')}")
                    st.markdown(f"**Justificación:** {prop.get('justification')}")

                st.divider()

    except Exception as e:
        st.error(f"Error cargando propuestas: {e}")

# ── TAB 3: Estadísticas ────────────────────────────────────────────────────────
with tab3:
    st.markdown("### 📊 Resumen Estadístico")

    if not groups_summary:
        st.info("No hay datos para mostrar")
    else:
        # Tabla de grupos
        table_data = []
        for code, info in groups_summary.items():
            rating_info = ratings_summary.get(code, {})
            avg_rating = rating_info.get("avg_rating", 0)
            rating_count = rating_info.get("count", 0)

            table_data.append({
                "Código": code,
                "Grupo": info["name"],
                "Total": info["total"],
                "Validados": info["validated"],
                "% Val.": f"{info['validated']/max(info['total'], 1)*100:.0f}%",
                "Rating": f"{avg_rating:.1f}⭐ ({rating_count})" if avg_rating > 0 else "—",
            })

        df_summary = pd.DataFrame(table_data)
        st.dataframe(df_summary, use_container_width=True)

        # Gráficos
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Especies por Grupo")
            chart_data = {row["Código"]: row["Total"] for row in table_data}
            st.bar_chart(chart_data)

        with col2:
            st.markdown("#### % Validación por Grupo")
            val_data = {}
            for row in table_data:
                pct = int(row["% Val."].rstrip("%"))
                val_data[row["Código"]] = pct
            st.bar_chart(val_data)
