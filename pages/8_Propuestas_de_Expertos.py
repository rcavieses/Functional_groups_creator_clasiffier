"""
Propuestas de Expertos — Revisión de cambios estructurales a grupos funcionales

Cada propuesta (dividir, fusionar, eliminar o crear un grupo) enviada por un experto desde
"Validar Grupos" se muestra aquí como una tarjeta: descripción del cambio, especies que
afecta (agrupables por nivel taxonómico) y dos acciones — aplicar o rechazar.
"""

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import streamlit as st
import pandas as pd
from sql_client import (
    get_db,
    get_group_proposals_df,
    get_species_for_group,
    resolve_group_proposal,
    apply_group_proposal_changes,
    expert_name_from_auth,
    REMOVE_TARGET,
)
from ui_helpers import run_db_action

DATA_DIR = Path(__file__).parent.parent / "data"
GROUPS_CSV = DATA_DIR / "functional_groups_final.csv"

st.set_page_config(page_title="Propuestas de Expertos", page_icon="🧩", layout="wide")

if not st.session_state.get("auth"):
    st.warning("⚠️ Debes iniciar sesión primero. Ve a la página de **Inicio**.")
    st.stop()

expert = expert_name_from_auth(st.session_state.auth)
db = get_db()

TYPE_ICON = {"modification": "✏️", "deletion": "🗑️", "new_group": "✨"}
TYPE_LABEL = {"modification": "Modificar grupo", "deletion": "Eliminar grupo", "new_group": "Nuevo grupo"}
STATUS_BADGE = {"pending": "⏳ Pendiente", "approved": "✅ Aplicada", "rejected": "❌ Rechazada"}
LEVEL_COL = {"Género": "genus", "Familia": "family", "Orden": "order_taxon", "Clase": "class_taxon", "Filum": "phylum"}


@st.cache_data
def load_groups() -> dict[str, str]:
    gdf = pd.read_csv(GROUPS_CSV)
    return dict(zip(gdf["Code"].str.strip(), gdf["Functional_Group"].str.strip()))


all_groups = load_groups()

st.title("🧩 Propuestas de Expertos")
st.caption(
    "Cambios estructurales a grupos funcionales sugeridos por los expertos "
    "(dividir, fusionar, eliminar o crear un grupo). Cada tarjeta muestra a qué especies "
    "afecta hoy y permite aplicar el cambio (moviéndolas/eliminándolas) o rechazarlo."
)

if st.button("🔄 Recargar", use_container_width=False):
    get_group_proposals_df(db, force=True)
    st.rerun()

df = get_group_proposals_df(db)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total propuestas", len(df))
m2.metric("⏳ Pendientes", int((df["status"] == "pending").sum()) if not df.empty else 0)
m3.metric("✅ Aplicadas", int((df["status"] == "approved").sum()) if not df.empty else 0)
m4.metric("❌ Rechazadas", int((df["status"] == "rejected").sum()) if not df.empty else 0)
st.divider()

if df.empty:
    st.info("Aún no hay propuestas de expertos.")
    st.stop()

status_filter = st.selectbox("Mostrar propuestas con estado:", ["Pendientes", "Todas", "Aplicadas", "Rechazadas"])
if status_filter == "Pendientes":
    view = df[df["status"] == "pending"]
elif status_filter == "Aplicadas":
    view = df[df["status"] == "approved"]
elif status_filter == "Rechazadas":
    view = df[df["status"] == "rejected"]
else:
    view = df

if view.empty:
    st.info("No hay propuestas con ese filtro.")
    st.stop()

target_options = ["— No mover especies —"] + [f"{code} — {name}" for code, name in sorted(all_groups.items())
                                                if not code.startswith("PROP_")] + ["🗑️ Eliminar especies seleccionadas"]

