"""Página: fuentes de información y referencias de la aplicación."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import riesgo
from src.ui import encabezado, pie_institucional

st.set_page_config(page_title="Fuentes y referencias · SAT Risaralda", layout="wide",
                   page_icon="📚", initial_sidebar_state="expanded")

encabezado(
    "📚 Fuentes y referencias",
    "Origen de los datos y referencias técnicas que sustentan cada módulo de la "
    "aplicación. Todos los productos se procesan en Google Earth Engine, salvo "
    "los indicados como consulta directa.",
)

st.markdown("### Datos de precipitación")
st.dataframe(pd.DataFrame([
    {"Fuente": "GPM IMERG", "Proveedor": "NASA",
     "Uso en la aplicación": "Lluvia reciente: series, mapas diarios y acumulados de 7 y 30 días.",
     "Resolución": "≈ 11 km · diaria",
     "Enlace": "https://gpm.nasa.gov/data/imerg"},
    {"Fuente": "CHIRPS v2", "Proveedor": "Climate Hazards Center, Universidad de California en Santa Bárbara",
     "Uso en la aplicación": "Climatología de 20 años y «normal» de 30 días para el porcentaje respecto a la normal.",
     "Resolución": "≈ 5 km · diaria · desde 1981",
     "Enlace": "https://www.chc.ucsb.edu/data/chirps"},
    {"Fuente": "ERA5-Land", "Proveedor": "ECMWF / Servicio de Cambio Climático de Copernicus",
     "Uso en la aplicación": "Serie de precipitación de reanálisis, como tercera referencia.",
     "Resolución": "≈ 9 km · horaria",
     "Enlace": "https://cds.climate.copernicus.eu"},
    {"Fuente": "Estaciones del IDEAM (consulta directa)", "Proveedor": "IDEAM, datos abiertos",
     "Uso en la aplicación": "Contraste de la lluvia satelital con estaciones.",
     "Resolución": "Puntual · diaria",
     "Enlace": "https://www.datos.gov.co"},
]), hide_index=True, use_container_width=True,
    column_config={"Enlace": st.column_config.LinkColumn("Enlace")})

st.markdown("### Imágenes satelitales y radar")
st.dataframe(pd.DataFrame([
    {"Fuente": "Sentinel-2 SR armonizado", "Proveedor": "ESA / Copernicus",
     "Uso en la aplicación": "Color real, falso color e índices de vegetación (NDVI, NDMI, BSI) y pérdida de vegetación.",
     "Resolución": "10 a 20 m · revisita de ~5 días",
     "Enlace": "https://sentinels.copernicus.eu"},
    {"Fuente": "Landsat 8 y 9, Colección 2 Nivel 2", "Proveedor": "USGS / NASA",
     "Uso en la aplicación": "Imágenes ópticas complementarias.",
     "Resolución": "30 m · revisita de ~8 días",
     "Enlace": "https://www.usgs.gov/landsat-missions"},
    {"Fuente": "Sentinel-1 GRD (banda C, VV)", "Proveedor": "ESA / Copernicus",
     "Uso en la aplicación": "Radar: imágenes, cambio de retrodispersión y puntos de interés.",
     "Resolución": "≈ 10 m (procesado a 30 m) · revisita de ~12 días",
     "Enlace": "https://sentinels.copernicus.eu"},
    {"Fuente": "NISAR (banda L, consulta directa)", "Proveedor": "NASA / ISRO, distribuido por el ASF DAAC",
     "Uso en la aplicación": "Catálogo de escenas disponibles sobre Risaralda.",
     "Resolución": "Según producto · repetición de 12 días",
     "Enlace": "https://nisar-docs.asf.alaska.edu"},
    {"Fuente": "GOES-Este, MODIS y VIIRS", "Proveedor": "NOAA / NASA, vía NASA GIBS",
     "Uso en la aplicación": "Monitoreo de nubosidad casi en tiempo real.",
     "Resolución": "10 min (GOES) · diaria (MODIS/VIIRS)",
     "Enlace": "https://earthdata.nasa.gov/gibs"},
    {"Fuente": "NASADEM", "Proveedor": "NASA JPL",
     "Uso en la aplicación": "Elevación y pendiente del terreno.",
     "Resolución": "≈ 30 m",
     "Enlace": "https://doi.org/10.5067/MEaSUREs/NASADEM/NASADEM_HGT.001"},
]), hide_index=True, use_container_width=True,
    column_config={"Enlace": st.column_config.LinkColumn("Enlace")})

st.markdown("### Amenaza, eventos y límites territoriales")
st.dataframe(pd.DataFrame([
    {"Fuente": "Mapa Nacional de Amenaza por Movimientos en Masa (2015, escala 1:100.000)",
     "Proveedor": "Servicio Geológico Colombiano (SGC)",
     "Uso en la aplicación": "Porcentaje del área municipal en amenaza baja, media, alta y muy alta.",
     "Enlace": "https://geoportal.sgc.gov.co"},
    {"Fuente": "SIMMA: inventario y catálogo de movimientos en masa",
     "Proveedor": "Servicio Geológico Colombiano (SGC)",
     "Uso en la aplicación": f"Eventos históricos (descarga del {riesgo.fecha_corte_sgc()}).",
     "Enlace": "https://simma.sgc.gov.co"},
    {"Fuente": "Mapa de susceptibilidad por movimientos en masa",
     "Proveedor": "Servicio Geológico Colombiano (SGC)",
     "Uso en la aplicación": "Capa de susceptibilidad en la página Amenaza y eventos.",
     "Enlace": "https://geoportal.sgc.gov.co"},
    {"Fuente": "DIVIPOLA: límites del departamento y los municipios",
     "Proveedor": "DANE",
     "Uso en la aplicación": "Polígonos de análisis y división municipal.",
     "Enlace": "https://www.dane.gov.co"},
]), hide_index=True, use_container_width=True,
    column_config={"Enlace": st.column_config.LinkColumn("Enlace")})

st.markdown("### Referencias técnicas")
st.markdown(
    """
