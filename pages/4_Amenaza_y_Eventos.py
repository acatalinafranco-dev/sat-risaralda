"""Página: Amenaza y eventos de movimientos en masa.

  1. Mapa con relieve (pendiente, sombreado o elevación), susceptibilidad por
     movimientos en masa del SGC (1:100.000) y eventos del SIMMA (inventario y
     catálogo).
  2. Amenaza del municipio (Mapa Nacional de Amenaza del SGC, 2015).
  3. Eventos registrados por tipo y por municipio, con descarga.
"""
from __future__ import annotations

import sys
from pathlib import Path

import folium
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import gee_terreno as gt
from src import riesgo
from src.gee_session import (codigo_activo, es_departamento, geojson_municipio,
                            nombre_activo)
from src.ui import (VERDE_CARDER, agregar_amenaza_sgc, agregar_contorno,
                    agregar_municipios,
                    ajustar_al_municipio, cache_mun, conectar_gee, encabezado,
                    leyenda_continua, mapa_base, pie_institucional)

st.set_page_config(page_title="Amenaza y eventos · SAT Risaralda",
                   layout="wide", page_icon="⛰️",
                   initial_sidebar_state="expanded")

encabezado(
    "⛰️ Amenaza y eventos · {mun}",
    "Relieve, susceptibilidad y amenaza por **movimientos en masa** del "
    "Servicio Geológico Colombiano (SGC) y eventos históricos del **SIMMA**. "
    "Permite ver *dónde* la lluvia y la pendiente pueden convertirse en un "
    "evento.",
)

with st.expander("Cómo leer esta página", expanded=False):
    st.markdown(
        """
- **Pendiente:** a mayor ángulo de ladera, mayor predisposición. Las laderas
  de más de 30° requieren especial atención.
- **Susceptibilidad (SGC, 1:100.000):** clasifica el terreno de 1 (menor) a 5
  (mayor) según sus condiciones naturales: geología, geomorfología, pendiente
  y cobertura. **No incluye la lluvia.**
- **Eventos SIMMA:** deslizamientos, flujos, caídas y otros movimientos
  registrados por el SGC. El *inventario* proviene de verificación en campo;
  el *catálogo* recoge registros históricos de distintas fuentes. Un lugar
  sin eventos **no** significa que no haya amenaza: puede no estar
  inventariado.
- **Amenaza por municipio (SGC, 2015):** porcentaje del área municipal en
  amenaza baja, media, alta y muy alta. Es una escala regional (1:100.000):
  no reemplaza los estudios detallados del POT.
"""
    )

if not conectar_gee():
    st.stop()


@cache_mun(ttl=86400)
def _terreno(nombre):
    return gt.mapa_terreno(nombre)


@cache_mun(ttl=86400)
def _pendiente_stats():
    return gt.estadisticas_pendiente()


# --------------------------------------------------------------------------
# 1) Mapa
# --------------------------------------------------------------------------
st.markdown("### Mapa de relieve, susceptibilidad y eventos")
c1, c2, c3, c4 = st.columns([1.3, 1, 1, 1])
with c1:
    capa_dem = st.selectbox("Relieve (DEM NASADEM 30 m)",
                            ["Ninguno"] + list(gt.CAPAS), index=1)
with c2:
    ver_sus = st.checkbox("Susceptibilidad SGC (1:100.000)", value=False)
with c3:
    ver_am = st.checkbox("Amenaza SGC (recortada)", value=False)
with c4:
    ver_ev = st.checkbox("Eventos SIMMA", value=True)

tipos_sel: list[str] = []
origenes_sel: list[str] = []
pts_all = riesgo.puntos_simma(codigo_activo())
if ver_ev:
    f1, f2 = st.columns(2)
    with f1:
        tipos = sorted(pts_all["tipo"].dropna().unique())
        tipos_sel = st.multiselect("Tipo de movimiento", tipos, default=tipos)
    with f2:
        origenes_sel = st.multiselect(
            "Fuente SIMMA", ["Inventario", "Catálogo"],
            default=["Inventario", "Catálogo"])

m = mapa_base(zoom=11, basemap="Esri.WorldImagery")

