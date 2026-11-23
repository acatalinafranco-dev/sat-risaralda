"""Reporte semanal de movimientos en masa por municipio (PDF, tamaño carta).

Página 1: mensaje de la semana, indicadores, mapa de propensión del terreno con
los sitios conocidos que muestran cambio satelital esta semana (máximo 20) y su
lista. Página 2: lluvia, evidencia satelital, acciones sugeridas, sustento
técnico y fundamento normativo. Página 3: sectores de 300 m para seguimiento.

El documento es informativo: no constituye una alerta. Las alertas
hidrometeorológicas las emite el IDEAM y las decisiones corresponden a los
consejos de gestión del riesgo (Ley 1523 de 2012).
"""
from __future__ import annotations

import datetime as dt
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import letter  # noqa: E402
from reportlab.lib.utils import ImageReader, simpleSplit  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from . import susceptibilidad as sus  # noqa: E402
from .ui import (AZUL_CARDER, CITA, CONTACTO, DEPENDENCIA, ENTIDAD,  # noqa: E402
                 VERDE_CARDER, _logo_fondo_blanco)

AZUL = colors.HexColor(AZUL_CARDER)
VERDE = colors.HexColor(VERDE_CARDER)
GRIS = colors.HexColor("#555555")
GRIS_CLARO = colors.HexColor("#eef1f3")
ANCHO, ALTO = letter
MX = 36
UTIL = ANCHO - 2 * MX
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8})


def _c(v):
    return f"{v:.2f}".replace(".", ",")


def _n(v, fmt="{:.0f}", vacio="s/d"):
    return vacio if v is None or v != v else fmt.format(v)


def _parrafo(c, texto, x, y, ancho, fuente="Helvetica", tam=8.5, interlin=11,
             color=colors.black):
    c.setFont(fuente, tam)
    c.setFillColor(color)
    for linea in simpleSplit(texto, fuente, tam, ancho):
        c.drawString(x, y, linea)
        y -= interlin
    return y


def _titulo_seccion(c, texto, x, y):
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(x, y, texto)
    c.setFillColor(VERDE)
    c.rect(x, y - 4, 28, 1.6, fill=1, stroke=0)
    return y - 15


def _encabezado(c, municipio: str, pagina: int):
    y = ALTO - 30
    logo = _logo_fondo_blanco()
    if logo:
        try:
            c.drawImage(ImageReader(io.BytesIO(logo)), MX, y - 36, height=42,
                        width=22, preserveAspectRatio=True, mask="auto")
        except Exception:  # noqa: BLE001
            pass
    c.setFillColor(VERDE)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(MX + 30, y - 9, DEPENDENCIA)
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 8)
    c.drawString(MX + 30, y - 20, ENTIDAD)
    c.drawRightString(ANCHO - MX, y - 9,
                      f"Fecha de corte: {dt.date.today().strftime('%d/%m/%Y')}")
    c.drawRightString(ANCHO - MX, y - 20, f"{municipio} · página {pagina}")
    y -= 40
    for i, col in enumerate([AZUL, VERDE, colors.HexColor("#FFCC00")]):
        c.setFillColor(col)
        c.rect(MX + i * UTIL / 3, y, UTIL / 3, 2.5, fill=1, stroke=0)
    return y - 8


def _pie(c):
    c.setStrokeColor(colors.HexColor("#d5dadf"))
    c.line(MX, 52, ANCHO - MX, 52)
    txt = ("REPORTE INFORMATIVO. No constituye una alerta: las alertas "
           "hidrometeorológicas las emite el IDEAM, y las decisiones corresponden a "
           "los consejos de gestión del riesgo (Ley 1523 de 2012). Los resultados "
           "del modelo son de escala regional y no reemplazan los estudios básicos "
           f"ni detallados del POT. Contacto: {CONTACTO}")
    _parrafo(c, txt, MX, 42, UTIL, tam=6.8, interlin=8.2, color=GRIS)


def _png(fig, dpi=200) -> ImageReader:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    buf.seek(0)
    return ImageReader(buf)


def _anillos(geom: dict):
    polis = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for p in polis:
        yield np.array(p[0])


