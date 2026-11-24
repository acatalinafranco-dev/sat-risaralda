"""Inicio: «Esta semana». Resumen gráfico para la toma de decisiones."""
from __future__ import annotations

import datetime as dt

import folium
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

from src import monitoreo as mon
from src import sectores as sec
from src import susceptibilidad as sus
from src.gee_session import (bounds_municipio, codigo_activo, es_departamento,
                             geojson_municipio, geojson_municipios, nombre_activo)
from src.ui import (ESRI_IMAGERY_ATTR, ESRI_IMAGERY_URL, GRADIENTE, VERDE_CARDER,
                    NOMBRE_APP, conectar_gee, encabezado, pie_institucional)

st.markdown(
    f"<h1 style='color:{VERDE_CARDER}; font-size:2.1rem; line-height:1.2; "
    f"margin:0 0 6px 0; padding:0;'>{NOMBRE_APP}</h1>",
    unsafe_allow_html=True,
)

encabezado(
    "🗓️ Esta semana · {mun}",
    "Reporte informativo: resumen para decidir **dónde hacer seguimiento**: cuánto ha llovido, qué sectores "
    "reúnen condiciones que favorecen movimientos en masa y qué sitios conocidos "
    "requieren atención.",
)

if not conectar_gee():
    pie_institucional()
    st.stop()

HOY = dt.date.today()
COD = codigo_activo()
U = sus.meta().get("umbral_lluvia") or {"acum7_mm": 63, "acum30_mm": 257}


def _c(x, d=0):
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _lluvia(codigo: str, fecha: str) -> dict:
    return mon.lluvia_municipio(codigo, fecha)


with st.spinner("Preparando el resumen de la semana (la primera consulta del día tarda 1 a 2 minutos)..."):
    errores = []
    try:
        ll = _lluvia(COD, HOY.isoformat())
    except Exception as exc:  # noqa: BLE001
        ll, _ = None, errores.append(f"lluvia: {exc}")
    try:
        cal = sec.calificar_semana(HOY.isoformat())
        df = sec.sectores(cal, COD)
        rs = sec.resumen(cal, COD)
    except Exception as exc:  # noqa: BLE001
        cal, df, rs = None, pd.DataFrame(), None
        errores.append(f"sectores: {exc}")

pts = sus.puntos(COD)
try:  # sitios conocidos con cambio satelital real esta semana (máximo 20 por municipio)
    prio = sec.sitios_semana(HOY.isoformat(), COD)
except Exception as exc:  # noqa: BLE001
    prio = pts.iloc[0:0]
    errores.append(f"cambios en sitios conocidos: {exc}")
a7 = (ll or {}).get("acum7")
a30 = (ll or {}).get("acum30")
pct = (ll or {}).get("pct_ref")

# --------------------------------------------------------------------------
# 1. Lectura en una frase
# --------------------------------------------------------------------------
supera = a7 is not None and a7 >= U["acum7_mm"]
alta = pct is not None and pct >= 115
if supera:
    color, icono, titulo = "#e67e22", "🟠", "Reforzar el seguimiento"
    razon = (f"la lluvia de los últimos 7 días ({_c(a7)} mm) supera el umbral de referencia "
             f"de {U['acum7_mm']} mm, calibrado con los eventos del departamento")
elif alta:
    color, icono, titulo = "#f1c40f", "🟡", "Atención al seguimiento"
    razon = (f"la lluvia de los últimos 30 días está por encima de lo habitual "
             f"({pct} % del promedio)")
else:
    color, icono, titulo = "#27ae60", "🟢", "Seguimiento habitual"
    razon = ("la lluvia está dentro de lo habitual para la época"
             + (f" ({_c(a7)} mm en 7 días; {pct} % del promedio de 30 días)" if a7 is not None and pct is not None else ""))

