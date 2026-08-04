# DOCUMENTACION.md · Monitoreo Satelital de Movimientos en Masa · Pajarito (Boyacá) — Memoria técnica del proyecto

> **Propósito de este archivo.** Memoria de arquitectura y operación del
> aplicativo, pensada para que cualquier ingeniero —o un asistente de IA—
> pueda retomar el desarrollo sin contexto previo. Describe la estructura de
> directorios, la función de cada archivo, las decisiones técnicas ya
> tomadas (y sus porqués), y el flujo de sincronización local → GitHub →
> Streamlit Cloud. Mantener actualizado con cada cambio estructural.

**Última actualización:** 2026-07-31 · **Responsable:** Jorge A. Alpala,
Subdirección para el Conocimiento del Riesgo, UNGRD ·
jorge.alpala@gestiondelriesgo.gov.co

---

## 1. Qué es este aplicativo

Sistema de Alerta Temprana (SAT) **100 % satelital** para el municipio de
**Pajarito, Boyacá** (código DANE `15518`, piedemonte llanero, ~313 km²).
Monitorea precipitación y cobertura vegetal calculando **en vivo** desde
**Google Earth Engine (GEE)** sobre el polígono municipal oficial
(DIVIPOLA), con foco en condiciones precursoras de **movimientos en masa**.

- **Stack:** Python 3.10+ · Streamlit (multipágina) · earthengine-api ·
  leafmap/folium (mapas) · Plotly (gráficas) · pandas.
- **Arquitectura:** *sin* backend ni base de datos. Streamlit habla directo
  con GEE; NASA GIBS se consume como tiles públicos. Todo el estado vive en
  el código + cachés de Streamlit.
- **Despliegue:** GitHub (`jorgealpala/sat-pajarito-boyaca`, rama `main`) →
  Streamlit Community Cloud (auto-redespliegue con cada push).
- **Marco legal:** herramienta de apoyo al conocimiento del riesgo. En el
  marco de la **Ley 1523 de 2012** NO sustituye SAT físicos/comunitarios,
  protocolos CMGRD/CDGRD ni alertas oficiales de IDEAM/SGC (descargo visible
  en el pie de todas las páginas).

## 2. Estructura de directorios

```
sat_pajarito/
├── app.py                        # Ventana "Inicio": branding, mapa, fuentes, estado GEE
├── DOCUMENTACION.md              # ESTE archivo (memoria técnica)
├── README.md                     # Guía de instalación local y despliegue
├── requirements.txt              # Dependencias pip
├── .gitignore                    # Excluye credenciales, venv, cachés
├── .streamlit/
│   ├── config.toml               # Tema (base oscura, primario naranja UNGRD #F7941D)
│   └── secrets.toml.example      # Plantilla de secrets (NUNCA commitear el real)
├── data/
│   └── pajarito.geojson          # Polígono municipal DIVIPOLA simplificado (~12 KB)
├── logo/
│   └── ungrd-horizontal.png      # Logo institucional (local; la app tolera su ausencia)
├── pages/                        # Páginas Streamlit (orden = prefijo numérico)
│   ├── 1_Precipitacion.py
│   ├── 2_Imagenes_Satelitales.py
│   └── 3_Indices_Vegetacion.py
└── src/                          # Lógica de negocio (importable, sin UI salvo ui.py)
    ├── __init__.py
    ├── gee_session.py            # Autenticación GEE + geometría del municipio
    ├── gee_precipitacion.py      # IMERG/CHIRPS/ERA5: series, grillas de mapas, climatología
    ├── gee_imagenes.py           # Catálogos y tiles S2 / Landsat / S1 / GOES
    ├── gee_indices.py            # NDVI/NDMI/BSI, ΔNDVI, serie NDVI
    ├── gibs.py                   # Capas diarias NASA GIBS (MODIS/VIIRS, sin GEE)
    └── ui.py                     # Branding UNGRD, mapas base, leyendas, pie legal
```

Archivos **solo locales** (ignorados por git, requeridos en producción vía
secrets): `gee-key.json` (service account), `.streamlit/secrets.toml`,
`.venv/`.

## 3. Qué hace cada archivo

### 3.1 Raíz

