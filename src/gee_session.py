"""Inicialización de Google Earth Engine y geometría de análisis (Risaralda).

Soporta tres modos de autenticación (en orden de prioridad):
  1. st.secrets["gee_json"] o st.secrets["gee_service_account"]  -> Streamlit Cloud
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
RUTA_DEPTO = DIR_DATA / "risaralda.geojson"
RUTA_MUNICIPIOS = DIR_DATA / "risaralda_municipios.geojson"
CODIGO_DEPTO = "66"

# Datos del departamento (DIVIPOLA / DANE)
MUNICIPIO = {
    "codigo_dane": CODIGO_DEPTO,
    "nombre": "Risaralda",
    "departamento": "Risaralda",
    "lat": 5.05,
    "lon": -75.95,
    "area_km2": 3560.0,
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
        info = None
        if "gee_json" in st.secrets:
            # Contenido completo del archivo JSON pegado entre comillas triples.
            info = json.loads(st.secrets["gee_json"])
        elif "gee_service_account" in st.secrets:
            info = dict(st.secrets["gee_service_account"])
        if info:
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
def _depto() -> dict:
    return json.loads(RUTA_DEPTO.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _municipios() -> dict:
    return json.loads(RUTA_MUNICIPIOS.read_text(encoding="utf-8"))


def lista_municipios() -> list[tuple[str, str]]:
    """[(codigo DANE, nombre)] de los 14 municipios, en orden alfabético."""
    items = [(f["properties"]["codigo"], f["properties"]["nombre"])
             for f in _municipios()["features"]]
    return sorted(items, key=lambda t: t[1])


def codigo_activo() -> str:
    """Código de la unidad de análisis elegida en la barra lateral
    ('66' = todo el departamento; '66001' = Pereira, etc.)."""
    return str(st.session_state.get("mun_codigo", CODIGO_DEPTO))


def nombre_activo() -> str:
    cod = codigo_activo()
    if cod == CODIGO_DEPTO:
        return "Risaralda"
    return dict(lista_municipios()).get(cod, "Risaralda")


def es_departamento() -> bool:
    return codigo_activo() == CODIGO_DEPTO


@lru_cache(maxsize=32)
def _geojson_de(codigo: str) -> dict:
    if codigo == CODIGO_DEPTO:
        return _depto()
    feats = [f for f in _municipios()["features"]
             if f["properties"]["codigo"] == codigo]
    if not feats:
        return _depto()
    return {"type": "FeatureCollection", "features": feats}


def geojson_municipio() -> dict:
    """GeoJSON de la unidad activa (para pintar el contorno en folium)."""
    return _geojson_de(codigo_activo())


def geojson_municipios() -> dict:
    """GeoJSON con los 14 municipios."""
    return _municipios()


def geojson_departamento() -> dict:
    return _depto()


def roi() -> ee.Geometry:
    """Polígono de la unidad activa (departamento o municipio) como ee.Geometry."""
    geom = _geojson_de(codigo_activo())["features"][0]["geometry"]
    return ee.Geometry(geom)


def roi_buffer_km(km: float = 15.0) -> ee.Geometry:
    """ROI ampliado: útil para mapas de contexto e interpolación
    (IMERG/ERA5 tienen píxeles de ~11 km)."""
    return roi().buffer(km * 1000)


def _bounds_de(gj: dict) -> list[list[float]]:
    coords: list[tuple[float, float]] = []

    def _walk(c):
        if isinstance(c[0], (int, float)):
            coords.append((c[0], c[1]))
        else:
            for sub in c:
                _walk(sub)

    for f in gj["features"]:
        _walk(f["geometry"]["coordinates"])
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return [[min(lats), min(lons)], [max(lats), max(lons)]]


def bounds_municipio() -> list[list[float]]:
    """[[lat_min, lon_min], [lat_max, lon_max]] de la unidad activa."""
    return _bounds_de(_geojson_de(codigo_activo()))


def centro_activo() -> tuple[float, float]:
    (la0, lo0), (la1, lo1) = bounds_municipio()
    return (la0 + la1) / 2, (lo0 + lo1) / 2


def tiles_de(img: ee.Image, vis: dict) -> str:
    """URL de tiles XYZ para una imagen de EE con parámetros de visualización."""
    return img.getMapId(vis)["tile_fetcher"].url_format