_ambito = "del departamento" if COD == "66" else "del municipio"
frase = (f"En **{nombre_activo()}** {razon}. "
         + (f"Esta semana, **{_c(rs['n_sectores'])} de los {_c(rs.get('n_total', 0))} sectores** "
            f"de 300 m {_ambito} ({_c(rs['pct_area'], 1)} %) quedaron para seguimiento "
            f"por terreno y lluvia"
            + (f"; **{_c(rs['n_prioritarios'])}** de ellos en seguimiento prioritario. "
               if rs["n_prioritarios"] else ". ") if rs else "")
         + (f"Aparte, de los **{_c(len(pts))} sitios** con movimientos en masa ya registrados, "
            f"**{_c(len(prio))}** muestran cambios en el terreno detectados por satélite esta semana."
            if len(prio) else
            f"De los **{_c(len(pts))} sitios** con movimientos en masa ya registrados, ninguno "
            "muestra cambios en el terreno detectados por satélite esta semana."))
st.markdown(
    f"""<div style="border-left:10px solid {color}; background:#fafafa; padding:14px 18px;
    border-radius:8px; margin-bottom:10px;">
    <div style="font-size:1.35rem; font-weight:700;">{icono} {titulo}</div>
    <div style="font-size:0.85rem; color:#555;">Nivel de seguimiento sugerido para la semana
    que termina el {HOY:%d/%m/%Y}</div></div>""",
    unsafe_allow_html=True)
st.markdown(frase)

# --------------------------------------------------------------------------
# 2. Cuatro indicadores visuales
# --------------------------------------------------------------------------


def _tarjeta(col, icono, valor, titulo, detalle, color, avance=None):
    barra = ""
    if avance is not None:
        p = max(0, min(100, avance))
        barra = (f"<div style='background:#e9ecef;border-radius:6px;height:9px;margin-top:8px;'>"
                 f"<div style='width:{p:.0f}%;background:{color};height:9px;border-radius:6px;'>"
                 f"</div></div>")
    col.markdown(
        f"""<div style="background:#ffffff;border:1px solid #e6e6e6;border-top:6px solid {color};
        border-radius:10px;padding:12px 14px;height:100%;">
        <div style="font-size:1.6rem;">{icono}</div>
        <div style="font-size:2rem;font-weight:700;line-height:1.1;">{valor}</div>
        <div style="font-weight:600;margin-top:2px;">{titulo}</div>
        <div style="font-size:0.8rem;color:#666;margin-top:4px;">{detalle}</div>{barra}</div>""",
        unsafe_allow_html=True)


k = st.columns(4)
c7 = "#e67e22" if (a7 or 0) >= U["acum7_mm"] else "#1e88e5"
_tarjeta(k[0], "🌧️", f"{_c(a7)} mm" if a7 is not None else "s/d", "Lluvia últimos 7 días",
         f"Umbral de referencia: {U['acum7_mm']} mm. La barra muestra qué tan cerca está.",
         c7, 100 * (a7 or 0) / U["acum7_mm"])
c30 = "#e67e22" if (pct or 0) >= 115 else "#1e88e5"
_tarjeta(k[1], "📅", f"{pct} %" if pct is not None else "s/d", "Lluvia 30 días frente a lo habitual",
         f"{_c(a30)} mm acumulados. 100 % = promedio de 20 años para estas fechas.",
         c30, (pct or 0) / 2)
_tarjeta(k[2], "🗺️", rs["n_sectores"] if rs else "s/d", "Sectores para seguimiento",
         (f"{rs['n_prioritarios']} prioritarios · {_c(rs['pct_area'], 1)} % del territorio · "
          f"{rs['n_con_cambio']} con cambio en la cobertura" if rs else ""),
         "#c0392b", (rs["pct_area"] * 5) if rs else None)
_tarjeta(k[3], "📍", len(prio), "Sitios conocidos con cambio esta semana",
         f"De {len(pts)} sitios registrados; se muestran como máximo 20 por municipio, solo "
         f"donde el satélite detecta cambio. {int((prio['viviendas'] > 0).sum())} con viviendas.",
         "#8e44ad")

for e in errores:
    st.warning(f"No fue posible calcular {e}")

st.markdown("")

