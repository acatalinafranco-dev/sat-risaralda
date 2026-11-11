"""Página: indicadores por punto (eventos del SIMMA o una lista propia)."""
from __future__ import annotations

import sys
from pathlib import Path

import folium
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import puntos as pt
from src import riesgo
from src.gee_session import codigo_activo, es_departamento, lista_municipios
from src.ui import (agregar_contorno, agregar_municipios, ajustar_al_municipio,
                    conectar_gee, encabezado, mapa_base, pie_institucional)

st.set_page_config(page_title="Puntos de interés · SAT Risaralda", layout="wide",
                   page_icon="📍", initial_sidebar_state="expanded")

MAX_PUNTOS = 300

encabezado(
    "📍 Puntos de interés · {mun}",
    "Indicadores en **puntos concretos**: la pendiente, el cambio reciente en "
    "el radar y la lluvia de los últimos días. Los puntos pueden ser los "
    "**eventos del SIMMA** o una **lista propia** (por ejemplo, sitios "
    "críticos de los municipios).",
)

with st.expander("📖 Guía: qué muestra esta página y cómo leerla", expanded=True):
    t1, t2, t3 = st.tabs(["Qué muestra", "Cómo leer cada columna", "Límites"])
    with t1:
        st.markdown(
            """
Esta página lleva el análisis de la escala municipal a la escala de **punto**.
Para cada punto calcula, con Google Earth Engine:

- la **elevación y la pendiente** del terreno (modelo NASADEM, 30 m),
- el **cambio reciente de retrodispersión del radar Sentinel-1** en un círculo
  de 90 m de radio alrededor del punto,
- la **lluvia acumulada** de los últimos 7 y 30 días (IMERG).

Puede trabajar con los **eventos del SIMMA** (inventario y catálogo del SGC)
o cargar un archivo **CSV** con sus propios puntos. El cálculo se hace al
pulsar el botón y toma de uno a varios minutos.
"""
        )
    with t2:
        st.markdown(
            """
| Columna | Qué indica |
|---|---|
| Elevación (m) | Altura sobre el nivel del mar en el punto. |
| Pendiente (°) | Inclinación del terreno. Desde 15° se considera ladera. |
| Cambio radar (dB) | Retrodispersión de la ventana reciente menos la de la referencia. Negativo: el terreno devuelve menos señal; positivo: más. Cambios de más de ±3 dB sobre ladera se destacan. |
| Lluvia 7 d y 30 d (mm) | Acumulado satelital IMERG en el punto. |

El cambio de radar es el mismo cálculo de la página *Radar SAR*.
"""
        )
    with t3:
        st.markdown(
            """
- **La lluvia IMERG tiene píxeles de unos 11 km.** Puntos cercanos entre sí
  reciben casi el mismo valor: indica la lluvia regional, no la del sitio.
- **Los eventos del SIMMA incluidos en la aplicación no traen fecha.** Por eso
  no se puede asegurar que el cambio de radar actual esté relacionado con el
  evento: son los lugares donde históricamente ocurrieron movimientos.
- **El cambio de radar no confirma movimientos en masa.** También responde a
  humedad, cultivos y sombras de ladera.
- **Resolución.** La pendiente y el radar se promedian en celdas de unos 30 m.
- Herramienta de apoyo al conocimiento del riesgo; no sustituye las alertas
  oficiales ni la verificación en campo.
"""
        )

if not conectar_gee():
    st.stop()

fuente = st.radio("Origen de los puntos", ["Eventos del SIMMA", "Mi lista (CSV)"],
                  horizontal=True, key="pi_fuente")

nombres = dict(lista_municipios())
base = None
if fuente == "Eventos del SIMMA":
    df = riesgo.puntos_simma()
    df["Municipio"] = df["codigo"].map(nombres)
    cods = [c for c, _ in lista_municipios()]
    defecto = [] if es_departamento() else [codigo_activo()]
    c1, c2, c3 = st.columns(3)
    with c1:
        sel_mun = st.multiselect("Municipio", cods, default=defecto,
                                 format_func=lambda c: nombres.get(c, c),
                                 key="pi_mun",
                                 help="Elija uno o varios municipios para "
                                      "limitar los puntos a calcular.")
    with c2:
        sel_tipo = st.multiselect("Tipo de evento", sorted(df["tipo"].dropna().unique()),
                                  key="pi_tipo", help="Vacío = todos los tipos.")
    with c3:
        sel_org = st.multiselect("Origen", sorted(df["origen"].dropna().unique()),
                                 key="pi_org",
                                 help="Inventario de campo o catálogo.")
    if sel_mun:
        df = df[df["codigo"].isin(sel_mun)]
    if sel_tipo:
        df = df[df["tipo"].isin(sel_tipo)]
    if sel_org:
        df = df[df["origen"].isin(sel_org)]
    base = pd.DataFrame({
        "Nombre": df["id"].astype(str), "lon": df["lon"], "lat": df["lat"],
        "Municipio": df["Municipio"], "Tipo": df["tipo"], "Origen": df["origen"],
    }).reset_index(drop=True)
