import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

import streamlit as st
import pandas as pd
from firebase_client import (
    expert_name_from_auth,
    get_db,
    load_species,
    get_species_for_group,
    get_groups_summary,
    get_removed_species,
    validate_species,
    remove_species,
    move_species,
    restore_species,
    propose_new_group,
)

DATA_DIR = Path(__file__).parent.parent.parent / "data"
GROUPS_CSV = DATA_DIR / "functional_groups_final.csv"

st.set_page_config(page_title="Validar Grupos", page_icon="✅", layout="wide")

# ── Auth guard ─────────────────────────────────────────────────────────────────
if not st.session_state.get("auth"):
    st.warning("⚠️ Debes iniciar sesión primero. Ve a la página de **Inicio**.")
    st.stop()

expert = expert_name_from_auth(st.session_state.auth)
db = get_db()


# ── Load groups reference (cached forever — static data) ──────────────────────
@st.cache_data
def load_groups() -> dict[str, str]:
    gdf = pd.read_csv(GROUPS_CSV)
    return dict(zip(gdf["Code"].str.strip(), gdf["Functional_Group"].str.strip()))


all_groups = load_groups()
# Exclude proposed-group codes (PROP_*) from the navigation list
nav_groups = {c: n for c, n in all_groups.items() if not c.startswith("PROP_")}


# ── Dialogs ────────────────────────────────────────────────────────────────────

@st.dialog("↔ Mover especie", width="small")
def dlg_move(taxon: str, from_code: str):
    st.markdown(f"**{taxon}**")
    st.caption(f"Grupo actual: {from_code} — {all_groups.get(from_code, '')}")
    options = {f"{c} — {n}": (c, n) for c, n in nav_groups.items() if c != from_code}
    choice = st.selectbox("Grupo destino:", list(options.keys()))
    note = st.text_input("Nota (opcional):", placeholder="¿Por qué mueves esta especie?")
    col1, col2 = st.columns(2)
    if col1.button("Mover", type="primary", use_container_width=True):
        to_code, to_name = options[choice]
        move_species(taxon, from_code, to_code, to_name, expert, note, db)
        st.rerun()
    if col2.button("Cancelar", use_container_width=True):
        st.rerun()


@st.dialog("💡 Proponer nuevo grupo funcional", width="large")
def dlg_propose(taxon: str, from_code: str):
    st.markdown(f"Proponer nuevo grupo para **{taxon}**")
    st.caption(
        "Tu propuesta será visible en **Resultados Finales** para revisión del equipo. "
        "La especie quedará asignada al grupo propuesto."
    )
    col1, col2 = st.columns([3, 1])
    with col1:
        group_name_new = st.text_input("Nombre del grupo:", placeholder="Ej. Aves playeras costeras")
    with col2:
        group_code_new = st.text_input("Código (máx 6):", placeholder="Ej. APC", max_chars=6)
    description = st.text_area(
        "Composición / descripción:",
        placeholder="¿Qué tipos de organismos componen este grupo? ¿Cuál es su rol ecológico?",
        height=100,
    )
    valid = bool(group_name_new.strip() and group_code_new.strip() and description.strip())
    col_ok, col_cancel = st.columns(2)
    if col_ok.button("Proponer y reasignar", type="primary", disabled=not valid, use_container_width=True):
        propose_new_group(
            taxon, from_code,
            group_name_new.strip(), group_code_new.strip(), description.strip(),
            expert, db,
        )
        st.rerun()
    if col_cancel.button("Cancelar", use_container_width=True):
        st.rerun()


@st.dialog("🗑 Confirmar eliminación", width="small")
def dlg_remove(taxon: str, current_code: str):
    st.warning(f"¿Quitar **{taxon}** del modelo?")
    st.caption(
        "Úsalo para taxa que no son marinos, son duplicados o no pertenecen "
        "al ecosistema del Golfo de California. Se puede restaurar después."
    )
    note = st.text_input("Razón (opcional):", placeholder="Ej. Ave terrestre, no marina")
    col1, col2 = st.columns(2)
    if col1.button("🗑 Confirmar", type="primary", use_container_width=True):
        remove_species(taxon, current_code, expert, note, db)
        st.rerun()
    if col2.button("Cancelar", use_container_width=True):
        st.rerun()


# ── Sidebar: group selector ────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"**👤 {expert}**")
    st.divider()
    st.subheader("Grupos Funcionales")

    if st.button("🔄 Recargar desde Firebase", use_container_width=True,
                 help="Recarga todos los datos (usa ~5000 lecturas). Solo necesario para ver cambios de otros expertos."):
        load_species(db, force=True)
        st.rerun()

    filter_opt = st.radio(
        "Mostrar:",
        ["Todos", "Con pendientes", "Completados"],
        horizontal=True,
    )

    # Summary computed from in-memory cache — zero Firestore reads
    summary = get_groups_summary(db)

    if "selected_group" not in st.session_state:
        st.session_state.selected_group = list(nav_groups.keys())[0]

    for code, name in nav_groups.items():
        s = summary.get(code, {"total": 0, "validated": 0, "pending": 0})
        total_g = s["total"]
        pending_g = s["pending"]

        if filter_opt == "Con pendientes" and pending_g == 0:
            continue
        if filter_opt == "Completados" and pending_g > 0:
            continue

        if total_g == 0:
            icon = "⬜"
        elif pending_g == 0:
            icon = "✅"
        else:
            icon = "⏳"

        label = f"{icon} {code} — {name[:22]}… ({total_g})" if len(name) > 22 else f"{icon} {code} — {name} ({total_g})"
        is_selected = st.session_state.selected_group == code

        if st.button(
            label,
            key=f"grp_{code}",
            use_container_width=True,
            type="primary" if is_selected else "secondary",
        ):
            st.session_state.selected_group = code
            st.rerun()


