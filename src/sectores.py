"""Reporte semanal de sectores (celdas de 300 m) con condiciones que favorecen
movimientos en masa.

Cada semana se califica cada sector del departamento con:
  - condiciones del terreno (fijas): susceptibilidad del modelo propio,
    pendiente media, fracción de ladera > 25°, relieve local, edad geológica
    y distancia a fallas (SGC 1:100.000);
  - lluvia de los últimos 30 días (IMERG): acumulado, máximo diario, máximo
    en 7 días y anomalía frente al promedio 2001-2020 del mes.
Con esas variables un bosque aleatorio estima la probabilidad relativa de un
movimiento en masa en el sector. Además se calcula, como evidencia
complementaria, la fracción del sector con pérdida de vegetación y aparición
de suelo expuesto (Sentinel-2) y con cambio fuerte en radar (Sentinel-1).

Validación (sectores-mes 2024-2026, 262 eventos fechados, bloques espaciales
de 5 km): ver data/modelo_sectores.json.

Archivos:
  data/sectores_grilla.npz        variables fijas, exposición y municipio por celda
  data/sectores_entrenamiento.csv.gz  filas de entrenamiento (sin coordenadas)
  data/modelo_sectores.json       metadatos, umbrales y validación
"""
from __future__ import annotations

import datetime as dt
import json
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

DIR_DATA = Path(__file__).resolve().parent.parent / "data"
RUTA_GRILLA = DIR_DATA / "sectores_grilla.npz"
RUTA_ENT = DIR_DATA / "sectores_entrenamiento.csv.gz"
RUTA_META = DIR_DATA / "modelo_sectores.json"

# Grilla EPSG:3116 (MAGNA-SIRGAS / Colombia Bogotá), celdas de 300 m
X0, Y0, RES, ANCHO, ALTO = 762600.0, 1109100.0, 300.0, 318, 344

V_TERRENO = ["susc", "pend", "f_pend25", "relieve", "geo_edad", "dist_falla"]
V_LLUVIA = ["im_mes", "im_max1d", "im_max7d", "im_anom"]
VARIABLES = V_TERRENO + V_LLUVIA

TEXTO = ("De acuerdo con las variables analizadas, se evidencia un cambio en este "
         "sector. Se sugiere realizar seguimiento y verificar cambios en el terreno.")
NIVELES = ["Seguimiento prioritario", "Seguimiento"]
COLOR_NIVEL = {"Seguimiento prioritario": "#c0392b", "Seguimiento": "#e67e22"}


def disponible() -> bool:
    return RUTA_GRILLA.exists() and RUTA_ENT.exists() and RUTA_META.exists()


