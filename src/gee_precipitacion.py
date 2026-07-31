"""Precipitación satelital sobre el municipio de Pajarito (Boyacá).

Fuentes (Google Earth Engine, cálculo en vivo):
  - IMERG V07 (NASA GPM)      ~11 km, media hora  -> latencia ~1-2 días
  - CHIRPS Daily (UCSB-CHG)   ~5.5 km, diario     -> latencia ~2-3 semanas
  - ERA5-Land Daily (ECMWF)   ~11 km, reanálisis  -> latencia ~5-6 días

Todos los cálculos se hacen sobre el POLÍGONO del municipio (media zonal),
no sobre un punto, reutilizando el patrón de GeoVolcanes-SCR pero adaptado
a escala municipal.
"""
from __future__ import annotations

import datetime as dt

import ee

from .gee_session import roi, roi_buffer_km, tiles_de

# Escala de reducción por fuente (resolución nativa aprox., en metros)
ESCALA = {"imerg": 11132, "chirps": 5566, "era5": 11132}
LATENCIA_DIAS = {"imerg": 2, "chirps": 21, "era5": 6}

PALETA_LLUVIA = ["ffffff", "b3e5fc", "4fc3f7", "0288d1", "7b1fa2", "d50000"]

def _interpolar(img: ee.Image, escala_m: float) -> ee.Image:
    """Remuestreo bilineal seguro para COMPUESTOS (sum/median).

    Un compuesto no tiene proyección fija: EE le asigna WGS84 a escala de
    1 grado y `resample()` sobre eso hace fallar la generación de tiles de
    forma silenciosa (mapa vacío). Fijar primero la proyección nativa de la
    fuente resuelve el problema y produce el campo interpolado esperado.
    """
    proj = ee.Projection("EPSG:4326").atScale(escala_m)
    return img.setDefaultProjection(proj).resample("bilinear")



# --------------------------------------------------------------------------
# Colecciones diarias homogéneas (banda 'precipitation' en mm/día)
# --------------------------------------------------------------------------
def _diaria_chirps(f0: ee.Date, f1: ee.Date) -> ee.ImageCollection:
    return (
        ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
        .select("precipitation")
        .filterDate(f0, f1)
    )


def _diaria_era5(f0: ee.Date, f1: ee.Date) -> ee.ImageCollection:
    col = (
        ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR")
        .select("total_precipitation_sum")
        .filterDate(f0, f1)
    )

    def _mm(img):
        return (
            img.multiply(1000.0)
            .rename("precipitation")
            .copyProperties(img, ["system:time_start"])
        )

    return col.map(_mm)


def _diaria_imerg(f0: ee.Date, f1: ee.Date) -> ee.ImageCollection:
    """Suma diaria a partir del producto de 30 minutos (mm/hr * 0.5 h)."""
    n_dias = f1.difference(f0, "day").round()
    dias = ee.List.sequence(0, n_dias.subtract(1))
    hh = ee.ImageCollection("NASA/GPM_L3/IMERG_V07").select("precipitation")

    def _dia(d):
        d0 = f0.advance(d, "day")
        d1 = d0.advance(1, "day")
        c = hh.filterDate(d0, d1)
        img = ee.Image(
            ee.Algorithms.If(
                c.size().gt(0),
                c.sum().multiply(0.5),
                ee.Image.constant(0).selfMask(),
            )
        )
        return img.rename("precipitation").set("system:time_start", d0.millis())

    return ee.ImageCollection.fromImages(dias.map(_dia))


def _coleccion_diaria(fuente: str, f0: ee.Date, f1: ee.Date) -> ee.ImageCollection:
    if fuente == "chirps":
        return _diaria_chirps(f0, f1)
    if fuente == "era5":
        return _diaria_era5(f0, f1)
    if fuente == "imerg":
        return _diaria_imerg(f0, f1)
    raise ValueError(f"Fuente desconocida: {fuente}")


def _rango(dias: int) -> tuple[ee.Date, ee.Date]:
    """Ventana calendario única [hoy-dias, mañana): igual para todas las
    fuentes. Cada curva termina donde su latencia se lo permite; los días
    sin dato se omiten (no se rellenan con 0)."""
    hoy = dt.date.today()
    fin = hoy + dt.timedelta(days=1)
    ini = hoy - dt.timedelta(days=dias)
    return ee.Date(ini.isoformat()), ee.Date(fin.isoformat())


