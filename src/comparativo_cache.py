"""Caché compartida del comparativo municipal (la usan el panel y las fichas)."""
from __future__ import annotations

import streamlit as st

from .gee_comparativo import tabla_comparativa


@st.cache_data(ttl=21600, show_spinner=False)
def comparativo_compartido(fecha_consulta: str):
    return tabla_comparativa()
