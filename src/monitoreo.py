"""Indicadores en vivo para el reporte municipal y monitoreo satelital de cambios.

- lluvia_municipio: serie diaria IMERG (90 días) y referencia CHIRPS de 30 días.
- vegetacion_municipio: pérdida severa de vegetación (Sentinel-2) y mapa PNG.
- cambios_recientes: modelo de cambio (Random Forest) entrenado con los cambios
  satelitales observados antes y después de los eventos confirmados; se aplica
  a los últimos 60 días frente a la ventana de 60 a 150 días atrás.
"""
from __future__ import annotations

import datetime as dt
import io
import json
from pathlib import Path

import ee
import streamlit as st

from . import gee_precipitacion as gp
from . import susceptibilidad as sus
from .gee_indices import UMBRAL_NUBES_CS
from .gee_session import geojson_municipios

DIR_DATA = Path(__file__).resolve().parent.parent / "data"
RUTA_CAMBIO = DIR_DATA / "modelo_cambio.json"


def _geom(codigo: str) -> ee.Geometry:
    if codigo == "66":  # todo el departamento
        return ee.FeatureCollection([ee.Feature(ee.Geometry(f["geometry"]))
                                     for f in geojson_municipios()["features"]]).geometry()
    for f in geojson_municipios()["features"]:
        if f["properties"]["codigo"] == codigo:
            return ee.Geometry(f["geometry"])
    raise KeyError(codigo)


def _gj(codigo: str) -> dict:
    return next(f for f in geojson_municipios()["features"]
                if f["properties"]["codigo"] == codigo)


# --------------------------------------------------------------------------
# Lluvia
# --------------------------------------------------------------------------
@st.cache_data(ttl=21600, show_spinner=False)
def lluvia_municipio(codigo: str, fecha: str) -> dict:
    hoy = dt.date.fromisoformat(fecha)
    geom = _geom(codigo)
    f0 = ee.Date((hoy - dt.timedelta(days=90)).isoformat())
    f1 = ee.Date((hoy + dt.timedelta(days=1)).isoformat())
    col = gp._diaria_imerg(f0, f1)

    def _red(img):
        v = gp._interpolar(img, 11132).reduceRegion(
            ee.Reducer.mean(), geom, 2000, maxPixels=1e9, bestEffort=True
        ).get("precipitation")
        return ee.Feature(None, {"fecha": ee.Date(img.get("system:time_start"))
                                 .format("YYYY-MM-dd"),
                                 "mm": ee.Algorithms.If(v, v, -1)})

    datos = ee.FeatureCollection(col.map(_red)).getInfo()["features"]
    serie = sorted(({"fecha": d["properties"]["fecha"], "mm": float(d["properties"]["mm"])}
                    for d in datos if float(d["properties"]["mm"]) >= 0),
                   key=lambda x: x["fecha"])
    # referencia de 30 días: promedio CHIRPS de la misma ventana en 20 años
    imgs = []
    for k in range(1, 21):
        try:
            fin = hoy.replace(year=hoy.year - k)
        except ValueError:
            fin = (hoy - dt.timedelta(days=1)).replace(year=hoy.year - k)
        imgs.append(ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
                    .filterDate((fin - dt.timedelta(days=30)).isoformat(),
                                (fin + dt.timedelta(days=1)).isoformat())
                    .select("precipitation").sum())
    ref = ee.ImageCollection.fromImages(imgs).mean().reduceRegion(
        ee.Reducer.mean(), geom, 5566, maxPixels=1e9, bestEffort=True
    ).get("precipitation").getInfo()
    u60 = serie[-60:]
    acum = lambda n: round(sum(x["mm"] for x in serie[-n:]), 1) if serie else None  # noqa: E731
    a30 = acum(30)
    return {"serie_completa": serie, "serie": u60, "acum7": acum(7), "acum30": a30,
            "ref30": round(ref, 1) if ref else None,
            "pct_ref": round(100 * a30 / ref) if ref and a30 is not None else None}


# --------------------------------------------------------------------------
# Vegetación
# --------------------------------------------------------------------------
def _ndvi(ini: str, fin: str, geom) -> ee.Image:
    s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(geom).filterDate(ini, fin)
    csp = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")
    return s2.linkCollection(csp, ["cs"]).map(
        lambda i: i.updateMask(i.select("cs").gte(UMBRAL_NUBES_CS))
        .normalizedDifference(["B8", "B4"]).rename("NDVI")).median()