else:
    plantilla = "nombre,lat,lon\nSitio ejemplo,4.8100,-75.7000\n"
    st.download_button("Descargar plantilla CSV", plantilla.encode("utf-8"),
                       file_name="plantilla_puntos.csv", mime="text/csv")
    arch = st.file_uploader("Cargue un CSV con columnas nombre, lat y lon",
                            type=["csv"], key="pi_csv")
    if arch is not None:
        try:
            crudo = pd.read_csv(arch)
            crudo.columns = [str(c).strip().lower() for c in crudo.columns]
            col_lat = next((c for c in ("lat", "latitud", "latitude") if c in crudo), None)
            col_lon = next((c for c in ("lon", "lng", "longitud", "longitude") if c in crudo), None)
            if not col_lat or not col_lon:
                raise ValueError("faltan las columnas lat y lon")
            crudo["lat"] = pd.to_numeric(crudo[col_lat], errors="coerce")
            crudo["lon"] = pd.to_numeric(crudo[col_lon], errors="coerce")
            crudo = crudo.dropna(subset=["lat", "lon"]).reset_index(drop=True)
            nom = crudo["nombre"].astype(str) if "nombre" in crudo else \
                pd.Series([f"Punto {i + 1}" for i in range(len(crudo))])
            base = pd.DataFrame({"Nombre": nom, "lon": crudo["lon"],
                                 "lat": crudo["lat"], "Municipio": "", "Tipo": "",
                                 "Origen": "Lista propia"})
            fuera = ((base["lat"] < 4.5) | (base["lat"] > 5.7)
                     | (base["lon"] < -76.6) | (base["lon"] > -75.1)).sum()
            if fuera:
                st.warning(f"{fuera} punto(s) quedan fuera de Risaralda; revise "
                           "que las coordenadas estén en grados decimales (WGS84).")
        except Exception as exc:  # noqa: BLE001
            st.error(f"No fue posible leer el archivo: {exc}")

if base is None or base.empty:
    st.info("Seleccione puntos para calcular: elija municipios o cargue un archivo.")
    pie_institucional()
    st.stop()

if len(base) > MAX_PUNTOS:
    st.warning(f"Hay {len(base)} puntos. Se calcula una muestra de "
               f"{MAX_PUNTOS} repartida al azar; use los filtros para "
               "acotar la selección y calcular todos.")
    base = base.sample(MAX_PUNTOS, random_state=0).sort_index().reset_index(drop=True)

st.write(f"**{len(base)} puntos** listos para calcular.")
c1, c2 = st.columns(2)
with c1:
    dias_rec = st.selectbox("Ventana reciente del radar", [12, 24, 36], index=1,
                            format_func=lambda d: f"últimos {d} días", key="pi_rec",
                            help="Misma definición que en la página Radar SAR.")
with c2:
    dias_ref = st.selectbox("Referencia del radar", [60, 90, 180], index=1,
                            format_func=lambda d: f"{d} días previos", key="pi_ref")

firma = (fuente, tuple(base["Nombre"]), tuple(base["lat"].round(5)), dias_rec, dias_ref)
if st.button("Calcular indicadores", type="primary"):
    try:
        with st.spinner("Calculando en Google Earth Engine (puede tardar varios minutos)..."):
            r = pt.calcular_puntos(tuple((i, float(x), float(y)) for i, (x, y) in
                                         enumerate(zip(base["lon"], base["lat"]))),
                                   dias_rec, dias_ref)
        st.session_state["pi_res"] = {"firma": firma, "r": r, "base": base}
    except Exception as exc:  # noqa: BLE001
        st.error(f"No fue posible calcular los indicadores: {exc}")

est = st.session_state.get("pi_res")
if not est or est["firma"] != firma:
    st.caption("Pulse «Calcular indicadores» para obtener los resultados.")
    pie_institucional()
    st.stop()

r, b = est["r"], est["base"]
filas = []
for i, row in b.iterrows():
    v = r["filas"].get(str(i), {})
    filas.append({
        "Nombre": row["Nombre"], "Municipio": row["Municipio"], "Tipo": row["Tipo"],
        "Origen": row["Origen"], "Latitud": round(row["lat"], 5),
        "Longitud": round(row["lon"], 5),
        "Elevación (m)": v.get("elevacion"), "Pendiente (°)": v.get("pendiente"),
        "Cambio radar (dB)": v.get("sar_db"),
        "Lluvia 7 d (mm)": v.get("lluvia_7d"), "Lluvia 30 d (mm)": v.get("lluvia_30d"),
    })
res = pd.DataFrame(filas)

