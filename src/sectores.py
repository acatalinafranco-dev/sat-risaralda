"""Reporte semanal de sectores (celdas de 300 m) con condiciones que favorecen
movimientos en masa.

Cada semana se califica cada sector del departamento con:
  - condiciones del terreno (fijas): susceptibilidad del modelo propio,
    pendiente media, fracción del sector con pendiente > 50 % (escarpado, IGAC), relieve local, edad geológica
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

V_TERRENO = ["susc", "pend", "f_pend50", "relieve", "geo_edad", "dist_falla"]
# Pendiente de 50 % (26,57°): límite inferior de la clase «escarpado» del IGAC.
PEND_IGAC_GRADOS = 26.565
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
def f_pend_igac() -> np.ndarray:
    """Fracción de cada sector con pendiente > 50 % (clases escarpado y muy
    escarpado del IGAC), con pendiente de NASADEM a 30 m. Se calcula una vez en
    Earth Engine con la misma grilla del modelo; si falla, se usa la fracción
    > 25° guardada en la grilla, que es casi equivalente (r = 0,96)."""
    g = grilla()
    if "f_pend50" in g:
        return g["f_pend50"]
    import ee

    s = ee.Terrain.slope(ee.Image("NASA/NASADEM_HGT/001").select("elevation"))
    img = (s.gt(PEND_IGAC_GRADOS).rename("f").toFloat()
           .reduceResolution(ee.Reducer.mean(), maxPixels=256))
    w2, h2 = ANCHO // 2, ALTO // 2
    partes = [(0, 0, w2, h2), (w2, 0, ANCHO - w2, h2),
              (0, h2, w2, ALTO - h2), (w2, h2, ANCHO - w2, ALTO - h2)]

    def _parte(p):
        j0, i0, w, h = p
        x0, y1 = X0 + RES * j0, Y0 - RES * i0
        return ee.data.computePixels({
            "expression": img, "fileFormat": "NUMPY_NDARRAY",
            "grid": {"dimensions": {"width": w, "height": h},
                     "affineTransform": {"scaleX": RES, "shearX": 0, "translateX": x0,
                                         "shearY": 0, "scaleY": -RES, "translateY": y1},
                     "crsCode": "EPSG:3116"}})

    with ThreadPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(_parte, partes))
    out = np.full((ALTO, ANCHO), np.nan, np.float32)
    for (j0, i0, w, h), a in zip(partes, res):
        out[i0:i0 + h, j0:j0 + w] = a["f"]
    return out


def _terreno(v: str) -> np.ndarray:
    if v != "f_pend50":
        return grilla()[v]
    try:
        return f_pend_igac()
    except Exception:  # noqa: BLE001
        return grilla()["f_pend25"]


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
def _capas_cambio(t, region) -> dict:
    """Capas de cambio a resolución nativa para la fecha de corte «t» (ee.Date).

    Vegetación (Sentinel-2, 10-20 m), dos comparaciones:
      - reciente: últimos 12 días frente a los 30 días anteriores;
      - mensual: últimos 30 días frente a los 90 días anteriores.
      Un píxel tiene cambio si en alguna de las dos cae el NDVI más de 0,15, sube
      el índice de suelo desnudo más de 0,05, antes había vegetación densa
      (NDVI > 0,5) y está en ladera (pendiente >= 10°).
    Radar (Sentinel-1, VH, 10 m): solo se comparan imágenes de la misma órbita.
      La mediana de los últimos 12 días se compara con las de los 30, 60 y 90
      días anteriores; hay cambio si la diferencia supera 2 dB en las tres
      comparaciones y con el mismo signo (cambio persistente, no ruido).
    """
    import ee

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

    def _comparacion(d_ahora, d_antes):
        antes = s2.filterDate(t.advance(-(d_ahora + d_antes), "day"),
                              t.advance(-d_ahora, "day")).median()
        ahora = s2.filterDate(t.advance(-d_ahora, "day"), t).median()
        dn = ahora.select("ndvi").subtract(antes.select("ndvi"))
        db = ahora.select("bsi").subtract(antes.select("bsi"))
        cam = (dn.lt(-0.15).And(db.gt(0.05)).And(antes.select("ndvi").gt(0.5))
               .And(ladera).unmask(0, False))
        return dn, cam

    dn12, cam12 = _comparacion(12, 30)
    dn30, cam30 = _comparacion(30, 90)
    cam_opt = cam12.Or(cam30)
    # caída de NDVI más fuerte de las dos comparaciones (para ubicar el punto)
    dn = ee.ImageCollection([dn12.rename("d"), dn30.rename("d")]).min()
    valido = dn30.mask().gt(0).unmask(0, False)

    s1 = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(region)
          .filter(ee.Filter.eq("instrumentMode", "IW"))
          .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
          .filterDate(t.advance(-102, "day"), t)
          .select("VH"))
    orbitas = (s1.filterDate(t.advance(-12, "day"), t)
               .aggregate_array("relativeOrbitNumber_start").distinct())

    def _por_orbita(o):
        so = s1.filter(ee.Filter.eq("relativeOrbitNumber_start", o))
        ahora = so.filterDate(t.advance(-12, "day"), t).median()
        d = [ahora.subtract(so.filterDate(t.advance(-(12 + k), "day"),
                                          t.advance(-12, "day")).median())
             for k in (30, 60, 90)]
        fuerte = d[0].abs().gt(2).And(d[1].abs().gt(2)).And(d[2].abs().gt(2))
        mismo = d[0].gt(0).eq(d[1].gt(0)).And(d[1].gt(0).eq(d[2].gt(0)))
        cam = fuerte.And(mismo).unmask(0, False)
        mag = d[0].abs().min(d[1].abs()).min(d[2].abs()).unmask(0, False)
        return cam.rename("cam").addBands(mag.rename("mag")).toFloat()

    rad = ee.ImageCollection(orbitas.map(_por_orbita))
    rad = ee.Image(ee.Algorithms.If(rad.size().gt(0),
                                    rad.qualityMosaic("mag"),
                                    ee.Image.constant([0, 0]).rename(["cam", "mag"]).toFloat()))
    cam_rad = rad.select("cam").gt(0).And(ladera).unmask(0, False)
    return {"slope": slope, "dn": dn, "dvh": rad.select("mag"), "cam_opt": cam_opt,
            "cam_rad": cam_rad, "valido": valido}


def _imagen_dinamica(fecha: str, region):
    import ee

    t = ee.Date(fecha)
    c = _capas_cambio(t, region)
    cam_opt, cam_rad, valido = c["cam_opt"], c["cam_rad"], c["valido"]

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
    X = np.column_stack([_terreno(v)[dentro] for v in V_TERRENO] +
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


try:  # caché compartida por las páginas de la app (6 horas)
    import streamlit as _st

    calificar_semana = _st.cache_data(ttl=6 * 3600, show_spinner=False)(calificar)
except Exception:  # noqa: BLE001
    calificar_semana = calificar


CLASES_IGAC = [(3, "Ligeramente plano"), (7, "Ligeramente inclinado"),
               (12, "Moderadamente inclinado"), (25, "Fuertemente inclinado"),
               (50, "Moderadamente escarpado"), (75, "Escarpado"), (1e9, "Muy escarpado")]


def clase_pendiente_igac(pct: float) -> str:
    """Clase de pendiente del IGAC (pendiente en porcentaje)."""
    for lim, nom in CLASES_IGAC:
        if pct <= lim:
            return nom
    return CLASES_IGAC[-1][1]


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
        "fila": ii, "col": jj,
        "codigo": [cods[g["mun"][i, j] - 1] for i, j in zip(ii, jj)],
        "lat": g["lat"][ii, jj].round(4), "lon": g["lon"][ii, jj].round(4),
        "prob": prob[ii, jj],
        "susceptibilidad": [_clase_susc(float(g["susc"][i, j])) for i, j in zip(ii, jj)],
        "pendiente_pct": (100 * np.tan(np.radians(g["pend"][ii, jj]))).round(0),
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
    df["pendiente_igac"] = df["pendiente_pct"].map(clase_pendiente_igac)
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
        "n_total": n_total,
        "n_prioritarios": int((df["nivel"] == NIVELES[0]).sum()) if len(df) else 0,
        "pct_area": round(100 * len(df) / max(n_total, 1), 1),
        "n_con_cambio": int(df["evidencia_cambio"].sum()) if len(df) else 0,
        "n_con_exposicion": int((df["exposicion"] != "").sum()) if len(df) else 0,
    }


# --------------------------------------------------------------------------
# Punto de verificación dentro de cada sector
# --------------------------------------------------------------------------
CRITERIO_PUNTO = {2: "Pérdida de vegetación y suelo expuesto (Sentinel-2)",
                  1: "Cambio de retrodispersión en radar (Sentinel-1)",
                  0: "Mayor pendiente del sector"}


def _puntos_bloque(fecha: str, celdas: list[tuple[int, int]]) -> list[dict]:
    import ee

    ii = [c[0] for c in celdas]
    jj = [c[1] for c in celdas]
    xa, xb = X0 + RES * min(jj), X0 + RES * (max(jj) + 1)
    ya, yb = Y0 - RES * (max(ii) + 1), Y0 - RES * min(ii)
    region = ee.Geometry.Rectangle([xa, ya, xb, yb], "EPSG:3116", False)
    c = _capas_cambio(ee.Date(fecha), region)
    # Candidato por cambio: grupos de píxeles (no píxeles aislados) con pérdida de
    # vegetación y suelo expuesto (prioridad, mayor caída de NDVI) o con cambio en radar
    # tras suavizar el moteado (mayor |ΔVH|). Candidato por terreno: píxel de mayor pendiente.
    optc = c["cam_opt"].focalMean(15, "circle", "meters").gte(0.5)
    radc = c["cam_rad"].focalMean(15, "circle", "meters").gte(0.5)
    punt = (ee.Image(0).where(radc, ee.Image(1000).add(c["dvh"]))
            .where(optc, ee.Image(2000).add(c["dn"].unmask(0, False).multiply(-100)))
            .toFloat())
    pend = c["slope"].toFloat()
    ll = ee.Image.pixelLonLat()
    img = ee.Image.cat([punt, ll, pend, pend, ll, pend])
    red_ = (ee.Reducer.max(4).setOutputs(["c", "clon", "clat", "cpend"])
            .combine(ee.Reducer.max(4).setOutputs(["s", "slon", "slat", "spend"]), None, False))
    fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Rectangle([X0 + RES * j, Y0 - RES * (i + 1),
                                          X0 + RES * (j + 1), Y0 - RES * i],
                                         "EPSG:3116", False), {"i": i, "j": j})
        for i, j in celdas])
    red = img.reduceRegions(collection=fc, reducer=red_, scale=10, crs="EPSG:3116",
                            tileScale=4)
    out = []
    for f in red.getInfo()["features"]:
        q = f["properties"]
        if q.get("s") is None:
            continue
        p = q.get("c") or 0
        out.append({"fila": int(q["i"]), "col": int(q["j"]),
                    "c_tipo": 2 if p >= 2000 else 1 if p >= 1000 else 0,
                    "c_lon": round(q["clon"], 5), "c_lat": round(q["clat"], 5),
                    "c_pend": round(q["cpend"], 0),
                    "s_lon": round(q["slon"], 5), "s_lat": round(q["slat"], 5),
                    "s_pend": round(q["spend"], 0)})
    return out


def puntos_verificacion(fecha: str, celdas: tuple[tuple[int, int], ...]) -> pd.DataFrame:
    """Coordenadas del punto que conviene verificar dentro de cada sector de 300 m."""
    celdas = sorted(celdas)
    lotes = [celdas[k:k + 250] for k in range(0, len(celdas), 250)]
    with ThreadPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(lambda l: _puntos_bloque(fecha, l), lotes))
    filas = [r for lote in res for r in lote]
    return pd.DataFrame(filas, columns=["fila", "col", "c_tipo", "c_lon", "c_lat", "c_pend",
                                        "s_lon", "s_lat", "s_pend"])


try:
    puntos_semana = _st.cache_data(ttl=6 * 3600, show_spinner=False)(puntos_verificacion)
except Exception:  # noqa: BLE001
    puntos_semana = puntos_verificacion


def agregar_puntos(df: pd.DataFrame, fecha: str, max_n: int = 1500) -> pd.DataFrame:
    """Añade a la tabla de sectores el punto de verificación de los «max_n» primeros.
    Si el cálculo falla, se usa el centro del sector."""
    if df is None or df.empty:
        return df
    cab = df.head(max_n)
    try:
        pv = puntos_semana(fecha, tuple(zip(cab["fila"].tolist(), cab["col"].tolist())))
        out = df.merge(pv, on=["fila", "col"], how="left")
        # El punto de cambio se usa solo si el sector tiene evidencia de cambio esa semana
        usa_c = out["evidencia_cambio"].astype(bool) & (out["c_tipo"].fillna(0) > 0)
        out["pv_lat"] = np.where(usa_c, out["c_lat"], out["s_lat"])
        out["pv_lon"] = np.where(usa_c, out["c_lon"], out["s_lon"])
        out["pv_pend"] = np.where(usa_c, out["c_pend"], out["s_pend"])
        out["pv_criterio"] = [CRITERIO_PUNTO[int(t)] if u else
                              (CRITERIO_PUNTO[0] if np.isfinite(la) else None)
                              for u, t, la in zip(usa_c, out["c_tipo"].fillna(0), out["s_lat"])]
        out = out.drop(columns=["c_tipo", "c_lon", "c_lat", "c_pend", "s_lon", "s_lat",
                                "s_pend"])
    except Exception:  # noqa: BLE001
        out = df.assign(pv_lon=np.nan, pv_lat=np.nan, pv_pend=np.nan, pv_criterio=None)
    falta = out["pv_lat"].isna()
    out.loc[falta, "pv_lat"] = out.loc[falta, "lat"]
    out.loc[falta, "pv_lon"] = out.loc[falta, "lon"]
    out.loc[falta, "pv_criterio"] = "Centro del sector (punto no calculado)"
    return out


def capa_cambio_url(fecha: str, codigo: str) -> str:
    """URL de teselas con los píxeles de cambio dentro del municipio (o del
    departamento): rojo, pérdida de vegetación (Sentinel-2); azul, cambio
    persistente en radar (Sentinel-1). Solo grupos de píxeles, no píxeles sueltos."""
    import ee
    from src.monitoreo import _geom

    region = _geom(codigo)
    c = _capas_cambio(ee.Date(fecha), region.bounds())
    optc = c["cam_opt"].focalMean(15, "circle", "meters").gte(0.5)
    radc = c["cam_rad"].focalMean(15, "circle", "meters").gte(0.5)
    img = radc.multiply(1).where(optc, 2).selfMask().clip(region)
    return img.getMapId({"min": 1, "max": 2, "palette": ["2f6fdf", "ff1f1f"]})["tile_fetcher"].url_format


try:
    capa_cambio_semana = _st.cache_data(ttl=6 * 3600, show_spinner=False)(capa_cambio_url)
except Exception:  # noqa: BLE001
    capa_cambio_semana = capa_cambio_url


# --------------------------------------------------------------------------
# Sitios conocidos con cambio satelital en la semana
# --------------------------------------------------------------------------
RADIO_SITIO_M = 100      # radio alrededor de cada sitio conocido
UMBRAL_SITIO = 0.25      # fracción mínima del círculo con cambio (una cuarta parte)
MAX_SITIOS = 20          # máximo de sitios destacados por municipio


def _cambio_sitios_bloque(fecha: str, filas: list[tuple[int, float, float]]) -> list[dict]:
    import ee

    lons = [f[2] for f in filas]
    lats = [f[1] for f in filas]
    region = ee.Geometry.Rectangle([min(lons) - 0.01, min(lats) - 0.01,
                                    max(lons) + 0.01, max(lats) + 0.01])
    c = _capas_cambio(ee.Date(fecha), region)
    optc = c["cam_opt"].focalMean(15, "circle", "meters").gte(0.5)
    radc = c["cam_rad"].focalMean(15, "circle", "meters").gte(0.5)
    img = ee.Image.cat([optc.Or(radc).rename("total"), optc.rename("opt"),
                        radc.rename("rad")]).toFloat()
    fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([lon, lat]).buffer(RADIO_SITIO_M), {"pid": pid})
        for pid, lat, lon in filas])
    red = img.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=10,
                            tileScale=4)
    return [{"pid": int(f["properties"]["pid"]),
             "f_cambio": f["properties"].get("total") or 0.0,
             "f_opt": f["properties"].get("opt") or 0.0,
             "f_rad": f["properties"].get("rad") or 0.0}
            for f in red.getInfo()["features"]]


def cambio_sitios(fecha: str) -> pd.DataFrame:
    """Fracción del círculo de 100 m alrededor de cada sitio conocido con pérdida de
    vegetación (Sentinel-2) o cambio persistente en radar (Sentinel-1)."""
    from src import susceptibilidad as sus

    pts = sus.puntos()
    filas = list(zip(pts["pid"].astype(int), pts["lat"].astype(float), pts["lon"].astype(float)))
    filas.sort(key=lambda f: (round(f[1], 1), f[2]))
    lotes = [filas[k:k + 120] for k in range(0, len(filas), 120)]
    with ThreadPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(lambda l: _cambio_sitios_bloque(fecha, l), lotes))
    return pd.DataFrame([r for lote in res for r in lote],
                        columns=["pid", "f_cambio", "f_opt", "f_rad"])


try:
    cambio_sitios_semana = _st.cache_data(ttl=6 * 3600, show_spinner=False)(cambio_sitios)
except Exception:  # noqa: BLE001
    cambio_sitios_semana = cambio_sitios


def sitios_semana(fecha: str, codigo: str | None = None, max_n: int = MAX_SITIOS) -> pd.DataFrame:
    """Sitios conocidos destacados en la semana: solo los que tienen cambio satelital
    en al menos el 25 % del círculo de 100 m. Máximo «max_n» por municipio, ordenados
    por la magnitud del cambio y, en empate, por el índice de atención."""
    from src import susceptibilidad as sus

    pts = sus.puntos(codigo)
    if pts.empty:
        return pts
    cam = cambio_sitios_semana(fecha)
    df = pts.merge(cam, on="pid", how="left").fillna({"f_cambio": 0, "f_opt": 0, "f_rad": 0})
    df = df[df["f_cambio"] >= UMBRAL_SITIO]
    df = df.sort_values(["f_cambio", "indice"], ascending=False)
    df = df.groupby("codigo", group_keys=False).head(max_n)
    df["cambio_detectado"] = np.select(
        [(df["f_opt"] > 0) & (df["f_rad"] > 0), df["f_opt"] > 0],
        ["Vegetación y radar", "Pérdida de vegetación"], "Radar")
    return df.reset_index(drop=True)