@st.cache_data(ttl=86400, show_spinner=False)
def vegetacion_municipio(codigo: str, fecha: str) -> dict:
    import requests
    from PIL import Image, ImageDraw

    hoy = dt.date.fromisoformat(fecha)
    d = lambda n: (hoy - dt.timedelta(days=n)).isoformat()  # noqa: E731
    geom = _geom(codigo)
    ref = _ndvi(d(365), d(180), geom)
    act = _ndvi(d(60), (hoy + dt.timedelta(days=1)).isoformat(), geom)
    delta = act.subtract(ref).rename("d")
    perdida = delta.lt(-0.20).And(ref.gt(0.4))
    ha = perdida.multiply(ee.Image.pixelArea()).divide(1e4).reduceRegion(
        ee.Reducer.sum(), geom, 20, maxPixels=1e10, bestEffort=True).getInfo()
    ha = round(list(ha.values())[0] or 0) if ha else None
    png = None
    try:
        vis = delta.clip(geom).visualize(min=-0.5, max=0.5, palette=[
            "a50026", "f46d43", "fee08b", "ffffbf", "d9ef8b", "66bd63", "006837"])
        borde = ee.Image().byte().paint(ee.FeatureCollection([ee.Feature(geom)]), 1, 2) \
            .visualize(palette=["000000"])
        url = vis.blend(borde).getThumbURL({"region": geom.bounds(), "dimensions": 700,
                                            "format": "png"})
        img = Image.open(io.BytesIO(requests.get(url, timeout=120).content)).convert("RGBA")
        lienzo = Image.new("RGBA", (img.width, img.height + 46), "white")
        lienzo.paste(img, (0, 0), img)
        dib = ImageDraw.Draw(lienzo)
        cols = ["#a50026", "#f46d43", "#fee08b", "#ffffbf", "#d9ef8b", "#66bd63", "#006837"]
        w = img.width // 7
        for i, ccol in enumerate(cols):
            dib.rectangle([i * w, img.height + 6, (i + 1) * w, img.height + 20], fill=ccol)
        dib.text((2, img.height + 24), "Pérdida", fill="black")
        dib.text((img.width - 70, img.height + 24), "Ganancia", fill="black")
        dib.text((img.width // 2 - 60, img.height + 24), "Cambio de NDVI", fill="black")
        b = io.BytesIO()
        lienzo.convert("RGB").save(b, "PNG")
        png = b.getvalue()
    except Exception:  # noqa: BLE001
        png = None
    return {"perdida_ha": ha, "png": png}


# --------------------------------------------------------------------------
# Modelo de cambio
# --------------------------------------------------------------------------
def disponible_cambio() -> bool:
    return RUTA_CAMBIO.exists()


def _modelo_cambio() -> dict:
    return json.loads(RUTA_CAMBIO.read_text(encoding="utf-8"))


def _clasificador():
    mc = _modelo_cambio()
    feats = [ee.Feature(None, dict(zip(mc["campos"], fila))) for fila in mc["filas"]]
    fc = ee.FeatureCollection(feats)
    return (ee.Classifier.smileRandomForest(numberOfTrees=mc["n_arboles"],
                                            minLeafPopulation=mc["min_hoja"],
                                            bagFraction=0.6, seed=7)
            .setOutputMode("PROBABILITY").train(fc, "clase", mc["variables"])), mc


def _variables_cambio(fecha: str, region) -> ee.Image:
    t = ee.Date(fecha)
    csp = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")
    s2 = (ee.ImageCollection("COPERNICUS/S2_HARMONIZED").filterBounds(region)
          .linkCollection(csp, ["cs_cdf"])
          .map(lambda i: i.normalizedDifference(["B8", "B4"]).rename("ndvi")
               .updateMask(i.select("cs_cdf").gte(0.6))))
    s1 = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(region)
          .filter(ee.Filter.eq("instrumentMode", "IW"))
          .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
          .select(["VV", "VH"]))
    a0, a1, d0, d1 = t.advance(-150, "day"), t.advance(-60, "day"), t.advance(-60, "day"), t
    n0 = s2.filterDate(a0, a1).median().unmask(-99)
    n1 = s2.filterDate(d0, d1).median().unmask(-99)
    r0 = s1.filterDate(a0, a1).median()
    r1 = s1.filterDate(d0, d1).median()
    ch = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
    im = gp._diaria_imerg(t.advance(-60, "day"), t)
    ll30 = im.filterDate(t.advance(-30, "day"), t).sum().rename("lluvia30")
    ll60 = im.sum().rename("lluvia60")
    mx = im.max().rename("lluvia_max1d")
    _ = ch
    img = ee.Image.cat([
        n0.rename("ndvi_antes"), n1.rename("ndvi_despues"),
        r0.select("VV").rename("vv_antes"), r1.select("VV").rename("vv_despues"),
        r0.select("VH").rename("vh_antes"), r1.select("VH").rename("vh_despues"),
        gp._interpolar(ll30, 11132), gp._interpolar(ll60, 11132),
        gp._interpolar(mx, 11132)])
    img = img.addBands(img.select("ndvi_despues").subtract(img.select("ndvi_antes"))
                       .rename("d_ndvi"))
    img = img.addBands(img.select("vv_despues").subtract(img.select("vv_antes"))
                       .rename("d_vv"))
    img = img.addBands(img.select("vh_despues").subtract(img.select("vh_antes"))
                       .rename("d_vh"))
    pend = ee.Terrain.slope(ee.Image("NASA/NASADEM_HGT/001").select("elevation"))
    return img.addBands(pend.rename("pendiente"))


@st.cache_data(ttl=43200, show_spinner=False)
def cambios_recientes(fecha: str) -> dict:
    """Probabilidad de cambio compatible con movimiento en masa en los últimos
    60 días, sobre zonas de susceptibilidad media o mayor."""
    clf, mc = _clasificador()
    region = ee.Geometry.Rectangle([-76.45, 4.65, -75.35, 5.55])
    dep = ee.FeatureCollection([ee.Feature(ee.Geometry(f["geometry"]))
                                for f in geojson_municipios()["features"]]).geometry()
    x = _variables_cambio(fecha, region).select(mc["variables"])
    p = x.classify(clf).rename("p").clip(dep)
    umbral = mc["umbral"]
    pend = ee.Terrain.slope(ee.Image("NASA/NASADEM_HGT/001").select("elevation"))
    vis_img = p.updateMask(p.gte(umbral).And(pend.gt(8)))
    tiles = vis_img.getMapId({"min": umbral, "max": 1,
                              "palette": ["ffff00", "ff8800", "ff00aa"]})["tile_fetcher"].url_format
    zonas = []
    try:
        vec = vis_img.gte(umbral).selfMask().reduceToVectors(
            geometry=dep, scale=60, geometryType="centroid", eightConnected=True,
            maxPixels=1e9, bestEffort=True, tileScale=4)
        vec = p.reduceRegions(vec, ee.Reducer.max().combine(ee.Reducer.count(), "", True),
                              60).sort("max", False).limit(60)
        for f in vec.getInfo()["features"]:
            lon, lat = f["geometry"]["coordinates"]
            zonas.append({"lat": round(lat, 4), "lon": round(lon, 4),
                          "prob": round(100 * (f["properties"].get("max") or 0)),
                          "area_ha": round((f["properties"].get("count") or 0) * 0.36, 1),
                          "clase": sus.clase_en(lat, lon) or ""})
    except Exception:  # noqa: BLE001
        pass
    from shapely.geometry import Point, shape
    polis = [(f["properties"]["codigo"], shape(f["geometry"]))
             for f in geojson_municipios()["features"]]
    for z in zonas:
        z["codigo"] = next((c for c, g in polis if g.contains(Point(z["lon"], z["lat"]))), None)
    zonas = [z for z in zonas if z["clase"] in ("Media", "Alta", "Muy alta")]
    return {"tiles": tiles, "zonas": zonas, "umbral": umbral, "fecha": fecha}


def cambios_municipio(cambio: dict | None, codigo: str) -> dict | None:
    if not cambio:
        return None
    z = [x for x in cambio["zonas"] if x.get("codigo") == codigo]
    return {"n_zonas": len(z), "zonas": z}
