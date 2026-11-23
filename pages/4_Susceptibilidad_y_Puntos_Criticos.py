"""Página: susceptibilidad a movimientos en masa (modelo propio), puntos
críticos y monitoreo satelital de cambios."""
from __future__ import annotations

import base64
import datetime as dt
import sys
from pathlib import Path

import folium
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import interactivo as itv
from src import monitoreo
from src import susceptibilidad as sus
from src.gee_session import (bounds_municipio, codigo_activo, es_departamento,
                             geojson_municipio, geojson_municipios, nombre_activo)
from src.ui import (ESRI_IMAGERY_ATTR, ESRI_IMAGERY_URL, conectar_gee, encabezado,
                    pie_institucional)

st.set_page_config(page_title="Susceptibilidad y puntos críticos · SAT Risaralda",
                   layout="wide", page_icon="🧭", initial_sidebar_state="expanded")

encabezado(
    "🧭 Susceptibilidad y puntos críticos · {mun}",
    "Modelo de **aprendizaje automático** entrenado con las visitas de campo por "
    "movimientos en masa en Risaralda. Muestra **dónde es más probable** un "
    "movimiento en masa que afecte a la población, **qué sitios conviene "
    "seguir** y **qué cambios recientes** detectan los satélites.",
)

if not sus.disponible():
    st.warning("Los productos del modelo aún no están cargados en la aplicación.")
    pie_institucional()
    st.stop()

m_meta = sus.meta()
val = m_meta["validacion"]
auc_txt = f"{val['auc']:.2f}".replace(".", ",")
n_fondo = f"{m_meta['n_fondo']:,}".replace(",", ".")

with st.expander("Cómo leer esta página y de dónde salen los datos", expanded=False):
    st.markdown(f"""
- **Susceptibilidad (modelo):** bosque aleatorio (*Random Forest*) entrenado con
  **{m_meta['n_presencias']} sitios** con movimiento en masa confirmado
  (coordinación departamental de gestión del riesgo, 2017-2026, y formulario
  posterior al sismo de 2026 de CARDER y de las entidades de Pereira),
  **{m_meta['n_ausencias']} sitios visitados sin movimiento** y
  {n_fondo} puntos de fondo. Usa {len(m_meta['variables'])} variables de
  terreno, drenaje, vías, cobertura, lluvia histórica y suelos.
- **Validación:** por bloques espaciales de 5 km (el modelo se evalúa en zonas que
  no vio). AUC **{auc_txt}**. En la validación, el
  {val['pct_eventos_alta']:.0f} % de los eventos cayó en las clases alta y muy alta,
  que ocupan el {val['pct_area_alta']:.0f} % del departamento.
- **Índice de atención (0-100):** susceptibilidad (35 %), prioridad asignada en
  campo (25 %), elementos expuestos (25 %) y actividad del movimiento (15 %).
  **Seguimiento prioritario** ≥ 65 (o prioridad crítica o alta asignada en
  campo) · **Seguimiento** 45-64 · **Vigilancia** < 45. La susceptibilidad del índice
  es la estimada en validación cruzada, para no premiar el ajuste del modelo.
- **Qué no es:** no es una alerta (las alertas hidrometeorológicas las emite el
  IDEAM) ni reemplaza la zonificación del SGC o los estudios del POT. A escala de
  predio no distingue un sitio con movimiento de uno sin movimiento.
""")

codigo = codigo_activo()
pts = sus.puntos(codigo)
res = sus.resumen_municipio(codigo)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Sitios con movimiento confirmado", res["n_sitios"])
k2.metric("En seguimiento prioritario", res["por_nivel"]["Seguimiento prioritario"])
k3.metric("Área con susceptibilidad alta y muy alta", f"{res['alta_muy_alta']:.0f} %")
k4.metric("Desempeño del modelo (AUC espacial)", auc_txt,
          help="Área bajo la curva ROC en validación por bloques espaciales de 5 km. "
               "0,5 = azar; 1 = perfecto. Valores de 0,8 a 0,9 se consideran buenos "
               "para susceptibilidad regional.")

# --------------------------------------------------------------------------
# Mapa
# --------------------------------------------------------------------------
st.markdown("### Mapa de susceptibilidad y sitios críticos")
c1, c2, c3 = st.columns([1, 1, 2])
opac = c1.slider("Opacidad de la susceptibilidad", 0.0, 1.0, 0.65, 0.05)
niveles = c2.multiselect("Niveles a mostrar", sus.NIVELES, default=sus.NIVELES)
ver_cambio = c3.toggle(
    "Mostrar cambios satelitales recientes (modelo de cambio)", value=False,
    disabled=not monitoreo.disponible_cambio(),
    help="Calcula con Google Earth Engine la probabilidad de cambio compatible con "
         "movimiento en masa en los últimos 60 días (Sentinel-1 y Sentinel-2). "
         "La primera consulta del día puede tardar 1 a 2 minutos.")

