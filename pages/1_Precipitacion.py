"""Página: Precipitación · series, mapas interpolados y climatología.

Dashboard automático (sin botón): al cargar calcula en vivo desde GEE la
precipitación media sobre el polígono seleccionado (Risaralda o un municipio) con IMERG, CHIRPS y
ERA5-Land, más la climatología CHIRPS de 20 años. Resultados en caché.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import gee_precipitacion as gp
from src.gee_session import es_departamento
from src.ui import (cache_mun, COLOR_FUENTE, MESES_ES, NOMBRE_FUENTE, agregar_contorno,
                    agregar_municipios, ajustar_al_municipio, conectar_gee,
                    encabezado, leyenda_continua, mapa_base, pie_institucional)


def _limites(mapa) -> None:
    """Contorno de la unidad activa; con Risaralda, la división municipal."""
    if es_departamento():
        agregar_municipios(mapa)
    else:
        agregar_contorno(mapa)

st.set_page_config(page_title="Precipitación · SAT Risaralda", layout="wide",
                   page_icon="🌧️", initial_sidebar_state="expanded")

encabezado(
    "🌧️ Precipitación · {mun}",
    "Lluvia media sobre el **polígono seleccionado**, calculada en vivo desde "
    "Google Earth Engine con **IMERG (NASA)**, **CHIRPS (UCSB)** y "
    "**ERA5-Land (ECMWF)**.",
)

if not conectar_gee():
    st.stop()


# --------------------------------------------------------------------------
# Cachés (GEE en vivo es costoso)
# --------------------------------------------------------------------------
# Nota: las excepciones NO se cachean (st.cache_data solo guarda éxitos),
# así un error transitorio de permisos/red no queda pegado una hora.
#
# Frescura de datos: el parámetro `fecha_consulta` (hoy) forma parte de la
# clave del caché. Garantiza que una consulta hecha otro día SIEMPRE
# recalcule con los datos más recientes disponibles, mientras el caché
# intradía (TTL) evita recalcular en cada interacción y protege la cuota GEE.
HOY = dt.date.today().isoformat()


@cache_mun(ttl=3600)
def _serie(fuente: str, dias: int, fecha_consulta: str):
    return gp.serie_diaria(fuente, dias)


@cache_mun(ttl=3600)
def _mapa(fuente: str, dias: int, fecha_consulta: str):
    return gp.mapa_acumulado(fuente, dias)


@cache_mun(ttl=3600)
def _grilla(fuente: str, modo: str, fecha_consulta: str):
    return gp.grilla_acumulados(fuente, modo)


@cache_mun(ttl=86400)
def _clim(anios: int, fecha_consulta: str):
    return gp.climatologia_chirps(anios)


@cache_mun(ttl=86400)
def _mapa_clim(anios: int, fecha_consulta: str):
    return gp.mapa_media_anual_chirps(anios)


def _seguro(fn, *args):
    """Ejecuta una función cacheada devolviendo {'__error__': ...} si falla."""
    try:
        return fn(*args)
    except Exception as exc:
        return {"__error__": str(exc)}


# --------------------------------------------------------------------------
# 1) Series comparadas
# --------------------------------------------------------------------------
VENTANAS = {"Última semana": 7, "Último mes": 30,
            "Últimos 6 meses": 180, "Último año": 365}

ventana = st.radio("Ventana de análisis", list(VENTANAS.keys()),
                   index=1, horizontal=True)
dias = VENTANAS[ventana]

if dias >= 180:
    st.caption(
        "⏳ Ventanas largas con IMERG suman miles de imágenes de 30 min: la "
        "primera carga puede tardar 1–2 minutos. Después queda en caché (1 h)."
    )

fuentes = ["imerg", "chirps", "era5"]
datos = {}
with st.spinner(f"Calculando precipitación de {ventana.lower()} (IMERG · CHIRPS · ERA5)..."):
    for f in fuentes:
        datos[f] = _seguro(_serie, f, dias, HOY)

errores = {f: d["__error__"] for f, d in datos.items() if d.get("__error__")}
validas = {f: d for f, d in datos.items() if not d.get("__error__") and d.get("serie")}

for f, e in errores.items():
    st.warning(f"**{NOMBRE_FUENTE[f]}** no disponible: {e}")

if not validas:
    st.error("Ninguna fuente respondió. Verifique la conexión con Earth Engine.")
    st.stop()

st.markdown("### Resumen del período")
cols = st.columns(len(validas))
for col, (f, d) in zip(cols, validas.items()):
    col.metric(
        NOMBRE_FUENTE[f],
        f"{d['acumulado_mm']:,.0f} mm",
        help=(f"Acumulado en {d['n_dias']} días · media {d['media_diaria_mm']:.1f} "
              f"mm/día · latencia ~{d['latencia_dias']} días"),
    )

st.markdown("### Serie diaria comparada")
fig = go.Figure()
for f, d in validas.items():
    df = pd.DataFrame(d["serie"])
    df["fecha"] = pd.to_datetime(df["fecha"])
    fig.add_trace(go.Scatter(
        x=df["fecha"], y=df["mm"], name=NOMBRE_FUENTE[f], mode="lines",
        line=dict(color=COLOR_FUENTE[f], width=1.6),
    ))
fig.update_layout(
    height=380, hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    xaxis_title="Fecha", yaxis_title="Precipitación (mm/día)",
    margin=dict(t=30, b=40, l=50, r=20),
)
st.plotly_chart(fig, use_container_width=True)
st.caption(
    "Diferencias entre fuentes son normales (resolución, algoritmo y latencia "
    "distintos). El dato más reciente de cada curva depende de su latencia: "
    "IMERG ~2 días, ERA5 ~6 días, CHIRPS ~2-3 semanas."
)
st.info(
    "**ERA5-Land en zona andina:** tiende a sobreestimar la lluvia "
    "orográfica casi a diario. Úselo para patrones temporales; para valores "
    "absolutos prefiera CHIRPS e IMERG.",
    icon="⛰️",
)

st.markdown("### Acumulado semanal por fuente")
figw = go.Figure()
for f, d in validas.items():
    dfw = pd.DataFrame(d["serie"])
    dfw["fecha"] = pd.to_datetime(dfw["fecha"])
    semanal = (dfw.set_index("fecha")["mm"]
               .resample("W-MON", label="left", closed="left").sum())
    etiquetas_w = [f"{t.day} {MESES_ES[t.month - 1]}" +
                   (f" {t.year}" if dias > 180 else "")
                   for t in semanal.index]
    figw.add_trace(go.Bar(
        x=etiquetas_w, y=semanal.values.round(1), name=NOMBRE_FUENTE[f],
        marker_color=COLOR_FUENTE[f],
    ))
figw.update_layout(
    barmode="group", height=360,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    xaxis_title="Semana (inicia lunes)",
    yaxis_title="Precipitación acumulada (mm/semana)",
    margin=dict(t=30, b=40, l=50, r=20),
)
st.plotly_chart(figw, use_container_width=True)
st.caption(
    "Suma semanal (semanas calendario lunes-domingo) de la serie diaria. La "
    "primera y última semana pueden estar incompletas. Semanas consecutivas "
    "muy lluviosas saturan el suelo: es el precursor típico de movimientos "
    "en masa en zonas de ladera."
)

st.markdown("### Acumulado mensual por fuente")
figm = go.Figure()
for f, d in validas.items():
    dfm = pd.DataFrame(d["serie"])
    dfm["fecha"] = pd.to_datetime(dfm["fecha"])
    mensual = dfm.set_index("fecha")["mm"].resample("MS").sum()
    etiquetas = [f"{MESES_ES[t.month - 1]} {t.year}" for t in mensual.index]
    figm.add_trace(go.Bar(
        x=etiquetas, y=mensual.values.round(0), name=NOMBRE_FUENTE[f],
        marker_color=COLOR_FUENTE[f],
    ))
figm.update_layout(
    barmode="group", height=360,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    xaxis_title="Mes", yaxis_title="Precipitación acumulada (mm/mes)",
    margin=dict(t=30, b=40, l=50, r=20),
)
st.plotly_chart(figm, use_container_width=True)
st.caption(
    "Suma mensual de la serie diaria de la ventana seleccionada. El primer y "
    "último mes pueden estar incompletos (borde de la ventana y latencia de "
    "cada fuente); compare meses completos entre sí."
)

# --------------------------------------------------------------------------
# 2) Mapa interpolado de lluvia acumulada
# --------------------------------------------------------------------------
st.divider()
st.markdown("### Mapas de lluvia acumulada por período")
st.caption(
    "Grilla de 8 submapas con **escala de color común** (comparables entre "
    "sí). IMERG y ERA5 tienen píxeles de ~11 km, CHIRPS de ~5.5 km: el campo "
    "se interpola bilinealmente sobre un buffer de 15 km alrededor del "
    "polígono. Los períodos terminan en la última fecha con datos de la "
    "fuente (según su latencia); los meses son calendario completos."
)

cm1, cm2 = st.columns(2)
with cm1:
    fuente_mapa = st.selectbox(
        "Fuente", ["imerg", "chirps", "era5"],
        format_func=lambda f: NOMBRE_FUENTE[f],
    )
with cm2:
    modo_label = st.selectbox(
        "Períodos", ["Últimos 8 días", "Últimas 8 semanas", "Últimos 8 meses"],
        index=0,
    )
MODOS = {"Últimos 8 días": "dias", "Últimas 8 semanas": "semanas",
         "Últimos 8 meses": "meses"}
modo = MODOS[modo_label]

if fuente_mapa == "imerg" and modo == "meses":
    st.caption("⏳ Los meses recientes de IMERG (sin producto mensual aún) se "
               "reconstruyen desde imágenes de 30 min: esos submapas pueden "
               "tardar en pintar al hacer zoom.")

with st.spinner(f"Generando {modo_label.lower()} · {NOMBRE_FUENTE[fuente_mapa]}..."):
    grilla = _seguro(_grilla, fuente_mapa, modo, HOY)

if grilla.get("__error__"):
    st.warning(f"No fue posible generar la grilla: {grilla['__error__']}")
else:
    UNID = {"dias": "mm/día", "semanas": "mm/semana", "meses": "mm/mes"}[modo]
    periodos = grilla["periodos"]
    for fila in range(0, len(periodos), 4):
        cols = st.columns(4)
        for col, pdef in zip(cols, periodos[fila:fila + 4]):
            with col:
                m = mapa_base(zoom=11, basemap="Esri.WorldImagery")
                m.add_tile_layer(
                    pdef["tiles_url"],
                    name=pdef["etiqueta"],
                    attribution="GEE",
                    opacity=1.0,
                )
                _limites(m)
                ajustar_al_municipio(m, margen=0.015)
                m.to_streamlit(height=260)
                media_txt = (f"{pdef['media_mm']:.0f} mm" if pdef["media_mm"]
                             is not None else "s/d")
                st.markdown(
                    f"<div style='text-align:center; margin-top:-0.6rem;'>"
                    f"<b>{pdef['etiqueta']}</b> · media zonal: {media_txt}</div>",
                    unsafe_allow_html=True,
                )
    st.write("")
    leyenda_continua(
        f"Acumulado por submapa · {NOMBRE_FUENTE[fuente_mapa]}",
        grilla["vis"], UNID,
    )

# --------------------------------------------------------------------------
# 3) Climatología CHIRPS 20 años
# --------------------------------------------------------------------------
st.divider()
st.markdown("### Climatología CHIRPS · promedio de los últimos 20 años")

with st.expander("📖 Guía: climatología de la precipitación (CHIRPS)", expanded=True):
    g1, g2, g3, g4 = st.tabs(["Definición", "Utilidad y aplicaciones",
                              "Interpretación", "Limitaciones"])
    with g1:
        st.markdown(
            """