umbral = st.slider("Umbral de cambio de radar (dB)", 2.0, 6.0, 3.0, 0.5, key="pi_umb",
                   help="Se destacan los puntos con cambio superior al umbral "
                        "(en valor absoluto) y pendiente de 15° o más.")
fuerte = (res["Cambio radar (dB)"].abs() > umbral) & (res["Pendiente (°)"] >= 15)
k1, k2, k3, k4 = st.columns(4)
k1.metric("Puntos calculados", len(res))
k2.metric("En ladera (≥ 15°)", int((res["Pendiente (°)"] >= 15).sum()),
          help="Puntos con pendiente de 15° o más.")
k3.metric("Con cambio fuerte de radar en ladera", int(fuerte.sum()),
          help="Cambio superior al umbral sobre pendiente de 15° o más. "
               "Son puntos por verificar, no eventos confirmados.")
k4.metric("Radar: órbita y fechas", r["meta"]["orbita"],
          f"{r['meta']['fecha_ini']} a {r['meta']['fecha_fin']}", delta_color="off")

variable = st.radio("Colorear el mapa por",
                    ["Cambio radar (dB)", "Pendiente (°)", "Lluvia 30 d (mm)"],
                    horizontal=True, key="pi_var")


def _color(v):
    if v is None or pd.isna(v):
        return "#9e9e9e"
    if variable == "Cambio radar (dB)":
        return "#2166ac" if v <= -umbral else "#e66101" if v >= umbral else "#cccccc"
    if variable == "Pendiente (°)":
        return "#e34a33" if v >= 30 else "#fdae61" if v >= 15 else "#ffffbf"
    lo, hi = res["Lluvia 30 d (mm)"].min(), res["Lluvia 30 d (mm)"].max()
    t = 0.0 if hi == lo else (v - lo) / (hi - lo)
    a, bb = (222, 235, 247), (8, 81, 156)
    return "#%02x%02x%02x" % tuple(int(a[k] + t * (bb[k] - a[k])) for k in range(3))


m = mapa_base(zoom=10, basemap="Esri.WorldImagery")
if es_departamento():
    agregar_municipios(m)
else:
    agregar_contorno(m)
for _, f in res.iterrows():
    fmt = lambda x, n=1: "s/d" if x is None or pd.isna(x) else f"{x:.{n}f}"  # noqa: E731
    folium.CircleMarker(
        [f["Latitud"], f["Longitud"]], radius=6, color="#ffffff", weight=1,
        fill=True, fill_color=_color(f[variable]), fill_opacity=0.95,
        tooltip=(f"{f['Nombre']} · {f['Tipo'] or f['Origen']}<br>"
                 f"Pendiente: {fmt(f['Pendiente (°)'], 0)}° · "
                 f"Radar: {fmt(f['Cambio radar (dB)'])} dB<br>"
                 f"Lluvia 7 d: {fmt(f['Lluvia 7 d (mm)'], 0)} mm · "
                 f"30 d: {fmt(f['Lluvia 30 d (mm)'], 0)} mm")).add_to(m)
ajustar_al_municipio(m, margen=0.03)
m.to_streamlit(height=520)
leyenda = {
    "Cambio radar (dB)": f"Azul: disminución · Naranja: aumento (más de ±{umbral:g} dB) · Gris: sin cambio fuerte",
    "Pendiente (°)": "Amarillo: menos de 15° · Naranja: 15 a 30° · Rojo: 30° o más",
    "Lluvia 30 d (mm)": "Azul claro a oscuro: menor a mayor lluvia entre los puntos",
}[variable]
st.caption(f"{leyenda} · Gris oscuro: sin dato.")

st.markdown("#### Resultados por punto")
orden = st.selectbox("Ordenar por", ["Cambio radar (dB)", "Pendiente (°)",
                                     "Lluvia 30 d (mm)", "Nombre"], key="pi_ord")
tabla = res.assign(_a=res["Cambio radar (dB)"].abs() if orden == "Cambio radar (dB)"
                   else res[orden]).sort_values(
    "_a", ascending=(orden == "Nombre"), na_position="last").drop(columns="_a")
st.dataframe(tabla, hide_index=True, use_container_width=True,
             column_config={c: st.column_config.NumberColumn(format="%.1f")
                            for c in ("Elevación (m)", "Pendiente (°)", "Cambio radar (dB)",
                                      "Lluvia 7 d (mm)", "Lluvia 30 d (mm)")})
st.download_button("Descargar resultados (CSV)",
                   tabla.to_csv(index=False).encode("utf-8-sig"),
                   file_name="puntos_de_interes.csv", mime="text/csv")
st.caption(
    "Fuentes: NASADEM (NASA), Copernicus Sentinel-1 (ESA), NASA GPM IMERG y "
    "SIMMA del Servicio Geológico Colombiano, procesados en Google Earth "
    "Engine. Los indicadores son referenciales y no constituyen una alerta."
)
pie_institucional()
