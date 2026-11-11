"""Página: imágenes satelitales (óptico y radar), análisis Radar SAR y NISAR."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.vistas import mostrar_secciones

st.set_page_config(page_title="Imágenes satelitales · SAT Risaralda", layout="wide",
                   page_icon="🛰️", initial_sidebar_state="expanded")

mostrar_secciones({
    "🛰️ Catálogo de imágenes": "imagenes.py",
    "📡 Radar SAR: cambio en laderas": "radar_sar.py",
    "🌐 NISAR (banda L)": "nisar.py",
}, "seccion_imagenes")