(la0, lo0), (la1, lo1) = bounds_municipio()
m = folium.Map(location=[(la0 + la1) / 2, (lo0 + lo1) / 2], zoom_start=10, tiles=None,
               control_scale=True)
folium.TileLayer(ESRI_IMAGERY_URL, attr=ESRI_IMAGERY_ATTR, name="Imagen satelital Esri",
                 max_zoom=19).add_to(m)
folium.TileLayer("OpenStreetMap", name="OpenStreetMap", show=False).add_to(m)
folium.raster_layers.ImageOverlay(
    image="data:image/png;base64," + base64.b64encode(sus.png_overlay()).decode(),
    bounds=sus.limites_png(), opacity=opac, name="Susceptibilidad (modelo)",
    interactive=False, zindex=400).add_to(m)
gj = geojson_municipios() if es_departamento() else geojson_municipio()
folium.GeoJson(gj, name="Límite municipal",
               style_function=lambda f: {"color": "#ffffff", "weight": 1.6,
                                         "fill": False}).add_to(m)

cambio = None
if ver_cambio:
    if conectar_gee():
        with st.spinner("Calculando cambios satelitales recientes..."):
            try:
                cambio = monitoreo.cambios_recientes(dt.date.today().isoformat())
            except Exception as exc:  # noqa: BLE001
                st.warning(f"No fue posible calcular el monitoreo de cambios: {exc}")
        if cambio:
            folium.TileLayer(cambio["tiles"], attr="CARDER · Copernicus Sentinel-1/2",
                             name="Probabilidad de cambio (60 días)", overlay=True,
                             opacity=0.85, zindex=450).add_to(m)

FORMA = {"Antes del sismo": "circulo", "Nuevo después del sismo": "triangulo",
         "Existente, revisado después del sismo": "rombo",
         "Después del sismo, sin dato del antecedente": "cuadrado"}


def _svg(forma: str, color: str, t: int) -> str:
    """Símbolo SVG (relleno = nivel de seguimiento; forma = momento del registro)."""
    b = 'stroke="white" stroke-width="1.5"'
    if forma == "triangulo":
        g = f'<polygon points="{t/2},1 {t-1},{t-1} 1,{t-1}" fill="{color}" {b}/>'
    elif forma == "rombo":
        g = f'<polygon points="{t/2},1 {t-1},{t/2} {t/2},{t-1} 1,{t/2}" fill="{color}" {b}/>'
    elif forma == "cuadrado":
        g = f'<rect x="2" y="2" width="{t-4}" height="{t-4}" fill="{color}" {b}/>'
    else:
        g = f'<circle cx="{t/2}" cy="{t/2}" r="{t/2-1.5}" fill="{color}" {b}/>'
    return f'<svg width="{t}" height="{t}" viewBox="0 0 {t} {t}">{g}</svg>'


