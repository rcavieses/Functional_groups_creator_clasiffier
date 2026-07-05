"""
ui_helpers.py — Utilidades de interfaz compartidas entre páginas.

`run_db_action` centraliza el manejo de errores de las escrituras a la base de datos:
muestra un spinner mientras guarda, un mensaje claro en español si algo falla, y evita
que la página se caiga con un traceback críptico. Así el experto siempre sabe si su
acción se guardó o no.
"""

from typing import Callable

import streamlit as st


def run_db_action(
    action: Callable[[], object],
    *,
    success: str | None = None,
    spinner: str = "Guardando cambios…",
) -> bool:
    """Ejecuta una escritura a la base de datos con manejo uniforme de errores.

    Devuelve True si la acción se guardó correctamente, False si falló (en cuyo caso ya
    se mostró el error al usuario). El llamador debe hacer `st.rerun()` solo si devuelve
    True, para que el mensaje de error permanezca visible cuando algo salga mal.
    """
    try:
        with st.spinner(spinner):
            action()
    except Exception as e:  # noqa: BLE001 — queremos capturar cualquier fallo de BD/red
        st.error(
            "⚠️ **No se pudo guardar el cambio.** "
            "Puede ser un problema temporal de conexión con la base de datos "
            "(Azure SQL a veces tarda en responder tras estar inactiva). "
            "Tu cambio **no** se guardó — espera unos segundos e inténtalo de nuevo.\n\n"
            f"Detalle técnico: `{e}`"
        )
        return False

    if success:
        st.success(success)
    return True