# --------------------------------------------------------------------------
# 1) Serie diaria (media zonal sobre el municipio)
# --------------------------------------------------------------------------
def serie_diaria(fuente: str, dias: int) -> dict:
    """Serie diaria de precipitación media sobre el polígono municipal.

    Devuelve: {serie: [{fecha, mm}], acumulado_mm, media_diaria_mm,
               n_dias, latencia_dias}
    """
    f0, f1 = _rango(dias)
    col = _coleccion_diaria(fuente, f0, f1)
    geom = roi()
    escala = ESCALA[fuente]

    def _reducir(img):
        mm = img.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=escala,
            maxPixels=1e9,
            bestEffort=True,
        ).get("precipitation")
        return ee.Feature(
            None,
            {
                "fecha": ee.Date(img.get("system:time_start")).format("YYYY-MM-dd"),
                "mm": ee.Algorithms.If(ee.Algorithms.IsEqual(mm, None), -9999, mm),
            },
        )

    fc = ee.FeatureCollection(col.map(_reducir))
    datos = fc.getInfo()["features"]
    serie = sorted(
        (
            {"fecha": f["properties"]["fecha"], "mm": float(f["properties"]["mm"])}
            for f in datos
            if float(f["properties"]["mm"] if f["properties"]["mm"] is not None else -9999) > -1
        ),
        key=lambda x: x["fecha"],
    )
    total = sum(x["mm"] for x in serie)
    n = len(serie)
    return {
        "fuente": fuente,
        "serie": serie,
        "acumulado_mm": round(total, 1),
        "media_diaria_mm": round(total / n, 2) if n else 0.0,
        "n_dias": n,
        "latencia_dias": LATENCIA_DIAS[fuente],
    }


# --------------------------------------------------------------------------
# 2) Mapa de precipitación acumulada (interpolación bilineal sobre buffer)
# --------------------------------------------------------------------------
def mapa_acumulado(fuente: str, dias: int, buffer_km: float = 15.0) -> dict:
    """Acumulado (mm) en los últimos `dias`, remuestreado bilinealmente para
    mostrar un campo continuo de lluvia alrededor del municipio.

    IMERG/ERA5 tienen píxeles de ~11 km: Pajarito cubre apenas ~3 celdas, por
    eso el mapa se calcula sobre un buffer y se interpola para ver gradientes.
    """
    f0, f1 = _rango(dias)
    col = _coleccion_diaria(fuente, f0, f1)
    zona = roi_buffer_km(buffer_km)

    acum = col.sum().rename("mm")
    suave = _interpolar(acum, ESCALA[fuente]).clip(zona)

    stats = acum.reduceRegion(
        reducer=ee.Reducer.minMax().combine(ee.Reducer.mean(), sharedInputs=True),
        geometry=roi(),
        scale=ESCALA[fuente],
        maxPixels=1e9,
        bestEffort=True,
    ).getInfo()

    vmax = max(stats.get("mm_max") or 0, 10)
    vis = {"min": 0, "max": round(vmax * 1.1), "palette": PALETA_LLUVIA}
    return {
        "tiles_url": tiles_de(suave, vis),
        "vis": vis,
        "min_mm": round(stats.get("mm_min") or 0, 1),
        "media_mm": round(stats.get("mm_mean") or 0, 1),
        "max_mm": round(stats.get("mm_max") or 0, 1),
        "periodo": f"{f0.format('YYYY-MM-dd').getInfo()} a {f1.advance(-1, 'day').format('YYYY-MM-dd').getInfo()}",
    }




# --------------------------------------------------------------------------
# 2b) Grilla de mapas acumulados (8 submapas: días / semanas / meses)
# --------------------------------------------------------------------------
# Escalas fijas por tipo de período (mm) para que los 8 submapas sean
# comparables entre sí (mismo criterio que la app IMERG de GEE).
VIS_GRILLA = {
    "dias":    {"min": 0, "max": 60,  "palette": PALETA_LLUVIA},
    "semanas": {"min": 0, "max": 250, "palette": PALETA_LLUVIA},
    "meses":   {"min": 0, "max": 600, "palette": PALETA_LLUVIA},
}