**Definición.** La climatología de la precipitación describe el comportamiento
promedio de la lluvia en un lugar: cuánto llueve en cada mes y en el año
completo. Constituye la referencia de condiciones normales frente a la cual se
evalúa la lluvia reciente.

**Fuente y periodo.** Los valores provienen de CHIRPS (*Climate Hazards Group
InfraRed Precipitation with Station data*), producto de la Universidad de
California en Santa Bárbara que combina estimaciones satelitales con datos de
estaciones en tierra, disponible desde 1981. La aplicación promedia los
**últimos 20 años** para cada mes y para el año completo.

**Contenido de esta sección.**

- **Gráfico de barras:** precipitación promedio mensual, en milímetros, de la
  unidad de análisis seleccionada.
- **Precipitación media anual:** acumulado promedio de un año completo.
- **Mapa de media anual:** distribución espacial de esa precipitación. Los tonos
  más oscuros corresponden a mayor precipitación.
"""
        )
    with g2:
        st.markdown(
            """
1. **Evaluación de la lluvia reciente.** La aplicación compara la precipitación
   de los últimos 30 días (IMERG) con el promedio CHIRPS de los mismos días. El
   resultado se presenta como **«% de la normal»** en la página de inicio, en el
   comparativo municipal y en las fichas municipales. Un valor de 150 % indica
   que la precipitación equivale a una vez y media la esperada para esa época.
