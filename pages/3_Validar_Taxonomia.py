"""
Validar Grupos Taxonómicos (Géneros/Familias) — Vista Detallada

Flujo: primero se elige el grupo funcional, luego se ven los géneros o
familias que contiene, y se puede validar todo un género/familia de una vez.
"""

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import streamlit as st
import pandas as pd
from sql_client import (
    get_db,
    load_species,
    get_species_for_group,
    get_groups_summary,
    get_removed_species,
    move_species,
    remove_species,
    restore_species,
    validate_species_bulk,
    expert_name_from_auth,
)

DATA_DIR = Path(__file__).parent.parent / "data"
GROUPS_CSV = DATA_DIR / "functional_groups_final.csv"

st.set_page_config(page_title="Validar Taxonomía", page_icon="🧬", layout="wide")

# ── Auth guard ─────────────────────────────────────────────────────────────────
if not st.session_state.get("auth"):
    st.warning("⚠️ Debes iniciar sesión primero. Ve a la página de **Inicio**.")
    st.stop()

expert = expert_name_from_auth(st.session_state.auth)
db = get_db()


@st.cache_data
def load_groups() -> dict[str, str]:
    gdf = pd.read_csv(GROUPS_CSV)
    return dict(zip(gdf["Code"].str.strip(), gdf["Functional_Group"].str.strip()))


all_groups = load_groups()
nav_groups = {c: n for c, n in all_groups.items() if not c.startswith("PROP_")}

groups_summary = get_groups_summary(db)
if "UNCLASSIFIED" in groups_summary:
    nav_groups["UNCLASSIFIED"] = "Sin clasificar"

st.title("🧬 Validación de Grupos Taxonómicos")
st.caption(f"Experto: **{expert}**")
st.markdown(
    "Elige un **grupo funcional**, revisa qué **géneros o familias** contiene, "
    "y valida todo un género/familia de una sola vez."
)

# ── Load data ──────────────────────────────────────────────────────────────────
with st.spinner("Cargando datos…"):
    species_df = load_species(db)

if species_df.empty:
    st.error("No hay datos disponibles")
    st.stop()

# ── 1. Select functional group ──────────────────────────────────────────────────
group_options = sorted(nav_groups.keys())


def _fmt_group(code: str) -> str:
    s = groups_summary.get(code, {"total": 0, "pending": 0})
    return f"{code} — {nav_groups.get(code, code)} ({s.get('total', 0)} especies, {s.get('pending', 0)} pendientes)"


selected_code = st.selectbox(
    "1️⃣ Selecciona un grupo funcional:",
    group_options,
    format_func=_fmt_group,
)
group_name = nav_groups.get(selected_code, selected_code)

group_df = get_species_for_group(selected_code, db)
if group_df.empty:
    st.info(f"El grupo **{group_name}** no tiene especies activas.")
    st.stop()

# ── 2. Choose taxonomy level to inspect the group by ────────────────────────────
taxon_type = st.radio(
    "2️⃣ Ver géneros o familias dentro de este grupo:",
    ["Género", "Familia"],
    horizontal=True,
)
tax_col = "genus" if taxon_type == "Género" else "family"

if tax_col not in group_df.columns:
    st.warning(f"No hay datos de {taxon_type.lower()} para este grupo.")
    st.stop()

breakdown = group_df.dropna(subset=[tax_col]).groupby(tax_col)
taxa_list = sorted(breakdown.groups.keys())

if not taxa_list:
    st.info(f"No hay {taxon_type.lower()}s registrados para las especies de este grupo.")
else:
    search_term = st.text_input(
        f"🔎 Buscar {taxon_type.lower()}:",
        key=f"search_{tax_col}_{selected_code}",
        placeholder=f"Filtrar {taxon_type.lower()}s por nombre…",
    ).strip().lower()

    filtered_taxa = (
        [t for t in taxa_list if search_term in t.lower()] if search_term else taxa_list
    )

    st.markdown(
        f"### 📌 {group_name} — {len(filtered_taxa)} de {len(taxa_list)} {taxon_type.lower()}(s)"
    )

    if not filtered_taxa:
        st.info(f"Ningún {taxon_type.lower()} coincide con «{search_term}».")

    for taxon_name in filtered_taxa:
        sub_df = breakdown.get_group(taxon_name).sort_values("taxon")
        pending = sub_df[sub_df["status"] == "pending"]
        pending_taxa = pending["taxon"].tolist()

        with st.expander(
            f"{'🧬' if pending_taxa else '✅'} **{taxon_name}** — "
            f"{len(sub_df)} especie(s), {len(pending_taxa)} pendiente(s)"
        ):
            col_validate, col_spacer = st.columns([1, 3])
            with col_validate:
                if st.button(
                    "✅ Validar todo",
                    key=f"bulk_validate_{tax_col}_{taxon_name}",
                    disabled=not pending_taxa,
                    help=f"Marca como validadas las {len(pending_taxa)} especies pendientes de {taxon_name}",
                ):
                    validate_species_bulk(pending_taxa, expert, db)
                    st.success(f"{len(pending_taxa)} especies de {taxon_name} validadas.")
                    st.rerun()

            for _, row in sub_df.iterrows():
                sp_name = row["taxon"]
                status = row["status"]
                c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                with c1:
                    st.write(sp_name)
                with c2:
                    st.caption("✅ Validado" if status == "validated" else "⏳ Pendiente")
                with c3:
                    if st.button("↔", key=f"mv_{tax_col}_{taxon_name}_{sp_name}", help="Mover a otro grupo"):
                        st.session_state["dialog_action"] = "move"
                        st.session_state["dialog_species_name"] = sp_name
                        st.session_state["dialog_current_code"] = selected_code
                        st.session_state["dialog_current_group"] = group_name
                        st.rerun()
                with c4:
                    if st.button("🗑", key=f"rm_{tax_col}_{taxon_name}_{sp_name}", help="Eliminar"):
                        st.session_state["dialog_action"] = "remove"
                        st.session_state["dialog_species_name"] = sp_name
                        st.session_state["dialog_current_code"] = selected_code
                        st.session_state["dialog_current_group"] = group_name
                        st.rerun()

