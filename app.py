"""Monitoreo Satelital de Movimientos en Masa · Risaralda · Página de inicio.

Monitoreo satelital basado en productos de Google Earth Engine
(hidrometeorología y cobertura vegetal) para el departamento de Risaralda y
sus 14 municipios. 

Ejecutar local:  streamlit run app.py
"""
from __future__ import annotations

import datetime as dt
import json
import math

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from src.gee_comparativo import tabla_comparativa
from src import interactivo as itv
from src import riesgo
from src.ficha import generar_ficha
from src.gee_session import codigo_activo, geojson_municipios, nombre_activo
from src.ui import (DEPENDENCIA, ENTIDAD, GRADIENTE, VERDE_CARDER,
                    agregar_amenaza_sgc, agregar_municipios,
                    ajustar_al_municipio,
                    branding_institucional, conectar_gee, mapa_base,
                    pie_institucional)

st.set_page_config(
    page_title="Monitoreo MM · Risaralda",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

branding_institucional()

st.title("🛰️ Monitoreo Satelital de Movimientos en Masa · Risaralda")
st.markdown(
    f"<div style='font-size:1.05rem; font-weight:600; color:{VERDE_CARDER}; "
    f"margin-top:-8px;'>{DEPENDENCIA}</div>"
    f"<div style='font-size:0.92rem; color:#3a3a3a; margin-top:2px;'>"
    f"{ENTIDAD}</div>"
    f"<hr style='border:none; height:4px; margin:10px 0 14px 0; width:340px; "
    f"background:{GRADIENTE};'>",
    unsafe_allow_html=True,
)
st.markdown(
    f"""
**Monitoreo satelital de movimientos en masa** para el departamento de
**Risaralda** y sus **14 municipios**: zona de cordillera con alta pendiente y
lluvias intensas, con recurrencia histórica de **movimientos en masa** y
crecientes súbitas.

Los datos se calculan **en vivo desde Google Earth Engine** sobre el polígono
oficial (DIVIPOLA). Elija en la barra lateral **«Todo Risaralda»** o un
municipio: las páginas de análisis se calculan sobre esa selección.

**Unidad de análisis actual: {nombre_activo()}**
"""
)

conectado = conectar_gee()


@st.cache_data(ttl=21600, show_spinner=False)
def _comparativo_v2(fecha_consulta: str):
    return tabla_comparativa()


res = {"filas": [], "errores": []}
if conectado:
    with st.spinner("Calculando los indicadores de los 14 municipios "
                    "(la primera carga del día puede tardar unos minutos)..."):
        try:
            res = _comparativo_v2(dt.date.today().isoformat())
        except Exception as exc:  # noqa: BLE001
            res = {"filas": [], "errores": [str(exc)]}

# --- Tabla base: lluvia/vegetación (GEE) + amenaza y eventos (SGC) ---------
if res["filas"]:
    df = pd.DataFrame(res["filas"])
else:
    df = pd.DataFrame([
        {"codigo": f["properties"]["codigo"], "nombre": f["properties"]["nombre"],
         "area_km2": f["properties"]["area_km2"]}
        for f in geojson_municipios()["features"]])
for col in ("lluvia_7d", "lluvia_30d", "pct_normal_30d", "perdida_ha", "perdida_pct"):
    if col not in df:
        df[col] = float("nan")
_am = riesgo.amenaza_municipal().set_index("codigo")
df["alta_muy_alta"] = df["codigo"].map(_am["alta_muy_alta"])
df["eventos"] = df["codigo"].map(riesgo.eventos_por_municipio()).fillna(0).astype(int)
_info = df.set_index("codigo").to_dict("index")

# --- Mapa por municipio + resumen -----------------------------------------
c1, c2 = st.columns([1.4, 1])

_CAPAS = [
    # (nombre de la capa, columna, color mínimo, color máximo, unidad, visible)
    ("Lluvia 30 d (% de la normal)", "pct_normal_30d", (222, 235, 247), (8, 81, 156), "%", True),
    ("Lluvia 7 d (mm)", "lluvia_7d", (255, 255, 217), (8, 29, 88), "mm", False),
    ("Lluvia 30 d (mm)", "lluvia_30d", (229, 245, 249), (0, 109, 44), "mm", False),
    ("Eventos SIMMA", "eventos", (242, 240, 247), (84, 39, 143), "", False),
    ("Pérdida de vegetación (ha)", "perdida_ha", (254, 227, 145), (102, 37, 6), "ha", False),
]


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(int(x) for x in rgb)


def _mezcla(a, b, t):
    return tuple(a[k] + t * (b[k] - a[k]) for k in range(3))


def _txt(v, unidad):
    if v is None or pd.isna(v):
        return "s/d"
    return f"{v:.0f} {unidad}".strip()


_FILAS = {f["codigo"]: f for f in res["filas"]}
_NOM = {c: i["nombre"] for c, i in _info.items()}


def _pdf_ficha(cod: str) -> bytes | None:
    """Ficha PDF de un municipio (None si aún no hay indicadores de GEE)."""
    fila = _FILAS.get(cod)
    if fila is None:
        return None
    a = riesgo.amenaza_municipal().set_index("codigo").loc[cod].to_dict()
    p = riesgo.puntos_simma(cod)
    return generar_ficha(fila, a, p["tipo"].value_counts().to_dict(),
                         int((p["origen"] == "Inventario").sum()))


def _abrir_ficha(cod: str) -> None:
    st.session_state["mun_codigo"] = cod
    st.switch_page("pages/5_Ficha_Municipal.py")


@st.cache_data(ttl=21600, show_spinner=False)
def _png_tematico(capa: str, fecha: str, valores: dict, unidad: str,
                  c_min: tuple, c_max: tuple) -> bytes:
    return itv.mapa_png(valores, f"Risaralda · {capa}", unidad, c_min, c_max)


def _panel_clic(lat: float, lon: float) -> None:
    mun = itv.municipio_en(lat, lon)
    if mun is None:
        st.info("El punto queda fuera de Risaralda. Haga clic dentro del "
                "departamento.")
        return
    cod = mun["codigo"]
    d_ = _info.get(cod, {})
    nivel = riesgo.nivel_atencion(d_.get("pct_normal_30d"), d_.get("alta_muy_alta"))
    st.markdown(f"**📍 {mun['nombre']}** · {lat:.4f}, {lon:.4f}")
    st.markdown(
        f"<div style='font-size:0.86rem;line-height:1.5'>"
        f"<b>Municipio</b><br>"
        f"Lluvia 30 d: {_txt(d_.get('pct_normal_30d'), '% de la referencia')} "
        f"({_txt(d_.get('lluvia_30d'), 'mm')}) · 7 d: {_txt(d_.get('lluvia_7d'), 'mm')}<br>"
        f"Área en amenaza alta y muy alta: {_txt(d_.get('alta_muy_alta'), '%')}<br>"
        f"Eventos SIMMA: {int(d_.get('eventos', 0))} · Pérdida de vegetación: "
        f"{_txt(d_.get('perdida_ha'), 'ha')}<br>"
        f"Nivel de atención provisional: <b style='color:"
        f"{riesgo.COLOR_NIVEL.get(nivel, '#555')}'>{nivel}</b></div>",
        unsafe_allow_html=True)
    am = itv.amenaza_en_punto(round(lat, 4), round(lon, 4))
    ev = itv.evento_cercano(lat, lon)
    pt = {"valores": {}, "error": None}
    if conectado:
        with st.spinner("Consultando el punto..."):
            pt = itv.datos_punto(round(lat, 4), round(lon, 4),
                                 dt.date.today().isoformat())
    v = pt["valores"]
    filas = [("Amenaza SGC en el punto",
              f"{am['categoria']} (escala {am['escala']})" if am else "s/d")]
    filas.append(("Lluvia 30 d en el punto",
                  "s/d" if v.get("l30") is None else
                  f"{v['l30']:.0f} mm" + ("" if v.get("pct") is None
                                          else f" ({v['pct']:.0f} % de la referencia)")))
    filas.append(("Lluvia 7 d en el punto",
                  "s/d" if v.get("l7") is None else f"{v['l7']:.0f} mm"))
    filas.append(("Cota", "s/d" if v.get("elev") is None else f"{v['elev']:.0f} m s. n. m."))
    filas.append(("Pendiente", "s/d" if v.get("pend") is None else
                  f"{v['pend']:.0f}° ({math.tan(math.radians(v['pend'])) * 100:.0f} %)"))
    filas.append(("Evento SIMMA más cercano",
                  "s/d" if ev is None else
                  f"{ev['tipo']} ({ev['origen'].lower()}), a {ev['km']:.1f} km"))
    st.markdown("**Punto consultado**")
    st.dataframe(pd.DataFrame(filas, columns=["Variable", "Valor"]),
                 hide_index=True, use_container_width=True)
    if pt["error"]:
        st.caption("No fue posible calcular parte de las variables del punto.")
    st.caption("Lluvia: IMERG (≈11 km) y referencia CHIRPS de 20 años; pendiente y "
               "cota: NASADEM (30 m); amenaza: servicio del SGC. Son valores "
               "indicativos de apoyo.")
    b1, b2 = st.columns(2)
    b1.button("Abrir la ficha", on_click=_abrir_ficha, args=(cod,),
              use_container_width=True)
    pdf = _pdf_ficha(cod)
    if pdf:
        b2.download_button("Ficha (PDF)", pdf, mime="application/pdf",
                           file_name=f"ficha_{mun['nombre'].lower().replace(' ', '_')}_"
                                     f"{dt.date.today().isoformat()}.pdf",
                           use_container_width=True)


with c1:
    st.markdown("#### Mapa por municipio")
    st.caption(
        "Use el control de capas (esquina superior derecha del mapa) para "
        "encender o apagar cada variable. La división municipal permanece "
        "visible y muestra todos los valores al pasar el cursor.")
    m = mapa_base(zoom=9, basemap="SATELLITE")
    leyendas = []
    for nombre_c, col, c_min, c_max, uni, visible in _CAPAS:
        vals = [d_[col] for d_ in _info.values()
                if d_.get(col) is not None and not pd.isna(d_[col])]
        vmin, vmax = (min(vals), max(vals)) if vals else (0.0, 1.0)
        gj = json.loads(json.dumps(geojson_municipios()))
        for f in gj["features"]:
            v = _info.get(f["properties"]["codigo"], {}).get(col)
            if v is None or pd.isna(v):
                f["properties"]["color"] = "#b0b7bd"
            else:
                t = 0.0 if vmax == vmin else (v - vmin) / (vmax - vmin)
                f["properties"]["color"] = _hex(_mezcla(c_min, c_max, t))
        folium.GeoJson(
            gj, name=nombre_c, show=visible,
            style_function=lambda f: {
                "color": "#ffffff", "weight": 0.5,
                "fillColor": f["properties"]["color"], "fillOpacity": 0.6},
        ).add_to(m)
        leyendas.append(
            f"<div style='display:flex;align-items:center;gap:8px;"
            f"font-size:0.82rem;margin:2px 0'>"
            f"<span style='flex:0 0 250px'>{nombre_c}</span>"
            f"<span>{vmin:.0f}</span>"
            f"<div style='flex:0 0 150px;height:10px;border-radius:5px;"
            f"background:linear-gradient(to right,{_hex(c_min)},{_hex(c_max)})'>"
            f"</div><span>{vmax:.0f} {uni}</span></div>")

    # Mapa original de zonificación de amenaza del SGC, recortado al departamento
    agregar_amenaza_sgc(m, geojson_municipios(), "risaralda")

    # División municipal (siempre visible) con los valores de cada capa
    gj = json.loads(json.dumps(geojson_municipios()))
    for f in gj["features"]:
        d_ = _info.get(f["properties"]["codigo"], {})
        f["properties"]["lluvia"] = _txt(d_.get("pct_normal_30d"), "% de la normal")
        f["properties"]["lluvia_7"] = _txt(d_.get("lluvia_7d"), "mm")
        f["properties"]["lluvia_mm"] = _txt(d_.get("lluvia_30d"), "mm")
        f["properties"]["amenaza"] = _txt(d_.get("alta_muy_alta"), "%")
        f["properties"]["eventos"] = str(int(d_.get("eventos", 0)))
        f["properties"]["perdida"] = _txt(d_.get("perdida_ha"), "ha")
    folium.GeoJson(
        gj, name="División municipal",
        style_function=lambda f: {
            "color": "#ffff00", "weight": 2, "fillColor": "#ffffff",
            "fillOpacity": 0.01},
        tooltip=folium.GeoJsonTooltip(
            fields=["nombre", "lluvia", "lluvia_7", "lluvia_mm", "amenaza", "eventos",
                    "perdida"],
            aliases=["Municipio", "Lluvia 30 d (% de la referencia)",
                     "Lluvia 7 d (acumulada)", "Lluvia 30 d (acumulada)",
                     "Área en amenaza alta y muy alta", "Eventos SIMMA",
                     "Pérdida de vegetación"]),
    ).add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)
    ajustar_al_municipio(m, margen=0.03)
    fg_clic = folium.FeatureGroup(name="Punto consultado", show=True)
    _clic = st.session_state.get("_clic")
    if _clic:
        folium.Marker(list(_clic), icon=folium.Icon(color="red", icon="info-sign")).add_to(fg_clic)
    salida = st_folium(m, height=520, use_container_width=True, key="mapa_inicio",
                       returned_objects=["last_clicked"], feature_group_to_add=fg_clic)
    if salida and salida.get("last_clicked"):
        _nuevo = (round(salida["last_clicked"]["lat"], 5), round(salida["last_clicked"]["lng"], 5))
        if _nuevo != st.session_state.get("_clic"):
            st.session_state["_clic"] = _nuevo
            st.rerun()
    st.markdown("".join(leyendas), unsafe_allow_html=True)
    st.caption(
        "«Amenaza SGC (mapa original)» muestra la zonificación de amenaza por "
        "movimientos en masa publicada por el Servicio Geológico Colombiano "
        "(geoportal.sgc.gov.co), con sus categorías de muy baja a muy alta, "
        "recortada al departamento; se consulta en línea y es independiente de "
        "la tabla de porcentaje por municipio.")
    st.caption("Gris: sin dato. Con varias capas activas se superponen; "
               "para leer una gama de colores conviene activar una a la vez. «% de la "
               "normal» es la lluvia de 30 días (IMERG) dividida por el promedio "
               "de 20 años de CHIRPS para la misma ventana: referencia de apoyo, "
               "no la normal oficial del IDEAM.")

    with st.expander("📥 Exportar lo que se está viendo"):
        x1, x2, x3 = st.columns(3)
        capa_x = x1.selectbox("Capa del mapa", [c[0] for c in _CAPAS], key="capa_exp")
        _, col_x, cmin_x, cmax_x, uni_x, _ = next(c for c in _CAPAS if c[0] == capa_x)
        x1.download_button(
            "Mapa temático (PNG)",
            _png_tematico(capa_x, dt.date.today().isoformat(),
                          {c: (None if pd.isna(i.get(col_x)) else float(i[col_x]))
                           for c, i in _info.items()}, uni_x, cmin_x, cmax_x),
            file_name=f"mapa_{col_x}_{dt.date.today().isoformat()}.png",
            mime="image/png", use_container_width=True)
        _clic_m = itv.municipio_en(*st.session_state["_clic"]) if st.session_state.get("_clic") else None
        _cods = list(_NOM)
        _def = _cods.index(_clic_m["codigo"]) if _clic_m else 0
        cod_x = x3.selectbox("Municipio de la ficha", _cods, index=_def,
                             format_func=lambda c: _NOM[c], key="mun_exp")
        _pdf_x = _pdf_ficha(cod_x)
        if _pdf_x:
            x3.download_button("Ficha municipal (PDF)", _pdf_x,
                               file_name=f"ficha_{_NOM[cod_x].lower().replace(' ', '_')}_"
                                         f"{dt.date.today().isoformat()}.pdf",
                               mime="application/pdf", use_container_width=True)
        x2.caption("La tabla comparativa y el semáforo se descargan en Excel "
                   "más abajo en esta página.")
        st.caption("Los archivos incluyen la fecha de corte y la cita institucional.")