2. **Identificación de temporadas.** El gráfico mensual permite reconocer los
   meses de mayor y menor precipitación y orientar el seguimiento de laderas,
   las visitas de campo y las jornadas de prevención con las comunidades.
3. **Caracterización territorial.** El mapa permite reconocer las zonas del
   departamento con mayor precipitación histórica y priorizar en ellas el
   seguimiento.
4. **Contextualización de eventos.** Ante un movimiento en masa, permite
   verificar si la precipitación del periodo fue excepcional o se ubicó dentro de
   lo habitual, como insumo para informes técnicos y para los consejos de gestión
   del riesgo.
5. **Planificación.** Los promedios mensuales y anuales sustentan con
   información la programación de actividades de conocimiento y reducción del
   riesgo.

**Usuarios previstos:** funcionarios de la CARDER, consejos municipales y
departamental de gestión del riesgo (CMGRD y CDGRD) y demás entidades que
requieran caracterizar el régimen de lluvias.
"""
        )
    with g3:
        st.markdown(
            """
- **Gráfico mensual.** Las barras más altas corresponden a los meses de mayor
  precipitación promedio y las más bajas, a los meses más secos. Se recomienda
  identificar cuántas temporadas lluviosas se presentan en el año; en la región
  andina colombiana suelen ser dos, aspecto que debe verificarse en el gráfico
  de cada municipio.
