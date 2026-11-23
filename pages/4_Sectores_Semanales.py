"""Página: reporte semanal de sectores de 300 m con condiciones que favorecen
movimientos en masa (terreno + lluvia, con evidencia satelital de cambio)."""
from __future__ import annotations

import datetime as dt
import io
import sys
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import sectores as sec
from src.gee_session import (bounds_municipio, codigo_activo, es_departamento,
                             geojson_municipio, geojson_municipios, nombre_activo)
from src.ui import (ESRI_IMAGERY_ATTR, ESRI_IMAGERY_URL, conectar_gee, encabezado,
                    pie_institucional)

st.set_page_config(page_title="Sectores semanales · Monitoreo satelital Risaralda", layout="wide",
                   page_icon="🗺️", initial_sidebar_state="expanded")

encabezado(
    "🗺️ Sectores con cambios en la semana · {mun}",
    "Sectores de **300 m** donde, según el terreno y la lluvia de los últimos 30 días, "
    "conviene **hacer seguimiento y verificar cambios en el terreno**. Es un **reporte "
    "informativo**; no es una alerta.",
)

if not sec.disponible():
    st.warning("Los productos del modelo de sectores aún no están cargados en la aplicación.")
    pie_institucional()
    st.stop()

M = sec.meta()
V = M["validacion"]


def _c(x, d=1):
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


with st.expander("¿Cómo se calcula?", expanded=False):
    st.markdown(f"""
**Unidad de análisis.** El departamento se divide en 39.510 cuadros de 300 m × 300 m
(9 hectáreas), llamados sectores.

**Qué se evalúa en cada sector**
- **Terreno** (no cambia de una semana a otra): propensión del terreno según el modelo
  propio, pendiente media, proporción del sector con pendiente escarpada, relieve, edad
  de las rocas y distancia a fallas geológicas (Servicio Geológico Colombiano, 1:100.000).
  La pendiente se expresa en las clases del IGAC.
- **Lluvia** (cambia cada semana): lluvia acumulada en los últimos 30 días, lluvia
  máxima en un día, lluvia máxima en 7 días seguidos y diferencia frente al promedio
  2001–2020 de ese mes (satélite IMERG de la NASA).

Con esas variables, un modelo estadístico (bosque aleatorio) asigna a cada sector una
calificación. Los sectores con calificación alta quedan en **seguimiento** y los más
altos, en **seguimiento prioritario**.

**Evidencia satelital complementaria** (no cambia la calificación; ayuda a ubicar
dónde mirar dentro del sector)
- **Pérdida de vegetación con suelo expuesto** (Sentinel-2): se comparan los últimos
  12 días con los 30 anteriores y los últimos 30 días con los 90 anteriores.
- **Cambio persistente en radar** (Sentinel-1): se comparan solo imágenes de la misma
  órbita; los últimos 12 días frente a los 30, 60 y 90 días anteriores. Se marca
  cambio solo si aparece en las tres comparaciones.

**¿Qué tan bien funciona?** Se probó con los movimientos en masa registrados entre
enero de 2024 y agosto de 2026, sin contar el mes del sismo. Para cada mes se
calcularon los sectores y se revisó si el lugar del evento había quedado marcado.
Para evitar que el modelo «hiciera trampa», cada zona se evaluó con un modelo que no
había visto datos de esa zona.

- Marcando en promedio el **{_c(V['umbral_seguimiento']['area_media_pct'])} %** del
  departamento, **{_c(V['umbral_seguimiento']['captura_sin_sismo_pct'], 0)} de cada 100
  eventos** cayeron en un sector marcado.
- Si solo se usara el terreno, sin la lluvia, el resultado sería menor: la lluvia
  mejora la detección en unos 10 eventos de cada 100.
- El área marcada cambia con la lluvia: cerca del {_c(V['umbral_seguimiento']['area_min_pct'])} %
  en meses secos y hasta el {_c(V['umbral_seguimiento']['area_max_pct'])} % en los más lluviosos.
""")

