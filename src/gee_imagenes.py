"""Imágenes satelitales disponibles para el municipio de Pajarito.

  - Sentinel-2 SR armonizado (óptico, 10 m, ~5 días de revisita)
  - Landsat 8/9 Collection 2 Level 2 (óptico, 30 m, ~8 días combinados)
  - Sentinel-1 GRD (radar SAR, ~10 m, penetra nubes)

Cada fuente expone: catálogo de escenas (con filtros de fecha y nubosidad)
y tiles de visualización para una escena o compuesto.
"""
from __future__ import annotations

import ee

from .gee_session import roi, roi_buffer_km, tiles_de

# --------------------------------------------------------------------------
# Visualizaciones ópticas
# --------------------------------------------------------------------------
VIS_S2 = {
    "color_real": {
        "nombre": "Color real (B4-B3-B2)",
        "bands": ["B4", "B3", "B2"],
        "min": 0, "max": 3000, "gamma": 1.2,
        "descripcion": "Como lo vería el ojo humano. Útil para identificar "
                       "cicatrices de deslizamientos, cambios de uso del suelo y nubes.",
    },
    "falso_color_veg": {
        "nombre": "Falso color vegetación (B8-B4-B3)",
        "bands": ["B8", "B4", "B3"],
        "min": 0, "max": 4000, "gamma": 1.2,
        "descripcion": "El infrarrojo cercano resalta la vegetación en rojo intenso. "
                       "Suelo desnudo y deslizamientos recientes aparecen en tonos cian/gris.",
    },
    "swir": {
        "nombre": "SWIR (B12-B8A-B4)",
        "bands": ["B12", "B8A", "B4"],
        "min": 0, "max": 4000, "gamma": 1.2,
        "descripcion": "Infrarrojo de onda corta: distingue humedad del suelo, "
                       "roca expuesta y áreas quemadas.",
    },
}

VIS_LANDSAT = {
    "color_real": {
        "nombre": "Color real (SR_B4-B3-B2)",
        "bands": ["SR_B4", "SR_B3", "SR_B2"],
        "min": 0.0, "max": 0.25, "gamma": 1.35,
        "descripcion": "Color natural Landsat (30 m). Serie histórica desde 2013 (L8).",
    },
    "falso_color_veg": {
        "nombre": "Falso color vegetación (SR_B5-B4-B3)",
        "bands": ["SR_B5", "SR_B4", "SR_B3"],
        "min": 0.0, "max": 0.4, "gamma": 1.3,
        "descripcion": "Vegetación en rojo (NIR). Complementa a Sentinel-2 con más historia.",
    },
}


# --------------------------------------------------------------------------
# Sentinel-2
# --------------------------------------------------------------------------
def _s2_coleccion(fecha_ini: str, fecha_fin: str, max_nubes: float) -> ee.ImageCollection:
    return (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(roi())
        .filterDate(fecha_ini, fecha_fin)
        .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", max_nubes))
    )


def escenas_s2(fecha_ini: str, fecha_fin: str, max_nubes: float = 60) -> list[dict]:
    """Catálogo de escenas Sentinel-2 sobre el municipio (una por día)."""
    col = _s2_coleccion(fecha_ini, fecha_fin, max_nubes)
    feats = col.map(
        lambda im: ee.Feature(
            None,
            {
                "fecha": ee.Date(im.get("system:time_start")).format("YYYY-MM-dd"),
                "nubes": im.get("CLOUDY_PIXEL_PERCENTAGE"),
            },
        )
    )
    datos = ee.FeatureCollection(feats).getInfo()["features"]
    vistos: dict[str, float] = {}
    for f in datos:
        p = f["properties"]
        fch, nb = p["fecha"], float(p["nubes"] or 0)
        if fch not in vistos or nb < vistos[fch]:
            vistos[fch] = nb
    return sorted(
        ({"fecha": k, "nubes": round(v, 1)} for k, v in vistos.items()),
        key=lambda x: x["fecha"],
        reverse=True,
    )


