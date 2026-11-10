"""Página: Imágenes satelitales · Sentinel-2, Landsat 8/9 y Sentinel-1.

Catálogo filtrable (rango de fechas + nubosidad) de escenas disponibles sobre
el polígono seleccionado (Risaralda o un municipio), con visualizaciones
ópticas y de radar.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import folium
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import gee_imagenes as gi
from src import gibs
from src.ui import (cache_mun, agregar_contorno, ajustar_al_municipio, conectar_gee,
                    encabezado, mapa_base, pie_institucional)

st.set_page_config(page_title="Satelital · SAT Risaralda", layout="wide",
                   page_icon="🛰️", initial_sidebar_state="expanded")

encabezado(
    "🛰️ Imágenes satelitales · {mun}",
    "Catálogo de escenas **Sentinel-2**, **Landsat 8/9** y **Sentinel-1 "
    "(radar)**, más monitoreo casi en tiempo real con **GOES-Este** "
    "(cada 10 min) y **MODIS/VIIRS diario** (NASA GIBS).",
)

with st.expander("📖 Guía: cómo leer las imágenes satelitales y cuál sensor usar",
                 expanded=False):
    st.markdown(
        "Esta página reúne imágenes de varios satélites. Cada uno observa la "
        "superficie de una forma distinta, por lo que ninguno sustituye a los "
        "demás: se complementan. La guía explica qué mide cada sensor, cómo "
        "interpretar lo que se ve en pantalla y cuáles son sus límites."
    )
    t1, t2, t3, t4, t5, t6 = st.tabs([
        "Óptico y radar", "Sentinel-2 y Landsat", "Sentinel-1 (radar)",
        "Escena, mosaico y compuesto", "GOES y MODIS/VIIRS",
        "Limitaciones y fuentes"])

    with t1:
        st.markdown(
            """
**Sensor óptico (Sentinel-2, Landsat).** Mide la luz solar reflejada por la
superficie, en el espectro visible y el infrarrojo. Produce imágenes
semejantes a una fotografía, fáciles de interpretar a simple vista. Requiere
luz diurna y no atraviesa las nubes.

**Sensor de radar (Sentinel-1).** Emite sus propias ondas de microondas y mide
la fracción que regresa al satélite (retrodispersión). Funciona de día y de
noche y atraviesa nubes y lluvia. La imagen no representa colores, sino la
rugosidad, la humedad y la estructura de la superficie, por lo que exige una
lectura distinta.

| Aspecto | Óptico | Radar |
|---|---|---|
| Fuente de energía | Luz solar | Señal propia del satélite |
| Nubes y lluvia | Las bloquean | Las atraviesa |
| Día y noche | Solo de día | Ambos |
| Qué mide | Color y reflectancia | Rugosidad, humedad y estructura |
| Lectura | Intuitiva | Requiere conocimiento previo |
| Uso principal | Cicatrices, cobertura, uso del suelo | Cambios bajo nubes, superficies expuestas |

**Cuándo usar cada uno.** En Risaralda la nubosidad es frecuente, de modo que
una escena óptica puede quedar parcial o cubierta. El radar garantiza una
observación periódica; el óptico permite confirmar e interpretar lo observado.
Lo recomendable es contrastar ambos.
"""
        )

    with t2:
        st.markdown(
            """
**Sentinel-2** (Programa Copernicus, ESA): resolución de 10 m en las bandas
visibles e infrarrojo cercano y de 20 m en el infrarrojo de onda corta, con una
revisita de unos 5 días.

**Landsat 8 y 9** (USGS y NASA): resolución de 30 m, revisita de unos 8 días y
registro histórico continuo desde 2013, útil para comparar fechas lejanas.

**Visualizaciones disponibles**

- **Color real:** bandas roja, verde y azul. Equivale a lo que percibiría el
  ojo humano. Permite reconocer cicatrices de movimientos en masa, suelo
  expuesto, cultivos, cuerpos de agua y nubes.
- **Falso color de vegetación:** incorpora el infrarrojo cercano, que la
  vegetación sana refleja con intensidad. La vegetación se ve en rojo; el suelo
  desnudo y las cicatrices recientes, en tonos cian o grises.
