"""Sección: lluvia y satélite (precipitación, estaciones, vegetación, imágenes
y radar, comparativo municipal y últimos datos disponibles)."""
from __future__ import annotations

from src.vistas import mostrar_secciones

mostrar_secciones({
    "🌧️ Lluvia satelital": "precipitacion.py",
    "📡 Estaciones IDEAM": "estaciones.py",
    "🌿 Vegetación": "../3_Indices_Vegetacion.py",
    "🛰️ Imágenes y radar": "imagenes_radar.py",
    "📊 Comparativo municipal": "comparativo.py",
    "🕒 Últimos datos": "../0_Panel_Semanal.py",
}, "seccion_lluvia")
