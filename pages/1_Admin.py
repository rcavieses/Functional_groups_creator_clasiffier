from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import streamlit as st
import pandas as pd
from sql_client import (
    is_admin,
    get_admin_emails,
    list_experts,
    create_expert,
    update_expert_name,
    toggle_expert,
    delete_expert,
    send_password_reset,
    expert_name_from_auth,
    get_db,
    get_group_assignments,
    get_assignment_stats,
    get_groups_summary,
    distribute_groups,
    clear_assignments,
    get_group_descriptions,
    set_group_description,
)
from ui_helpers import run_db_action

st.set_page_config(page_title="Admin — Expertos", page_icon="🔧", layout="wide")

# ── Auth + admin guard ─────────────────────────────────────────────────────────
if not st.session_state.get("auth"):
    st.warning("⚠️ Debes iniciar sesión primero. Ve a la página de **Inicio**.")
    st.stop()

if not is_admin(st.session_state.auth):
    st.error("🚫 No tienes permisos para acceder a esta página.")
    st.caption(f"Tu correo: {st.session_state.auth.get('email', '')}")
    st.stop()

admin_name = expert_name_from_auth(st.session_state.auth)
st.title("🔧 Administración de Expertos")
st.caption(f"Sesión admin: **{admin_name}**")

# ── Load users ─────────────────────────────────────────────────────────────────
if st.button("🔄 Actualizar lista", use_container_width=False):
    if "_experts_list" in st.session_state:
        del st.session_state["_experts_list"]

if "_experts_list" not in st.session_state:
    with st.spinner("Cargando usuarios de Firebase Auth…"):
        st.session_state["_experts_list"] = list_experts()

experts = st.session_state["_experts_list"]

db = get_db()

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_list, tab_create, tab_dist, tab_desc = st.tabs([
    "👥 Expertos registrados",
    "➕ Registrar nuevo experto",
    "📋 Distribución de Grupos",
    "📝 Descripciones de Grupos",
])