if capa_dem != "Ninguno":
    try:
        t = _terreno(capa_dem)
        m.add_tile_layer(t["tiles_url"], name=capa_dem, shown=True,
                         attribution="Google Earth Engine / NASADEM")
    except Exception as exc:  # noqa: BLE001
        st.warning(f"No fue posible generar la capa de relieve: {exc}")

if ver_sus:
    folium.TileLayer(
        tiles=riesgo.URL_SUSCEPTIBILIDAD,
        attr="Servicio Geológico Colombiano",
        name="Susceptibilidad SGC", overlay=True, control=True,
        opacity=0.6, max_native_zoom=14, max_zoom=19,
    ).add_to(m)

if ver_am:
    if not agregar_amenaza_sgc(m, geojson_municipio(), codigo_activo(),
                               visible=True):
        st.warning("No fue posible obtener el mapa de amenaza del SGC en "
                   "este momento; intente de nuevo más tarde.")

if es_departamento():
    agregar_municipios(m)
else:
    agregar_contorno(m)

if ver_ev and not pts_all.empty:
    pts = pts_all[pts_all["tipo"].isin(tipos_sel)
                  & pts_all["origen"].isin(origenes_sel)]
    grupo = folium.FeatureGroup(name=f"Eventos SIMMA ({len(pts)})")
    for r in pts.itertuples():
        folium.CircleMarker(
            [r.lat, r.lon], radius=4 if r.origen == "Inventario" else 3,
            color="#ffffff", weight=0.8, fill=True,
            fill_color=riesgo.COLOR_TIPO.get(r.tipo, "#555555"),
            fill_opacity=0.9,
            tooltip=f"{r.tipo}" + (f" · {r.subtipo}" if r.subtipo else "")
                    + f" ({r.origen}, ID {r.id})",
        ).add_to(grupo)
    grupo.add_to(m)

folium.LayerControl(collapsed=True).add_to(m)
ajustar_al_municipio(m)
m.to_streamlit(height=560)

# Leyendas
l1, l2, l3 = st.columns(3)
with l1:
    if capa_dem != "Ninguno" and capa_dem != "Relieve sombreado":
        leyenda_continua(capa_dem, gt.CAPAS[capa_dem]["vis"],
                         gt.CAPAS[capa_dem]["unidades"])
with l2:
    if ver_sus:
        st.markdown(
            "**Susceptibilidad SGC**<br>"
            "<span style='background:#38a800;color:#fff;padding:1px 8px'>1</span> "
            "<span style='background:#98e600;padding:1px 8px'>2</span> "
            "<span style='background:#ffff00;padding:1px 8px'>3</span> "
            "<span style='background:#ffaa00;padding:1px 8px'>4</span> "
            "<span style='background:#ff0000;color:#fff;padding:1px 8px'>5</span> "
            "<span style='font-size:0.8rem'>(menor → mayor)</span>",
            unsafe_allow_html=True)
with l3:
    if ver_am:
        st.markdown(
            "**Amenaza SGC**<br><span style='font-size:0.8rem'>Categorías de muy "
            "baja a muy alta, según la leyenda del SGC; recortada al área de "
            "análisis.</span>", unsafe_allow_html=True)
    if ver_ev:
        chips = " ".join(
            f"<span style='color:{riesgo.COLOR_TIPO.get(t, '#555')}'>●</span> {t}"
            for t in tipos_sel)
        st.markdown(f"<div style='font-size:0.85rem'>{chips}</div>",
                    unsafe_allow_html=True)

st.caption(
    f"Fuente de susceptibilidad y eventos: Servicio Geológico Colombiano "
    f"(geoportal.sgc.gov.co), datos de eventos descargados el "
    f"{riesgo.fecha_corte_sgc()}. La susceptibilidad se consulta en línea al "
    f"SGC; si no se dibuja, el servicio del SGC puede estar fuera de línea."
)

# --------------------------------------------------------------------------
# 2) Resumen del municipio
# --------------------------------------------------------------------------
st.divider()
st.markdown(f"### Resumen · {nombre_activo()}")
am = riesgo.amenaza_municipal()
if es_departamento():
    k1, k2, k3 = st.columns(3)
    k1.metric("Eventos SIMMA en Risaralda", f"{len(pts_all):,}".replace(",", "."))
    k2.metric("Eventos de inventario (campo)",
              int((pts_all["origen"] == "Inventario").sum()))
    top = am.sort_values("alta_muy_alta", ascending=False).iloc[0]
    k3.metric("Mayor % en amenaza alta y muy alta",
              f"{top['alta_muy_alta']:.0f} %", top["municipio"])
