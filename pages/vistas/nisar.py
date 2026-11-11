"""Página: escenas NISAR (NASA-ISRO, banda L) disponibles sobre Risaralda."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import folium
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.gee_session import codigo_activo, es_departamento, geojson_municipios
from src.ui import (VERDE_CARDER, agregar_contorno, agregar_municipios,
                    ajustar_al_municipio, encabezado, mapa_base,
                    pie_institucional)

st.set_page_config(page_title="NISAR · SAT Risaralda", layout="wide",
                   page_icon="🛰️", initial_sidebar_state="expanded")

ASF = "https://api.daac.asf.alaska.edu/services/search/param"
VERTEX = "https://search.asf.alaska.edu/"

PRODUCTOS = {
    "RRSD": ("Nivel 0B", "Datos crudos del radar, sin procesar.",
             "Uso especializado: procesamiento propio desde la señal original."),
    "RSLC": ("Nivel 1", "Imagen compleja (amplitud y fase) en geometría de radar.",
             "Base para interferometría propia y análisis detallado."),
    "RIFG": ("Nivel 1", "Interferograma envuelto en geometría de radar.",
             "Diferencia de fase entre dos fechas; aún sin desenvolver."),
    "RUNW": ("Nivel 1", "Interferograma desenvuelto en geometría de radar.",
             "Medición de desplazamiento en la línea de visión del satélite."),
    "ROFF": ("Nivel 1", "Desplazamientos de píxeles en geometría de radar.",
             "Desplazamientos grandes que la fase no puede medir."),
    "GSLC": ("Nivel 2", "Imagen compleja geocodificada (sobre mapa).",
             "Análisis de series de tiempo sobre una grilla común."),
    "GCOV": ("Nivel 2", "Covarianza polarimétrica geocodificada (retrodispersión).",
             "Equivalente en banda L de lo que se hace con Sentinel-1: "
             "detección de cambios, cobertura, biomasa y humedad."),
    "GUNW": ("Nivel 2", "Interferograma desenvuelto geocodificado.",
             "Deformación del terreno (InSAR) entre dos fechas: laderas con "
             "movimiento lento, hundimientos, deformación por sismos."),
    "GOFF": ("Nivel 2", "Desplazamientos de píxeles geocodificados.",
             "Desplazamientos rápidos y grandes, como deslizamientos."),
    "SME2": ("Nivel 3", "Humedad del suelo.",
             "Complemento a la lluvia como indicador de saturación."),
}


def _bbox_activo() -> tuple[float, float, float, float]:
    """Caja (oeste, sur, este, norte) de la unidad activa."""
    cod = None if es_departamento() else str(codigo_activo())
    xs, ys = [], []

    def _rec(c):
        if c and isinstance(c[0], (int, float)):
            xs.append(c[0])
            ys.append(c[1])
        else:
            for s in c:
                _rec(s)

    for f in geojson_municipios()["features"]:
        if cod is None or str(f["properties"].get("codigo")) == cod:
            _rec(f["geometry"]["coordinates"])
    return min(xs), min(ys), max(xs), max(ys)


@st.cache_data(ttl=3600, show_spinner=False)
def _buscar(bbox: tuple, ini: str, fin: str) -> list[dict]:
    w, s, e, n = bbox
    poligono = f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"
    r = requests.get(
        ASF,
        params={"platform": "NISAR", "intersectsWith": poligono,
                "start": f"{ini}T00:00:00Z", "end": f"{fin}T23:59:59Z",
                "maxResults": 2000, "output": "json"},
        headers={"User-Agent": "sat-risaralda-carder"}, timeout=60)
    r.raise_for_status()
    datos = r.json()
    if datos and isinstance(datos[0], list):
        datos = datos[0]
    filas = []
    for g in datos:
        url = g.get("downloadUrl") or ""
        partes = url.split("/")
        coleccion = partes[4] if len(partes) > 4 else ""
        version = ("Provisional" if "PROVISIONAL" in coleccion
                   else "Beta" if "BETA" in coleccion else "Otra")
        nisar = g.get("nisar") or {}
        pol = nisar.get("mainBandPolarization") or []
        filas.append({
            "Inicio": (g.get("startTime") or "")[:19].replace("T", " "),
            "Fin": (g.get("stopTime") or "")[:19].replace("T", " "),
            "Producto": g.get("processingLevel") or "",
            "Versión": version,
            "Órbita": {"ASCENDING": "Ascendente", "DESCENDING": "Descendente"}.get(
                g.get("flightDirection") or "", g.get("flightDirection") or ""),
            "Trayectoria": g.get("relativeOrbit"),
            "Marco": g.get("frameNumber"),
            "Polarización": ", ".join(pol),
            "Cobertura del marco": nisar.get("frameCoverage") or "",
            "Procesado": (g.get("processingDate") or "")[:10],
            "Huella": g.get("stringFootprint") or "",
            "Vista previa": (g.get("browse") or [""])[0],
            "Descarga": url,
            "Nombre": g.get("fileName") or "",
        })
    filas.sort(key=lambda f: f["Inicio"], reverse=True)
    return filas


def _huella(wkt: str):
    """Lista de [lat, lon] de un POLYGON ((lon lat, ...)) simple."""
    try:
        cuerpo = wkt[wkt.index("((") + 2: wkt.rindex("))")]
        return [[float(p.split()[1]), float(p.split()[0])]
                for p in cuerpo.split(",")]
    except Exception:  # noqa: BLE001
        return []


encabezado(
    "🛰️ NISAR · radar de banda L · {mun}",
    "Búsqueda de las escenas de **NISAR** (NASA–ISRO) disponibles sobre la "
    "zona, con su fecha, tipo de producto y enlace de descarga. NISAR es la "
    "misión de radar de banda L más reciente y penetra mejor la vegetación "
    "densa que Sentinel-1.",
)

with st.expander("📖 Guía: qué es NISAR y cómo usar esta página", expanded=True):
    t1, t2, t3, t4 = st.tabs(["¿Qué es NISAR?", "Tipos de producto",
                              "Cómo usar esta página", "Límites"])
    with t1:
        st.markdown(
            """
