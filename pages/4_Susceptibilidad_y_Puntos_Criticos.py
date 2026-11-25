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
                    etiquetas_municipios,
                    pie_institucional)

st.set_page_config(page_title="Propensión del terreno y sitios conocidos · Monitoreo satelital Risaralda",
                   layout="wide", page_icon="🧭", initial_sidebar_state="expanded")

encabezado(
    "🧭 Propensión del terreno y sitios conocidos · {mun}",
    "Mapa de la **propensión del terreno** a movimientos en masa (modelo propio) y "
    "**sitios donde ya se registraron movimientos en masa**. Es información de "
    "referencia, que no cambia cada semana; el seguimiento semanal está en "
    "«Sectores de la semana».",
)

if not sus.disponible():
    st.warning("Los productos del modelo aún no están cargados en la aplicación.")
    pie_institucional()
    st.stop()

m_meta = sus.meta()
val = m_meta["validacion"]


def _p(x: float) -> str:
    return f"{x:.0f}".replace(".", ",")


with st.expander("¿Cómo leer esta página?", expanded=False):
    st.markdown(f"""
**Propensión del terreno.** Indica qué tan favorable es el terreno para que ocurra un
movimiento en masa, según un modelo estadístico propio que relaciona los lugares donde ya
ocurrieron movimientos en masa con la pendiente, el relieve, el drenaje, los suelos, la
cobertura, la cercanía a vías y la lluvia histórica. Se presenta en cinco clases, de
muy baja a muy alta. No es la susceptibilidad oficial: para esa, consulte la capa del
Servicio Geológico Colombiano en «Amenaza SGC e inventario de eventos».

**Sitios conocidos.** Son lugares donde se registró un movimiento en masa. El **color**
indica el nivel de atención y la **forma**, si el registro es anterior o posterior al
sismo del 10 de agosto de 2026.

**Nivel de atención de cada sitio.** Cada sitio recibe una calificación de 0 a 100 que
suma cuatro aspectos:

| Aspecto | Peso | De dónde sale |
|---|---|---|
| Propensión del terreno en el sitio | 35 % | Modelo propio |
| Prioridad asignada en campo | 25 % | Calificación del evaluador: crítica, alta, media o baja |
| Elementos expuestos | 25 % | Viviendas, personas, vías y equipamientos registrados |
| Actividad del movimiento | 15 % | Estado y tendencia registrados en campo |

- **Seguimiento prioritario:** 65 puntos o más, o cuando el evaluador lo calificó en
  campo con prioridad crítica o alta.
- **Seguimiento:** entre 45 y 64 puntos.
- **Vigilancia:** menos de 45 puntos.

**Actividad del movimiento.** Se toma del estado (activo, en evolución, reactivado,
potencialmente inestable o inactivo) y de la tendencia (rápida, moderada o lenta)
anotados en el formulario de campo de 2026. Los registros anteriores no tienen ese dato;
en ellos este aspecto vale cero.

**¿Qué tan confiable es el mapa?** Se probó dividiendo el departamento en cuadros de
5 km: cada cuadro se evaluó con un modelo que no había visto sus datos. El
**{_p(val['pct_eventos_alta'])} %** de los movimientos en masa registrados cayó en las
clases alta y muy alta, que ocupan solo el **{_p(val['pct_area_alta'])} %** del
departamento: en una quinta parte del territorio están siete de cada diez eventos.
""")

codigo = codigo_activo()
pts = sus.puntos(codigo)
res = sus.resumen_municipio(codigo)

k1, k2, k3 = st.columns(3)
k1.metric("Sitios con movimiento en masa registrado", res["n_sitios"])
k2.metric("En seguimiento prioritario", res["por_nivel"]["Seguimiento prioritario"])
k3.metric("Área con propensión alta y muy alta", f"{res['alta_muy_alta']:.0f} %")

# --------------------------------------------------------------------------
# Mapa
# --------------------------------------------------------------------------
st.markdown("### Mapa de propensión del terreno y sitios conocidos")
c1, c2, c3 = st.columns([1, 1.4, 1])
opac = c1.slider("Opacidad de la propensión", 0.0, 1.0, 0.9, 0.05)
niveles = c2.multiselect("Niveles a mostrar", sus.NIVELES, default=sus.NIVELES)
calor = c3.toggle("Mapa de calor de sitios", value=False,
                  help="Muestra dónde se concentran los sitios registrados, ponderados por "
                       "su nivel de atención.")

(la0, lo0), (la1, lo1) = bounds_municipio()
m = folium.Map(location=[(la0 + la1) / 2, (lo0 + lo1) / 2], zoom_start=10, tiles=None,
               control_scale=True)
