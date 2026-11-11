"""Página: contraste de la lluvia satelital con estaciones del IDEAM."""
from __future__ import annotations

import sys
from pathlib import Path

import folium
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import estaciones as est
from src import gee_estaciones as ge
from src.ui import (VERDE_CARDER, agregar_municipios, conectar_gee, encabezado,
                    mapa_base, pie_institucional)

st.set_page_config(page_title="Estaciones · SAT Risaralda", layout="wide",
                   page_icon="📡", initial_sidebar_state="expanded")

encabezado(
    "📡 Estaciones pluviométricas · Risaralda",
    "Contraste de la lluvia estimada por satélite (**IMERG**) con las "
    "estaciones automáticas del **IDEAM**, en los últimos 30 días.",
)

with st.expander("Cómo leer esta página", expanded=False):
    st.markdown(
        """
- Las **estaciones** miden la lluvia en un punto; el **satélite** la estima
  en celdas de unos 10 km. Por eso no coinciden exactamente: en ladera y con
  lluvia convectiva las diferencias pueden ser grandes.
- Un satélite que **subestima** respecto a la estación implica que el nivel
  de atención del tablero podría ser mayor en esa zona.
- Los datos del IDEAM son **preliminares y sin validar**. Se descartan días
  con más de 200 mm y se marcan como *dudosas* las estaciones con lecturas
  improbables o con datos incompletos; esas **no** entran en el contraste.
- Solo se dispone en datos abiertos de las estaciones **automáticas**. Las
  convencionales y las redes propias de CARDER no están incluidas todavía.
"""
    )

if not conectar_gee():
    st.stop()


@st.cache_data(ttl=3600, show_spinner="Consultando estaciones del IDEAM...")
def _estaciones_v1(fecha: str):
    return est.estaciones(30)


@st.cache_data(ttl=3600, show_spinner="Estimando lluvia satelital en las estaciones...")
def _imerg_v1(fecha: str, puntos: tuple):
    return ge.imerg_en_puntos(list(puntos), 30)


import datetime as dt  # noqa: E402

hoy = dt.date.today().isoformat()
try:
    res = _estaciones_v1(hoy)
except Exception as exc:  # noqa: BLE001
    st.error("No fue posible consultar los datos abiertos del IDEAM "
             f"(datos.gov.co). Intente de nuevo más tarde. Detalle: {exc}")
    st.stop()

filas = res["filas"]
if not filas:
    st.info("No hay estaciones automáticas con datos recientes en Risaralda.")
    st.stop()

try:
    sat = _imerg_v1(hoy, tuple((f["codigo"], f["lon"], f["lat"]) for f in filas))
except Exception as exc:  # noqa: BLE001
    sat = {}
    st.warning(f"No fue posible obtener la lluvia satelital: {exc}")

df = pd.DataFrame(filas)
df["sat_30d"] = df["codigo"].map(sat)
df["dif_pct"] = (df["sat_30d"] - df["mm_30d"]) / df["mm_30d"].where(df["mm_30d"] > 0) * 100
ok = df[df["calidad"] == "Aceptable"].copy()

# KPIs ----------------------------------------------------------------------
k1, k2, k3, k4 = st.columns(4)
k1.metric("Estaciones automáticas", len(df))
k2.metric("Con datos aceptables", len(ok))
k3.metric("Última lectura", res["corte"] or "s/d")
if len(ok) and ok["sat_30d"].notna().any():
    sesgo = (ok["sat_30d"].sum() - ok["mm_30d"].sum()) / ok["mm_30d"].sum() * 100
    k4.metric("Satélite frente a estaciones", f"{sesgo:+.0f} %",
              "total de las estaciones aceptables", delta_color="off")

# Mapa -----------------------------------------------------------------------
st.markdown("### Mapa de estaciones")
m = mapa_base(zoom=10, basemap="Esri.WorldImagery")
agregar_municipios(m)
for r in df.itertuples():
    color = VERDE_CARDER if r.calidad == "Aceptable" else "#9aa5ab"
    sat_txt = f"{r.sat_30d:.0f} mm" if pd.notna(r.sat_30d) else "s/d"
    folium.CircleMarker(
        [r.lat, r.lon], radius=8, color="#ffffff", weight=1.5, fill=True,
        fill_color=color, fill_opacity=0.95,
        tooltip=(f"{r.nombre} ({r.municipio}) · estación 30 d: {r.mm_30d:.0f} mm · "
                 f"satélite: {sat_txt} · calidad: {r.calidad}"),
    ).add_to(m)
la = [r["lat"] for r in filas]
lo = [r["lon"] for r in filas]
m.fit_bounds([[min(la) - 0.08, min(lo) - 0.08], [max(la) + 0.08, max(lo) + 0.08]])
m.to_streamlit(height=460)
st.caption("Verde: calidad aceptable. Gris: dudosa (no se usa en el contraste).")

# Contraste ------------------------------------------------------------------
st.markdown("### Contraste en los últimos 30 días")
if len(ok) and ok["sat_30d"].notna().any():
    fig = go.Figure()
    fig.add_bar(x=ok["nombre"], y=ok["mm_30d"], name="Estación (IDEAM)",
                marker_color=VERDE_CARDER)
    fig.add_bar(x=ok["nombre"], y=ok["sat_30d"], name="Satélite (IMERG)",
                marker_color="#004B87")
    fig.update_layout(barmode="group", height=380, yaxis_title="mm en 30 días",
                      margin=dict(l=0, r=0, t=10, b=0), plot_bgcolor="white",
                      legend=dict(orientation="h", y=-0.25))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Ninguna estación tiene datos aceptables para el contraste.")

tabla = df.assign(
    **{"Estación": df["nombre"], "Municipio": df["municipio"],
       "Estación 7 d (mm)": df["mm_7d"].round(0),
       "Estación 30 d (mm)": df["mm_30d"].round(0),
       "Satélite 30 d (mm)": df["sat_30d"].round(0),
       "Diferencia (%)": df["dif_pct"].round(0),
       "Calidad": df["calidad"], "Observación": df["motivo"]}
)[["Estación", "Municipio", "Estación 7 d (mm)", "Estación 30 d (mm)",
   "Satélite 30 d (mm)", "Diferencia (%)", "Calidad", "Observación"]]
st.dataframe(tabla, hide_index=True, use_container_width=True)
st.download_button("Descargar tabla (CSV)",
                   tabla.to_csv(index=False).encode("utf-8-sig"),
                   file_name="contraste_estaciones_risaralda.csv",
                   mime="text/csv")

# Serie diaria ---------------------------------------------------------------
st.markdown("### Lluvia diaria por estación")
sel = st.selectbox("Estación", list(df["nombre"]))
cod = df.loc[df["nombre"] == sel, "codigo"].iloc[0]
serie = res["serie"].get(cod, [])
if serie:
    fig2 = go.Figure(go.Bar(x=[s[0] for s in serie], y=[s[1] for s in serie],
                            marker_color=VERDE_CARDER))
    fig2.update_layout(height=300, yaxis_title="mm/día",
                       margin=dict(l=0, r=0, t=10, b=0), plot_bgcolor="white")
    st.plotly_chart(fig2, use_container_width=True)
    fila = df[df["codigo"] == cod].iloc[0]
    if fila["calidad"] == "Dudosa":
        st.warning(f"Estación con calidad dudosa: {fila['motivo']}.")

st.caption(
    "Fuente: IDEAM, datos abiertos (datos.gov.co), sensor de precipitación "
    "automático, información preliminar sin validar. Satélite: NASA GPM IMERG "
    "V07. Calculado en vivo; se actualiza cada hora."
)
pie_institucional()