**La misión.** NISAR (NASA-ISRO Synthetic Aperture Radar) es una misión
conjunta de la NASA y la agencia espacial de la India (ISRO), lanzada en
2025. Lleva dos radares de apertura sintética: uno de **banda L** (longitud
de onda cercana a 24 cm) y uno de **banda S**. Los datos de banda L son los
que hoy se distribuyen públicamente.

**Por qué importa para movimientos en masa.** La banda L tiene una longitud de
onda mayor que la banda C de Sentinel-1 (unos 5,6 cm). Por eso **atraviesa
mejor el dosel** y conserva la señal sobre bosque y cultivos densos como los
de Risaralda. Eso la hace más apta para medir **deformación lenta del terreno**
mediante interferometría (InSAR) y para detectar cambios bajo vegetación.

**Frecuencia.** El satélite repite su órbita cada 12 días y cubre
prácticamente todas las tierras emergidas. Los productos de nivel 1 a 3 se
publican entre 36 y 72 horas después de la toma.

**Estado de los datos.** Los productos **provisionales** están calibrados,
pero su validación es parcial. Los productos **beta** (anteriores) no tienen
la calibración final. La reprocesamiento validado está previsto para finales
de 2026.
"""
        )
    with t2:
        filas = [{"Código": k, "Nivel": v[0], "Qué es": v[1], "Para qué sirve": v[2]}
                 for k, v in PRODUCTOS.items()]
        st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
        st.caption(
            "Los códigos de producto son los del ASF. Para estudios de "
            "movimientos en masa los más útiles son GCOV (cambio de "
            "retrodispersión), GUNW (deformación) y GOFF (desplazamientos)."
        )
    with t3:
        st.markdown(
            """
1. Elija el **rango de fechas** y, si lo desea, filtre por **producto**,
   **órbita** y **versión**.
2. El gráfico y la tabla muestran las escenas que **intersectan** la zona
   seleccionada. Intersectar no significa cubrirla por completo: revise la
   columna *Cobertura del marco* y la huella en el mapa.
3. Seleccione una escena para ver su **huella** sobre el mapa y su **vista
   previa**.
4. La descarga requiere una **cuenta gratuita de NASA Earthdata**
   (urs.earthdata.nasa.gov). El enlace de la tabla abre el archivo en el ASF.
   Para buscar con filtros más avanzados use ASF Vertex.
5. Los archivos están en formato HDF5 y pesan desde cientos de megabytes
   hasta varios gigabytes. Se procesan con herramientas como Python, QGIS o
   ArcGIS Pro.
"""
        )
    with t4:
        st.markdown(
            """
- Esta página **solo lista** las escenas; no procesa ni interpreta los datos.
- Los productos provisionales pueden cambiar cuando se publique el
  reprocesamiento validado.
- Los productos de deformación (GUNW) exigen que **dos fechas** sean
  coherentes. En vegetación densa y en lluvias intensas la coherencia puede
  perderse, aun en banda L.
- Una huella que intersecta Risaralda puede cubrir solo una parte del
  departamento.
- Herramienta de apoyo al conocimiento del riesgo: no sustituye las alertas
  oficiales ni la verificación en campo.
