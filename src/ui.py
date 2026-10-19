"""Componentes de interfaz compartidos por todas las páginas.

Incluye la identidad institucional de la CARDER (logo, colores y pie con el
descargo de responsabilidad en el marco de la Ley 1523 de 2012).
"""
from __future__ import annotations

import base64
import io
from functools import lru_cache
from pathlib import Path

import folium
import leafmap.foliumap as leafmap
import streamlit as st

from .gee_session import MUNICIPIO, bounds_municipio, geojson_municipio, init_ee

# ---- Identidad institucional CARDER ----------------------------------------
# Los nombres de las variables de color se conservan para no romper las páginas.
AZUL_UNGRD = "#004B87"      # azul institucional CARDER
NARANJA_UNGRD = "#008A4B"   # verde institucional CARDER (color de acento)
AMARILLO_UNGRD = "#FFCC00"  # amarillo CARDER

RUTA_LOGO = Path(__file__).resolve().parent.parent / "logo" / "carder-logo.png"
DEPENDENCIA = "Subdirección para el Conocimiento y la Reducción del Riesgo - SCORE"
ENTIDAD = "Corporación Autónoma Regional de Risaralda - CARDER"
CONTACTO = "correo@carder.gov.co"  # ← escriba aquí su correo de contacto
CITA = (
    "Corporación Autónoma Regional de Risaralda - CARDER (2026). Monitoreo "
    "Satelital de Movimientos en Masa, Risaralda: seguimiento "
    "hidrometeorológico y de cobertura vegetal con Google Earth Engine. "
    "Subdirección para el Conocimiento y la Reducción del Riesgo - SCORE. "
)



@lru_cache(maxsize=1)
def _logo_fondo_blanco() -> bytes | None:
    """Devuelve el logo compuesto sobre fondo blanco (PNG en bytes).

    El logo institucional tiene fondo transparente y texto oscuro; sobre el
    tema oscuro de Streamlit el texto se pierde. Aquí se aplana sobre blanco
    para que st.logo lo muestre nítido. Si Pillow no está o falla, devuelve
    el PNG original.
    """
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


def _logo_html(ancho: int = 240) -> str | None:
    """Logo sobre tarjeta blanca (el PNG institucional trae texto oscuro que
    se perdería sobre el tema oscuro de la app)."""
    b64 = _logo_b64()
    if not b64:
        return None
    return (
        f"<div style='background:#ffffff; padding:8px 14px; border-radius:8px; "
        f"display:inline-block; border-bottom:4px solid {NARANJA_UNGRD};'>"
        f"<img src='data:image/png;base64,{b64}' width='{ancho}'></div>"
    )


def branding_institucional() -> None:
    """Logo institucional (fondo blanco) fijo arriba de la barra lateral.

    Usa la API nativa st.logo, que ancla el logo por encima de la navegación
    de páginas SIN CSS. El logo se aplana sobre blanco para ser legible en el
    tema oscuro. La leyenda de dependencia/entidad va debajo, en el sidebar.
    Idempotente: seguro de llamar en cada página.
    """
    datos = _logo_fondo_blanco()
    if datos:
        # st.logo necesita ruta o URL; guardamos el PNG compuesto una vez.
        ruta_tmp = RUTA_LOGO.parent / "_ungrd_blanco.png"
        try:
            if not ruta_tmp.exists():
                ruta_tmp.write_bytes(datos)
            st.logo(str(ruta_tmp), size="large")
        except Exception:
            pass

    with st.sidebar:
        st.markdown(
            f"<div style='font-size:0.78rem; color:#c9c9c9; margin-top:4px; "
            f"line-height:1.35;'><b>{DEPENDENCIA}</b><br>"
            f"<span style='color:#9a9a9a;'>{ENTIDAD}</span></div>"
            f"<hr style='border:none; height:3px; margin:8px 0 4px 0; "
            f"background:linear-gradient(to right, {AZUL_UNGRD}, {NARANJA_UNGRD});'>",
            unsafe_allow_html=True,
        )


def pie_institucional() -> None:
    """Descargo (Ley 1523 de 2012), citación y contacto. Llamar al final."""
    st.markdown(
        f"<hr style='border:none; height:3px; margin:24px 0 12px 0; "
        f"background:linear-gradient(to right, {AZUL_UNGRD}, {NARANJA_UNGRD});'>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
<div style='font-size:0.8rem; color:#b8b8b8; line-height:1.5;'>
<b style='color:{NARANJA_UNGRD};'>⚠️ Descargo de responsabilidad.</b>
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
    st.markdown(f"## {titulo}")
    st.markdown(
        f"<hr style='border:none; height:4px; margin:0 0 12px 0; width:260px; "
        f"background:linear-gradient(to right, {AZUL_UNGRD}, {NARANJA_UNGRD});'>",
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


# Tile oficial de Esri World Imagery (no depende del catálogo de leafmap,
# que en algunas versiones no reconoce el nombre "Esri.WorldImagery").
ESRI_IMAGERY_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
ESRI_IMAGERY_ATTR = "Esri, Maxar, Earthstar Geographics, GIS User Community"


def mapa_base(zoom: int = 12, basemap: str = "Esri.WorldImagery") -> leafmap.Map:
    m = leafmap.Map(
        center=[MUNICIPIO["lat"], MUNICIPIO["lon"]],
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


def agregar_contorno(m: leafmap.Map, nombre: str = "Límite Pajarito") -> None:
    folium.GeoJson(
        geojson_municipio(),
        name=nombre,
        style_function=lambda _: {
            "color": "#ffff00", "weight": 2.5, "fill": False,
        },
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
