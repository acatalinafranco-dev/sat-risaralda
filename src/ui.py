"""Componentes de interfaz compartidos por todas las páginas.

Incluye la identidad institucional de la CARDER (logo, colores y pie con el
descargo de responsabilidad en el marco de la Ley 1523 de 2012) y el selector
de municipio (Todo Risaralda + 14 municipios) que gobierna todas las páginas.
"""
from __future__ import annotations

import base64
import io
from functools import lru_cache
from pathlib import Path

import folium
import leafmap.foliumap as leafmap
import streamlit as st

from .gee_session import (CODIGO_DEPTO, MUNICIPIO, bounds_municipio,
                          centro_activo, codigo_activo, geojson_municipio,
                          geojson_municipios, init_ee, lista_municipios,
                          nombre_activo)

# ---- Identidad institucional CARDER ----------------------------------------
VERDE_CARDER = "#008A4B"
AZUL_CARDER = "#004B87"
AMARILLO_CARDER = "#FFCC00"
# Nombres heredados (las páginas los importan): se conservan como alias.
AZUL_UNGRD = AZUL_CARDER
NARANJA_UNGRD = VERDE_CARDER      # color de acento = verde CARDER
AMARILLO_UNGRD = AMARILLO_CARDER

RUTA_LOGO = Path(__file__).resolve().parent.parent / "logo" / "carder-logo.png"
DEPENDENCIA = "Subdirección para el Conocimiento y la Reducción del Riesgo - SCORE"
ENTIDAD = "Corporación Autónoma Regional de Risaralda - CARDER"
CONTACTO = "agalindo@carder.gov.co"
CITA = (
    "Corporación Autónoma Regional de Risaralda - CARDER (2026). Monitoreo "
    "Satelital de Movimientos en Masa, Risaralda: seguimiento "
    "hidrometeorológico y de cobertura vegetal con Google Earth Engine. "
    "Subdirección para el Conocimiento y la Reducción del Riesgo - SCORE. "
    "Aplicación web Streamlit. Adaptación de la aplicación desarrollada por "
    "J. A. Alpala (2026), Subdirección para el Conocimiento del Riesgo, "
    "Unidad Nacional para la Gestión del Riesgo de Desastres (UNGRD)."
)

GRADIENTE = f"linear-gradient(to right, {AZUL_CARDER}, {VERDE_CARDER}, {AMARILLO_CARDER})"


@lru_cache(maxsize=1)
def _logo_fondo_blanco() -> bytes | None:
    """Devuelve el logo compuesto sobre fondo blanco (PNG en bytes)."""
    if not RUTA_LOGO.exists():
        return None
    try:
        from PIL import Image

        img = Image.open(RUTA_LOGO).convert("RGBA")
        fondo = Image.new("RGBA", img.size, (255, 255, 255, 255))
        fondo.paste(img, (0, 0), img)
        buf = io.BytesIO()
        fondo.convert("RGB").save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        try:
            return RUTA_LOGO.read_bytes()
        except Exception:
            return None


@lru_cache(maxsize=1)
def _logo_b64() -> str | None:
    try:
        return base64.b64encode(RUTA_LOGO.read_bytes()).decode()
    except Exception:
        return None


def selector_municipio() -> None:
    """Selector de unidad de análisis en la barra lateral.

    'Todo Risaralda' o uno de los 14 municipios. La elección se guarda en
    st.session_state['mun_codigo'] y la leen todas las páginas.
    """
    opciones = [(CODIGO_DEPTO, "Todo Risaralda")] + lista_municipios()
    codigos = [c for c, _ in opciones]
    nombres = dict(opciones)
    actual = codigo_activo()
    idx = codigos.index(actual) if actual in codigos else 0
    with st.sidebar:
        sel = st.selectbox(
            "Municipio de análisis", codigos, index=idx,
            format_func=lambda c: nombres[c],
            help="Todas las páginas se calculan sobre el polígono elegido.",
        )
    st.session_state["mun_codigo"] = sel


def cache_mun(ttl: int):
    """Como st.cache_data, pero la clave incluye el municipio elegido, para
    que cambiar de municipio nunca devuelva resultados de otro."""
    def deco(fn):
        def _interna(_id, _codigo, *args, **kwargs):
            return fn(*args, **kwargs)

        _interna.__name__ = fn.__name__
        _interna.__qualname__ = f"cache_mun.{fn.__qualname__}"
        cacheada = st.cache_data(ttl=ttl, show_spinner=False)(_interna)

        def envoltura(*args, **kwargs):
            return cacheada(fn.__qualname__, codigo_activo(), *args, **kwargs)

        envoltura.__name__ = fn.__name__
        return envoltura

    return deco


def branding_institucional() -> None:
    """Logo institucional (fondo blanco) fijo arriba de la barra lateral,
    leyenda de dependencia/entidad y selector de municipio.
    Idempotente: seguro de llamar en cada página."""
    datos = _logo_fondo_blanco()
    if datos:
        ruta_tmp = RUTA_LOGO.parent / "_carder_blanco.png"
        try:
            if not ruta_tmp.exists():
                ruta_tmp.write_bytes(datos)
            st.logo(str(ruta_tmp), size="large")
        except Exception:
            pass

    with st.sidebar:
        st.markdown(
            f"<div style='font-size:0.78rem; color:#3a3a3a; margin-top:4px; "
            f"line-height:1.35;'><b>{DEPENDENCIA}</b><br>"
            f"<span style='color:#666666;'>{ENTIDAD}</span></div>"
            f"<hr style='border:none; height:3px; margin:8px 0 4px 0; "
            f"background:{GRADIENTE};'>",
            unsafe_allow_html=True,
        )
    selector_municipio()


