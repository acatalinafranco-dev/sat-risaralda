"""Lluvia satelital (IMERG) en los puntos de las estaciones, para contraste."""
from __future__ import annotations

import datetime as dt

import ee

from . import gee_precipitacion as gp


def imerg_en_puntos(puntos: list[tuple[str, float, float]], dias: int = 30
                    ) -> dict[str, float | None]:
    """Lluvia IMERG acumulada (mm) de los últimos `dias` días, por punto
    (código, lon, lat). Misma ventana y procesamiento que el comparativo."""
    hoy = dt.date.today()
    f0 = ee.Date((hoy - dt.timedelta(days=dias)).isoformat())
    f1 = ee.Date(hoy.isoformat())  # hasta ayer: las estaciones llegan a ayer
    acum = gp._interpolar(gp._diaria_imerg(f0, f1).sum().rename("mm"), 11132)
    fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([lon, lat]), {"codigo": c})
        for c, lon, lat in puntos])
    res = acum.reduceRegions(collection=fc, reducer=ee.Reducer.first(),
                             scale=1000).getInfo()
    return {f["properties"]["codigo"]: f["properties"].get("first")
            for f in res["features"]}