- **SWIR (infrarrojo de onda corta, solo Sentinel-2):** destaca la humedad del
  suelo, la roca expuesta y las áreas quemadas.
- **Nitidez de 15 m (solo Landsat en color real):** combina la imagen de 30 m
  con la banda pancromática para aumentar el detalle visual. No incorpora
  información nueva sobre la superficie.

**Nubosidad máxima de escena.** Filtra las escenas por el porcentaje de nubes
sobre toda la escena, no sobre el municipio. Una escena con poca nubosidad
global puede tener nubes sobre la zona de interés, y a la inversa.

**Cómo leer la imagen.** Las nubes aparecen en blanco y sus sombras en tono
oscuro; no deben confundirse con cambios en el terreno. Para detectar un
cambio real conviene comparar dos fechas con las mismas condiciones de
iluminación y visualización.
"""
        )

    with t3:
        st.markdown(
            """
**Qué muestra la imagen.** Cada píxel indica la intensidad de la señal que
regresa al satélite, expresada en decibelios (dB) y mostrada en escala de
grises (de −22 dB, oscuro, a 0 dB, claro). La banda utilizada es la C, con
longitud de onda cercana a 5,6 cm.

**Cómo interpretar los tonos**

- **Oscuro:** superficies lisas que desvían la señal lejos del satélite, como
  agua en calma, vías pavimentadas o suelos muy húmedos y planos. También las
  zonas de sombra de radar.
- **Claro:** superficies rugosas o estructuras que devuelven mucha señal, como
  zonas urbanas, bosque denso y laderas orientadas hacia el satélite.
- **Cambios entre fechas:** un cambio marcado puede relacionarse con remoción
  de vegetación o suelo, inundación o cambios de humedad. Requiere
  verificación, porque la humedad y la lluvia también modifican la señal.

**Polarización: VV y VH.** Indica la orientación de la onda emitida y la
recibida. La primera letra corresponde a la emisión y la segunda a la
recepción.

- **VV (emite vertical, recibe vertical):** responde sobre todo a la rugosidad y
  la humedad de la superficie. Es la polarización de referencia en esta
  aplicación para detectar cambios en laderas.
- **VH (emite vertical, recibe horizontal):** responde a la dispersión
  múltiple dentro de la vegetación, por lo que resalta la estructura del dosel.
  Es útil para diferenciar bosque de áreas abiertas.

**Órbita ascendente y descendente.** Sentinel-1 recorre la órbita de sur a
norte (ascendente) y de norte a sur (descendente), y en cada caso observa el
terreno con un ángulo lateral distinto.

- **Descendente:** pasa sobre Colombia en la mañana (cerca de las 6:00,
  hora local) y observa hacia el occidente.
- **Ascendente:** pasa en la tarde (cerca de las 18:00, hora local) y observa
  hacia el oriente.

En terreno montañoso esta diferencia es importante. Una ladera orientada hacia
el satélite aparece comprimida y muy brillante, y una ladera opuesta puede
quedar en sombra, con poca o ninguna información. Por eso una misma ladera se
ve distinta en cada órbita, y **no deben compararse imágenes de órbita
ascendente con imágenes de órbita descendente**. Para detectar cambios se
comparan fechas de la misma órbita y la misma polarización.

**Moteado (speckle).** El radar produce un aspecto granulado inherente a la
técnica. No corresponde a objetos reales. Los mosaicos y compuestos lo
atenúan.

**Mayor análisis.** La página *Radar SAR* calcula el cambio entre períodos y la
superficie con cambio fuerte sobre laderas.
"""
        )

    with t4:
        st.markdown(
            """
- **Escena individual:** una sola toma, de una fecha concreta. Es la imagen
  original, pero cubre una franja limitada: una escena óptica puede incluir
  nubes y una pasada de radar puede no abarcar todo el departamento.
- **Mosaico:** une las tomas más recientes (30 días en óptico y 12 días en
  radar) y conserva, en cada píxel, el valor más reciente. En óptico se omiten
  los píxeles con nubes y sombras. En radar se une una sola dirección de órbita,
  para mantener la comparabilidad. Permite cubrir todo el departamento, pero
  **no corresponde a una fecha única**: distintas zonas de la imagen pueden
  provenir de días diferentes.
