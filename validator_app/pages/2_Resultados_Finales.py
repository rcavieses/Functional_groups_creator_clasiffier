import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

import streamlit as st
import pandas as pd
from firebase_client import (
    get_db,
    load_species,
    get_proposed_groups,
    get_audit_log,
    get_removed_species,
)

st.set_page_config(page_title="Resultados Finales", page_icon="📊", layout="wide")

if not st.session_state.get("auth"):
    st.warning("⚠️ Debes iniciar sesión primero. Ve a la página de **Inicio**.")
    st.stop()

db = get_db()

st.title("📊 Resultados Finales")
st.caption("Vista consolidada de la validación por expertos")

col_refresh, _ = st.columns([1, 5])
with col_refresh:
    if st.button("🔄 Recargar desde Firebase", use_container_width=True,
                 help="Vuelve a leer Firestore (~5000 lecturas). Solo si necesitas ver cambios de otros expertos."):
        load_species(db, force=True)
        st.rerun()

# ── Load data (from in-memory cache) ──────────────────────────────────────────
with st.spinner("Cargando datos…"):
    all_df = load_species(db)
    proposed = get_proposed_groups(db)

if all_df.empty:
    st.warning("No hay datos en Firebase.")
    st.stop()

active = all_df[all_df["status"] != "removed"].copy() if not all_df.empty else pd.DataFrame()
removed_df = all_df[all_df["status"] == "removed"].copy() if not all_df.empty else pd.DataFrame()
validated = active[active["status"] == "validated"]
total = len(active)
pct = len(validated) / max(total, 1)

# ── KPIs ───────────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Taxa activos", f"{total:,}")
c2.metric("✅ Validados", f"{len(validated):,}", f"{pct:.0%}")
c3.metric("⏳ Pendientes", f"{int((active['status']=='pending').sum()):,}")
c4.metric("🗑 Removidos", f"{len(removed_df):,}")
c5.metric("💡 Grupos propuestos", len(proposed))
st.progress(pct, text=f"Validación: {pct:.1%}")

st.divider()

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "📋 Grupos Finales",
    "💡 Grupos Propuestos",
    "🗑 Taxa Removidos",
    "📜 Historial de Cambios",
])

# ── Tab 1: Final groups ────────────────────────────────────────────────────────
with tab1:
    st.subheader("Composición final por grupo funcional")

    # Group summary table
    group_summary = (
        active.groupby(["current_code", "current_group"])
        .agg(
            Total=("taxon", "count"),
            Validados=("status", lambda x: (x == "validated").sum()),
            Pendientes=("status", lambda x: (x == "pending").sum()),
        )
        .reset_index()
        .rename(columns={"current_code": "Código", "current_group": "Grupo"})
        .sort_values("Total", ascending=False)
    )

    # Confidence breakdown
    if "confidence" in active.columns:
        conf_pivot = active.groupby("current_code")["confidence"].value_counts().unstack(fill_value=0)
        for c in ["high", "medium", "low"]:
            if c not in conf_pivot.columns:
                conf_pivot[c] = 0
        conf_pivot = conf_pivot[["high", "medium", "low"]].rename(
            columns={"high": "Conf. Alta 🟢", "medium": "Conf. Media 🟡", "low": "Conf. Baja 🔴"}
        )
        group_summary = group_summary.merge(
            conf_pivot, left_on="Código", right_index=True, how="left"
        ).fillna(0)
        for col in ["Conf. Alta 🟢", "Conf. Media 🟡", "Conf. Baja 🔴"]:
            group_summary[col] = group_summary[col].astype(int)

    st.dataframe(
        group_summary,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Total": st.column_config.NumberColumn(format="%d"),
            "Validados": st.column_config.NumberColumn(format="%d"),
            "Pendientes": st.column_config.NumberColumn(format="%d"),
        },
    )

    # Group detail drill-down
    st.subheader("Detalle de especies por grupo")
    group_options = group_summary["Código"].tolist()
    selected_g = st.selectbox(
        "Seleccionar grupo:",
        group_options,
        format_func=lambda c: (
            f"{c} — {group_summary[group_summary['Código']==c]['Grupo'].values[0]} "
            f"({group_summary[group_summary['Código']==c]['Total'].values[0]} taxa)"
        ),
    )
    if selected_g:
        detail = active[active["current_code"] == selected_g][
            ["taxon", "confidence", "status", "original_code", "original_group", "last_modified_by"]
        ].copy()
        detail.columns = ["Taxon", "Confianza", "Estado", "Grupo Original", "Nombre Original", "Editado por"]
        detail["Movido"] = detail["Grupo Original"] != selected_g
        st.dataframe(
            detail.sort_values("Taxon"),
            use_container_width=True,
            hide_index=True,
        )

    # Downloads
    st.subheader("Descargar resultados")
    col_dl1, col_dl2 = st.columns(2)

    export_active = active[
        ["taxon", "current_code", "current_group", "original_code", "original_group",
         "confidence", "status", "last_modified_by"]
    ].copy()
    export_active.columns = [
        "taxon", "group_code", "group_name", "original_code", "original_group",
        "confidence", "validation_status", "validated_by"
    ]

    col_dl1.download_button(
        "📥 CSV — Taxa activos validados",
        data=export_active.to_csv(index=False).encode("utf-8"),
        file_name="grupos_funcionales_validados.csv",
        mime="text/csv",
        use_container_width=True,
    )

    export_all = all_df[
        ["taxon", "current_code", "current_group", "original_code", "original_group",
         "confidence", "status", "last_modified_by"]
    ].copy()
    export_all.columns = [
        "taxon", "group_code", "group_name", "original_code", "original_group",
        "confidence", "status", "edited_by"
    ]
    col_dl2.download_button(
        "📥 CSV — Todos (incluye removidos)",
        data=export_all.to_csv(index=False).encode("utf-8"),
        file_name="grupos_funcionales_completo.csv",
        mime="text/csv",
        use_container_width=True,
    )