hoy = dt.date.today()
c1, c2 = st.columns([1, 3])
fecha = c1.date_input("Semana que termina el", value=hoy, max_value=hoy,
                      min_value=dt.date(2024, 1, 1), format="DD/MM/YYYY")
ini, fin = fecha - dt.timedelta(days=6), fecha
c2.markdown(f"<br>Lluvia de los 30 días previos al **{fecha:%d/%m/%Y}**; cambio de "
            "cobertura frente a los 90 días anteriores.", unsafe_allow_html=True)

if not conectar_gee():
    pie_institucional()
    st.stop()


with st.spinner("Calculando la calificación semanal de sectores (1 a 2 minutos la primera vez)..."):
    try:
        cal = sec.calificar_semana(fecha.isoformat())
    except Exception as exc:  # noqa: BLE001
        st.error(f"No fue posible calcular los sectores: {exc}")
        pie_institucional()
        st.stop()

codigo = codigo_activo()
df = sec.sectores(cal, codigo)
r = sec.resumen(cal, codigo)
if not df.empty:
    with st.spinner("Ubicando el punto de verificación dentro de cada sector..."):
        df = sec.agregar_puntos(df, cal["fecha"])

k1, k2, k3, k4 = st.columns(4)
k1.metric("Sectores para seguimiento", r["n_sectores"])
k2.metric("Seguimiento prioritario", r["n_prioritarios"])
k3.metric("Área marcada", f"{_c(r['pct_area'])} %")
k4.metric("Con cambio de cobertura o radar", r["n_con_cambio"])

(la0, lo0), (la1, lo1) = bounds_municipio()
m = folium.Map(location=[(la0 + la1) / 2, (lo0 + lo1) / 2], zoom_start=10, tiles=None,
               control_scale=True)
folium.TileLayer(ESRI_IMAGERY_URL, attr=ESRI_IMAGERY_ATTR, name="Imagen satelital Esri",
                 max_zoom=19).add_to(m)
folium.TileLayer("OpenStreetMap", name="OpenStreetMap", show=False).add_to(m)
gj = geojson_municipios() if es_departamento() else geojson_municipio()
folium.GeoJson(gj, name="Límite municipal",
               style_function=lambda f: {"color": "#ffffff", "weight": 1.6, "fill": False}).add_to(m)
d = 0.00135  # media celda (~150 m) en grados
try:
    folium.TileLayer(sec.capa_cambio_semana(cal["fecha"], codigo),
                     attr="Copernicus Sentinel-1/2 · Google Earth Engine",
                     name="Píxeles con cambio (10 m)", overlay=True, show=True,
                     max_zoom=19).add_to(m)
except Exception:  # noqa: BLE001
    pass
fg = folium.FeatureGroup(name="Sectores", show=True)
fp = folium.FeatureGroup(name="Puntos de verificación", show=True)
for _, s in df.head(1500).iterrows():
    expo = s["exposicion"] or "sin edificaciones ni vías cercanas identificadas"
    html = (f"<b>{s['nivel']}</b><br>{sec.TEXTO}<br><br>"
            f"Propensión del terreno: {s['susceptibilidad']}<br>"
            f"Pendiente media: {s['pendiente_pct']:.0f} % ({s['pendiente_igac']})<br>"
            f"Lluvia 30 días: {s['lluvia_30d_mm']:.0f} mm (anomalía {s['anomalia_lluvia']:.2f})<br>"
            f"Máx. 7 días: {s['lluvia_max7d_mm']:.0f} mm<br>"
            f"Cambio de cobertura: {s['cambio_cobertura_pct']:.1f} % del sector "
            f"(imagen válida {s['imagen_optica_valida_pct']:.0f} %)<br>"
            f"Cambio en radar: {s['cambio_radar_pct']:.1f} %<br>"
            f"Expuestos: {expo}<br><br><b>Punto de verificación:</b> "
            f"{s['pv_lat']:.5f}, {s['pv_lon']:.5f}<br>{s['pv_criterio']}")
    folium.Rectangle([[s["lat"] - d, s["lon"] - d], [s["lat"] + d, s["lon"] + d]],
                     color=sec.COLOR_NIVEL[s["nivel"]],
                     weight=2 if s["evidencia_cambio"] else 1,
                     fill=True, fill_opacity=0.55,
                     popup=folium.Popup(html, max_width=300),
                     tooltip=f"{s['nivel']}").add_to(fg)
    folium.CircleMarker([s["pv_lat"], s["pv_lon"]], radius=3, stroke=False,
                        fill=True, fill_color="#ffd400", fill_opacity=0.6,
                        popup=folium.Popup(html, max_width=300),
                        tooltip=f"Punto de verificación · {s['pv_criterio']}").add_to(fp)
