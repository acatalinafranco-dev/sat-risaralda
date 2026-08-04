"""Monitoreo Satelital de Movimientos en Masa - Pajarito (Boyacá) · Página de inicio.

Monitoreo satelital de movimientos en masa basado en productos de Google
Earth Engine (hidrometeorología y cobertura vegetal) para el municipio de
Pajarito, Boyacá (piedemonte llanero).

Ejecutar local:  streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

from src.gee_session import MUNICIPIO
from src.ui import (AZUL_UNGRD, DEPENDENCIA, ENTIDAD, NARANJA_UNGRD,
                    agregar_contorno, ajustar_al_municipio,
                    branding_institucional, conectar_gee, mapa_base,
                    pie_institucional)

st.set_page_config(
    page_title="Monitoreo MM · Pajarito, Boyacá",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

branding_institucional()

st.title("🛰️ Monitoreo Satelital Movimientos en Masa · Pajarito, Boyacá")
st.markdown(
    f"<div style='font-size:1.05rem; font-weight:600; color:{NARANJA_UNGRD}; "
    f"margin-top:-8px;'>{DEPENDENCIA}</div>"
    f"<div style='font-size:0.92rem; color:#c9c9c9; margin-top:2px;'>"
    f"{ENTIDAD}</div>"
    f"<hr style='border:none; height:4px; margin:10px 0 14px 0; width:340px; "
    f"background:linear-gradient(to right, {AZUL_UNGRD}, {NARANJA_UNGRD});'>",
    unsafe_allow_html=True,
)
st.markdown(
    f"""
**Monitoreo satelital de movimientos en masa** para el municipio de
**{MUNICIPIO['nombre']} ({MUNICIPIO['departamento']})** — código DANE
`{MUNICIPIO['codigo_dane']}`, ~{MUNICIPIO['area_km2']:.0f} km², cabecera a
{MUNICIPIO['altitud_cabecera_m']} m s.n.m. en el piedemonte llanero, sobre la
vía Sogamoso–Yopal: territorio de alta pendiente y lluvias intensas, con
recurrencia histórica de **movimientos en masa** y crecientes súbitas.

Los datos se calculan **en vivo desde Google Earth Engine** sobre el polígono
oficial del municipio (DIVIPOLA), sin bases de datos intermedias.
"""
)

conectado = conectar_gee()

c1, c2 = st.columns([1.4, 1])

with c1:
    st.markdown("#### Área de monitoreo")
    m = mapa_base(zoom=11, basemap="SATELLITE")
    agregar_contorno(m)
    ajustar_al_municipio(m)
    m.to_streamlit(height=480)

with c2:
    st.markdown("#### Módulos del sistema")
    st.markdown(
        """
**🌧️ Precipitación** — series diarias comparadas (IMERG · CHIRPS · ERA5-Land)
para la última semana, mes, 6 meses y año; mapas interpolados de lluvia
acumulada; climatología CHIRPS de los últimos 20 años.

**🛰️ Imágenes satelitales** — catálogo filtrable de escenas Sentinel-2,
Landsat 8/9 y Sentinel-1 (radar) sobre el municipio, con visualizaciones en
color real, falso color y SAR.

**🌿 Índices de vegetación** — NDVI, NDMI y BSI, detección de cambios
(ΔNDVI) para identificar pérdida de cobertura vegetal asociada a
**movimientos en masa**, y serie temporal de NDVI municipal.
"""
    )
    st.markdown("#### Estado")
    if conectado:
        st.success("Google Earth Engine conectado ✔")
    st.info(
        "**IDEAM (red terrestre):** integración pendiente para una próxima "
        "iteración; hoy el SAT opera 100 % con fuentes satelitales.",
        icon="📡",
    )

st.divider()

st.markdown("#### Fuentes de datos")
st.markdown(
    """
| Fuente | Producto GEE | Resolución | Latencia aprox. | Uso en el SAT |
|---|---|---|---|---|
| NASA GPM **IMERG V07** | `NASA/GPM_L3/IMERG_V07` | ~11 km / 30 min | 1–2 días | Lluvia casi en tiempo real |
| UCSB **CHIRPS** | `UCSB-CHG/CHIRPS/DAILY` + `PENTAD` | ~5.5 km / diario | 2–3 semanas | Series y climatología 20 años |
| ECMWF **ERA5-Land** | `ECMWF/ERA5_LAND/DAILY_AGGR` | ~11 km / diario | ~6 días | Contraste de patrones temporales |
| **Sentinel-2** SR | `COPERNICUS/S2_SR_HARMONIZED` | 10–20 m / ~5 días | horas–días | Óptico + índices de vegetación |
| **Landsat 8/9** C2L2 | `LANDSAT/LC08·LC09/C02/T1_L2` | 30 m / ~8 días | ~1 día | Óptico histórico |
| **Sentinel-1** GRD | `COPERNICUS/S1_GRD` | ~10 m / ~12 días | ~1 día | Radar (penetra nubes) |

> **Nota sobre ERA5-Land en montaña andina:** tiende a sobreestimar la lluvia
> orográfica; úselo para patrones y tendencias, no para magnitudes absolutas.
> Para valores absolutos son más confiables CHIRPS e IMERG.
"""
)

st.caption(
    "Monitoreo Satelital de Movimientos en Masa · Pajarito · datos calculados en vivo desde Google Earth "
    "sobre el polígono municipal DIVIPOLA (DANE)."
)

pie_institucional()
