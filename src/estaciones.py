"""Estaciones pluviométricas automáticas del IDEAM en Risaralda.

Fuente: datos abiertos del IDEAM en datos.gov.co (API Socrata, sin clave):
  - Catálogo de estaciones:      hp9r-jxuu
  - Precipitación (sensor 0240): s54a-sgyg  (datos casi en tiempo real,
    sin validar por el IDEAM)

Los datos son preliminares. Se aplica un control de calidad básico y las
estaciones dudosas se muestran, pero no se usan en el contraste.
"""
from __future__ import annotations

import datetime as dt

import requests

from .gee_session import geojson_municipios

BASE = "https://www.datos.gov.co/resource"
DS_PRECIP = "s54a-sgyg"
SENSOR_PRECIP = "0240"
MAX_MM_DIA = 200.0        # lámina diaria por encima de la cual se descarta el día
MIN_DIAS_VALIDOS = 0.8    # fracción mínima de días con dato en la ventana
MAX_DIAS_DESCARTADOS = 2  # más de esto -> estación dudosa


def _en_anillo(lon: float, lat: float, anillo: list) -> bool:
    dentro = False
    j = len(anillo) - 1
    for i in range(len(anillo)):
        xi, yi = anillo[i][0], anillo[i][1]
        xj, yj = anillo[j][0], anillo[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            dentro = not dentro
        j = i
    return dentro


def municipio_de(lon: float, lat: float) -> tuple[str, str] | None:
    """(código, nombre) del municipio de Risaralda que contiene el punto."""
    for f in geojson_municipios()["features"]:
        g = f["geometry"]
        polis = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poli in polis:
            if _en_anillo(lon, lat, poli[0]) and not any(
                    _en_anillo(lon, lat, h) for h in poli[1:]):
                return f["properties"]["codigo"], f["properties"]["nombre"]
    return None


def _consulta(params: dict) -> list[dict]:
    r = requests.get(f"{BASE}/{DS_PRECIP}.json", params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def descargar_diario(dias: int = 30) -> list[dict]:
    """Lámina diaria (mm) por estación de Risaralda, últimos `dias` días."""
    desde = (dt.date.today() - dt.timedelta(days=dias)).isoformat()
    filas = _consulta({
        "$select": ("codigoestacion,nombreestacion,latitud,longitud,"
                    "date_trunc_ymd(fechaobservacion) as dia,"
                    "sum(valorobservado) as mm,count(*) as n"),
        "$where": (f"departamento='Risaralda' and codigosensor='{SENSOR_PRECIP}' "
                   f"and fechaobservacion>='{desde}T00:00:00'"),
        "$group": "codigoestacion,nombreestacion,latitud,longitud,dia",
        "$limit": "50000",
    })
    return filas


def estaciones(dias: int = 30) -> dict:
    """Devuelve {'filas': [...], 'serie': {codigo: [(fecha, mm)]}, 'corte': fecha}.

    Cada fila: codigo, nombre, lat, lon, municipio, mm_7d, mm_30d, dias_validos,
    dias_descartados, calidad ('Aceptable' | 'Dudosa'), motivo.
    """
    datos = descargar_diario(dias)
    por_est: dict[str, dict] = {}
    for d in datos:
        e = por_est.setdefault(d["codigoestacion"], {
            "codigo": d["codigoestacion"],
            "nombre": d["nombreestacion"].split("[")[0].strip(),
            "lat": float(d["latitud"]), "lon": float(d["longitud"]),
            "dias": {},
        })
        e["dias"][d["dia"][:10]] = (float(d["mm"]), int(d["n"]))

    hoy = dt.date.today()
    filas, series = [], {}
    ultima = None
    for e in por_est.values():
        mun = municipio_de(e["lon"], e["lat"])
        if mun is None:  # fuera de Risaralda (el catálogo a veces se equivoca)
            continue
        fechas = sorted(e["dias"])
        ultima = max(ultima or fechas[-1], fechas[-1])
        validos, descartados = {}, 0
        for f, (mm, n) in e["dias"].items():
            if mm < 0 or mm > MAX_MM_DIA:
                descartados += 1
            else:
                validos[f] = mm
        total = sum(validos.values())
        ult7 = sum(v for f, v in validos.items()
                   if f > (hoy - dt.timedelta(days=8)).isoformat())
        motivo = ""
        if descartados > MAX_DIAS_DESCARTADOS:
            motivo = (f"{descartados} días con láminas diarias superiores a "
                      f"{MAX_MM_DIA:.0f} mm (lectura improbable)")
        elif len(validos) < MIN_DIAS_VALIDOS * dias:
            motivo = f"solo {len(validos)} de {dias} días con dato"
        elif total == 0:
            motivo = "0 mm en toda la ventana (posible sensor detenido)"
        filas.append({
            "codigo": e["codigo"], "nombre": e["nombre"],
            "lat": e["lat"], "lon": e["lon"],
            "cod_mun": mun[0], "municipio": mun[1],
            "mm_7d": ult7, "mm_30d": total,
            "dias_validos": len(validos), "dias_descartados": descartados,
            "calidad": "Dudosa" if motivo else "Aceptable", "motivo": motivo,
        })
        series[e["codigo"]] = sorted(validos.items())
    return {"filas": sorted(filas, key=lambda r: r["nombre"]),
            "serie": series, "corte": ultima}