- **Compuesto mediano del rango:** calcula, para cada píxel, el valor central
  de todas las tomas del rango de fechas elegido. Atenúa nubes, moteado y
  valores extremos. Resulta útil para observar una condición típica, pero no
  muestra un momento concreto.

En Sentinel-2 y Landsat, la opción por defecto es la escena original más
reciente; el mosaico es una opción adicional. En Sentinel-1, el mosaico
descendente de 12 días es la opción por defecto, porque cubre toda la zona.
"""
        )

    with t5:
        st.markdown(
            """
**GOES-Este.** Satélite geoestacionario ubicado a 75° de longitud oeste. Observa
de forma continua a Colombia y entrega una imagen cada 10 minutos. Su
resolución, de uno a dos kilómetros, permite una vista regional y no
municipal. Sirve para seguir la nubosidad y la convección que origina los
aguaceros. El producto infrarrojo (C13) funciona de día y de noche; los
productos visibles solo de día.

**MODIS y VIIRS (NASA GIBS).** Una imagen diaria en color real por satélite,
con resolución de 250 a 375 m. Se publica unas horas después del paso del
satélite. Permite ver el estado de la nubosidad y del territorio del día, sin
esperar a Sentinel o Landsat. Las franjas negras indican zonas no cubiertas por
el paso diario.

Estos productos describen condiciones atmosféricas y regionales. No tienen el
detalle necesario para identificar movimientos en masa individuales.
"""
        )

    with t6:
        st.markdown(
            """
**Limitaciones**

- Las imágenes son un apoyo para el conocimiento del riesgo; **no emiten
  alertas** ni sustituyen la verificación en campo.
- La nubosidad puede impedir el uso de las imágenes ópticas durante semanas.
- La resolución limita el tamaño de lo detectable: un movimiento en masa
  pequeño puede no ser visible en imágenes de 10 a 30 m.
- Las imágenes se muestran sin corrección de relieve adicional; en laderas muy
  pronunciadas, el radar presenta distorsiones geométricas.

**Fuentes**

- Sentinel-1 y Sentinel-2: Programa Copernicus, Agencia Espacial Europea (ESA).
  Torres, R. et al. (2012), *GMES Sentinel-1 mission*, Remote Sensing of
  Environment, 120, 9-24. Drusch, M. et al. (2012), *Sentinel-2: ESA's optical
  high-resolution mission for GMES operational services*, Remote Sensing of
  Environment, 120, 25-36.
- Landsat 8 y 9, Colección 2 Nivel 2: Servicio Geológico de los Estados Unidos
  (USGS) y NASA.
- GOES-Este (GOES-R): NOAA y NASA.
- MODIS y VIIRS: NASA, servicio GIBS (Worldview).
- Procesamiento: Google Earth Engine (Gorelick et al., 2017).