# --------------------------------------------------------------------------
# 3. Mapa + qué hacer
# --------------------------------------------------------------------------
cm, cd = st.columns([3, 2])
with cm:
    st.markdown("#### 🗺️ Mapa de seguimiento")
    (la0, lo0), (la1, lo1) = bounds_municipio()
    m = folium.Map(location=[(la0 + la1) / 2, (lo0 + lo1) / 2], zoom_start=10 if not es_departamento() else 9,
                   tiles=None, control_scale=True)
    folium.TileLayer(ESRI_IMAGERY_URL, attr=ESRI_IMAGERY_ATTR, name="Imagen satelital",
                     max_zoom=19).add_to(m)
    gj = geojson_municipios() if es_departamento() else geojson_municipio()
    folium.GeoJson(gj, name="Municipios", style_function=lambda f: {
        "color": "#ffffff", "weight": 1.5, "fill": False},
        tooltip=folium.GeoJsonTooltip(["nombre"], labels=False) if es_departamento() else None).add_to(m)
    # Sitios conocidos primero, para que queden debajo de los sectores
    for _, r in prio.iterrows():
        folium.CircleMarker([r["lat"], r["lon"]], radius=3, color="white", weight=0.8,
                            fill=True, fill_color="#8e44ad", fill_opacity=1,
                            tooltip=f"Sitio conocido con cambio · {r['vereda'] or r['municipio']} · "
                                    f"{sus.texto_exposicion(r) or 'sin expuestos registrados'}"
                            ).add_to(m)
    d = 0.00135
    for _, s in df.head(900 if es_departamento() else 600).iterrows():
        folium.Rectangle([[s["lat"] - d, s["lon"] - d], [s["lat"] + d, s["lon"] + d]],
                         color=sec.COLOR_NIVEL[s["nivel"]], weight=2 if s["evidencia_cambio"] else 0.5,
                         fill=True, fill_opacity=0.6,
                         tooltip=f"{s['nivel']} · {s['exposicion'] or 'sin expuestos identificados'}"
                         ).add_to(m)
    st_folium(m, height=470, use_container_width=True, returned_objects=[])
    st.markdown(
        "<span style='color:#c0392b'>■</span> Sector de seguimiento prioritario &nbsp; "
        "<span style='color:#e67e22'>■</span> Sector de seguimiento &nbsp; "
        "<b>▢</b> borde grueso = cambio en la cobertura &nbsp; "
        "<span style='color:#8e44ad'>●</span> Sitio conocido con cambio esta semana",
        unsafe_allow_html=True)

with cd:
    st.markdown("#### ✅ ¿Qué hacer?")
    pasos = [
        ("1", "Revisar los sectores en rojo", "Empezar por los que tienen viviendas o vías "
         "cerca. En el detalle está el listado con coordenadas."),
        ("2", "Verificar los sitios conocidos con cambio", "De acuerdo con la información secundaria, en estos sitios "
         "se presentan condiciones favorables que evidencian un posible movimiento en masa, por lo que se "
         "recomienda realizar una verificación del lugar."),
        ("3", "Registrar lo encontrado", "Realizar las acciones correspondientes."),
    ]
    for n, t, x in pasos:
        st.markdown(
            f"""<div style="display:flex;gap:10px;margin-bottom:8px;">
            <div style="min-width:30px;height:30px;border-radius:50%;background:{VERDE_CARDER};
            color:white;font-weight:700;display:flex;align-items:center;justify-content:center;">{n}</div>
            <div><b>{t}</b><br><span style="font-size:0.85rem;color:#555;">{x}</span></div></div>""",
            unsafe_allow_html=True)

    if rs and len(df):
        if es_departamento():
            nom = {f["properties"]["codigo"]: f["properties"]["nombre"]
                   for f in geojson_municipios()["features"]}
            g = (df.assign(m=df["codigo"].map(nom)).groupby(["m", "nivel"]).size()
                 .unstack(fill_value=0).reindex(columns=sec.NIVELES, fill_value=0))
            g = g.loc[g.sum(axis=1).sort_values().index]
            titulo_g = "Sectores por municipio"
        else:
            g = (df.groupby(["susceptibilidad", "nivel"]).size().unstack(fill_value=0)
                 .reindex(columns=sec.NIVELES, fill_value=0))
            g = g.reindex([c for c in sus.CLASES if c in g.index])
            titulo_g = "Sectores según propensión del terreno"
        fig = go.Figure()
        for n in sec.NIVELES[::-1]:
            fig.add_bar(y=g.index, x=g[n], orientation="h", name=n,
                        marker_color=sec.COLOR_NIVEL[n])
        fig.update_layout(barmode="stack", height=120 + 24 * len(g), margin=dict(l=0, r=10, t=30, b=0),
                          yaxis=dict(type="category", dtick=1), xaxis_title="Número de sectores",
                          title=dict(text=titulo_g, font=dict(size=14)),
                          legend=dict(orientation="h", y=-0.15), plot_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True)