def tiles_s2(vis_key: str, fecha: str | None, fecha_ini: str, fecha_fin: str,
             max_nubes: float = 60) -> dict:
    """Tiles de una escena S2 (por fecha) o del compuesto mediano del rango."""
    vis = VIS_S2[vis_key]
    if fecha:
        f0 = ee.Date(fecha)
        col = _s2_coleccion(fecha, f0.advance(1, "day").format("YYYY-MM-dd").getInfo(), 100)
        img = col.mosaic()
        etiqueta = fecha
    else:
        img = _s2_coleccion(fecha_ini, fecha_fin, max_nubes).median()
        etiqueta = f"Compuesto {fecha_ini} a {fecha_fin}"
    img = img.clip(roi_buffer_km(4))
    params = {k: vis[k] for k in ("bands", "min", "max") if k in vis}
    if "gamma" in vis:
        params["gamma"] = vis["gamma"]
    return {"tiles_url": tiles_de(img, params), "etiqueta": etiqueta,
            "nombre": vis["nombre"], "descripcion": vis["descripcion"]}


# --------------------------------------------------------------------------
# Landsat 8/9 (Collection 2, Level 2 - reflectancia de superficie)
# --------------------------------------------------------------------------
def _landsat_sr(img: ee.Image) -> ee.Image:
    """Aplica factores de escala C2L2 y máscara de nubes (QA_PIXEL)."""
    optico = img.select("SR_B.").multiply(0.0000275).add(-0.2)
    qa = img.select("QA_PIXEL")
    # bits 3 = nube, 4 = sombra de nube
    mascara = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
    return (
        img.addBands(optico, None, True)
        .updateMask(mascara)
        .copyProperties(img, ["system:time_start", "CLOUD_COVER", "SPACECRAFT_ID"])
    )


def _landsat_coleccion(fecha_ini: str, fecha_fin: str, max_nubes: float) -> ee.ImageCollection:
    l8 = ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
    l9 = ee.ImageCollection("LANDSAT/LC09/C02/T1_L2")
    return (
        l8.merge(l9)
        .filterBounds(roi())
        .filterDate(fecha_ini, fecha_fin)
        .filter(ee.Filter.lte("CLOUD_COVER", max_nubes))
        .map(_landsat_sr)
    )


def escenas_landsat(fecha_ini: str, fecha_fin: str, max_nubes: float = 70) -> list[dict]:
    col = _landsat_coleccion(fecha_ini, fecha_fin, max_nubes)
    feats = col.map(
        lambda im: ee.Feature(
            None,
            {
                "fecha": ee.Date(im.get("system:time_start")).format("YYYY-MM-dd"),
                "nubes": im.get("CLOUD_COVER"),
                "satelite": im.get("SPACECRAFT_ID"),
            },
        )
    )
    datos = ee.FeatureCollection(feats).getInfo()["features"]
    escenas = [
        {
            "fecha": f["properties"]["fecha"],
            "nubes": round(float(f["properties"]["nubes"] or 0), 1),
            "satelite": str(f["properties"].get("satelite") or "LANDSAT"),
        }
        for f in datos
    ]
    # dedupe por fecha, quedarnos con la de menor nubosidad
    mejores: dict[str, dict] = {}
    for e in escenas:
        if e["fecha"] not in mejores or e["nubes"] < mejores[e["fecha"]]["nubes"]:
            mejores[e["fecha"]] = e
    return sorted(mejores.values(), key=lambda x: x["fecha"], reverse=True)


def tiles_landsat(vis_key: str, fecha: str | None, fecha_ini: str, fecha_fin: str,
                  max_nubes: float = 70) -> dict:
    vis = VIS_LANDSAT[vis_key]
    if fecha:
        f0 = ee.Date(fecha)
        col = _landsat_coleccion(
            fecha, f0.advance(1, "day").format("YYYY-MM-dd").getInfo(), 100
        )
        img = col.mosaic()
        etiqueta = fecha
    else:
        img = _landsat_coleccion(fecha_ini, fecha_fin, max_nubes).median()
        etiqueta = f"Compuesto {fecha_ini} a {fecha_fin}"
    img = img.clip(roi_buffer_km(4))
    params = {"bands": vis["bands"], "min": vis["min"], "max": vis["max"]}
    if "gamma" in vis:
        params["gamma"] = vis["gamma"]
    return {"tiles_url": tiles_de(img, params), "etiqueta": etiqueta,
            "nombre": vis["nombre"], "descripcion": vis["descripcion"]}