# --------------------------------------------------------------------------
# Figuras
# --------------------------------------------------------------------------
def _panel(ax, caja, geom_mun, otros, pts, etiquetas, lw_mun=1.3, escala=True):
    o, e, s, n = caja
    sub, ext = sus.recorte([[s, o], [n, e]])
    kx = np.cos(np.radians((s + n) / 2))
    cmap = ListedColormap(["#ffffff00"] + [sus.COLOR_CLASE[k] for k in sus.CLASES])
    ax.imshow(np.ma.masked_equal(sub, 0), extent=ext, cmap=cmap, vmin=0, vmax=5,
              interpolation="nearest", alpha=0.85, aspect=1 / kx)
    for g in otros:
        for a in _anillos(g):
            ax.plot(a[:, 0], a[:, 1], color="#8a8a8a", lw=0.5)
    for a in _anillos(geom_mun):
        ax.plot(a[:, 0], a[:, 1], color="#111111", lw=lw_mun)
    if len(pts):
        orden = {nv: k for k, nv in enumerate(sus.NIVELES[::-1])}
        p = pts.assign(_o=pts["nivel"].map(orden)).sort_values("_o")
        for nivel in sus.NIVELES[::-1]:
            q = p[p["nivel"] == nivel]
            ax.scatter(q["lon"], q["lat"], s=16 if nivel != sus.NIVELES[0] else 26,
                       c=sus.COLOR_NIVEL[nivel], edgecolors="white", linewidths=0.6,
                       zorder=3, label=nivel)
        for k, r in etiquetas.iterrows():
            ax.annotate(str(k + 1), (r["lon"], r["lat"]), xytext=(3, 3),
                        textcoords="offset points", fontsize=6.3, weight="bold",
                        color="#111", zorder=4,
                        bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.8))
    ax.set_xlim(o, e)
    ax.set_ylim(s, n)
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_color("#999")
    if escala:
        ancho_km = (e - o) * 111 * kx
        km = 1 if ancho_km < 8 else 2 if ancho_km < 16 else 5 if ancho_km < 40 else 10
        lx, ly = o + (e - o) * 0.05, s + (n - s) * 0.04
        ax.plot([lx, lx + km / (111 * kx)], [ly, ly], color="black", lw=2.2)
        ax.text(lx + km / (111 * kx) / 2, ly + (n - s) * 0.015, f"{km} km",
                ha="center", fontsize=6.5)
    return kx


def figura_mapa(geom_mun: dict, otros: list[dict], pts: pd.DataFrame,
                n_etiquetas: int = 14) -> tuple[ImageReader, float]:
    xs = np.concatenate([a[:, 0] for a in _anillos(geom_mun)])
    ys = np.concatenate([a[:, 1] for a in _anillos(geom_mun)])
    pad = 0.02
    o, e, s, n = xs.min() - pad, xs.max() + pad, ys.min() - pad, ys.max() + pad
    kx = np.cos(np.radians((s + n) / 2))
    asp = (n - s) / ((e - o) * kx)
    top = pts.head(n_etiquetas)
    # Recuadro de detalle cuando los sitios priorizados se concentran
    detalle = None
    if len(top) >= 6:
        lo0, lo1 = top["lon"].quantile([0.1, 0.9])
        la0, la1 = top["lat"].quantile([0.1, 0.9])
        frac = ((lo1 - lo0) * (la1 - la0)) / ((e - o) * (n - s))
        if frac < 0.04:
            cx, cy = (lo0 + lo1) / 2, (la0 + la1) / 2
            r = max(lo1 - lo0, (la1 - la0) / kx, 0.02) * 0.75
            detalle = (cx - r, cx + r, cy - r * kx * 1.0, cy + r * kx * 1.0)
    if detalle:
        dentro = top[(top["lon"].between(detalle[0], detalle[1])) &
                     (top["lat"].between(detalle[2], detalle[3]))]
        fuera = top.drop(dentro.index)
        fig, (ax, ax2) = plt.subplots(1, 2, figsize=(7.4, 3.9),
                                      gridspec_kw={"width_ratios": [1.45, 1]})
        _panel(ax, (o, e, s, n), geom_mun, otros, pts, fuera)
        ax.add_patch(plt.Rectangle((detalle[0], detalle[2]), detalle[1] - detalle[0],
                                   detalle[3] - detalle[2], fill=False, ec="#004B87",
                                   lw=1.4, zorder=5))
        _panel(ax2, detalle, geom_mun, otros, pts, dentro, lw_mun=1.6)
        ax2.set_title("Detalle de la zona con más sitios", fontsize=7)
        for sp in ax2.spines.values():
            sp.set_color("#004B87")
            sp.set_linewidth(1.4)
    else:
        fig, ax = plt.subplots(figsize=(5.6, 5.6 * min(1.2, max(0.45, asp))))
        _panel(ax, (o, e, s, n), geom_mun, otros, pts, top)
    ax.annotate("N", xy=(e - (e - o) * 0.05, n - (n - s) * 0.04),
                xytext=(e - (e - o) * 0.05, n - (n - s) * 0.12),
                arrowprops=dict(arrowstyle="-|>", color="black", lw=1),
                ha="center", fontsize=8, weight="bold")
    h1 = [plt.Rectangle((0, 0), 1, 1, color=sus.COLOR_CLASE[k]) for k in sus.CLASES]
    l1 = fig.legend(h1, sus.CLASES, title="Propensión del terreno", loc="upper left",
                    bbox_to_anchor=(1.0, 0.98), fontsize=6.5, title_fontsize=7,
                    frameon=False, alignment="left")
    if len(pts):
        hs, ls = ax.get_legend_handles_labels()
        fig.legend(hs[::-1], ls[::-1], title="Sitios con cambio esta semana",
                   loc="upper left", bbox_to_anchor=(1.0, 0.55), fontsize=6.5,
                   title_fontsize=7, frameon=False, alignment="left")
    fig.add_artist(l1)
    fig.tight_layout()
    return _png(fig), asp