| Archivo | Función |
|---|---|
| `app.py` | Página de inicio. Muestra logo/branding UNGRD, línea de la Subdirección y la Entidad, mapa del municipio (Esri + contorno amarillo), tabla de fuentes de datos con latencias, verificación de conexión GEE (`conectar_gee`) y pie institucional. No hace cálculos pesados. |
| `requirements.txt` | `streamlit, earthengine-api, leafmap, folium, plotly, pandas`. Streamlit Cloud lo instala en cada deploy. |
| `.gitignore` | Crítico: excluye `gee-key.json`, `secrets.toml`, `*credentials*.json`, `.venv/`, `__pycache__/`. Verificar SIEMPRE antes de un push. |

### 3.2 `src/gee_session.py` — sesión y geometría

- `init_ee()` (cacheada con `st.cache_resource`): autenticación GEE en
  cascada, en este orden:
  1. `st.secrets["gee_service_account"]` → **Streamlit Cloud** (producción).
  2. Variable de entorno `GEE_CREDENTIALS_JSON` = ruta al JSON → **local**
     (modo usado en desarrollo: `$env:GEE_CREDENTIALS_JSON = "...\gee-key.json"`).
  3. Credenciales de `earthengine authenticate` + `EE_PROJECT`.
- `MUNICIPIO`: dict con nombre, DANE, lat/lon (5.3823, −72.6967), área.
- `roi()` → `ee.Geometry` del polígono; `roi_buffer_km(km)` → buffer para
  mapas de contexto; `bounds_municipio()` → para `fit_bounds`.
- `tiles_de(img, vis)` → URL XYZ vía `getMapId` (usada por todos los mapas GEE).

> **Para adaptar a OTRO municipio:** reemplazar `data/<municipio>.geojson`
> (extraído de DIVIPOLA por `MpCodigo`), actualizar `MUNICIPIO` y
> `RUTA_GEOJSON`. Nada más depende de Pajarito.

### 3.3 `src/gee_precipitacion.py` — módulo de lluvia

- Fuentes homogeneizadas a colecciones diarias (banda `precipitation`, mm/día):
  `_diaria_chirps` (CHIRPS DAILY), `_diaria_era5` (ERA5-Land DAILY_AGGR,
  m→mm), `_diaria_imerg` (suma diaria de imágenes de 30 min × 0.5).
- Constantes: `ESCALA` (resolución por fuente: 11132/5566/11132 m) y
  `LATENCIA_DIAS` (imerg 2, chirps 21, era5 6) — se usan para acotar "el
  dato más reciente disponible".
- `_rango(dias)`: **ventana calendario ÚNICA** para las tres fuentes
  (hoy−días → hoy). Cada curva termina donde su latencia se lo permite; los
  días sin dato se **omiten** (centinela −9999), no se rellenan con 0.
- `serie_diaria(fuente, dias)` → media zonal diaria sobre el polígono
  (una sola llamada `getInfo` sobre una FeatureCollection).
- `grilla_acumulados(fuente, modo)` → 8 submapas ('dias'|'semanas'|'meses')
  con escala de color **fija por modo** (`VIS_GRILLA`: 0-60 / 0-250 /
  0-600 mm) para comparabilidad. Meses = calendario completo. Para IMERG
  mensual usa `_mes_imerg_hibrido` (producto MONTHLY si existe; si no,
  reconstruye desde 30 min — lógica portada de la app IMERG de GEE del autor).
- `climatologia_chirps(20)` y `mapa_media_anual_chirps(20)` → promedio
  mensual multianual y mapa de media anual (CHIRPS PENTAD).
- `_interpolar(img, escala_m)`: **⚠ decisión crítica** — antes de
  `resample('bilinear')` sobre un compuesto (`.sum()`), fija
  `setDefaultProjection(EPSG:4326 @ escala nativa)`. Sin esto, EE asigna al
  compuesto una proyección de 1° y los tiles fallan **silenciosamente**
  (mapa vacío, sin excepción). No eliminar.

### 3.4 `src/gee_imagenes.py` — sensores de imagen

- **Sentinel-2** (`COPERNICUS/S2_SR_HARMONIZED`): `escenas_s2` (catálogo
  dedupe por fecha, filtro `CLOUDY_PIXEL_PERCENTAGE`), `tiles_s2` (escena o
  compuesto mediano). Visualizaciones en `VIS_S2`: color real, falso color
  vegetación, SWIR.