def pie_institucional() -> None:
    """Descargo (Ley 1523 de 2012), citación y contacto. Llamar al final."""
    st.markdown(
        f"<hr style='border:none; height:3px; margin:24px 0 12px 0; "
        f"background:{GRADIENTE};'>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
<div style='font-size:0.8rem; color:#3a3a3a; line-height:1.5;'>
<b style='color:{VERDE_CARDER};'>⚠️ Descargo de responsabilidad.</b>
Este es un <b>sistema de monitoreo satelital de apoyo</b> al conocimiento del
riesgo. En el marco de la <b>Ley 1523 de 2012</b> (Política Nacional de
Gestión del Riesgo de Desastres), <b>no sustituye</b> los sistemas de alerta
temprana físicos/instrumentales ni comunitarios, ni los protocolos y
decisiones de los consejos municipales y departamentales de gestión del
riesgo (CMGRD/CDGRD), ni las alertas oficiales del IDEAM y del Servicio
Geológico Colombiano.<br><br>
<b>Cómo citar:</b> {CITA}<br>
<b>Contacto:</b> <a href='mailto:{CONTACTO}'>{CONTACTO}</a> ·
{DEPENDENCIA} · {ENTIDAD}
</div>
""",
        unsafe_allow_html=True,
    )


MESES_ES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
            "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

COLOR_FUENTE = {"imerg": "#1e88e5", "chirps": "#f57c00", "era5": "#43a047"}
NOMBRE_FUENTE = {
    "imerg": "IMERG (NASA)",
    "chirps": "CHIRPS (UCSB)",
    "era5": "ERA5-Land (ECMWF)",
}


def encabezado(titulo: str, subtitulo: str) -> None:
    branding_institucional()
    titulo = titulo.replace("{mun}", nombre_activo())
    st.markdown(f"## {titulo}")
    st.markdown(
        f"<hr style='border:none; height:4px; margin:0 0 12px 0; width:260px; "
        f"background:{GRADIENTE};'>",
        unsafe_allow_html=True,
    )
    st.markdown(subtitulo)
    st.divider()


def conectar_gee() -> bool:
    """Inicializa GEE mostrando un error accionable si falla."""
    try:
        init_ee()
        return True
    except Exception as exc:
        st.error(
            "No fue posible conectar con Google Earth Engine. "
            "Verifique la autenticación (ver README, sección *Autenticación GEE*).\n\n"
            f"Detalle: `{exc}`"
        )
        return False


# Tile oficial de Esri World Imagery.
ESRI_IMAGERY_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
ESRI_IMAGERY_ATTR = "Esri, Maxar, Earthstar Geographics, GIS User Community"


def mapa_base(zoom: int = 12, basemap: str = "Esri.WorldImagery") -> leafmap.Map:
    lat, lon = centro_activo()
    m = leafmap.Map(
        center=[lat, lon],
        zoom=zoom,
        draw_control=False,
        measure_control=False,
    )
    if basemap in ("Esri.WorldImagery", "SATELLITE"):
        folium.TileLayer(
            tiles=ESRI_IMAGERY_URL,
            attr=ESRI_IMAGERY_ATTR,
            name="Esri WorldImagery",
            overlay=False,
            control=True,
            max_zoom=19,
        ).add_to(m)
    else:
        try:
            m.add_basemap(basemap)
        except Exception:
            pass
    return m


def agregar_contorno(m: leafmap.Map, nombre: str | None = None) -> None:
    folium.GeoJson(
        geojson_municipio(),
        name=nombre or f"Límite {nombre_activo()}",
        style_function=lambda _: {
            "color": "#ffff00", "weight": 2.5, "fill": False,
        },
    ).add_to(m)


def agregar_municipios(m: leafmap.Map) -> None:
    """Pinta los 14 municipios con su nombre; resalta el elegido."""
    activo = codigo_activo()

    def _estilo(feat):
        es = feat["properties"]["codigo"] == activo
        return {
            "color": "#ffff00" if es else "#ffffff",
            "weight": 3.5 if es else 1.2,
            "fillColor": VERDE_CARDER,
            "fillOpacity": 0.35 if es else 0.08,
        }

    folium.GeoJson(
        geojson_municipios(),
        name="Municipios de Risaralda",
        style_function=_estilo,
        tooltip=folium.GeoJsonTooltip(
            fields=["nombre", "area_km2"], aliases=["Municipio", "Área (km²)"]),
    ).add_to(m)


def ajustar_al_municipio(m: leafmap.Map, margen: float = 0.03) -> None:
    (la0, lo0), (la1, lo1) = bounds_municipio()
    m.fit_bounds([[la0 - margen, lo0 - margen], [la1 + margen, lo1 + margen]])


def leyenda_continua(titulo: str, vis: dict, unidades: str = "") -> None:
    """Leyenda simple min→max con la paleta usada."""
    paleta = vis.get("palette", [])
    colores = ", ".join(f"#{c.lstrip('#')}" for c in paleta)
    st.markdown(
        f"""
        <div style="font-size:0.85rem; margin-top:-0.5rem;">
          <b>{titulo}</b><br>
          <div style="background: linear-gradient(to right, {colores});
                      height: 14px; border-radius: 3px; border: 1px solid #999;"></div>
          <div style="display:flex; justify-content:space-between;">
            <span>{vis.get('min', 0)} {unidades}</span>
            <span>{vis.get('max', '')} {unidades}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
