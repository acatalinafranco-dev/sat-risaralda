"""Ficha municipal de seguimiento (PDF de una página, tamaño carta)."""
from __future__ import annotations

import datetime as dt
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas

from . import riesgo
from .ui import AZUL_CARDER, CONTACTO, DEPENDENCIA, ENTIDAD, VERDE_CARDER, _logo_fondo_blanco

AZUL = colors.HexColor(AZUL_CARDER)
VERDE = colors.HexColor(VERDE_CARDER)
GRIS = colors.HexColor("#555555")
GRIS_CLARO = colors.HexColor("#e6eaed")

RECOMENDACION = {
    "Alto": ("Se sugiere priorizar el seguimiento diario de la lluvia, verificar "
             "en campo las laderas con eventos previos y coordinar con el "
             "Consejo Municipal de Gestión del Riesgo (CMGRD)."),
    "Moderado": ("Se sugiere mantener el seguimiento de la lluvia varias veces "
                 "por semana y revisar los puntos con eventos registrados."),
    "Bajo": ("Se sugiere continuar el seguimiento rutinario. Un nivel bajo no "
             "descarta la ocurrencia de eventos locales."),
    "Sin dato": "No fue posible calcular el nivel de atención con los datos disponibles.",
}


def _num(v, fmt="{:.0f}", vacio="s/d") -> str:
    return vacio if v is None or v != v else fmt.format(v)


def _parrafo(c, texto, x, y, ancho, fuente="Helvetica", tam=9.5, interlin=12.5,
             color=colors.black) -> float:
    c.setFont(fuente, tam)
    c.setFillColor(color)
    for linea in simpleSplit(texto, fuente, tam, ancho):
        c.drawString(x, y, linea)
        y -= interlin
    return y