- **Landsat 8/9** (`LC08/LC09 C02 T1_L2`): `_landsat_sr` aplica factores de
  escala (×0.0000275 −0.2) y máscara QA_PIXEL (bits 3 nube, 4 sombra).
  `VIS_LANDSAT` con gamma 1.3-1.35 (contraste equiparado a S2).
  `tiles_landsat_pan`: **pansharpening HSV** con la banda pancromática B8
  (15 m) — requiere la colección **TOA** (`T1_TOA`; el SR no trae B8), por
  eso los tonos difieren levemente del SR.
- **Sentinel-1** (`COPERNICUS/S1_GRD`, modo IW): catálogo por polarización
  VV/VH, escena o compuesto mediano en dB (vis −22 a 0).
- **GOES-Este** (`goes_escena`): última imagen full-disk de las últimas
  12 h con *fallback* `GOES-19 → GOES-16 → GOES-18` (el catálogo GEE cambia
  según relevo operativo). Productos: GeoColor aproximado (verde sintético
  0.45·C02+0.10·C03+0.45·C01), Visible C02, Infrarrojo C13 (día y noche).
  `_cmi()` aplica escala/offset desde metadatos por banda.
  **⚠ NO hacer `.clip()` sobre imágenes GOES**: están en proyección
  geoestacionaria y el clip con polígonos geodésicos lanza
  `Can't transform (0,0)`. Los tiles solo se calculan donde se mira.

### 3.5 `src/gibs.py` — NASA GIBS (sin GEE)

Cinco capas diarias de color real de NASA Worldview vía tiles XYZ públicos
(sin autenticación, sin cuota GEE): MODIS Terra/Aqua (250 m) y VIIRS
S-NPP/NOAA-20/NOAA-21 (375 m). `url_tiles(capa, fecha)` construye la URL
WMTS (`GoogleMapsCompatible_Level9`: máximo zoom nativo z9; en folium se
declara `max_native_zoom=9` y se amplía). Latencia 3-5 h tras el paso.

**Fuentes evaluadas y descartadas** (documentar para no re-evaluar):
Meteosat-9/11 (miran Índico/África — no ven Colombia), Himawari-8
(Asia-Pacífico, además retirado), GOES-17 (en reserva desde 2023).
GOES-Este es el único geoestacionario con vista continua de Colombia.

### 3.6 `src/gee_indices.py` — vegetación y movimientos en masa

- `_s2_limpia`: S2 con máscara de nubes **Cloud Score+**
  (`GOOGLE/CLOUD_SCORE_PLUS`, umbral cs ≥ 0.60) — más robusta que QA60 en
  piedemonte nuboso.
- Índices: NDVI (B8,B4), NDMI (B8,B11), BSI (suelo desnudo).
- `mapa_cambio_ndvi(ref, actual)`: **producto central del SAT de
  movimientos en masa**. ΔNDVI continuo + máscara magenta de pérdida severa
  (ΔNDVI < umbral y NDVI_ref > 0.4) + área afectada en ha dentro del
  municipio (`pixelArea`).
- `serie_ndvi_mensual(meses)`: NDVI medio municipal por mes (meses sin
  escenas limpias se omiten con centinela −9999).

### 3.7 `src/ui.py` — interfaz compartida e identidad UNGRD

- Constantes institucionales (ÚNICO lugar para cambiarlas):
  `AZUL_UNGRD=#003087`, `NARANJA_UNGRD=#F7941D`, `DEPENDENCIA`, `ENTIDAD`,
  `CONTACTO`, `CITA`.
- `branding_institucional()`: logo + dependencia en la barra lateral (el
  logo se pinta sobre **tarjeta blanca** porque el PNG trae texto oscuro
  ilegible en tema oscuro; si `logo/ungrd-horizontal.png` no existe, se
  omite sin romper).
- `encabezado(t, s)`: branding + título + franja degradada azul→naranja.
  Todas las páginas lo llaman → el branding aparece en todas las ventanas.
- `pie_institucional()`: descargo Ley 1523 + citación + contacto. Llamado
  al final de `app.py` y de las 3 páginas.
- `mapa_base(zoom, basemap)`: **⚠ Esri.WorldImagery se agrega por URL
  directa** (`server.arcgisonline.com/.../World_Imagery`), no por
  `add_basemap`, porque el catálogo de leafmap instalado no reconoce ese
  nombre (fallaba en silencio → quedaba OSM).
