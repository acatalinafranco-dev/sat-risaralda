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

st.set_page_config(page_title="Sectores semanales · SAT Risaralda", layout="wide",
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


with st.expander("Cómo se calcula y qué tan confiable es", expanded=False):
    st.markdown(f"""
- **Unidad:** {M['unidad']}.
- **Terreno:** {', '.join(M['variables']['terreno']).lower()}.
- **Lluvia:** {', '.join(M['variables']['lluvia']).lower()}.
- **Evidencia complementaria:** {'; '.join(M['variables']['evidencia_complementaria']).lower()}.
- **Entrenamiento:** {M['entrenamiento']}
- **Validación** (bloques espaciales de 5 km, mes a mes; sin el mes del sismo):
  marcando el 10 % de los sectores con mayor calificación se habría señalado el
  **{_c(V['captura_top10_sin_sismo'], 0)} %** de los eventos que luego visitó la
  coordinación (AUC {_c(V['auc_sin_sismo'], 2)}). Con solo el terreno: {_c(V['solo_terreno']['captura_top10_sin_sismo'], 0)} %.
  Con el umbral de seguimiento se marca en promedio el {_c(V['umbral_seguimiento']['area_media_pct'])} %
  del departamento ({_c(V['umbral_seguimiento']['area_min_pct'])} % en meses secos y hasta
  {_c(V['umbral_seguimiento']['area_max_pct'])} % en los más lluviosos).
- {V['aporte_cambio']}
- **Límites:** {' '.join(M['limites'])}
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
fg = folium.FeatureGroup(name="Sectores", show=True)
for _, s in df.head(1500).iterrows():
    expo = s["exposicion"] or "sin edificaciones ni vías cercanas identificadas"
    html = (f"<b>{s['nivel']}</b><br>{sec.TEXTO}<br><br>"
            f"Susceptibilidad: {s['susceptibilidad']}<br>"
            f"Lluvia 30 días: {s['lluvia_30d_mm']:.0f} mm (anomalía {s['anomalia_lluvia']:.2f})<br>"
            f"Máx. 7 días: {s['lluvia_max7d_mm']:.0f} mm<br>"
            f"Cambio de cobertura: {s['cambio_cobertura_pct']:.1f} % del sector "
            f"(imagen válida {s['imagen_optica_valida_pct']:.0f} %)<br>"
            f"Cambio en radar: {s['cambio_radar_pct']:.1f} %<br>"
            f"Expuestos: {expo}<br>{s['lat']:.4f}, {s['lon']:.4f}")
    folium.Rectangle([[s["lat"] - d, s["lon"] - d], [s["lat"] + d, s["lon"] + d]],
                     color=sec.COLOR_NIVEL[s["nivel"]],
                     weight=2 if s["evidencia_cambio"] else 1,
                     fill=True, fill_opacity=0.55,
                     popup=folium.Popup(html, max_width=300),
                     tooltip=f"{s['nivel']}").add_to(fg)
fg.add_to(m)
folium.LayerControl(collapsed=True).add_to(m)
st_folium(m, height=560, use_container_width=True, returned_objects=[])
st.caption("Rojo: seguimiento prioritario · Naranja: seguimiento. Borde grueso: hay cambio "
           "de cobertura o en radar dentro del sector.")

st.markdown("### Sectores para seguimiento")
if df.empty:
    st.info("Esta semana no hay sectores que superen el umbral de seguimiento.")
else:
    from src.gee_session import geojson_municipios as _gm
    nom = {f["properties"]["codigo"]: f["properties"]["nombre"] for f in _gm()["features"]}
    tab = df.assign(municipio=df["codigo"].map(nom))[
        ["municipio", "nivel", "lat", "lon", "susceptibilidad", "lluvia_30d_mm",
         "lluvia_max7d_mm", "anomalia_lluvia", "cambio_cobertura_pct", "cambio_radar_pct",
         "exposicion"]].rename(columns={
            "municipio": "Municipio", "nivel": "Nivel", "lat": "Latitud", "lon": "Longitud",
            "susceptibilidad": "Susceptibilidad", "lluvia_30d_mm": "Lluvia 30 d (mm)",
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