with c2:
    st.markdown("#### Consulta por clic")
    _c = st.session_state.get("_clic")
    if _c:
        _panel_clic(*_c)
    else:
        st.caption("Haga clic en cualquier punto del mapa para ver el resumen "
                   "del municipio y los datos de ese punto: amenaza del SGC, "
                   "lluvia, pendiente y evento más cercano.")
    st.divider()
    st.markdown("#### Resumen")
    st.caption(f"Fecha de corte: {dt.date.today().strftime('%d/%m/%Y')} · "
               f"Unidad de análisis: **{nombre_activo()}**")
    if df["pct_normal_30d"].notna().any():
        i = df["pct_normal_30d"].idxmax()
        st.metric("Mayor lluvia de 30 días frente a la normal",
                  f"{df.loc[i, 'pct_normal_30d']:.0f} %",
                  df.loc[i, "nombre"], delta_color="off")
    j = df["alta_muy_alta"].idxmax()
    st.metric("Mayor área en amenaza alta y muy alta",
              f"{df.loc[j, 'alta_muy_alta']:.0f} %",
              df.loc[j, "nombre"], delta_color="off")
    st.metric("Eventos registrados en el SIMMA", int(df["eventos"].sum()),
              help="Inventario y catálogo del SGC, suma de los 14 municipios.")
    if conectado:
        st.success("Google Earth Engine conectado ✔")
    st.info(
        "Esta página presenta **indicadores**, no niveles de alerta. Las "
        "alertas oficiales corresponden al IDEAM, al SGC y a los "
        "CMGRD/CDGRD.", icon="ℹ️")

