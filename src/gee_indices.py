"""Índices de vegetación y detección de cambios (movimientos en masa).

Base: Sentinel-2 SR armonizado con máscara de nubes Cloud Score+.

Productos:
  - NDVI / NDMI / BSI (compuestos medianos de un período)
  - ΔNDVI entre un período de referencia y uno reciente: la pérdida abrupta
    de vegetación (ΔNDVI muy negativo) en laderas es un indicador clásico de
    cicatrices de deslizamiento o remoción de cobertura.
  - Serie temporal mensual de NDVI medio del municipio.
"""
from __future__ import annotations

import datetime as dt

import ee

from .gee_session import roi, roi_buffer_km, tiles_de

UMBRAL_NUBES_CS = 0.60  # Cloud Score+ (cs): 0 = nublado, 1 = despejado

PALETA_NDVI = [
    "9e5b3d", "c9a227", "f5f0a9", "b7e075", "6fbf5a", "2e8b3d", "0b5e1f",
]
PALETA_DELTA = ["7f0000", "d73027", "fdae61", "ffffbf", "a6d96a", "1a9850"]
PALETA_NDMI = ["c9a227", "f5f0a9", "a6d9e8", "4fa3d1", "0b4f8a"]


# --------------------------------------------------------------------------
# Compuestos S2 con máscara de nubes Cloud Score+
# --------------------------------------------------------------------------
def _s2_limpia(fecha_ini: str, fecha_fin: str) -> ee.ImageCollection:
    s2 = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(roi())
        .filterDate(fecha_ini, fecha_fin)
    )
    csp = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")
    enlazada = s2.linkCollection(csp, ["cs"])

    def _mask(img):
        return img.updateMask(img.select("cs").gte(UMBRAL_NUBES_CS))

    return enlazada.map(_mask)


def _indices(img: ee.Image) -> ee.Image:
    ndvi = img.normalizedDifference(["B8", "B4"]).rename("NDVI")
    ndmi = img.normalizedDifference(["B8", "B11"]).rename("NDMI")
    # Bare Soil Index: resalta suelo desnudo (cicatrices de deslizamiento)
    bsi = img.expression(
        "((SWIR + RED) - (NIR + BLUE)) / ((SWIR + RED) + (NIR + BLUE))",
        {
            "SWIR": img.select("B11"),
            "RED": img.select("B4"),
            "NIR": img.select("B8"),
            "BLUE": img.select("B2"),
        },
    ).rename("BSI")
    return img.addBands([ndvi, ndmi, bsi])


def compuesto_indices(fecha_ini: str, fecha_fin: str) -> ee.Image:
    """Compuesto mediano con bandas NDVI/NDMI/BSI para un período."""
    return _s2_limpia(fecha_ini, fecha_fin).map(_indices).median()


# --------------------------------------------------------------------------
# Mapas
# --------------------------------------------------------------------------
def mapa_indice(indice: str, fecha_ini: str, fecha_fin: str) -> dict:
    comp = compuesto_indices(fecha_ini, fecha_fin).clip(roi_buffer_km(4))
    if indice == "NDVI":
        vis = {"min": 0.0, "max": 0.9, "palette": PALETA_NDVI}
        desc = ("Índice de vegetación de diferencia normalizada. Verde intenso = "
                "vegetación vigorosa; tonos pardos = suelo desnudo o roca "
                "(posibles cicatrices de deslizamiento).")
    elif indice == "NDMI":
        vis = {"min": -0.2, "max": 0.6, "palette": PALETA_NDMI}
        desc = ("Índice de humedad de la vegetación (NIR-SWIR). Valores altos = "
                "vegetación húmeda; caídas sostenidas pueden anticipar estrés "
                "o pérdida de cobertura.")
    else:  # BSI
        vis = {"min": -0.4, "max": 0.4,
               "palette": ["0b5e1f", "b7e075", "f5f0a9", "e0a26a", "8c4a2f"]}
        desc = ("Índice de suelo desnudo. Valores altos (pardo) marcan suelo "
                "expuesto: deslizamientos recientes, cortes de vía, erosión.")
    img = comp.select(indice)

    stats = img.reduceRegion(
        reducer=ee.Reducer.minMax().combine(ee.Reducer.mean(), sharedInputs=True),
        geometry=roi(),
        scale=20,
        maxPixels=1e9,
        bestEffort=True,
    ).getInfo()
    return {
        "tiles_url": tiles_de(img, vis),
        "vis": vis,
        "descripcion": desc,
        "media": round(stats.get(f"{indice}_mean") or 0, 3),
        "min": round(stats.get(f"{indice}_min") or 0, 3),
        "max": round(stats.get(f"{indice}_max") or 0, 3),
    }


