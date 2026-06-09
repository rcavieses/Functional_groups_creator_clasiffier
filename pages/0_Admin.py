from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import streamlit as st
from firebase_client import (
    is_admin,
    list_experts,
    create_expert,
    update_expert_name,
    toggle_expert,
    delete_expert,
    send_password_reset,
    expert_name_from_auth,
)

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

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_list, tab_create = st.tabs(["👥 Expertos registrados", "➕ Registrar nuevo experto"])


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
                delete_expert(uid)
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
            if cols[4].button("🔑", key=f"reset_{uid}", help="Enviar correo de restablecimiento"):
                try:
                    send_password_reset(email)
                    st.toast(f"Correo de restablecimiento enviado a {email}", icon="✅")
                except ValueError as e:
                    st.error(str(e))

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