st.divider()
st.markdown("#### Módulos del sistema")
mc1, mc2, mc3, mc4 = st.columns(4)
mc1.markdown("**🌧️ Precipitación**<br>Series diarias (IMERG · CHIRPS · ERA5-Land), "
             "mapas de lluvia acumulada y climatología de 20 años.",
             unsafe_allow_html=True)
mc2.markdown("**🛰️ Imágenes satelitales**<br>Sentinel-2, Landsat 8/9 y "
             "Sentinel-1 (radar), en color real, falso color y SAR.",
             unsafe_allow_html=True)
mc3.markdown("**🌿 Índices de vegetación**<br>NDVI, NDMI, BSI y detección de "
             "cambios (ΔNDVI) asociados a movimientos en masa.",
             unsafe_allow_html=True)
mc4.markdown("**⛰️ Amenaza y eventos**<br>Pendiente, susceptibilidad y "
             "amenaza del SGC y eventos históricos del SIMMA.",
             unsafe_allow_html=True)
st.caption("Use el menú de la barra lateral para abrir cada módulo.")

st.divider()

# --------------------------------------------------------------------------
# Comparativo de los 14 municipios
# --------------------------------------------------------------------------
st.markdown("#### Comparativo entre municipios")
st.caption(
    "Lluvia acumulada (IMERG, media sobre el polígono), su relación con la "
    "referencia climatológica (promedio de 20 años de CHIRPS para la misma "
    "ventana de 30 días; no es la normal oficial del IDEAM), amenaza del SGC, eventos del SIMMA y pérdida severa de vegetación "
    "(ΔNDVI < −0,20 sobre zonas con NDVI > 0,4; Sentinel-2, últimos 60 días "
    "frente a hace 6–12 meses). Se actualiza cada día."
)
for e in res["errores"]:
    st.warning(f"No fue posible calcular una parte del comparativo. {e}")

