"""Monitoreo Satelital de Movimientos en Masa · Risaralda.

Punto de entrada: define la navegación en cinco secciones.
Ejecutar local:  streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="SAT Risaralda · Movimientos en masa", page_icon="🛰️",
                   layout="wide", initial_sidebar_state="expanded")

paginas = [
    st.Page("secciones/esta_semana.py", title="Esta semana", icon="🗓️", default=True),
    st.Page("secciones/movimientos.py", title="Movimientos en masa", icon="⛰️",
            url_path="movimientos"),
    st.Page("secciones/lluvia_satelite.py", title="Lluvia y satélite", icon="🌧️",
            url_path="lluvia"),
    st.Page("secciones/consultar.py", title="Consultar un lugar", icon="📍",
            url_path="consultar"),
    st.Page("secciones/reportes.py", title="Reporte PDF y método", icon="📄",
            url_path="reportes"),
]
st.navigation(paginas).run()
