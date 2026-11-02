"""Relieve para la página «Amenaza y eventos»: pendiente, sombreado y
elevación a partir de NASADEM (30 m) en Google Earth Engine."""
from __future__ import annotations

import ee

from .gee_session import roi, tiles_de

CAPAS = {
    "Pendiente (°)": {
        "vis": {"min": 0, "max": 60,
                "palette": ["1a9850", "91cf60", "d9ef8b", "fee08b",
                            "fc8d59", "d73027"]},
        "unidades": "°",
    },
    "Relieve sombreado": {
        "vis": {"min": 0, "max": 255, "palette": ["000000", "ffffff"]},
        "unidades": "",
    },
    "Elevación (m s. n. m.)": {
        "vis": {"min": 0, "max": 4800,
                "palette": ["2b8a3e", "a9d18e", "ffe699", "c9a27a",
                            "8c6d62", "ffffff"]},
        "unidades": "m",
    },
}


def mapa_terreno(nombre: str) -> dict:
    """URL de tiles del DEM recortado al municipio activo."""
    dem = ee.Image("NASA/NASADEM_HGT/001").select("elevation")
    g = roi()
    if nombre.startswith("Pendiente"):
        img = ee.Terrain.slope(dem)
    elif nombre.startswith("Relieve"):
        img = ee.Terrain.hillshade(dem)
    else:
        img = dem
    vis = CAPAS[nombre]["vis"]
    return {"tiles_url": tiles_de(img.clip(g), vis), "vis": vis}


def estadisticas_pendiente() -> dict:
    """Pendiente media y % del área con pendiente > 30° en el municipio."""
    dem = ee.Image("NASA/NASADEM_HGT/001").select("elevation")
    sl = ee.Terrain.slope(dem)
    g = roi()
    media = sl.reduceRegion(ee.Reducer.mean(), g, 90, maxPixels=1e9,
                            tileScale=4).get("slope")
    fuerte = sl.gt(30).reduceRegion(ee.Reducer.mean(), g, 90, maxPixels=1e9,
                                    tileScale=4).get("slope")
    res = ee.Dictionary({"media": media, "fuerte": fuerte}).getInfo()
    return {"media": res.get("media"),
            "pct_mayor_30": (res.get("fuerte") or 0) * 100}
