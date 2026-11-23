"""Modelo de susceptibilidad a movimientos en masa y módulo de puntos críticos.

Productos (carpeta data/, generados fuera de la app con Google Earth Engine):
  - modelo_susceptibilidad.json: metadatos, validación, importancia de
    variables, cortes de clase y área por clase en cada municipio.
  - susceptibilidad_60m.png: clases de susceptibilidad (1 a 5) en una grilla
    regular de ~60 m (EPSG:4326), coloreadas; sirve para el mapa y, leyendo
    el color de cada celda, para las consultas por punto. La extensión de la
    grilla está en modelo_susceptibilidad.json["raster"].
  - puntos_criticos.json: sitios del inventario unificado (CDGRD 2017-2026 y
    formulario posterior al sismo de 2026) con su índice de atención.

El modelo es un bosque aleatorio (Random Forest) entrenado con los sitios de
movimientos en masa visitados por la coordinación departamental y las
entidades de Pereira, frente a ausencias confirmadas en campo y puntos de
fondo. Se validó por bloques espaciales de 5 km.
"""
from __future__ import annotations

import io
import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

DIR_DATA = Path(__file__).resolve().parent.parent / "data"
RUTA_META = DIR_DATA / "modelo_susceptibilidad.json"
RUTA_PNG = DIR_DATA / "susceptibilidad_60m.png"
RUTA_PUNTOS = DIR_DATA / "puntos_criticos.json"

CLASES = ["Muy baja", "Baja", "Media", "Alta", "Muy alta"]
COLOR_CLASE = {"Muy baja": "#1a9850", "Baja": "#a6d96a", "Media": "#fee08b",
               "Alta": "#f46d43", "Muy alta": "#a50026"}
NIVELES = ["Seguimiento prioritario", "Seguimiento", "Vigilancia"]
COLOR_NIVEL = {"Seguimiento prioritario": "#c0392b", "Seguimiento": "#e67e22",
               "Vigilancia": "#2e86c1"}
ACCION_NIVEL = {
    "Seguimiento prioritario": (
        "Verificar información, principalmente los elementos expuestos."),
    "Seguimiento": (
        "Programar inspección periódica, en especial después de lluvias intensas. "
        "Revisar manejo de aguas lluvias y de escorrentía."),
    "Vigilancia": (
        "Atender en caso de que se reporten cambios en el terreno (grietas, hundimientos, "
        "árboles o postes inclinados, etc.)."),
}


@lru_cache(maxsize=1)
def meta() -> dict:
    return json.loads(RUTA_META.read_text(encoding="utf-8"))


def disponible() -> bool:
    return RUTA_META.exists() and RUTA_PUNTOS.exists() and RUTA_PNG.exists()


@lru_cache(maxsize=1)
def _puntos_todos() -> pd.DataFrame:
    raw = json.loads(RUTA_PUNTOS.read_text(encoding="utf-8"))
    df = pd.DataFrame(raw["p"], columns=raw["campos"])
    for c, valores in raw["dic"].items():
        df[c] = df[c].map(dict(enumerate(valores)))
    df["codigo"] = "66" + df["codigo"].astype(str)
    for c in ("post_sismo", "via", "equipamiento"):
        df[c] = df[c].astype(bool)
    df["fecha_ultima"] = pd.to_datetime(df["fecha_ultima"])
    df["pid"] = np.arange(len(df))
    return df


def puntos(codigo: str | None = None) -> pd.DataFrame:
    """Sitios con movimiento en masa confirmado, ordenados por índice de
    atención (mayor primero). «codigo»: código DANE del municipio."""
    df = _puntos_todos()
    if codigo and codigo != "66":
        df = df[df["codigo"] == codigo]
    return df.sort_values(["indice", "susc"], ascending=False).reset_index(drop=True)


@lru_cache(maxsize=1)
def raster() -> dict:
    from PIL import Image

    img = np.asarray(Image.open(RUTA_PNG).convert("RGBA")).astype(np.int16)
    pal = np.array([[int(COLOR_CLASE[k][i:i + 2], 16) for i in (1, 3, 5)] for k in CLASES])
    d = ((img[:, :, None, :3] - pal[None, None, :, :]) ** 2).sum(-1)
    clase = (d.argmin(-1) + 1).astype(np.uint8)
    clase[img[:, :, 3] < 128] = 0
    r = meta()["raster"]
    return {"clase": clase, "oeste": r["oeste"], "norte": r["norte"],
            "dx": r["dx"], "dy": r["dy"]}


def clase_en(lat: float, lon: float) -> str | None:
    r = raster()
    i = int((r["norte"] - lat) / r["dy"])
    j = int((lon - r["oeste"]) / r["dx"])
    a = r["clase"]
    if 0 <= i < a.shape[0] and 0 <= j < a.shape[1] and a[i, j] > 0:
        return CLASES[int(a[i, j]) - 1]
    return None


def limites_png() -> list[list[float]]:
    r = raster()
    a = r["clase"]
    return [[r["norte"] - a.shape[0] * r["dy"], r["oeste"]],
            [r["norte"], r["oeste"] + a.shape[1] * r["dx"]]]


def recorte(bounds: list[list[float]]) -> tuple[np.ndarray, list[float]]:
    """Recorte de la grilla de clases a una caja [[s, o], [n, e]]; devuelve el
    arreglo y la extensión [o, e, s, n] para dibujar."""
    r = raster()
    (s, o), (n, e) = bounds
    i0 = max(0, int((r["norte"] - n) / r["dy"]))
    i1 = min(r["clase"].shape[0], int(math.ceil((r["norte"] - s) / r["dy"])))
    j0 = max(0, int((o - r["oeste"]) / r["dx"]))
    j1 = min(r["clase"].shape[1], int(math.ceil((e - r["oeste"]) / r["dx"])))
    sub = r["clase"][i0:i1, j0:j1]
    ext = [r["oeste"] + j0 * r["dx"], r["oeste"] + j1 * r["dx"],
           r["norte"] - i1 * r["dy"], r["norte"] - i0 * r["dy"]]
    return sub, ext


def area_por_clase(codigo: str) -> dict[str, float]:
    """% del área municipal (o departamental, '66') en cada clase."""
    return meta()["area_por_clase"].get(codigo, {})


def resumen_municipio(codigo: str) -> dict:
    df = puntos(codigo)
    a = area_por_clase(codigo)
    return {
        "n_sitios": int(len(df)),
        "por_nivel": {n: int((df["nivel"] == n).sum()) for n in NIVELES},
        "alta_muy_alta": round(a.get("Alta", 0) + a.get("Muy alta", 0), 1),
        "area": a,
        "con_viviendas": int((df["viviendas"] > 0).sum()),
        "con_via": int(df["via"].sum()),
    }


def png_overlay() -> bytes:
    return RUTA_PNG.read_bytes()


def texto_exposicion(fila: pd.Series | dict) -> str:
    partes = []
    v = fila.get("viviendas") or 0
    p = fila.get("personas")
    if v and v > 0:
        partes.append(f"{int(v)} vivienda{'s' if v != 1 else ''}")
    if p is not None and p == p and p > 0:
        partes.append(f"{int(p)} persona{'s' if p != 1 else ''}")
    if fila.get("via"):
        partes.append("vía")
    if fila.get("equipamiento"):
        partes.append("equipamiento o red de servicio")
    return ", ".join(partes)
