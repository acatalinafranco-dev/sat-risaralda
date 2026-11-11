"""Agrupa varias vistas en una sola página con un selector de sección."""
from __future__ import annotations

import runpy
from pathlib import Path

import streamlit as st

CARPETA = Path(__file__).resolve().parent.parent / "pages" / "vistas"


def mostrar_secciones(secciones: dict[str, str], clave: str) -> None:
    """Muestra un selector horizontal y ejecuta la vista elegida.

    secciones: {etiqueta: archivo dentro de pages/vistas}. Cada vista conserva
    su propio encabezado, guía y controles; solo se ejecuta la seleccionada."""
    elegida = st.radio("Sección", list(secciones), horizontal=True, key=clave,
                       label_visibility="collapsed")
    original = st.set_page_config
    st.set_page_config = lambda *a, **k: None  # la página contenedora ya la fijó
    try:
        runpy.run_path(str(CARPETA / secciones[elegida]), run_name="__main__")
    finally:
        st.set_page_config = original
