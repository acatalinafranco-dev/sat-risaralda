"""Página: Imágenes satelitales · Sentinel-2, Landsat 8/9 y Sentinel-1.

Catálogo filtrable (rango de fechas + nubosidad) de escenas disponibles sobre
el municipio, con visualizaciones ópticas y de radar.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import folium
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import gee_imagenes as gi
from src import gibs
from src.ui import (agregar_contorno, ajustar_al_municipio, conectar_gee,
                    encabezado, mapa_base, pie_institucional)

st.set_page_config(page_title="Satelital · SAT Pajarito", layout="wide",
                   page_icon="🛰️", initial_sidebar_state="expanded")

encabezado(
    "🛰️ Imágenes satelitales · Pajarito, Boyacá",
    "Catálogo de escenas **Sentinel-2**, **Landsat 8/9** y **Sentinel-1 "
    "(radar)**, más monitoreo casi en tiempo real con **GOES-Este** "
    "(cada 10 min) y **MODIS/VIIRS diario** (NASA GIBS).",
)

if not conectar_gee():
    st.stop()


@st.cache_data(ttl=1800, show_spinner=False)
def _cat_s2(f0, f1, nubes):
    return gi.escenas_s2(f0, f1, nubes)


@st.cache_data(ttl=1800, show_spinner=False)
def _cat_ls(f0, f1, nubes):
    return gi.escenas_landsat(f0, f1, nubes)


@st.cache_data(ttl=1800, show_spinner=False)
def _cat_s1(f0, f1, pol):
    return gi.escenas_s1(f0, f1, pol)


@st.cache_data(ttl=300, show_spinner=False)  # 5 min: casi tiempo real
def _goes(producto, _marca_tiempo):
    return gi.goes_escena(producto)


def _goes_fresco(producto):
    """Clave = intervalo de 5 min actual: cada consulta trae la última imagen."""
    marca = dt.datetime.utcnow().strftime("%Y-%m-%d %H:") + f"{dt.datetime.utcnow().minute // 5}"
    return _goes(producto, marca)


@st.cache_data(ttl=1800, show_spinner=False)
def _tiles_pan(fecha, f0, f1, nubes):
    return gi.tiles_landsat_pan(fecha, f0, f1, nubes)


@st.cache_data(ttl=1800, show_spinner=False)
def _tiles(sensor, *args):
    if sensor == "s2":
        return gi.tiles_s2(*args)
    if sensor == "ls":
        return gi.tiles_landsat(*args)
    return gi.tiles_s1(*args)


def _selector_fechas(clave: str, dias_atras: int = 120):
    hoy = dt.date.today()
    c1, c2 = st.columns(2)
    with c1:
        f0 = st.date_input("Desde", hoy - dt.timedelta(days=dias_atras),
                           key=f"{clave}_f0", max_value=hoy)
    with c2:
        f1 = st.date_input("Hasta", hoy, key=f"{clave}_f1", max_value=hoy)
    return f0.isoformat(), (f1 + dt.timedelta(days=1)).isoformat()


def _pintar(res: dict, altura: int = 560):
    m = mapa_base(zoom=12, basemap="Esri.WorldImagery")
    m.add_tile_layer(res["tiles_url"], name=f"{res['nombre']} · {res['etiqueta']}",
                     attribution="Google Earth Engine / Copernicus / USGS")
    agregar_contorno(m)
    ajustar_al_municipio(m, margen=0.008)  # zoom ceñido al municipio
    m.to_streamlit(height=altura)
    st.caption(f"**{res['nombre']}** — {res['etiqueta']}. {res['descripcion']}")


# Selector de sensor (radio en vez de st.tabs: los mapas Leaflet dentro de
# pestañas ocultas se inicializan con tamaño 0 y fitBounds resuelve zoom 0
# -> vista mundial. Con radio solo se renderiza -y se consulta a GEE- el
# sensor activo.
sensor = st.radio(
    "Sensor",
    ["Sentinel-2 (óptico 10 m)", "Landsat 8/9 (óptico 30 m)", "Sentinel-1 (radar)",
     "GOES-Este (cada 10 min)", "MODIS/VIIRS diario (NASA GIBS)"],
    horizontal=True,
    label_visibility="collapsed",
)
st.write("")

# --------------------------------------------------------------------------
# SENTINEL-2
# --------------------------------------------------------------------------
if sensor == "Sentinel-2 (óptico 10 m)":
    f0, f1 = _selector_fechas("s2")
    c1, c2 = st.columns(2)
    with c1:
        nubes = st.slider("Nubosidad máxima de escena (%)", 5, 100, 60, 5, key="s2_nb")
    with c2:
        vis = st.selectbox("Visualización", list(gi.VIS_S2.keys()),
                           format_func=lambda k: gi.VIS_S2[k]["nombre"], key="s2_vis")

    with st.spinner("Consultando catálogo Sentinel-2..."):
        escenas = _cat_s2(f0, f1, nubes)

    if not escenas:
        st.warning("Sin escenas S2 en el rango con ese umbral de nubes. "
                   "Amplíe fechas o suba el umbral (el piedemonte es muy nuboso).")
    else:
        opciones = ["🧩 Compuesto mediano del rango"] + [
            f"{e['fecha']}  ·  {e['nubes']:.0f}% nubes" for e in escenas
        ]
        sel = st.selectbox(f"Escena ({len(escenas)} disponibles)", opciones,
                           index=1, key="s2_sel")
        fecha = None if sel.startswith("🧩") else sel.split("·")[0].strip()

        with st.spinner("Generando visualización..."):
            res = _tiles("s2", vis, fecha, f0, f1, nubes)
        _pintar(res)

        with st.expander("📅 Calendario de escenas del rango"):
            st.dataframe(pd.DataFrame(escenas).rename(
                columns={"fecha": "Fecha", "nubes": "Nubes (%)"}),
                use_container_width=True, hide_index=True)

# --------------------------------------------------------------------------
# LANDSAT
# --------------------------------------------------------------------------
if sensor == "Landsat 8/9 (óptico 30 m)":
    f0, f1 = _selector_fechas("ls", dias_atras=365)
    c1, c2 = st.columns(2)
    with c1:
        nubes = st.slider("Nubosidad máxima de escena (%)", 5, 100, 70, 5, key="ls_nb")
    with c2:
        vis = st.selectbox("Visualización", list(gi.VIS_LANDSAT.keys()),
                           format_func=lambda k: gi.VIS_LANDSAT[k]["nombre"], key="ls_vis")

    with st.spinner("Consultando catálogo Landsat 8/9..."):
        escenas = _cat_ls(f0, f1, nubes)

    if not escenas:
        st.warning("Sin escenas Landsat en el rango con ese umbral. Landsat "
                   "revisita cada ~8 días (L8+L9): amplíe el rango de fechas.")
    else:
        opciones = ["🧩 Compuesto mediano del rango"] + [
            f"{e['fecha']}  ·  {e['nubes']:.0f}% nubes  ·  {e['satelite']}"
            for e in escenas
        ]
        sel = st.selectbox(f"Escena ({len(escenas)} disponibles)", opciones,
                           index=1, key="ls_sel")
        fecha = None if sel.startswith("🧩") else sel.split("·")[0].strip()

        pan = False
        if vis == "color_real":
            pan = st.checkbox(
                "🔍 Nitidez 15 m (fusión con banda pancromática B8)",
                value=True, key="ls_pan",
                help="Fusión HSV con la pancromática del producto TOA: "
                     "duplica el detalle espacial del color real (30 m → 15 m)",
            )

        with st.spinner("Generando visualización..."):
            if pan:
                res = _tiles_pan(fecha, f0, f1, nubes)
            else:
                res = _tiles("ls", vis, fecha, f0, f1, nubes)
        _pintar(res)

        with st.expander("📅 Calendario de escenas del rango"):
            st.dataframe(pd.DataFrame(escenas).rename(
                columns={"fecha": "Fecha", "nubes": "Nubes (%)", "satelite": "Satélite"}),
                use_container_width=True, hide_index=True)

# --------------------------------------------------------------------------
# SENTINEL-1 (RADAR)
# --------------------------------------------------------------------------
if sensor == "Sentinel-1 (radar)":
    st.caption(
        "El radar SAR **penetra nubes** y opera día y noche: es la fuente más "
        "confiable en el piedemonte durante temporada de lluvias. Cambios "
        "bruscos de retrodispersión entre fechas pueden indicar remoción de "
        "suelo/vegetación."
    )
    f0, f1 = _selector_fechas("s1", dias_atras=90)
    pol = st.selectbox("Polarización", ["VV", "VH"], key="s1_pol",
                       help="VV: sensible a rugosidad del terreno · VH: sensible a estructura de vegetación")

    with st.spinner("Consultando catálogo Sentinel-1..."):
        escenas = _cat_s1(f0, f1, pol)

    if not escenas:
        st.warning("Sin pasadas Sentinel-1 en el rango. Amplíe las fechas "
                   "(revisita ~12 días).")
    else:
        opciones = ["🧩 Compuesto mediano del rango"] + [
            f"{e['fecha']}  ·  órbita {e['orbita'].lower()}" for e in escenas
        ]
        sel = st.selectbox(f"Pasada ({len(escenas)} disponibles)", opciones,
                           index=1, key="s1_sel")
        fecha = None if sel.startswith("🧩") else sel.split("·")[0].strip()

        with st.spinner("Generando radar..."):
            res = _tiles("s1", pol, fecha, f0, f1)
        _pintar(res)

        with st.expander("📅 Calendario de pasadas del rango"):
            st.dataframe(pd.DataFrame(escenas).rename(
                columns={"fecha": "Fecha", "orbita": "Órbita"}),
                use_container_width=True, hide_index=True)

# --------------------------------------------------------------------------
# GOES-ESTE (geoestacionario · casi tiempo real)
# --------------------------------------------------------------------------
if sensor == "GOES-Este (cada 10 min)":
    st.caption(
        "El geoestacionario **GOES-Este (75°O)** es el único que observa a "
        "Colombia de forma continua: una imagen full-disk cada 10 minutos, "
        "con ~15-30 min de latencia en GEE. Ideal para vigilar la convección "
        "que dispara los aguaceros sobre el piedemonte. Resolución ~1-2 km: "
        "vista regional, no municipal."
    )
    producto = st.selectbox(
        "Producto",
        ["geocolor", "visible", "ir"],
        format_func=lambda k: {
            "geocolor": "GeoColor aproximado (diurno)",
            "visible": "Visible C02 (diurno)",
            "ir": "Infrarrojo C13 · nubes (día y noche)",
        }[k],
        index=2,
        help="De noche solo el infrarrojo C13 muestra información",
    )
    try:
        with st.spinner("Consultando última imagen GOES..."):
            res = _goes_fresco(producto)
        m = mapa_base(zoom=8, basemap="Esri.WorldImagery")
        m.add_tile_layer(res["tiles_url"],
                         name=f"{res['satelite']} · {res['etiqueta']}",
                         attribution="NOAA / Google Earth Engine",
                         opacity=0.85)
        agregar_contorno(m)
        ajustar_al_municipio(m, margen=1.2)  # vista regional (~250 km)
        m.to_streamlit(height=560)
        c1, c2 = st.columns(2)
        c1.metric("Satélite", res["satelite"])
        c2.metric("Hora de la imagen", res["etiqueta"])
        st.caption(f"**{res['nombre']}** — {res['descripcion']} "
                   "La imagen se refresca automáticamente cada ~5 minutos "
                   "(caché) al recargar la página.")
    except Exception as exc:
        st.warning(f"GOES no disponible en este momento: {exc}")

# --------------------------------------------------------------------------
# MODIS / VIIRS DIARIO (NASA GIBS · sin GEE)
# --------------------------------------------------------------------------
if sensor == "MODIS/VIIRS diario (NASA GIBS)":
    st.caption(
        "Reflectancia corregida en **color real** de NASA Worldview (GIBS): "
        "una imagen por día y satélite, disponible ~3-5 horas después del "
        "paso (media mañana y primera tarde). Resolución 250-375 m: vista "
        "subregional. Útil para ver la nubosidad y el estado del territorio "
        "de HOY sin esperar a Sentinel/Landsat."
    )
    c1, c2 = st.columns(2)
    with c1:
        capa = st.selectbox(
            "Satélite / capa",
            list(gibs.CAPAS_GIBS.keys()),
            format_func=lambda k: gibs.CAPAS_GIBS[k]["nombre"],
        )
    with c2:
        fecha_gibs = st.date_input(
            "Fecha", dt.date.today(),
            max_value=dt.date.today(),
            min_value=dt.date.today() - dt.timedelta(days=365),
        )
    info = gibs.CAPAS_GIBS[capa]
    m = mapa_base(zoom=10, basemap="Esri.WorldImagery")
    folium.TileLayer(
        tiles=gibs.url_tiles(capa, fecha_gibs),
        attr="NASA EOSDIS GIBS / Worldview",
        name=f"{info['nombre']} · {fecha_gibs}",
        overlay=True,
        control=True,
        max_native_zoom=9,   # GIBS sirve hasta z9; de ahí en adelante se amplía
        max_zoom=14,
    ).add_to(m)
    agregar_contorno(m)
    ajustar_al_municipio(m, margen=0.008)  # zoom a nivel de municipio
    m.to_streamlit(height=560)
    st.caption(
        f"**{info['nombre']}** · resolución {info['res']} · paso "
        f"{info['paso']}. Si la imagen de hoy aparece vacía o parcial, el "
        "satélite aún no ha pasado o GIBS no la ha publicado: seleccione el "
        "día anterior. Franjas negras = zonas sin cobertura del paso diario."
    )

pie_institucional()
