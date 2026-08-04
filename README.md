# 🛰️ Monitoreo Satelital de Movimientos en Masa · Pajarito, Boyacá

Sistema de monitoreo **100 % satelital** para el municipio de Pajarito
(Boyacá, código DANE 15518), en el piedemonte llanero. Monitorea precipitación
y cobertura vegetal en vivo desde **Google Earth Engine (GEE)** sobre el
polígono oficial del municipio (DIVIPOLA), con foco en la detección temprana
de condiciones asociadas a **movimientos en masa**.

Construido con **Streamlit + earthengine-api + leafmap + Plotly**, sin bases
de datos ni backend intermedio: corre local y se despliega directo desde
GitHub a Streamlit Community Cloud.

## Módulos

| Página | Contenido |
|---|---|
| **Inicio** | Área de monitoreo, estado de conexión GEE, fuentes de datos |
| **🌧️ Precipitación** | Series diarias IMERG · CHIRPS · ERA5-Land (7 / 30 / 180 / 365 días) sobre el polígono municipal · mapas interpolados de lluvia acumulada (3 días a 6 meses, IMERG/ERA5) · climatología CHIRPS de los últimos 20 años (mensual + mapa de media anual) |
| **🛰️ Imágenes satelitales** | Catálogo filtrable (fechas + nubosidad) de escenas Sentinel-2, Landsat 8/9 y Sentinel-1 (radar), con color real, falso color, SWIR y SAR |
| **🌿 Índices de vegetación** | NDVI / NDMI / BSI · detección de cambios ΔNDVI con estimación de área de pérdida severa (candidatas a movimientos en masa) · serie mensual de NDVI municipal |

> **IDEAM (red terrestre):** pendiente para una segunda iteración.

## 1. Ejecución local

Requisitos: Python 3.10+ y una cuenta de Google habilitada en
[Earth Engine](https://code.earthengine.google.com) con un proyecto de
Google Cloud registrado para EE.

```bash
# En C:\Users\MSI\Downloads\sat_boyaca_pajarito (o donde prefiera)
cd sat_pajarito

python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac: source .venv/bin/activate)

pip install -r requirements.txt

# Autenticación GEE (una sola vez; abre el navegador)
earthengine authenticate

# Indique su proyecto de EE (reemplace por el suyo)
set EE_PROJECT=mi-proyecto-ee   # Windows CMD
# $env:EE_PROJECT="mi-proyecto-ee"   # PowerShell

streamlit run app.py
```

Alternativa al `set EE_PROJECT`: copie `.streamlit/secrets.toml.example` como
`.streamlit/secrets.toml` y defina solo la línea `ee_project = "..."`.

### Notas de rendimiento

- Todo se calcula **en vivo** en GEE y queda en caché (`st.cache_data`,
  1 h para series/mapas, 24 h para climatologías).
- La ventana de **1 año con IMERG** suma ~17.500 imágenes de 30 minutos: la
  primera carga puede tardar 1–2 minutos. Las siguientes son inmediatas.
- El piedemonte es muy nuboso: si Sentinel-2 no muestra escenas, suba el
  umbral de nubosidad o use el compuesto mediano / Sentinel-1 (radar).

## 2. Despliegue en GitHub + Streamlit Cloud

1. Cree el repositorio y suba el proyecto (el `.gitignore` ya excluye
   credenciales):

   ```bash
   git init
   git add .
   git commit -m "SAT satelital Pajarito - version inicial"
   git branch -M main
   git remote add origin https://github.com/<usuario>/sat-pajarito-boyaca.git
   git push -u origin main
   ```

2. Cree un **service account** de GEE (recomendado para producción):
   - En Google Cloud Console → IAM → *Service accounts* → crear cuenta y
     descargar la llave JSON.
   - Regístrela en Earth Engine:
     <https://developers.google.com/earth-engine/guides/service_account>

3. En [share.streamlit.io](https://share.streamlit.io) cree la app apuntando
   al repo (`app.py` como entrypoint) y en **Settings → Secrets** pegue el
   contenido de `secrets.toml.example` con los valores reales del JSON del
   service account.

El módulo `src/gee_session.py` detecta automáticamente el modo: secrets
(Cloud) → variable `GEE_CREDENTIALS_JSON` (ruta a JSON) → credenciales
locales de `earthengine authenticate`.

## Estructura

```
sat_pajarito/
├── app.py                      # Inicio
├── pages/
│   ├── 1_Precipitacion.py      # Series + mapas + climatología 20 años
│   ├── 2_Imagenes_Satelitales.py  # S2 / Landsat / S1 con filtros
│   └── 3_Indices_Vegetacion.py    # NDVI/NDMI/BSI + ΔNDVI + serie
├── src/
│   ├── gee_session.py          # Auth GEE + geometría municipal
│   ├── gee_precipitacion.py    # IMERG/CHIRPS/ERA5: series, mapas, climatología
│   ├── gee_imagenes.py         # Catálogos y tiles S2/Landsat/S1
│   ├── gee_indices.py          # Índices y detección de cambios
│   └── ui.py                   # Componentes compartidos (mapas, leyendas)
├── data/pajarito.geojson       # Polígono municipal DIVIPOLA simplificado
├── .streamlit/                 # Tema + plantilla de secrets
└── requirements.txt
```

## Fuentes y créditos

NASA GPM IMERG V07 · UCSB-CHG CHIRPS · ECMWF ERA5-Land · Copernicus
Sentinel-1/2 · USGS Landsat 8/9 · Google Earth Engine · límites municipales
DANE (DIVIPOLA/MGN).

> **Descargo:** herramienta indicativa de monitoreo. No reemplaza los
> sistemas oficiales de alerta del IDEAM, el SGC ni la UNGRD.