fp.add_to(m)  # los puntos van debajo de los sectores
fg.add_to(m)
folium.LayerControl(collapsed=True).add_to(m)
st_folium(m, height=560, use_container_width=True, returned_objects=[])
_sym = ("display:inline-block;width:13px;height:13px;margin:0 6px 0 14px;"
        "vertical-align:-2px;")
st.markdown(
    "<div style='font-size:0.9rem;line-height:2'>"
    f"<span style='{_sym}background:#c0392b;opacity:.75'></span>Sector en seguimiento prioritario"
    f"<span style='{_sym}background:#e67e22;opacity:.75'></span>Sector en seguimiento"
    f"<span style='{_sym}border-radius:50%;background:#ffd400;opacity:.6'></span>Punto sugerido para verificar"
    "<br>"
    f"<span style='{_sym}background:#ff1f1f'></span>Pérdida de vegetación (Sentinel-2)"
    f"<span style='{_sym}background:#2f6fdf'></span>Cambio persistente en radar (Sentinel-1)"
    f"<span style='{_sym}border:2.5px solid #555;background:none'></span>Borde grueso: el sector tiene cambio"
    "</div>", unsafe_allow_html=True)
st.caption("El punto sugerido está donde el satélite detectó cambio dentro del sector; si no hubo "
           "cambio, en el lugar de mayor pendiente. Los píxeles de cambio se muestran solo "
           "dentro del municipio.")

st.markdown("### Sectores para seguimiento")
if df.empty:
    st.info("Esta semana no hay sectores que superen el umbral de seguimiento.")
else:
    from src.gee_session import geojson_municipios as _gm
    nom = {f["properties"]["codigo"]: f["properties"]["nombre"] for f in _gm()["features"]}
    tab = df.assign(municipio=df["codigo"].map(nom))[
        ["municipio", "nivel", "pv_lat", "pv_lon", "pv_criterio", "lat", "lon", "susceptibilidad",
         "pendiente_pct", "pendiente_igac", "lluvia_30d_mm",
         "lluvia_max7d_mm", "anomalia_lluvia", "cambio_cobertura_pct", "cambio_radar_pct",
         "exposicion"]].rename(columns={
            "municipio": "Municipio", "nivel": "Nivel",
            "pv_lat": "Latitud punto", "pv_lon": "Longitud punto",
            "pv_criterio": "Criterio del punto",
            "lat": "Latitud centro", "lon": "Longitud centro",
            "susceptibilidad": "Propensión del terreno", "pendiente_pct": "Pendiente media (%)",
            "pendiente_igac": "Clase de pendiente (IGAC)", "lluvia_30d_mm": "Lluvia 30 d (mm)",
            "lluvia_max7d_mm": "Máx. 7 d (mm)", "anomalia_lluvia": "Anomalía",
            "cambio_cobertura_pct": "Cambio cobertura (%)", "cambio_radar_pct": "Cambio radar (%)",
            "exposicion": "Elementos expuestos"})
    st.dataframe(tab, use_container_width=True, hide_index=True, height=380)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        tab.assign(Mensaje=sec.TEXTO).to_excel(w, index=False, sheet_name="Sectores")
    st.download_button("Descargar en Excel", buf.getvalue(),
                       file_name=f"sectores_{nombre_activo()}_{fecha:%Y%m%d}.xlsx")

pie_institucional()