- Funk, C., Peterson, P., Landsfeld, M. *et al.* (2015). The climate hazards
  infrared precipitation with stations — a new environmental record for
  monitoring extremes. *Scientific Data*, 2, 150066.
  [doi:10.1038/sdata.2015.66](https://doi.org/10.1038/sdata.2015.66)
- Muñoz-Sabater, J. *et al.* (2021). ERA5-Land: a state-of-the-art global
  reanalysis dataset for land applications. *Earth System Science Data*, 13,
  4349–4383. [doi:10.5194/essd-13-4349-2021](https://doi.org/10.5194/essd-13-4349-2021)
- Gorelick, N. *et al.* (2017). Google Earth Engine: planetary-scale geospatial
  analysis for everyone. *Remote Sensing of Environment*, 202, 18–27.
  [doi:10.1016/j.rse.2017.06.031](https://doi.org/10.1016/j.rse.2017.06.031)
- Organización Meteorológica Mundial (2017). *Directrices de la OMM para el
  cálculo de las normales climáticas* (WMO-No. 1203). Ginebra.
- NASA JPL (2020). *NASADEM Merged DEM Global 1 arc second V001*. NASA EOSDIS
  Land Processes DAAC.
  [doi:10.5067/MEaSUREs/NASADEM/NASADEM_HGT.001](https://doi.org/10.5067/MEaSUREs/NASADEM/NASADEM_HGT.001)
"""
)

st.markdown("### Marco normativo y origen de la aplicación")
st.markdown(
    """
- **Ley 1523 de 2012**, por la cual se adopta la Política Nacional de Gestión
  del Riesgo de Desastres y se establece el Sistema Nacional de Gestión del
  Riesgo de Desastres.
- **Aplicación original:** *Monitoreo Satelital de Movimientos en Masa*,
  desarrollada por J. A. Alpala (Unidad Nacional para la Gestión del Riesgo de
  Desastres, UNGRD) para el municipio de Pajarito, Boyacá. La versión para
  Risaralda es una adaptación de la Corporación Autónoma Regional de Risaralda
  (CARDER), Subdirección para el Conocimiento y la Reducción del Riesgo (SCORE).
"""
)
st.caption(
    "Los enlaces dirigen a las páginas oficiales de cada proveedor. Los datos se "
    "usan con fines de apoyo al conocimiento del riesgo; esta herramienta no "
    "sustituye las alertas oficiales del IDEAM ni del SGC."
)
pie_institucional()
