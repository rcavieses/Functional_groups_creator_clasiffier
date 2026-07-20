"""
Validación de Grupos Funcionales — Golfo de California (ATLANTIS)
=================================================================

Ejecutar localmente:
    cd Functional_groups_creator_clasiffier
    streamlit run app.py
"""

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import streamlit as st
from sql_client import (
    get_db,
    is_imported,
    import_classifications,
    load_species,
    sign_in,
    expert_name_from_auth,
    seed_group_descriptions,
    get_group_descriptions,
)

DATA_DIR       = Path(__file__).parent / "data"
OUTPUT_DIR     = Path(__file__).parent / "output"
CLASSIFIED_CSV = OUTPUT_DIR / "species_classified.csv"
GROUPS_CSV     = DATA_DIR  / "functional_groups_final.csv"
LOGO_PATH      = Path(__file__).parent / "CEDO_2023_logo.png"

st.set_page_config(
    page_title="Introducción — Grupos Funcionales",
    page_icon="🐟",
    layout="wide",
    initial_sidebar_state="expanded",
)

if LOGO_PATH.exists():
    st.logo(str(LOGO_PATH), size="small")
    st.markdown(
        "<style>[data-testid='stLogo'] { transform: scale(2.2); transform-origin: left center; }</style>",
        unsafe_allow_html=True,
    )

# ── Session state defaults ─────────────────────────────────────────────────────
st.session_state.setdefault("auth", None)
st.session_state.setdefault("expert_name", "")
st.session_state.setdefault("db_imported", False)

# ── Header ─────────────────────────────────────────────────────────────────────
st.title("🐟 Introducción — Validación de Grupos Funcionales")
st.caption("Golfo de California · Modelo ATLANTIS · Validación por expertos")

st.markdown(
    "Este proyecto clasifica cerca de **10,800 especies marinas del Golfo de California** "
    "en **grupos funcionales** para el modelo ecosistémico **ATLANTIS**. Un modelo de lenguaje (LLM) "
    "propone una clasificación inicial para cada especie, y el rol de los expertos aquí reunidos es "
    "**revisar, corregir y validar** esas propuestas antes de que se usen en el modelo."
)

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
            with st.spinner("Verificando… (puede tardar hasta 2 min si la base de datos estaba inactiva)"):
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

# ── DB init ───────────────────────────────────────────────────────────────────
db = get_db()

st.session_state.db_imported = True

# Sembrar descripciones desde CSV si la tabla está vacía
if GROUPS_CSV.exists() and "_groups_desc_seeded" not in st.session_state:
    try:
        existing = get_group_descriptions(db)
        if not existing:
            import pandas as _pd
            groups_rows = _pd.read_csv(GROUPS_CSV).to_dict("records")
            seed_group_descriptions(groups_rows, db)
        st.session_state["_groups_desc_seeded"] = True
    except Exception:
        pass

# ── Stats dashboard ────────────────────────────────────────────────────────────
force_reload = st.button(
    "🔄 Recargar datos desde Azure SQL",
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
    "Usa el menú lateral izquierdo para navegar entre las páginas. El flujo recomendado para "
    "un experto es: revisar los grupos que te fueron asignados, validar taxonomía o especies "
    "individuales, y consultar resultados cuando termines.\n\n"
    "| Página | Descripción |\n"
    "|---|---|\n"
    "| **📊 Validar Grupos** | Punto de partida: revisa cada grupo funcional, califica qué tan bien agrupadas están sus especies y comenta si algo no encaja. |\n"
    "| **🧬 Validar Taxonomía** | Revisa el grupo por género o familia y valida varias especies a la vez cuando toda la familia/género pertenece claramente al grupo. |\n"
    "| **✅ Validar Especies** | Vista especie por especie dentro de un grupo, con filtros por taxonomía (reino, filo, clase, orden, familia). Confirma, mueve o quita taxa uno a uno. |\n"
    "| **🤖 Validación de IA** | Revisa sugerencias de reclasificación generadas por IA y decide si aceptarlas o rechazarlas. |\n"
    "| **📈 Dashboard** | Estadísticas generales de avance, comentarios de otros expertos y propuestas pendientes. |\n"
    "| **📊 Resultados** | Vista consolidada del estado final, grupos propuestos y descarga de resultados (CSV/JSON). |\n\n"
    "*(Solo administradores verán además la página de* **🔧 Admin***, para gestionar expertos y asignar grupos.)*"
)

st.markdown(
    "<div style='text-align:center; color:#bbb; font-size:0.72rem; margin-top:4rem;'>"
    "App desarrollada por Ricardo Cavieses"
    "</div>",
    unsafe_allow_html=True,
)