for _, prop in view.iterrows():
    pid = int(prop["id"])
    ptype = prop.get("type", "modification")
    code = prop.get("group_code", "—")
    name = prop.get("group_name", "—")
    status = prop.get("status", "pending")
    icon = TYPE_ICON.get(ptype, "🔹")

    affected = get_species_for_group(code, db)
    n_affected = len(affected)

    with st.container(border=True):
        st.markdown(f"## {icon} {code} — {name}")
        st.caption(
            f"{TYPE_LABEL.get(ptype, ptype)} · Propuesto por **{prop.get('proposed_by')}** · "
            f"{pd.to_datetime(prop['proposed_at']).strftime('%Y-%m-%d')} · {STATUS_BADGE.get(status, status)}"
        )

        if ptype == "deletion":
            st.markdown(f"**Razón para eliminar:** {prop.get('reason') or '—'}")
        elif ptype == "modification":
            st.markdown(f"**Modificación sugerida:** {prop.get('reason') or '—'}")
        else:
            st.markdown(f"**Descripción:** {prop.get('description') or '—'}")
            if prop.get("justification"):
                st.markdown(f"**Justificación:** {prop.get('justification')}")

        st.metric("Especies afectadas (actualmente en este grupo)", n_affected)

        selected_taxa: list[str] = []
        if n_affected > 0:
            with st.expander(f"🔍 Ver especies del grupo ({n_affected})"):
                level = st.radio(
                    "Agrupar por:", ["Especie", "Género", "Familia", "Orden", "Clase", "Filum"],
                    horizontal=True, key=f"level_{pid}",
                )
                show = affected.copy()
                checkbox_col = st.column_config.CheckboxColumn(
                    "Seleccionar", help="Incluir en la acción de aplicar (mover/eliminar)"
                )

                if level == "Especie":
                    tbl = show[["taxon", "current_group", "status"]].rename(
                        columns={"taxon": "Especie", "current_group": "Grupo actual", "status": "Estado"}
                    ).reset_index(drop=True)
                    tbl.insert(0, "Seleccionar", False)
                    edited = st.data_editor(
                        tbl, use_container_width=True, hide_index=True, height=280,
                        key=f"editor_{pid}_{level}",
                        disabled=[c for c in tbl.columns if c != "Seleccionar"],
                        column_config={"Seleccionar": checkbox_col},
                    )
                    selected_taxa = list(edited.loc[edited["Seleccionar"], "Especie"])
                else:
                    group_col = LEVEL_COL[level]
                    grouped = show.groupby(group_col).agg(
                        Especies=("taxon", "count"),
                        Ejemplos=("taxon", lambda s: ", ".join(s.head(3))),
                    ).reset_index().rename(columns={group_col: level})
                    grouped.insert(1, "Seleccionar", False)
                    edited = st.data_editor(
                        grouped, use_container_width=True, hide_index=True, height=280,
                        key=f"editor_{pid}_{level}",
                        disabled=[c for c in grouped.columns if c != "Seleccionar"],
                        column_config={"Seleccionar": checkbox_col},
                    )
                    picked = set(edited.loc[edited["Seleccionar"], level])
                    selected_taxa = list(show[show[group_col].isin(picked)]["taxon"])

        target_label = None
        if n_affected > 0 and status == "pending":
            target_label = st.selectbox(
                "Al aplicar, mover las especies seleccionadas a:", target_options, key=f"target_{pid}",
            )

        bc1, bc2 = st.columns(2)
        apply_disabled = status != "pending"
        if bc1.button("✅ Aplicar cambios", key=f"apply_{pid}", type="primary",
                      use_container_width=True, disabled=apply_disabled):
            def _do_apply(pid=pid, code=code, target_label=target_label, selected_taxa=selected_taxa, prop=prop):
                if selected_taxa and target_label and target_label != "— No mover especies —":
                    if target_label == "🗑️ Eliminar especies seleccionadas":
                        to_code, to_name = REMOVE_TARGET, None
                    else:
                        to_code, to_name = target_label.split(" — ", 1)
                    apply_group_proposal_changes(
                        selected_taxa, code, to_code, to_name, expert,
                        f"Aplicado desde propuesta de experto #{pid} ({prop.get('proposed_by')}): {prop.get('reason') or prop.get('description') or ''}",
                        db,
                    )
                resolve_group_proposal(pid, "approved", expert, db, note=prop.get("reason") or prop.get("description") or "")

            if run_db_action(_do_apply, spinner="Aplicando cambio…"):
                st.success("Propuesta aplicada.")
                st.rerun()

        if bc2.button("❌ Rechazar", key=f"reject_{pid}", use_container_width=True, disabled=apply_disabled):
            if run_db_action(
                lambda: resolve_group_proposal(pid, "rejected", expert, db,
                                                note=prop.get("reason") or prop.get("description") or ""),
                spinner="Registrando rechazo…",
            ):
                st.warning("Propuesta rechazada.")
                st.rerun()