def _mes_imerg_hibrido(f0: ee.Date) -> ee.Image:
    """Acumulado mensual IMERG (mm): usa el producto mensual Final Run si
    existe; si no (meses recientes, latencia 3-4 meses), lo reconstruye
    desde las imágenes de 30 minutos. Portado de la app IMERG en GEE."""
    f0 = ee.Date(f0)
    f1 = f0.advance(1, "month")
    mensual = (
        ee.ImageCollection("NASA/GPM_L3/IMERG_MONTHLY_V07")
        .select("precipitation")
        .filterDate(f0, f1)
    )
    horas = f1.difference(f0, "hour")
    return ee.Image(
        ee.Algorithms.If(
            mensual.size().gt(0),
            ee.Image(mensual.first()).multiply(horas),  # mm/hr x horas del mes
            _diaria_imerg(f0, f1).sum(),
        )
    ).rename("mm")


def _acumulado_periodo(fuente: str, f0: str, f1: str, es_mes: bool) -> ee.Image:
    if fuente == "imerg" and es_mes:
        return _mes_imerg_hibrido(ee.Date(f0))
    col = _coleccion_diaria(fuente, ee.Date(f0), ee.Date(f1))
    return col.sum().rename("mm")


def _mes_atras(anio: int, mes: int, n: int) -> tuple[int, int]:
    idx = anio * 12 + (mes - 1) - n
    return idx // 12, idx % 12 + 1


def grilla_acumulados(fuente: str, modo: str, n: int = 8,
                      buffer_km: float = 10.0) -> dict:
    """Grilla de N mapas de precipitación acumulada por subperíodo.

    modo: 'dias' | 'semanas' | 'meses'. Los períodos terminan en la última
    fecha con datos de la fuente (hoy - latencia), y para 'meses' se alinean
    a meses calendario completos.
    """
    hoy = dt.date.today()
    fin_disp = hoy - dt.timedelta(days=LATENCIA_DIAS[fuente] - 1)
    zona = roi_buffer_km(buffer_km)
    geom = roi()
    escala = ESCALA[fuente]

    periodos: list[dict] = []
    if modo == "dias":
        for i in range(n, 0, -1):
            d0 = fin_disp - dt.timedelta(days=i)
            periodos.append({
                "f0": d0.isoformat(),
                "f1": (d0 + dt.timedelta(days=1)).isoformat(),
                "etiqueta": d0.strftime("%d %b"),
                "es_mes": False,
            })
    elif modo == "semanas":
        for i in range(n, 0, -1):
            d0 = fin_disp - dt.timedelta(days=7 * i)
            d1 = d0 + dt.timedelta(days=7)
            periodos.append({
                "f0": d0.isoformat(),
                "f1": d1.isoformat(),
                "etiqueta": f"{d0.strftime('%d %b')} – {(d1 - dt.timedelta(days=1)).strftime('%d %b')}",
                "es_mes": False,
            })
    else:  # meses calendario completos, terminando en el mes anterior
        a, m = fin_disp.year, fin_disp.month
        for i in range(n, 0, -1):
            a0, m0 = _mes_atras(a, m, i)
            a1, m1 = _mes_atras(a, m, i - 1)
            periodos.append({
                "f0": f"{a0:04d}-{m0:02d}-01",
                "f1": f"{a1:04d}-{m1:02d}-01",
                "etiqueta": f"{a0:04d}-{m0:02d}",
                "es_mes": True,
            })

    vis = VIS_GRILLA[modo]
    feats = []
    for pdef in periodos:
        img = _acumulado_periodo(fuente, pdef["f0"], pdef["f1"], pdef["es_mes"])
        suave = _interpolar(img, escala).clip(zona)
        pdef["tiles_url"] = tiles_de(suave, vis)
        feats.append(
            ee.Feature(None, {
                "etiqueta": pdef["etiqueta"],
                "media": img.reduceRegion(
                    reducer=ee.Reducer.mean(), geometry=geom, scale=escala,
                    maxPixels=1e9, bestEffort=True,
                ).get("mm"),
            })
        )

    # Una sola llamada para todas las medias municipales
    medias = ee.FeatureCollection(feats).getInfo()["features"]
    por_etiqueta = {
        f["properties"]["etiqueta"]: f["properties"].get("media")
        for f in medias
    }
    for pdef in periodos:
        v = por_etiqueta.get(pdef["etiqueta"])
        pdef["media_mm"] = round(float(v), 1) if v is not None else None
        pdef.pop("es_mes", None)

    return {"periodos": periodos, "vis": vis, "modo": modo, "fuente": fuente}


