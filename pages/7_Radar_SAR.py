"""Página: cambios del terreno con radar Sentinel-1 (SAR)."""
from __future__ import annotations

import sys
from pathlib import Path

import folium
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import gee_sar as gs
from src import riesgo
from src.gee_session import codigo_activo, es_departamento, nombre_activo
from src.ui import (VERDE_CARDER, agregar_contorno, agregar_municipios,
                    ajustar_al_municipio, cache_mun, conectar_gee, encabezado,
                    leyenda_continua, mapa_base, pie_institucional)

st.set_page_config(page_title="Radar SAR · SAT Risaralda", layout="wide",
                   page_icon="📡", initial_sidebar_state="expanded")

encabezado(
    "🛰️ Radar SAR · cambios del terreno · {mun}",
    "Comparación de imágenes de radar **Sentinel-1** (ESA) para señalar "
    "laderas donde la superficie cambió con fuerza. El radar **atraviesa las "
    "nubes**, por lo que sirve en plena temporada de lluvias.",
)

with st.expander("Cómo leer esta página", expanded=False):
    st.markdown(
        """
- Se compara la **retrodispersión del radar (dB)** de una ventana reciente
  con la de una ventana anterior de referencia, con la misma órbita para que
  la geometría sea idéntica.
- **Azul:** el terreno devuelve menos señal que antes (por ejemplo, suelo
  liso o pérdida de cobertura). **Naranja:** devuelve más señal (superficie
  más rugosa o más húmeda).
- **Magenta:** cambio fuerte (más de ±3 dB por defecto) sobre **laderas** de
  más de 15° de pendiente. Son zonas para **verificar en campo o con otra
  imagen**, no eventos confirmados.
- El radar también cambia por **humedad del suelo, cultivos, agua y
  sombras**. Un cambio no es por sí solo un movimiento en masa: úselo para
  priorizar, junto con el nivel de atención y los eventos del SIMMA.
- Sentinel-1 pasa cada 12 días sobre la zona; la ventana reciente debe
  cubrir al menos un paso.
"""
    )

if not conectar_gee():
    st.stop()

c1, c2, c3, c4 = st.columns(4)
with c1:
    dias_rec = st.selectbox("Ventana reciente", [12, 24, 36], index=1,
                            format_func=lambda d: f"últimos {d} días")
with c2:
    dias_ref = st.selectbox("Referencia anterior", [60, 90, 180], index=1,
                            format_func=lambda d: f"{d} días previos")
with c3:
    umbral = st.slider("Umbral de cambio (dB)", 2.0, 6.0, 3.0, 0.5)
with c4:
    pend_min = st.slider("Pendiente mínima (°)", 5, 30, 15, 5)
ver_ev = st.checkbox("Mostrar eventos del SIMMA", value=False)


@cache_mun(ttl=21600)
def _mapa(dr, df_, u, p):
    return gs.mapa_cambio(dr, df_, u, p)


@st.cache_data(ttl=21600, show_spinner=False)
def _ranking(dr, df_, u, p):
    return gs.ranking_municipal(dr, df_, u, p)


try:
    with st.spinner("Procesando imágenes de radar (puede tardar un minuto)..."):
        r = _mapa(dias_rec, dias_ref, float(umbral), float(pend_min))
except Exception as exc:  # noqa: BLE001
    st.error(f"No fue posible procesar el radar: {exc}")
    st.stop()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Área con cambio fuerte en ladera", f"{r['ha_total']:,.0f} ha".replace(",", "."))
k2.metric("Porcentaje del área", f"{r['pct']:.1f} %")
k3.metric("Imágenes recientes / referencia",
          f"{r['n_reciente']} / {r['n_referencia']}")
k4.metric("Órbita", r["orbita"],
          f"{r['fecha_ini']} a {r['fecha_fin']}", delta_color="off")

m = mapa_base(zoom=11, basemap="Esri.WorldImagery")
m.add_tile_layer(r["tiles_cambio"], name="Cambio de retrodispersión (dB)",
                 shown=True, attribution="Copernicus Sentinel-1 / Google Earth Engine")
m.add_tile_layer(r["tiles_marca"], name="Cambio fuerte en ladera",
                 shown=True, attribution="Copernicus Sentinel-1 / Google Earth Engine")
if es_departamento():
    agregar_municipios(m)
else:
    agregar_contorno(m)
if ver_ev:
    pts = riesgo.puntos_simma(codigo_activo())
    g = folium.FeatureGroup(name=f"Eventos SIMMA ({len(pts)})")
    for p in pts.itertuples():
        folium.CircleMarker(
            [p.lat, p.lon], radius=3, color="#ffffff", weight=0.8, fill=True,
            fill_color=riesgo.COLOR_TIPO.get(p.tipo, "#555555"), fill_opacity=0.9,
            tooltip=f"{p.tipo} ({p.origen})").add_to(g)
    g.add_to(m)
folium.LayerControl(collapsed=True).add_to(m)
ajustar_al_municipio(m)
m.to_streamlit(height=560)
leyenda_continua("Cambio de retrodispersión (dB)", gs.VIS_CAMBIO, "dB")
st.caption(
    f"Órbita {r['orbita'].lower()} (trayectorias {', '.join(map(str, r['orbitas_relativas']))}). "
    f"Referencia: {r['ventana_referencia']}. Sentinel-1 GRD, banda C, "
    "polarización VV, suavizado de 30 m. Magenta: cambio superior al umbral "
    f"sobre pendientes de {pend_min}° o más ({r['ha_dismin']:,.0f} ha con "
    f"disminución y {r['ha_aumento']:,.0f} ha con aumento)."
)

if es_departamento():
    st.divider()
    st.markdown("### Cambio fuerte en ladera por municipio")
    try:
        with st.spinner("Calculando los 14 municipios..."):
            rk = _ranking(dias_rec, dias_ref, float(umbral), float(pend_min))
        df = pd.DataFrame(rk)
        orden = df.sort_values("pct")
        fig = go.Figure(go.Bar(x=orden["pct"], y=orden["nombre"], orientation="h",
                               marker_color=VERDE_CARDER))
        fig.update_layout(height=440, xaxis_title="% del área municipal",
                          margin=dict(l=0, r=10, t=10, b=0), plot_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True)
        tabla = df.rename(columns={
            "nombre": "Municipio", "area_km2": "Área (km²)",
            "ha_dismin": "Disminución (ha)", "ha_aumento": "Aumento (ha)",
            "ha_total": "Total (ha)", "pct": "% del área"}).drop(columns="codigo")
        st.dataframe(tabla.round(1), hide_index=True, use_container_width=True)
        st.download_button("Descargar tabla (CSV)",
                           tabla.round(1).to_csv(index=False).encode("utf-8-sig"),
                           file_name="cambio_radar_municipios.csv", mime="text/csv")
    except Exception as exc:  # noqa: BLE001
        st.warning(f"No fue posible calcular el ranking municipal: {exc}")

st.caption(
    "Fuente: Copernicus Sentinel-1 (ESA), procesado en Google Earth Engine; "
    "pendiente: NASADEM. Herramienta de apoyo al conocimiento del riesgo: no "
    "sustituye la verificación en campo ni las alertas oficiales."
)
pie_institucional()