# ── Tab 2: Proposed groups ─────────────────────────────────────────────────────
with tab2:
    st.subheader(f"Grupos propuestos por los expertos ({len(proposed)})")
    if not proposed:
        st.info("Ningún experto ha propuesto grupos nuevos aún.")
    else:
        for p in proposed:
            prop_at = p.get("proposed_at", "")
            if hasattr(prop_at, "strftime"):
                prop_at_str = prop_at.strftime("%Y-%m-%d %H:%M")
            else:
                prop_at_str = str(prop_at)[:16]

            with st.expander(
                f"💡 [{p.get('group_code','?')}] {p.get('group_name','?')} "
                f"— propuesto por {p.get('proposed_by','?')}"
            ):
                col_a, col_b = st.columns(2)
                col_a.markdown(f"**Código propuesto:** `{p.get('group_code','')}`")
                col_a.markdown(f"**Nombre:** {p.get('group_name','')}")
                col_a.markdown(f"**Taxon origen:** *{p.get('taxon_origin','')}*")
                col_a.markdown(f"**Grupo original:** `{p.get('from_code','')}`")
                col_b.markdown(f"**Propuesto por:** {p.get('proposed_by','')}")
                col_b.markdown(f"**Fecha:** {prop_at_str}")
                st.markdown(f"**Descripción:** {p.get('description','')}")

                # Species currently in this proposed group
                prop_code = f"PROP_{p.get('group_code','').upper()}"
                prop_species = active[active["current_code"] == prop_code]
                if not prop_species.empty:
                    st.markdown(f"**Taxa asignados a este grupo propuesto ({len(prop_species)}):**")
                    st.dataframe(
                        prop_species[["taxon", "original_group", "last_modified_by"]].rename(
                            columns={"taxon": "Taxon", "original_group": "Grupo Original", "last_modified_by": "Movido por"}
                        ),
                        hide_index=True,
                        use_container_width=True,
                    )


# ── Tab 3: Removed taxa ────────────────────────────────────────────────────────
with tab3:
    st.subheader(f"Taxa removidos del modelo ({len(removed_df)})")
    if removed_df.empty:
        st.info("No se ha removido ningún taxon aún.")
    else:
        display_removed = removed_df[
            ["taxon", "original_code", "original_group", "last_modified_by", "last_modified_at"]
        ].copy()
        display_removed.columns = ["Taxon", "Código Original", "Grupo Original", "Removido por", "Fecha"]
        if "Fecha" in display_removed.columns:
            display_removed["Fecha"] = pd.to_datetime(display_removed["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M")

        st.dataframe(display_removed.sort_values("Taxon"), use_container_width=True, hide_index=True)

        st.download_button(
            "📥 CSV — Taxa removidos",
            data=display_removed.to_csv(index=False).encode("utf-8"),
            file_name="taxa_removidos.csv",
            mime="text/csv",
        )


# ── Tab 4: Audit log ───────────────────────────────────────────────────────────
with tab4:
    st.subheader("Historial completo de cambios")
    with st.spinner("Cargando historial…"):
        audit_df = get_audit_log(db, limit=1000)

    if audit_df.empty:
        st.info("No hay cambios registrados aún.")
    else:
        # Filters
        col_exp, col_act = st.columns(2)
        experts_list = ["Todos"] + sorted(audit_df["expert"].dropna().unique().tolist()) if "expert" in audit_df.columns else ["Todos"]
        actions_list = ["Todas"] + sorted(audit_df["action"].dropna().unique().tolist()) if "action" in audit_df.columns else ["Todas"]

        with col_exp:
            exp_filter = st.selectbox("Filtrar por experto:", experts_list)
        with col_act:
            act_filter = st.selectbox("Filtrar por acción:", actions_list)

        filtered = audit_df.copy()
        if exp_filter != "Todos" and "expert" in filtered.columns:
            filtered = filtered[filtered["expert"] == exp_filter]
        if act_filter != "Todas" and "action" in filtered.columns:
            filtered = filtered[filtered["action"] == act_filter]

        st.caption(f"{len(filtered)} registros")
        st.dataframe(filtered, use_container_width=True, hide_index=True)

        st.download_button(
            "📥 CSV — Historial de cambios",
            data=filtered.to_csv(index=False).encode("utf-8"),
            file_name="historial_cambios.csv",
            mime="text/csv",
        )
