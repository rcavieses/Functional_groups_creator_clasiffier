"""
dashboard.py — App de solo lectura (independiente).

Muestra, en tiempo casi real, las aportaciones de los expertos:
  • Comentarios y calificaciones de grupos   (tabla group_ratings)
  • Modificaciones propuestas                 (group_proposals, type='modification')
  • Grupos nuevos propuestos                  (group_proposals, type='new_group')
  • Grupos propuestos para eliminar           (group_proposals, type='deletion')

No depende de la app principal: tiene su propia conexión a Azure SQL y
solo hace SELECT. Se actualiza sola cada N segundos.

Ejecutar:
    streamlit run dashboard.py
"""

import os

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Dashboard de Resultados", page_icon="📊", layout="wide")


# ── Conexión a la BD (propia, solo lectura) ──────────────────────────────────────

def _secret(key: str, default: str = "") -> str:
    try:
        val = st.secrets.get(key, "")
        if val:
            return str(val)
    except Exception:
        pass
    return os.environ.get(key, default)


@st.cache_resource
def get_engine():
    from urllib.parse import quote_plus

    from sqlalchemy import create_engine

    server = _secret("AZURE_SQL_SERVER", "gocfg.database.windows.net")
    database = _secret("AZURE_SQL_DATABASE", "free-sql-db-5085999")
    user = _secret("AZURE_SQL_USER", "rcavieses")
    password = _secret("AZURE_SQL_PASSWORD", "")

    if not password:
        st.error("❌ `AZURE_SQL_PASSWORD` no configurada (env o secrets).")
        st.stop()

    return create_engine(
        f"mssql+pymssql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{server}:1433/{database}?tds_version=7.4",
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"timeout": 30, "login_timeout": 30},
    )


# ttl corto: cada refresco trae datos frescos sin martillar la BD en cada rerun.
@st.cache_data(ttl=15, show_spinner=False)
def load_proposals() -> pd.DataFrame:
    return pd.read_sql(
        """SELECT id, type, group_code, group_name, reason, description,
                  justification, proposed_by, proposed_at, status
           FROM group_proposals
           ORDER BY proposed_at DESC""",
        get_engine(),
    )


@st.cache_data(ttl=15, show_spinner=False)
def load_ratings() -> pd.DataFrame:
    return pd.read_sql(
        """SELECT id, group_code, group_name, rating, comment, expert, timestamp
           FROM group_ratings
           ORDER BY timestamp DESC""",
        get_engine(),
    )


# ── Render del contenido (se recarga solo cada N segundos) ───────────────────────

def _show_proposals(df: pd.DataFrame, cols: list[str], rename: dict, empty_msg: str):
    if df.empty:
        st.info(empty_msg)
        return
    view = df[cols].rename(columns=rename)
    st.dataframe(view, use_container_width=True, hide_index=True)


def render():
    try:
        proposals = load_proposals()
        ratings = load_ratings()
    except Exception as e:
        st.error(f"No se pudo consultar la base de datos: {e}")
        st.stop()

    mods = proposals[proposals["type"] == "modification"]
    nuevos = proposals[proposals["type"] == "new_group"]
    elim = proposals[proposals["type"] == "deletion"]
    comentarios = ratings[ratings["comment"].fillna("").str.strip() != ""]

    # KPIs
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("✏️ Modificaciones", len(mods))
    k2.metric("➕ Grupos nuevos", len(nuevos))
    k3.metric("🗑️ A eliminar", len(elim))
    k4.metric("💬 Comentarios", len(comentarios))

    st.caption(f"Última actualización: {pd.Timestamp.now():%Y-%m-%d %H:%M:%S}")

    tab_mod, tab_new, tab_del, tab_com = st.tabs(
        ["✏️ Modificaciones", "➕ Grupos nuevos", "🗑️ A eliminar", "💬 Comentarios"]
    )

    with tab_mod:
        st.subheader("Modificaciones propuestas")
        _show_proposals(
            mods,
            ["group_code", "group_name", "reason", "proposed_by", "proposed_at", "status"],
            {
                "group_code": "Código", "group_name": "Grupo", "reason": "Sugerencia",
                "proposed_by": "Experto", "proposed_at": "Fecha", "status": "Estado",
            },
            "Sin modificaciones propuestas todavía.",
        )

    with tab_new:
        st.subheader("Grupos nuevos propuestos")
        _show_proposals(
            nuevos,
            ["group_code", "group_name", "description", "justification", "proposed_by", "proposed_at", "status"],
            {
                "group_code": "Código", "group_name": "Grupo", "description": "Descripción",
                "justification": "Justificación", "proposed_by": "Experto",
                "proposed_at": "Fecha", "status": "Estado",
            },
            "Sin grupos nuevos propuestos todavía.",
        )

    with tab_del:
        st.subheader("Grupos propuestos para eliminar")
        _show_proposals(
            elim,
            ["group_code", "group_name", "reason", "proposed_by", "proposed_at", "status"],
            {
                "group_code": "Código", "group_name": "Grupo", "reason": "Motivo",
                "proposed_by": "Experto", "proposed_at": "Fecha", "status": "Estado",
            },
            "Sin grupos propuestos para eliminar.",
        )

    with tab_com:
        st.subheader("Comentarios y calificaciones")
        _show_proposals(
            comentarios,
            ["group_code", "group_name", "rating", "comment", "expert", "timestamp"],
            {
                "group_code": "Código", "group_name": "Grupo", "rating": "Calif.",
                "comment": "Comentario", "expert": "Experto", "timestamp": "Fecha",
            },
            "Aún no hay comentarios de los expertos.",
        )


# ── Página ───────────────────────────────────────────────────────────────────────

st.title("📊 Dashboard de Resultados — Validación de Expertos")

with st.sidebar:
    st.header("⚙️ Opciones")
    refresh_secs = st.slider("Actualizar cada (segundos)", 10, 120, 30, step=5)
    if st.button("🔄 Actualizar ahora", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# Fragmento con auto-refresco (Streamlit ≥ 1.33). Solo este bloque se vuelve a
# ejecutar cada `refresh_secs`, sin recargar toda la página.
fragment = st.fragment(run_every=refresh_secs)(render)
fragment()
