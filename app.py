"""Monitoreo Satelital de Movimientos en Masa · Risaralda · Página de inicio.

Monitoreo satelital basado en productos de Google Earth Engine
(hidrometeorología y cobertura vegetal) para el departamento de Risaralda y
sus 14 municipios. Adaptación de la aplicación desarrollada por J. A. Alpala
(UNGRD) para Pajarito, Boyacá.

Ejecutar local:  streamlit run app.py
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

from src.gee_comparativo import tabla_comparativa
from src.gee_session import nombre_activo
from src.ui import (DEPENDENCIA, ENTIDAD, GRADIENTE, VERDE_CARDER,
                    agregar_municipios, ajustar_al_municipio,
                    branding_institucional, conectar_gee, mapa_base,
                    pie_institucional)

st.set_page_config(
    page_title="Monitoreo MM · Risaralda",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

branding_institucional()

st.title("🛰️ Monitoreo Satelital Movimientos en Masa · Risaralda")
st.markdown(
    f"<div style='font-size:1.05rem; font-weight:600; color:{VERDE_CARDER}; "
    f"margin-top:-8px;'>{DEPENDENCIA}</div>"
    f"<div style='font-size:0.92rem; color:#3a3a3a; margin-top:2px;'>"
    f"{ENTIDAD}</div>"
    f"<hr style='border:none; height:4px; margin:10px 0 14px 0; width:340px; "
    f"background:{GRADIENTE};'>",
    unsafe_allow_html=True,
)
st.markdown(
    f"""
**Monitoreo satelital de movimientos en masa** para el departamento de
**Risaralda** y sus **14 municipios**: zona de cordillera con alta pendiente y
lluvias intensas, con recurrencia histórica de **movimientos en masa** y
crecientes súbitas.

Los datos se calculan **en vivo desde Google Earth Engine** sobre el polígono
oficial (DIVIPOLA). Elija en la barra lateral **«Todo Risaralda»** o un
municipio: las tres páginas de análisis se calculan sobre esa selección.

**Unidad de análisis actual: {nombre_activo()}**
"""
)

conectado = conectar_gee()

c1, c2 = st.columns([1.4, 1])

with c1:
    st.markdown("#### Área de monitoreo")
    m = mapa_base(zoom=9, basemap="SATELLITE")
    agregar_municipios(m)
    ajustar_al_municipio(m, margen=0.03)
    m.to_streamlit(height=480)

with c2:
    st.markdown("#### Módulos del sistema")
    st.markdown(
        """
**🌧️ Precipitación** — series diarias comparadas (IMERG · CHIRPS · ERA5-Land)
para la última semana, mes, 6 meses y año; mapas interpolados de lluvia
acumulada; climatología CHIRPS de los últimos 20 años.

**🛰️ Imágenes satelitales** — catálogo filtrable de escenas Sentinel-2,
Landsat 8/9 y Sentinel-1 (radar), con visualizaciones en color real, falso
color y SAR.

**🌿 Índices de vegetación** — NDVI, NDMI y BSI, detección de cambios
(ΔNDVI) para identificar pérdida de cobertura vegetal asociada a
**movimientos en masa**, y serie temporal de NDVI.
"""
    )
    st.markdown("#### Estado")
    if conectado:
        st.success("Google Earth Engine conectado ✔")
    st.info(
        "**IDEAM (red terrestre):** integración pendiente para una próxima "
        "iteración; hoy el sistema opera 100 % con fuentes satelitales.",
        icon="📡",
    )

st.divider()

# --------------------------------------------------------------------------
# Comparativo de los 14 municipios
# --------------------------------------------------------------------------
st.markdown("#### Comparativo entre municipios")
st.caption(
    "Lluvia acumulada (IMERG, media sobre el polígono) y pérdida severa de "
    "vegetación (ΔNDVI < −0,20 sobre zonas con NDVI > 0,4; Sentinel-2, últimos "
    "60 días frente a hace 6–12 meses). Se calcula para los 14 municipios en "
    "una sola consulta y se actualiza cada día."
)


@st.cache_data(ttl=21600, show_spinner=False)
def _comparativo(fecha_consulta: str):
    return tabla_comparativa()


if conectado:
    with st.spinner("Calculando el comparativo de los 14 municipios "
                    "(la primera carga del día puede tardar unos minutos)..."):
        try:
            res = _comparativo(dt.date.today().isoformat())
        except Exception as exc:  # noqa: BLE001
            res = {"filas": [], "errores": [str(exc)]}

    for e in res["errores"]:
        st.warning(f"No fue posible calcular una parte del comparativo. {e}")

    if res["filas"]:
        df = pd.DataFrame(res["filas"]).rename(columns={
            "nombre": "Municipio", "area_km2": "Área (km²)",
            "lluvia_7d": "Lluvia 7 días (mm)",
            "lluvia_30d": "Lluvia 30 días (mm)",
            "perdida_ha": "Pérdida de vegetación (ha)",
            "perdida_pct": "% del área municipal",
        }).drop(columns=["codigo"])
        orden = st.radio(
            "Ordenar por", ["Municipio", "Lluvia 30 días (mm)",
                            "Pérdida de vegetación (ha)"],
            horizontal=True,
        )
        df = df.sort_values(orden, ascending=(orden == "Municipio"),
                            na_position="last")
        st.dataframe(
            df, hide_index=True, use_container_width=True,
            column_config={
                "Área (km²)": st.column_config.NumberColumn(format="%.1f"),
                "Lluvia 7 días (mm)": st.column_config.NumberColumn(format="%.0f"),
                "Lluvia 30 días (mm)": st.column_config.NumberColumn(format="%.0f"),
                "Pérdida de vegetación (ha)": st.column_config.NumberColumn(format="%.0f"),
                "% del área municipal": st.column_config.NumberColumn(format="%.2f"),
            },
        )
        st.download_button(
            "Descargar tabla (CSV)",
            df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"comparativo_risaralda_{dt.date.today().isoformat()}.csv",
            mime="text/csv",
        )
        st.caption(
            "Los valores son indicativos: IMERG tiene píxeles de ~11 km, por lo "
            "que en municipios pequeños (La Virginia, Dosquebradas) la lluvia "
            "refleja el campo regional. La pérdida de vegetación debe verificarse "
            "contra la imagen en color real antes de cualquier decisión."
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
    "Monitoreo Satelital de Movimientos en Masa · Risaralda · datos calculados "
    "en vivo desde Google Earth Engine sobre los polígonos DIVIPOLA (DANE). "
    "Adaptación de la aplicación de J. A. Alpala (UNGRD)."
)

pie_institucional()
