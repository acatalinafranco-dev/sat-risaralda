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

with st.expander("📖 Guía: qué es el radar SAR y cómo leer esta página", expanded=True):
    t1, t2, t3, t4 = st.tabs(["¿Qué es?", "Cómo se calcula", "Cómo leer el mapa",
                              "Límites y buen uso"])
    with t1:
        st.markdown(
            """
**El satélite.** Sentinel-1 es una misión de la Agencia Espacial Europea
(programa Copernicus). Lleva un **radar de apertura sintética (SAR)** en
**banda C** (longitud de onda cercana a 5,6 cm). A diferencia de una cámara,
el radar **emite su propia señal de microondas** y mide la parte que el
terreno le devuelve. Esa señal devuelta se llama **retrodispersión**.

**Por qué sirve en Risaralda.** Las microondas **atraviesan nubes y lluvia** y
funcionan **de día y de noche**. En una zona con nubosidad casi permanente, el
radar entrega datos utilizables en fechas en que las imágenes ópticas
(Sentinel-2, Landsat) quedan cubiertas.

**Qué mide.** La retrodispersión depende de la **rugosidad** de la superficie,
de su **humedad**, de su **estructura** (vegetación, suelo desnudo, agua) y de
la **inclinación** del terreno respecto al satélite. Se expresa en
**decibeles (dB)**: un valor más alto significa más señal devuelta.

**Polarización VV.** El radar emite y recibe en orientación vertical. Es la
polarización con mejor respuesta a la rugosidad del suelo y la más usada para
detectar cambios del terreno.

**Frecuencia de paso.** Sentinel-1 revisita la misma zona cada 12 días. Por
eso la ventana reciente debe cubrir al menos un paso.
"""
        )
    with t2:
        st.markdown(
            """
1. **Selección de imágenes.** Se toman las pasadas Sentinel-1 de la ventana
   **reciente** y de la ventana de **referencia** anterior, siempre de la
   **misma dirección de órbita** (ascendente o descendente) y de la
   **misma trayectoria**. Así el ángulo con que el satélite mira la ladera es
   idéntico y las diferencias no se deben a la geometría.
2. **Mediana por ventana.** Cada ventana se resume con la mediana de sus
   imágenes, que reduce el ruido propio del radar (moteado) y los valores
   atípicos.
3. **Suavizado de 30 m.** Se aplica un filtro de mediana de 30 m de radio
   para estabilizar el resultado.
4. **Cambio (dB).** Se resta la referencia a la ventana reciente:
   *cambio = reciente − referencia*. Si hay varias trayectorias, se promedian
   los cambios.
5. **Marca de cambio fuerte en ladera.** Se señalan los píxeles donde el
   cambio supera el **umbral** (en valor absoluto) **y** la pendiente del
   terreno (modelo NASADEM) alcanza el mínimo elegido. Se excluyen así las
   zonas planas, donde el cambio suele deberse a cultivos o agua.
"""
        )
    with t3:
        st.markdown(
            """
**Capa «Cambio de retrodispersión (dB)»**

| Color | Significado |
|---|---|
| Azul | El terreno devuelve **menos** señal que en la referencia (disminución). |
| Blanco o gris | Sin cambio relevante. |
| Naranja | El terreno devuelve **más** señal que en la referencia (aumento). |

**Capa «Cambio fuerte en ladera» (magenta).** Marca los píxeles con cambio
superior al umbral sobre pendientes del mínimo elegido o mayores. Son **zonas
para verificar**, no eventos confirmados.

**Indicadores superiores**

- **Área con cambio fuerte en ladera:** hectáreas marcadas en magenta dentro
  de la unidad seleccionada.
- **Porcentaje del área:** esa superficie sobre el área total de la unidad.
- **Imágenes recientes / referencia:** número de pasadas usadas en cada
  ventana. Con pocas imágenes el resultado es menos estable.
- **Órbita:** dirección de la órbita usada y fechas de las imágenes recientes.

**Qué puede explicar un cambio.** El sentido del cambio (azul o naranja) no
identifica por sí solo la causa. Entre las posibles: remoción de suelo o
vegetación por un movimiento en masa, tala o cosecha, cambios de humedad del
suelo por lluvias recientes, crecimiento de cultivos y presencia de agua.
"""
        )
    with t4:
        st.markdown(
            """
- **No confirma movimientos en masa.** Prioriza laderas para contrastar con
  la sección *Catálogo de imágenes* (óptico), los eventos del SIMMA y la
  verificación en campo.
- **Distorsiones de ladera.** En pendientes muy inclinadas frente al satélite
  la imagen de radar se deforma (acortamiento, inversión y sombra). Por eso
  se compara siempre la misma órbita; aun así, pueden aparecer artefactos.
- **El umbral no está calibrado para Risaralda.** El valor de 3 dB es una
  referencia general. Un umbral menor detecta más zonas pero genera más
  falsos positivos; uno mayor es más restrictivo.
- **Resolución.** El procesamiento trabaja con celdas de unos 30 m. No
  detecta movimientos pequeños ni cambios menores a esa escala.
- **Lluvia reciente.** La humedad del suelo aumenta la retrodispersión. Una
  ventana reciente muy lluviosa frente a una referencia seca puede mostrar
  aumentos generalizados que no son movimientos en masa.
- **Uso sugerido.** (1) Revise el porcentaje por municipio al final de la
  página. (2) Active los eventos del SIMMA. (3) Contraste las zonas
  magenta con una imagen Sentinel-2 reciente. (4) Programe verificación en
  campo donde coincidan.
"""
        )

