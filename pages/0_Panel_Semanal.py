"""Página: panel «Qué cambió esta semana» con lo más reciente de cada fuente."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import gee_imagenes as gi
from src import gee_sar as gs
from src.comparativo_cache import comparativo_compartido
from src.gee_session import es_departamento, nombre_activo
from src.ui import VERDE_CARDER, conectar_gee, encabezado, pie_institucional

st.set_page_config(page_title="Panel semanal · SAT Risaralda", layout="wide",
                   page_icon="🗓️", initial_sidebar_state="expanded")

ASF = "https://api.daac.asf.alaska.edu/services/search/param"

encabezado(
    "🗓️ Qué cambió esta semana · {mun}",
    "Lo más reciente de cada fuente en una sola pantalla: lluvia de los "
    "últimos 7 días, últimas imágenes de Sentinel-1 y Sentinel-2 y escenas "
    "nuevas de NISAR.",
)

with st.expander("Cómo leer este panel", expanded=False):
    st.markdown(
        """
- **Lluvia 7 días:** acumulado satelital IMERG por municipio. IMERG tiene
  píxeles de unos 11 km, de modo que en municipios pequeños refleja la lluvia
  regional.
- **Última pasada Sentinel-1 y última imagen Sentinel-2:** fecha del dato más
  reciente disponible sobre la zona. Sentinel-1 pasa cada 12 días; Sentinel-2,
  cada 5, pero con frecuencia queda cubierta de nubes.
- **NISAR:** escenas de banda L publicadas en los últimos 14 días por el
  Alaska Satellite Facility. Que existan escenas no implica que cubran todo el
  departamento.
- El panel **no emite alertas**: resume la disponibilidad y los valores
  recientes de los datos. Las alertas oficiales corresponden al IDEAM, al SGC y
  a los CMGRD/CDGRD.
