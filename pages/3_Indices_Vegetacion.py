"""Página: Índices de vegetación · monitoreo de movimientos en masa.

  1. Mapa del índice actual (NDVI / NDMI / BSI) sobre el municipio.
  2. Detección de cambios ΔNDVI (referencia vs. período reciente): la pérdida
     abrupta de vegetación en laderas es indicador de cicatrices de
     deslizamiento, remoción de cobertura o intervención antrópica.
  3. Serie temporal mensual del NDVI medio municipal.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import gee_indices as gx
from src.ui import (agregar_contorno, ajustar_al_municipio, conectar_gee,
                    encabezado, leyenda_continua, mapa_base, pie_institucional)

st.set_page_config(page_title="Vegetación · SAT Pajarito", layout="wide",
                   page_icon="🌿", initial_sidebar_state="expanded")

encabezado(
    "🌿 Índices de vegetación · Pajarito, Boyacá",
    "Monitoreo de la cobertura vegetal con Sentinel-2 (máscara de nubes "
    "Cloud Score+) para la **detección temprana de movimientos en masa**: "
    "pérdidas abruptas de NDVI en ladera son la firma óptica típica de un "
    "deslizamiento.",
)

if not conectar_gee():
    st.stop()


# Las excepciones no se cachean: un error transitorio no queda pegado.
@st.cache_data(ttl=3600, show_spinner=False)
def _mapa_indice(indice, f0, f1):
    return gx.mapa_indice(indice, f0, f1)


@st.cache_data(ttl=3600, show_spinner=False)
def _cambio(r0, r1, a0, a1, umbral):
    return gx.mapa_cambio_ndvi(r0, r1, a0, a1, umbral)


@st.cache_data(ttl=86400, show_spinner=False)
def _serie_ndvi(meses, fecha_consulta):
    return gx.serie_ndvi_mensual(meses)


def _seguro(fn, *args):
    try:
        return fn(*args)
    except Exception as exc:
        return {"__error__": str(exc)}


hoy = dt.date.today()

# --------------------------------------------------------------------------
# 1) Índice actual
# --------------------------------------------------------------------------
st.markdown("### Estado actual de la vegetación")

c1, c2 = st.columns(2)
with c1:
    indice = st.selectbox(
        "Índice", ["NDVI", "NDMI", "BSI"],
        format_func=lambda k: {
            "NDVI": "NDVI · vigor de la vegetación",
            "NDMI": "NDMI · humedad de la vegetación",
            "BSI": "BSI · suelo desnudo",
        }[k],
    )
with c2:
    ventana = st.selectbox("Período del compuesto",
                           ["Últimos 30 días", "Últimos 60 días", "Últimos 90 días"],
                           index=1,
                           help="Compuesto mediano libre de nubes del período")
DIAS_V = {"Últimos 30 días": 30, "Últimos 60 días": 60, "Últimos 90 días": 90}
f0 = (hoy - dt.timedelta(days=DIAS_V[ventana])).isoformat()
f1 = (hoy + dt.timedelta(days=1)).isoformat()

with st.spinner(f"Generando compuesto {indice} ({ventana.lower()})..."):
    res = _seguro(_mapa_indice, indice, f0, f1)

if res.get("__error__"):
    st.warning(f"No fue posible generar el índice: {res['__error__']}")
else:
    m = mapa_base(zoom=12, basemap="Esri.WorldImagery")
    m.add_tile_layer(res["tiles_url"], name=f"{indice} · {ventana}",
                     attribution="Google Earth Engine / Copernicus")
    agregar_contorno(m)
    ajustar_al_municipio(m)
    m.to_streamlit(height=520)

    k1, k2, k3 = st.columns(3)
    k1.metric(f"{indice} medio (municipio)", f"{res['media']:.3f}")
    k2.metric("Mínimo", f"{res['min']:.3f}")
    k3.metric("Máximo", f"{res['max']:.3f}")
    leyenda_continua(f"{indice} · {ventana.lower()}", res["vis"])
    st.caption(res["descripcion"])

# --------------------------------------------------------------------------
# 2) Detección de cambios ΔNDVI
# --------------------------------------------------------------------------
st.divider()
st.markdown("### Detección de cambios (ΔNDVI) · posibles movimientos en masa")
st.caption(
    "Compara un período de **referencia** con uno **reciente**. Las zonas en "
    "magenta perdieron vegetación densa de forma severa: revíselas contra la "
    "imagen en color real de la página *Imágenes satelitales* antes de emitir "
    "cualquier alerta."
)

cc1, cc2, cc3 = st.columns(3)
with cc1:
    ref = st.selectbox("Período de referencia",
                       ["Hace 6–12 meses", "Hace 3–6 meses", "Año anterior (12–24 meses)"])
with cc2:
    act = st.selectbox("Período reciente", ["Últimos 60 días", "Últimos 90 días"])
with cc3:
    umbral = st.slider("Umbral de pérdida (ΔNDVI)", -0.5, -0.1, -0.2, 0.05,
                       help="Más negativo = solo cambios más severos")

RANGOS_REF = {
    "Hace 6–12 meses": (365, 180),
    "Hace 3–6 meses": (180, 90),
    "Año anterior (12–24 meses)": (730, 365),
}
d_ini, d_fin = RANGOS_REF[ref]
r0 = (hoy - dt.timedelta(days=d_ini)).isoformat()
r1 = (hoy - dt.timedelta(days=d_fin)).isoformat()
a0 = (hoy - dt.timedelta(days=DIAS_V.get(act, 60))).isoformat()
a1 = (hoy + dt.timedelta(days=1)).isoformat()

with st.spinner("Calculando cambio de NDVI (dos compuestos S2)..."):
    cambio = _seguro(_cambio, r0, r1, a0, a1, umbral)

if cambio.get("__error__"):
    st.warning(f"No fue posible calcular el cambio: {cambio['__error__']}")
else:
    m2 = mapa_base(zoom=12, basemap="Esri.WorldImagery")
    m2.add_tile_layer(cambio["tiles_delta"], name="ΔNDVI (continuo)",
                      attribution="GEE", opacity=0.65)
    m2.add_tile_layer(cambio["tiles_perdida"],
                      name=f"Pérdida severa (ΔNDVI < {umbral})",
                      attribution="GEE")
    agregar_contorno(m2)
    ajustar_al_municipio(m2)
    m2.to_streamlit(height=520)

    st.metric(
        "Área con pérdida severa de vegetación (dentro del municipio)",
        f"{cambio['area_perdida_ha']:,.1f} ha",
        help=f"Píxeles con ΔNDVI < {umbral} que antes tenían NDVI > 0.4",
    )
    leyenda_continua("ΔNDVI (pérdida ← → ganancia)", cambio["vis"])
    st.caption(cambio["descripcion"])

# --------------------------------------------------------------------------
# 3) Serie temporal NDVI
# --------------------------------------------------------------------------
st.divider()
st.markdown("### Serie temporal · NDVI medio del municipio")

meses = st.select_slider("Meses hacia atrás", options=[12, 18, 24, 36], value=24)

with st.spinner("Calculando serie mensual de NDVI (puede tardar en la primera carga)..."):
    serie = _seguro(_serie_ndvi, meses, hoy.isoformat())

if isinstance(serie, dict) and serie.get("__error__"):
    st.warning(f"Serie no disponible: {serie['__error__']}")
elif not serie:
    st.info("Sin datos suficientes de NDVI en el período.")
else:
    dfn = pd.DataFrame(serie)
    fig = go.Figure(go.Scatter(
        x=dfn["fecha"], y=dfn["ndvi"], mode="lines+markers",
        line=dict(color="#2e8b3d", width=2), marker=dict(size=5),
        name="NDVI medio",
    ))
    media = dfn["ndvi"].mean()
    fig.add_hline(y=media, line_dash="dash", line_color="#888",
                  annotation_text=f"media {media:.2f}")
    fig.update_layout(height=360, xaxis_title="Mes",
                      yaxis_title="NDVI medio municipal",
                      margin=dict(t=30, b=40, l=50, r=20))
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Caídas sostenidas del NDVI municipal (fuera de la estacionalidad "
        "normal) ameritan revisión con ΔNDVI e imágenes en color real. "
        "Meses muy nubosos pueden quedar sin dato."
    )

pie_institucional()