"""
        )

hoy = dt.date.today()
c1, c2, c3, c4 = st.columns(4)
with c1:
    ini = st.date_input("Desde", hoy - dt.timedelta(days=90), key="nisar_ini",
                        help="Primera fecha de adquisición a buscar. Los "
                             "productos provisionales empiezan el 17 de junio "
                             "de 2026; hay beta desde octubre de 2025.")
with c2:
    fin = st.date_input("Hasta", hoy, key="nisar_fin")

try:
    with st.spinner("Consultando el catálogo del ASF..."):
        filas = _buscar(_bbox_activo(), ini.isoformat(), fin.isoformat())
except Exception as exc:  # noqa: BLE001
    st.error(f"No fue posible consultar el catálogo del ASF: {exc}")
    st.link_button("Abrir ASF Vertex", VERTEX)
    st.stop()

if not filas:
    st.info("No hay escenas NISAR en ese rango de fechas. Amplíe el rango.")
    st.link_button("Abrir ASF Vertex", VERTEX)
    pie_institucional()
    st.stop()

df = pd.DataFrame(filas)
with c3:
    prod = st.multiselect("Producto", sorted(df["Producto"].unique()),
                          default=[], key="nisar_prod",
                          help="Tipo de producto (vea la pestaña «Tipos de "
                               "producto» de la guía). Vacío = todos.")
with c4:
    ver = st.multiselect("Versión", sorted(df["Versión"].unique()), default=[],
                         key="nisar_ver",
                         help="Provisional: calibrado, validación parcial. "
                              "Beta: sin calibración final.")
orb = st.multiselect("Órbita", sorted(df["Órbita"].unique()), default=[],
                     key="nisar_orb",
                     help="Ascendente o descendente. Para comparar fechas, "
                          "use la misma órbita y trayectoria.")
if prod:
    df = df[df["Producto"].isin(prod)]
if ver:
    df = df[df["Versión"].isin(ver)]
if orb:
    df = df[df["Órbita"].isin(orb)]

k1, k2, k3 = st.columns(3)
k1.metric("Escenas", f"{len(df):,}".replace(",", "."),
          help="Escenas que intersectan la zona seleccionada, tras los filtros.")
k2.metric("Última adquisición", df["Inicio"].max()[:10] if len(df) else "s/d",
          help="Fecha de inicio de la escena más reciente.")
k3.metric("Trayectorias distintas", int(df["Trayectoria"].nunique()),
          help="Cada trayectoria es una franja distinta sobre el terreno.")

if len(df):
    cont = df["Producto"].value_counts().sort_values()
    fig = go.Figure(go.Bar(x=cont.values, y=cont.index, orientation="h",
                           marker_color=VERDE_CARDER))
    fig.update_layout(height=max(220, 40 * len(cont) + 80), xaxis_title="Escenas",
                      margin=dict(l=0, r=10, t=10, b=0), plot_bgcolor="white")
    st.plotly_chart(fig, use_container_width=True)

    vista = df.drop(columns=["Huella", "Vista previa", "Nombre"])
    st.dataframe(vista, hide_index=True, use_container_width=True,
                 column_config={"Descarga": st.column_config.LinkColumn(
                     "Descarga", display_text="Descargar")})
    st.download_button("Descargar tabla (CSV)",
                       vista.to_csv(index=False).encode("utf-8-sig"),
                       file_name="escenas_nisar.csv", mime="text/csv")

    st.divider()
    st.markdown("#### Huella y vista previa de una escena")
    etiquetas = [f"{r.Inicio[:16]} · {r.Producto} · {r.Órbita} · "
                 f"trayectoria {r.Trayectoria} · {r.Versión}"
                 for r in df.itertuples()]
    sel = st.selectbox("Escena", range(len(etiquetas)),
                       format_func=lambda i: etiquetas[i], key="nisar_sel")
    esc = df.iloc[sel]
    m = mapa_base(zoom=8, basemap="Esri.WorldImagery")
    if es_departamento():
        agregar_municipios(m)
    else:
        agregar_contorno(m)
    pts = _huella(esc["Huella"])
    if pts:
        folium.Polygon(pts, color="#ff00ff", weight=2, fill=True,
                       fill_opacity=0.08,
                       tooltip=f"{esc['Producto']} · {esc['Inicio'][:16]}").add_to(m)
    ajustar_al_municipio(m, margen=1.0)
    m.to_streamlit(height=460)
    cizq, cder = st.columns([2, 1])
    with cizq:
        st.caption(f"Archivo: {esc['Nombre']}")
        st.link_button("Descargar escena (requiere cuenta Earthdata)",
                       esc["Descarga"])
    with cder:
        if esc["Vista previa"]:
            st.image(esc["Vista previa"], caption="Vista previa del ASF",
                     use_container_width=True)
else:
    st.info("Ningún resultado con esos filtros.")

st.link_button("Buscar con filtros avanzados en ASF Vertex", VERTEX)
st.caption(
    "Fuente: NASA / ISRO NISAR, distribuido por el Alaska Satellite Facility "
    "(ASF DAAC). Productos provisionales y beta: pueden cambiar con el "
    "reprocesamiento validado. Herramienta de apoyo al conocimiento del "
    "riesgo; no sustituye las alertas oficiales."
)
pie_institucional()