def _landsat_toa(fecha_ini: str, fecha_fin: str, max_nubes: float) -> ee.ImageCollection:
    """Colección TOA (única con la banda pancromática B8 de 15 m)."""
    l8 = ee.ImageCollection("LANDSAT/LC08/C02/T1_TOA")
    l9 = ee.ImageCollection("LANDSAT/LC09/C02/T1_TOA")
    return (
        l8.merge(l9)
        .filterBounds(roi())
        .filter(ee.Filter.lte("CLOUD_COVER", max_nubes))
        .filterDate(fecha_ini, fecha_fin)
    )


def tiles_landsat_pan(fecha: str | None, fecha_ini: str, fecha_fin: str,
                      max_nubes: float = 70) -> dict:
    """Color real fusionado con la banda pancromática B8 (15 m).

    Fusión HSV clásica: se convierte RGB->HSV y se reemplaza el canal de
    valor (brillo) por la pancromática, recuperando el detalle espacial.
    Requiere el producto TOA (el SR no incluye B8).
    """
    if fecha:
        f0 = ee.Date(fecha)
        col = _landsat_toa(fecha, f0.advance(1, "day").format("YYYY-MM-dd").getInfo(), 100)
        img = col.mosaic()
        etiqueta = f"{fecha} · pancromática 15 m"
    else:
        img = _landsat_toa(fecha_ini, fecha_fin, max_nubes).median()
        etiqueta = f"Compuesto {fecha_ini} a {fecha_fin} · pancromática 15 m"

    rgb = img.select(["B4", "B3", "B2"])
    pan = img.select("B8")
    hsv = rgb.rgbToHsv()
    sharp = ee.Image.cat([
        hsv.select("hue"), hsv.select("saturation"), pan
    ]).hsvToRgb().clip(roi_buffer_km(4))

    vis = {"min": 0.0, "max": 0.30, "gamma": 1.4}
    return {
        "tiles_url": tiles_de(sharp, vis),
        "etiqueta": etiqueta,
        "nombre": "Color real pancromático (15 m)",
        "descripcion": ("Fusión HSV del color real con la banda pancromática "
                        "B8: duplica el detalle espacial (de 30 a 15 m). Usa "
                        "reflectancia TOA, por lo que el tono puede diferir "
                        "levemente del producto SR."),
    }


# --------------------------------------------------------------------------
# Sentinel-1 (radar SAR)
# --------------------------------------------------------------------------
def _s1_coleccion(fecha_ini: str, fecha_fin: str, pol: str) -> ee.ImageCollection:
    return (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(roi())
        .filterDate(fecha_ini, fecha_fin)
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", pol))
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .select(pol)
    )


def escenas_s1(fecha_ini: str, fecha_fin: str, pol: str = "VV") -> list[dict]:
    col = _s1_coleccion(fecha_ini, fecha_fin, pol)
    feats = col.map(
        lambda im: ee.Feature(
            None,
            {
                "fecha": ee.Date(im.get("system:time_start")).format("YYYY-MM-dd"),
                "orbita": im.get("orbitProperties_pass"),
            },
        )
    )
    datos = ee.FeatureCollection(feats).getInfo()["features"]
    vistos = {}
    for f in datos:
        p = f["properties"]
        vistos[p["fecha"]] = str(p.get("orbita") or "")
    return sorted(
        ({"fecha": k, "orbita": v} for k, v in vistos.items()),
        key=lambda x: x["fecha"],
        reverse=True,
    )


def tiles_s1(pol: str, fecha: str | None, fecha_ini: str, fecha_fin: str) -> dict:
    """Escena SAR individual o compuesto mediano del rango (dB)."""
    if fecha:
        f0 = ee.Date(fecha)
        col = _s1_coleccion(fecha, f0.advance(1, "day").format("YYYY-MM-dd").getInfo(), pol)
        img = col.mosaic()
        etiqueta = f"{fecha} ({pol})"
    else:
        col = _s1_coleccion(fecha_ini, fecha_fin, pol)
        img = col.median()
        etiqueta = f"Compuesto {pol} {fecha_ini} a {fecha_fin}"
    img = img.clip(roi_buffer_km(4))
    vis = {"min": -22, "max": 0}
    return {
        "tiles_url": tiles_de(img, vis),
        "etiqueta": etiqueta,
        "nombre": f"Sentinel-1 {pol}",
        "descripcion": "Radar de apertura sintética: penetra nubes y opera día y noche. "
                       "Cambios bruscos de retrodispersión entre fechas pueden indicar "
                       "remoción de suelo o vegetación (movimientos en masa).",
    }

