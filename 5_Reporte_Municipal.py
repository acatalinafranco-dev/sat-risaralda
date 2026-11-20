"""Página: reporte informativo municipal de movimientos en masa (PDF)."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import monitoreo as mon
from src import susceptibilidad as sus
from src.gee_session import codigo_activo, es_departamento, geojson_municipios, lista_municipios
from src.reporte import generar_reporte
from src.ui import conectar_gee, encabezado, pie_institucional

st.set_page_config(page_title="Reporte municipal · SAT Risaralda", layout="wide",
                   page_icon="📄", initial_sidebar_state="expanded")

encabezado(
    "📄 Reporte informativo municipal",
    "Documento en PDF para la **Alcaldía y el Consejo Municipal de Gestión del Riesgo "
    "de Desastres**: mensaje principal, mapa de susceptibilidad con los sitios "
    "priorizados, lluvia reciente, cambio de cobertura, acciones sugeridas y "
    "sustento técnico. **Es informativo: no constituye una alerta.**",
)

if not sus.disponible():
    st.warning("Los productos del modelo aún no están cargados en la aplicación.")
    pie_institucional()
    st.stop()
if not conectar_gee():
    st.stop()

nombres = dict(lista_municipios())
codigos = [c for c, _ in lista_municipios()]
defecto = 0 if es_departamento() else codigos.index(codigo_activo())
cod = st.selectbox("Municipio", codigos, index=defecto, format_func=lambda c: nombres[c])
nombre = nombres[cod]
hoy = dt.date.today().isoformat()

res = sus.resumen_municipio(cod)
k1, k2, k3, k4 = st.columns(4)
k1.metric("Sitios con movimiento confirmado", res["n_sitios"])
k2.metric("En seguimiento prioritario", res["por_nivel"]["Seguimiento prioritario"])
k3.metric("Susceptibilidad alta y muy alta", f"{res['alta_muy_alta']:.0f} % del área")
k4.metric("Sitios con viviendas expuestas", res["con_viviendas"])

incluir_cambio = st.toggle(
    "Incluir el monitoreo satelital de cambios (modelo de cambio)",
    value=mon.disponible_cambio(), disabled=not mon.disponible_cambio(),
    help="Agrega las zonas con cambio reciente compatible con movimientos en masa. "
         "Puede tardar 1 a 2 minutos la primera vez del día.")

if st.button(f"Preparar el reporte de {nombre}", type="primary"):
    feats = geojson_municipios()["features"]
    f = next(x for x in feats if x["properties"]["codigo"] == cod)
    otros = [x["geometry"] for x in feats if x is not f]
    errores = []
    with st.spinner("Consultando lluvia (IMERG y CHIRPS)..."):
        try:
            lluvia = mon.lluvia_municipio(cod, hoy)
        except Exception as exc:  # noqa: BLE001
            lluvia, _ = None, errores.append(f"lluvia: {exc}")
    with st.spinner("Calculando cambio de cobertura (Sentinel-2)..."):
        try:
            veg = mon.vegetacion_municipio(cod, hoy)
        except Exception as exc:  # noqa: BLE001
            veg, _ = None, errores.append(f"vegetación: {exc}")
    cambio = None
    if incluir_cambio:
        with st.spinner("Aplicando el modelo de cambio satelital..."):
            try:
                cambio = mon.cambios_municipio(mon.cambios_recientes(hoy), cod)
            except Exception as exc:  # noqa: BLE001
                errores.append(f"monitoreo de cambios: {exc}")
    with st.spinner("Armando el PDF..."):
        pdf = generar_reporte(cod, nombre, f["geometry"], otros, lluvia, veg, cambio)
    st.session_state["_reporte"] = (cod, hoy, pdf)
    for e in errores:
        st.warning(f"No fue posible calcular {e}. El reporte indica «s/d» en ese campo.")

if st.session_state.get("_reporte", (None,))[0] == cod:
    _, fecha, pdf = st.session_state["_reporte"]
    st.download_button(f"Descargar el reporte de {nombre} (PDF)", pdf,
                       file_name=f"reporte_mm_{nombre.lower().replace(' ', '_')}_{fecha}.pdf",
                       mime="application/pdf")
    st.success("Reporte listo. Revíselo antes de enviarlo: los sitios y niveles deben "
               "confirmarse con la información de campo más reciente.")

with st.expander("Qué contiene el reporte"):
    st.markdown("""
1. **Página 1:** mensaje principal en lenguaje claro, cuatro indicadores, mapa de
   susceptibilidad del municipio con los sitios críticos numerados y la tabla de
   sitios priorizados (vereda o barrio, nivel, susceptibilidad, elementos expuestos,
   coordenadas y fecha de la última visita).
2. **Página 2:** lluvia diaria de los últimos 60 días frente a la referencia
   histórica, visitas por año, mapa de cambio de vegetación, zonas con cambio
   satelital reciente, acciones sugeridas por nivel, método, validación, límites,
   fundamento en la Ley 1523 de 2012 y fuentes.
3. **Anexo:** lista completa de sitios cuando no caben en la primera página.

Los nombres de evaluadores y los datos personales de las fichas no se incluyen. La
coordinación departamental se cita como fuente de la información de visitas.
""")
pie_institucional()