fg = folium.FeatureGroup(name="Sitios con movimiento en masa", show=True)
for i, r in pts[pts["nivel"].isin(niveles)].iterrows():
    expo = sus.texto_exposicion(r) or "sin elementos expuestos registrados"
    html = (f"<b>{r['vereda'] or 's/d'}</b> · {r['municipio']}<br>"
            f"<b>{r['nivel']}</b> (índice {r['indice']})<br>"
            f"Susceptibilidad: {r['clase']}<br>Expuestos: {expo}<br>"
            f"Tipo: {r['tipo'] or 's/d'} · Estado: {r['estado'] or 's/d'}<br>"
            f"Visitas: {r['n_visitas']} · última {r['fecha_ultima']:%d/%m/%Y}<br>"
            f"Fuente: {r['fuente']}<br>"
            f"Registro: {r.get('momento') or 's/d'}<br>{r['lat']:.4f}, {r['lon']:.4f}")
    t = 16 if r["nivel"] == sus.NIVELES[0] else 12
    folium.Marker(
        [r["lat"], r["lon"]],
        icon=folium.DivIcon(html=_svg(FORMA.get(r.get("momento"), "circulo"),
                                      sus.COLOR_NIVEL[r["nivel"]], t),
                            icon_size=(t, t), icon_anchor=(t // 2, t // 2)),
        popup=folium.Popup(html, max_width=280),
        tooltip=f"{r['vereda'] or 's/d'} · {r['nivel']} · {r.get('momento') or ''}").add_to(fg)
fg.add_to(m)
folium.LayerControl(collapsed=True).add_to(m)
st_folium(m, height=560, use_container_width=True, key="mapa_susc", returned_objects=[],
          center=[(la0 + la1) / 2, (lo0 + lo1) / 2], zoom=9 if es_departamento() else 11)

ley = " ".join(
    f"<span style='display:inline-block;width:14px;height:14px;background:{sus.COLOR_CLASE[k]};"
    f"margin:0 4px -2px 10px;border:1px solid #999'></span>{k}" for k in sus.CLASES)
ley2 = " ".join(
    f"<span style='display:inline-block;width:12px;height:12px;border-radius:50%;"
    f"background:{sus.COLOR_NIVEL[n]};margin:0 4px -1px 10px'></span>{n}" for n in sus.NIVELES)
ley3 = " ".join(
    f"<span style='margin:0 4px -3px 10px'>{_svg(f, '#777777', 14)}</span>{k}"
    for k, f in FORMA.items())
st.markdown(f"<div style='font-size:0.85rem'><b>Susceptibilidad:</b>{ley}<br>"
            f"<b>Sitios (color = nivel):</b>{ley2}<br>"
            f"<b>Sitios (forma = registro frente al sismo del 10/08/2026):</b>{ley3}</div>",
            unsafe_allow_html=True)
if cambio:
    st.caption("Probabilidad de cambio: amarillo (moderada) a magenta (alta). Solo se "
               "muestra donde supera el umbral de detección y la susceptibilidad es "
               "media o mayor.")

# --------------------------------------------------------------------------
# Lista de sitios
# --------------------------------------------------------------------------
st.markdown("### Sitios priorizados")
tabla = pts[pts["nivel"].isin(niveles)].copy()
tabla["Elementos expuestos"] = tabla.apply(sus.texto_exposicion, axis=1)
tabla = tabla.rename(columns={
    "municipio": "Municipio", "vereda": "Vereda / barrio", "nivel": "Nivel",
    "indice": "Índice", "clase": "Susceptibilidad", "tipo": "Tipo",
    "estado": "Estado", "prioridad_campo": "Prioridad de campo",
    "n_visitas": "Visitas", "fecha_ultima": "Última visita", "lat": "Latitud",
    "lon": "Longitud", "fuente": "Fuente"})
cols = ["Municipio", "Vereda / barrio", "Nivel", "Índice", "Susceptibilidad",
        "Elementos expuestos", "Tipo", "Estado", "Prioridad de campo", "Visitas",
        "Última visita", "Latitud", "Longitud", "Fuente"]
if not es_departamento():
    cols.remove("Municipio")
st.dataframe(tabla[cols], hide_index=True, use_container_width=True, height=380,
             column_config={"Última visita": st.column_config.DateColumn(format="DD/MM/YYYY"),
                            "Índice": st.column_config.ProgressColumn(
                                min_value=0, max_value=100, format="%d")})
d1, d2, _ = st.columns([1, 1, 2])
d1.download_button(
    "Descargar la lista (Excel)",
    itv.excel_bytes({"Sitios": tabla[cols]}, [
        "Sitios con movimiento en masa confirmado y su índice de atención.",
        "Fuentes: coordinación departamental de gestión del riesgo (visitas 2017-2026); "
        "CARDER, Secretaría de Infraestructura y DIGER de Pereira (formulario 2026).",
        m_meta["formula_indice"],
        "Reporte informativo: no constituye una alerta."]),
    file_name=f"sitios_criticos_{nombre_activo().lower().replace(' ', '_')}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
zonas = [z for z in (cambio or {}).get("zonas", [])
         if es_departamento() or z.get("codigo") == codigo]
if zonas:
    with d2.popover(f"Zonas con cambio reciente ({len(zonas)})"):
        st.dataframe(pd.DataFrame(zonas).rename(columns={
            "lat": "Latitud", "lon": "Longitud", "prob": "Probabilidad (%)",
            "area_ha": "Área (ha)", "clase": "Susceptibilidad"}).drop(
                columns=["codigo"], errors="ignore"), hide_index=True)

# --------------------------------------------------------------------------
# Validación y comparación
# --------------------------------------------------------------------------
st.markdown("### Validación del modelo")
v1, v2 = st.columns([1.1, 1])
with v1:
    imp = pd.Series(m_meta["importancia"]).sort_values()
    imp = imp[imp > 0].tail(15)
    nombres = m_meta.get("nombres_variables", {})
    fig = go.Figure(go.Bar(x=imp.values, y=[nombres.get(k, k) for k in imp.index],
                           orientation="h", marker_color="#004B87"))
    fig.update_layout(height=420, margin=dict(l=0, r=0, t=30, b=0),
                      title="Variables con mayor peso en el modelo",
                      xaxis_title="Importancia relativa (Gini)")
    st.plotly_chart(fig, use_container_width=True)
with v2:
    comp = pd.DataFrame(m_meta["comparacion"])
    st.dataframe(comp, hide_index=True, use_container_width=True)
    st.caption(m_meta["nota_comparacion"])
    st.markdown("**Límites del modelo**")
    for t in m_meta["limites"]:
        st.markdown(f"- {t}")

st.info("Para el reporte informativo en PDF de cada municipio, use la página "
        "**Reporte municipal**.")
pie_institucional()
