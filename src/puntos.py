"""Indicadores por punto: lluvia reciente, pendiente y cambio de radar."""
from __future__ import annotations

import ee

from . import gee_sar as gs
from .gee_estaciones import imerg_en_puntos


def calcular_puntos(puntos: tuple, dias_rec: int = 24, dias_ref: int = 90,
                    radio_m: int = 90) -> dict:
    """'puntos': tupla de (id, lon, lat). Devuelve {"filas": {id: {...}},
    "meta": {...}} con elevación y pendiente (NASADEM), cambio de
    retrodispersión Sentinel-1 (media en un círculo de 'radio_m') y lluvia
    IMERG de 7 y 30 días en el punto."""
    lons = [p[1] for p in puntos]
    lats = [p[2] for p in puntos]
    geom = ee.Geometry.Rectangle([min(lons) - 0.05, min(lats) - 0.05,
                                  max(lons) + 0.05, max(lats) + 0.05])
    cambio, meta = gs._cambio(geom, dias_rec, dias_ref)
    dem = ee.Image("NASA/NASADEM_HGT/001").select("elevation")
    img = (cambio.rename("sar")
           .addBands(ee.Terrain.slope(dem).rename("pend"))
           .addBands(dem.rename("elev")))
    fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([lon, lat]).buffer(radio_m), {"id": str(i)})
        for i, lon, lat in puntos])
    res = img.reduceRegions(collection=fc, reducer=ee.Reducer.mean(),
                            scale=30, tileScale=4).getInfo()
    filas = {}
    for f in res["features"]:
        p = f["properties"]
        filas[p["id"]] = {"sar_db": p.get("sar"), "pendiente": p.get("pend"),
                          "elevacion": p.get("elev")}
    pts = [(str(i), lon, lat) for i, lon, lat in puntos]
    for dias, clave in ((7, "lluvia_7d"), (30, "lluvia_30d")):
        try:
            for k, v in imerg_en_puntos(pts, dias).items():
                filas.setdefault(k, {})[clave] = v
        except Exception:  # noqa: BLE001
            for k in filas:
                filas[k][clave] = None
    return {"filas": filas, "meta": meta}