def figura_lluvia(serie: list[dict], ref30: float | None,
                  umbral30: float | None = None) -> ImageReader:
    df = pd.DataFrame(serie)
    fig, ax = plt.subplots(figsize=(3.9, 1.9))
    if len(df):
        df["fecha"] = pd.to_datetime(df["fecha"])
        acum30 = df.set_index("fecha")["mm"].rolling("30D").sum()
        corte = df["fecha"].max() - pd.Timedelta(days=59)
        df = df[df["fecha"] >= corte]
        acum30 = acum30[acum30.index >= corte]
        ax.bar(df["fecha"], df["mm"], color="#2b8cbe", width=0.9)
        ax2 = ax.twinx()
        ax2.plot(acum30.index, acum30.values, color="#08306b", lw=1.4,
                 label="Acumulado 30 días")
        if ref30:
            ax2.axhline(ref30, color="#e6550d", lw=1.1, ls="--",
                        label="Referencia 30 días (CHIRPS, 20 años)")
        if umbral30:
            ax2.axhline(umbral30, color="#c0392b", lw=1.1, ls=":",
                        label=f"Umbral preliminar 30 días ({umbral30:.0f} mm)")
        ax2.set_ylabel("Acumulado 30 d (mm)", fontsize=6.5)
        ax2.tick_params(labelsize=6)
        ax2.legend(fontsize=5.8, loc="upper left", frameon=False)
        ax2.set_ylim(0, max(acum30.max(), ref30 or 0, umbral30 or 0) * 1.3 + 1)
    ax.set_ylabel("mm/día", fontsize=6.5)
    ax.tick_params(labelsize=6)
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%d/%m"))
    ax.set_title("Lluvia diaria media en el municipio (IMERG), últimos 60 días",
                 fontsize=7, loc="left")
    for sp in ("top",):
        ax.spines[sp].set_visible(False)
    return _png(fig)


