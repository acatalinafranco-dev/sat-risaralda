"""Página: precipitación satelital (IMERG, CHIRPS) y estaciones IDEAM."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.vistas import mostrar_secciones

st.set_page_config(page_title="Precipitación y estaciones · SAT Risaralda",
                   layout="wide", page_icon="🌧️", initial_sidebar_state="expanded")

mostrar_secciones({
    "🌧️ Precipitación satelital": "precipitacion.py",
    "📍 Estaciones IDEAM": "estaciones.py",
}, "seccion_precipitacion")
