"""
Validación de Grupos Funcionales — Golfo de California (ATLANTIS)
=================================================================

Ejecutar:
    cd Functional_groups_creator_clasiffier
    streamlit run validator_app/app.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import streamlit as st
from firebase_client import (
    get_db,
    is_imported,
    import_classifications,
    load_species,
    sign_in,
    expert_name_from_auth,
)

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_DIR = Path(__file__).parent.parent / "output"
CLASSIFIED_CSV = OUTPUT_DIR / "species_classified.csv"
GROUPS_CSV = DATA_DIR / "functional_groups_final.csv"

st.set_page_config(
    page_title="Validación — Grupos Funcionales",
    page_icon="🐟",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session state defaults ─────────────────────────────────────────────────────
st.session_state.setdefault("auth", None)
st.session_state.setdefault("expert_name", "")
st.session_state.setdefault("db_imported", False)

# ── Header ─────────────────────────────────────────────────────────────────────
st.title("🐟 Validación de Grupos Funcionales")
st.caption("Golfo de California · Modelo ATLANTIS · Validación por expertos")

# ── Login ──────────────────────────────────────────────────────────────────────
if not st.session_state.auth:
    st.markdown("### Iniciar sesión")
    st.info(
        "Usa el correo electrónico con el que fuiste registrado en el proyecto. "
        "Todos los cambios quedarán registrados con tu nombre."
    )

    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("Correo electrónico:", placeholder="tu@correo.com")
        password = st.text_input("Contraseña:", type="password")
        submitted = st.form_submit_button("🔐 Iniciar sesión", type="primary", use_container_width=True)

    if submitted:
        if not email.strip() or not password:
            st.error("Ingresa correo y contraseña.")
        else:
            with st.spinner("Verificando…"):
                try:
                    auth = sign_in(email.strip(), password)
                    st.session_state.auth = auth
                    st.session_state.expert_name = expert_name_from_auth(auth)
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
    st.stop()

# ── Active session header ──────────────────────────────────────────────────────
auth = st.session_state.auth
col_user, _, col_logout = st.columns([4, 3, 1])
col_user.success(
    f"👤 **{st.session_state.expert_name}** · {auth.get('email', '')}"
)
with col_logout:
    if st.button("Cerrar sesión"):
        st.session_state.auth = None
        st.session_state.expert_name = ""
        st.session_state.db_imported = False
        if "_species_df" in st.session_state:
            del st.session_state["_species_df"]
        st.rerun()

st.markdown("---")

# ── Firebase init + one-time import ───────────────────────────────────────────
db = get_db()

if not st.session_state.db_imported:
    if not is_imported(db):
        if not CLASSIFIED_CSV.exists():
            st.error(
                f"No se encontró el archivo clasificado: `{CLASSIFIED_CSV}`\n\n"
                "Ejecuta primero el script de clasificación:\n"
                "```\npython classify_species.py --input data/final_taxonomy_occ.csv "
                "--by-genus --provider anthropic --no-reasoning\n```"
            )
            st.stop()
        with st.spinner("Importando clasificaciones a Firebase… (solo ocurre la primera vez)"):
            n = import_classifications(CLASSIFIED_CSV, GROUPS_CSV, db)
        st.success(f"✅ {n:,} taxa importados exitosamente a Firestore.")
    st.session_state.db_imported = True

# ── Stats dashboard ────────────────────────────────────────────────────────────
force_reload = st.button(
    "🔄 Recargar datos desde Firebase",
    help="Solo necesario para ver cambios recientes de otros expertos.",
)
with st.spinner("Cargando estadísticas…"):
    df = load_species(db, force=force_reload)

if df.empty:
    st.warning("No hay datos en Firebase.")
    st.stop()

active = df[df["status"] != "removed"]
total = len(active)
validated = int((active["status"] == "validated").sum())
pending = int((active["status"] == "pending").sum())
removed = int((df["status"] == "removed").sum())
pct = validated / max(total, 1)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Taxa activos", f"{total:,}")
c2.metric("✅ Validados", f"{validated:,}", f"{pct:.0%}")
c3.metric("⏳ Pendientes", f"{pending:,}")
c4.metric("🗑 Removidos", f"{removed:,}")
st.progress(pct, text=f"Progreso de validación: {pct:.1%}")

st.markdown("---")
st.markdown(
    "### ¿Por dónde empezar?\n\n"
    "Usa el menú lateral izquierdo para navegar entre las páginas:\n\n"
    "| Página | Descripción |\n"
    "|---|---|\n"
    "| **✅ Validar Grupos** | Revisa las especies de cada grupo. Confirma, mueve o quita taxa. |\n"
    "| **📊 Resultados Finales** | Vista consolidada, grupos propuestos y descarga de resultados. |"
)