def figura_visitas(por_anio: dict) -> ImageReader:
    fig, ax = plt.subplots(figsize=(2.9, 1.9))
    if por_anio:
        a = sorted((int(k), v) for k, v in por_anio.items())
        ax.bar([str(k) for k, _ in a], [v for _, v in a], color="#008A4B")
        for k, v in a:
            ax.text(str(k), v, str(v), ha="center", va="bottom", fontsize=5.8)
    ax.set_title("Visitas por movimientos en masa por año", fontsize=7, loc="left")
    ax.tick_params(labelsize=5.8)
    ax.tick_params(axis="x", rotation=60)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    return _png(fig)


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------
def _kpi(c, x, y, w, h, valor, etiqueta, color=AZUL):
    c.setFillColor(GRIS_CLARO)
    c.roundRect(x, y, w, h, 4, fill=1, stroke=0)
    c.setFillColor(color)
    c.rect(x, y, 3, h, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(x + 10, y + h - 20, valor)
    _parrafo(c, etiqueta, x + 10, y + h - 32, w - 16, tam=7, interlin=8.3, color=GRIS)


def _tabla(c, x, y, cols, filas, anchos, tam=7, alto_f=12.5, cabecera=True):
    if cabecera:
        c.setFillColor(AZUL)
        c.rect(x, y - 3, sum(anchos), alto_f, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", tam)
        xx = x + 3
        for col, w in zip(cols, anchos):
            c.drawString(xx, y + 1, col)
            xx += w
        y -= alto_f
    for i, f in enumerate(filas):
        if i % 2 == 0:
            c.setFillColor(GRIS_CLARO)
            c.rect(x, y - 3, sum(anchos), alto_f, fill=1, stroke=0)
        xx = x + 3
        for j, (v, w) in enumerate(zip(f, anchos)):
            txt = str(v)
            if isinstance(v, tuple):  # (texto, color)
                txt, colh = v
                c.setFillColor(colors.HexColor(colh))
                c.circle(xx + 3, y + 2.3, 2.6, fill=1, stroke=0)
                xx2 = xx + 8
            else:
                xx2 = xx
            c.setFillColor(colors.black)
            c.setFont("Helvetica", tam)
            while c.stringWidth(txt, "Helvetica", tam) > w - 6 - (xx2 - xx) and len(txt) > 3:
                txt = txt[:-2]
                txt = txt.rstrip() + "…" if not txt.endswith("…") else txt
            c.drawString(xx2, y + 1, txt)
            xx += w
        y -= alto_f
    return y


def _supera_umbral(m, lluvia) -> list[str]:
    u = m.get("umbral_lluvia") or {}
    if not lluvia or not u:
        return []
    sup = []
    if (lluvia.get("acum7") or 0) >= u["acum7_mm"]:
        sup.append(f"7 días ({lluvia['acum7']:.0f} mm frente a {u['acum7_mm']} mm)")
    # El umbral de 30 días se calibró con CHIRPS y no es comparable con IMERG;
    # para la semana se usa solo el de 7 días (igual que en la página de inicio).
    return sup


def _texto_umbral(m, lluvia) -> str:
    u = m.get("umbral_lluvia") or {}
    if not u:
        return ""
    sup = _supera_umbral(m, lluvia)
    t = (f"Umbral preliminar de lluvia, calibrado con eventos registrados en el departamento: "
         f"{u['acum7_mm']} mm en 7 días. ")
    t += ("Hoy se supera en " + " y ".join(sup) + ". ") if sup else "Hoy no se supera. "
    return t + u["desempeno"]


def _mensaje(nombre, res, sitios, lluvia, sectores=None) -> str:
    """Mensaje de la semana: lluvia, sectores y sitios conocidos con cambio."""
    t = ""
    a7 = lluvia.get("acum7") if lluvia else None
    p = lluvia.get("pct_ref") if lluvia else None
    if a7 is not None and a7 == a7:
        t += f"En los últimos 7 días llovieron {a7:.0f} mm en {nombre}"
        if p is not None and p == p:
            estado = ("por encima de" if p >= 115 else "por debajo de" if p <= 85 else "cerca de")
            t += f"; la lluvia de 30 días está {estado} lo habitual ({p:.0f} %)"
        t += ". "
    sup = _supera_umbral(sus.meta(), lluvia)
    if sup:
        t += ("La lluvia acumulada supera el umbral preliminar de " + " y ".join(sup)
              + ": se sugiere hacer seguimiento a los sectores y sitios señalados. ")
    if sectores and sectores.get("resumen"):
        r = sectores["resumen"]
        if r["n_sectores"]:
            t += (f"Esta semana, {r['n_sectores']} de los {r.get('n_total', 0)} sectores de "
                  f"300 m del municipio ({_c(r['pct_area'])} %) reúnen condiciones de terreno "
                  "y lluvia que sugieren hacer seguimiento"
                  + (f"; {r['n_prioritarios']} en seguimiento prioritario" if r["n_prioritarios"] else "")
                  + ". ")
        else:
            t += "Esta semana ningún sector supera el umbral de seguimiento por terreno y lluvia. "
    n = 0 if sitios is None else len(sitios)
    if n:
        t += (f"{n} sitio{'s' if n > 1 else ''} donde ya se había registrado un movimiento en "
              f"masa muestra{'n' if n > 1 else ''} cambios en el terreno detectados por satélite "
              "esta semana. ")
    else:
        t += ("Ningún sitio con movimiento en masa registrado muestra cambios en el terreno "
              "detectados por satélite esta semana. ")
    return t + "Reporte informativo: la verificación y las acciones corresponden a la administración municipal."


def figura_sectores(geom_mun: dict, df: pd.DataFrame) -> ImageReader:
    from src import sectores as sec

    fig, ax = plt.subplots(figsize=(4.2, 3.6))
    xs, ys = [], []
    for a in _anillos(geom_mun):
        ax.fill(a[:, 0], a[:, 1], color="#f2f2f2", zorder=1)
        ax.plot(a[:, 0], a[:, 1], color="#555555", lw=1.0, zorder=3)
        xs += list(a[:, 0]); ys += list(a[:, 1])
    d = 0.00135
    if df is not None and len(df):
        for _, r in df.iloc[::-1].iterrows():
            ax.add_patch(plt.Rectangle((r["lon"] - d, r["lat"] - d), 2 * d, 2 * d,
                                       color=sec.COLOR_NIVEL[r["nivel"]], lw=0,
                                       alpha=0.9, zorder=2))
            if r["evidencia_cambio"]:
                ax.add_patch(plt.Rectangle((r["lon"] - d, r["lat"] - d), 2 * d, 2 * d,
                                           fill=False, ec="black", lw=0.6, zorder=2.5))
    ax.set_xlim(min(xs) - 0.01, max(xs) + 0.01)
    ax.set_ylim(min(ys) - 0.01, max(ys) + 0.01)
    ax.set_aspect(1 / np.cos(np.radians(np.mean(ys))))
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    h = [plt.Rectangle((0, 0), 1, 1, color=sec.COLOR_NIVEL[n]) for n in sec.NIVELES]
    h.append(plt.Rectangle((0, 0), 1, 1, fill=False, ec="black", lw=0.8))
    ax.legend(h, sec.NIVELES + ["Con cambio de cobertura o radar"], loc="upper center",
              bbox_to_anchor=(0.5, -0.01), ncol=2, fontsize=6.5, frameon=False)
    return _png(fig)


def _crit(t) -> str:
    if not t:
        return "Centro"
    t = str(t)
    return ("Vegetación" if "Sentinel-2" in t else "Radar" if "Sentinel-1" in t
            else "Pendiente" if "pendiente" in t else "Centro")


def _pagina_sectores(c, nombre: str, sectores: dict, pag: int, geom_mun=None) -> int:
    from src import sectores as sec

    df = sectores.get("tabla")
    r = sectores.get("resumen") or {}
    ms = sec.meta()
    y = _encabezado(c, nombre, pag)
    y -= 14
    y = _titulo_seccion(c, f"Sectores para seguimiento · semana que termina el "
                           f"{sectores.get('fecha', '')}", MX, y)
    y = _parrafo(c, sec.TEXTO, MX, y, UTIL, fuente="Helvetica-Bold", tam=8, interlin=10) - 2
    vv = ms["validacion"]
    intro = (f"Sectores de 300 m calificados con el terreno (propensión, pendiente, "
             "relieve, geología y fallas del SGC) y la lluvia satelital de los 30 días previos "
             "(acumulado, máximos de 1 y 7 días y anomalía). Se marca «seguimiento» cuando la "
             "calificación supera el umbral validado y «seguimiento prioritario» en el umbral "
             f"superior. En la validación 2024-2026, el umbral de seguimiento marcó en promedio "
             f"el {vv['umbral_seguimiento']['area_media_pct']:.0f} % del departamento y señaló "
             f"el {vv['umbral_seguimiento']['captura_sin_sismo_pct']:.0f} % de los eventos "
             "registrados después (sin contar el sismo de agosto de 2026). El cambio de cobertura "
             "(Sentinel-2) y de radar (Sentinel-1) se indica como evidencia complementaria. "
             "Para cada sector se da un punto de verificación: el píxel de 10 m con cambio "
             "detectado o, si no lo hay, el de mayor pendiente dentro del sector.")
    if geom_mun is not None:
        c.drawImage(figura_sectores(geom_mun, df), MX, y - 205, width=250, height=205,
                    preserveAspectRatio=True, anchor="nw")
        xk = MX + 262
        wk = (UTIL - 262 - 8) / 2
        _kpi(c, xk, y - 46, wk, 44, str(r.get("n_sectores", 0)), "Sectores para seguimiento")
        _kpi(c, xk + wk + 8, y - 46, wk, 44, str(r.get("n_prioritarios", 0)),
             "Seguimiento prioritario", color=colors.HexColor(sec.COLOR_NIVEL[sec.NIVELES[0]]))
        _kpi(c, xk, y - 98, wk, 44, f"{r.get('pct_area', 0):.1f} %".replace(".", ","),
             "Del área municipal")
        _kpi(c, xk + wk + 8, y - 98, wk, 44, str(r.get("n_con_cambio", 0)),
             "Con cambio de cobertura o radar")
        _parrafo(c, intro, xk, y - 112, UTIL - 262, tam=6.6, interlin=8.0)
        y -= 228
    else:
        y = _parrafo(c, intro, MX, y, UTIL, tam=7, interlin=8.6) - 4
    if df is None or df.empty:
        y = _parrafo(c, "En esta semana ningún sector del municipio supera el umbral de "
                        "seguimiento.", MX, y, UTIL, tam=8)
    else:
        n_tot = len(df)
        df = df.head(28)
        filas = [[str(i + 1),
                  (s_["nivel"].replace("Seguimiento prioritario", "Prioritario"),
                   sec.COLOR_NIVEL[s_["nivel"]]),
                  f"{s_.get('pv_lat', s_['lat']):.5f}, {s_.get('pv_lon', s_['lon']):.5f}",
                  _crit(s_.get("pv_criterio")), s_["susceptibilidad"],
                  f"{s_['lluvia_30d_mm']:.0f} / {s_['lluvia_max7d_mm']:.0f}",
                  _c(s_["anomalia_lluvia"]),
                  ("Sí" if s_["evidencia_cambio"] else "No")
                  + ("" if s_["imagen_optica_valida_pct"] >= 50 else " (nubes)"),
                  s_["exposicion"] or "—"]
                 for i, s_ in df.iterrows()]
        cab = ["N°", "Nivel", "Punto de verificación", "Criterio", "Propens.",
               "Lluvia 30 d / 7 d", "Anom.", "Cambio", "Expuestos"]
        anchos = [18, 58, 92, 52, 44, 66, 32, 50, UTIL - 412]
        y = _tabla(c, MX, y, cab, filas, anchos, tam=6.4, alto_f=11.2)
        if n_tot > len(df):
            y = _parrafo(c, f"Se muestran los 28 sectores con mayor calificación de {n_tot}. "
                            "La lista completa se descarga en Excel desde la aplicación "
                            "(sección «Movimientos en masa», pestaña «Sectores de la semana»).",
                         MX, y - 4, UTIL, tam=6.8, color=GRIS)
    y = _parrafo(c, "Reporte informativo de apoyo al seguimiento. No constituye una alerta: "
                    "las alertas hidrometeorológicas las emite el IDEAM. Los sectores indican "
                    "dónde verificar, no el predio afectado. Criterio del punto: «Vegetación», "
                    "pérdida de vegetación y suelo expuesto (Sentinel-2); «Radar», cambio en "
                    "Sentinel-1; «Pendiente», sin cambio detectado, píxel de mayor pendiente.",
                 MX, y - 6, UTIL, tam=6.8,
                 color=GRIS)
    _pie(c)
    c.showPage()
    return pag + 1


def generar_reporte(codigo: str, nombre: str, geom_mun: dict, otros: list[dict],
                    lluvia: dict | None = None, sectores: dict | None = None,
                    sitios: pd.DataFrame | None = None, fecha: str | None = None) -> bytes:
    """Reporte semanal. «lluvia»: {serie, acum7, acum30, ref30, pct_ref}.
    «sectores»: {fecha, resumen, tabla}. «sitios»: sitios conocidos con cambio
    satelital esta semana (src.sectores.sitios_semana)."""
    m = sus.meta()
    res = sus.resumen_municipio(codigo)
    sitios = sitios if sitios is not None else sus.puntos(codigo).iloc[0:0]
    fecha_txt = dt.date.fromisoformat(fecha).strftime("%d/%m/%Y") if fecha else ""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setTitle(f"Reporte semanal de movimientos en masa - {nombre}")
    c.setAuthor(ENTIDAD)

    # ======================= PÁGINA 1 =======================================
    y = _encabezado(c, nombre, 1)
    y -= 16
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(MX, y, f"Reporte semanal de movimientos en masa · {nombre}")
    y -= 13
    c.setFont("Helvetica", 8.5)
    c.setFillColor(GRIS)
    c.drawString(MX, y, f"Semana que termina el {fecha_txt}. Reporte informativo de monitoreo "
                        "satelital; no constituye una alerta.")
    y -= 12
    msg = _mensaje(nombre, res, sitios, lluvia, sectores)
    lineas = simpleSplit(msg, "Helvetica", 8.6, UTIL - 20)
    h = 14 + 10.6 * len(lineas)
    c.setFillColor(colors.HexColor("#fff8e1"))
    c.roundRect(MX, y - h, UTIL, h, 4, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#f2b705"))
    c.rect(MX, y - h, 3, h, fill=1, stroke=0)
    _parrafo(c, msg, MX + 10, y - 12, UTIL - 20, tam=8.6, interlin=10.6)
    y -= h + 8
    # Indicadores de la semana
    w = (UTIL - 18) / 4
    hk = 46
    u7 = (m.get("umbral_lluvia") or {}).get("acum7_mm", 63)
    a7 = lluvia.get("acum7") if lluvia else None
    pct = lluvia.get("pct_ref") if lluvia else None
    rs = (sectores or {}).get("resumen") or {}
    _kpi(c, MX, y - hk, w, hk, f"{_n(a7)} mm",
         f"lluvia de los últimos 7 días (umbral de referencia {u7} mm)", colors.HexColor("#2b8cbe"))
    _kpi(c, MX + (w + 6), y - hk, w, hk, f"{_n(pct)} %",
         "lluvia de 30 días frente a lo habitual", colors.HexColor("#2b8cbe"))
    _kpi(c, MX + 2 * (w + 6), y - hk, w, hk, _n(rs.get("n_sectores")),
         f"sectores de 300 m para seguimiento ({_n(rs.get('n_prioritarios'))} prioritarios)",
         colors.HexColor(sus.COLOR_NIVEL[sus.NIVELES[0]]))
    _kpi(c, MX + 3 * (w + 6), y - hk, w, hk, str(len(sitios)),
         "sitios conocidos con cambio satelital esta semana", colors.HexColor("#8e44ad"))
    y -= hk + 10

    # Mapa con los sitios conocidos que cambiaron esta semana
    img, _ = figura_mapa(geom_mun, otros, sitios)
    iw, ih = img.getSize()
    h_max = 290
    w_map = UTIL
    h_map = w_map * ih / iw
    if h_map > h_max:
        h_map = h_max
        w_map = h_map * iw / ih
    c.drawImage(img, MX + (UTIL - w_map) / 2, y - h_map, width=w_map, height=h_map,
                mask="auto")
    y -= h_map + 8
    y = _parrafo(c, "Propensión del terreno: modelo propio (CARDER, 2026), 30 m presentada a "
                    "60 m. Sitios: lugares con movimiento en masa registrado donde esta semana "
                    "el satélite detectó pérdida de vegetación o cambio persistente en radar en "
                    "un radio de 100 m (máximo 20 por municipio). Los números corresponden a la "
                    "tabla.", MX, y, UTIL, tam=6.3, interlin=7.5, color=GRIS)
    y -= 6
    y = _titulo_seccion(c, "Sitios conocidos con cambio detectado esta semana", MX, y)
    if len(sitios):
        filas = []
        for i, r in sitios.reset_index(drop=True).iterrows():
            filas.append([str(i + 1), r["vereda"] or "s/d",
                          (r["nivel"].replace("Seguimiento prioritario", "Prioritario"),
                           sus.COLOR_NIVEL[r["nivel"]]),
                          r["cambio_detectado"], f"{100 * r['f_cambio']:.0f} %",
                          sus.texto_exposicion(r) or "—",
                          f"{r['lat']:.4f}, {r['lon']:.4f}"])
        y = _tabla(c, MX, y, ["N°", "Vereda / barrio", "Nivel", "Cambio detectado",
                              "Área con cambio", "Elementos expuestos", "Coordenadas"],
                   filas, [18, 120, 70, 96, 56, 112, UTIL - 472], tam=6.7, alto_f=11.5)
        _parrafo(c, "Área con cambio: porcentaje del círculo de 100 m alrededor del sitio con "
                    "cambio detectado. Se sugiere verificar en campo.", MX, y - 3, UTIL,
                 tam=6.6, color=GRIS)
    else:
        _parrafo(c, "Esta semana ningún sitio con movimiento en masa registrado muestra cambios "
                    "detectados por satélite. Los sectores para seguimiento se presentan en la "
                    "página 3.", MX, y, UTIL)
    _pie(c)
    c.showPage()

    # ======================= PÁGINA 2 =======================================
    y = _encabezado(c, nombre, 2)
    y -= 14
    y2 = _titulo_seccion(c, "Lluvia de los últimos 60 días", MX, y)
    if lluvia and lluvia.get("serie"):
        c.drawImage(figura_lluvia(lluvia.get("serie_completa") or lluvia["serie"],
                                  lluvia.get("ref30"), None),
                    MX, y2 - 150, width=UTIL, height=150, preserveAspectRatio=True, anchor="nw")
    y = y2 - 158
    if lluvia:
        y = _parrafo(c, f"Lluvia acumulada: {_n(lluvia.get('acum7'))} mm en 7 días y "
                        f"{_n(lluvia.get('acum30'))} mm en 30 días (NASA GPM IMERG). "
                        f"Referencia de 30 días: {_n(lluvia.get('ref30'))} mm (promedio "
                        "CHIRPS de 20 años de la misma ventana). " + _texto_umbral(m, lluvia),
                     MX, y, UTIL, tam=7.2, interlin=9)
    y -= 6
    y = _titulo_seccion(c, "Evidencia satelital de la semana", MX, y)
    txt = ("Se buscan cambios en el terreno con dos sensores: pérdida de vegetación con suelo "
           "expuesto en Sentinel-2 (últimos 12 días frente a los 30 anteriores y últimos 30 días "
           "frente a los 90 anteriores) y cambio persistente en el radar Sentinel-1 (misma órbita; "
           "últimos 12 días frente a los 30, 60 y 90 anteriores). ")
    if rs:
        txt += (f"Esta semana, {_n(rs.get('n_con_cambio'))} de los sectores para seguimiento "
                "presentan alguno de esos cambios. ")
    txt += ("Un cambio puede deberse a un movimiento en masa, pero también a cosechas, talas, "
            "quemas u obras: requiere verificación.")
    y = _parrafo(c, txt, MX, y, UTIL, tam=7.2, interlin=9) - 8

    # Acciones sugeridas
    y = _titulo_seccion(c, "Acciones sugeridas", MX, y)
    y = _parrafo(c, "Orientaciones de apoyo. La verificación en campo y las acciones que se "
                    "deriven de ella corresponden a la administración municipal, en el marco de "
                    "su autonomía.", MX, y, UTIL, tam=6.9, interlin=8.4) - 4
    wb = (UTIL - 12) / 3
    hb = 64
    for i, n in enumerate(sus.NIVELES):
        x = MX + i * (wb + 6)
        c.setFillColor(GRIS_CLARO)
        c.roundRect(x, y - hb, wb, hb, 3, fill=1, stroke=0)
        c.setFillColor(colors.HexColor(sus.COLOR_NIVEL[n]))
        c.rect(x, y - hb, 3, hb, fill=1, stroke=0)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 7.6)
        c.drawString(x + 8, y - 11, n)
        _parrafo(c, sus.ACCION_NIVEL[n], x + 8, y - 22, wb - 14, tam=6.7, interlin=8.1)
    y -= hb + 10

    # Sustento técnico
    y = _titulo_seccion(c, "Sustento técnico", MX, y)
    v = m["validacion"]
    vs = {}
    try:
        from src import sectores as sec
        vs = sec.meta()["validacion"]
    except Exception:  # noqa: BLE001
        pass
    metodo = (
        "Sectores de la semana: cada sector de 300 m se califica con un modelo estadístico "
        "(bosque aleatorio) que combina el terreno (propensión, pendiente en clases IGAC, "
        "relieve, geología y fallas del SGC) con la lluvia satelital de los últimos 30 días. "
        + (f"En la prueba con movimientos en masa de 2024 a 2026 (sin el mes del sismo), "
           f"marcando en promedio el {vs['umbral_seguimiento']['area_media_pct']:.0f} % del "
           f"departamento se habría señalado el {vs['umbral_seguimiento']['captura_sin_sismo_pct']:.0f} % "
           "de los eventos. " if vs else "")
        + "Propensión del terreno: modelo propio a 30 m que relaciona los movimientos en masa "
        "registrados con el terreno, el drenaje, los suelos, la cobertura, las vías y la lluvia "
        f"histórica; el {v['pct_eventos_alta']:.0f} % de los eventos cayó en las clases alta y muy "
        f"alta, que ocupan el {v['pct_area_alta']:.0f} % del departamento.")
    y = _parrafo(c, metodo, MX, y, UTIL, tam=6.9, interlin=8.4)
    limites = (
        "Límites: es un monitoreo de escala regional. A escala de predio no distingue sitios "
        "con y sin movimiento. Complementa, y no reemplaza, la zonificación del SGC "
        "(1:100.000) ni los estudios básicos y detallados del POT (Decreto 1077 de 2015). "
        "No constituye una alerta: las alertas hidrometeorológicas las emite el IDEAM.")
    y = _parrafo(c, limites, MX, y - 2, UTIL, tam=6.9, interlin=8.4)
    norma = (
        "Fundamento: Ley 1523 de 2012 (arts. 4, 12, 14 y 31): el conocimiento del riesgo "
        "incluye el monitoreo y la comunicación del riesgo; los alcaldes conducen la gestión "
        "del riesgo en su jurisdicción y las corporaciones autónomas regionales apoyan a las "
        "entidades territoriales en los estudios para el conocimiento del riesgo.")
    y = _parrafo(c, norma, MX, y - 2, UTIL, tam=6.9, interlin=8.4)
    fuentes = ("Fuentes: CARDER; NASA (GPM IMERG, NASADEM); UCSB CHG (CHIRPS); ESA Copernicus "
               "(Sentinel-1, Sentinel-2, WorldCover); USGS (Landsat 8); MERIT Hydro; GRIP4; "
               "OpenLandMap; SGC; IGAC (clases de pendiente). Procesado en Google Earth Engine. "
               "Cómo citar: " + CITA)
    _parrafo(c, fuentes, MX, y - 2, UTIL, tam=6.2, interlin=7.6, color=GRIS)
    _pie(c)
    c.showPage()

    # ======================= SECTORES DE LA SEMANA ==========================
    if sectores is not None:
        _pagina_sectores(c, nombre, sectores, 3, geom_mun)
    c.save()
    return buf.getvalue()