@lru_cache(maxsize=1)
def meta() -> dict:
    return json.loads(RUTA_META.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def grilla() -> dict:
    z = np.load(RUTA_GRILLA, allow_pickle=False)
    return {k: z[k] for k in z.files}


@lru_cache(maxsize=1)
def modelo():
    from sklearn.ensemble import RandomForestClassifier

    d = pd.read_csv(RUTA_ENT)
    m = meta()
    rf = RandomForestClassifier(n_estimators=m["n_arboles"], min_samples_leaf=m["min_hoja"],
                                max_samples=0.6, n_jobs=-1, random_state=7)
    rf.fit(d[VARIABLES].fillna(-99).values, d["clase"].values)
    return rf


def semana_de(fecha: dt.date) -> tuple[dt.date, dt.date]:
    """Lunes y domingo de la semana ISO que contiene «fecha»."""
    ini = fecha - dt.timedelta(days=fecha.weekday())
    return ini, ini + dt.timedelta(days=6)


# --------------------------------------------------------------------------
# Variables dinámicas desde Earth Engine
# --------------------------------------------------------------------------
def _imagen_dinamica(fecha: str, region):
    import ee

    t = ee.Date(fecha)
    slope = ee.Terrain.slope(ee.Image("NASA/NASADEM_HGT/001").select("elevation"))
    ladera = slope.gte(10)
    csp = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")

    def _limpia(i):
        scl = i.select("SCL")
        m = (i.select("cs_cdf").gte(0.5).And(scl.neq(3)).And(scl.neq(8))
             .And(scl.neq(9)).And(scl.neq(10)))
        r = i.select(["B2", "B4", "B8", "B11"]).divide(1e4)
        ndvi = r.normalizedDifference(["B8", "B4"]).rename("ndvi")
        bsi = r.expression("((b('B11')+b('B4'))-(b('B8')+b('B2')))/"
                           "((b('B11')+b('B4'))+(b('B8')+b('B2')))").rename("bsi")
        return (ndvi.addBands(bsi).toFloat().updateMask(m)
                .copyProperties(i, ["system:time_start"]))

    s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(region)
          .filterDate(t.advance(-120, "day"), t)
          .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 90))
          .linkCollection(csp, ["cs_cdf"]).map(_limpia))
    antes = s2.filterDate(t.advance(-120, "day"), t.advance(-30, "day")).median()
    ahora = s2.filterDate(t.advance(-30, "day"), t).median()
    dn = ahora.select("ndvi").subtract(antes.select("ndvi"))
    db = ahora.select("bsi").subtract(antes.select("bsi"))
    cam_opt = (dn.lt(-0.15).And(db.gt(0.05)).And(antes.select("ndvi").gt(0.5))
               .And(ladera).unmask(0, False))
    valido = dn.mask().gt(0).unmask(0, False)

    s1 = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(region)
          .filter(ee.Filter.eq("instrumentMode", "IW"))
          .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
          .select("VH"))
    dvh = (s1.filterDate(t.advance(-12, "day"), t).median()
           .subtract(s1.filterDate(t.advance(-102, "day"), t.advance(-12, "day")).median()))
    cam_rad = dvh.abs().gt(2).And(ladera).unmask(0, False)

    p60 = ee.Projection("EPSG:3116").atScale(60)
    p300 = ee.Projection("EPSG:3116").atScale(300)
    cambio = (ee.Image.cat([cam_opt.rename("f_cambio_opt"), valido.rename("f_valido_opt"),
                            cam_rad.rename("f_cambio_rad")])
              .reproject(p60).reduceResolution(ee.Reducer.mean(), maxPixels=64)
              .reproject(p300))

    im = ee.ImageCollection("NASA/GPM_L3/IMERG_V07").select("precipitation")
    t0 = t.advance(-30, "day")
    dias = ee.ImageCollection.fromImages(ee.List.sequence(0, 29).map(
        lambda k: im.filterDate(t0.advance(k, "day"), t0.advance(ee.Number(k).add(1), "day"))
        .sum().multiply(0.5)))
    lista = dias.toList(30)
    s7 = ee.ImageCollection.fromImages(ee.List.sequence(0, 23).map(
        lambda k: ee.ImageCollection.fromImages(lista.slice(k, ee.Number(k).add(7))).sum())).max()
    mes = t.get("month")
    clim = (ee.ImageCollection("NASA/GPM_L3/IMERG_MONTHLY_V07").select("precipitation")
            .filter(ee.Filter.calendarRange(mes, mes, "month"))
            .filterDate("2001-01-01", "2021-01-01").mean().multiply(24 * 30))
    ll = dias.sum()
    lluvia = ee.Image.cat([ll.rename("im_mes"), dias.max().rename("im_max1d"),
                           s7.rename("im_max7d"), ll.divide(clim.max(1)).rename("im_anom")])
    return cambio.addBands(lluvia.reproject(p300)).toFloat().clip(region)


def _bloque(fecha: str, j0: int, i0: int, w: int, h: int) -> np.ndarray:
    import ee

    x0, y1 = X0 + RES * j0, Y0 - RES * i0
    region = ee.Geometry.Rectangle([x0, y1 - RES * h, x0 + RES * w, y1], "EPSG:3116", False)
    img = _imagen_dinamica(fecha, region)
    arr = ee.data.computePixels({
        "expression": img,
        "fileFormat": "NUMPY_NDARRAY",
        "grid": {"dimensions": {"width": w, "height": h},
                 "affineTransform": {"scaleX": RES, "shearX": 0, "translateX": x0,
                                     "shearY": 0, "scaleY": -RES, "translateY": y1},
                 "crsCode": "EPSG:3116"},
    })
    return arr


def dinamicas(fecha: str) -> dict[str, np.ndarray]:
    """Variables dinámicas en la grilla completa (4 bloques en paralelo)."""
    w2, h2 = ANCHO // 2, ALTO // 2
    partes = [(0, 0, w2, h2), (w2, 0, ANCHO - w2, h2),
              (0, h2, w2, ALTO - h2), (w2, h2, ANCHO - w2, ALTO - h2)]
    with ThreadPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(lambda p: _bloque(fecha, *p), partes))
    nombres = res[0].dtype.names
    out = {n: np.full((ALTO, ANCHO), np.nan, np.float32) for n in nombres}
    for (j0, i0, w, h), a in zip(partes, res):
        for n in nombres:
            out[n][i0:i0 + h, j0:j0 + w] = a[n]
    return out


