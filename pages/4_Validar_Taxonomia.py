"""
Validar Grupos Taxonómicos (Géneros/Familias) — Vista Detallada

Interfaz para validar especies agrupadas por género o familia:
- Ver todas las especies de un taxón
- Ver qué grupos funcionales están asignados
- Mover especies entre grupos (registra en audit_log)
- Eliminar especies (registra en audit_log)
"""

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import streamlit as st
import pandas as pd
from sql_client import (
    get_db,
    load_species,
    get_species_by_genus,
    get_species_by_family,
    get_taxon_summary,
    get_groups_summary,
    move_species,
    remove_species,
    expert_name_from_auth,
)

st.set_page_config(
    page_title="Validar Taxonomía",
    page_icon="🧬",
    layout="wide",
)

# ── Auth guard ─────────────────────────────────────────────────────────────────
if not st.session_state.get("auth"):
    st.warning("⚠️ Debes iniciar sesión primero. Ve a la página de **Inicio**.")
    st.stop()

expert = expert_name_from_auth(st.session_state.auth)
expert_email = st.session_state.get("auth", {}).get("email", "").lower()
db = get_db()

st.title("🧬 Validación de Grupos Taxonómicos")
st.caption(f"Experto: **{expert}**")
st.markdown(
    "Revisa y ajusta las asignaciones de especies agrupadas por **género** o **familia**. "
    "Puedes mover especies entre grupos o marcarlas como eliminadas."
)

# ── Load data ──────────────────────────────────────────────────────────────────
with st.spinner("Cargando datos…"):
    species_df = load_species(db)
    groups_summary = get_groups_summary(db)

if species_df.empty:
    st.error("No hay datos disponibles")
    st.stop()

# ── Main interface ─────────────────────────────────────────────────────────────

# 1. Choose taxonomy level
col1, col2 = st.columns(2)
with col1:
    taxon_type = st.radio(
        "Agrupar por:",
        ["Género", "Familia"],
        horizontal=True,
        help="¿Agrupar especies por género o familia?",
    )

taxon_type_key = "genus" if taxon_type == "Género" else "family"

# 2. Load grouped data
if taxon_type_key == "genus":
    taxa_dict = get_species_by_genus(db)
    label = "Géneros"
else:
    taxa_dict = get_species_by_family(db)
    label = "Familias"

if not taxa_dict:
    st.info(f"No hay {label.lower()} disponibles para validar.")
    st.stop()

# 3. Select taxon
taxon_names = sorted(taxa_dict.keys())
selected_taxon = st.selectbox(
    f"Selecciona un {taxon_type.lower()}:",
    taxon_names,
    help=f"Elige el {taxon_type.lower()} a validar",
)

# 4. Get taxon summary
summary = get_taxon_summary(selected_taxon, taxon_type_key, db)
species_df_taxon = summary.get("full_df", pd.DataFrame())

if species_df_taxon.empty:
    st.error(f"No hay datos para {selected_taxon}")
    st.stop()

# ── Display summary ────────────────────────────────────────────────────────────
st.markdown(f"### 📌 {taxon_type}: **{selected_taxon}**")

col_count, col_groups, col_pending = st.columns(3)
with col_count:
    st.metric("Total de especies", summary["count"])

with col_groups:
    st.metric("Grupos funcionales asignados", len(summary["groups"]))

with col_pending:
    pending_count = len(species_df_taxon[species_df_taxon["status"] != "validated"])
    st.metric("Pendientes de validar", pending_count)

# ── Display groups distribution ────────────────────────────────────────────────
if summary["groups"]:
    st.markdown("#### Distribución por grupo funcional")
    cols = st.columns(min(3, len(summary["groups"])))
    for idx, (code, name) in enumerate(summary["groups"].items()):
        count = len(summary["species_by_group"].get(code, []))
        with cols[idx % 3]:
            st.info(f"**{code}** — {name}\n{count} especie{'s' if count > 1 else ''}")

# ── Species table with actions ─────────────────────────────────────────────────
st.markdown("#### 🔧 Ajustar asignaciones de especies")

# Create a working copy for display
display_df = species_df_taxon[
    ["taxon", "current_code", "current_group", "status"]
].copy()
display_df = display_df.sort_values("taxon").reset_index(drop=True)

# Add action buttons
st.markdown("**Instrucciones:** Usa los botones para cada especie")

