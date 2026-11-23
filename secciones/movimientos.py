"""Sección: movimientos en masa (sectores de la semana, puntos críticos,
susceptibilidad y amenaza del SGC, inventario de eventos)."""
from __future__ import annotations

from src.vistas import mostrar_secciones

mostrar_secciones({
    "🗺️ Sectores de la semana": "../4_Sectores_Semanales.py",
    "🧭 Propensión del terreno y sitios conocidos": "../4_Susceptibilidad_y_Puntos_Criticos.py",
    "⛰️ Amenaza SGC e inventario de eventos": "../4_Amenaza_y_Eventos.py",
}, "seccion_movimientos")