# ── 3. Ajustar asignaciones de especies (vista alternativa) ────────────────────
st.markdown("---")
st.markdown("#### 🔧 Ajustar asignaciones de especies")

view_by = st.selectbox(
    "Ajustar asignaciones de especie por:",
    ["Género", "Grupo", "Eliminados"],
    help=(
        "Género: agrupa la tabla de especies por género. "
        "Grupo: lista plana de todas las especies del grupo funcional seleccionado. "
        "Eliminados: muestra las especies eliminadas de este grupo, con opción de restaurar."
    ),
)

if view_by == "Eliminados":
    removed_all = get_removed_species(db)
    group_removed = (
        removed_all[removed_all["original_code"] == selected_code]
        if not removed_all.empty and "original_code" in removed_all.columns
        else pd.DataFrame()
    )
    if group_removed.empty:
        st.info("No hay especies eliminadas en este grupo.")
    else:
        for _, row in group_removed.iterrows():
            rt = row["taxon"]
            by = row.get("last_modified_by", "—")
            rc1, rc2, rc3 = st.columns([5, 3, 2])
            rc1.markdown(f"~~{rt}~~")
            rc2.markdown(by)
            if rc3.button("↩ Restaurar", key=f"restore_{rt}"):
                restore_species(rt, row["original_code"], row["original_group"], expert, db)
                st.rerun()
else:
    if view_by == "Género":
        display_df = group_df.dropna(subset=["genus"]).sort_values(["genus", "taxon"])
    else:
        display_df = group_df.sort_values("taxon")

    adj_search = st.text_input(
        "🔎 Buscar por género o especie:" if view_by == "Género" else "🔎 Buscar especie:",
        key=f"adj_search_{view_by}_{selected_code}",
        placeholder="Filtrar por nombre…",
    ).strip().lower()

    if adj_search:
        if view_by == "Género":
            mask = display_df["genus"].str.lower().str.contains(adj_search, na=False) | display_df[
                "taxon"
            ].str.lower().str.contains(adj_search, na=False)
        else:
            mask = display_df["taxon"].str.lower().str.contains(adj_search, na=False)
        display_df = display_df[mask]

    st.caption(f"{len(display_df)} especie(s) mostradas.")
    if display_df.empty:
        st.info(f"Ninguna especie coincide con «{adj_search}».")

    for _, row in display_df.iterrows():
        sp_name = row["taxon"]
        status = row["status"]
        col_species, col_extra, col_status, col_move, col_remove = st.columns([2, 1.5, 1, 1, 1])
        with col_species:
            st.write(sp_name)
        with col_extra:
            if view_by == "Género":
                st.caption(str(row.get("genus", "")))
        with col_status:
            st.caption("✅ Validado" if status == "validated" else "⏳ Pendiente")
        with col_move:
            if st.button("↔ Mover", key=f"adj_move_{sp_name}"):
                st.session_state["dialog_action"] = "move"
                st.session_state["dialog_species_name"] = sp_name
                st.session_state["dialog_current_code"] = selected_code
                st.session_state["dialog_current_group"] = group_name
                st.rerun()
        with col_remove:
            if st.button("🗑 Eliminar", key=f"adj_remove_{sp_name}"):
                st.session_state["dialog_action"] = "remove"
                st.session_state["dialog_species_name"] = sp_name
                st.session_state["dialog_current_code"] = selected_code
                st.session_state["dialog_current_group"] = group_name
                st.rerun()

# ── Dialog handlers (at page level) ────────────────────────────────────────────
if st.session_state.get("dialog_action") == "move":
    species_name = st.session_state.get("dialog_species_name", "")
    current_code = st.session_state.get("dialog_current_code", "")
    current_group = st.session_state.get("dialog_current_group", "")

    with st.dialog(f"Mover: {species_name}", width="small"):
        st.markdown(f"**{species_name}**")
        st.caption(f"Grupo actual: **{current_code}** — {current_group}")

        available_groups = {
            f"{c} — {n}": (c, n)
            for c, n in nav_groups.items()
            if c != current_code and c != "UNCLASSIFIED"
        }

        if available_groups:
            choice = st.selectbox("Nuevo grupo:", list(available_groups.keys()), key="move_select")
            note = st.text_input(
                "Nota (opcional):", placeholder="¿Por qué mueves esta especie?", key="move_note"
            )

            col1, col2 = st.columns(2)
            if col1.button("✓ Mover", type="primary", key="move_confirm"):
                to_code, to_name = available_groups[choice]
                move_species(species_name, current_code, to_code, to_name, expert, note, db)
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
        if col1.button("✓ Eliminar", type="primary", disabled=not reason.strip(), key="remove_confirm"):
            remove_species(species_name, current_code, expert, reason.strip(), db)
            st.session_state["dialog_action"] = None
            st.rerun()

        if col2.button("✗ Cancelar", key="remove_cancel"):
            st.session_state["dialog_action"] = None
            st.rerun()

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    "💡 Consejo: Los cambios se registran directamente en la base de datos. "
    "Puedes ver el historial completo en **Resultados**."
)