folium.TileLayer(ESRI_IMAGERY_URL, attr=ESRI_IMAGERY_ATTR, name="Imagen satelital Esri",
                 max_zoom=19).add_to(m)
folium.TileLayer("OpenStreetMap", name="OpenStreetMap", show=False).add_to(m)
folium.raster_layers.ImageOverlay(
    image="data:image/png;base64," + base64.b64encode(sus.png_overlay()).decode(),
    bounds=sus.limites_png(), opacity=opac, name="Propensión del terreno (modelo)",
    interactive=False, zindex=400).add_to(m)
gj = geojson_municipios() if es_departamento() else geojson_municipio()
folium.GeoJson(gj, name="Límite municipal",
               style_function=lambda f: {"color": "#ffffff", "weight": 1.6,
                                         "fill": False}).add_to(m)

FORMA = {"Antes del sismo": "circulo", "Nuevo después del sismo": "triangulo",
         "Existente, revisado después del sismo": "rombo",
         "Después del sismo, sin dato del antecedente": "cuadrado"}


def _svg(forma: str, color: str, t: int, op: float = 0.8) -> str:
    """Símbolo SVG sin borde blanco (relleno = nivel; forma = momento del registro)."""
    b = f'fill-opacity="{op}" stroke="#222" stroke-width="0.6" stroke-opacity="0.7"'
    if forma == "triangulo":
        g = f'<polygon points="{t/2},1 {t-1},{t-1} 1,{t-1}" fill="{color}" {b}/>'
    elif forma == "rombo":
        g = f'<polygon points="{t/2},1 {t-1},{t/2} {t/2},{t-1} 1,{t/2}" fill="{color}" {b}/>'
    elif forma == "cuadrado":
        g = f'<rect x="1.5" y="1.5" width="{t-3}" height="{t-3}" fill="{color}" {b}/>'
    else:
        g = f'<circle cx="{t/2}" cy="{t/2}" r="{t/2-1}" fill="{color}" {b}/>'
    return f'<svg width="{t}" height="{t}" viewBox="0 0 {t} {t}">{g}</svg>'


vis = pts[pts["nivel"].isin(niveles)]
if calor and len(vis):
    from folium.plugins import HeatMap
    peso = vis["nivel"].map({sus.NIVELES[0]: 1.0, sus.NIVELES[1]: 0.6, sus.NIVELES[2]: 0.3})
    HeatMap(list(zip(vis["lat"], vis["lon"], peso)), name="Mapa de calor de sitios",
            radius=18, blur=22, min_opacity=0.25).add_to(m)