def generar_ficha(fila: dict, nivel: str, amenaza: dict, eventos_tipo: dict,
                  n_inventario: int) -> bytes:
    """`fila`: codigo, nombre, area_km2, lluvia_7d, lluvia_30d, normal_30d,
    pct_normal_30d, perdida_ha, perdida_pct (de tabla_comparativa).
    `amenaza`: baja, media, alta, muy_alta, alta_muy_alta (% del área)."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    ancho, alto = letter
    mx = 48
    util = ancho - 2 * mx
    y = alto - 40

    # Encabezado ---------------------------------------------------------
    logo = _logo_fondo_blanco()
    if logo:
        try:
            c.drawImage(ImageReader(io.BytesIO(logo)), mx, y - 34, height=36,
                        width=36, preserveAspectRatio=True, mask="auto")
        except Exception:  # noqa: BLE001
            pass
    c.setFillColor(VERDE)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(mx + 46, y - 8, DEPENDENCIA)
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 9)
    c.drawString(mx + 46, y - 21, ENTIDAD)
    c.setFont("Helvetica", 8.5)
    c.drawRightString(ancho - mx, y - 8,
                      f"Fecha de corte: {dt.date.today().strftime('%d/%m/%Y')}")
    y -= 44
    c.setFillColor(AZUL)
    c.rect(mx, y, util / 3, 3, fill=1, stroke=0)
    c.setFillColor(VERDE)
    c.rect(mx + util / 3, y, util / 3, 3, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#FFCC00"))
    c.rect(mx + 2 * util / 3, y, util / 3, 3, fill=1, stroke=0)
    y -= 26

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(mx, y, f"Ficha de seguimiento · {fila['nombre']}")
    y -= 15
    c.setFont("Helvetica", 9.5)
    c.setFillColor(GRIS)
    c.drawString(mx, y, f"Movimientos en masa · Risaralda · Código DANE {fila['codigo']} · "
                        f"Área {_num(fila.get('area_km2'), '{:,.0f}')} km²")
    y -= 24

    # Nivel de atención ----------------------------------------------------
    col = colors.HexColor(riesgo.COLOR_NIVEL.get(nivel, "#b0b7bd"))
    c.setFillColor(col)
    c.roundRect(mx, y - 40, util, 44, 6, fill=1, stroke=0)
    c.setFillColor(colors.white if nivel != "Moderado" else colors.black)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(mx + 14, y - 14, f"Nivel de atención: {nivel.upper()}")
    c.setFont("Helvetica", 8.5)
    c.drawString(mx + 14, y - 30, "Provisional · combina lluvia de 30 días frente a su "
                                  "normal y amenaza por movimientos en masa (SGC)")
    y -= 62

    # Indicadores ------------------------------------------------------------
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(mx, y, "Indicadores")
    y -= 6
    filas = [
        ("Lluvia acumulada, últimos 7 días (IMERG)", f"{_num(fila.get('lluvia_7d'))} mm"),
        ("Lluvia acumulada, últimos 30 días (IMERG)", f"{_num(fila.get('lluvia_30d'))} mm"),
        ("Normal de 30 días (CHIRPS, 20 años)", f"{_num(fila.get('normal_30d'))} mm"),
        ("Lluvia de 30 días respecto a la normal", f"{_num(fila.get('pct_normal_30d'))} %"),
        ("Área en amenaza alta y muy alta (SGC, 2015)", f"{_num(amenaza.get('alta_muy_alta'))} %"),
        ("Eventos registrados en el SIMMA (inventario + catálogo)",
         f"{sum(eventos_tipo.values())}  ({n_inventario} de inventario en campo)"),
        ("Pérdida severa de vegetación (Sentinel-2, últimos 60 días)",
         f"{_num(fila.get('perdida_ha'), '{:,.0f}')} ha"),
    ]
    for i, (k, v) in enumerate(filas):
        y -= 17
        if i % 2 == 0:
            c.setFillColor(GRIS_CLARO)
            c.rect(mx, y - 4, util, 17, fill=1, stroke=0)
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 9.5)
        c.drawString(mx + 6, y, k)
        c.setFont("Helvetica-Bold", 9.5)
        c.drawRightString(ancho - mx - 6, y, v)
    y -= 28

    # Amenaza (barra apilada) ---------------------------------------------------
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(mx, y, "Amenaza por movimientos en masa (% del área municipal)")
    y -= 22
    x = mx
    for clave, nombre, colh in [("baja", "Baja", "#38a800"), ("media", "Media", "#ffd000"),
                                ("alta", "Alta", "#ff8c00"), ("muy_alta", "Muy alta", "#d62728")]:
        w = util * (amenaza.get(clave) or 0) / 100
        c.setFillColor(colors.HexColor(colh))
        c.rect(x, y, w, 16, fill=1, stroke=0)
        if w > 34:
            c.setFillColor(colors.black if clave in ("media", "baja") else colors.white)
            c.setFont("Helvetica-Bold", 8)
            c.drawCentredString(x + w / 2, y + 5, f"{amenaza.get(clave):.0f} %")
        x += w
    y -= 12
    c.setFont("Helvetica", 8)
    c.setFillColor(GRIS)
    c.drawString(mx, y, "Baja · Media · Alta · Muy alta (de izquierda a derecha). "
                        "Escala regional 1:100.000.")
    y -= 26

    # Eventos por tipo ------------------------------------------------------------
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(mx, y, "Eventos registrados por tipo (SIMMA)")
    y -= 6
    if eventos_tipo:
        for tipo, n in sorted(eventos_tipo.items(), key=lambda t: -t[1]):
            y -= 14
            c.setFillColor(colors.HexColor(riesgo.COLOR_TIPO.get(tipo, "#555555")))
            c.circle(mx + 8, y + 3, 3.2, fill=1, stroke=0)
            c.setFillColor(colors.black)
            c.setFont("Helvetica", 9.5)
            c.drawString(mx + 18, y, tipo)
            c.drawRightString(mx + 190, y, str(n))
    else:
        y -= 14
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 9.5)
        c.drawString(mx + 6, y, "El SIMMA no registra eventos en este municipio.")
    y -= 22

    # Lectura ----------------------------------------------------------------------
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(mx, y, "Lectura")
    y -= 14
    pa = riesgo._puntos_amenaza(amenaza.get("alta_muy_alta"))
    pl = riesgo._puntos_lluvia(fila.get("pct_normal_30d"))
    texto = (f"La lluvia de los últimos 30 días equivale a "
             f"{_num(fila.get('pct_normal_30d'))} % de la normal (puntaje "
             f"{'s/d' if pl is None else pl} de 3) y el "
             f"{_num(amenaza.get('alta_muy_alta'))} % del área municipal se encuentra en "
             f"amenaza alta o muy alta (puntaje {'s/d' if pa is None else pa} de 3). "
             + RECOMENDACION[nivel])
    y = _parrafo(c, texto, mx, y, util)

    # Pie ----------------------------------------------------------------------------
    c.setStrokeColor(GRIS_CLARO)
    c.line(mx, 92, ancho - mx, 92)
    pie = ("Herramienta de apoyo al conocimiento del riesgo. No sustituye las alertas "
           "oficiales del IDEAM ni las decisiones de los consejos de gestión del riesgo. "
           "El nivel de atención es provisional y sus umbrales están pendientes de "
           "validación. Fuentes: NASA GPM IMERG, UCSB CHIRPS, Copernicus Sentinel-2, "
           "Servicio Geológico Colombiano (amenaza 2015 y SIMMA), DANE (DIVIPOLA). "
           f"Calculado con Google Earth Engine. Contacto: {CONTACTO}")
    _parrafo(c, pie, mx, 80, util, tam=7.5, interlin=9.5, color=GRIS)
    c.showPage()
    c.save()
    return buf.getvalue()
