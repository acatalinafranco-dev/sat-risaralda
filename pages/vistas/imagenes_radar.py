"""Vista: imágenes ópticas, radar Sentinel-1 y NISAR."""
from __future__ import annotations

from src.vistas import mostrar_secciones

mostrar_secciones({
    "Catálogo de imágenes": "imagenes.py",
    "Radar: cambio en laderas": "radar_sar.py",
    "NISAR (banda L)": "nisar.py",
}, "seccion_imagenes")