if not conectar_gee():
    st.stop()

c1, c2, c3, c4 = st.columns(4)
with c1:
    dias_rec = st.selectbox(
        "Ventana reciente", [12, 24, 36], index=1,
        format_func=lambda d: f"últimos {d} días",
        help="Periodo que se evalúa. Sentinel-1 pasa cada 12 días: 24 días "
             "incluyen unas dos pasadas y dan un resultado más estable; 12 "
             "días muestran solo lo más reciente, con más ruido.")
with c2:
    dias_ref = st.selectbox(
        "Referencia anterior", [60, 90, 180], index=1,
        format_func=lambda d: f"{d} días previos",
        help="Periodo anterior a la ventana reciente contra el cual se "
             "compara. Una referencia más larga es más estable; una más "
             "corta se parece más a las condiciones actuales de humedad.")
with c3:
    umbral = st.slider(
        "Umbral de cambio (dB)", 2.0, 6.0, 3.0, 0.5,
        help="Cambio mínimo, en decibeles, para marcar un píxel. Menor "
             "umbral: más zonas marcadas y más falsos positivos. Mayor "
             "umbral: solo cambios muy fuertes. El valor de 3 dB es "
             "referencial y no está calibrado para Risaralda.")
with c4:
    pend_min = st.slider(
        "Pendiente mínima (°)", 5, 30, 15, 5,
        help="Solo se marcan píxeles con esta pendiente o mayor, según el "
             "modelo de elevación NASADEM. Excluye terreno plano, donde el "
             "cambio suele deberse a cultivos o agua.")
ver_ev = st.checkbox(
    "Mostrar eventos del SIMMA", value=False,
    help="Dibuja sobre el mapa los movimientos en masa registrados por el "
         "Servicio Geológico Colombiano (inventario y catálogo), para ver si "
         "las zonas marcadas coinciden con eventos previos.")


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
k1.metric("Área con cambio fuerte en ladera", f"{r['ha_total']:,.0f} ha".replace(",", "."),
          help="Hectáreas marcadas en magenta: cambio de retrodispersión "
               "superior al umbral sobre pendientes del mínimo elegido o "
               "mayores. Son zonas por verificar, no eventos confirmados.")
k2.metric("Porcentaje del área", f"{r['pct']:.1f} %",
          help="Superficie marcada sobre el área total de la unidad "
               "seleccionada (departamento o municipio).")
k3.metric("Imágenes recientes / referencia",
          f"{r['n_reciente']} / {r['n_referencia']}",
          help="Número de pasadas Sentinel-1 usadas en la ventana reciente y "
               "en la de referencia. Con pocas imágenes, el resultado es "
               "menos estable.")
k4.metric("Órbita", r["orbita"],
          f"{r['fecha_ini']} a {r['fecha_fin']}", delta_color="off",
          help="Dirección de la órbita usada (ascendente o descendente) y "
               "fechas de las imágenes recientes. Se compara siempre la "
               "misma órbita para que la geometría de observación sea igual.")

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