- `agregar_contorno` (polígono amarillo), `ajustar_al_municipio(m, margen)`
  (fit_bounds; margen chico ≈ zoom municipal, grande ≈ regional),
  `leyenda_continua` (barra de color min→max en HTML).
- `conectar_gee()`: envuelve `init_ee` con mensaje de error accionable.
- Diccionarios compartidos: `COLOR_FUENTE`, `NOMBRE_FUENTE`, `MESES_ES`.

### 3.8 `pages/` — las tres ventanas

**`1_Precipitacion.py`** — orden de secciones: serie **diaria** comparada →
acumulado **semanal** (barras, semanas lunes-domingo; proxy de saturación
del suelo) → acumulado **mensual** → **grillas de 8 submapas** (fuente ×
modo días/semanas/meses, media municipal bajo cada submapa, leyenda común)
→ **climatología CHIRPS 20 años** (barras mensuales + mapa media anual).
Ventanas de análisis: 7/30/180/365 días.

**`2_Imagenes_Satelitales.py`** — selector `st.radio` de 5 sensores:
S2 / Landsat (checkbox pancromática 15 m en color real) / S1 / GOES-Este /
MODIS-VIIRS GIBS. **⚠ Se usa radio y NO `st.tabs` a propósito**: Leaflet
dentro de pestañas ocultas se inicializa con tamaño 0 y `fitBounds`
resuelve zoom 0 (vista mundial). El radio además evita consultar a GEE los
sensores no visibles.

**`3_Indices_Vegetacion.py`** — índice actual (NDVI/NDMI/BSI, compuesto
30/60/90 días) → ΔNDVI referencia vs. reciente con umbral ajustable y área
de pérdida severa → serie mensual de NDVI (12-36 meses).

### 3.9 Política de caché y frescura de datos (decisión de diseño)

- Excepciones **no** se cachean: las funciones `@st.cache_data` llaman al
  backend sin try/except; las páginas envuelven con `_seguro()` →
  `{"__error__": ...}`. Así un fallo transitorio (permisos IAM, red) no
  queda pegado hasta vencer el TTL.
- **La fecha de consulta (`HOY`) forma parte de la clave del caché** en
  series, grillas, climatología y serie NDVI: una consulta en un día
  distinto SIEMPRE recalcula con los datos más recientes; dentro del día,
  el TTL evita recalcular y protege la cuota GEE.
- TTLs: series/grillas/índices 1 h · catálogos de escenas 30 min ·
  climatologías 24 h · **GOES 5 min** (clave = intervalo de 5 min actual).
- "Más reciente disponible" está acotado por la **latencia de la fuente**
  (no por la app): IMERG hoy−2 d, ERA5 hoy−6 d, CHIRPS hoy−2/3 sem;
  GOES minutos, GIBS horas.

## 4. Credenciales y permisos (GEE)

- Service account actual: proyecto `geovolcanes-scr-piloto` (compartido con
  GeoVolcanes; **pendiente** migrar a uno dedicado).
- Roles IAM requeridos en el proyecto: **Earth Engine Resource Writer**
  (sin él, las series funcionan pero `getMapId` falla con
  `Permission 'earthengine.maps.create' denied`) y Service Usage Consumer.
  El service account debe estar **registrado** en Earth Engine.
- Local: `$env:GEE_CREDENTIALS_JSON = "C:\...\sat_pajarito\gee-key.json"`.
- Producción: mismo JSON traducido a TOML en Secrets de Streamlit Cloud
  (formato en `.streamlit/secrets.toml.example`; el `private_key` va en una
  línea conservando los `\n` literales).

## 5. Flujo de trabajo: local → GitHub → Streamlit Cloud

### 5.1 Ejecutar en local (PowerShell)

```powershell
cd C:\Users\MSI\Downloads\sat_boyaca_pajarito\sat_pajarito
.\.venv\Scripts\Activate.ps1
$env:GEE_CREDENTIALS_JSON = "C:\Users\MSI\Downloads\sat_boyaca_pajarito\sat_pajarito\gee-key.json"
streamlit run app.py
```

Primera vez en una máquina nueva: `python -m venv .venv` → activar →
`pip install -r requirements.txt` (si PowerShell bloquea scripts:
`Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`).