# --------------------------------------------------------------------------
# 4. Lluvia: gráfica explicada
# --------------------------------------------------------------------------
st.markdown("#### 🌧️ ¿Cuánto ha llovido?")
if ll and ll.get("serie"):
    s = pd.DataFrame(ll["serie_completa"])
    s["fecha"] = pd.to_datetime(s["fecha"])
    s["a7"] = s["mm"].rolling(7, min_periods=1).sum()
    s = s.tail(60)
    fig = go.Figure()
    fig.add_bar(x=s["fecha"], y=s["mm"], name="Lluvia del día (mm)", marker_color="#90caf9")
    fig.add_scatter(x=s["fecha"], y=s["a7"], name="Acumulado de 7 días (mm)",
                    line=dict(color="#1565c0", width=3))
    fig.add_hline(y=U["acum7_mm"], line_dash="dash", line_color="#e67e22",
                  annotation_text=f"Umbral de referencia 7 días: {U['acum7_mm']} mm",
                  annotation_position="top right", annotation_bgcolor="white")
    fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0), plot_bgcolor="white",
                      legend=dict(orientation="h", y=1.12), yaxis_title="mm",
                      xaxis=dict(tickformat="%d/%m"))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Lluvia estimada por satélite (NASA GPM IMERG), promedio sobre "
               f"{nombre_activo()}. Cuando la línea azul cruza la línea naranja, la lluvia de "
               "la última semana es similar a la que antecedió a la mitad de los movimientos en "
               "masa registrados por la coordinación departamental (umbral preliminar).")
else:
    st.info("Sin datos de lluvia disponibles en este momento.")

# --------------------------------------------------------------------------
# 5. ¿Cómo se construye este resumen?
# --------------------------------------------------------------------------
st.markdown("#### 🧩 Cómo se construye este resumen")
cajas = [
    ("⛰️", "Terreno", "Pendiente (clases IGAC), relieve, geología y fallas del SGC, y la "
     "propensión del terreno según el modelo propio."),
    ("🌧️", "Lluvia", "Acumulado de 7 y 30 días y su diferencia con lo habitual, medido "
     "por satélite cada día."),
    ("🛰️", "Cambios", "Pérdida de vegetación y suelo expuesto (Sentinel-2) y cambios "
     "persistentes en radar (Sentinel-1)."),
    ("📋", "Resultado", "Sectores de 300 m y sitios conocidos para verificar en campo, con "
     "elementos expuestos."),
]
html = "<div style='display:flex;gap:6px;align-items:stretch;flex-wrap:wrap;'>"
for i, (ic, t, x) in enumerate(cajas):
    html += (f"<div style='flex:1;min-width:160px;background:#f4f8f4;border-radius:10px;"
             f"padding:10px 12px;'><div style='font-size:1.5rem'>{ic}</div><b>{t}</b><br>"
             f"<span style='font-size:0.82rem;color:#555'>{x}</span></div>")
    if i < len(cajas) - 1:
        html += "<div style='align-self:center;font-size:1.4rem;color:#999;'>➜</div>"
html += "</div>"
st.markdown(html, unsafe_allow_html=True)
st.markdown(f"<hr style='border:none;height:3px;margin:18px 0 8px 0;background:{GRADIENTE};'>",
            unsafe_allow_html=True)

st.markdown("#### Ir al detalle")
l1, l2, l3, l4 = st.columns(4)
l1.page_link("secciones/movimientos.py", label="Movimientos en masa", icon="⛰️")
l2.page_link("secciones/lluvia_satelite.py", label="Lluvia y satélite", icon="🌧️")
l3.page_link("secciones/consultar.py", label="Consultar un lugar", icon="📍")
l4.page_link("secciones/reportes.py", label="Reporte PDF y método", icon="📄")

pie_institucional()
