"""Herramientas interactivas del SAT Risaralda.

  - Consulta por clic: municipio y punto (amenaza SGC, lluvia, pendiente y
    evento más cercano).
  - Semáforo con umbrales ajustables.
  - Estadísticas de una zona dibujada por el usuario.
  - Exportación: mapa temático (PNG) y libro de Excel con la cita institucional.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import math
from functools import lru_cache

import pandas as pd
import requests
import streamlit as st
from shapely.geometry import Point, shape

from . import riesgo
from .gee_session import geojson_municipios

URL_AMENAZA = ("https://geoportal.sgc.gov.co/arcgis/rest/services/SIMMA/"
               "ZonificacionAmenazaCache/MapServer")

# Colores de la leyenda del servicio del SGC (categorías de amenaza relativa).
COLOR_AMENAZA = {
    "Muy baja": (55, 168, 0), "Baja": (153, 230, 0), "Media": (255, 255, 0),
    "Alta": (255, 169, 0), "Muy alta": (255, 0, 0),
}

# Umbrales por defecto del nivel de atención (los mismos de src/riesgo.py).
U_LLUVIA = (100, 130, 170)     # % de la referencia: puntos 1, 2 y 3
U_AMENAZA = (30, 60, 80)       # % del área en amenaza alta y muy alta
CORTES = (2, 4)                # suma ≤2 bajo; ≤4 moderado; mayor alto


# --------------------------------------------------------------------------
# Municipio bajo un clic
# --------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _polis() -> list[tuple[dict, object]]:
    return [(f["properties"], shape(f["geometry"]))
            for f in geojson_municipios()["features"]]


def municipio_en(lat: float, lon: float) -> dict | None:
    """Propiedades del municipio que contiene el punto (None si queda fuera
    de Risaralda)."""
    p = Point(lon, lat)
    for props, g in _polis():
        if g.contains(p):
            return dict(props)
    return None


# --------------------------------------------------------------------------
# Consulta por punto
# --------------------------------------------------------------------------
@st.cache_data(ttl=86400, show_spinner=False)
def amenaza_en_punto(lat: float, lon: float) -> dict | None:
    """Categoría de amenaza por movimientos en masa del SGC en el punto
    (escala 1:100.000; si no hay cobertura, la regional 1:500.000)."""
    try:
        r = requests.get(URL_AMENAZA + "/identify", params={
            "geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint",
            "sr": 4326, "layers": "all:11,12", "tolerance": 2,
            "mapExtent": f"{lon - .1},{lat - .1},{lon + .1},{lat + .1}",
            "imageDisplay": "400,400,96", "returnGeometry": "false",
            "f": "json"}, timeout=30)
        res = r.json().get("results", [])
    except Exception:  # noqa: BLE001
        return None
    for capa, escala in ((11, "1:100.000"), (12, "1:500.000")):
        for x in res:
            cat = (x.get("attributes") or {}).get("CatAme")
            if x.get("layerId") == capa and cat:
                return {"categoria": cat, "escala": escala}
    return None


def evento_cercano(lat: float, lon: float) -> dict | None:
    """Evento del SIMMA más próximo al punto (distancia en km)."""
    df = riesgo.puntos_simma()
    if df.empty:
        return None
    f1, f2 = math.radians(lat), df["lat"].map(math.radians)
    dl = (df["lon"] - lon).map(math.radians)
    a = ((f2 - f1) / 2).map(math.sin) ** 2 + math.cos(f1) * f2.map(
        math.cos) * (dl / 2).map(math.sin) ** 2
    d = 2 * 6371.0 * a.map(lambda v: math.asin(min(1.0, math.sqrt(v))))
    i = d.idxmin()
    fila = df.loc[i]
    return {"km": float(d.loc[i]), "tipo": fila["tipo"],
            "origen": fila["origen"], "id": int(fila["id"]),
            "lat": float(fila["lat"]), "lon": float(fila["lon"])}


def _acum_imerg(dias: int):
    import ee

    from . import gee_precipitacion as gp
    hoy = dt.date.today()
    f0 = ee.Date((hoy - dt.timedelta(days=dias)).isoformat())
    f1 = ee.Date((hoy + dt.timedelta(days=1)).isoformat())
    return gp._interpolar(gp._diaria_imerg(f0, f1).sum().rename("mm"), 11132)


def _normal_img(dias: int, anios: int = 20):
    """Lluvia acumulada media (mm) de la misma ventana en los últimos anios
    años (CHIRPS diario): referencia de apoyo del SAT."""
    import ee
    hoy = dt.date.today()
    imgs = []
    for k in range(1, anios + 1):
        try:
            fin = hoy.replace(year=hoy.year - k)
        except ValueError:
            fin = (hoy - dt.timedelta(days=1)).replace(year=hoy.year - k)
        ini = fin - dt.timedelta(days=dias)
        imgs.append(ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
                    .filterDate(ini.isoformat(),
                                (fin + dt.timedelta(days=1)).isoformat())
                    .select("precipitation").sum())
    return ee.ImageCollection.fromImages(imgs).mean().rename("mm")


def _dem():
    import ee
    return ee.Image("NASA/NASADEM_HGT/001").select("elevation")


@st.cache_data(ttl=21600, show_spinner=False)
def datos_punto(lat: float, lon: float, fecha: str) -> dict:
    """Lluvia (IMERG), referencia (CHIRPS), cota y pendiente (NASADEM) en un
    punto. Devuelve {'valores': {...}, 'error': str | None}."""
    import ee
    try:
        pt = ee.Geometry.Point([lon, lat])
        dem = _dem()
        img = ee.Image.cat([
            _acum_imerg(7).rename("l7"), _acum_imerg(30).rename("l30"),
            _normal_img(30).rename("nor"), dem.rename("elev"),
            ee.Terrain.slope(dem).rename("pend")])
        v = img.reduceRegion(ee.Reducer.first(), pt, 30).getInfo()
        l30, nor = v.get("l30"), v.get("nor")
        v["pct"] = (l30 / nor * 100) if (l30 is not None and nor) else None
        return {"valores": v, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"valores": {}, "error": str(exc)}


# --------------------------------------------------------------------------
# Semáforo con umbrales ajustables
# --------------------------------------------------------------------------
def _puntos(v, cortes) -> int | None:
    if v is None or pd.isna(v):
        return None
    return sum(v >= c for c in cortes)


def nivel_con_umbrales(pct_normal, pct_alta, u_lluvia=U_LLUVIA,
                       u_amenaza=U_AMENAZA, cortes=CORTES) -> str:
    """Igual que riesgo.nivel_atencion, con umbrales parametrizables.
    Cada variable aporta de 0 a 3 puntos (uno por cada umbral superado); la
    suma se clasifica en Bajo, Moderado o Alto según cortes."""
    a, b = _puntos(pct_normal, u_lluvia), _puntos(pct_alta, u_amenaza)
    if a is None or b is None:
        return "Sin dato"
    s = a + b
    return "Bajo" if s <= cortes[0] else ("Moderado" if s <= cortes[1] else "Alto")


# --------------------------------------------------------------------------
# Zona dibujada por el usuario
# --------------------------------------------------------------------------
def _area_km2(g) -> float:
    lat0 = g.centroid.y
    return abs(g.area) * (111.32 * math.cos(math.radians(lat0))) * 110.57


def _merc(lon, lat):
    return (lon * 20037508.342789244 / 180.0,
            math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * 6378137.0)


@st.cache_data(ttl=86400, show_spinner=False)
def composicion_amenaza(geom_json: str) -> dict | None:
    """% del área de la zona en cada categoría de amenaza del SGC (se
    clasifica por color la imagen del servicio, sobre la zona)."""
    from PIL import Image, ImageDraw
    g = json.loads(geom_json)
    sg = shape(g)
    lo0, la0, lo1, la1 = sg.bounds
    x0, y0 = _merc(lo0, la0)
    x1, y1 = _merc(lo1, la1)
    k = 500 / max(x1 - x0, y1 - y0)
    an, al = max(20, int((x1 - x0) * k)), max(20, int((y1 - y0) * k))
    try:
        r = requests.get(URL_AMENAZA + "/export", params={
            "bbox": f"{x0},{y0},{x1},{y1}", "bboxSR": 3857, "imageSR": 3857,
            "size": f"{an},{al}", "format": "png32", "transparent": "true",
            "f": "image"}, timeout=60)
        if r.status_code != 200 or "image" not in r.headers.get("content-type", ""):
            return None
        img = Image.open(io.BytesIO(r.content)).convert("RGBA")
    except Exception:  # noqa: BLE001
        return None
    masc = Image.new("L", img.size, 0)
    dib = ImageDraw.Draw(masc)
    polis = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    for poli in polis:
        for i, anillo in enumerate(poli):
            pts = []
            for c in anillo:
                x, y = _merc(c[0], c[1])
                pts.append(((x - x0) / (x1 - x0) * img.size[0],
                            (y1 - y) / (y1 - y0) * img.size[1]))
            dib.polygon(pts, fill=255 if i == 0 else 0)
    px, mk = img.load(), masc.load()
    cuenta = {n: 0 for n in COLOR_AMENAZA}
    dentro = 0
    for yy in range(img.size[1]):
        for xx in range(img.size[0]):
            if mk[xx, yy] < 128:
                continue
            dentro += 1
            r_, g_, b_, a_ = px[xx, yy]
            if a_ < 128:
                continue
            mejor, dmin = None, 60 ** 2 * 3
            for n, (cr, cg, cb) in COLOR_AMENAZA.items():
                d = (r_ - cr) ** 2 + (g_ - cg) ** 2 + (b_ - cb) ** 2
                if d < dmin:
                    mejor, dmin = n, d
            if mejor:
                cuenta[mejor] += 1
    if not dentro:
        return None
    out = {n: c / dentro * 100 for n, c in cuenta.items()}
    out["Sin clasificar"] = max(0.0, 100 - sum(out.values()))
    return out


@st.cache_data(ttl=21600, show_spinner=False)
def estadisticas_zona(geom_json: str, fecha: str) -> dict:
    """Indicadores de una zona: lluvia, relieve, pérdida de vegetación,
    población, amenaza SGC, eventos SIMMA y municipios que toca.
    Cada bloque falla por separado y deja su mensaje en errores."""
    import ee

    from .gee_comparativo import _ndvi
    g = json.loads(geom_json)
    sg = shape(g)
    eeg = ee.Geometry(g)
    out: dict = {"area_km2": _area_km2(sg), "errores": []}

    try:
        v = ee.Image.cat([_acum_imerg(7).rename("l7"),
                          _acum_imerg(30).rename("l30"),
                          _normal_img(30).rename("nor")]).reduceRegion(
            ee.Reducer.mean(), eeg, 1000, maxPixels=1e9,
            tileScale=4).getInfo()
        out["lluvia_7d"], out["lluvia_30d"], out["normal_30d"] = (
            v.get("l7"), v.get("l30"), v.get("nor"))
        out["pct_normal_30d"] = (out["lluvia_30d"] / out["normal_30d"] * 100
                                 if out["lluvia_30d"] is not None
                                 and out["normal_30d"] else None)
    except Exception as exc:  # noqa: BLE001
        out["errores"].append(f"Lluvia: {exc}")

    try:
        dem = _dem()
        pend = ee.Terrain.slope(dem)
        v = ee.Image.cat([pend.rename("pend"),
                          pend.gt(30).multiply(100).rename("p30")]
                         ).reduceRegion(ee.Reducer.mean(), eeg, 30,
                                        maxPixels=1e9, tileScale=4).getInfo()
        mm = dem.reduceRegion(ee.Reducer.minMax(), eeg, 30, maxPixels=1e9,
                              tileScale=4).getInfo()
        out["pendiente_media"], out["pct_pend_30"] = v.get("pend"), v.get("p30")
        out["elev_min"], out["elev_max"] = (mm.get("elevation_min"),
                                            mm.get("elevation_max"))
    except Exception as exc:  # noqa: BLE001
        out["errores"].append(f"Relieve: {exc}")

    try:
        hoy = dt.date.today()
        d = lambda n: (hoy - dt.timedelta(days=n)).isoformat()  # noqa: E731
        ref = _ndvi(d(365), d(180), eeg)
        act = _ndvi(d(60), (hoy + dt.timedelta(days=1)).isoformat(), eeg)
        perd = act.subtract(ref).lt(-0.20).And(ref.gt(0.4))
        ha = perd.multiply(ee.Image.pixelArea()).divide(10_000).rename("ha")
        v = ha.reduceRegion(ee.Reducer.sum(), eeg, 40, maxPixels=1e9,
                            tileScale=8).getInfo()
        out["perdida_ha"] = v.get("ha")
    except Exception as exc:  # noqa: BLE001
        out["errores"].append(f"Vegetación: {exc}")

    try:
        pop = (ee.ImageCollection("WorldPop/GP/100m/pop")
               .filter(ee.Filter.eq("country", "COL"))
               .filter(ee.Filter.eq("year", 2020)).mosaic())
        v = pop.reduceRegion(ee.Reducer.sum(), eeg, 100, maxPixels=1e9,
                             tileScale=4).getInfo()
        out["poblacion"] = next(iter(v.values()), None)
    except Exception as exc:  # noqa: BLE001
        out["errores"].append(f"Población: {exc}")

    out["amenaza"] = composicion_amenaza(geom_json)
    if out["amenaza"] is None:
        out["errores"].append("Amenaza SGC: el servicio no respondió.")

    try:
        import shapely
        ev = riesgo.puntos_simma()
        dentro = shapely.contains_xy(sg, ev["lon"].to_numpy(),
                                     ev["lat"].to_numpy())
        out["eventos"] = ev[dentro].reset_index(drop=True)
    except Exception as exc:  # noqa: BLE001
        out["eventos"] = pd.DataFrame()
        out["errores"].append(f"Eventos: {exc}")

    filas = []
    for props, poli in _polis():
        inter = poli.intersection(sg)
        if not inter.is_empty and inter.area > 0:
            filas.append({"Municipio": props["nombre"],
                          "Área de la zona (km²)": _area_km2(inter),
                          "% de la zona": inter.area / sg.area * 100})
    out["municipios"] = (pd.DataFrame(filas).sort_values(
        "% de la zona", ascending=False) if filas else pd.DataFrame())
    return out


# --------------------------------------------------------------------------
# Exportación
# --------------------------------------------------------------------------
def excel_bytes(hojas: dict[str, pd.DataFrame], notas: list[str]) -> bytes:
    """Libro de Excel con las tablas indicadas y una hoja «Cita y notas»."""
    from .ui import CITA, DEPENDENCIA, ENTIDAD
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for nombre, df in hojas.items():
            df.to_excel(xw, sheet_name=nombre[:31], index=False)
            ws = xw.sheets[nombre[:31]]
            for col in ws.columns:
                ancho = max(len(str(c.value)) if c.value is not None else 0
                            for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(
                    max(10, ancho + 2), 48)
        filas = ([ENTIDAD, DEPENDENCIA,
                  f"Fecha de corte: {dt.date.today().strftime('%d/%m/%Y')}", "",
                  "Cómo citar:", CITA, ""] + notas)
        pd.DataFrame({"Cita y notas": filas}).to_excel(
            xw, sheet_name="Cita y notas", index=False)
        xw.sheets["Cita y notas"].column_dimensions["A"].width = 120
    return buf.getvalue()


def _fuente(tam: int, negrita: bool = False):
    from PIL import ImageFont
    nombres = (["DejaVuSans-Bold.ttf", "arialbd.ttf"] if negrita
               else ["DejaVuSans.ttf", "arial.ttf"])
    for n in nombres:
        try:
            return ImageFont.truetype(n, tam)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default(size=tam)


def mapa_png(valores: dict[str, float | None], titulo: str, unidad: str,
             c_min: tuple, c_max: tuple) -> bytes:
    """Mapa temático de los 14 municipios (PNG) con leyenda, fuente y cita."""
    from PIL import Image, ImageDraw

    from .ui import CITA, DEPENDENCIA, ENTIDAD
    feats = geojson_municipios()["features"]
    lons, lats = [], []

    def _walk(c):
        if isinstance(c[0], (int, float)):
            lons.append(c[0])
            lats.append(c[1])
        else:
            for s in c:
                _walk(s)
    for f in feats:
        _walk(f["geometry"]["coordinates"])
    lo0, lo1, la0, la1 = min(lons), max(lons), min(lats), max(lats)
    kx = math.cos(math.radians((la0 + la1) / 2))
    W, mapa_w = 1400, 900
    esc = mapa_w / ((lo1 - lo0) * kx)
    mapa_h = int((la1 - la0) * esc)
    H = max(mapa_h + 150 + 210, 900)
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    ox, oy = 40, 150

    def px(lon, lat):
        return (ox + (lon - lo0) * kx * esc, oy + (la1 - lat) * esc)

    vals = [v for v in valores.values() if v is not None and not pd.isna(v)]
    vmin, vmax = (min(vals), max(vals)) if vals else (0, 1)

    def color(v):
        if v is None or pd.isna(v):
            return (176, 183, 189)
        t = 0.0 if vmax == vmin else (v - vmin) / (vmax - vmin)
        return tuple(int(c_min[i] + t * (c_max[i] - c_min[i])) for i in range(3))

    for f in feats:
        g = f["geometry"]
        polis = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        col = color(valores.get(f["properties"]["codigo"]))
        for poli in polis:
            for i, anillo in enumerate(poli):
                pts = [px(c[0], c[1]) for c in anillo]
                d.polygon(pts, fill=col if i == 0 else "white",
                          outline=(60, 60, 60))
    ft, fn = _fuente(15), _fuente(14, True)
    for props, poli in _polis():
        p = poli.representative_point()
        x, y = px(p.x, p.y)
        v = valores.get(props["codigo"])
        txt = props["nombre"] + ("" if v is None or pd.isna(v) else f"\n{v:.0f}")
        d.multiline_text((x, y), txt, fill=(20, 20, 20), font=ft, anchor="mm",
                         align="center", stroke_width=2, stroke_fill="white")
    # Encabezado
    d.text((40, 24), titulo, fill=(0, 75, 135), font=_fuente(26, True))
    d.text((40, 62), DEPENDENCIA, fill=(0, 138, 75), font=_fuente(15, True))
    d.text((40, 84), ENTIDAD, fill=(85, 85, 85), font=_fuente(15))
    d.text((40, 108), f"Fecha de corte: {dt.date.today().strftime('%d/%m/%Y')}",
           fill=(85, 85, 85), font=_fuente(15))
    d.rectangle([40, 134, 40 + 150, 138], fill=(0, 75, 135))
    d.rectangle([190, 134, 340, 138], fill=(0, 138, 75))
    d.rectangle([340, 134, 490, 138], fill=(255, 204, 0))
    # Leyenda
    lx, ly = ox + mapa_w + 50, oy + 40
    d.text((lx, ly - 30), f"{titulo.split('·')[-1].strip()}", fill="black", font=fn)
    for k in range(200):
        t = 1 - k / 199
        c = tuple(int(c_min[i] + t * (c_max[i] - c_min[i])) for i in range(3))
        d.rectangle([lx, ly + k * 2, lx + 28, ly + k * 2 + 2], fill=c)
    d.text((lx + 40, ly), f"{vmax:.0f} {unidad}".strip(), fill="black", font=ft,
           anchor="lm")
    d.text((lx + 40, ly + 400), f"{vmin:.0f} {unidad}".strip(), fill="black",
           font=ft, anchor="lm")
    d.rectangle([lx, ly + 430, lx + 28, ly + 446], fill=(176, 183, 189))
    d.text((lx + 40, ly + 438), "Sin dato", fill="black", font=ft, anchor="lm")
    # Pie con la cita
    y = H - 150
    d.line([40, y, W - 40, y], fill=(200, 200, 200), width=2)
    from textwrap import wrap
    pie = ("Cómo citar: " + CITA + " Los valores son indicativos y no sustituyen "
           "las alertas oficiales del IDEAM, del SGC ni las decisiones de los "
           "CMGRD/CDGRD.")
    for i, linea in enumerate(wrap(pie, 150)):
        d.text((40, y + 14 + i * 20), linea, fill=(85, 85, 85), font=_fuente(14))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
