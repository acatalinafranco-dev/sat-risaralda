"""Datos de amenaza y eventos del Servicio Geológico Colombiano (SGC) y regla
provisional del «nivel de atención» por municipio.

Fuentes (archivos incluidos en data/, descargados del geoportal del SGC):
  - SIMMA: inventario y catálogo de movimientos en masa (puntos).
  - Mapa Nacional de Amenaza por Movimientos en Masa, escala 1:100.000 (2015):
    porcentaje del área municipal en amenaza baja, media, alta y muy alta.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

DIR_DATA = Path(__file__).resolve().parent.parent / "data"
RUTA_SIMMA = DIR_DATA / "simma_risaralda.json"
RUTA_AMENAZA = DIR_DATA / "amenaza_sgc_municipal.json"

URL_SUSCEPTIBILIDAD = (
    "https://geoportal.sgc.gov.co/arcgis/rest/services/SIMMA/"
    "ZonificacionSusceptibilidadCache/MapServer/tile/{z}/{y}/{x}"
)

COLOR_TIPO = {
    "Deslizamiento": "#d73027",
    "Flujo": "#1f78b4",
    "Caida": "#ff7f00",
    "Reptación": "#8c564b",
    "Volcamiento": "#6a3d9a",
    "Propagación lateral": "#33a02c",
    "Deformaciones gravitacionales": "#555555",
}

NIVELES = ["Bajo", "Moderado", "Alto"]
COLOR_NIVEL = {"Bajo": "#2e9e5b", "Moderado": "#f2b705", "Alto": "#d64545",
               "Sin dato": "#b0b7bd"}


@lru_cache(maxsize=1)
def _simma_raw() -> dict:
    return json.loads(RUTA_SIMMA.read_text(encoding="utf-8"))


def fecha_corte_sgc() -> str:
    return _simma_raw()["descargado"]


def puntos_simma(codigo: str | None = None) -> pd.DataFrame:
    """Eventos SIMMA (inventario + catálogo) de Risaralda; si se indica un
    código DANE de municipio, solo los de ese municipio."""
    raw = _simma_raw()
    df = pd.DataFrame(raw["p"], columns=["lon", "lat", "t", "s", "id", "f", "m"])
    df["tipo"] = df["t"].map(dict(enumerate(raw["tipos"])))
    df["subtipo"] = df["s"].map(dict(enumerate(raw["subtipos"])))
    df["origen"] = df["f"].map(dict(enumerate(raw["fuentes"])))
    df["codigo"] = df["m"].map(dict(enumerate(raw["municipios"])))
    df = df[["lon", "lat", "tipo", "subtipo", "id", "origen", "codigo"]]
    if codigo and codigo != "66":
        df = df[df["codigo"] == codigo]
    return df.reset_index(drop=True)


@lru_cache(maxsize=1)
def amenaza_municipal() -> pd.DataFrame:
    """% del área municipal por clase de amenaza (SGC 2015, 1:100.000)."""
    raw = json.loads(RUTA_AMENAZA.read_text(encoding="utf-8"))
    filas = [{"codigo": c, **v} for c, v in raw["municipios"].items()]
    df = pd.DataFrame(filas)
    df["alta_muy_alta"] = (df["alta"] + df["muy_alta"]).round(1)
    return df


def eventos_por_municipio() -> dict[str, int]:
    df = puntos_simma()
    return df.groupby("codigo").size().to_dict()


def _puntos_lluvia(pct_normal: float | None) -> int | None:
    if pct_normal is None:
        return None
    if pct_normal < 100:
        return 0
    if pct_normal < 130:
        return 1
    if pct_normal < 170:
        return 2
    return 3


def _puntos_amenaza(pct_alta: float | None) -> int | None:
    if pct_alta is None:
        return None
    if pct_alta < 30:
        return 0
    if pct_alta < 60:
        return 1
    if pct_alta < 80:
        return 2
    return 3


def nivel_atencion(pct_normal: float | None, pct_alta: float | None) -> str:
    """Nivel de atención PROVISIONAL (bajo, moderado, alto).

    Suma dos puntajes de 0 a 3: lluvia de 30 días respecto a la normal
    (IMERG frente a la climatología CHIRPS) y proporción del municipio en
    amenaza alta y muy alta (SGC). 0-2: bajo; 3-4: moderado; 5-6: alto.
    Los umbrales deben validarse con el SGC, el IDEAM y el inventario de
    eventos de CARDER antes de cualquier uso oficial.
    """
    a, b = _puntos_lluvia(pct_normal), _puntos_amenaza(pct_alta)
    if a is None or b is None:
        return "Sin dato"
    total = a + b
    return "Bajo" if total <= 2 else ("Moderado" if total <= 4 else "Alto")