"""
    )

if not conectar_gee():
    st.stop()

hoy = dt.date.today()
ini = (hoy - dt.timedelta(days=14)).isoformat()
fin = (hoy + dt.timedelta(days=1)).isoformat()


@st.cache_data(ttl=3600, show_spinner=False)
def _ultimas(unidad: str, dia: str):
    s1 = gi.escenas_s1(ini, fin, "VV")
    s2 = gi.escenas_s2(ini, fin, 60)
    return s1, s2


@st.cache_data(ttl=3600, show_spinner=False)
def _nisar(dia: str):
    r = requests.get(
        ASF,
        params={"platform": "NISAR",
                "intersectsWith": "POLYGON((-76.3 4.6,-75.4 4.6,-75.4 5.5,-76.3 5.5,-76.3 4.6))",
                "start": f"{ini}T00:00:00Z", "end": f"{hoy.isoformat()}T23:59:59Z",
                "maxResults": 2000, "output": "json"},
        headers={"User-Agent": "sat-risaralda-carder"}, timeout=60)
    r.raise_for_status()
    datos = r.json()
    if datos and isinstance(datos[0], list):
        datos = datos[0]
    return [{"inicio": (g.get("startTime") or "")[:10],
             "producto": g.get("processingLevel") or ""} for g in datos]


# --- Lluvia por municipio ----------------------------------------------------
res = {"filas": [], "errores": []}
with st.spinner("Calculando la lluvia de los 14 municipios "
                "(la primera carga del día puede tardar unos minutos)..."):
    try:
        res = comparativo_compartido(hoy.isoformat())
    except Exception as exc:  # noqa: BLE001
        res = {"filas": [], "errores": [str(exc)]}

s1 = s2 = None
err_sat = None
try:
    s1, s2 = _ultimas(nombre_activo(), hoy.isoformat())
except Exception as exc:  # noqa: BLE001
    err_sat = str(exc)

nis = None
err_nis = None
try:
    nis = _nisar(hoy.isoformat())
except Exception as exc:  # noqa: BLE001
    err_nis = str(exc)

dfl = pd.DataFrame(res["filas"]) if res["filas"] else pd.DataFrame()

# --- Tarjetas ----------------------------------------------------------------
k1, k2, k3, k4 = st.columns(4)
if not dfl.empty and dfl["lluvia_7d"].notna().any():
    i = dfl["lluvia_7d"].idxmax()
    k1.metric("Mayor lluvia en 7 días", f"{dfl.loc[i, 'lluvia_7d']:.0f} mm",
              dfl.loc[i, "nombre"], delta_color="off",
              help="Mayor acumulado IMERG de los últimos 7 días entre los 14 municipios.")
else:
    k1.metric("Mayor lluvia en 7 días", "s/d")
if s1:
    u = max(s1, key=lambda e: e["fecha"])
    k2.metric("Última pasada Sentinel-1", u["fecha"],
              {"ASCENDING": "ascendente", "DESCENDING": "descendente"}.get(
                  u["orbita"].upper(), u["orbita"].lower()),
              delta_color="off", help="Pasada de radar más reciente sobre la zona.")
else:
    k2.metric("Última pasada Sentinel-1", "s/d")
if s2:
    u2 = max(s2, key=lambda e: e["fecha"])
    k3.metric("Última imagen Sentinel-2", u2["fecha"], f"{u2['nubes']:.0f} % nubes",
              delta_color="off", help="Escena óptica más reciente y su nubosidad.")
else:
    k3.metric("Última imagen Sentinel-2", "s/d")
if nis is not None:
    k4.metric("Escenas NISAR (14 días)", len(nis),
              (f"última: {max(e['inicio'] for e in nis)}" if nis else None),
              delta_color="off",
              help="Escenas de banda L que intersectan el departamento.")
else:
    k4.metric("Escenas NISAR (14 días)", "s/d")

for e in res["errores"]:
    st.warning(f"No fue posible calcular una parte de la lluvia. {e}")
if err_sat:
    st.warning(f"No fue posible consultar el catálogo Sentinel: {err_sat}")
if err_nis:
    st.warning(f"No fue posible consultar NISAR: {err_nis}")

# --- Lluvia 7 días -------------------------------------------------------------
st.markdown("#### Lluvia de los últimos 7 días por municipio")
if not dfl.empty:
    orden = dfl.sort_values("lluvia_7d", na_position="first")
    fig = go.Figure(go.Bar(x=orden["lluvia_7d"], y=orden["nombre"],
                           orientation="h", marker_color=VERDE_CARDER))
    fig.update_layout(height=440, xaxis_title="Lluvia acumulada 7 días (mm)",
                      margin=dict(l=0, r=10, t=10, b=0), plot_bgcolor="white")
    st.plotly_chart(fig, use_container_width=True)
    tabla = dfl.rename(columns={
        "nombre": "Municipio", "lluvia_7d": "Lluvia 7 d (mm)",
        "lluvia_30d": "Lluvia 30 d (mm)",
        "pct_normal_30d": "Lluvia 30 d (% de la normal)"})[
        ["Municipio", "Lluvia 7 d (mm)", "Lluvia 30 d (mm)",
         "Lluvia 30 d (% de la normal)"]].sort_values("Lluvia 7 d (mm)",
                                                      ascending=False)
    st.dataframe(tabla.round(0), hide_index=True, use_container_width=True)
else:
    st.info("No hay datos de lluvia disponibles en este momento.")

# --- Novedades por fuente ----------------------------------------------------
st.markdown("#### Novedades por fuente (últimos 14 días)")
filas = []
if s1 is not None:
    filas.append({"Fuente": "Sentinel-1 (radar)", "Escenas": len(s1),
                  "Último dato": max((e["fecha"] for e in s1), default="—")})
if s2 is not None:
    filas.append({"Fuente": "Sentinel-2 (óptico, hasta 60 % de nubes)",
                  "Escenas": len(s2),
                  "Último dato": max((e["fecha"] for e in s2), default="—")})
if nis is not None:
    filas.append({"Fuente": "NISAR (banda L)", "Escenas": len(nis),
                  "Último dato": max((e["inicio"] for e in nis), default="—")})
if filas:
    st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
st.caption("El número de escenas puede incluir varias por día y por trayectoria.")

# --- Cambio en radar (bajo demanda) ----------------------------------------
st.markdown("#### Cambio reciente en radar por municipio")
st.caption("Cálculo bajo demanda: compara los últimos 24 días de Sentinel-1 con "
           "los 90 días previos y mide la superficie con cambio fuerte sobre "
           "laderas. Es el mismo cálculo de la sección *Radar SAR* de Imágenes satelitales.")


@st.cache_data(ttl=21600, show_spinner=False)
def _radar(dia: str):
    return gs.ranking_municipal(24, 90, 3.0, 15.0)


if es_departamento():
    if st.button("Calcular cambio en radar de los 14 municipios"):
        try:
            with st.spinner("Procesando imágenes de radar (puede tardar un minuto)..."):
                rk = _radar(hoy.isoformat())
            st.session_state["panel_radar"] = rk
        except Exception as exc:  # noqa: BLE001
            st.error(f"No fue posible calcular el radar: {exc}")
    rk = st.session_state.get("panel_radar")
    if rk:
        d = pd.DataFrame(rk).sort_values("pct", ascending=False)
        fig = go.Figure(go.Bar(x=d["pct"].iloc[::-1], y=d["nombre"].iloc[::-1],
                               orientation="h", marker_color="#e66101"))
        fig.update_layout(height=440, xaxis_title="% del área municipal con cambio fuerte en ladera",
                          margin=dict(l=0, r=10, t=10, b=0), plot_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Seleccione «Todo Risaralda» en la barra lateral para comparar los "
            "municipios en radar.")

st.caption(
    "Fuentes: NASA GPM IMERG, UCSB CHIRPS, Copernicus Sentinel-1 y Sentinel-2 "
    "(ESA), NASA/ISRO NISAR (ASF DAAC), procesados en Google Earth Engine. "
    "Herramienta de apoyo al conocimiento del riesgo; no sustituye las "
    "alertas oficiales."
)
pie_institucional()