- **Cifra anual.** Corresponde al promedio del polígono seleccionado. Al cambiar
  el municipio en la barra lateral se aprecian las diferencias entre municipios.
- **Mapa.** No representa la lluvia de la semana, sino la precipitación promedio
  de un año.
- **Nombre de los municipios.** Con «Todo Risaralda» seleccionado, al ubicar el
  puntero sobre un municipio se muestran su nombre y su área.
- **Lectura conjunta con las secciones anteriores.** Las series y los mapas
  diarios muestran la precipitación reciente; esta sección muestra la
  precipitación habitual. La comparación de ambas permite establecer si la lluvia
  reciente es alta o baja respecto de lo esperado.
"""
        )
    with g4:
        st.markdown(
            """
- **No constituye una predicción ni una alerta.** Describe el comportamiento
  promedio observado, no lo que ocurrirá.
- **Estimación satelital.** CHIRPS tiene celdas de aproximadamente 5 km. Describe
  adecuadamente el patrón regional, pero no la lluvia puntual de una vereda o un
  sitio específico.
- **Periodo de referencia.** Veinte años es un periodo menor a los 30 años que
  la Organización Meteorológica Mundial establece para las normales climáticas.
  Las normales oficiales son calculadas y publicadas por el IDEAM a partir de
  estaciones. Los valores de esta sección son **indicativos** y no las sustituyen.
- **Años extremos.** Los años con fenómeno de El Niño o La Niña de alta
  intensidad pueden modificar el promedio de 20 años; la climatología no los
  discrimina.
- Herramienta de apoyo al conocimiento del riesgo: no sustituye las alertas
  oficiales del IDEAM ni las decisiones de los consejos de gestión del riesgo.
"""
        )

cc1, cc2 = st.columns(2)

with cc1:
    with st.spinner("Calculando climatología mensual (20 años CHIRPS)..."):
        clim = _seguro(_clim, 20, HOY)
    if clim.get("__error__"):
        st.warning(f"Climatología no disponible: {clim['__error__']}")
    else:
        dfc = pd.DataFrame(clim["climatologia"])
        dfc["Mes"] = dfc["mes"].map(lambda m: MESES_ES[m - 1])
        fig_c = go.Figure(go.Bar(
            x=dfc["Mes"], y=dfc["mm"], marker_color="#f57c00",
            text=dfc["mm"].round(0), textposition="outside",
        ))
        fig_c.update_layout(height=360, yaxis_title="mm/mes (promedio)",
                            title=f"Promedio mensual {clim['periodo']}",
                            margin=dict(t=40, b=40, l=50, r=20))
        st.plotly_chart(fig_c, use_container_width=True)
        st.metric("Precipitación media anual (polígono seleccionado)",
                  f"{clim['anual_mm']:,.0f} mm/año")
        st.caption(
            "Los meses de mayor lluvia promedio son las épocas en que conviene "
            "reforzar el seguimiento de las laderas. La lluvia alta aumenta la "
            "probabilidad de movimientos en masa, pero no los determina por sí sola."
        )

with cc2:
    with st.spinner("Generando mapa de media anual (20 años)..."):
        mclim = _seguro(_mapa_clim, 20, HOY)
    if mclim.get("__error__"):
        st.warning(f"Mapa climatológico no disponible: {mclim['__error__']}")
    else:
        m2 = mapa_base(zoom=10, basemap="Esri.WorldImagery")
        m2.add_tile_layer(
            mclim["tiles_url"],
            name=f"CHIRPS media anual {mclim['periodo']}",
            attribution="Google Earth Engine",
            opacity=1.0,
        )
        _limites(m2)
        ajustar_al_municipio(m2, margen=0.04)
        m2.to_streamlit(height=430)
        leyenda_continua(f"Media anual {mclim['periodo']}", mclim["vis"], "mm/año")

st.divider()
st.caption(
    "Media zonal sobre el polígono seleccionado DIVIPOLA. Fuentes: NASA GPM IMERG "
    "V07 · UCSB CHIRPS Daily/Pentad · ECMWF ERA5-Land. Próxima iteración: "
    "integración de estaciones IDEAM (red terrestre)."
)

pie_institucional()