def mapa_cambio_ndvi(ref_ini: str, ref_fin: str, act_ini: str, act_fin: str,
                     umbral_perdida: float = -0.20) -> dict:
    """ΔNDVI = NDVI(actual) − NDVI(referencia).

    Devuelve tiles del cambio continuo y de la máscara de pérdida severa
    (ΔNDVI < umbral), junto con el área afectada estimada en hectáreas.
    """
    ndvi_ref = compuesto_indices(ref_ini, ref_fin).select("NDVI")
    ndvi_act = compuesto_indices(act_ini, act_fin).select("NDVI")
    delta = ndvi_act.subtract(ndvi_ref).rename("dNDVI").clip(roi_buffer_km(4))

    perdida = delta.lt(umbral_perdida).And(ndvi_ref.gt(0.4)).selfMask()

    # Área de pérdida dentro del municipio (ha)
    area_img = perdida.multiply(ee.Image.pixelArea()).divide(10_000)
    area_ha = area_img.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=roi(),
        scale=20,
        maxPixels=1e9,
        bestEffort=True,
    ).getInfo()

    vis_delta = {"min": -0.5, "max": 0.5, "palette": PALETA_DELTA}
    return {
        "tiles_delta": tiles_de(delta, vis_delta),
        "tiles_perdida": tiles_de(perdida, {"palette": ["ff00ff"]}),
        "vis": vis_delta,
        "area_perdida_ha": round(list(area_ha.values())[0] or 0, 1) if area_ha else 0.0,
        "umbral": umbral_perdida,
        "descripcion": (
            "Rojo = pérdida de vegetación entre los dos períodos; verde = ganancia. "
            "La capa magenta marca pérdida severa (ΔNDVI < "
            f"{umbral_perdida}) sobre zonas que antes tenían vegetación densa: "
            "candidatas a movimientos en masa, deforestación o intervención antrópica. "
            "Verifique siempre contra la imagen en color real."
        ),
    }


# --------------------------------------------------------------------------
# Serie temporal NDVI (media municipal por mes)
# --------------------------------------------------------------------------
def serie_ndvi_mensual(meses: int = 24) -> list[dict]:
    hoy = dt.date.today().replace(day=1)
    geom = roi()
    puntos = []
    fechas = []
    for i in range(meses, 0, -1):
        anio = hoy.year + (hoy.month - 1 - i) // 12
        mes = (hoy.month - 1 - i) % 12 + 1
        fechas.append((anio, mes))

    lista = ee.List([[a, m] for a, m in fechas])

    def _mes(par):
        par = ee.List(par)
        a, m = ee.Number(par.get(0)), ee.Number(par.get(1))
        f0 = ee.Date.fromYMD(a, m, 1)
        f1 = f0.advance(1, "month")
        col = _s2_limpia("2015-01-01", "2100-01-01").filterDate(f0, f1)
        img = ee.Image(
            ee.Algorithms.If(
                col.size().gt(0),
                col.map(_indices).median().select("NDVI"),
                ee.Image.constant(-9999).rename("NDVI"),
            )
        )
        val = img.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=60,
            maxPixels=1e9,
            bestEffort=True,
        ).get("NDVI")
        return ee.Feature(
            None,
            {"fecha": f0.format("YYYY-MM"), "ndvi": ee.Algorithms.If(
                ee.Algorithms.IsEqual(val, None), -9999, val)},
        )

    fc = ee.FeatureCollection(lista.map(_mes)).getInfo()["features"]
    serie = []
    for f in fc:
        v = float(f["properties"]["ndvi"])
        if v > -1:  # descarta meses sin datos
            serie.append({"fecha": f["properties"]["fecha"], "ndvi": round(v, 3)})
    return sorted(serie, key=lambda x: x["fecha"])