else:
    fila = am[am["codigo"] == codigo_activo()]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Eventos SIMMA", len(pts_all))
    k2.metric("Del inventario (campo)", int((pts_all["origen"] == "Inventario").sum()))
    if not fila.empty:
        k3.metric("Área en amenaza alta y muy alta",
                  f"{fila.iloc[0]['alta_muy_alta']:.0f} %")
    try:
        ps = _pendiente_stats()
        k4.metric("Área con pendiente > 30°", f"{ps['pct_mayor_30']:.0f} %",
                  f"pendiente media {ps['media']:.0f}°", delta_color="off")
    except Exception:  # noqa: BLE001
        pass

# Amenaza por municipio (barras apiladas)
orden = am.sort_values("alta_muy_alta", ascending=True)
fig = go.Figure()
for col, nombre, color in [("baja", "Baja", "#38a800"),
                           ("media", "Media", "#ffd000"),
                           ("alta", "Alta", "#ff8c00"),
                           ("muy_alta", "Muy alta", "#d62728")]:
    fig.add_bar(y=orden["municipio"], x=orden[col], name=nombre,
                orientation="h", marker_color=color,
                hovertemplate="%{y}: %{x:.1f} %<extra>" + nombre + "</extra>")
fig.update_layout(
    barmode="stack", height=460, margin=dict(l=0, r=10, t=30, b=0),
    title="Amenaza por movimientos en masa por municipio (% del área, SGC 2015)",
    xaxis_title="% del área municipal", yaxis_title=None,
    legend=dict(orientation="h", y=-0.15), plot_bgcolor="white",
)
st.plotly_chart(fig, use_container_width=True)

# --------------------------------------------------------------------------
# 3) Eventos registrados
# --------------------------------------------------------------------------
st.divider()
st.markdown("### Eventos registrados (SIMMA)")
if pts_all.empty:
    st.info("El SIMMA no registra eventos dentro de esta unidad de análisis.")
else:
    e1, e2 = st.columns(2)
    por_tipo = (pts_all.groupby(["tipo", "origen"]).size()
                .reset_index(name="n"))
    with e1:
        fig2 = go.Figure()
        for origen, color in [("Inventario", VERDE_CARDER), ("Catálogo", "#9aa5ab")]:
            d = por_tipo[por_tipo["origen"] == origen]
            fig2.add_bar(x=d["tipo"], y=d["n"], name=origen, marker_color=color)
        fig2.update_layout(barmode="stack", height=340, title="Por tipo de movimiento",
                           margin=dict(l=0, r=0, t=40, b=0), plot_bgcolor="white",
                           legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig2, use_container_width=True)
    with e2:
        nombres = dict(zip(am["codigo"], am["municipio"]))
        todos = riesgo.puntos_simma()
        por_mun = (todos.assign(Municipio=todos["codigo"].map(nombres))
                   .groupby("Municipio").size().sort_values())
        fig3 = go.Figure(go.Bar(x=por_mun.values, y=por_mun.index,
                                orientation="h", marker_color=VERDE_CARDER))
        fig3.update_layout(height=340, title="Por municipio (Risaralda)",
                           margin=dict(l=0, r=0, t=40, b=0), plot_bgcolor="white")
        st.plotly_chart(fig3, use_container_width=True)

    tabla = pts_all.assign(
        Municipio=pts_all["codigo"].map(dict(zip(am["codigo"], am["municipio"])))
    )[["Municipio", "tipo", "subtipo", "origen", "id", "lat", "lon"]].rename(
        columns={"tipo": "Tipo", "subtipo": "Subtipo", "origen": "Fuente SIMMA",
                 "id": "ID SIMMA", "lat": "Latitud", "lon": "Longitud"})
    st.download_button(
        "Descargar eventos (CSV)",
        tabla.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"eventos_simma_{nombre_activo().lower().replace(' ', '_')}.csv",
        mime="text/csv",
    )
    st.caption(
        "Los eventos son registros históricos, no una lista exhaustiva ni en "
        "tiempo real. Para registrar o consultar eventos nuevos, use el SIMMA "
        "del SGC (simma.sgc.gov.co)."
    )

pie_institucional()
