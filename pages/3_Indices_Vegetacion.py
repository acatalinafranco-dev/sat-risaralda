"""Página: vegetación · estado actual y pérdida de vegetación en un solo mapa.

El mapa combina el NDVI del período reciente (estado actual) con la pérdida de
vegetación frente a un período de referencia (capa magenta). La serie mensual
de NDVI se calcula solo si el usuario la pide, porque es la consulta más lenta.
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
from src.ui import (cache_mun, agregar_contorno, ajustar_al_municipio, conectar_gee,
                    encabezado, leyenda_continua, mapa_base, pie_institucional)

st.set_page_config(page_title="Vegetación · Monitoreo satelital Risaralda", layout="wide",
                   page_icon="🌿", initial_sidebar_state="expanded")

encabezado(
    "🌿 Vegetación · {mun}",
    "Estado actual de la vegetación y zonas donde **se perdió vegetación** en ladera "
    "(imágenes Sentinel-2 sin nubes).",
)

if not conectar_gee():
    st.stop()


@cache_mun(ttl=3600)
def _mapa(a0, a1, r0, r1, umbral):
    d = gx.mapa_vegetacion(a0, a1, r0, r1, umbral)
    d.pop("_perdida", None)
    return d


@cache_mun(ttl=3600)
def _area(a0, a1, r0, r1, umbral):
    return gx.area_perdida_ha(a0, a1, r0, r1, umbral)


@cache_mun(ttl=86400)
def _serie_ndvi(meses, fecha_consulta):
    return gx.serie_ndvi_mensual(meses)


hoy = dt.date.today()
DIAS = {"Últimos 30 días": 30, "Últimos 60 días": 60, "Últimos 90 días": 90}
REF = {"Hace 3 a 6 meses": (180, 90), "Hace 6 a 12 meses": (365, 180),
       "Hace 12 a 24 meses": (730, 365)}

with st.expander("¿Cómo funciona este mapa?", expanded=False):
    st.markdown("""
**Fondo de colores (estado actual).** Es el índice de vegetación NDVI del período
reciente: verde intenso = vegetación vigorosa; amarillo = vegetación escasa; pardo =
suelo desnudo, roca o construcciones.

**Capa magenta (pérdida de vegetación).** Marca los lugares donde el NDVI bajó más que el
umbral elegido entre el período de referencia y el reciente. Para evitar falsas alarmas,
solo se marca un lugar si cumple todo lo siguiente:

1. Antes tenía vegetación (NDVI mayor a 0,4).
2. Está en ladera (pendiente de 10° o más), para descartar cosechas en zonas planas.
3. Forma un grupo de píxeles (al menos la mitad de los píxeles en un radio de 15 m),
   para descartar píxeles sueltos.
4. Las imágenes usadas no tienen nubes ni sombras (máscara Cloud Score+).

**Filtros que puede cambiar**
- **Período reciente:** imágenes de los últimos 30, 60 o 90 días. Con más días hay menos
  vacíos por nubes, pero el cambio puede ser más antiguo.
- **Período de referencia:** con qué momento se compara.
- **Umbral de pérdida:** qué tanto debe bajar el NDVI. Más negativo = solo cambios fuertes.

**Cómo interpretarlo.** La pérdida de vegetación puede deberse a un movimiento en masa,
pero también a cosechas, quemas, talas u obras. Verifique con la imagen en color real
(«Imágenes y radar») o en campo.
""")

c1, c2, c3 = st.columns(3)
act = c1.selectbox("Período reciente", list(DIAS), index=1)
ref = c2.selectbox("Período de referencia", list(REF), index=1)
umbral = c3.slider("Umbral de pérdida (caída del NDVI)", -0.5, -0.1, -0.2, 0.05,
                   help="Más negativo = solo pérdidas más fuertes")
a0 = (hoy - dt.timedelta(days=DIAS[act])).isoformat()
a1 = (hoy + dt.timedelta(days=1)).isoformat()
r0 = (hoy - dt.timedelta(days=REF[ref][0])).isoformat()
r1 = (hoy - dt.timedelta(days=REF[ref][1])).isoformat()

with st.spinner("Preparando el mapa de vegetación..."):
    try:
        res = _mapa(a0, a1, r0, r1, umbral)
    except Exception as exc:  # noqa: BLE001
        res = None
        st.warning(f"No fue posible generar el mapa: {exc}")

if res:
    m = mapa_base(zoom=12, basemap="Esri.WorldImagery")
    m.add_tile_layer(res["tiles_ndvi"], name="Estado actual (NDVI)",
                     attribution="Google Earth Engine / Copernicus", opacity=0.75)
    m.add_tile_layer(res["tiles_perdida"], name="Pérdida de vegetación",
                     attribution="Google Earth Engine / Copernicus")
    agregar_contorno(m)
    ajustar_al_municipio(m)
    m.to_streamlit(height=560)
    leyenda_continua("Estado actual de la vegetación (NDVI): suelo desnudo → vegetación vigorosa",
                     res["vis_ndvi"])
    st.markdown(
        "<span style='display:inline-block;width:14px;height:14px;background:#ff00ff;"
        "margin:0 6px -2px 0'></span><b>Magenta: pérdida de vegetación</b> entre "
        f"{ref.lower()} y los {act.lower()} (caída del NDVI mayor a {abs(umbral):.2f})",
        unsafe_allow_html=True)
    if st.button("Calcular el área con pérdida de vegetación"):
        with st.spinner("Calculando el área..."):
            try:
                st.metric("Área con pérdida de vegetación", f"{_area(a0, a1, r0, r1, umbral):,.1f} ha")
            except Exception as exc:  # noqa: BLE001
                st.warning(f"No fue posible calcular el área: {exc}")

with st.expander("Serie mensual del NDVI (opcional, tarda en cargar)"):
    meses = st.select_slider("Meses hacia atrás", options=[12, 18, 24, 36], value=24)
    if st.button("Calcular la serie"):
        with st.spinner("Calculando la serie mensual de NDVI..."):
            try:
                serie = _serie_ndvi(meses, hoy.isoformat())
            except Exception as exc:  # noqa: BLE001
                serie = None
                st.warning(f"Serie no disponible: {exc}")
        if serie:
            dfn = pd.DataFrame(serie)
            fig = go.Figure(go.Scatter(x=dfn["fecha"], y=dfn["ndvi"], mode="lines+markers",
                                       line=dict(color="#2e8b3d", width=2), marker=dict(size=5)))
            fig.update_layout(height=340, xaxis_title="Mes", yaxis_title="NDVI medio",
                              margin=dict(t=20, b=40, l=50, r=20))
            st.plotly_chart(fig, use_container_width=True)
            st.caption("Caídas sostenidas fuera de la variación normal del año ameritan "
                       "revisión. Meses muy nublados pueden quedar sin dato.")

pie_institucional()