# ── Tab 1: List + manage ───────────────────────────────────────────────────────
with tab_list:
    active_count = sum(1 for u in experts if not u["disabled"])
    disabled_count = sum(1 for u in experts if u["disabled"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Total registrados", len(experts))
    c2.metric("✅ Activos", active_count)
    c3.metric("🚫 Deshabilitados", disabled_count)
    st.divider()

    if not experts:
        st.info("No hay usuarios registrados aún.")
    else:
        # Filter
        filter_col, search_col = st.columns([1, 3])
        with filter_col:
            show = st.selectbox("Mostrar:", ["Todos", "Activos", "Deshabilitados"])
        with search_col:
            search = st.text_input("Buscar por nombre o correo:", placeholder="García…")

        filtered = experts
        if show == "Activos":
            filtered = [u for u in filtered if not u["disabled"]]
        elif show == "Deshabilitados":
            filtered = [u for u in filtered if u["disabled"]]
        if search.strip():
            q = search.strip().lower()
            filtered = [u for u in filtered if q in u["email"].lower() or q in u["display_name"].lower()]

        st.caption(f"{len(filtered)} usuarios")
        st.divider()

        # Dialogs
        @st.dialog("✏️ Editar nombre", width="small")
        def dlg_edit_name(uid: str, current_name: str):
            new_name = st.text_input("Nuevo nombre:", value=current_name)
            c1, c2 = st.columns(2)
            if c1.button("Guardar", type="primary", use_container_width=True,
                          disabled=not new_name.strip() or new_name.strip() == current_name):
                update_expert_name(uid, new_name.strip())
                del st.session_state["_experts_list"]
                st.rerun()
            if c2.button("Cancelar", use_container_width=True):
                st.rerun()

        @st.dialog("🗑️ Eliminar cuenta", width="small")
        def dlg_delete(uid: str, email: str):
            st.warning(f"¿Eliminar permanentemente la cuenta de **{email}**?")
            st.caption("Esta acción no se puede deshacer.")
            c1, c2 = st.columns(2)
            if c1.button("🗑️ Eliminar", type="primary", use_container_width=True):
                if run_db_action(
                    lambda: delete_expert(uid),
                    success=f"Cuenta de {email} eliminada.",
                ):
                    del st.session_state["_experts_list"]
                    st.rerun()
            if c2.button("Cancelar", use_container_width=True):
                st.rerun()

        # User rows
        header = st.columns([3, 3, 1, 1, 1, 1, 1])
        for col, label in zip(header, ["Nombre", "Correo", "Estado", "✏️", "🔑 Reset", "🚫/✅", "🗑️"]):
            col.markdown(f"**{label}**")
        st.divider()

        for user in filtered:
            uid = user["uid"]
            email = user["email"]
            name = user["display_name"] or "—"
            disabled = user["disabled"]

            cols = st.columns([3, 3, 1, 1, 1, 1, 1])
            cols[0].markdown(name)
            cols[1].markdown(f"`{email}`")
            cols[2].markdown("🚫 Deshabilitado" if disabled else "✅ Activo")

            # Edit name
            if cols[3].button("✏️", key=f"edit_{uid}", help="Editar nombre"):
                dlg_edit_name(uid, user["display_name"] or "")

            # Password reset
            if cols[4].button("🔑", key=f"reset_{uid}", help="Generar nueva contraseña temporal"):
                try:
                    new_pwd = send_password_reset(email)
                    st.session_state[f"reset_pwd_{uid}"] = new_pwd
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

            if st.session_state.get(f"reset_pwd_{uid}"):
                st.text_input(
                    f"Nueva contraseña temporal para {email}:",
                    value=st.session_state[f"reset_pwd_{uid}"],
                    key=f"show_pwd_{uid}",
                    help="Copia esta contraseña y compártela de forma segura.",
                )
                if st.button("✓ Listo", key=f"ack_pwd_{uid}"):
                    del st.session_state[f"reset_pwd_{uid}"]
                    st.rerun()

            # Toggle disable
            if disabled:
                if cols[5].button("✅", key=f"enable_{uid}", help="Habilitar cuenta"):
                    toggle_expert(uid, disable=False)
                    del st.session_state["_experts_list"]
                    st.rerun()
            else:
                if cols[5].button("🚫", key=f"disable_{uid}", help="Deshabilitar cuenta"):
                    toggle_expert(uid, disable=True)
                    del st.session_state["_experts_list"]
                    st.rerun()

            # Delete
            if cols[6].button("🗑️", key=f"del_{uid}", help="Eliminar cuenta permanentemente"):
                dlg_delete(uid, email)


# ── Tab 2: Create new expert ───────────────────────────────────────────────────
with tab_create:
    st.subheader("Registrar nuevo experto")
    st.info(
        "Se genera una contraseña temporal aleatoria. "
        "Compártela con el experto por un canal seguro (no por correo en claro). "
        "El experto puede cambiarla usando **Olvidé mi contraseña** en la pantalla de login."
    )

    with st.form("create_expert_form", clear_on_submit=True):
        col_name, col_email = st.columns(2)
        with col_name:
            new_name = st.text_input("Nombre completo:", placeholder="Dra. María García López")
        with col_email:
            new_email = st.text_input("Correo electrónico:", placeholder="mgarcia@cibnor.mx")

        submitted = st.form_submit_button("➕ Crear cuenta", type="primary", use_container_width=True)

    if submitted:
        if not new_name.strip() or not new_email.strip():
            st.error("Ingresa nombre y correo.")
        elif "@" not in new_email:
            st.error("El correo no tiene formato válido.")
        else:
            with st.spinner("Creando cuenta…"):
                try:
                    temp_password = create_expert(new_email.strip(), new_name.strip())
                    del st.session_state["_experts_list"]  # invalidate cache
                    st.success(f"✅ Cuenta creada para **{new_name.strip()}**")
                    st.markdown("### Credenciales temporales")
                    cred_col1, cred_col2 = st.columns(2)
                    cred_col1.text_input("Correo:", value=new_email.strip(), disabled=True)
                    cred_col2.text_input(
                        "Contraseña temporal:",
                        value=temp_password,
                        help="Copia esta contraseña ahora — no se mostrará de nuevo.",
                    )
                    st.warning(
                        "⚠️ Esta contraseña solo se muestra una vez. "
                        "Cópiala y compártela con el experto de forma segura."
                    )
                except ValueError as e:
                    st.error(str(e))
                except Exception as e:  # noqa: BLE001 — error de conexión/BD
                    st.error(
                        "⚠️ No se pudo crear la cuenta por un problema temporal de conexión. "
                        f"Inténtalo de nuevo en unos segundos.\n\nDetalle técnico: `{e}`"
                    )


# ── Tab 3: Distribución de Grupos ─────────────────────────────────────────────
with tab_dist:
    st.subheader("📋 Distribución de grupos entre expertos")
    st.markdown(
        "Asigna grupos a los expertos de forma que cada grupo sea evaluado por al menos **N expertos**. "
        "Los expertos pueden ver todos los grupos, pero solo son responsables de calificar los asignados."
    )

    with st.spinner("Cargando…"):
        groups_summary = get_groups_summary(db)
        assignments_df = get_group_assignments(db, force=True)
        assignment_stats = get_assignment_stats(db)

    admin_emails = get_admin_emails()
    active_experts = [
        u for u in experts
        if not u["disabled"] and u["email"].lower() not in admin_emails
    ]
    G = len(groups_summary)
    N = len(active_experts)

    if assignment_stats:
        groups_with_min3 = sum(1 for c in assignment_stats.values() if c >= 3)
    else:
        groups_with_min3 = 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Grupos funcionales", G)
    m2.metric("Expertos activos", N)
    m3.metric("Grupos con ≥3 evaluadores", f"{groups_with_min3}/{G}")
    m4.metric("Total asignaciones", 0 if assignments_df.empty else len(assignments_df))

    st.divider()

    col_cfg, col_btn = st.columns([3, 2])

    with col_cfg:
        min_evals = st.number_input(
            "Evaluaciones mínimas por grupo",
            min_value=1,
            max_value=max(N, 1),
            value=min(3, max(N, 1)),
            help="Cada grupo será asignado a este número de expertos como mínimo.",
        )

    with col_btn:
        st.markdown("&nbsp;")
        if N == 0:
            st.warning("No hay expertos activos registrados.")
        elif G == 0:
            st.warning("No hay grupos funcionales en la base de datos.")
        else:
            groups_per_expert = round(G * min_evals / N, 1)
            st.caption(f"Cada experto recibirá aprox. **{groups_per_expert}** grupos.")

            if st.button("🔀 Distribuir grupos", type="primary", use_container_width=True):
                st.session_state["confirm_distribute"] = True

    if st.session_state.get("confirm_distribute"):
        st.warning(
            f"Esto borrará las asignaciones actuales y redistribuirá {G} grupos "
            f"entre {N} expertos ({min_evals} evaluadores por grupo mínimo). ¿Confirmar?"
        )
        c_yes, c_no = st.columns(2)
        if c_yes.button("✅ Sí, distribuir", type="primary", use_container_width=True):
            expert_emails = [u["email"] for u in active_experts]
            with st.spinner("Distribuyendo grupos…"):
                distribute_groups(expert_emails, int(min_evals), admin_name, db)
            st.session_state["confirm_distribute"] = False
            st.success("✅ Grupos distribuidos correctamente.")
            st.rerun()
        if c_no.button("Cancelar", use_container_width=True):
            st.session_state["confirm_distribute"] = False
            st.rerun()

    if not assignments_df.empty:
        st.divider()
        if st.button("🗑️ Limpiar todas las asignaciones", use_container_width=False):
            st.session_state["confirm_clear"] = True

        if st.session_state.get("confirm_clear"):
            st.warning("¿Eliminar todas las asignaciones? Esta acción no se puede deshacer.")
            c1, c2 = st.columns(2)
            if c1.button("✅ Sí, limpiar", type="primary", use_container_width=True):
                clear_assignments(db)
                st.session_state["confirm_clear"] = False
                st.success("Asignaciones eliminadas.")
                st.rerun()
            if c2.button("Cancelar", key="cancel_clear", use_container_width=True):
                st.session_state["confirm_clear"] = False
                st.rerun()

    st.divider()
    st.markdown("#### Asignaciones actuales")

    if assignments_df.empty:
        st.info("No hay asignaciones. Usa el botón de arriba para distribuir los grupos.")
    else:
        counts = pd.crosstab(assignments_df["group_code"], assignments_df["expert_email"])
        pivot = counts.map(lambda x: "✅" if x > 0 else "—")
        pivot.columns = [c.split("@")[0] for c in pivot.columns]
        pivot.columns.name = None
        pivot.index.name = "Grupo"

        raw_stats = assignments_df.groupby("group_code").size().rename("# Evaluadores")
        pivot = pivot.join(raw_stats)

        st.dataframe(pivot, use_container_width=True)

        under_covered = [
            code for code in groups_summary
            if assignment_stats.get(code, 0) < min_evals
        ]
        if under_covered:
            st.warning(
                f"⚠️ {len(under_covered)} grupo(s) con menos de {min_evals} evaluador(es): "
                + ", ".join(under_covered)
            )
        else:
            st.success(f"✅ Todos los grupos tienen al menos {min_evals} evaluador(es) asignado(s).")


# ── Tab 4: Descripciones de Grupos ────────────────────────────────────────────
with tab_desc:
    st.subheader("📝 Descripciones / Características de los Grupos")
    st.caption("Estas descripciones aparecen en las fichas que ven los expertos al validar.")

    with st.spinner("Cargando descripciones…"):
        descriptions = get_group_descriptions(db, force=True)
        groups_summary_desc = get_groups_summary(db)

    if not groups_summary_desc:
        st.info("No hay grupos funcionales en la base de datos.")
    else:
        for group_code in sorted(groups_summary_desc.keys()):
            group_name = groups_summary_desc[group_code]["name"]
            current_desc = descriptions.get(group_code, "")

            with st.expander(f"**{group_code}** — {group_name}"):
                new_desc = st.text_area(
                    "Descripción / Características:",
                    value=current_desc,
                    height=100,
                    key=f"desc_{group_code}",
                    placeholder="Composición de especies, características ecológicas, rol funcional…",
                )
                if st.button("💾 Guardar", key=f"save_desc_{group_code}"):
                    run_db_action(
                        lambda: set_group_description(group_code, new_desc, admin_name, db),
                        success="✅ Descripción guardada.",
                    )
