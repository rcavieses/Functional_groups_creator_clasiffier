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
from firebase_client import get_db, is_imported, import_classifications, get_all_species

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

# ── Session state ──────────────────────────────────────────────────────────────
if "expert_name" not in st.session_state:
    st.session_state.expert_name = ""
if "db_imported" not in st.session_state:
    st.session_state.db_imported = False

# ── Header ─────────────────────────────────────────────────────────────────────
st.title("🐟 Validación de Grupos Funcionales")
st.caption("Golfo de California · Modelo ATLANTIS · Validación por expertos")

# ── Login ──────────────────────────────────────────────────────────────────────
if not st.session_state.expert_name:
    st.markdown("### Identifícate para comenzar")
    st.info(
        "Cada cambio que realices — quitar una especie, moverla o proponer "
        "un grupo nuevo — quedará registrado con tu nombre en la base de datos."
    )
    col1, col2 = st.columns([3, 1])
    with col1:
        name = st.text_input(
            "Tu nombre completo:",
            placeholder="Ej. María García López",
            key="name_input",
        )
    with col2:
        st.write("")
        st.write("")
        if st.button("✅ Entrar", type="primary", disabled=not name.strip()):
            st.session_state.expert_name = name.strip()
            st.rerun()
    st.stop()

# ── Active session header ──────────────────────────────────────────────────────
col_user, _, col_logout = st.columns([3, 4, 1])
col_user.success(f"👤 Experto activo: **{st.session_state.expert_name}**")
with col_logout:
    if st.button("Cerrar sesión"):
        st.session_state.expert_name = ""
        st.rerun()

st.markdown("---")

# ── Firebase init + one-time import ───────────────────────────────────────────
db = get_db()

if not st.session_state.db_imported:
    if not is_imported(db):
        if not CLASSIFIED_CSV.exists():
            st.error(
                f"No se encontró el archivo clasificado:\n`{CLASSIFIED_CSV}`\n\n"
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
with st.spinner("Cargando estadísticas…"):
    df = get_all_species(db)

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

# ── Navigation guide ───────────────────────────────────────────────────────────
st.markdown(
    "### ¿Por dónde empezar?\n\n"
    "Usa el menú lateral izquierdo para navegar entre las páginas:\n\n"
    "| Página | Descripción |\n"
    "|---|---|\n"
    "| **✅ Validar Grupos** | Revisa las especies de cada grupo. Confirma, mueve o quita taxa. |\n"
    "| **📊 Resultados Finales** | Vista consolidada, grupos propuestos y descarga de resultados. |"
)