# --------------------------------------------------------------------------
# Calificación de sectores
# --------------------------------------------------------------------------
def calificar(fecha: str) -> dict:
    g, m = grilla(), meta()
    din = dinamicas(fecha)
    dentro = g["mun"] > 0
    X = np.column_stack([g[v][dentro] for v in V_TERRENO] +
                        [din[v][dentro] for v in V_LLUVIA])
    X = np.where(np.isfinite(X), X, -99)
    p = modelo().predict_proba(X)[:, 1]
    prob = np.full((ALTO, ANCHO), np.nan, np.float32)
    prob[dentro] = p
    # Evidencia de cambio: sector dentro del 5 % con mayor fracción de cambio en el
    # departamento esa semana (y por encima de un mínimo absoluto).
    u_opt = max(0.05, float(np.nanpercentile(din["f_cambio_opt"][dentro], 95)))
    u_rad = max(0.15, float(np.nanpercentile(din["f_cambio_rad"][dentro], 95)))
    return {"fecha": fecha, "prob": prob, "din": din,
            "umbral": m["umbral_seguimiento"], "umbral_prioritario": m["umbral_prioritario"],
            "umbral_cambio_opt": u_opt, "umbral_cambio_rad": u_rad}


def _clase_susc(v: float) -> str:
    cortes = meta()["cortes_susc"]  # en % de probabilidad del modelo de susceptibilidad
    nombres = ["Muy baja", "Baja", "Media", "Alta", "Muy alta"]
    return nombres[int(np.searchsorted(cortes, v, side="right"))]


def sectores(cal: dict, codigo: str | None = None) -> pd.DataFrame:
    """Sectores que superan el umbral de seguimiento, ordenados por probabilidad."""
    g = grilla()
    prob, din = cal["prob"], cal["din"]
    sel = prob >= cal["umbral"]
    if codigo and codigo != "66":
        k = list(g["cods"]).index(codigo) + 1
        sel &= g["mun"] == k
    ii, jj = np.where(sel)
    if not len(ii):
        return pd.DataFrame()
    cods = list(g["cods"])
    df = pd.DataFrame({
        "codigo": [cods[g["mun"][i, j] - 1] for i, j in zip(ii, jj)],
        "lat": g["lat"][ii, jj].round(4), "lon": g["lon"][ii, jj].round(4),
        "prob": prob[ii, jj],
        "susceptibilidad": [_clase_susc(float(g["susc"][i, j])) for i, j in zip(ii, jj)],
        "lluvia_30d_mm": din["im_mes"][ii, jj].round(0),
        "lluvia_max7d_mm": din["im_max7d"][ii, jj].round(0),
        "anomalia_lluvia": din["im_anom"][ii, jj].round(2),
        "cambio_cobertura_pct": (100 * din["f_cambio_opt"][ii, jj]).round(1),
        "imagen_optica_valida_pct": (100 * din["f_valido_opt"][ii, jj]).round(0),
        "cambio_radar_pct": (100 * din["f_cambio_rad"][ii, jj]).round(1),
        "edificaciones": g["n_edif"][ii, jj].astype(int),
        "dist_via_m": g["dist_via"][ii, jj].round(0),
    })
    df["nivel"] = np.where(df["prob"] >= cal["umbral_prioritario"], NIVELES[0], NIVELES[1])
    df["evidencia_cambio"] = ((df["cambio_cobertura_pct"] >= 100 * cal.get("umbral_cambio_opt", 0.05))
                              | (df["cambio_radar_pct"] >= 100 * cal.get("umbral_cambio_rad", 0.15)))
    df["exposicion"] = df.apply(_texto_exposicion, axis=1)
    df["mensaje"] = TEXTO
    return df.sort_values(["prob"], ascending=False).reset_index(drop=True)


def _texto_exposicion(f) -> str:
    partes = []
    if f["edificaciones"] > 0:
        n = int(f["edificaciones"])
        partes.append(f"{n} edificaci{'ones' if n != 1 else 'ón'}")
    if f["dist_via_m"] <= 150:
        partes.append("vía a menos de 150 m")
    return ", ".join(partes)


def resumen(cal: dict, codigo: str) -> dict:
    df = sectores(cal, codigo)
    g = grilla()
    if codigo and codigo != "66":
        k = list(g["cods"]).index(codigo) + 1
        n_total = int((g["mun"] == k).sum())
    else:
        n_total = int((g["mun"] > 0).sum())
    return {
        "n_sectores": int(len(df)),
        "n_prioritarios": int((df["nivel"] == NIVELES[0]).sum()) if len(df) else 0,
        "pct_area": round(100 * len(df) / max(n_total, 1), 1),
        "n_con_cambio": int(df["evidencia_cambio"].sum()) if len(df) else 0,
        "n_con_exposicion": int((df["exposicion"] != "").sum()) if len(df) else 0,
    }
