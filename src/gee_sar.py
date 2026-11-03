"""Detección de cambios con radar Sentinel-1 (banda C, polarización VV).

El radar atraviesa las nubes, algo decisivo en Risaralda. Se compara la
retrodispersión (dB) de una ventana reciente con la de una ventana de
referencia anterior, siempre con la misma órbita relativa para que la
geometría de observación sea idéntica. Un cambio fuerte sobre ladera se marca
como zona para verificación; NO confirma un movimiento en masa.
"""
from __future__ import annotations

import datetime as dt

import ee

from .gee_comparativo import _municipios_fc
from .gee_session import roi, tiles_de

VIS_CAMBIO = {"min": -6, "max": 6,
              "palette": ["#2166ac", "#67a9cf", "#f7f7f7", "#fdb863", "#e66101"]}
VIS_MARCA = {"palette": ["#ff00ff"], "min": 0, "max": 1}


def _col(geom, ini: str, fin: str, orbita: str) -> ee.ImageCollection:
    return (ee.ImageCollection("COPERNICUS/S1_GRD")
            .filterBounds(geom).filterDate(ini, fin)
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
            .filter(ee.Filter.eq("orbitProperties_pass", orbita)))


def _ventanas(dias_rec: int, dias_ref: int) -> tuple[str, str, str, str]:
    hoy = dt.date.today()
    fin = (hoy + dt.timedelta(days=1)).isoformat()
    ini_rec = (hoy - dt.timedelta(days=dias_rec)).isoformat()
    ini_ref = (hoy - dt.timedelta(days=dias_rec + dias_ref)).isoformat()
    return ini_ref, ini_rec, ini_rec, fin


def _cambio(geom, dias_rec: int, dias_ref: int) -> tuple[ee.Image, dict]:
    """Imagen de cambio (dB) y metadatos de la comparación."""
    ini_ref, fin_ref, ini_rec, fin_rec = _ventanas(dias_rec, dias_ref)
    n = {o: _col(geom, ini_rec, fin_rec, o).size().getInfo()
         for o in ("ASCENDING", "DESCENDING")}
    orbita = max(n, key=n.get)
    if n[orbita] == 0:
        raise RuntimeError("No hay imágenes Sentinel-1 en la ventana reciente.")
    rec = _col(geom, ini_rec, fin_rec, orbita).select("VV")
    ref = _col(geom, ini_ref, fin_ref, orbita).select("VV")

    rels = sorted(set(rec.aggregate_array("relativeOrbitNumber_start").getInfo()))
    difs, usadas = [], []
    for r in rels:
        rr = rec.filter(ee.Filter.eq("relativeOrbitNumber_start", r))
        rf = ref.filter(ee.Filter.eq("relativeOrbitNumber_start", r))
        if rf.size().getInfo() == 0:
            continue
        a = rr.median().focalMedian(30, "circle", "meters")
        b = rf.median().focalMedian(30, "circle", "meters")
        difs.append(a.subtract(b).rename("dVV"))
        usadas.append(r)
    if not difs:
        raise RuntimeError("No hay imágenes de referencia con la misma órbita.")
    cambio = ee.ImageCollection.fromImages(difs).mean().rename("dVV")

    t = rec.aggregate_array("system:time_start").getInfo()
    meta = {
        "orbita": "Ascendente" if orbita == "ASCENDING" else "Descendente",
        "orbitas_relativas": usadas,
        "n_reciente": int(rec.size().getInfo()),
        "n_referencia": int(ref.size().getInfo()),
        "fecha_ini": dt.datetime.fromtimestamp(min(t) / 1000, dt.timezone.utc).strftime("%d/%m/%Y"),
        "fecha_fin": dt.datetime.fromtimestamp(max(t) / 1000, dt.timezone.utc).strftime("%d/%m/%Y"),
        "ventana_referencia": f"{ini_ref} a {fin_ref}",
    }
    return cambio, meta


def _marcas(cambio: ee.Image, umbral: float, pend_min: float) -> ee.Image:
    dem = ee.Image("NASA/NASADEM_HGT/001").select("elevation")
    pend = ee.Terrain.slope(dem)
    en_ladera = pend.gte(pend_min)
    neg = cambio.lt(-umbral).And(en_ladera).rename("neg")
    pos = cambio.gt(umbral).And(en_ladera).rename("pos")
    return neg.addBands(pos)


def mapa_cambio(dias_rec: int = 24, dias_ref: int = 90, umbral: float = 3.0,
                pend_min: float = 15.0) -> dict:
    """Capas y estadísticas para la unidad de análisis activa."""
    geom = roi()
    cambio, meta = _cambio(geom, dias_rec, dias_ref)
    marcas = _marcas(cambio, umbral, pend_min)
    alerta = marcas.reduce(ee.Reducer.max()).selfMask()

    ha = (marcas.multiply(ee.Image.pixelArea()).divide(10_000)
          .reduceRegion(ee.Reducer.sum(), geom, 30, maxPixels=int(1e10),
                        tileScale=4).getInfo())
    area_ha = geom.area(100).divide(10_000).getInfo()
    ha_neg, ha_pos = ha.get("neg") or 0.0, ha.get("pos") or 0.0
    meta.update({
        "tiles_cambio": tiles_de(cambio.clip(geom), VIS_CAMBIO),
        "tiles_marca": tiles_de(alerta.clip(geom), VIS_MARCA),
        "ha_dismin": ha_neg, "ha_aumento": ha_pos,
        "ha_total": ha_neg + ha_pos,
        "pct": (ha_neg + ha_pos) / area_ha * 100 if area_ha else 0.0,
        "area_ha": area_ha,
    })
    return meta


def ranking_municipal(dias_rec: int = 24, dias_ref: int = 90,
                      umbral: float = 3.0, pend_min: float = 15.0) -> list[dict]:
    """Hectáreas con cambio fuerte sobre ladera, por municipio."""
    fc = _municipios_fc()
    cambio, _ = _cambio(fc.geometry(), dias_rec, dias_ref)
    marcas = _marcas(cambio, umbral, pend_min)
    res = (marcas.multiply(ee.Image.pixelArea()).divide(10_000)
           .reduceRegions(collection=fc, reducer=ee.Reducer.sum(), scale=40,
                          tileScale=4).getInfo())
    filas = []
    for f in res["features"]:
        p = f["properties"]
        neg, pos = p.get("neg") or 0.0, p.get("pos") or 0.0
        filas.append({
            "codigo": p["codigo"], "nombre": p["nombre"],
            "area_km2": p["area_km2"], "ha_dismin": neg, "ha_aumento": pos,
            "ha_total": neg + pos,
            "pct": (neg + pos) / (p["area_km2"] * 100) * 100,
        })
    return sorted(filas, key=lambda r: -r["pct"])