El listado completo se encuentra en la página *Fuentes y referencias*.
"""
        )

if not conectar_gee():
    st.stop()


@cache_mun(ttl=1800)
def _cat_s2(f0, f1, nubes):
    return gi.escenas_s2(f0, f1, nubes)


@cache_mun(ttl=1800)
def _cat_ls(f0, f1, nubes):
    return gi.escenas_landsat(f0, f1, nubes)


@cache_mun(ttl=1800)
def _cat_s1(f0, f1, pol):
    return gi.escenas_s1(f0, f1, pol)


@cache_mun(ttl=300)  # 5 min: casi tiempo real
def _goes(producto, _marca_tiempo):
    return gi.goes_escena(producto)


def _goes_fresco(producto):
    """Clave = intervalo de 5 min actual: cada consulta trae la última imagen."""
    marca = dt.datetime.utcnow().strftime("%Y-%m-%d %H:") + f"{dt.datetime.utcnow().minute // 5}"
    return _goes(producto, marca)


@cache_mun(ttl=1800)
def _tiles_pan(fecha, f0, f1, nubes):
    return gi.tiles_landsat_pan(fecha, f0, f1, nubes)


@cache_mun(ttl=1800)
def _tiles(sensor, *args):
    if sensor == "s2":
        return gi.tiles_s2(*args)
    if sensor == "ls":
        return gi.tiles_landsat(*args)
    return gi.tiles_s1(*args)


def _selector_fechas(clave: str, dias_atras: int = 120):
    hoy = dt.date.today()
    c1, c2 = st.columns(2)
    with c1:
        f0 = st.date_input("Desde", hoy - dt.timedelta(days=dias_atras),
                           key=f"{clave}_f0", max_value=hoy)
    with c2:
        f1 = st.date_input("Hasta", hoy, key=f"{clave}_f1", max_value=hoy)
    return f0.isoformat(), (f1 + dt.timedelta(days=1)).isoformat()


def _pintar(res: dict, altura: int = 560):
    m = mapa_base(zoom=12, basemap="Esri.WorldImagery")
    m.add_tile_layer(res["tiles_url"], name=f"{res['nombre']} · {res['etiqueta']}",
                     attribution="Google Earth Engine / Copernicus / USGS")
    agregar_contorno(m)
    ajustar_al_municipio(m, margen=0.008)  # zoom ceñido a la unidad elegida
    m.to_streamlit(height=altura)
    st.caption(f"**{res['nombre']}** — {res['etiqueta']}. {res['descripcion']}")


# Selector de sensor (radio en vez de st.tabs: los mapas Leaflet dentro de
# pestañas ocultas se inicializan con tamaño 0 y fitBounds resuelve zoom 0
# -> vista mundial. Con radio solo se renderiza -y se consulta a GEE- el
# sensor activo.
sensor = st.radio(
    "Sensor",
    ["Sentinel-2 (óptico 10 m)", "Landsat 8/9 (óptico 30 m)", "Sentinel-1 (radar)",
     "GOES-Este (cada 10 min)", "MODIS/VIIRS diario (NASA GIBS)"],
    horizontal=True,
    label_visibility="collapsed",
)
st.write("")

# --------------------------------------------------------------------------
# SENTINEL-2
# --------------------------------------------------------------------------
if sensor == "Sentinel-2 (óptico 10 m)":
    f0, f1 = _selector_fechas("s2")
    c1, c2 = st.columns(2)
    with c1:
        nubes = st.slider("Nubosidad máxima de escena (%)", 5, 100, 60, 5, key="s2_nb")
    with c2:
        vis = st.selectbox("Visualización", list(gi.VIS_S2.keys()),
                           format_func=lambda k: gi.VIS_S2[k]["nombre"], key="s2_vis")

    with st.spinner("Consultando catálogo Sentinel-2..."):
        escenas = _cat_s2(f0, f1, nubes)

    if not escenas:
        st.warning("Sin escenas S2 en el rango con ese umbral de nubes. "
                   "Amplíe fechas o suba el umbral (la zona es muy nubosa).")
    else:
        opciones = ["🗺️ Mosaico de 30 días sin nubes (cobertura completa)",
                    "🧩 Compuesto mediano del rango"] + [
            f"{e['fecha']}  ·  {e['nubes']:.0f}% nubes" for e in escenas
        ]
        sel = st.selectbox(f"Escena ({len(escenas)} disponibles)", opciones,
                           index=2, key="s2_sel",
            help="Una escena individual puede dejar partes del departamento con "
                 "nubes. El mosaico une las tomas de los últimos 30 días y deja, "
                 "en cada píxel, el último valor sin nube.")
        if sel.startswith("🗺️"):
            fecha = "ULT:30"
        elif sel.startswith("🧩"):
            fecha = None
        else:
            fecha = sel.split("·")[0].strip()

        with st.spinner("Generando visualización..."):
            res = _tiles("s2", vis, fecha, f0, f1, nubes)
        _pintar(res)

        with st.expander("📅 Calendario de escenas del rango"):
            st.dataframe(pd.DataFrame(escenas).rename(
                columns={"fecha": "Fecha", "nubes": "Nubes (%)"}),
                use_container_width=True, hide_index=True)

# --------------------------------------------------------------------------
# LANDSAT
# --------------------------------------------------------------------------
if sensor == "Landsat 8/9 (óptico 30 m)":
    f0, f1 = _selector_fechas("ls", dias_atras=365)
    c1, c2 = st.columns(2)
    with c1:
        nubes = st.slider("Nubosidad máxima de escena (%)", 5, 100, 70, 5, key="ls_nb")
    with c2:
        vis = st.selectbox("Visualización", list(gi.VIS_LANDSAT.keys()),
                           format_func=lambda k: gi.VIS_LANDSAT[k]["nombre"], key="ls_vis")

    with st.spinner("Consultando catálogo Landsat 8/9..."):
        escenas = _cat_ls(f0, f1, nubes)

    if not escenas:
        st.warning("Sin escenas Landsat en el rango con ese umbral. Landsat "
                   "revisita cada ~8 días (L8+L9): amplíe el rango de fechas.")
    else:
        opciones = ["🗺️ Mosaico de 30 días sin nubes (cobertura completa)",
                    "🧩 Compuesto mediano del rango"] + [
            f"{e['fecha']}  ·  {e['nubes']:.0f}% nubes  ·  {e['satelite']}"
            for e in escenas
        ]
        sel = st.selectbox(f"Escena ({len(escenas)} disponibles)", opciones,
                           index=2, key="ls_sel",
            help="Una escena individual puede dejar partes del departamento con "
                 "nubes. El mosaico une las tomas de los últimos 30 días y deja, "
                 "en cada píxel, el último valor sin nube.")
        if sel.startswith("🗺️"):
            fecha = "ULT:30"
        elif sel.startswith("🧩"):
            fecha = None
        else:
            fecha = sel.split("·")[0].strip()

        pan = False
        if vis == "color_real":
            pan = st.checkbox(
                "🔍 Nitidez 15 m (fusión con banda pancromática B8)",
                value=True, key="ls_pan",
                help="Fusión HSV con la pancromática del producto TOA: "
                     "duplica el detalle espacial del color real (30 m → 15 m)",
            )

        with st.spinner("Generando visualización..."):
            if pan and fecha != "ULT:30":
                res = _tiles_pan(fecha, f0, f1, nubes)
            else:
                res = _tiles("ls", vis, fecha, f0, f1, nubes)
        _pintar(res)

        with st.expander("📅 Calendario de escenas del rango"):
            st.dataframe(pd.DataFrame(escenas).rename(
                columns={"fecha": "Fecha", "nubes": "Nubes (%)", "satelite": "Satélite"}),
                use_container_width=True, hide_index=True)

# --------------------------------------------------------------------------
# SENTINEL-1 (RADAR)
# --------------------------------------------------------------------------
if sensor == "Sentinel-1 (radar)":
    st.caption(
        "El radar SAR **penetra nubes** y opera día y noche: es la fuente más "
        "confiable en la zona andina durante temporada de lluvias. Cambios "
        "bruscos de retrodispersión entre fechas pueden indicar remoción de "
        "suelo/vegetación."
    )
    f0, f1 = _selector_fechas("s1", dias_atras=90)
    pol = st.selectbox("Polarización", ["VV", "VH"], key="s1_pol",
                       help="VV: sensible a rugosidad del terreno · VH: sensible a estructura de vegetación")

    with st.spinner("Consultando catálogo Sentinel-1..."):
        escenas = _cat_s1(f0, f1, pol)

    if not escenas:
        st.warning("Sin pasadas Sentinel-1 en el rango. Amplíe las fechas "
                   "(revisita ~12 días).")
    else:
        opciones = [
            "🗺️ Mosaico de 12 días · órbita descendente (cobertura completa)",
            "🗺️ Mosaico de 12 días · órbita ascendente",
            "🧩 Compuesto mediano del rango",
        ] + [
            f"{e['fecha']}  ·  órbita {e['orbita'].lower()}" for e in escenas
        ]
        sel = st.selectbox(
            f"Pasada ({len(escenas)} disponibles)", opciones, index=0,
            key="s1_sel",
            help="Una pasada individual cubre solo una franja del departamento. "
                 "El mosaico une las pasadas de los últimos 12 días de una misma "
                 "dirección de órbita para cubrir toda la zona.")
        if sel.startswith("🗺️"):
            fecha = "ULT:12:" + ("DESCENDING" if "descendente" in sel else "ASCENDING")
        elif sel.startswith("🧩"):
            fecha = None
        else:
            fecha = sel.split("·")[0].strip()

        with st.spinner("Generando radar..."):
            res = _tiles("s1", pol, fecha, f0, f1)
        _pintar(res)

        with st.expander("📅 Calendario de pasadas del rango"):
            st.dataframe(pd.DataFrame(escenas).rename(
                columns={"fecha": "Fecha", "orbita": "Órbita"}),
                use_container_width=True, hide_index=True)

# --------------------------------------------------------------------------
# GOES-ESTE (geoestacionario · casi tiempo real)
# --------------------------------------------------------------------------
if sensor == "GOES-Este (cada 10 min)":
    st.caption(
        "El geoestacionario **GOES-Este (75°O)** es el único que observa a "
        "Colombia de forma continua: una imagen full-disk cada 10 minutos, "
        "con ~15-30 min de latencia en GEE. Ideal para vigilar la convección "
        "que dispara los aguaceros sobre la región. Resolución ~1-2 km: "
        "vista regional, no municipal."
    )
    producto = st.selectbox(
        "Producto",
        ["geocolor", "visible", "ir"],
        format_func=lambda k: {
            "geocolor": "GeoColor aproximado (diurno)",
            "visible": "Visible C02 (diurno)",
            "ir": "Infrarrojo C13 · nubes (día y noche)",
        }[k],
        index=2,
        help="De noche solo el infrarrojo C13 muestra información",
    )
    try:
        with st.spinner("Consultando última imagen GOES..."):
            res = _goes_fresco(producto)
        m = mapa_base(zoom=8, basemap="Esri.WorldImagery")
        m.add_tile_layer(res["tiles_url"],
                         name=f"{res['satelite']} · {res['etiqueta']}",
                         attribution="NOAA / Google Earth Engine",
                         opacity=0.85)
        agregar_contorno(m)
        ajustar_al_municipio(m, margen=1.2)  # vista regional (~250 km)
        m.to_streamlit(height=560)
        c1, c2 = st.columns(2)
        c1.metric("Satélite", res["satelite"])
        c2.metric("Hora de la imagen", res["etiqueta"])
        st.caption(f"**{res['nombre']}** — {res['descripcion']} "
                   "La imagen se refresca automáticamente cada ~5 minutos "
                   "(caché) al recargar la página.")
    except Exception as exc:
        st.warning(f"GOES no disponible en este momento: {exc}")

# --------------------------------------------------------------------------
# MODIS / VIIRS DIARIO (NASA GIBS · sin GEE)
# --------------------------------------------------------------------------
if sensor == "MODIS/VIIRS diario (NASA GIBS)":
    st.caption(
        "Reflectancia corregida en **color real** de NASA Worldview (GIBS): "
        "una imagen por día y satélite, disponible ~3-5 horas después del "
        "paso (media mañana y primera tarde). Resolución 250-375 m: vista "
        "subregional. Útil para ver la nubosidad y el estado del territorio "
        "de HOY sin esperar a Sentinel/Landsat."
    )
    c1, c2 = st.columns(2)
    with c1:
        capa = st.selectbox(
            "Satélite / capa",
            list(gibs.CAPAS_GIBS.keys()),
            format_func=lambda k: gibs.CAPAS_GIBS[k]["nombre"],
        )
    with c2:
        fecha_gibs = st.date_input(
            "Fecha", dt.date.today(),
            max_value=dt.date.today(),
            min_value=dt.date.today() - dt.timedelta(days=365),
        )
    info = gibs.CAPAS_GIBS[capa]
    m = mapa_base(zoom=10, basemap="Esri.WorldImagery")
    folium.TileLayer(
        tiles=gibs.url_tiles(capa, fecha_gibs),
        attr="NASA EOSDIS GIBS / Worldview",
        name=f"{info['nombre']} · {fecha_gibs}",
        overlay=True,
        control=True,
        max_native_zoom=9,   # GIBS sirve hasta z9; de ahí en adelante se amplía
        max_zoom=14,
    ).add_to(m)
    agregar_contorno(m)
    ajustar_al_municipio(m, margen=0.008)  # zoom a la unidad elegida
    m.to_streamlit(height=560)
    st.caption(
        f"**{info['nombre']}** · resolución {info['res']} · paso "
        f"{info['paso']}. Si la imagen de hoy aparece vacía o parcial, el "
        "satélite aún no ha pasado o GIBS no la ha publicado: seleccione el "
        "día anterior. Franjas negras = zonas sin cobertura del paso diario."
    )

pie_institucional()