Durante el desarrollo: cambios en `pages/` → tecla `R` (Rerun) basta;
cambios en `src/` → reiniciar (`Ctrl+C` → `streamlit run app.py`); si se
tocó lógica de tiles/series ya cacheada → tecla `C` → *Clear cache*.

### 5.2 Sincronizar cambios (el ciclo estándar)

```powershell
# 1. Probar en local que todo funciona
# 2. Revisar qué se va a subir (NUNCA debe listar gee-key.json ni secrets.toml)
git status
# 3. Subir
git add .
git commit -m "descripcion corta del cambio"
git push
```

**Streamlit Cloud redespliega SOLO con cada `git push` a `main`** (1-3 min;
progreso en share.streamlit.io → la app → *Manage app*). No hay que hacer
nada más. Equivalente visual en VS Code: panel *Control de código fuente* →
✓ Commit → ↑ Push.

Reglas del flujo:
- Los **secrets** de producción se cambian en share.streamlit.io →
  *Settings → Secrets* (reinicia la app solo); jamás por git.
- El logo y `gee-key.json` viven fuera del historial si se rotan: el logo
  SÍ está versionado; la llave NUNCA.
- Si la app pública falla tras un push: *Manage app* → log de build; para
  volver atrás, `git revert HEAD` + `git push`.
- Nuevas dependencias: agregarlas a `requirements.txt` (el deploy las
  instala; en local, `pip install <paquete>` en el venv).

### 5.3 URLs del proyecto

- Repo: `https://github.com/jorgealpala/sat-pajarito-boyaca`
- App: URL asignada por Streamlit Cloud (visible en share.streamlit.io).
- Plan gratuito: la app "duerme" tras días sin uso y despierta sola en
  ~30 s; el caché es compartido entre usuarios.

## 6. Errores ya resueltos (no reintroducir)

| Síntoma | Causa raíz | Solución vigente |
|---|---|---|
| Mapas de lluvia/climatología vacíos, sin error | `resample('bilinear')` sobre compuesto sin proyección fija → tiles fallan en silencio | `_interpolar()`: `setDefaultProjection` antes de resample |
| `Permission 'earthengine.maps.create' denied` | Faltaba rol IAM al service account | Earth Engine Resource Writer en el proyecto |
| Error de permisos "pegado" 1 h tras corregirlo | El caché guardaba también los errores | Excepciones fuera del caché (`_seguro`) |
| Landsat/S1 con vista mundial (zoom 0) | Leaflet + `st.tabs`: contenedor oculto de tamaño 0 | Selector `st.radio` en vez de pestañas |
| GOES: `Image.clip: Can't transform (0.0,0.0)` | Clip geodésico sobre proyección geoestacionaria | No clipear imágenes GOES |
| Esri.WorldImagery no cargaba (quedaba OSM) | `add_basemap` no reconocía el nombre y el error se silenciaba | Tile Esri por URL directa en `mapa_base` |
| Series IMERG/ERA5 "vacías" al inicio de la ventana | Cada fuente usaba una ventana distinta (desplazada por su latencia) | Ventana calendario única `_rango(dias)` |
| Días sin dato graficados como 0 mm | `None → 0` en la reducción | Centinela −9999 y omisión del día |

## 7. Pendientes / hoja de ruta

1. **Umbrales de alerta** (convierte el monitoreo en SAT operativo): bandas
   amarilla/naranja/roja sobre acumulados de 24 h y 7 días, calibradas con
   la climatología CHIRPS de 20 años ya disponible.
2. **Integración IDEAM** (red terrestre de estaciones) — señalizada como
   pendiente en la UI desde la v1.
3. **Service account dedicado** (proyecto GCP propio del SAT, separado de
   GeoVolcanes) y rotación de la llave actual.
4. Posibles: descarga de reportes (PDF/CSV), multi-municipio (la
   arquitectura ya lo permite, ver §3.2), notificaciones.

## 8. Cómo citar

> Alpala, J. A. (2026). *Monitoreo Satelital de Movimientos en Masa,
> Pajarito (Boyacá): seguimiento hidrometeorológico y de cobertura vegetal
> con Google Earth Engine.*
> Subdirección para el Conocimiento del Riesgo, Unidad Nacional para la
> Gestión del Riesgo de Desastres (UNGRD). Aplicación web Streamlit.

Contacto: jorge.alpala@gestiondelriesgo.gov.co
