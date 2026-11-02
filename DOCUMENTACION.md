# DOCUMENTACION.md · Monitoreo Satelital de Movimientos en Masa · Risaralda — Memoria técnica

**Última actualización:** 2026-11-02 · **Responsable:** Subdirección para el
Conocimiento y la Reducción del Riesgo - SCORE, Corporación Autónoma Regional
de Risaralda - CARDER · agalindo@carder.gov.co

> **Origen y créditos.** Esta aplicación es una adaptación, autorizada por su
> autor, de la aplicación *Monitoreo Satelital de Movimientos en Masa ·
> Pajarito (Boyacá)* desarrollada por J. A. Alpala (2026), Subdirección para el
> Conocimiento del Riesgo, Unidad Nacional para la Gestión del Riesgo de
> Desastres (UNGRD). La lógica de cálculo (IMERG, CHIRPS, ERA5-Land,
> Sentinel-1/2, Landsat, índices de vegetación) proviene de esa aplicación.

## 1. Propósito y alcance

Sistema de monitoreo **100 % satelital** de apoyo al conocimiento del riesgo
por movimientos en masa en el departamento de **Risaralda** (código DANE 66) y
sus **14 municipios**: Apía, Balboa, Belén de Umbría, Dosquebradas, Guática,
La Celia, La Virginia, Marsella, Mistrató, Pereira, Pueblo Rico, Quinchía,
Santa Rosa de Cabal y Santuario. Todo se calcula en vivo en Google Earth
Engine (GEE) sobre los polígonos DIVIPOLA; no hay base de datos ni backend.

No sustituye los sistemas de alerta temprana ni los protocolos de los consejos
de gestión del riesgo (Ley 1523 de 2012).

## 2. Cambios frente a la aplicación original

| Aspecto | Original (Pajarito) | Esta versión (Risaralda) |
|---|---|---|
| Unidad de análisis | 1 municipio fijo | «Todo Risaralda» o 1 de 14 municipios, elegido en la barra lateral |
| Geometría | `pajarito.geojson` | `risaralda.geojson` (departamento) + `risaralda_municipios.geojson` (14 municipios) |
| Caché | Clave sin municipio | Clave incluye el municipio (`cache_mun` en `src/ui.py`) |
| Comparativo | No existe | Tabla de los 14 municipios en la página de inicio (`src/gee_comparativo.py`) |
| Identidad | UNGRD, tema oscuro | CARDER, tema claro (verde `#008A4B`, azul `#004B87`, amarillo `#FFCC00`) |

## 3. Estructura del código

```
app.py                         Inicio: mapa de municipios, estado GEE, comparativo, fuentes
pages/1_Precipitacion.py       Series diarias, acumulados, mapas, climatología CHIRPS 20 años
pages/2_Imagenes_Satelitales.py  Sentinel-2, Landsat 8/9, Sentinel-1, GOES, MODIS/VIIRS
pages/3_Indices_Vegetacion.py  NDVI/NDMI/BSI, ΔNDVI, serie mensual
src/gee_session.py             Autenticación GEE y geometría de la unidad activa
src/gee_comparativo.py         Lluvia y pérdida de vegetación por municipio (reduceRegions)
src/gee_precipitacion.py       Productos de precipitación
src/gee_imagenes.py            Catálogos y tiles ópticos / radar
src/gee_indices.py             Índices de vegetación y detección de cambios
src/gibs.py                    Capas NASA GIBS
src/ui.py                      Identidad CARDER, selector de municipio, mapas, pie legal
data/                          GeoJSON en WGS84 (EPSG:4326)
```

### 3.1 Selección de municipio

`src/ui.py › selector_municipio()` dibuja el selector en la barra lateral y
guarda el código en `st.session_state["mun_codigo"]` (`"66"` = departamento;
`"66001"` = Pereira, etc.). `src/gee_session.py` expone `roi()`,
`roi_buffer_km()`, `bounds_municipio()` y `geojson_municipio()`, que devuelven
siempre la geometría de la unidad activa, de modo que los módulos de cálculo
no cambian. Las funciones cacheadas usan `@cache_mun(ttl=...)`, que añade el
código del municipio a la clave de `st.cache_data`.