for idx, row in display_df.iterrows():
    species_name = row["taxon"]
    current_code = row["current_code"]
    current_group = row["current_group"]
    status = row["status"]

    # Create columns for each species row
    col_species, col_code, col_status, col_move, col_remove = st.columns(
        [2, 1.5, 1, 1, 1]
    )

    with col_species:
        st.write(species_name)

    with col_code:
        st.caption(f"{current_code}")

    with col_status:
        status_badge = "✅ Validado" if status == "validated" else "⏳ Pendiente"
        st.caption(status_badge)

    with col_move:
        if st.button("↔ Mover", key=f"move_{idx}_{species_name}"):
            st.session_state["dialog_action"] = "move"
            st.session_state["dialog_species_idx"] = idx
            st.session_state["dialog_species_name"] = species_name
            st.session_state["dialog_current_code"] = current_code
            st.session_state["dialog_current_group"] = current_group
            st.rerun()

    with col_remove:
        if st.button("🗑 Eliminar", key=f"remove_{idx}_{species_name}"):
            st.session_state["dialog_action"] = "remove"
            st.session_state["dialog_species_idx"] = idx
            st.session_state["dialog_species_name"] = species_name
            st.session_state["dialog_current_code"] = current_code
            st.session_state["dialog_current_group"] = current_group
            st.rerun()

# ── Dialog handlers (at page level) ────────────────────────────────────────────

# Dialog: Move species
if st.session_state.get("dialog_action") == "move":
    species_name = st.session_state.get("dialog_species_name", "")
    current_code = st.session_state.get("dialog_current_code", "")
    current_group = st.session_state.get("dialog_current_group", "")

    with st.dialog(f"Mover: {species_name}", width="small"):
        st.markdown(f"**{species_name}**")
        st.caption(f"Grupo actual: **{current_code}** — {current_group}")

        # Get available groups
        available_groups = {
            f"{c} — {n}": (c, n)
            for c, n in groups_summary.items()
            if c != current_code and c != "UNCLASSIFIED"
        }

        if available_groups:
            choice = st.selectbox(
                "Nuevo grupo:",
                list(available_groups.keys()),
                key="move_select",
            )
            note = st.text_input(
                "Nota (opcional):",
                placeholder="¿Por qué mueves esta especie?",
                key="move_note",
            )

            col1, col2 = st.columns(2)
            if col1.button("✓ Mover", type="primary", key="move_confirm"):
                to_code, to_name = available_groups[choice]
                move_species(
                    species_name,
                    current_code,
                    to_code,
                    to_name,
                    expert,
                    note,
                    db,
                )
                st.session_state["dialog_action"] = None
                st.rerun()

            if col2.button("✗ Cancelar", key="move_cancel"):
                st.session_state["dialog_action"] = None
                st.rerun()
        else:
            st.warning("No hay otros grupos disponibles para mover esta especie.")
            if st.button("Cerrar", key="move_close"):
                st.session_state["dialog_action"] = None
                st.rerun()

# Dialog: Remove species
if st.session_state.get("dialog_action") == "remove":
    species_name = st.session_state.get("dialog_species_name", "")
    current_code = st.session_state.get("dialog_current_code", "")
    current_group = st.session_state.get("dialog_current_group", "")

    with st.dialog(f"Eliminar: {species_name}", width="small"):
        st.markdown(f"**{species_name}**")
        st.caption(f"Grupo actual: **{current_code}** — {current_group}")
        st.warning(
            "⚠️ Esto marcará la especie como eliminada. "
            "Puedes restaurarla después si es necesario."
        )

        reason = st.text_area(
            "Justificación (obligatorio):",
            placeholder="¿Por qué eliminas esta especie?",
            key="remove_reason",
        )

        col1, col2 = st.columns(2)
        if col1.button(
            "✓ Eliminar",
            type="primary",
            disabled=not reason.strip(),
            key="remove_confirm",
        ):
            remove_species(
                species_name,
                current_code,
                expert,
                reason.strip(),
                db,
            )
            st.session_state["dialog_action"] = None
            st.rerun()

        if col2.button("✗ Cancelar", key="remove_cancel"):
            st.session_state["dialog_action"] = None
            st.rerun()

# ── Summary of changes ─────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("#### 📊 Resumen de acciones")

changes_count = len(
    species_df_taxon[
        (species_df_taxon["status"] != "validated")
        | (species_df_taxon.get("action") == "moved")
    ]
)

st.info(
    f"Se han registrado automáticamente los cambios en el audit log. "
    f"Las especies pendientes de validar: **{pending_count}**"
)

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    "💡 Consejo: Los cambios se registran directamente en la base de datos. "
    "Puedes ver el historial completo en **Resultados Finales**."
)