# --------------------------------------------------------------------------
# 3) Climatología CHIRPS (promedio de los últimos 20 años)
# --------------------------------------------------------------------------
def climatologia_chirps(anios: int = 20) -> dict:
    """Promedio mensual multianual (mm/mes) con CHIRPS PENTAD sobre el municipio."""
    fin = dt.date.today().year - 1  # último año calendario completo
    ini = fin - anios + 1
    pentad = (
        ee.ImageCollection("UCSB-CHG/CHIRPS/PENTAD")
        .select("precipitation")
        .filterDate(f"{ini}-01-01", f"{fin + 1}-01-01")
    )
    geom = roi()
    meses = ee.List.sequence(1, 12)
    lista_anios = ee.List.sequence(ini, fin)

    def _por_anio(a):
        a = ee.Number(a)

        def _por_mes(m):
            img = pentad.filter(
                ee.Filter.And(
                    ee.Filter.calendarRange(a, a, "year"),
                    ee.Filter.calendarRange(m, m, "month"),
                )
            ).sum()
            val = img.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geom,
                scale=5566,
                maxPixels=1e9,
                bestEffort=True,
            ).get("precipitation")
            return ee.Feature(
                None,
                {
                    "anio": a,
                    "mes": m,
                    "mm": ee.Algorithms.If(ee.Algorithms.IsEqual(val, None), 0, val),
                },
            )

        return ee.FeatureCollection(meses.map(_por_mes))

    todos = ee.FeatureCollection(lista_anios.map(_por_anio)).flatten()

    def _promedio(m):
        prom = todos.filter(ee.Filter.eq("mes", m)).aggregate_mean("mm")
        return ee.Feature(None, {"mes": m, "mm": prom})

    clim = ee.FeatureCollection(meses.map(_promedio)).getInfo()["features"]
    mensual = sorted(
        (
            {"mes": int(f["properties"]["mes"]), "mm": round(float(f["properties"]["mm"] or 0), 1)}
            for f in clim
        ),
        key=lambda x: x["mes"],
    )
    return {
        "climatologia": mensual,
        "anual_mm": round(sum(x["mm"] for x in mensual), 0),
        "periodo": f"{ini}-{fin}",
    }


def mapa_media_anual_chirps(anios: int = 20, buffer_km: float = 15.0) -> dict:
    """Mapa de precipitación media anual (mm/año) CHIRPS de los últimos N años."""
    fin = dt.date.today().year - 1
    ini = fin - anios + 1
    pentad = (
        ee.ImageCollection("UCSB-CHG/CHIRPS/PENTAD")
        .select("precipitation")
        .filterDate(f"{ini}-01-01", f"{fin + 1}-01-01")
    )
    media_anual = pentad.sum().divide(anios).rename("mm")
    zona = roi_buffer_km(buffer_km)
    img = _interpolar(media_anual, 5566).clip(zona)

    stats = media_anual.reduceRegion(
        reducer=ee.Reducer.minMax().combine(ee.Reducer.mean(), sharedInputs=True),
        geometry=zona,
        scale=5566,
        maxPixels=1e9,
        bestEffort=True,
    ).getInfo()
    vmin = stats.get("mm_min") or 0
    vmax = stats.get("mm_max") or 4000
    vis = {"min": round(vmin), "max": round(vmax), "palette": PALETA_LLUVIA}
    return {
        "tiles_url": tiles_de(img, vis),
        "vis": vis,
        "media_municipio_mm": round(
            media_anual.reduceRegion(
                ee.Reducer.mean(), roi(), 5566, bestEffort=True, maxPixels=1e9
            ).getInfo().get("mm")
            or 0
        ),
        "periodo": f"{ini}-{fin}",
    }