fg = folium.FeatureGroup(name="Sitios con movimiento en masa", show=True)
for i, r in vis.iterrows():
    expo = sus.texto_exposicion(r) or "sin elementos expuestos registrados"
    html = (f"<b>{r['vereda'] or 's/d'}</b> · {r['municipio']}<br>"
            f"<b>{r['nivel']}</b> (calificación {r['indice']})<br>"
            f"Propensión del terreno: {r['clase']}<br>Expuestos: {expo}<br>"
            f"Tipo: {r['tipo'] or 's/d'} · Estado: {r['estado'] or 's/d'}<br>"
            f"Último registro: {r['fecha_ultima']:%d/%m/%Y}<br>"
            f"Registro: {r.get('momento') or 's/d'}<br>{r['lat']:.4f}, {r['lon']:.4f}")
    t = 11 if r["nivel"] == sus.NIVELES[0] else 9
    folium.Marker(
        [r["lat"], r["lon"]],
        icon=folium.DivIcon(html=_svg(FORMA.get(r.get("momento"), "circulo"),
                                      sus.COLOR_NIVEL[r["nivel"]], t),
                            icon_size=(t, t), icon_anchor=(t // 2, t // 2)),
        popup=folium.Popup(html, max_width=280),
        tooltip=f"{r['vereda'] or 's/d'} · {r['nivel']} · {r.get('momento') or ''}").add_to(fg)
fg.add_to(m)
etiquetas_municipios(m)
folium.LayerControl(collapsed=True).add_to(m)
st_folium(m, height=560, use_container_width=True, key=f"mapa_susc_{codigo}", returned_objects=[],
          center=[(la0 + la1) / 2, (lo0 + lo1) / 2], zoom=9 if es_departamento() else 11)

ley = " ".join(
    f"<span style='display:inline-block;width:14px;height:14px;background:{sus.COLOR_CLASE[k]};"
    f"margin:0 4px -2px 10px;border:1px solid #999'></span>{k}" for k in sus.CLASES)
ley2 = " ".join(
    f"<span style='margin:0 4px -2px 10px'>{_svg('circulo', sus.COLOR_NIVEL[n], 13)}</span>{n}"
    for n in sus.NIVELES)
ley3 = " ".join(
    f"<span style='margin:0 4px -3px 10px'>{_svg(f, '#777777', 13)}</span>{k}"
    for k, f in FORMA.items())
st.markdown(f"<div style='font-size:0.85rem;line-height:1.9'><b>Propensión del terreno:</b>{ley}<br>"
            f"<b>Color del sitio (nivel):</b>{ley2}<br>"
            f"<b>Forma del sitio (registro frente al sismo del 10/08/2026):</b>{ley3}</div>",
            unsafe_allow_html=True)

# --------------------------------------------------------------------------
# Lista de sitios
# --------------------------------------------------------------------------
st.markdown("### Sitios registrados")
tabla = pts[pts["nivel"].isin(niveles)].copy()
tabla["Elementos expuestos"] = tabla.apply(sus.texto_exposicion, axis=1)
tabla = tabla.rename(columns={
    "municipio": "Municipio", "vereda": "Vereda / barrio", "nivel": "Nivel",
    "indice": "Calificación", "clase": "Propensión del terreno", "tipo": "Tipo",
    "estado": "Estado", "prioridad_campo": "Prioridad de campo",
    "fecha_ultima": "Último registro", "lat": "Latitud", "lon": "Longitud"})
cols = ["Municipio", "Vereda / barrio", "Nivel", "Calificación", "Propensión del terreno",
        "Elementos expuestos", "Tipo", "Estado", "Prioridad de campo",
        "Último registro", "Latitud", "Longitud"]
if not es_departamento():
    cols.remove("Municipio")
st.dataframe(tabla[cols], hide_index=True, use_container_width=True, height=380,
             column_config={"Último registro": st.column_config.DateColumn(format="DD/MM/YYYY"),
                            "Calificación": st.column_config.ProgressColumn(
                                min_value=0, max_value=100, format="%d")})
d1, d2, _ = st.columns([1, 1, 2])
d1.download_button(
    "Descargar la lista (Excel)",
    itv.excel_bytes({"Sitios": tabla[cols]}, [
        "Sitios con movimiento en masa registrado y su nivel de atención.",
        "Calificación de 0 a 100: propensión del terreno (35 %), prioridad de campo (25 %), "
        "elementos expuestos (25 %) y actividad del movimiento (15 %).",
        "Reporte informativo: no constituye una alerta."]),
    file_name=f"sitios_criticos_{nombre_activo().lower().replace(' ', '_')}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# --------------------------------------------------------------------------
# Validación y comparación
# --------------------------------------------------------------------------
st.markdown("### ¿Qué tan confiable es el mapa de propensión?")
v1, v2 = st.columns([1.15, 1])
with v1:
    cl = list(reversed(sus.CLASES))
    fig = go.Figure()
    fig.add_bar(y=cl, x=[val["pct_area_por_clase"][c] for c in cl], orientation="h",
                name="% del departamento", marker_color="#b0b7bf",
                text=[f"{val['pct_area_por_clase'][c]:.0f} %" for c in cl], textposition="outside")
    fig.add_bar(y=cl, x=[val["pct_eventos_por_clase"][c] for c in cl], orientation="h",
                name="% de los movimientos en masa", marker_color="#c0392b",
                text=[f"{val['pct_eventos_por_clase'][c]:.0f} %" for c in cl], textposition="outside")
    fig.update_layout(barmode="group", height=360, margin=dict(l=0, r=30, t=40, b=0),
                      title="Área de cada clase frente a los movimientos en masa que cayeron en ella",
                      xaxis_title="%", legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig, use_container_width=True)
with v2:
    st.markdown(f"""
Si el mapa no sirviera, cada clase tendría la misma proporción de área y de eventos.
En cambio:

- La clase **muy alta** ocupa el **{_p(val['pct_area_por_clase']['Muy alta'])} %** del
  departamento y contiene el **{_p(val['pct_eventos_por_clase']['Muy alta'])} %** de los
  movimientos en masa registrados.
- La clase **muy baja** ocupa el **{_p(val['pct_area_por_clase']['Muy baja'])} %** y
  contiene solo el **{_p(val['pct_eventos_por_clase']['Muy baja'])} %**.

La prueba se hizo con cuadros de 5 km que el modelo no había visto.

**Diferencia con el mapa del SGC.** El Servicio Geológico Colombiano zonifica la amenaza
física regional y es la referencia oficial. Este modelo aprende de los movimientos en
masa registrados, que se concentran cerca de vías y zonas pobladas; por eso marca más
esas zonas. Son complementarios.

**Límite principal.** A escala de predio no distingue un terreno con movimiento de su
vecino sin movimiento; para eso se requiere la visita técnica.
""")

st.info("Para el reporte informativo en PDF de cada municipio, use la página "
        "**Reporte municipal**.")
pie_institucional()
