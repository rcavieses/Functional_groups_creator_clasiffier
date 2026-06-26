"""
Validar Grupos Funcionales — Vista de Fichas

Interfaz principal para validar grupos completos:
- Ver estadísticas de cada grupo con su descripción/características
- Ver qué grupos están asignados al experto actual
- Calificar grupos (1-5 estrellas)
- Proponer eliminación con argumento
- Proponer nuevo grupo con descripción
"""

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import streamlit as st
import pandas as pd
from sql_client import (
    get_db,
    load_species,
    get_groups_summary,
    rate_group,
    get_my_group_rating,
    propose_group_deletion,
    propose_new_group_detailed,
    get_group_rating_summary,
    get_proposed_groups,
    get_group_descriptions,
    get_my_assignments,
    get_assignment_stats,
    propose_group_modification,
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

auth = st.session_state.get("auth", {})
expert_name = st.session_state.get("expert_name", "")
expert_email = auth.get("email", "").lower()
db = get_db()

st.title("📊 Validación de Grupos Funcionales")
st.caption(f"Experto: **{expert_name}**")

# ── Cargar datos ───────────────────────────────────────────────────────────────
with st.spinner("Cargando datos…"):
    species_df = load_species(db)
    groups_summary = get_groups_summary(db)
    ratings_summary = get_group_rating_summary(db)
    descriptions = get_group_descriptions(db)
    my_assignments = set(get_my_assignments(expert_email, db))
    assignment_stats = get_assignment_stats(db)

if species_df.empty:
    st.error("No hay datos disponibles")
    st.stop()

# ── Tabs principales ───────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["🎯 Validar Grupos", "💡 Propuestas", "📊 Estadísticas"])

# ── TAB 1: Validar Grupos (Fichas) ─────────────────────────────────────────────
with tab1:
    st.markdown("### Fichas de Grupos Funcionales")

    if not groups_summary:
        st.info("No hay grupos para validar")
    else:
        # ── Filtro de vista ────────────────────────────────────────────────────
        assignments_exist = bool(my_assignments)
        if assignments_exist:
            col_filter, col_info = st.columns([2, 5])
            with col_filter:
                view_mode = st.radio(
                    "Mostrar:",
                    ["Mis grupos asignados", "Todos los grupos"],
                    horizontal=True,
                )
            with col_info:
                st.info(
                    f"📌 Tienes **{len(my_assignments)}** grupos asignados para evaluar. "
                    "Puedes ver todos los grupos, pero se te pide que califiques los marcados con 📌."
                )
        else:
            view_mode = "Todos los grupos"
            st.caption("Sin asignaciones aún — puedes calificar cualquier grupo.")

        all_codes = sorted(c for c in groups_summary.keys() if c != "UNCLASSIFIED")
        if view_mode == "Mis grupos asignados" and assignments_exist:
            display_codes = [c for c in all_codes if c in my_assignments]
        else:
            display_codes = all_codes

        if not display_codes:
            st.info("No hay grupos en esta vista.")
        else:
            cols = st.columns(3)
            for col_idx, group_code in enumerate(display_codes):
                group_info = groups_summary[group_code]
                col = cols[col_idx % 3]

                with col:
                    is_assigned = group_code in my_assignments
                    with st.container(border=True):
                        # Encabezado con badge de asignación
                        header_parts = [f"### {group_code}"]
                        if is_assigned:
                            header_parts.append("📌")
                        st.markdown(" ".join(header_parts))
                        st.markdown(f"**{group_info['name']}**")

                        if is_assigned:
                            st.caption("📌 _Asignado para tu evaluación_")

                        # Descripción / características
                        desc = descriptions.get(group_code, "").strip()
                        if desc:
                            st.markdown("📋 **Características:**")
                            st.caption(desc)

                        # Estadísticas principales
                        species_count = group_info["total"]
                        validated_count = group_info["validated"]

                        col_m1, col_m2 = st.columns(2)
                        col_m1.metric("Especies", f"{species_count}", f"{validated_count} validadas")

                        n_evals = assignment_stats.get(group_code, 0)
                        col_m2.metric("Expertos asignados", f"{n_evals}")

                        # Rating
                        if group_code in ratings_summary:
                            avg_rating = ratings_summary[group_code]["avg_rating"]
                            count = ratings_summary[group_code]["count"]
                            st.markdown(f"⭐ **{avg_rating:.1f}/5** ({count} calificaciones)")
                        else:
                            st.markdown("⭐ **Sin calificaciones aún**")

                        # Calificación propia de este experto (si ya calificó)
                        my_rating = get_my_group_rating(group_code, expert_name, db)
                        if my_rating and my_rating["rating"]:
                            st.caption(f"📝 Tu calificación actual: **{my_rating['rating']}⭐** — puedes modificarla")

                        st.divider()

                        # Acciones
                        st.markdown("**Acciones:**")

                        col_a, col_b = st.columns(2)

                        default_rating = my_rating["rating"] if my_rating and my_rating["rating"] else 1
                        with col_a:
                            rating = st.selectbox(
                                "Calificación",
                                [1, 2, 3, 4, 5],
                                index=default_rating - 1,
                                key=f"rating_{group_code}",
                                label_visibility="collapsed",
                            )

                        rate_btn_label = "✏️ Modificar" if my_rating else "⭐ Calificar"
                        with col_b:
                            if st.button(rate_btn_label, key=f"btn_rate_{group_code}", use_container_width=True):
                                st.session_state[f"show_comment_{group_code}"] = True

                        if st.session_state.get(f"show_comment_{group_code}"):
                            comment = st.text_area(
                                "Comentario (opcional)",
                                value=(my_rating["comment"] if my_rating else ""),
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

                        # Sugerir modificación
                        if st.button("✏️ Sugerir modificación", key=f"btn_modify_{group_code}", use_container_width=True):
                            st.session_state[f"show_modify_{group_code}"] = True

                        if st.session_state.get(f"show_modify_{group_code}"):
                            suggestion = st.text_area(
                                "¿Qué modificación propones?",
                                key=f"modify_text_{group_code}",
                                height=80,
                                placeholder="Describe el cambio que sugieres para este grupo…",
                            )
                            if st.button("✓ Enviar sugerencia", key=f"send_modify_{group_code}", use_container_width=True):
                                if suggestion.strip():
                                    try:
                                        propose_group_modification(
                                            group_code,
                                            group_info["name"],
                                            suggestion,
                                            expert_name,
                                            db,
                                        )
                                        st.success("✅ Sugerencia enviada")
                                        st.session_state[f"show_modify_{group_code}"] = False
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Error: {e}")
                                else:
                                    st.warning("Ingresa una sugerencia")

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

    st.markdown("### 📋 Propuestas Pendientes")
    try:
        proposals_list = get_proposed_groups(db)

        if not proposals_list:
            st.info("No hay propuestas aún")
        else:
            for prop in proposals_list:
                status_color = "🟡" if prop.get("status") == "pending" else "✅"
                st.markdown(f"{status_color} **{prop.get('group_code')} - {prop.get('group_name', 'N/A')}**")
                st.caption(f"Propuesto por: {prop.get('proposed_by')}")

                if prop.get("type") == "deletion":
                    st.markdown(f"**Razón para eliminar:** {prop.get('reason')}")
                elif prop.get("type") == "modification":
                    st.markdown(f"**Modificación sugerida:** {prop.get('reason')}")
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
        table_data = []
        for code, info in groups_summary.items():
            if code == "UNCLASSIFIED":
                continue
            rating_info = ratings_summary.get(code, {})
            avg_rating = rating_info.get("avg_rating", 0)
            rating_count = rating_info.get("count", 0)
            n_assigned = assignment_stats.get(code, 0)

            table_data.append({
                "Código": code,
                "Grupo": info["name"],
                "Total": info["total"],
                "Validados": info["validated"],
                "% Val.": f"{info['validated']/max(info['total'], 1)*100:.0f}%",
                "Calificaciones": f"{avg_rating:.1f}⭐ ({rating_count})" if avg_rating > 0 else "—",
                "Expertos asignados": n_assigned,
            })

        df_summary = pd.DataFrame(table_data)
        st.dataframe(df_summary, use_container_width=True)

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Especies por Grupo")
            chart_data = {row["Código"]: row["Total"] for row in table_data}
            st.bar_chart(chart_data)

        with col2:
            st.markdown("#### Expertos asignados por Grupo")
            assign_data = {row["Código"]: row["Expertos asignados"] for row in table_data}
            st.bar_chart(assign_data)
