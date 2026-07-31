"""NASA GIBS (Global Imagery Browse Services) · imágenes diarias NRT.

Capas de reflectancia corregida en color real (las mismas de NASA Worldview):
MODIS Terra/Aqua (250 m) y VIIRS S-NPP / NOAA-20 / NOAA-21 (375 m).
Latencia típica: 3-5 horas tras el paso del satélite (~10:30/13:30 hora local).

Servicio público de tiles XYZ, sin autenticación ni GEE.
"""
from __future__ import annotations

import datetime as dt

CAPAS_GIBS = {
    "MODIS_Terra_CorrectedReflectance_TrueColor": {
        "nombre": "MODIS / Terra · color real",
        "res": "250 m",
        "paso": "~10:30 a.m. hora local",
    },
    "MODIS_Aqua_CorrectedReflectance_TrueColor": {
        "nombre": "MODIS / Aqua · color real",
        "res": "250 m",
        "paso": "~1:30 p.m. hora local",
    },
    "VIIRS_SNPP_CorrectedReflectance_TrueColor": {
        "nombre": "VIIRS S-NPP · color real",
        "res": "375 m",
        "paso": "~1:30 p.m. hora local",
    },
    "VIIRS_NOAA20_CorrectedReflectance_TrueColor": {
        "nombre": "VIIRS NOAA-20 · color real",
        "res": "375 m",
        "paso": "~12:40 p.m. hora local",
    },
    "VIIRS_NOAA21_CorrectedReflectance_TrueColor": {
        "nombre": "VIIRS NOAA-21 · color real",
        "res": "375 m",
        "paso": "~1:00 p.m. hora local",
    },
}

_URL = (
    "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{capa}/default/"
    "{fecha}/GoogleMapsCompatible_Level9/{{z}}/{{y}}/{{x}}.jpg"
)


def url_tiles(capa: str, fecha: dt.date | str) -> str:
    """URL XYZ de la capa GIBS para una fecha (YYYY-MM-DD)."""
    if isinstance(fecha, dt.date):
        fecha = fecha.isoformat()
    return _URL.format(capa=capa, fecha=fecha)
