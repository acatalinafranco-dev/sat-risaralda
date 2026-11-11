"""Página: indicadores de una zona de interés dibujada sobre el mapa."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import folium
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from folium.plugins import Draw
from shapely.geometry import shape
from streamlit_folium import st_folium

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import interactivo as itv
from src import riesgo
from src.gee_session import centro_activo, geojson_municipios
from src.ui import (ESRI_IMAGERY_ATTR, ESRI_IMAGERY_URL, conectar_gee,
                    encabezado, pie_institucional)

st.set_page_config(page_title="Zona de interés · SAT Risaralda", layout="wide",
                   page_icon="✏️", initial_sidebar_state="expanded")

MAX_KM2 = 1500

encabezado(
    "✏️ Zona de interés",
    "Dibuje sobre el mapa una **vereda, una cuenca o cualquier área** y "
    "obtenga sus indicadores: lluvia, relieve, pérdida de vegetación, "
    "población estimada, amenaza del SGC y eventos del SIMMA. "
    "Use las herramientas de **polígono** o **rectángulo** del costado "
    "izquierdo del mapa.",
)

if not conectar_gee():
    st.stop()

lat, lon = centro_activo()
m = folium.Map(location=[lat, lon], zoom_start=10, tiles=None, control_scale=True)
folium.TileLayer(tiles=ESRI_IMAGERY_URL, attr=ESRI_IMAGERY_ATTR,
                 name="Esri WorldImagery", max_zoom=19).add_to(m)
folium.GeoJson(
    geojson_municipios(), name="División municipal",
    style_function=lambda f: {"color": "#ffff00", "weight": 1.5, "fill": False},
    tooltip=folium.GeoJsonTooltip(fields=["nombre"], aliases=["Municipio"]),
).add_to(m)
sombra = {"color": "#00e5ff", "weight": 3, "fillOpacity": 0.15}
Draw(
    export=False,
    draw_options={"polyline": False, "circle": False, "marker": False,
                  "circlemarker": False,
                  "polygon": {"allowIntersection": False, "showArea": False,
                              "shapeOptions": sombra},
                  "rectangle": {"shapeOptions": sombra}},
    edit_options={"edit": True, "remove": True},
).add_to(m)
folium.LayerControl(collapsed=True).add_to(m)

salida = st_folium(m, height=560, use_container_width=True, key="mapa_zona",
                   returned_objects=["all_drawings"])
dibujos = (salida or {}).get("all_drawings") or []
geom = None
for f in reversed(dibujos):
    g = f.get("geometry") if isinstance(f, dict) else None
    if g and g.get("type") in ("Polygon", "MultiPolygon"):
        geom = g
        break

if geom is None:
    st.info("Dibuje una zona en el mapa para calcular sus indicadores. Si "
            "dibuja varias, se usa la última.")
    pie_institucional()
    st.stop()

sg = shape(geom)
area = itv._area_km2(sg)
st.markdown(f"**Zona dibujada: {area:,.1f} km²**")
if area > MAX_KM2:
    st.warning(f"La zona supera {MAX_KM2:,} km². Dibuje un área menor para que "
               "el cálculo sea rápido y confiable.")
    pie_institucional()
    st.stop()
if area < 0.05:
    st.warning("La zona es muy pequeña (menos de 5 ha); los datos de 10 a 100 m "
               "no son representativos. Dibuje un área mayor.")
    pie_institucional()
    st.stop()

geom_json = json.dumps(geom, sort_keys=True)
if st.button("Calcular indicadores de la zona", type="primary"):
    st.session_state["zona_calculada"] = geom_json
if st.session_state.get("zona_calculada") != geom_json:
    st.caption("Pulse el botón para calcular. El primer cálculo puede tardar "
               "entre 30 segundos y un par de minutos.")
    pie_institucional()
    st.stop()

with st.spinner("Calculando con Google Earth Engine..."):
    r = itv.estadisticas_zona(geom_json, dt.date.today().isoformat())


def _n(v, fmt="{:,.0f}", vacio="s/d"):
    return vacio if v is None or v != v else fmt.format(v)


for e in r["errores"]:
    st.warning(f"No fue posible calcular una parte de los indicadores. {e}")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Población estimada", _n(r.get("poblacion")),
          help="WorldPop 2020, 100 m. Estimación modelada, no censo.")
k2.metric("Pérdida de vegetación", f"{_n(r.get('perdida_ha'))} ha",
          help="ΔNDVI < −0,20 sobre zonas con NDVI > 0,4 (Sentinel-2, últimos "
               "60 días frente a hace 6–12 meses).")
k3.metric("Lluvia 30 días", f"{_n(r.get('lluvia_30d'))} mm",
          None if r.get("pct_normal_30d") is None
          else f"{r['pct_normal_30d']:.0f} % de la referencia", delta_color="off")
k4.metric("Eventos SIMMA en la zona", len(r["eventos"]))

k5, k6, k7, k8 = st.columns(4)
k5.metric("Lluvia 7 días", f"{_n(r.get('lluvia_7d'))} mm")
k6.metric("Pendiente media", f"{_n(r.get('pendiente_media'))}°")
k7.metric("Área con pendiente > 30°", f"{_n(r.get('pct_pend_30'))} %")
k8.metric("Cota", f"{_n(r.get('elev_min'))}–{_n(r.get('elev_max'))} m")

st.markdown("#### Amenaza por movimientos en masa (SGC) dentro de la zona")
am = r.get("amenaza")
if am:
    colores = {"Muy baja": "#37a800", "Baja": "#99e600", "Media": "#ffff00",
               "Alta": "#ffa900", "Muy alta": "#ff0000", "Sin clasificar": "#b0b7bd"}
    fig = go.Figure()
    for nombre, v in am.items():
        if v > 0.05:
            fig.add_bar(y=[""], x=[v], name=nombre, orientation="h",
                        marker_color=colores[nombre],
                        text=f"{v:.0f} %" if v >= 4 else "", textposition="inside",
                        hovertemplate=f"{nombre}: %{{x:.1f}} %<extra></extra>")
    fig.update_layout(barmode="stack", height=130, margin=dict(l=0, r=0, t=0, b=0),
                      xaxis=dict(range=[0, 100], title="% del área de la zona"),
                      legend=dict(orientation="h", y=1.4))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Zonificación de amenaza relativa del SGC (1:100.000), clasificada "
               "por color sobre la imagen publicada por el servicio. «Sin "
               "clasificar» incluye áreas sin cobertura a esa escala.")
else:
    st.caption("No fue posible consultar el servicio del SGC.")

c1, c2 = st.columns(2)
with c1:
    st.markdown("#### Municipios que abarca la zona")
    if len(r["municipios"]):
        st.dataframe(r["municipios"], hide_index=True, use_container_width=True,
                     column_config={
                         "Área de la zona (km²)": st.column_config.NumberColumn(format="%.1f"),
                         "% de la zona": st.column_config.NumberColumn(format="%.0f")})
    else:
        st.caption("La zona queda fuera de los 14 municipios.")
with c2:
    st.markdown("#### Eventos del SIMMA en la zona")
    ev = r["eventos"]
    if len(ev):
        tipos = ev["tipo"].value_counts().rename_axis("Tipo").reset_index(name="Eventos")
        st.dataframe(tipos, hide_index=True, use_container_width=True)
    else:
        st.caption("No hay eventos registrados dentro de la zona.")

st.caption(
    "La exposición se describe con la población residente estimada y la "
    "composición de la amenaza dentro de la zona. Los valores son indicativos "
    "(lluvia IMERG de ~11 km; la zona pequeña refleja el campo regional) y no "
    "sustituyen las alertas oficiales del IDEAM, del SGC ni las decisiones de "
    "los CMGRD/CDGRD.")

ind = pd.DataFrame([
    ("Área (km²)", r["area_km2"], "Polígono dibujado"),
    ("Población estimada", r.get("poblacion"), "WorldPop 2020, 100 m"),
    ("Pérdida de vegetación (ha)", r.get("perdida_ha"), "Sentinel-2, ΔNDVI < −0,20"),
    ("Lluvia 7 días (mm)", r.get("lluvia_7d"), "IMERG V07"),
    ("Lluvia 30 días (mm)", r.get("lluvia_30d"), "IMERG V07"),
    ("Referencia de 30 días (mm, promedio de 20 años)", r.get("normal_30d"), "CHIRPS"),
    ("Lluvia 30 d (% de la referencia)", r.get("pct_normal_30d"), "IMERG / CHIRPS"),
    ("Pendiente media (°)", r.get("pendiente_media"), "NASADEM, 30 m"),
    ("Área con pendiente > 30° (%)", r.get("pct_pend_30"), "NASADEM, 30 m"),
    ("Cota mínima (m)", r.get("elev_min"), "NASADEM"),
    ("Cota máxima (m)", r.get("elev_max"), "NASADEM"),
    ("Eventos SIMMA en la zona", len(ev), f"SIMMA, descarga del {riesgo.fecha_corte_sgc()}"),
], columns=["Indicador", "Valor", "Fuente"])
hojas = {"Indicadores": ind}
if am:
    hojas["Amenaza SGC"] = pd.DataFrame(
        {"Categoría": list(am), "% del área de la zona": list(am.values())})
if len(r["municipios"]):
    hojas["Municipios"] = r["municipios"]
if len(ev):
    hojas["Eventos SIMMA"] = ev
d1, d2, _ = st.columns([1, 1, 2])
d1.download_button(
    "Descargar indicadores (Excel)",
    itv.excel_bytes(hojas, [
        "Zona dibujada por el usuario sobre el mapa; indicadores calculados con Google Earth Engine.",
        "Los valores son indicativos y no sustituyen las alertas oficiales."]),
    file_name=f"zona_interes_{dt.date.today().isoformat()}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
d2.download_button(
    "Descargar la zona (GeoJSON)",
    json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"area_km2": round(area, 2)},
         "geometry": geom}]}).encode("utf-8"),
    file_name=f"zona_interes_{dt.date.today().isoformat()}.geojson",
    mime="application/geo+json")
pie_institucional()