tabla = df.rename(columns={
    "nombre": "Municipio",
    "area_km2": "Área (km²)",
    "lluvia_7d": "Lluvia 7 días (mm)", "lluvia_30d": "Lluvia 30 días (mm)",
    "pct_normal_30d": "Lluvia 30 d (% de la normal)",
    "alta_muy_alta": "Amenaza alta y muy alta (% área)",
    "eventos": "Eventos SIMMA",
    "perdida_ha": "Pérdida de vegetación (ha)",
    "perdida_pct": "% del área municipal",
})[["Municipio", "Lluvia 7 días (mm)",
    "Lluvia 30 días (mm)", "Lluvia 30 d (% de la normal)",
    "Amenaza alta y muy alta (% área)", "Eventos SIMMA",
    "Pérdida de vegetación (ha)", "% del área municipal", "Área (km²)"]]
orden = st.radio(
    "Ordenar por", ["Municipio", "Lluvia 30 d (% de la normal)",
                    "Amenaza alta y muy alta (% área)", "Eventos SIMMA",
                    "Pérdida de vegetación (ha)"],
    horizontal=True,
)
tabla = tabla.sort_values(orden, ascending=(orden == "Municipio"),
                          na_position="last")
st.dataframe(
    tabla, hide_index=True, use_container_width=True,
    column_config={
        "Área (km²)": st.column_config.NumberColumn(format="%.1f"),
        "Lluvia 7 días (mm)": st.column_config.NumberColumn(format="%.0f"),
        "Lluvia 30 días (mm)": st.column_config.NumberColumn(format="%.0f"),
        "Lluvia 30 d (% de la normal)": st.column_config.NumberColumn(format="%.0f"),
        "Amenaza alta y muy alta (% área)": st.column_config.NumberColumn(format="%.0f"),
        "Pérdida de vegetación (ha)": st.column_config.NumberColumn(format="%.0f"),
        "% del área municipal": st.column_config.NumberColumn(format="%.2f"),
    },
)
st.download_button(
    "Descargar tabla (CSV)",
    tabla.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"comparativo_risaralda_{dt.date.today().isoformat()}.csv",
    mime="text/csv",
)
st.download_button(
    "Descargar tabla (Excel)",
    itv.excel_bytes({"Comparativo": tabla}, [
        "Lluvia: IMERG V07 (acumulado 7 y 30 días) frente al promedio de 20 años de "
        "CHIRPS para la misma ventana; es una referencia de apoyo, no la normal oficial del IDEAM.",
        "Amenaza: Mapa Nacional de Amenaza por Movimientos en Masa, SGC (2015, 1:100.000).",
        f"Eventos: SIMMA del SGC (descarga del {riesgo.fecha_corte_sgc()}).",
        "Pérdida de vegetación: ΔNDVI < −0,20 sobre zonas con NDVI > 0,4, Sentinel-2.",
        "Los valores son indicativos y no sustituyen las alertas oficiales."]),
    file_name=f"comparativo_risaralda_{dt.date.today().isoformat()}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
st.caption(
    "Los valores son indicativos: IMERG tiene píxeles de ~11 km, por lo que en "
    "municipios pequeños (La Virginia, Dosquebradas) la lluvia refleja el campo "
    "regional. La amenaza proviene del Mapa Nacional del SGC (2015, escala "
    "1:100.000) y los eventos del SIMMA (descarga del "
    f"{riesgo.fecha_corte_sgc()}). La pérdida de vegetación debe verificarse "
    "contra la imagen en color real antes de cualquier decisión."
)

st.divider()
st.markdown("#### Semáforo de atención con umbrales ajustables")
st.caption(
    "Cada municipio recibe de 0 a 3 puntos por la lluvia de 30 días (frente a la "
    "referencia de 20 años) y de 0 a 3 puntos por la proporción de su área en "
    "amenaza alta y muy alta; la suma define el nivel. Los umbrales de partida son "
    "provisionales: mueva los controles para ver cómo cambia el orden de los "
    "municipios y calibre el criterio con el SGC, el IDEAM y el inventario de "
    "eventos. No es un nivel de alerta oficial.")
_DEF = {"ul1": 100, "ul2": 130, "ul3": 170, "ua1": 30, "ua2": 60, "ua3": 80,
        "cm": 3, "ca": 5}
for _k, _v in _DEF.items():
    st.session_state.setdefault(_k, _v)


def _reset_umbrales() -> None:
    for _k, _v in _DEF.items():
        st.session_state[_k] = _v


sc1, sc2, sc3 = st.columns(3)
with sc1:
    st.markdown("**Lluvia 30 d (% de la referencia)**")
    st.slider("Suma 1 punto desde", 50, 300, key="ul1")
    st.slider("Suma 2 puntos desde", 50, 300, key="ul2")
    st.slider("Suma 3 puntos desde", 50, 300, key="ul3")
with sc2:
    st.markdown("**Área en amenaza alta y muy alta (%)**")
    st.slider("Suma 1 punto desde ", 0, 100, key="ua1")
    st.slider("Suma 2 puntos desde ", 0, 100, key="ua2")
    st.slider("Suma 3 puntos desde ", 0, 100, key="ua3")
with sc3:
    st.markdown("**Nivel según la suma (0 a 6)**")
    st.slider("Moderado desde", 1, 6, key="cm")
    st.slider("Alto desde", 2, 6, key="ca")
    st.button("Restablecer umbrales de partida", on_click=_reset_umbrales)

_ul = tuple(sorted((st.session_state["ul1"], st.session_state["ul2"], st.session_state["ul3"])))
_ua = tuple(sorted((st.session_state["ua1"], st.session_state["ua2"], st.session_state["ua3"])))
_cm = st.session_state["cm"]
_ca = max(st.session_state["ca"], _cm + 1)
_cortes = (_cm - 1, _ca - 1)

_filas_sem = []
for _, r in df.iterrows():
    pl = itv._puntos(r["pct_normal_30d"], _ul)
    pa = itv._puntos(r["alta_muy_alta"], _ua)
    n_aj = itv.nivel_con_umbrales(r["pct_normal_30d"], r["alta_muy_alta"], _ul, _ua, _cortes)
    n_df = riesgo.nivel_atencion(None if pd.isna(r["pct_normal_30d"]) else r["pct_normal_30d"],
                                 r["alta_muy_alta"])
    orden_n = {"Bajo": 0, "Moderado": 1, "Alto": 2}
    cambio = "="
    if n_aj in orden_n and n_df in orden_n and n_aj != n_df:
        cambio = "↑ sube" if orden_n[n_aj] > orden_n[n_df] else "↓ baja"
    _filas_sem.append({
        "Municipio": r["nombre"], "Lluvia 30 d (% ref.)": r["pct_normal_30d"],
        "Amenaza alta y muy alta (%)": r["alta_muy_alta"],
        "Puntos lluvia": pl, "Puntos amenaza": pa,
        "Suma": None if pl is None or pa is None else pl + pa,
        "Nivel ajustado": n_aj, "Nivel de partida": n_df, "Cambio": cambio})
sem = pd.DataFrame(_filas_sem).sort_values(
    ["Suma", "Lluvia 30 d (% ref.)"], ascending=False, na_position="last")

mk1, mk2, mk3 = st.columns(3)
for _col, _n in zip((mk1, mk2, mk3), ("Alto", "Moderado", "Bajo")):
    _a, _b = int((sem["Nivel ajustado"] == _n).sum()), int((sem["Nivel de partida"] == _n).sum())
    _col.metric(f"Municipios en nivel {_n.lower()}", _a, delta=f"{_a - _b:+d} frente a los umbrales de partida",
                delta_color="off")


def _color_nivel(v):
    c = riesgo.COLOR_NIVEL.get(v)
    return "" if c is None else f"background-color:{c};color:{'#000' if v == 'Moderado' else '#fff'}"


st.dataframe(
    sem.style.map(_color_nivel, subset=["Nivel ajustado", "Nivel de partida"]).format(
        {"Lluvia 30 d (% ref.)": "{:.0f}", "Amenaza alta y muy alta (%)": "{:.0f}",
         "Puntos lluvia": "{:.0f}", "Puntos amenaza": "{:.0f}", "Suma": "{:.0f}"},
        na_rep="s/d"),
    hide_index=True, use_container_width=True)
_umb = pd.DataFrame([
    {"Parámetro": "Lluvia 30 d: 1, 2 y 3 puntos desde (% de la referencia)", "Valor": " / ".join(map(str, _ul))},
    {"Parámetro": "Amenaza alta y muy alta: 1, 2 y 3 puntos desde (%)", "Valor": " / ".join(map(str, _ua))},
    {"Parámetro": "Nivel moderado desde (suma)", "Valor": _cortes[0] + 1},
    {"Parámetro": "Nivel alto desde (suma)", "Valor": _cortes[1] + 1}])
st.download_button(
    "Descargar semáforo (Excel)",
    itv.excel_bytes({"Semáforo": sem, "Umbrales": _umb}, [
        "Nivel de atención provisional: no es un nivel de alerta oficial.",
        "Cada variable aporta de 0 a 3 puntos (uno por umbral superado); la suma define el nivel.",
        "Los umbrales de partida (100/130/170 % y 30/60/80 %) deben validarse con el SGC, el IDEAM y el inventario de eventos de CARDER."]),
    file_name=f"semaforo_risaralda_{dt.date.today().isoformat()}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.divider()

st.markdown("#### Fuentes de datos")
st.markdown(
    """
| Fuente | Producto GEE | Resolución | Latencia aprox. | Uso en el SAT |
|---|---|---|---|---|
| NASA GPM **IMERG V07** | `NASA/GPM_L3/IMERG_V07` | ~11 km / 30 min | 1–2 días | Lluvia casi en tiempo real |
| UCSB **CHIRPS** | `UCSB-CHG/CHIRPS/DAILY` + `PENTAD` | ~5.5 km / diario | 2–3 semanas | Series y climatología 20 años |
| ECMWF **ERA5-Land** | `ECMWF/ERA5_LAND/DAILY_AGGR` | ~11 km / diario | ~6 días | Contraste de patrones temporales |
| **Sentinel-2** SR | `COPERNICUS/S2_SR_HARMONIZED` | 10–20 m / ~5 días | horas–días | Óptico + índices de vegetación |
| **Landsat 8/9** C2L2 | `LANDSAT/LC08·LC09/C02/T1_L2` | 30 m / ~8 días | ~1 día | Óptico histórico |
| **Sentinel-1** GRD | `COPERNICUS/S1_GRD` | ~10 m / ~12 días | ~1 día | Radar (penetra nubes) |

> **Nota sobre ERA5-Land en montaña andina:** tiende a sobreestimar la lluvia
> orográfica; úselo para patrones y tendencias, no para magnitudes absolutas.
> Para valores absolutos son más confiables CHIRPS e IMERG.
"""
)

st.caption(
    "Monitoreo Satelital de Movimientos en Masa · Risaralda · datos calculados "
    "en vivo desde Google Earth Engine sobre los polígonos DIVIPOLA (DANE). "
)

pie_institucional()