# ── Main: group detail ─────────────────────────────────────────────────────────
selected_code = st.session_state.get("selected_group")
if not selected_code:
    st.info("Selecciona un grupo en el menú lateral.")
    st.stop()

group_name = nav_groups.get(selected_code, selected_code)
st.title(f"`{selected_code}` — {group_name}")

with st.spinner("Cargando especies del grupo…"):
    species_df = get_species_for_group(selected_code, db)

# Toolbar
col_stats, col_filter = st.columns([3, 1])
with col_stats:
    if species_df.empty:
        st.info("Este grupo no tiene taxa activos.")
    else:
        n_total = len(species_df)
        n_val = int((species_df["status"] == "validated").sum())
        n_pend = int((species_df["status"] == "pending").sum())
        h = int((species_df["confidence"] == "high").sum())
        m = int((species_df["confidence"] == "medium").sum())
        lo = int((species_df["confidence"] == "low").sum())
        st.caption(
            f"**{n_total} taxa** · ✅ {n_val} validados · ⏳ {n_pend} pendientes &nbsp;|&nbsp; "
            f"🟢 {h} alta · 🟡 {m} media · 🔴 {lo} baja"
        )

with col_filter:
    conf_filter = st.selectbox(
        "Filtrar confianza:",
        ["Todos", "high", "medium", "low"],
        key="conf_filter",
    )

if species_df.empty:
    st.stop()

# Apply filter
display_df = species_df.copy()
if conf_filter != "Todos":
    display_df = display_df[display_df["confidence"] == conf_filter]

# Sort: pending first, then alphabetical
status_order = {"pending": 0, "validated": 1}
display_df = display_df.sort_values(
    ["status", "taxon"],
    key=lambda col: col.map(status_order).fillna(2) if col.name == "status" else col,
).reset_index(drop=True)

st.divider()

# Column headers
hcols = st.columns([5, 2, 2, 1, 1, 1, 1])
hcols[0].markdown("**Taxon**")
hcols[1].markdown("**Estado**")
hcols[2].markdown("**Confianza LLM**")
hcols[3].markdown("**✅**")
hcols[4].markdown("**↔**")
hcols[5].markdown("**💡**")
hcols[6].markdown("**🗑**")
st.divider()

CONF_ICON = {"high": "🟢 alta", "medium": "🟡 media", "low": "🔴 baja"}

for _, row in display_df.iterrows():
    taxon = row["taxon"]
    status = row.get("status", "pending")
    confidence = row.get("confidence", "?")
    modified_by = row.get("last_modified_by") or ""

    cols = st.columns([5, 2, 2, 1, 1, 1, 1])

    with cols[0]:
        st.markdown(f"*{taxon}*")
        if modified_by:
            st.caption(f"↳ {modified_by}")

    with cols[1]:
        if status == "validated":
            st.markdown("✅ Validado")
        else:
            st.markdown("⏳ Pendiente")

    with cols[2]:
        st.markdown(CONF_ICON.get(confidence, f"⚪ {confidence}"))

    with cols[3]:
        if st.button("✅", key=f"ok_{taxon}", help="Confirmar: clasificación correcta"):
            validate_species(taxon, expert, db)
            st.rerun()

    with cols[4]:
        if st.button("↔", key=f"mv_{taxon}", help="Mover a otro grupo"):
            dlg_move(taxon, selected_code)

    with cols[5]:
        if st.button("💡", key=f"np_{taxon}", help="Proponer nuevo grupo funcional"):
            dlg_propose(taxon, selected_code)

    with cols[6]:
        if st.button("🗑", key=f"rm_{taxon}", help="Quitar del modelo (no marino / irrelevante)"):
            dlg_remove(taxon, selected_code)

# ── Removed taxa accordion ─────────────────────────────────────────────────────
removed_all = get_removed_species(db)
if not removed_all.empty and "original_code" in removed_all.columns:
    group_removed = removed_all[removed_all["original_code"] == selected_code]
    if not group_removed.empty:
        st.divider()
        with st.expander(f"🗑️ Taxa removidos de este grupo ({len(group_removed)}) — click para ver"):
            r_hcols = st.columns([5, 3, 2])
            r_hcols[0].markdown("**Taxon**")
            r_hcols[1].markdown("**Removido por**")
            r_hcols[2].markdown("**Restaurar**")
            for _, rrow in group_removed.iterrows():
                rt = rrow["taxon"]
                by = rrow.get("last_modified_by", "—")
                rc1, rc2, rc3 = st.columns([5, 3, 2])
                rc1.markdown(f"~~{rt}~~")
                rc2.markdown(by)
                if rc3.button("↩ Restaurar", key=f"rst_{rt}"):
                    restore_species(rt, rrow["original_code"], rrow["original_group"], expert, db)
                    st.rerun()
