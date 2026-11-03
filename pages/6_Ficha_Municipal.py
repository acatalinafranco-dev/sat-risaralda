"""Página: ficha municipal de seguimiento en PDF (una página por municipio)."""
from __future__ import annotations

import datetime as dt
import io
import sys
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import riesgo
from src.comparativo_cache import comparativo_compartido
from src.ficha import generar_ficha
from src.gee_session import codigo_activo, es_departamento, lista_municipios
from src.ui import conectar_gee, encabezado, pie_institucional

st.set_page_config(page_title="Ficha municipal · SAT Risaralda", layout="wide",
                   page_icon="📄", initial_sidebar_state="expanded")

encabezado(
    "📄 Ficha municipal de seguimiento",
    "Resumen de **una página** por municipio, con el nivel de atención, la "
    "lluvia, la amenaza y los eventos del SIMMA. Pensada para reuniones del "
    "consejo de gestión del riesgo y para informes de seguimiento.",
)

if not conectar_gee():
    st.stop()

hoy = dt.date.today().isoformat()
with st.spinner("Calculando los indicadores de los 14 municipios "
                "(la primera carga del día puede tardar unos minutos)..."):
    try:
        res = comparativo_compartido(hoy)
    except Exception as exc:  # noqa: BLE001
        st.error(f"No fue posible calcular los indicadores: {exc}")
        st.stop()

if res.get("errores"):
    st.warning("Algunos indicadores no se pudieron calcular y aparecen como "
               "«s/d» en la ficha: " + "; ".join(res["errores"]))

am = riesgo.amenaza_municipal().set_index("codigo")
pts = riesgo.puntos_simma()
filas = {f["codigo"]: f for f in res["filas"]}


def _pdf(codigo: str) -> bytes:
    f = filas[codigo]
    a = am.loc[codigo].to_dict()
    p = pts[pts["codigo"] == codigo]
    nivel = riesgo.nivel_atencion(f.get("pct_normal_30d"), a.get("alta_muy_alta"))
    return generar_ficha(
        f, nivel, a, p["tipo"].value_counts().to_dict(),
        int((p["origen"] == "Inventario").sum()))


nombres = dict(lista_municipios())
codigos = [c for c, _ in lista_municipios()]
defecto = codigos.index(codigo_activo()) if not es_departamento() else 0
cod = st.selectbox("Municipio", codigos, index=defecto,
                   format_func=lambda c: nombres[c])

f = filas[cod]
a = am.loc[cod]
nivel = riesgo.nivel_atencion(f.get("pct_normal_30d"), a["alta_muy_alta"])
k1, k2, k3, k4 = st.columns(4)
k1.metric("Nivel de atención", nivel)
k2.metric("Lluvia 30 d respecto a la normal",
          "s/d" if pd.isna(f.get("pct_normal_30d") or float("nan"))
          else f"{f['pct_normal_30d']:.0f} %")
k3.metric("Área en amenaza alta y muy alta", f"{a['alta_muy_alta']:.0f} %")
k4.metric("Eventos SIMMA", int((pts["codigo"] == cod).sum()))

pdf = _pdf(cod)
st.download_button(f"Descargar ficha de {nombres[cod]} (PDF)", pdf,
                   file_name=f"ficha_{nombres[cod].lower().replace(' ', '_')}_{hoy}.pdf",
                   mime="application/pdf", type="primary")

st.divider()
st.markdown("#### Las 14 fichas en un solo archivo")
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    for c in codigos:
        z.writestr(f"ficha_{nombres[c].lower().replace(' ', '_')}_{hoy}.pdf", _pdf(c))
st.download_button("Descargar las 14 fichas (ZIP)", buf.getvalue(),
                   file_name=f"fichas_risaralda_{hoy}.zip", mime="application/zip")
st.caption(
    "El nivel de atención es provisional: sus umbrales deben validarse con el "
    "SGC, el IDEAM y CARDER. La ficha no sustituye las alertas oficiales."
)
pie_institucional()
