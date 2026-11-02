"""Comparativo entre los 14 municipios de Risaralda.

Una sola consulta a Google Earth Engine por indicador (reduceRegions sobre la
capa de municipios), independiente del municipio elegido en la barra lateral:
  - Lluvia acumulada IMERG (7 y 30 días), media zonal en mm.
  - Pérdida severa de vegetación (ΔNDVI) en hectáreas, con Sentinel-2.
"""
from __future__ import annotations

import datetime as dt

import ee

from . import gee_precipitacion as gp
from .gee_indices import UMBRAL_NUBES_CS
from .gee_session import geojson_municipios


def _municipios_fc() -> ee.FeatureCollection:
    feats = []
    for f in geojson_municipios()["features"]:
        feats.append(ee.Feature(ee.Geometry(f["geometry"]), f["properties"]))
    return ee.FeatureCollection(feats)


def _lluvia(dias: int, fc: ee.FeatureCollection) -> dict[str, float | None]:
    hoy = dt.date.today()
    f0 = ee.Date((hoy - dt.timedelta(days=dias)).isoformat())
    f1 = ee.Date((hoy + dt.timedelta(days=1)).isoformat())
    acum = gp._interpolar(gp._diaria_imerg(f0, f1).sum().rename("mm"), 11132)
    res = acum.reduceRegions(
        collection=fc, reducer=ee.Reducer.mean(), scale=1000, tileScale=4
    ).getInfo()
    return {f["properties"]["codigo"]: f["properties"].get("mean")
            for f in res["features"]}


def _normal_chirps(dias: int, fc: ee.FeatureCollection, anios: int = 20
                   ) -> dict[str, float | None]:
    """Lluvia acumulada normal (mm) de la misma ventana de `dias` días en los
    últimos `anios` años (CHIRPS diario), media zonal por municipio."""
    hoy = dt.date.today()
    imgs = []
    for k in range(1, anios + 1):
        try:
            fin = hoy.replace(year=hoy.year - k)
        except ValueError:  # 29 de febrero
            fin = (hoy - dt.timedelta(days=1)).replace(year=hoy.year - k)
        ini = fin - dt.timedelta(days=dias)
        imgs.append(
            ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
            .filterDate(ini.isoformat(), (fin + dt.timedelta(days=1)).isoformat())
            .select("precipitation").sum()
        )
    normal = ee.ImageCollection.fromImages(imgs).mean().rename("mm")
    res = normal.reduceRegions(
        collection=fc, reducer=ee.Reducer.mean(), scale=1000, tileScale=4
    ).getInfo()
    return {f["properties"]["codigo"]: f["properties"].get("mean")
            for f in res["features"]}


def _ndvi(ini: str, fin: str, geom: ee.Geometry) -> ee.Image:
    s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
          .filterBounds(geom).filterDate(ini, fin))
    csp = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")

    def _f(img):
        img = img.updateMask(img.select("cs").gte(UMBRAL_NUBES_CS))
        return img.normalizedDifference(["B8", "B4"]).rename("NDVI")

    return s2.linkCollection(csp, ["cs"]).map(_f).median()


def _perdida_ha(fc: ee.FeatureCollection, umbral: float = -0.20
                ) -> dict[str, float | None]:
    hoy = dt.date.today()
    d = lambda n: (hoy - dt.timedelta(days=n)).isoformat()
    geom = fc.geometry()
    ref = _ndvi(d(365), d(180), geom)
    act = _ndvi(d(60), (hoy + dt.timedelta(days=1)).isoformat(), geom)
    perdida = act.subtract(ref).lt(umbral).And(ref.gt(0.4))
    area = perdida.multiply(ee.Image.pixelArea()).divide(10_000).rename("ha")
    res = area.reduceRegions(
        collection=fc, reducer=ee.Reducer.sum(), scale=40, tileScale=8
    ).getInfo()
    return {f["properties"]["codigo"]: f["properties"].get("sum")
            for f in res["features"]}


def tabla_comparativa() -> dict:
    """Devuelve {'filas': [...], 'errores': [...]}; cada fila trae código,
    nombre, área (km²), lluvia 7 d y 30 d, normal de 30 d (CHIRPS, 20 años), % de
    la normal y pérdida de vegetación (ha)."""
    fc = _municipios_fc()
    errores: list[str] = []
    r7 = r30 = perd = n30 = {}
    try:
        r7 = _lluvia(7, fc)
        r30 = _lluvia(30, fc)
        n30 = _normal_chirps(30, fc)
    except Exception as exc:  # noqa: BLE001
        errores.append(f"Lluvia: {exc}")
    try:
        perd = _perdida_ha(fc)
    except Exception as exc:  # noqa: BLE001
        errores.append(f"Vegetación: {exc}")

    filas = []
    for f in geojson_municipios()["features"]:
        p = f["properties"]
        c = p["codigo"]
        ha = perd.get(c)
        l30, nor = r30.get(c), n30.get(c)
        pct = (l30 / nor * 100) if (l30 is not None and nor) else None
        filas.append({
            "codigo": c,
            "nombre": p["nombre"],
            "area_km2": p["area_km2"],
            "lluvia_7d": r7.get(c),
            "lluvia_30d": l30,
            "normal_30d": nor,
            "pct_normal_30d": pct,
            "perdida_ha": ha,
            "perdida_pct": (ha / (p["area_km2"] * 100) * 100) if ha is not None else None,
        })
    return {"filas": filas, "errores": errores}