### 3.2 Comparativo de municipios

`src/gee_comparativo.py › tabla_comparativa()` hace una consulta por
indicador, independiente del municipio elegido:

- **Lluvia:** suma IMERG diaria de los últimos 7 y 30 días, interpolada
  bilinealmente, con media zonal por municipio (`reduceRegions`, 1 km).
- **Pérdida de vegetación:** ΔNDVI de Sentinel-2 (últimos 60 días frente a
  hace 6–12 meses, máscara Cloud Score+ ≥ 0,60); se cuentan los píxeles con
  ΔNDVI < −0,20 y NDVI de referencia > 0,4, en hectáreas y como % del área.

IMERG tiene píxeles de ~11 km: en municipios pequeños la lluvia refleja el
campo regional. Los valores son indicativos y deben verificarse contra
imágenes en color real.

### 3.3 Fuentes de datos

| Fuente | Producto GEE | Resolución | Latencia |
|---|---|---|---|
| NASA GPM IMERG V07 | `NASA/GPM_L3/IMERG_V07` | ~11 km / 30 min | 1–2 días |
| UCSB CHIRPS | `UCSB-CHG/CHIRPS/DAILY`, `PENTAD` | ~5,5 km / diario | 2–3 semanas |
| ECMWF ERA5-Land | `ECMWF/ERA5_LAND/DAILY_AGGR` | ~11 km / diario | ~6 días |
| Sentinel-2 SR | `COPERNICUS/S2_SR_HARMONIZED` | 10–20 m | horas–días |
| Landsat 8/9 C2L2 | `LANDSAT/LC08·LC09/C02/T1_L2` | 30 m | ~1 día |
| Sentinel-1 GRD | `COPERNICUS/S1_GRD` | ~10 m | ~1 día |

## 4. Datos geográficos

Capas DANE (DIVIPOLA/MGN), originalmente en MAGNA-SIRGAS CTM12, convertidas a
WGS84 y simplificadas (~100 m). Cada municipio trae `codigo` (DANE, 5 dígitos),
`nombre` y `area_km2`.

## 5. Autenticación y despliegue

- Proyecto de Google Cloud con Earth Engine habilitado (uso no comercial):
  `sat-risaralda`.
- Cuenta de servicio con los roles «Editor de Earth Engine (Beta)» y
  «Consumidor de Service Usage».
- En Streamlit Community Cloud, en **Settings → Secrets**, se pegan
  `ee_project` y el bloque `[gee_service_account]` (ver
  `.streamlit/secrets.toml.example`). **La llave JSON no se sube nunca a
  GitHub.**
- Modos de autenticación (`src/gee_session.py › init_ee`): secrets de
  Streamlit → variable `GEE_CREDENTIALS_JSON` → credenciales locales de
  `earthengine authenticate`.
- Streamlit Cloud redespliega automáticamente con cada cambio en `main`.

## 6. Pendientes

- Integrar estaciones del IDEAM (red terrestre).
- Revisar los colores contra el manual de identidad de la CARDER.
- La elegibilidad de Earth Engine no comercial debe renovarse según la
  vigencia indicada en la consola de Google Cloud.

## 7. Cómo citar

> Corporación Autónoma Regional de Risaralda - CARDER (2026). Monitoreo
> Satelital de Movimientos en Masa, Risaralda: seguimiento hidrometeorológico
> y de cobertura vegetal con Google Earth Engine. Subdirección para el
> Conocimiento y la Reducción del Riesgo - SCORE. Aplicación web Streamlit.
> Adaptación de la aplicación desarrollada por J. A. Alpala (2026),
> Subdirección para el Conocimiento del Riesgo, UNGRD.

Contacto: agalindo@carder.gov.co
