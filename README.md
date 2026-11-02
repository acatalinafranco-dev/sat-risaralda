# 🛰️ Monitoreo Satelital de Movimientos en Masa · Risaralda

Sistema de monitoreo **100 % satelital** para el departamento de Risaralda
(código DANE 66) y sus **14 municipios**. Calcula precipitación y cobertura
vegetal en vivo desde **Google Earth Engine (GEE)** sobre los polígonos
oficiales (DIVIPOLA), con foco en la detección temprana de condiciones
asociadas a **movimientos en masa**.

Desarrollado para la **Corporación Autónoma Regional de Risaralda - CARDER**,
Subdirección para el Conocimiento y la Reducción del Riesgo - SCORE.

> **Créditos.** Adaptación de la aplicación *Monitoreo Satelital de Movimientos
> en Masa · Pajarito (Boyacá)* desarrollada por J. A. Alpala (2026),
> Subdirección para el Conocimiento del Riesgo, Unidad Nacional para la
> Gestión del Riesgo de Desastres (UNGRD), reutilizada con su autorización.

Construido con **Streamlit + earthengine-api + leafmap + Plotly**, sin bases
de datos ni backend intermedio: se despliega directo desde GitHub a Streamlit
Community Cloud.

## Módulos

En la barra lateral se elige **«Todo Risaralda»** o uno de los 14 municipios;
las tres páginas de análisis se calculan sobre esa selección.

| Página | Contenido |
|---|---|
| **Inicio** | Mapa de los 14 municipios, estado de conexión GEE, **tabla comparativa por municipio** (lluvia 7 y 30 días, pérdida de vegetación en ha) con descarga en CSV, fuentes de datos |
| **🌧️ Precipitación** | Series diarias IMERG · CHIRPS · ERA5-Land (7 / 30 / 180 / 365 días) · mapas interpolados de lluvia acumulada · climatología CHIRPS de 20 años |
| **🛰️ Imágenes satelitales** | Catálogo filtrable de escenas Sentinel-2, Landsat 8/9 y Sentinel-1 (radar), GOES-Este y MODIS/VIIRS diario |
| **🌿 Índices de vegetación** | NDVI / NDMI / BSI · detección de cambios ΔNDVI con estimación de área de pérdida severa · serie mensual de NDVI |

> **IDEAM (red terrestre):** pendiente para una segunda iteración.

## Municipios

Apía, Balboa, Belén de Umbría, Dosquebradas, Guática, La Celia, La Virginia,
Marsella, Mistrató, Pereira, Pueblo Rico, Quinchía, Santa Rosa de Cabal y
Santuario.

## 1. Ejecución local

Requisitos: Python 3.10+ y una cuenta de Google habilitada en
[Earth Engine](https://code.earthengine.google.com) con un proyecto de
Google Cloud registrado para EE.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac: source .venv/bin/activate)

pip install -r requirements.txt

# Autenticación GEE (una sola vez; abre el navegador)
earthengine authenticate

# Proyecto de EE
set EE_PROJECT=sat-risaralda          # Windows CMD
# $env:EE_PROJECT="sat-risaralda"     # PowerShell

streamlit run app.py
```

Alternativa al `set EE_PROJECT`: copie `.streamlit/secrets.toml.example` como
`.streamlit/secrets.toml` y defina solo la línea `ee_project = "..."`.

### Notas de rendimiento

- Todo se calcula **en vivo** en GEE y queda en caché (`st.cache_data`,
  1 h para series/mapas, 24 h para climatologías). La clave del caché incluye
  el municipio elegido.
- «Todo Risaralda» con 1 año de IMERG suma ~17.500 imágenes de 30 minutos: la
  primera carga puede tardar 1–2 minutos. Las siguientes son inmediatas.
- La tabla comparativa de la página de inicio se calcula una vez al día para
  los 14 municipios (la primera carga puede tardar unos minutos).
- La zona andina es muy nubosa: si Sentinel-2 no muestra escenas, suba el
  umbral de nubosidad o use el compuesto mediano / Sentinel-1 (radar).

## 2. Despliegue en Streamlit Community Cloud

1. El código vive en el repositorio de GitHub (rama `main`).
2. En [share.streamlit.io](https://share.streamlit.io) cree la app apuntando
   al repositorio (`app.py` como archivo principal).
3. En **Settings → Secrets** pegue el contenido de
   `.streamlit/secrets.toml.example` con los valores reales de la llave JSON
   de la cuenta de servicio de Earth Engine. **Nunca suba la llave JSON al
   repositorio.**

El módulo `src/gee_session.py` detecta automáticamente el modo: secrets
(Cloud) → variable `GEE_CREDENTIALS_JSON` (ruta a JSON) → credenciales
locales de `earthengine authenticate`.

## Estructura

```
├── app.py                      # Inicio: mapa, comparativo, fuentes
├── pages/
│   ├── 1_Precipitacion.py      # Series + mapas + climatología 20 años
│   ├── 2_Imagenes_Satelitales.py  # S2 / Landsat / S1 con filtros
│   └── 3_Indices_Vegetacion.py    # NDVI/NDMI/BSI + ΔNDVI + serie
├── src/
│   ├── gee_session.py          # Auth GEE + geometría del municipio elegido
│   ├── gee_comparativo.py      # Tabla comparativa de los 14 municipios
│   ├── gee_precipitacion.py    # IMERG/CHIRPS/ERA5: series, mapas, climatología
│   ├── gee_imagenes.py         # Catálogos y tiles S2/Landsat/S1
│   ├── gee_indices.py          # Índices y detección de cambios
│   ├── gibs.py                 # Capas NASA GIBS
│   └── ui.py                   # Identidad CARDER, selector, mapas, leyendas
├── data/
│   ├── risaralda.geojson             # Departamento (DIVIPOLA, simplificado)
│   └── risaralda_municipios.geojson  # 14 municipios (código, nombre, área)
├── logo/carder-logo.png
├── .streamlit/                 # Tema claro CARDER + plantilla de secrets
└── requirements.txt
```

## Fuentes y créditos

NASA GPM IMERG V07 · UCSB-CHG CHIRPS · ECMWF ERA5-Land · Copernicus
Sentinel-1/2 · USGS Landsat 8/9 · Google Earth Engine · límites municipales
DANE (DIVIPOLA/MGN). Aplicación original: J. A. Alpala (UNGRD).

> **Descargo:** herramienta indicativa de monitoreo, de apoyo al conocimiento
> del riesgo en el marco de la Ley 1523 de 2012. No reemplaza los sistemas
> oficiales de alerta del IDEAM y el Servicio Geológico Colombiano, ni las
> decisiones de los consejos municipales y departamental de gestión del
> riesgo.

**Contacto:** agalindo@carder.gov.co · Subdirección para el Conocimiento y la
Reducción del Riesgo - SCORE · CARDER.
