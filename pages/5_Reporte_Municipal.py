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
from src import sectores as sec
from src.reporte import generar_reporte
from src.ui import conectar_gee, encabezado, pie_institucional

st.set_page_config(page_title="Reporte municipal · Monitoreo satelital Risaralda", layout="wide",
                   page_icon="📄", initial_sidebar_state="expanded")

encabezado(
    "📄 Reporte semanal municipal",
    "Documento en PDF con la situación de la semana: lluvia, sectores para seguimiento, "
    "sitios conocidos con cambio detectado por satélite y acciones sugeridas. "
    "**Es informativo: no constituye una alerta.**",
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

st.caption("El reporte se prepara con la información de la semana que termina hoy. "
           "La primera consulta del día puede tardar 2 a 3 minutos.")

if st.button(f"Preparar el reporte de {nombre}", type="primary"):
    feats = geojson_municipios()["features"]
    f = next(x for x in feats if x["properties"]["codigo"] == cod)
    otros = [x["geometry"] for x in feats if x is not f]
    errores = []
    with st.spinner("Consultando la lluvia (IMERG y CHIRPS)..."):
        try:
            lluvia = mon.lluvia_municipio(cod, hoy)
        except Exception as exc:  # noqa: BLE001
            lluvia, _ = None, errores.append(f"lluvia: {exc}")
    sectores = None
    if sec.disponible():
        with st.spinner("Calificando los sectores de la semana..."):
            try:
                cal = sec.calificar_semana(hoy)
                sectores = {"fecha": dt.date.fromisoformat(hoy).strftime("%d/%m/%Y"),
                            "resumen": sec.resumen(cal, cod),
                            "tabla": sec.agregar_puntos(sec.sectores(cal, cod), cal["fecha"],
                                                        max_n=28)}
            except Exception as exc:  # noqa: BLE001
                errores.append(f"sectores de la semana: {exc}")
    sitios = None
    with st.spinner("Revisando cambios satelitales en los sitios conocidos..."):
        try:
            sitios = sec.sitios_semana(hoy, cod)
        except Exception as exc:  # noqa: BLE001
            errores.append(f"cambios en sitios conocidos: {exc}")
    with st.spinner("Armando el PDF..."):
        pdf = generar_reporte(cod, nombre, f["geometry"], otros, lluvia, sectores, sitios, hoy)
    st.session_state["_reporte"] = (cod, hoy, pdf)
    for e in errores:
        st.warning(f"No fue posible calcular {e}. El reporte indica «s/d» en ese campo.")

if st.session_state.get("_reporte", (None,))[0] == cod:
    _, fecha, pdf = st.session_state["_reporte"]
    st.download_button(f"Descargar el reporte de {nombre} (PDF)", pdf,
                       file_name=f"reporte_mm_{nombre.lower().replace(' ', '_')}_{fecha}.pdf",
                       mime="application/pdf")
    st.success("Reporte listo. Revíselo antes de enviarlo.")

with st.expander("¿Qué contiene el reporte?"):
    st.markdown("""
1. **Página 1 · La semana:** mensaje principal, cuatro indicadores (lluvia de 7 días,
   lluvia de 30 días frente a lo habitual, sectores para seguimiento y sitios conocidos con
   cambio), mapa y lista de los sitios conocidos donde el satélite detectó cambios esta
   semana (máximo 20 por municipio).
2. **Página 2 · Contexto:** lluvia diaria de los últimos 60 días frente a la referencia
   histórica, evidencia satelital, acciones sugeridas, sustento técnico y fundamento en la
   Ley 1523 de 2012.
3. **Página 3 · Sectores de la semana:** mapa e indicadores de los sectores de 300 m para
   seguimiento y tabla con el punto sugerido para verificar en cada uno.
""")
pie_institucional()
