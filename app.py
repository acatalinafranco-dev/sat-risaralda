"""Monitoreo Satelital de Movimientos en Masa · Risaralda · Página de inicio.

Monitoreo satelital basado en productos de Google Earth Engine
(hidrometeorología y cobertura vegetal) para el departamento de Risaralda y
sus 14 municipios. 

Ejecutar local:  streamlit run app.py
"""
from __future__ import annotations

import datetime as dt
import json

import folium
import pandas as pd
import streamlit as st

from src.gee_comparativo import tabla_comparativa
from src import riesgo
from src.gee_session import geojson_municipios, nombre_activo
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

st.title("🛰️ Monitoreo Satelital de Movimientos en Masa · Risaralda")
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
municipio: las páginas de análisis se calculan sobre esa selección.

**Unidad de análisis actual: {nombre_activo()}**
"""
)

conectado = conectar_gee()


@st.cache_data(ttl=21600, show_spinner=False)
def _comparativo_v2(fecha_consulta: str):
    return tabla_comparativa()


res = {"filas": [], "errores": []}
if conectado:
    with st.spinner("Calculando los indicadores de los 14 municipios "
                    "(la primera carga del día puede tardar unos minutos)..."):
        try:
            res = _comparativo_v2(dt.date.today().isoformat())
        except Exception as exc:  # noqa: BLE001
            res = {"filas": [], "errores": [str(exc)]}

# --- Tabla base: lluvia/vegetación (GEE) + amenaza y eventos (SGC) ---------
if res["filas"]:
    df = pd.DataFrame(res["filas"])
else:
    df = pd.DataFrame([
        {"codigo": f["properties"]["codigo"], "nombre": f["properties"]["nombre"],
         "area_km2": f["properties"]["area_km2"]}
        for f in geojson_municipios()["features"]])
for col in ("lluvia_7d", "lluvia_30d", "pct_normal_30d", "perdida_ha", "perdida_pct"):
    if col not in df:
        df[col] = float("nan")
_am = riesgo.amenaza_municipal().set_index("codigo")
df["alta_muy_alta"] = df["codigo"].map(_am["alta_muy_alta"])
df["eventos"] = df["codigo"].map(riesgo.eventos_por_municipio()).fillna(0).astype(int)
_info = df.set_index("codigo").to_dict("index")

# --- Mapa por municipio + resumen -----------------------------------------
c1, c2 = st.columns([1.4, 1])

_CAPAS = [
    # (nombre de la capa, columna, color mínimo, color máximo, unidad, visible)
    ("Lluvia 30 d (% de la normal)", "pct_normal_30d", (222, 235, 247), (8, 81, 156), "%", True),
    ("Lluvia 30 d (mm)", "lluvia_30d", (229, 245, 249), (0, 109, 44), "mm", False),
    ("Área en amenaza alta y muy alta (%)", "alta_muy_alta", (254, 237, 222), (166, 54, 3), "%", False),
    ("Eventos SIMMA", "eventos", (242, 240, 247), (84, 39, 143), "", False),
    ("Pérdida de vegetación (ha)", "perdida_ha", (254, 227, 145), (102, 37, 6), "ha", False),
]


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(int(x) for x in rgb)


def _mezcla(a, b, t):
    return tuple(a[k] + t * (b[k] - a[k]) for k in range(3))


def _txt(v, unidad):
    if v is None or pd.isna(v):
        return "s/d"
    return f"{v:.0f} {unidad}".strip()


with c1:
    st.markdown("#### Mapa por municipio")
    st.caption(
        "Use el control de capas (esquina superior derecha del mapa) para "
        "encender o apagar cada variable. La división municipal permanece "
        "visible y muestra todos los valores al pasar el cursor.")
    m = mapa_base(zoom=9, basemap="SATELLITE")
    leyendas = []
    for nombre_c, col, c_min, c_max, uni, visible in _CAPAS:
        vals = [d_[col] for d_ in _info.values()
                if d_.get(col) is not None and not pd.isna(d_[col])]
        vmin, vmax = (min(vals), max(vals)) if vals else (0.0, 1.0)
        gj = json.loads(json.dumps(geojson_municipios()))
        for f in gj["features"]:
            v = _info.get(f["properties"]["codigo"], {}).get(col)
            if v is None or pd.isna(v):
                f["properties"]["color"] = "#b0b7bd"
            else:
                t = 0.0 if vmax == vmin else (v - vmin) / (vmax - vmin)
                f["properties"]["color"] = _hex(_mezcla(c_min, c_max, t))
        folium.GeoJson(
            gj, name=nombre_c, show=visible,
            style_function=lambda f: {
                "color": "#ffffff", "weight": 0.5,
                "fillColor": f["properties"]["color"], "fillOpacity": 0.6},
        ).add_to(m)
        leyendas.append(
            f"<div style='display:flex;align-items:center;gap:8px;"
            f"font-size:0.82rem;margin:2px 0'>"
            f"<span style='flex:0 0 250px'>{nombre_c}</span>"
            f"<span>{vmin:.0f}</span>"
            f"<div style='flex:0 0 150px;height:10px;border-radius:5px;"
            f"background:linear-gradient(to right,{_hex(c_min)},{_hex(c_max)})'>"
            f"</div><span>{vmax:.0f} {uni}</span></div>")

    # División municipal (siempre visible) con los valores de cada capa
    gj = json.loads(json.dumps(geojson_municipios()))
    for f in gj["features"]:
        d_ = _info.get(f["properties"]["codigo"], {})
        f["properties"]["lluvia"] = _txt(d_.get("pct_normal_30d"), "% de la normal")
        f["properties"]["lluvia_mm"] = _txt(d_.get("lluvia_30d"), "mm")
        f["properties"]["amenaza"] = _txt(d_.get("alta_muy_alta"), "%")
        f["properties"]["eventos"] = str(int(d_.get("eventos", 0)))
        f["properties"]["perdida"] = _txt(d_.get("perdida_ha"), "ha")
    folium.GeoJson(
        gj, name="División municipal",
        style_function=lambda f: {
            "color": "#ffff00", "weight": 2, "fillColor": "#ffffff",
            "fillOpacity": 0.01},
        tooltip=folium.GeoJsonTooltip(
            fields=["nombre", "lluvia", "lluvia_mm", "amenaza", "eventos",
                    "perdida"],
            aliases=["Municipio", "Lluvia 30 d", "Lluvia 30 d (acumulada)",
                     "Área en amenaza alta y muy alta", "Eventos SIMMA",
                     "Pérdida de vegetación"]),
    ).add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    ajustar_al_municipio(m, margen=0.03)
    m.to_streamlit(height=520)
    st.markdown("".join(leyendas), unsafe_allow_html=True)
    st.caption("Gris: sin dato. Con varias capas activas se superponen; "
               "para leer una gama de colores conviene activar una a la vez.")

with c2:
    st.markdown("#### Resumen")
    st.caption(f"Fecha de corte: {dt.date.today().strftime('%d/%m/%Y')} · "
               f"Unidad de análisis: **{nombre_activo()}**")
    if df["pct_normal_30d"].notna().any():
        i = df["pct_normal_30d"].idxmax()
        st.metric("Mayor lluvia de 30 días frente a la normal",
                  f"{df.loc[i, 'pct_normal_30d']:.0f} %",
                  df.loc[i, "nombre"], delta_color="off")
    j = df["alta_muy_alta"].idxmax()
    st.metric("Mayor área en amenaza alta y muy alta",
              f"{df.loc[j, 'alta_muy_alta']:.0f} %",
              df.loc[j, "nombre"], delta_color="off")
    st.metric("Eventos registrados en el SIMMA", int(df["eventos"].sum()),
              help="Inventario y catálogo del SGC, suma de los 14 municipios.")
    if conectado:
        st.success("Google Earth Engine conectado ✔")
    st.info(
        "Esta página presenta **indicadores**, no niveles de alerta. Las "
        "alertas oficiales corresponden al IDEAM, al SGC y a los "
        "CMGRD/CDGRD.", icon="ℹ️")

st.divider()
st.markdown("#### Módulos del sistema")
mc1, mc2, mc3, mc4 = st.columns(4)
mc1.markdown("**🌧️ Precipitación**<br>Series diarias (IMERG · CHIRPS · ERA5-Land), "
             "mapas de lluvia acumulada y climatología de 20 años.",
             unsafe_allow_html=True)
mc2.markdown("**🛰️ Imágenes satelitales**<br>Sentinel-2, Landsat 8/9 y "
             "Sentinel-1 (radar), en color real, falso color y SAR.",
             unsafe_allow_html=True)
mc3.markdown("**🌿 Índices de vegetación**<br>NDVI, NDMI, BSI y detección de "
             "cambios (ΔNDVI) asociados a movimientos en masa.",
             unsafe_allow_html=True)
mc4.markdown("**⛰️ Amenaza y eventos**<br>Pendiente, susceptibilidad y "
             "amenaza del SGC y eventos históricos del SIMMA.",
             unsafe_allow_html=True)
st.caption("Use el menú de la barra lateral para abrir cada módulo.")

st.divider()

# --------------------------------------------------------------------------
# Comparativo de los 14 municipios
# --------------------------------------------------------------------------
st.markdown("#### Comparativo entre municipios")
st.caption(
    "Lluvia acumulada (IMERG, media sobre el polígono), su relación con la "
    "normal, amenaza del SGC, eventos del SIMMA y pérdida severa de vegetación "
    "(ΔNDVI < −0,20 sobre zonas con NDVI > 0,4; Sentinel-2, últimos 60 días "
    "frente a hace 6–12 meses). Se actualiza cada día."
)
for e in res["errores"]:
    st.warning(f"No fue posible calcular una parte del comparativo. {e}")

tabla = df.rename(columns={
    "nombre": "Municipio",
    "area_km2": "Área (km²)",
    "lluvia_7d": "Lluvia 7 días (mm)", "lluvia_30d": "Lluvia 30 días (mm)",
    "pct_normal_30d": "Lluvia 30 d (% de la normal)",
    "alta_muy_alta": "Amenaza alta y muy alta (% área)",
    "eventos": "Eventos SIMMA",
    "perdida_ha": "Pérdida de vegetación (ha)",
    "perdida_pct": "% del área municipal",
})[["Municipio", "Lluvia 7 días (mm)",
    "Lluvia 30 días (mm)", "Lluvia 30 d (% de la normal)",
    "Amenaza alta y muy alta (% área)", "Eventos SIMMA",
    "Pérdida de vegetación (ha)", "% del área municipal", "Área (km²)"]]
orden = st.radio(
    "Ordenar por", ["Municipio", "Lluvia 30 d (% de la normal)",
                    "Amenaza alta y muy alta (% área)", "Eventos SIMMA",
                    "Pérdida de vegetación (ha)"],
    horizontal=True,
)
tabla = tabla.sort_values(orden, ascending=(orden == "Municipio"),
                          na_position="last")
st.dataframe(
    tabla, hide_index=True, use_container_width=True,
    column_config={
        "Área (km²)": st.column_config.NumberColumn(format="%.1f"),
        "Lluvia 7 días (mm)": st.column_config.NumberColumn(format="%.0f"),
        "Lluvia 30 días (mm)": st.column_config.NumberColumn(format="%.0f"),
        "Lluvia 30 d (% de la normal)": st.column_config.NumberColumn(format="%.0f"),
        "Amenaza alta y muy alta (% área)": st.column_config.NumberColumn(format="%.0f"),
        "Pérdida de vegetación (ha)": st.column_config.NumberColumn(format="%.0f"),
        "% del área municipal": st.column_config.NumberColumn(format="%.2f"),
    },
)
st.download_button(
    "Descargar tabla (CSV)",
    tabla.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"comparativo_risaralda_{dt.date.today().isoformat()}.csv",
    mime="text/csv",
)
st.caption(
    "Los valores son indicativos: IMERG tiene píxeles de ~11 km, por lo que en "
    "municipios pequeños (La Virginia, Dosquebradas) la lluvia refleja el campo "
    "regional. La amenaza proviene del Mapa Nacional del SGC (2015, escala "
    "1:100.000) y los eventos del SIMMA (descarga del "
    f"{riesgo.fecha_corte_sgc()}). La pérdida de vegetación debe verificarse "
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
)

pie_institucional()