# --------------------------------------------------------------------------
# GOES-Este (geoestacionario, imagen cada 10 min, latencia ~15-30 min en GEE)
# --------------------------------------------------------------------------
# Fallback automático: GOES-19 relevó a GOES-16 como GOES-Este en 2025, pero
# el catálogo de GEE puede tener uno u otro según la época consultada.
_GOES_CANDIDATOS = [
    ("NOAA/GOES/19/MCMIPF", "GOES-19 (GOES-Este)"),
    ("NOAA/GOES/16/MCMIPF", "GOES-16 (GOES-Este)"),
    ("NOAA/GOES/18/MCMIPF", "GOES-18 (GOES-Oeste)"),
]


def _cmi(img: ee.Image, banda: str) -> ee.Image:
    """Aplica escala y offset de una banda CMI (metadatos por imagen)."""
    return (
        img.select(banda)
        .multiply(img.getNumber(banda + "_scale"))
        .add(img.getNumber(banda + "_offset"))
    )


def _goes_ultima() -> tuple[ee.Image, str, str]:
    """Última imagen full-disk disponible (busca en las últimas 12 h UTC)."""
    import time as _time

    ahora = ee.Date(int(_time.time() * 1000))
    for cid, nombre in _GOES_CANDIDATOS:
        try:
            col = ee.ImageCollection(cid).filterDate(
                ahora.advance(-12, "hour"), ahora.advance(1, "hour")
            )
            if col.size().getInfo() > 0:
                img = ee.Image(col.sort("system:time_start", False).first())
                fecha = (
                    ee.Date(img.get("system:time_start"))
                    .format("YYYY-MM-dd HH:mm")
                    .getInfo()
                )
                return img, nombre, fecha + " UTC"
        except Exception:
            continue
    raise RuntimeError(
        "Sin imágenes GOES recientes en el catálogo de GEE (últimas 12 h)."
    )


def goes_escena(producto: str, buffer_km: float = 250.0) -> dict:
    """Tiles de la última imagen GOES-Este sobre la región.

    producto: 'geocolor' (color aproximado diurno), 'visible' (C02, 0.5 km)
              o 'ir' (C13, nubes día y noche).
    """
    img, satelite, fecha = _goes_ultima()
    # OJO: no se hace clip. Las imágenes GOES están en proyección
    # geoestacionaria y recortarlas con un polígono geodésico produce
    # "Can't transform (0,0)". Los tiles solo se calculan donde se mira.

    if producto == "ir":
        # C13 (10.3 um): temperatura de brillo. Nubes altas/frias -> blanco.
        capa = _cmi(img, "CMI_C13")
        vis = {"min": 195, "max": 300, "palette": ["ffffff", "e0e0e0", "808080", "202020"]}
        nombre = "Infrarrojo C13 · nubes (dia y noche)"
        desc = ("Temperatura de brillo 10.3 um: blanco = topes de nube fríos y "
                "altos (convección profunda, tormentas); oscuro = cielo "
                "despejado. Funciona de día y de noche.")
    elif producto == "visible":
        capa = _cmi(img, "CMI_C02")
        vis = {"min": 0.0, "max": 0.75, "gamma": 1.4}
        nombre = "Visible C02 (0.64 um)"
        desc = ("Banda visible de mayor resolución (~0.5-1 km). Solo útil con "
                "luz solar; de noche aparece negra.")
    else:  # geocolor aproximado
        r = _cmi(img, "CMI_C02")
        b = _cmi(img, "CMI_C01")
        g_veg = _cmi(img, "CMI_C03")
        g = r.multiply(0.45).add(g_veg.multiply(0.10)).add(b.multiply(0.45))
        capa = ee.Image.cat([r, g, b]).rename(["R", "G", "B"])
        vis = {"min": 0.0, "max": 0.8, "gamma": 1.3}
        nombre = "GeoColor aproximado (C02-C03-C01)"
        desc = ("Composición en color con verde sintético (estándar CIMSS). "
                "Solo diurna; de noche use el infrarrojo C13.")

    return {
        "tiles_url": tiles_de(capa, vis),
        "nombre": nombre,
        "etiqueta": fecha,
        "satelite": satelite,
        "descripcion": desc + f" Fuente: {satelite}, imagen cada 10 minutos.",
    }
