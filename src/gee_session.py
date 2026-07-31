"""Inicialización de Google Earth Engine y geometría del municipio.

Soporta tres modos de autenticación (en orden de prioridad):
  1. st.secrets["gee_service_account"]  -> despliegue en Streamlit Cloud
  2. Variable de entorno GEE_CREDENTIALS_JSON (ruta a un JSON de service account)
  3. Credenciales locales de `earthengine authenticate` (desarrollo local)

El proyecto de EE se lee de st.secrets["ee_project"] o de la variable
de entorno EE_PROJECT.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import ee
import streamlit as st

DIR_DATA = Path(__file__).resolve().parent.parent / "data"
RUTA_GEOJSON = DIR_DATA / "pajarito.geojson"

# Datos del municipio (DIVIPOLA / DANE)
MUNICIPIO = {
    "codigo_dane": "15518",
    "nombre": "Pajarito",
    "departamento": "Boyacá",
    "lat": 5.3823,
    "lon": -72.6967,
    "area_km2": 313.0,
    "altitud_cabecera_m": 793,
}


def _proyecto() -> str | None:
    try:
        if "ee_project" in st.secrets:
            return st.secrets["ee_project"]
    except Exception:
        pass
    return os.getenv("EE_PROJECT")


@st.cache_resource(show_spinner="Conectando con Google Earth Engine...")
def init_ee() -> bool:
    """Inicializa Earth Engine una sola vez por sesión de servidor."""
    proyecto = _proyecto()

    # 1) Service account desde st.secrets (Streamlit Cloud)
    try:
        if "gee_service_account" in st.secrets:
            info = dict(st.secrets["gee_service_account"])
            creds = ee.ServiceAccountCredentials(
                info["client_email"], key_data=json.dumps(info)
            )
            ee.Initialize(creds, project=proyecto or info.get("project_id"))
            return True
    except Exception:
        pass

    # 2) Service account desde archivo (variable de entorno)
    ruta_json = os.getenv("GEE_CREDENTIALS_JSON")
    if ruta_json and Path(ruta_json).exists():
        info = json.loads(Path(ruta_json).read_text())
        creds = ee.ServiceAccountCredentials(
            info["client_email"], key_file=ruta_json
        )
        ee.Initialize(creds, project=proyecto or info.get("project_id"))
        return True

    # 3) Credenciales locales (earthengine authenticate)
    ee.Initialize(project=proyecto)
    return True


@lru_cache(maxsize=1)
def _geojson() -> dict:
    return json.loads(RUTA_GEOJSON.read_text(encoding="utf-8"))


def geojson_municipio() -> dict:
    """GeoJSON crudo (para pintar el contorno en folium/leafmap)."""
    return _geojson()


def roi() -> ee.Geometry:
    """Polígono del municipio como ee.Geometry (MultiPolygon)."""
    geom = _geojson()["features"][0]["geometry"]
    return ee.Geometry(geom)


def roi_buffer_km(km: float = 15.0) -> ee.Geometry:
    """ROI ampliado: útil para mapas de contexto e interpolación
    (IMERG/ERA5 tienen píxeles de ~11 km; el municipio solo cubre ~3)."""
    return roi().buffer(km * 1000)


def bounds_municipio() -> list[list[float]]:
    """[[lat_min, lon_min], [lat_max, lon_max]] para fit_bounds de folium."""
    coords: list[tuple[float, float]] = []

    def _walk(c):
        if isinstance(c[0], (int, float)):
            coords.append((c[0], c[1]))
        else:
            for sub in c:
                _walk(sub)

    _walk(_geojson()["features"][0]["geometry"]["coordinates"])
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return [[min(lats), min(lons)], [max(lats), max(lons)]]


def tiles_de(img: ee.Image, vis: dict) -> str:
    """URL de tiles XYZ para una imagen de EE con parámetros de visualización."""
    return img.getMapId(vis)["tile_fetcher"].url_format
