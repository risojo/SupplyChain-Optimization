"""Estilos compartidos de la interfaz de Inventarios."""
from __future__ import annotations

import base64
import html
import os
import re
from dataclasses import dataclass, replace
from typing import Any, Literal

import pandas as pd
import streamlit as st

TABLA_FONT_SIZE_DEFAULT = 17
TABLA_FONT_SIZE_MIN = 12
TABLA_FONT_SIZE_MAX = 32


def font_campos_px() -> int:
    """Tamaño de letra global (slider en sidebar → ``inv_tabla_fontsize``)."""
    return int(st.session_state.get("inv_tabla_fontsize", TABLA_FONT_SIZE_DEFAULT))


_DIR_MODULO = os.path.dirname(os.path.abspath(__file__))
_RAIZ_PROYECTO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARCHIVO_LOGO_LRI = os.path.join(_RAIZ_PROYECTO, "assets", "LRI_logo.png")
ARCHIVO_LOGO_HEADER = os.path.join(_DIR_MODULO, "assets", "LRI_logo_header.png")
TITULO_MODULO = "Inventory Pro"
SIDEBAR_LOGO_HEIGHT_PX = 122


def _ruta_logo_lri() -> str | None:
    for ruta in (
        ARCHIVO_LOGO_HEADER,
        ARCHIVO_LOGO_LRI,
        os.path.join(_DIR_MODULO, "assets", "LRI_logo.png"),
    ):
        if os.path.isfile(ruta):
            return ruta
    return None


def _logo_sidebar_base64() -> str | None:
    ruta = _ruta_logo_lri()
    if not ruta:
        return None
    with open(ruta, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def render_branding_sidebar() -> None:
    """Logo LRI en sidebar con tamaño real (st.logo ignora CSS externo)."""
    h = SIDEBAR_LOGO_HEIGHT_PX
    w = max(1, int(h * 149 / 88))
    st.markdown(
        f"""
<style>
section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"]:has(.lri-inv-sidebar-logo),
section[data-testid="stSidebar"] div[data-testid="stElementContainer"]:has(.lri-inv-sidebar-logo) {{
    overflow: visible !important;
    max-height: none !important;
    height: auto !important;
}}
.lri-inv-sidebar-logo {{
    padding-top: 12px;
    padding-bottom: 0;
    margin: 0;
    line-height: 0;
    overflow: visible;
}}
.lri-inv-sidebar-logo img {{
    height: {h}px !important;
    width: auto !important;
    max-width: 100% !important;
    max-height: none !important;
    object-fit: contain !important;
    display: block !important;
}}
section[data-testid="stSidebar"] .lri-inv-sidebar-titulo {{
    margin: 0.2rem 0 0.75rem 0 !important;
    padding: 0 !important;
    font-size: 1.3rem !important;
    font-weight: 700 !important;
    color: #f8fafc !important;
    line-height: 1.15 !important;
    letter-spacing: 0.01em !important;
}}
</style>
""",
        unsafe_allow_html=True,
    )
    logo_b64 = _logo_sidebar_base64()
    if logo_b64:
        st.markdown(
            f'<div class="lri-inv-sidebar-logo">'
            f'<img src="data:image/png;base64,{logo_b64}" alt="LRI" '
            f'width="{w}" height="{h}" /></div>',
            unsafe_allow_html=True,
        )


def _css_titulo_main() -> str:
    return """
<style>
section[data-testid="stMain"] div[data-testid="stElementContainer"]:has(.lri-inv-titulo-main),
section[data-testid="stMain"] div[data-testid="stMarkdownContainer"]:has(.lri-inv-titulo-main),
section[data-testid="stMain"] div[data-testid="stVerticalBlock"]:has(.lri-inv-titulo-main) {
    overflow: visible !important;
    max-height: none !important;
    height: auto !important;
    min-height: 52px !important;
    padding-top: 0 !important;
}
.lri-inv-titulo-main {
    margin: 0.75rem 0 12px 0;
    padding: 10px 0 6px 0;
    overflow: visible;
    min-height: 36px;
    line-height: normal;
}
.lri-inv-titulo-main .lri-app-title {
    font-size: 24px;
    font-weight: 700;
    color: #f8fafc;
    line-height: 1.25;
    letter-spacing: 0.01em;
    white-space: nowrap;
    display: block;
    overflow: visible;
    padding-top: 2px;
}
.lri-inv-titulo-main .lri-app-pro {
    color: #38bdf8;
    font-weight: 800;
}
.lri-inv-titulo-main .lri-app-sub {
    font-size: 0.9rem;
    color: #94a3b8;
    margin-top: 4px;
    line-height: 1.2;
}
</style>
"""


def cabecera_modulo_inventarios(subtitulo: str | None = None) -> None:
    """Solo título «Inventory Pro» en pantalla principal (logo en sidebar)."""
    sub = (
        f'<div class="lri-app-sub">{html.escape(subtitulo)}</div>'
        if subtitulo
        else ""
    )
    st.markdown(
        f"""{_css_titulo_main()}<div class="lri-inv-titulo-main">
  <span class="lri-app-title">Inventory <span class="lri-app-pro">Pro</span></span>
  {sub}
</div>""",
        unsafe_allow_html=True,
    )


TABLA_LINE_HEIGHT = 1.3
# Títulos de bloque (Datos • Editable, etc.): más grandes que filas de parámetros.
TITULO_SECCION_EXTRA_PX = 5
TITULO_SECCION_MARGIN_BOTTOM_PX = 18
COLOR_TITULO_SECCION_EDITABLE = "#ffffff"
ANCHO_INPUT_MIN_PX = 300
ANCHO_INPUT_FACTOR = 15.0
# Filas más compactas para ver más parámetros sin scroll.
ALTURA_FILA_FACTOR = 1.85
ALTURA_FILA_MIN_PX = 42
BTN_FILA_FACTOR = 1.65
BTN_FILA_MIN_PX = 36


def _ancho_input_px(font_px: int) -> int:
    """Ancho total del set box (+ valor + −), como en el boceto del usuario."""
    return max(ANCHO_INPUT_MIN_PX, int(font_px * ANCHO_INPUT_FACTOR))


# Proporción col.2: ancho fijo del set box; col.1 acotada para no comprimir los botones +/−.
W_INP_COLUMN_RATIO_FIJO = 50
W_LAB_COLUMN_RATIO_MAX = 22


def _medidas_input(
    font_px: int,
    *,
    inp_px: int,
    campo_min_px: int = 160,
) -> tuple[int, int, int, int]:
    altura = max(ALTURA_FILA_MIN_PX, int(font_px * ALTURA_FILA_FACTOR))
    btn = max(BTN_FILA_MIN_PX, int(font_px * BTN_FILA_FACTOR))
    campo = max(campo_min_px, inp_px - 2 * btn - 10)
    return inp_px, campo, btn, altura


def medidas_input_estandar(font_px: int) -> tuple[int, int, int, int]:
    """(ancho_input_px, ancho_campo_px, btn_px, altura_fila) — referencia sección Datos."""
    return _medidas_input(font_px, inp_px=_ancho_input_px(font_px))


def parametro_acepta_decimales(tag: str, nombre: str) -> bool:
    """Montos en $ (costos/inversiones) permiten centavos; personas/metros van en enteros."""
    if "costos" in tag or "inversiones" in tag:
        return True
    if tag.endswith("_calculados") or tag.endswith("_calculado"):
        cl = nombre.lower()
        if any(k in cl for k in ("ventas", "inversión", "inversion", "costo financiero")):
            return True
    if "$" in nombre:
        return True
    return False


# Fila parámetro: etiqueta en col.1 y number_input en col.2 (mismo bloque horizontal).
_CSS_FILA_PARAM = 'div[data-testid="stHorizontalBlock"]:has(.inv-param-celda-label)'


def _css_setbox_number_input(
    scope: str,
    *,
    inp_px: int,
    campo_px: int,
    btn_px: int,
    altura_px: int,
    font_px: int,
    pad_inp: str,
    color_valor: str | None = None,
    color_fondo: str | None = None,
    color_borde: str | None = None,
) -> str:
    """Estilo unificado del set box (+/−) para un scope CSS (p. ej. col.2 de la fila)."""
    inp_h = max(44, altura_px - 8)
    fs_btn = max(16, font_px - 2)
    extra_input = ""
    if color_valor:
        extra_input = f"""
{scope} [data-testid="stNumberInput"] input {{
    color: {color_valor} !important;
    background: {color_fondo} !important;
    border: 1px solid {color_borde} !important;
}}
"""
    return f"""
{scope} [data-testid="stNumberInput"],
{scope} [data-testid="stSelectbox"] {{
    width: {inp_px}px !important;
    min-width: {inp_px}px !important;
    max-width: {inp_px}px !important;
    margin: 0 !important;
    font-size: {font_px}px !important;
}}
{scope} [data-testid="stNumberInput"] > div {{
    width: {inp_px}px !important;
    min-width: {inp_px}px !important;
    min-height: {altura_px}px !important;
    height: {altura_px}px !important;
    display: flex !important;
    flex-direction: row !important;
    align-items: center !important;
    gap: 6px !important;
    flex-wrap: nowrap !important;
    overflow: visible !important;
}}
{scope} [data-testid="stNumberInput"] button,
{scope} [data-testid="stNumberInput"] [data-baseweb="button"] {{
    display: inline-flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    pointer-events: auto !important;
    flex: 0 0 {btn_px}px !important;
    flex-shrink: 0 !important;
    font-size: {fs_btn}px !important;
    min-width: {btn_px}px !important;
    min-height: {btn_px}px !important;
    width: {btn_px}px !important;
    height: {btn_px}px !important;
    padding: 0 !important;
}}
{scope} [data-testid="stNumberInput"] input {{
    flex: 1 1 0 !important;
    min-width: 0 !important;
    max-width: calc(100% - {2 * btn_px + 12}px) !important;
    width: auto !important;
    font-size: {font_px}px !important;
    padding: {pad_inp} !important;
    min-height: {inp_h}px !important;
    height: {inp_h}px !important;
    box-sizing: border-box !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
}}
{extra_input}
"""
TABLA_ZOOM_REF_PX = 16
LayoutTabla = Literal["auto", "parametros", "ancha", "scorecard", "alternada"]
OrigenDato = Literal["neutro", "editable", "calculado"]

# Paleta tipo terminal financiero (Bloomberg / Wall Street).
WS_FONDO_TABLA = "#05080f"
WS_BORDE_TABLA = "#1e3a5f"
# Columnas ancladas al desplazar horizontalmente: codigo, categoria, subcategoria, descripcion.
WS_COLUMNAS_FIJAS = 4
WS_COLUMNA_INICIO_CENTRO = "pais"
ANCHOS_IDENTIDAD_DEFECTO: dict[str, int] = {
    "categoria": 150,
    "subcategoria": 175,
    "descripcion": 300,
}
WS_HEADER_BG = "#1a2f4a"
WS_HEADER_FG = "#e8edf4"
WS_HEADER_BORDE = "#334155"


@dataclass(frozen=True)
class EstiloColumnaWS:
    th_bg: str
    th_bg_alt: str
    th_fg: str
    td_fg: str
    td_bg: str
    td_bg_alt: str
    align: str
    ancho_px: int


_WS_ESTILOS: dict[str, EstiloColumnaWS] = {
    "identidad": EstiloColumnaWS(
        "#2d5a87", "#3d6fa3", "#ffffff", "#f8fafc", "#0a1422", "#1a3050", "left", 100
    ),
    "logistica": EstiloColumnaWS(
        "#1e4a9a", "#2860c4", "#bfdbfe", "#eff6ff", "#061428", "#102a55", "right", 90
    ),
    "demanda": EstiloColumnaWS(
        "#0e5f8c", "#1480b8", "#67e8f9", "#a5f3fc", "#041c30", "#0a3355", "right", 90
    ),
    "precio": EstiloColumnaWS(
        "#15803d", "#1ca34f", "#bbf7d0", "#ecfdf5", "#042a14", "#0a4522", "right", 100
    ),
    "costo": EstiloColumnaWS(
        "#9f1239", "#be185d", "#fecdd3", "#ffe4e6", "#3a0518", "#5c0a28", "right", 100
    ),
    "financiero": EstiloColumnaWS(
        "#15803d", "#1ca34f", "#86efac", "#dcfce7", "#042a14", "#0a4522", "right", 108
    ),
    "metrica": EstiloColumnaWS(
        "#a16207", "#ca8a04", "#fef08a", "#fffbeb", "#3d2804", "#5c3d08", "right", 92
    ),
    "default": EstiloColumnaWS(
        "#334155", "#475569", "#e2e8f0", "#f1f5f9", "#0c121c", "#1a2436", "right", 88
    ),
}


def _categoria_columna_ws(nombre: str) -> str:
    cl = nombre.lower().strip()
    if cl in ("codigo", "categoria", "subcategoria", "descripcion", "proveedor", "pais"):
        return "identidad"
    if "demanda mes" in cl:
        return "demanda"
    if any(k in cl for k in ("ventas totales", "margen bruto", "valor inv. prom", "icc asignado", "evai", "% margen", "% icc")):
        return "financiero"
    if "costo" in cl and "margen" not in cl:
        return "costo"
    if "precio" in cl:
        return "precio"
    if cl in ("rotacion", "meses inventario", "factor escazes", "margen utilidad ventas", "gmroi"):
        return "metrica"
    if any(
        k in cl
        for k in (
            "inventario", "empaque", "bultos", "cubicaje", "ordenes",
            "tiempo", "transito", "unidades", "despachados",
        )
    ):
        return "logistica"
    return "default"


def _ancho_titulo_compacto(nombre: str, font_px: int) -> int:
    """Ancho justo para el título (tabla más comprimida)."""
    return int(len(nombre) * font_px * 0.50) + 22


def _indice_columna_centro(columnas: list[str]) -> int:
    try:
        return columnas.index(WS_COLUMNA_INICIO_CENTRO)
    except ValueError:
        return WS_COLUMNAS_FIJAS


def _align_columna_ws(nombre: str, col_idx: int, columnas: list[str]) -> str:
    """Izquierda en columnas fijas de lectura; centro desde país en adelante."""
    if col_idx >= _indice_columna_centro(columnas):
        return "center"
    cl = nombre.lower().strip()
    if cl in ("codigo", "categoria", "subcategoria", "descripcion", "proveedor"):
        return "left"
    return "center"


def _ancho_columna_ws(
    nombre: str,
    font_px: int = TABLA_FONT_SIZE_DEFAULT,
    *,
    anchos_manual: dict[str, int] | None = None,
) -> int:
    """Ancho por columna: manual en identidad; compacto en el resto (título completo)."""
    cl = nombre.lower().strip()
    manual = anchos_manual or {}
    if cl in manual:
        return int(manual[cl])
    if cl in ANCHOS_IDENTIDAD_DEFECTO and cl not in manual:
        return max(ANCHOS_IDENTIDAD_DEFECTO[cl], _ancho_titulo_compacto(nombre, font_px))

    titulo = _ancho_titulo_compacto(nombre, font_px)

    if cl == "codigo":
        return max(118, min(titulo, 132))
    if cl == "proveedor":
        return max(108, titulo)
    if "demanda mes" in cl:
        return max(66, titulo)
    if cl in ("empaque", "pais", "rotacion", "factor escazes"):
        return max(56, titulo)

    minimo = _WS_ESTILOS[_categoria_columna_ws(nombre)].ancho_px
    return max(minimo, titulo)


def _anchos_columnas_ws(
    columnas: list[str],
    font_px: int,
    *,
    anchos_manual: dict[str, int] | None = None,
) -> list[int]:
    return [_ancho_columna_ws(c, font_px, anchos_manual=anchos_manual) for c in columnas]


def _left_columna_fija(anchos: list[int], col_idx: int) -> int:
    return sum(anchos[:col_idx])


def _fondo_intercalado_ws(est: EstiloColumnaWS, *, fila_idx: int, col_idx: int, es_header: bool) -> str:
    """Bandas visibles alternando fila + columna (más ritmo de color)."""
    par = (fila_idx + col_idx) % 2
    if es_header:
        return est.th_bg if par == 0 else est.th_bg_alt
    return est.td_bg if par == 0 else est.td_bg_alt


def _estilo_sticky_celda_ws(*, es_header: bool, col_idx: int, left_px: int) -> str:
    """Solo columnas fijas: anclaje horizontal; encabezado fijo también arriba."""
    z = 55 + col_idx if es_header else 20 + col_idx
    sombra = ""
    if col_idx == WS_COLUMNAS_FIJAS - 1:
        sombra = "box-shadow:6px 0 12px rgba(0,0,0,0.45);"
    if es_header:
        return f"position:sticky;top:0;left:{left_px}px;z-index:{z};{sombra}"
    return f"position:sticky;left:{left_px}px;z-index:{z};{sombra}"


def _estilo_columna_ws(
    nombre: str,
    *,
    es_header: bool,
    font_px: int,
    fila_idx: int = 0,
    col_idx: int = 0,
    left_fijo: int | None = None,
    columnas: list[str] | None = None,
) -> str:
    cat = _categoria_columna_ws(nombre)
    est = _WS_ESTILOS[cat]
    pad = _padding_celda(font_px)
    bg = _fondo_intercalado_ws(est, fila_idx=fila_idx, col_idx=col_idx, es_header=es_header)
    align = "center" if es_header else (
        _align_columna_ws(nombre, col_idx, columnas) if columnas else est.align
    )
    base = (
        f"font-size:{font_px}px;line-height:{TABLA_LINE_HEIGHT};vertical-align:middle;"
        f"padding:{pad};text-align:{align};white-space:nowrap;"
    )
    if left_fijo is not None:
        sticky = _estilo_sticky_celda_ws(es_header=es_header, col_idx=col_idx, left_px=left_fijo)
    elif es_header:
        sticky = "position:sticky;top:0;z-index:35;"
    else:
        sticky = ""
    if es_header:
        return (
            f"{base}font-weight:600;color:{WS_HEADER_FG};background:{WS_HEADER_BG};"
            f"border-bottom:none;border-right:1px solid {WS_HEADER_BORDE};"
            f"{sticky}overflow:visible;text-overflow:clip;"
        )
    clip = "overflow:hidden;text-overflow:ellipsis;"
    nums = "font-variant-numeric:tabular-nums;" if align != "left" else ""
    if align == "left" and left_fijo is None:
        clip += "max-width:0;"
    return (
        f"{base}{nums}{clip}color:{est.td_fg};background:{bg};"
        f"border-bottom:1px solid #243b53;border-right:1px solid #1e293b;{sticky}"
    )

# Manual = editable. Rojo suave = calculado por el sistema (solo lectura).
# Naranja = reservado (tablas HTML legacy); no usar en set boxes de parámetros.
COLOR_EDITABLE_TEXTO = "#4ade80"
COLOR_EDITABLE_VALOR = "#86efac"
COLOR_EDITABLE_FONDO_INPUT = "rgba(34,197,94,0.12)"
COLOR_SISTEMA_TEXTO = "#f87171"
COLOR_SISTEMA_VALOR = "#fecaca"
COLOR_SISTEMA_FONDO = "#2a1216"
COLOR_SISTEMA_BORDE = "rgba(248, 113, 113, 0.55)"
COLOR_CALCULADO_TEXTO = "#fb923c"
COLOR_CALCULADO_VALOR = "#fdba74"
COLOR_CALCULADO_FONDO = "#2a1f14"

# Scorecard: color por columna de categoría y filas meta / total.
SCORECARD_PALETA_COLUMNAS: list[tuple[str, str]] = [
    ("#1e3a5f", "#dbeafe"),
    ("#14532d", "#bbf7d0"),
    ("#713f12", "#fef08a"),
    ("#581c87", "#e9d5ff"),
    ("#134e4a", "#99f6e4"),
    ("#7f1d1d", "#fecaca"),
    ("#365314", "#d9f99d"),
    ("#1e3a8a", "#bfdbfe"),
]
SCORECARD_CELDA_META = ("#111827", "#e2e8f0")
SCORECARD_CELDA_DRIVER = ("#1e293b", "#cbd5e1")
SCORECARD_CELDA_TOTAL = ("#334155", "#fde68a")
SCORECARD_DRIVER_CARD_COLORS = [
    ("#0c2a3a", "#38bdf8"),  # celeste
    ("#14532d", "#4ade80"),  # verde
    ("#1e293b", "#ffffff"),  # blanco (antes amarillo)
    ("#581c87", "#c084fc"),  # morado / lila
]
# Cuatro tonos base (celeste, verde, blanco, morado) — se repiten en ciclo.
ASIGNACION_LINEA_ACENTOS = [
    "#38bdf8", "#4ade80", "#f1f5f9", "#c084fc",
]
# (borde, texto cuenta, fondo)
ASIGNACION_LINEA_PALETA: list[tuple[str, str, str]] = [
    ("#0ea5e9", "#7dd3fc", "rgba(12,35,55,0.55)"),
    ("#22c55e", "#86efac", "rgba(20,50,30,0.5)"),
    ("#e2e8f0", "#ffffff", "rgba(30,35,48,0.6)"),
    ("#a855f7", "#d8b4fe", "rgba(45,25,70,0.5)"),
]
ASIGNACION_DRIVERS_FONT_PX = 23
# Colores por tipo de driver (fondo, texto, borde) — mismos cuatro tonos en rotación.
PALETA_DRIVER_ASIGNACION: list[tuple[str, str, str]] = [
    ("#0c2a3a", "#7dd3fc", "#38bdf8"),
    ("#14532d", "#86efac", "#4ade80"),
    ("#1e293b", "#ffffff", "#f1f5f9"),
    ("#581c87", "#d8b4fe", "#c084fc"),
]
PALETA_FILAS_SCORECARD: list[tuple[str, str]] = [
    ("#0f2a38", "#bae6fd"),
    ("#1a2f22", "#d1fae5"),
    ("#1e293b", "#ffffff"),
    ("#2a1a38", "#ede9fe"),
]
# Tablas ROI / KPI: fila celeste, fila gris — texto blanco en datos.
PALETA_FILAS_ALTERNADAS: list[tuple[str, str]] = [
    ("#0c4a6e", "#ffffff"),
    ("#334155", "#ffffff"),
]
PALETA_FILAS_RESUMEN_KPI = PALETA_FILAS_ALTERNADAS


def es_tag_calculado_sistema(tag: str | None) -> bool:
    if not tag:
        return False
    return tag.endswith("_calculados") or tag.endswith("_calculado")


def colores_calculado_sistema() -> ColoresGrupoParam:
    return ColoresGrupoParam(
        COLOR_SISTEMA_TEXTO,
        COLOR_SISTEMA_VALOR,
        COLOR_SISTEMA_FONDO,
        COLOR_SISTEMA_BORDE,
    )


@dataclass(frozen=True)
class ColoresGrupoParam:
    texto: str
    valor: str
    fondo_input: str
    borde_input: str


# Colores por grupo de inputs (Datos / Costos / Inversiones, etc.)
_COLORES_GRUPO: dict[str, ColoresGrupoParam] = {
    "alm_datos": ColoresGrupoParam("#38bdf8", "#e0f2fe", "rgba(56,189,248,0.18)", "rgba(56,189,248,0.65)"),
    "alm_costosgastos": ColoresGrupoParam("#fbbf24", "#fef3c7", "rgba(251,191,36,0.18)", "rgba(251,191,36,0.65)"),
    "alm_inversiones": ColoresGrupoParam("#c084fc", "#f3e8ff", "rgba(192,132,252,0.18)", "rgba(192,132,252,0.65)"),
    "inv_datos": ColoresGrupoParam("#2dd4bf", "#ccfbf1", "rgba(45,212,191,0.18)", "rgba(45,212,191,0.65)"),
    "inv_costosgastos": ColoresGrupoParam("#fbbf24", "#fef3c7", "rgba(251,191,36,0.18)", "rgba(251,191,36,0.65)"),
    "inv_inversiones": ColoresGrupoParam("#f472b6", "#fce7f3", "rgba(244,114,182,0.18)", "rgba(244,114,182,0.65)"),
    "inv_datos_calculados": colores_calculado_sistema(),
    "inv_inversiones_calculado": colores_calculado_sistema(),
    "gen_financieros_calculados": colores_calculado_sistema(),
    "gen_financieros": ColoresGrupoParam("#4ade80", "#dcfce7", "rgba(74,222,128,0.18)", "rgba(74,222,128,0.65)"),
    "gen_operativos": ColoresGrupoParam("#f87171", "#fee2e2", "rgba(248,113,113,0.18)", "rgba(248,113,113,0.65)"),
}


def colores_grupo_parametros(tag: str) -> ColoresGrupoParam:
    if tag in _COLORES_GRUPO:
        return _COLORES_GRUPO[tag]
    if "costos" in tag:
        return _COLORES_GRUPO["alm_costosgastos"]
    if "inversiones" in tag or "inversion" in tag:
        return _COLORES_GRUPO["alm_inversiones"]
    if "datos" in tag:
        return _COLORES_GRUPO["alm_datos"]
    return ColoresGrupoParam(
        COLOR_EDITABLE_TEXTO,
        COLOR_EDITABLE_VALOR,
        COLOR_EDITABLE_FONDO_INPUT,
        "rgba(74, 222, 128, 0.55)",
    )


def _padding_celda(font_px: int) -> str:
    v = max(3, font_px // 6)
    h = max(5, font_px // 3)
    return f"{v}px {h}px"


def css_interfaz(zoom_pct: int, tabla_font_px: int) -> str:
    """CSS global: tipografía en tablas HTML, Glide, inputs y formularios compactos."""
    pad_inp = _padding_celda(tabla_font_px)
    escala_glide = tabla_font_px / TABLA_ZOOM_REF_PX
    ancho_input = _ancho_input_px(tabla_font_px)
    alto_fila = max(ALTURA_FILA_MIN_PX, int(tabla_font_px * ALTURA_FILA_FACTOR))
    alto_btn = max(BTN_FILA_MIN_PX, int(tabla_font_px * BTN_FILA_FACTOR))
    ancho_campo = max(160, ancho_input - 2 * alto_btn - 12)
    return f"""
<style>
.stApp {{
    zoom: {zoom_pct / 100};
}}
section[data-testid="stMain"] > div {{
    padding-top: 4px !important;
}}
section[data-testid="stMain"] .block-container {{
    /* Sin font-size global: evita recortar el logo en contenedores Streamlit. */
    padding-top: 1.5rem !important;
    padding-bottom: 0.35rem !important;
    padding-left: 1rem !important;
    padding-right: 0.75rem !important;
    max-width: 100% !important;
}}
section[data-testid="stMain"] div[data-testid="stElementContainer"]:has(.lri-inv-titulo-main),
section[data-testid="stMain"] div[data-testid="stMarkdownContainer"]:has(.lri-inv-titulo-main),
section[data-testid="stMain"] div[data-testid="stElementContainer"]:has(.inv-leyenda-param),
section[data-testid="stMain"] div[data-testid="stMarkdownContainer"]:has(.inv-leyenda-param) {{
    overflow: visible !important;
    max-height: none !important;
    height: auto !important;
}}
section[data-testid="stMain"] div[data-testid="stElementContainer"]:has(.inv-leyenda-param),
section[data-testid="stMain"] div[data-testid="stMarkdownContainer"]:has(.inv-leyenda-param) {{
    padding-top: 2px !important;
}}
section[data-testid="stMain"] .block-container p,
section[data-testid="stMain"] .block-container li,
section[data-testid="stMain"] .block-container td,
section[data-testid="stMain"] .block-container th,
section[data-testid="stMain"] .block-container [data-testid="stAlert"],
section[data-testid="stMain"] .block-container [data-testid="stRadio"],
section[data-testid="stMain"] .block-container [data-testid="stExpander"],
section[data-testid="stMain"] .block-container [data-testid="stInfo"],
section[data-testid="stMain"] .block-container [data-testid="stWarning"],
section[data-testid="stMain"] .block-container [data-testid="stSuccess"],
section[data-testid="stMain"] .block-container [data-testid="stError"] {{
    font-size: {tabla_font_px}px;
}}
section[data-testid="stMain"] h1 {{
    font-size: {tabla_font_px + 6}px !important;
}}
section[data-testid="stMain"] h2, section[data-testid="stMain"] h3 {{
    font-size: {tabla_font_px + 3}px !important;
}}
section[data-testid="stMain"] .stCaption, section[data-testid="stMain"] label {{
    font-size: {tabla_font_px}px !important;
}}
/* Tablas Glide (scorecard y similares) */
div[data-testid="stDataEditor"] {{
    zoom: {escala_glide};
    max-width: 100%;
    overflow-x: auto;
}}
div[data-testid="stDataEditor"] [role="gridcell"],
div[data-testid="stDataEditor"] [role="columnheader"],
div[data-testid="stDataEditor"] input,
div[data-testid="stDataEditor"] select {{
    font-size: {tabla_font_px}px !important;
    line-height: {TABLA_LINE_HEIGHT} !important;
}}
/* Parámetros: etiquetas y set boxes a {tabla_font_px}px */
.inv-param-celda-label {{
    font-size: {tabla_font_px}px !important;
    font-weight: 500 !important;
}}
{_CSS_FILA_PARAM} > [data-testid="column"]:nth-child(2) [data-testid="stSelectbox"] > div > div {{
    font-size: {tabla_font_px}px !important;
    min-height: {alto_fila}px !important;
}}
{_css_setbox_number_input(
    f'{_CSS_FILA_PARAM} > [data-testid="column"]:nth-child(2)',
    inp_px=ancho_input,
    campo_px=ancho_campo,
    btn_px=alto_btn,
    altura_px=alto_fila,
    font_px=tabla_font_px,
    pad_inp=pad_inp,
)}
/* Col.1 atributos (izq.) | col.2 set box fijo (mismo tamaño en Datos, Costos e Inversiones) */
{_CSS_FILA_PARAM} {{
    display: grid !important;
    grid-template-columns: minmax(0, 1fr) {ancho_input}px !important;
    align-items: center !important;
    gap: 0 6px !important;
    margin: 0 !important;
    justify-content: flex-start !important;
    width: 100% !important;
    max-width: 100% !important;
}}
{_CSS_FILA_PARAM} > [data-testid="column"] {{
    flex: unset !important;
    min-width: 0 !important;
}}
{_CSS_FILA_PARAM} > [data-testid="column"]:nth-child(1) {{
    grid-column: 1 !important;
    width: auto !important;
    max-width: 100% !important;
    overflow: visible !important;
}}
{_CSS_FILA_PARAM} > [data-testid="column"]:nth-child(2) {{
    grid-column: 2 !important;
    width: {ancho_input}px !important;
    min-width: {ancho_input}px !important;
    max-width: {ancho_input}px !important;
    flex-shrink: 0 !important;
}}
div[data-testid="stVerticalBlock"]:has(.inv-param-celda-label) {{
    gap: 0.15rem !important;
}}
div[data-testid="stVerticalBlock"]:has(.inv-param-bloque-tabla) {{
    gap: 0.15rem !important;
}}
section[data-testid="stMain"] hr,
div[data-testid="stDivider"] {{
    margin: 0.35rem 0 !important;
}}
.inv-separador-param {{
    border-top: 1px solid #2d3142;
    margin: 0.35rem 0 !important;
    height: 0;
    padding: 0;
}}
{_CSS_FILA_PARAM} > [data-testid="column"] {{
    padding: 0 !important;
    align-self: center !important;
}}
{_CSS_FILA_PARAM} > [data-testid="column"]:nth-child(2) {{
    padding-left: 2px !important;
    min-width: {ancho_input}px !important;
    flex-shrink: 0 !important;
}}
.inv-param-celda-label {{
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
    text-align: left !important;
    padding: 0 4px 0 0 !important;
    margin: 0 !important;
    white-space: nowrap !important;
    box-sizing: border-box !important;
    width: 100% !important;
}}
.inv-param-bloque-tabla {{
    margin-left: 0 !important;
    padding-left: 0 !important;
    width: fit-content !important;
    max-width: 100% !important;
}}
div[data-testid="stVerticalBlock"]:has(.inv-param-bloque-tabla) {{
    align-items: flex-start !important;
}}
.inv-titulo-seccion-param {{
    font-size: {tabla_font_px + TITULO_SECCION_EXTRA_PX}px !important;
    text-align: left !important;
    margin: 0 0 {TITULO_SECCION_MARGIN_BOTTOM_PX}px 0 !important;
    padding: 0 !important;
    line-height: 1.25 !important;
}}
.inv-param-label {{
    margin: 0;
    padding: 2px 0;
    line-height: {TABLA_LINE_HEIGHT};
    color: #fafafa;
    font-weight: 500;
}}
.inv-param-editable .inv-param-label {{
    color: {COLOR_EDITABLE_TEXTO} !important;
}}
.inv-param-editable [data-testid="stNumberInput"] input {{
    color: {COLOR_EDITABLE_VALOR} !important;
    border: 1px solid rgba(74, 222, 128, 0.55) !important;
    background: {COLOR_EDITABLE_FONDO_INPUT} !important;
}}
.inv-param-calculado [data-testid="stNumberInput"] button {{
    pointer-events: none !important;
    opacity: 0.45 !important;
    cursor: default !important;
}}
.inv-param-calculado [data-testid="stNumberInput"] input {{
    color: {COLOR_SISTEMA_VALOR} !important;
    border: 1px solid {COLOR_SISTEMA_BORDE} !important;
    background: {COLOR_SISTEMA_FONDO} !important;
    cursor: default !important;
}}
.inv-tabla-scroll.inv-tabla-calculado {{
    border-left: 3px solid {COLOR_SISTEMA_TEXTO};
}}
.inv-tabla-scroll {{
    line-height: {TABLA_LINE_HEIGHT};
}}
.inv-tabla-ws-wrap {{
    box-shadow: inset 0 0 0 1px {WS_BORDE_TABLA};
    overflow-x: scroll !important;
    overflow-y: auto !important;
    scrollbar-gutter: stable both-edges;
    scrollbar-width: auto;
    scrollbar-color: #3b82f6 #0a0f1a;
}}
.inv-tabla-ws-wrap .inv-tabla-ws thead tr {{
    border-bottom: 2px solid {WS_HEADER_BORDE};
}}
.inv-tabla-ws-wrap .inv-tabla-ws thead th {{
    position: sticky !important;
    top: 0 !important;
    z-index: 35 !important;
    box-shadow: none !important;
    border-bottom: none !important;
    background: {WS_HEADER_BG} !important;
    color: {WS_HEADER_FG} !important;
}}
.inv-tabla-ws-wrap .inv-tabla-ws thead th[style*="left:"] {{
    z-index: 55 !important;
}}
.inv-tabla-ws-wrap .inv-tabla-ws th,
.inv-tabla-ws-wrap .inv-tabla-ws td {{
    background-clip: padding-box;
}}
.inv-tabla-ws-wrap::-webkit-scrollbar {{
    height: 26px;
    width: 22px;
}}
.inv-tabla-ws-wrap::-webkit-scrollbar-track {{
    background: #0a0f1a;
    border-radius: 10px;
    margin: 2px;
}}
.inv-tabla-ws-wrap::-webkit-scrollbar-thumb {{
    background: linear-gradient(180deg, #60a5fa 0%, #2563eb 55%, #1d4ed8 100%);
    border-radius: 10px;
    border: 3px solid #0a0f1a;
    min-height: 48px;
    min-width: 48px;
}}
.inv-tabla-ws-wrap::-webkit-scrollbar-thumb:hover {{
    background: linear-gradient(180deg, #93c5fd 0%, #3b82f6 55%, #2563eb 100%);
}}
.inv-tabla-alternada-wrap {{
    box-shadow: inset 0 0 0 1px {WS_BORDE_TABLA};
}}
.inv-tabla-alternada-wrap .inv-tabla-ws thead th {{
    position: sticky !important;
    top: 0 !important;
    z-index: 35 !important;
    background-clip: padding-box !important;
    height: auto !important;
    min-height: 2.6em;
    overflow: visible !important;
    vertical-align: middle;
    line-height: 1.25 !important;
    padding-top: 6px !important;
    padding-bottom: 6px !important;
}}
.inv-tabla-alternada-wrap .inv-tabla-ws thead th[style*="left:"] {{
    z-index: 55 !important;
}}
.inv-tabla-scroll.inv-tabla-alternada-wrap {{
    overscroll-behavior: contain;
}}
.inv-tabla-head-flow .inv-tabla-ws thead th {{
    position: relative !important;
    top: auto !important;
    z-index: 20 !important;
    min-height: 52px !important;
    height: auto !important;
    overflow: visible !important;
    white-space: normal !important;
    word-break: break-word !important;
    line-height: 1.3 !important;
    vertical-align: middle !important;
}}
.inv-tabla-head-flow .inv-tabla-ws thead th[style*="left:"] {{
    position: sticky !important;
    top: auto !important;
    z-index: 30 !important;
}}
.inv-tabla-scorecard-wrap {{
    box-shadow: inset 0 0 0 1px #334155;
    overflow-x: scroll !important;
    overflow-y: auto !important;
    scrollbar-gutter: stable both-edges;
    scrollbar-width: auto;
    scrollbar-color: #38bdf8 #0a0f1a;
}}
.inv-tabla-scorecard-wrap .inv-tabla-scorecard thead th {{
    position: sticky !important;
    top: 0 !important;
    z-index: 40 !important;
    background-clip: padding-box !important;
}}
.inv-tabla-scorecard-wrap .inv-tabla-scorecard thead th[style*="left:"] {{
    z-index: 56 !important;
}}
.inv-tabla-scorecard-wrap .inv-tabla-scorecard th,
.inv-tabla-scorecard-wrap .inv-tabla-scorecard td {{
    background-clip: padding-box;
}}
.inv-tabla-scorecard-wrap::-webkit-scrollbar {{
    height: 26px;
    width: 22px;
}}
.inv-tabla-scorecard-wrap::-webkit-scrollbar-track {{
    background: #0a0f1a;
    border-radius: 10px;
    margin: 2px;
}}
.inv-tabla-scorecard-wrap::-webkit-scrollbar-thumb {{
    background: linear-gradient(180deg, #7dd3fc 0%, #0ea5e9 55%, #0284c7 100%);
    border-radius: 10px;
    border: 3px solid #0a0f1a;
    min-height: 48px;
    min-width: 48px;
}}
.inv-tabla-scorecard-wrap::-webkit-scrollbar-thumb:hover {{
    background: linear-gradient(180deg, #bae6fd 0%, #38bdf8 55%, #0ea5e9 100%);
}}
.inv-tabla-scorecard-wrap::-webkit-scrollbar-corner {{
    background: #0a0f1a;
}}
.inv-tabla-scorecard-wrap.inv-tabla-kpi-completa {{
    overflow-y: hidden !important;
    min-height: unset !important;
}}
section[data-testid="stMain"] [data-testid="stVerticalBlock"] {{
    gap: 0.35rem !important;
}}
</style>
"""


def controles_ancho_columnas_tabla() -> dict[str, int]:
    """Sliders para ensanchar columnas de lectura (similar a arrastrar en Excel)."""
    with st.expander("📐 Ajustar ancho de columnas", expanded=False):
        st.caption(
            "Ensanche **categoría**, **subcategoría** y **descripción** para leer mejor. "
            "El resto de columnas se mantienen compactas."
        )
        c1, c2, c3 = st.columns(3)
        return {
            "categoria": c1.slider(
                "Categoría (px)",
                min_value=120,
                max_value=320,
                value=ANCHOS_IDENTIDAD_DEFECTO["categoria"],
                key="inv_tabla_w_categoria",
            ),
            "subcategoria": c2.slider(
                "Subcategoría (px)",
                min_value=140,
                max_value=360,
                value=ANCHOS_IDENTIDAD_DEFECTO["subcategoria"],
                key="inv_tabla_w_subcategoria",
            ),
            "descripcion": c3.slider(
                "Descripción (px)",
                min_value=220,
                max_value=520,
                value=ANCHOS_IDENTIDAD_DEFECTO["descripcion"],
                key="inv_tabla_w_descripcion",
            ),
        }


def leyenda_tabla_wall_street() -> None:
    """Leyenda compacta de colores por tipo de columna (estilo terminal financiero)."""
    items = [
        ("Identidad", _WS_ESTILOS["identidad"].th_fg),
        ("Logística", _WS_ESTILOS["logistica"].th_fg),
        ("Demanda", _WS_ESTILOS["demanda"].th_fg),
        ("Precios", _WS_ESTILOS["precio"].th_fg),
        ("Costos", _WS_ESTILOS["costo"].th_fg),
        ("Financiero", _WS_ESTILOS["financiero"].th_fg),
        ("Métricas", _WS_ESTILOS["metrica"].th_fg),
    ]
    chips = " ".join(
        f'<span style="color:{color};font-weight:700;margin-right:14px;">■ {label}</span>'
        for label, color in items
    )
    st.markdown(
        f'<div style="font-size:{TABLA_FONT_SIZE_DEFAULT}px;line-height:{TABLA_LINE_HEIGHT};'
        f'margin:0 0 10px 0;color:#94a3b8;">{chips}</div>',
        unsafe_allow_html=True,
    )


def leyenda_scorecard_columnas(
    n_categorias: int,
    nombres: list[str] | None = None,
) -> None:
    """Paleta por columna de categoría (tabla de KPI's)."""
    n = min(n_categorias, len(SCORECARD_PALETA_COLUMNAS))
    if n <= 0:
        return
    chips = []
    for i in range(n):
        bg, fg = SCORECARD_PALETA_COLUMNAS[i]
        etiqueta = (
            str(nombres[i])
            if nombres is not None and i < len(nombres)
            else f"Cat. {i + 1}"
        )
        chips.append(
            f'<span style="display:inline-block;margin:0 8px 4px 0;padding:2px 10px;'
            f"border-radius:4px;background:{bg};color:{fg};font-size:13px;"
            f'">{html.escape(etiqueta)}</span>'
        )
    st.markdown(
        f'<div style="margin:4px 0 10px 0;">{"".join(chips)}'
        '<span style="color:#64748b;font-size:13px;margin-left:6px;">'
        "Color por columna de categoría</span></div>",
        unsafe_allow_html=True,
    )


def leyenda_scorecard_colores(n_filas: int) -> None:
    """Muestra la paleta de filas del scorecard (líneas contables)."""
    n = min(max(n_filas, 0), len(PALETA_FILAS_SCORECARD))
    if n <= 0:
        return
    chips = []
    for i in range(n):
        bg, fg = PALETA_FILAS_SCORECARD[i]
        chips.append(
            f'<span style="display:inline-block;margin:0 8px 4px 0;padding:2px 10px;'
            f"border-radius:4px;background:{bg};color:{fg};font-size:13px;"
            f'">Línea {i + 1}</span>'
        )
    chips.append(
        f'<span style="display:inline-block;margin:0 8px 4px 0;padding:2px 10px;'
        f"border-radius:4px;background:{SCORECARD_CELDA_TOTAL[0]};"
        f'color:{SCORECARD_CELDA_TOTAL[1]};font-size:13px;">Total</span>'
    )
    st.markdown(
        f'<div style="margin:4px 0 10px 0;">{"".join(chips)}'
        '<span style="color:#64748b;font-size:13px;margin-left:6px;">'
        "Color por fila de línea contable · fila final = totales</span></div>",
        unsafe_allow_html=True,
    )


def leyenda_origen_parametros() -> None:
    """Leyenda: colores por grupo (Datos/Costos/Inversiones) y naranja desde Excel."""
    c_d = colores_grupo_parametros("alm_datos")
    c_c = colores_grupo_parametros("alm_costosgastos")
    c_i = colores_grupo_parametros("alm_inversiones")
    st.markdown(
        f"""
<div class="inv-leyenda-param" style="display:flex;flex-wrap:wrap;gap:12px 20px;
            margin:6px 0 12px 0;padding-top:4px;
            font-size:{TABLA_FONT_SIZE_DEFAULT}px;line-height:{TABLA_LINE_HEIGHT};">
  <span><span style="color:{c_d.texto};font-weight:700;">■ Datos</span>
        — manual</span>
  <span><span style="color:{c_c.texto};font-weight:700;">■ Costos</span>
        — manual</span>
  <span><span style="color:{c_i.texto};font-weight:700;">■ Inversiones</span>
        — manual</span>
  <span><span style="color:{COLOR_SISTEMA_TEXTO};font-weight:700;">■ Rojo suave</span>
        — calculado por el sistema (set box fijo, solo lectura)</span>
  <span><span style="color:{COLOR_CALCULADO_TEXTO};font-weight:700;">■ Naranja</span>
        — tablas derivadas del Excel (si aplica)</span>
</div>
""",
        unsafe_allow_html=True,
    )


def titulo_seccion_parametros(
    titulo: str,
    *,
    editable: bool,
    font_px: int | None = None,
    tag: str | None = None,
) -> None:
    fs_base = font_px if font_px is not None else TABLA_FONT_SIZE_DEFAULT
    fs_titulo = fs_base + TITULO_SECCION_EXTRA_PX
    fs_badge = fs_base + max(4, TITULO_SECCION_EXTRA_PX - 2)
    mb = TITULO_SECCION_MARGIN_BOTTOM_PX
    if editable:
        badge = (
            f'<span style="color:{COLOR_TITULO_SECCION_EDITABLE};font-size:{fs_badge}px;'
            f'font-weight:600;margin-left:12px;">● Editable</span>'
        )
        color_titulo = COLOR_TITULO_SECCION_EDITABLE
    else:
        badge = (
            f'<span style="color:{COLOR_SISTEMA_TEXTO};font-size:{fs_badge}px;'
            f'font-weight:600;margin-left:12px;">● Calculado</span>'
        )
        color_titulo = COLOR_SISTEMA_TEXTO
    st.markdown(
        f'<p class="inv-titulo-seccion-param" style="font-size:{fs_titulo}px;font-weight:700;'
        f'line-height:1.25;margin:0 0 {mb}px 0;color:{color_titulo};">'
        f'{titulo}{badge}</p>',
        unsafe_allow_html=True,
    )


def separador_parametros() -> None:
    """Separador fino entre bloques (menos espacio que st.divider)."""
    st.markdown('<div class="inv-separador-param"></div>', unsafe_allow_html=True)


def titulo_seccion_scorecard(
    nivel: int,
    titulo: str,
    *,
    subtitulo: str | None = None,
    font_px: int | None = None,
) -> None:
    """Encabezado numerado para los tres bloques del tablero financiero."""
    fs_base = font_px if font_px is not None else TABLA_FONT_SIZE_DEFAULT
    fs_titulo = fs_base + TITULO_SECCION_EXTRA_PX + 1
    fs_nivel = fs_base
    fs_sub = max(fs_base - 1, TABLA_FONT_SIZE_MIN)
    mb = TITULO_SECCION_MARGIN_BOTTOM_PX
    sub_html = (
        f'<div style="font-size:{fs_sub}px;color:#94a3b8;font-weight:400;'
        f'margin-top:4px;line-height:1.3;">{html.escape(subtitulo)}</div>'
        if subtitulo
        else ""
    )
    st.markdown(
        f'<div class="inv-titulo-seccion-scorecard" style="margin:0 0 {mb}px 0;">'
        f'<p style="font-size:{fs_titulo}px;font-weight:700;line-height:1.25;'
        f'margin:0;color:#38bdf8;">'
        f'<span style="font-size:{fs_nivel}px;color:#64748b;font-weight:600;'
        f'margin-right:10px;">Nivel {nivel}</span>{html.escape(titulo)}</p>'
        f"{sub_html}</div>",
        unsafe_allow_html=True,
    )


def separador_scorecard() -> None:
    """Separador entre bloques del scorecard (más aire que parámetros)."""
    st.markdown(
        '<div class="inv-separador-scorecard" style="border-top:1px solid #2d3142;'
        'margin:1.25rem 0 0.75rem 0;height:0;padding:0;"></div>',
        unsafe_allow_html=True,
    )


def _extraer_tabla_html(html: str) -> str:
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.S | re.I)
    m = re.search(r"<table[^>]*>.*?</table>", html, flags=re.S | re.I)
    return m.group(0) if m else html


def _preparar_html_scorecard_resumen(html: str) -> str:
    """Encabezado único: esquina «Métrica» + nombres de categoría a color."""
    html = re.sub(
        r"(<thead>\s*<tr>.*?</tr>)\s*<tr>.*?</tr>",
        r"\1",
        html,
        count=1,
        flags=re.I | re.S,
    )
    return re.sub(
        r'(<thead>\s*<tr>\s*<th[^>]*class="[^"]*blank[^"]*"[^>]*>)\s*(?:&nbsp;|\s)*(</th>)',
        r"\1Métrica\2",
        html,
        count=1,
        flags=re.I | re.S,
    )


def _merge_style_attr(tag: str, estilo: str) -> str:
    if 'style="' in tag:
        return tag.replace('style="', f'style="{estilo}', 1)
    return tag[:-1] + f' style="{estilo}">'


def _detectar_layout(df: pd.DataFrame) -> LayoutTabla:
    cols = list(df.columns)
    if cols == ["Parámetro", "Valor"]:
        return "parametros"
    if len(cols) >= 6:
        return "ancha"
    return "ancha"


def _columnas_texto(layout: LayoutTabla, hide_index: bool) -> int:
    if layout == "parametros":
        return 1
    if layout == "scorecard":
        return 1 if not hide_index else 2
    return 0


def _meta_scorecard(columnas: list[str] | None, hide_index: bool) -> tuple[int, int]:
    """Columnas meta (concepto + driver) y cola (totales) en tablas scorecard."""
    if columnas and hide_index and "Drivers" in columnas:
        return 2, 2
    if not hide_index:
        return 1, 0
    tail = 2 if columnas and "Costo Totales" in columnas else 0
    return 1, tail


def _anchos_scorecard_px(columnas: list[str], font_px: int) -> list[int]:
    anchos: list[int] = []
    for i, col in enumerate(columnas):
        nombre = str(col)
        if i == 0:
            anchos.append(max(220, min(300, len(nombre) * 8 + 48)))
        elif nombre == "Drivers":
            anchos.append(128)
        elif nombre in ("Costo Totales", "% Costo"):
            anchos.append(max(118, int(font_px * 5.8)))
        else:
            anchos.append(max(96, int(font_px * 4.6)))
    return anchos


def _sticky_scorecard(
    col_i: int,
    meta_cols: int,
    anchos: list[int] | None,
    *,
    es_header: bool,
) -> str:
    """Encabezado fijo arriba; columnas meta (cuenta/driver o KPI) fijas a la izquierda."""
    if es_header:
        if col_i < meta_cols and anchos:
            left = sum(anchos[:col_i])
            z = 56 + col_i
            sombra = (
                "box-shadow:6px 0 12px rgba(0,0,0,0.45);"
                if col_i == meta_cols - 1
                else ""
            )
            return f"position:sticky;top:0;left:{left}px;z-index:{z};{sombra}"
        return "position:sticky;top:0;z-index:40;"
    if col_i < meta_cols and anchos:
        left = sum(anchos[:col_i])
        z = 22 + col_i
        sombra = (
            "box-shadow:6px 0 12px rgba(0,0,0,0.45);"
            if col_i == meta_cols - 1
            else ""
        )
        return f"position:sticky;left:{left}px;z-index:{z};{sombra}"
    return ""


def _estilo_celda_alternada(
    col_i: int,
    fila_i: int,
    font_px: int,
    *,
    es_header: bool,
    columnas: list[str] | None,
    left_fijo: int | None = None,
    resaltar_negativo: bool = False,
    color_texto: str | None = None,
    cabecera_sticky_vertical: bool = True,
) -> str:
    pad = _padding_celda(font_px)
    alto = max(38, int(font_px * 1.45))
    if es_header:
        alto_hdr = max(48, int(font_px * 1.75))
        base = (
            f"font-size:{font_px}px;line-height:1.2;vertical-align:middle;"
            f"padding:{pad};min-height:{alto_hdr}px;height:auto;"
            f"box-sizing:border-box;border-bottom:1px solid #334155;"
        )
    else:
        base = (
            f"font-size:{font_px}px;line-height:{TABLA_LINE_HEIGHT};vertical-align:middle;"
            f"padding:{pad};min-height:{alto}px;height:{alto}px;"
            f"box-sizing:border-box;border-bottom:1px solid #334155;"
        )
    nombre = columnas[col_i] if columnas and col_i < len(columnas) else ""
    align = (
        _align_columna_ws(nombre, col_i, columnas)
        if columnas
        else ("left" if col_i < 4 else "right")
    )
    if es_header:
        est = _WS_ESTILOS[_categoria_columna_ws(nombre)]
        bg = est.th_bg if col_i % 2 == 0 else est.th_bg_alt
        fg = est.th_fg
        peso = "font-weight:700;"
        sticky = ""
        if left_fijo is not None:
            z = 55 + col_i
            sombra = (
                "box-shadow:6px 0 12px rgba(0,0,0,0.45);"
                if col_i == WS_COLUMNAS_FIJAS - 1
                else ""
            )
            top = "top:0;" if cabecera_sticky_vertical else ""
            sticky = f"position:sticky;{top}left:{left_fijo}px;z-index:{z};{sombra}"
        elif col_i < WS_COLUMNAS_FIJAS and cabecera_sticky_vertical:
            sticky = "position:sticky;top:0;z-index:35;"
        wrap = "white-space:normal;word-break:break-word;overflow:visible;"
    else:
        bg, fg = PALETA_FILAS_ALTERNADAS[fila_i % len(PALETA_FILAS_ALTERNADAS)]
        peso = "font-weight:500;"
        if color_texto:
            fg = color_texto
            peso = "font-weight:700;"
        elif resaltar_negativo:
            fg = "#ff3333"
            peso = "font-weight:700;"
        sticky = ""
        if left_fijo is not None:
            z = 20 + col_i
            sombra = (
                "box-shadow:6px 0 12px rgba(0,0,0,0.45);"
                if col_i == WS_COLUMNAS_FIJAS - 1
                else ""
            )
            sticky = f"position:sticky;left:{left_fijo}px;z-index:{z};{sombra}"
        wrap = (
            "white-space:normal;word-break:break-word;overflow:visible;"
            if col_i < 4
            else "white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"
        )
    nums = "font-variant-numeric:tabular-nums;" if align != "left" else ""
    return f"{base}{peso}color:{fg};background:{bg};text-align:{align};{wrap}{sticky}{nums}"


def _estilo_celda_scorecard(
    col_i: int,
    fila_i: int,
    n_cols: int,
    n_filas: int,
    font_px: int,
    *,
    es_header: bool,
    columnas: list[str] | None,
    hide_index: bool,
    anchos: list[int] | None = None,
) -> str:
    pad = _padding_celda(font_px)
    alto = max(38, int(font_px * 1.48))
    base = (
        f"font-size:{font_px}px;line-height:1.35;vertical-align:middle;"
        f"padding:{pad};min-height:{alto}px;height:{alto}px;"
        f"box-sizing:border-box;border-bottom:1px solid #334155;"
    )
    meta_cols, tail_cols = _meta_scorecard(columnas, hide_index)
    es_tabla_resumen = columnas is not None and not hide_index
    es_total = (
        n_filas > 0
        and fila_i >= n_filas - 1
        and not es_tabla_resumen
    )
    es_meta = col_i < meta_cols
    es_cola = tail_cols > 0 and col_i >= n_cols - tail_cols
    usar_color_fila = (
        columnas is not None
        and hide_index
        and "Drivers" in columnas
        and not es_header
    )
    usar_banda_resumen = es_tabla_resumen and not es_header and not es_cola

    if es_header:
        if es_meta:
            bg, fg = SCORECARD_CELDA_META
        elif es_cola:
            bg, fg = SCORECARD_CELDA_TOTAL
        else:
            cat_i = col_i - meta_cols
            bg, fg = SCORECARD_PALETA_COLUMNAS[cat_i % len(SCORECARD_PALETA_COLUMNAS)]
        peso = "font-weight:700;"
    elif es_total or es_cola:
        bg, fg = SCORECARD_CELDA_TOTAL
        peso = "font-weight:700;"
    elif usar_banda_resumen:
        bg, fg = PALETA_FILAS_RESUMEN_KPI[fila_i % len(PALETA_FILAS_RESUMEN_KPI)]
        peso = "font-weight:600;" if es_meta else "font-weight:500;"
    elif usar_color_fila:
        bg, fg = PALETA_FILAS_SCORECARD[fila_i % len(PALETA_FILAS_SCORECARD)]
        peso = "font-weight:600;" if es_meta else "font-weight:500;"
    elif es_meta:
        if col_i == 0:
            bg, fg = SCORECARD_CELDA_META
        else:
            bg, fg = SCORECARD_CELDA_DRIVER
        peso = "font-weight:500;"
    else:
        cat_i = col_i - meta_cols
        bg, fg = SCORECARD_PALETA_COLUMNAS[cat_i % len(SCORECARD_PALETA_COLUMNAS)]
        if fila_i % 2 == 1:
            bg = _oscurecer_hex(bg, 0.12)
        peso = ""

    align = "left" if col_i < meta_cols else "right"
    if col_i == 0:
        wrap = "white-space:normal;word-break:break-word;overflow:visible;"
    else:
        wrap = "white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"
    sticky = _sticky_scorecard(col_i, meta_cols, anchos, es_header=es_header)
    return f"{base}{peso}color:{fg};background:{bg};text-align:{align};{wrap}{sticky}"


def _oscurecer_hex(hex_color: str, factor: float) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r = max(0, int(r * (1 - factor)))
    g = max(0, int(g * (1 - factor)))
    b = max(0, int(b * (1 - factor)))
    return f"#{r:02x}{g:02x}{b:02x}"


def _colgroup_html(
    layout: LayoutTabla,
    n_cols: int,
    hide_index: bool,
    *,
    columnas: list[str] | None = None,
    font_px: int = TABLA_FONT_SIZE_DEFAULT,
    anchos_manual: dict[str, int] | None = None,
) -> str:
    if layout == "ancha" and columnas:
        anchos = _anchos_columnas_ws(columnas, font_px, anchos_manual=anchos_manual)
        partes = [
            f'<col style="width:{w}px;min-width:{w}px">' for w in anchos
        ]
        return "<colgroup>" + "".join(partes) + "</colgroup>"
    if layout == "alternada" and columnas:
        anchos = _anchos_columnas_ws(columnas, font_px, anchos_manual=anchos_manual)
        partes = [
            f'<col style="width:{w}px;min-width:{w}px">' for w in anchos
        ]
        return "<colgroup>" + "".join(partes) + "</colgroup>"
    if layout == "parametros":
        return '<colgroup><col style="width:64%"><col style="width:36%"></colgroup>'
    if layout == "scorecard" and columnas:
        anchos = _anchos_scorecard_px(columnas, font_px)
        partes = [
            f'<col style="width:{w}px;min-width:{w}px">' for w in anchos
        ]
        return "<colgroup>" + "".join(partes) + "</colgroup>"
    if layout == "scorecard" and n_cols >= 2:
        partes: list[str] = []
        if hide_index and n_cols >= 3:
            pct_name, pct_drv = 30, 14
            resto = n_cols - 2
            pct_num = (100 - pct_name - pct_drv) / resto
            partes = [
                f'<col style="width:{pct_name}%">',
                f'<col style="width:{pct_drv}%">',
            ]
            partes.extend([f'<col style="width:{pct_num:.3f}%">' for _ in range(resto)])
        else:
            pct_first = 34
            resto = n_cols - 1
            pct_num = (100 - pct_first) / resto
            partes = [f'<col style="width:{pct_first}%">']
            partes.extend([f'<col style="width:{pct_num:.3f}%">' for _ in range(resto)])
        return "<colgroup>" + "".join(partes) + "</colgroup>"
    return ""


def _aplicar_font_inline_html(
    html: str,
    font_px: int,
    layout: LayoutTabla,
    *,
    hide_index: bool = True,
    origen: OrigenDato = "neutro",
    ancho_tabla_px: int | None = None,
    columnas: list[str] | None = None,
    anchos_manual: dict[str, int] | None = None,
    evai_neg_filas: frozenset[int] | None = None,
    colores_columna: dict[str, str] | None = None,
    cabecera_sticky_vertical: bool = True,
) -> str:
    usar_ws = layout == "ancha" and columnas
    usar_alternada = layout == "alternada" and columnas
    pad = _padding_celda(font_px)

    if not usar_ws and not usar_alternada:
        if origen == "calculado":
            color_txt, color_num = COLOR_SISTEMA_TEXTO, COLOR_SISTEMA_VALOR
            bg_td = COLOR_SISTEMA_FONDO
            bg_th = "#3d1a1f"
        elif origen == "editable":
            color_txt, color_num = COLOR_EDITABLE_TEXTO, COLOR_EDITABLE_VALOR
            bg_td = "#0f1f14"
            bg_th = "#1a2e22"
        else:
            color_txt = color_num = "#fafafa"
            bg_td = "#0e1117"
            bg_th = "#262730"

        base = (
            f"font-size:{font_px}px;line-height:{TABLA_LINE_HEIGHT};vertical-align:middle;"
            f"padding:{pad};"
        )
        estilo_th_txt = (
            f"{base}font-weight:600;color:{color_txt};background:{bg_th};"
            f"border-bottom:1px solid #3d4149;text-align:left;white-space:nowrap;"
        )
        estilo_th_num = estilo_th_txt.replace("text-align:left", "text-align:right")
        estilo_td_txt = (
            f"{base}color:{color_txt};background:{bg_td};"
            f"border-bottom:1px solid #2d3142;text-align:left;white-space:nowrap;"
        )
        estilo_td_num = estilo_td_txt.replace(f"color:{color_txt}", f"color:{color_num}").replace(
            "text-align:left", "text-align:right"
        )

    n_th = len(re.findall(r"<th\b", html, flags=re.I))
    n_cols = len(columnas) if columnas else max(n_th, 1)
    n_txt = _columnas_texto(layout, hide_index)
    n_td = len(re.findall(r"<td\b", html, flags=re.I))
    es_scorecard_con_indice = layout == "scorecard" and bool(columnas) and not hide_index
    if es_scorecard_con_indice:
        html = _preparar_html_scorecard_resumen(html)
    n_cols_datos = n_cols - 1 if es_scorecard_con_indice else n_cols
    if layout == "scorecard" and n_cols_datos:
        n_filas_scorecard = n_td // n_cols_datos
    else:
        n_filas_scorecard = (n_td // n_cols) if n_cols else 0
    idx_th = 0
    idx_td = 0
    anchos_ws = (
        _anchos_columnas_ws(columnas, font_px, anchos_manual=anchos_manual)
        if (usar_ws or usar_alternada) and columnas
        else []
    )
    anchos_sc = (
        _anchos_scorecard_px(columnas, font_px)
        if layout == "scorecard" and columnas
        else []
    )

    def _nombre_col(idx: int) -> str:
        if columnas and idx < len(columnas):
            return columnas[idx]
        return ""

    def _left_fijo(col_i: int) -> int | None:
        if col_i < WS_COLUMNAS_FIJAS and anchos_ws:
            return _left_columna_fija(anchos_ws, col_i)
        return None

    def repl_th(m: re.Match[str]) -> str:
        nonlocal idx_th
        es_header_celda = idx_th < n_cols
        if es_scorecard_con_indice and not es_header_celda:
            col_i = 0
            fila_i = idx_th - n_cols
            es_header = False
        else:
            col_i = idx_th % n_cols
            fila_i = 0
            es_header = es_header_celda
        if usar_alternada:
            estilo = _estilo_celda_alternada(
                col_i,
                fila_i if not es_header else 0,
                font_px,
                es_header=es_header,
                columnas=columnas,
                left_fijo=_left_fijo(col_i),
                cabecera_sticky_vertical=cabecera_sticky_vertical,
            )
        elif usar_ws:
            estilo = _estilo_columna_ws(
                _nombre_col(col_i),
                es_header=es_header,
                font_px=font_px,
                col_idx=col_i,
                left_fijo=_left_fijo(col_i),
                columnas=columnas,
            )
        else:
            estilo = estilo_th_txt if col_i < n_txt else estilo_th_num
        if layout == "scorecard":
            estilo = _estilo_celda_scorecard(
                col_i,
                fila_i,
                n_cols,
                n_filas_scorecard,
                font_px,
                es_header=es_header,
                columnas=columnas,
                hide_index=hide_index,
                anchos=anchos_sc or None,
            )
        idx_th += 1
        return _merge_style_attr(m.group(0), estilo)

    def repl_td(m: re.Match[str]) -> str:
        nonlocal idx_td
        if es_scorecard_con_indice:
            col_i = 1 + (idx_td % n_cols_datos)
            fila_i = idx_td // n_cols_datos
        else:
            col_i = idx_td % n_cols
            fila_i = idx_td // n_cols
        if usar_alternada:
            nombre_col = columnas[col_i] if columnas and col_i < len(columnas) else ""
            resaltar = (
                nombre_col == "EVAI"
                and evai_neg_filas is not None
                and fila_i in evai_neg_filas
            )
            color_col = (
                colores_columna.get(nombre_col)
                if colores_columna and nombre_col
                else None
            )
            estilo = _estilo_celda_alternada(
                col_i,
                fila_i,
                font_px,
                es_header=False,
                columnas=columnas,
                left_fijo=_left_fijo(col_i),
                resaltar_negativo=resaltar,
                color_texto=color_col if not resaltar else None,
            )
        elif usar_ws:
            estilo = _estilo_columna_ws(
                _nombre_col(col_i),
                es_header=False,
                font_px=font_px,
                fila_idx=fila_i,
                col_idx=col_i,
                left_fijo=_left_fijo(col_i),
                columnas=columnas,
            )
        else:
            estilo = estilo_td_txt if col_i < n_txt else estilo_td_num
        if layout == "scorecard":
            estilo = _estilo_celda_scorecard(
                col_i,
                fila_i,
                n_cols,
                n_filas_scorecard,
                font_px,
                es_header=False,
                columnas=columnas,
                hide_index=hide_index,
                anchos=anchos_sc or None,
            )
        idx_td += 1
        return _merge_style_attr(m.group(0), estilo)

    # \b evita que <thead> se cuente como <th> (desplazaba el sticky una columna).
    html = re.sub(r"<th\b[^>]*>", repl_th, html, flags=re.I)
    html = re.sub(r"<td\b[^>]*>", repl_td, html, flags=re.I)

    if layout == "parametros":
        ancho_tabla = ancho_tabla_px if ancho_tabla_px else min(900, max(540, font_px * 28))
        table_style = (
            f"border-collapse:collapse;width:{ancho_tabla}px;max-width:100%;"
            "table-layout:fixed;"
        )
    elif layout == "scorecard":
        if columnas:
            ancho_total = sum(_anchos_scorecard_px(columnas, font_px))
        else:
            ancho_total = max(960, n_cols * 108)
        table_style = (
            "border-collapse:separate;border-spacing:0;"
            f"table-layout:fixed;width:{ancho_total}px;min-width:100%;"
        )
    elif usar_alternada and columnas:
        ancho_total = sum(anchos_ws)
        table_style = (
            "border-collapse:separate;border-spacing:0;"
            f"table-layout:fixed;width:{ancho_total}px;"
            "font-family:Consolas,'IBM Plex Mono','Segoe UI',system-ui,sans-serif;"
        )
    elif usar_ws and columnas:
        ancho_total = sum(anchos_ws)
        table_style = (
            "border-collapse:separate;border-spacing:0;"
            f"table-layout:fixed;width:{ancho_total}px;"
            "font-family:Consolas,'IBM Plex Mono','Segoe UI',system-ui,sans-serif;"
        )
    else:
        table_style = "border-collapse:collapse;width:max-content;min-width:100%;table-layout:fixed;"

    colgroup = _colgroup_html(
        layout,
        n_th,
        hide_index,
        columnas=columnas,
        font_px=font_px,
        anchos_manual=anchos_manual,
    )
    if layout == "scorecard":
        clase = ' class="inv-tabla-scorecard"'
    elif usar_alternada:
        clase = ' class="inv-tabla-ws inv-tabla-alternada"'
    elif usar_ws:
        clase = ' class="inv-tabla-ws"'
    else:
        clase = ""
    return re.sub(
        r"<table([^>]*)>",
        f"<table\\1{clase} style=\"{table_style}\">{colgroup}",
        html,
        count=1,
        flags=re.I,
    )


def altura_tabla_px(n_filas: int, font_px: int, min_h: int = 280, max_h: int = 780) -> int:
    alto_fila = max(30, int(font_px * 1.45))
    return int(min(max_h, max(min_h, 40 + n_filas * alto_fila)))


def altura_tabla_con_encabezado_px(
    n_filas: int,
    font_px: int,
    *,
    min_h: int = 280,
    max_h: int = 780,
) -> int:
    """Altura del contenedor incluyendo fila de encabezado (evita recorte de títulos)."""
    alto_hdr = max(52, int(font_px * 2.0))
    alto_fila = max(30, int(font_px * 1.45))
    return int(min(max_h, max(min_h, alto_hdr + 14 + n_filas * alto_fila)))


def altura_tabla_scorecard_completa_px(
    n_filas: int,
    font_px: int,
    *,
    con_encabezado: bool = True,
) -> int:
    """Altura exacta para tablas scorecard sin scroll vertical (p. ej. resumen KPI)."""
    alto_fila = max(38, int(font_px * 1.48))
    filas_visibles = n_filas + (1 if con_encabezado else 0)
    return int(10 + filas_visibles * alto_fila)


def _max_ancho_contenedor(
    layout: LayoutTabla,
    font_px: int,
    *,
    ancho_tabla_px: int | None = None,
) -> str:
    if layout == "parametros":
        w = ancho_tabla_px if ancho_tabla_px else min(820, max(520, font_px * 26))
        return f"max-width:{w}px;width:{w}px;"
    return "max-width:100%;width:100%;"


def _anchos_manual_key(anchos_manual: dict[str, int] | None) -> tuple[tuple[str, int], ...]:
    if not anchos_manual:
        return ()
    return tuple(sorted(anchos_manual.items()))


@st.cache_data(show_spinner=False)
def _html_tabla_wall_street_cached(
    df: pd.DataFrame,
    format_items: tuple[tuple[str, str], ...],
    font_px: int,
    hide_index: bool,
    origen: str,
    ancho_tabla_px: int | None,
    anchos_key: tuple[tuple[str, int], ...],
) -> str:
    """Genera HTML estilo WS; se invalida al cambiar datos o sliders de ancho."""
    fmt = dict(format_items)
    styler = df.style.format(fmt)
    if hide_index:
        styler = styler.hide(axis="index")
    columnas = list(df.columns)
    html_raw = _extraer_tabla_html(styler.to_html())
    anchos_manual = dict(anchos_key) if anchos_key else None
    return _aplicar_font_inline_html(
        html_raw,
        font_px,
        "ancha",
        hide_index=hide_index,
        origen=origen,  # type: ignore[arg-type]
        ancho_tabla_px=ancho_tabla_px,
        columnas=columnas,
        anchos_manual=anchos_manual,
    )


def mostrar_tabla_html(
    styler: Any,
    font_px: int,
    *,
    n_filas: int | None = None,
    altura_px: int | None = None,
    hide_index: bool = True,
    layout: LayoutTabla = "auto",
    origen: OrigenDato = "neutro",
    ancho_tabla_px: int | None = None,
    anchos_manual: dict[str, int] | None = None,
    format_items: tuple[tuple[str, str], ...] | None = None,
    mostrar_completa: bool = False,
    evai_neg_filas: frozenset[int] | None = None,
    colores_columna: dict[str, str] | None = None,
    cabecera_sticky_vertical: bool = True,
) -> None:
    """Tabla HTML con letra grande y columnas juntas (controlada por el slider)."""
    if hide_index and hasattr(styler, "hide"):
        styler = styler.hide(axis="index")
    try:
        df = styler.data
    except AttributeError:
        df = styler
    if layout == "auto" and isinstance(df, pd.DataFrame):
        layout = _detectar_layout(df)

    columnas = None
    if isinstance(df, pd.DataFrame):
        if hide_index:
            columnas = list(df.columns)
        else:
            idx_name = df.index.name or "KPI"
            columnas = [str(idx_name), *list(df.columns)]
    usar_cache_ws = (
        layout == "ancha"
        and isinstance(df, pd.DataFrame)
        and len(df) >= 80
        and format_items is not None
    )
    if usar_cache_ws:
        html_tabla = _html_tabla_wall_street_cached(
            df,
            format_items,
            font_px,
            hide_index,
            origen,
            ancho_tabla_px,
            _anchos_manual_key(anchos_manual),
        )
    else:
        html_tabla = _aplicar_font_inline_html(
            _extraer_tabla_html(styler.to_html()),
            font_px,
            layout,
            hide_index=hide_index,
            origen=origen,
            ancho_tabla_px=ancho_tabla_px,
            columnas=columnas,
            anchos_manual=anchos_manual,
            evai_neg_filas=evai_neg_filas,
            colores_columna=colores_columna,
            cabecera_sticky_vertical=cabecera_sticky_vertical,
        )
    if n_filas is None and isinstance(df, pd.DataFrame):
        n_filas = len(df)
    elif n_filas is None:
        n_filas = 12
    if mostrar_completa and layout == "scorecard":
        altura_px = altura_tabla_scorecard_completa_px(n_filas, font_px)
    elif altura_px is None:
        altura_px = altura_tabla_px(n_filas, font_px)

    ancho_wrap = _max_ancho_contenedor(layout, font_px, ancho_tabla_px=ancho_tabla_px)
    clase_origen = " inv-tabla-calculado" if origen == "calculado" else ""
    if layout == "ancha" and columnas:
        clase_origen += " inv-tabla-ws-wrap"
        fondo = WS_FONDO_TABLA
        borde = WS_BORDE_TABLA
    elif layout == "alternada" and columnas:
        clase_origen += " inv-tabla-ws-wrap inv-tabla-alternada-wrap"
        if not cabecera_sticky_vertical:
            clase_origen += " inv-tabla-head-flow"
        fondo = WS_FONDO_TABLA
        borde = WS_BORDE_TABLA
    elif layout == "scorecard":
        clase_origen += " inv-tabla-scorecard-wrap"
        if mostrar_completa:
            clase_origen += " inv-tabla-kpi-completa"
        fondo = "#0a0f18"
        borde = "#334155"
    else:
        fondo = "#0e1117"
        borde = "#2d3142"
    if layout == "ancha" and columnas:
        overflow = "overflow-x:scroll;overflow-y:auto;"
    elif layout == "alternada" and columnas:
        overflow = "overflow-x:scroll;overflow-y:auto;"
    elif layout == "scorecard" and mostrar_completa:
        overflow = "overflow-x:scroll;overflow-y:hidden;"
    elif layout == "scorecard":
        overflow = "overflow-x:scroll;overflow-y:auto;"
    else:
        overflow = "overflow:auto;"
    bloque = (
        f'<div class="inv-tabla-scroll{clase_origen}" style="height:{altura_px}px;'
        f"min-height:{altura_px}px;max-height:{altura_px}px;{overflow}{ancho_wrap}"
        f"border:1px solid {borde};border-radius:4px;background:{fondo};"
        f'">{html_tabla}</div>'
    )
    st.markdown(bloque, unsafe_allow_html=True)


def _grupo_css_id(grupo_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", grupo_id)


@dataclass(frozen=True)
class LayoutParametros:
    """Anchos por grupo: col.1 = ancho del atributo más largo del grupo; col.2 = set boxes alineados."""
    w_lab: int
    w_inp: int
    altura_fila: int
    font_px: int
    ancho_col_label_px: int
    ancho_col_input_px: int
    ancho_campo_px: int
    btn_px: int
    ancho_tabla_px: int
    grupo_id: str = ""
    color_texto: str = COLOR_EDITABLE_TEXTO
    color_valor: str = COLOR_EDITABLE_VALOR
    color_fondo_input: str = COLOR_EDITABLE_FONDO_INPUT
    color_borde_input: str = "rgba(74, 222, 128, 0.55)"


def recopilar_nombres_tags(params: dict, tags: list[str]) -> list[str]:
    import parametros as _param

    nombres: list[str] = []
    for tag in tags:
        try:
            df = _param.tag_a_dataframe(params, tag)
            nombres.extend(str(x) for x in df["Parámetro"])
        except (KeyError, ValueError):
            continue
    return nombres


def _ancho_columna_label_px(nombres: list[str], font_px: int) -> int:
    """Ancho col.1 = cabe el atributo más largo del grupo (línea amarilla en boceto)."""
    max_chars = max((len(n) for n in nombres), default=18)
    return int(max_chars * font_px * 0.56) + 28


def _ratios_tabla_parametros(nombres: list[str], font_px: int) -> tuple[int, int]:
    """Reserva espacio fijo para el set box aunque la etiqueta sea muy larga."""
    max_chars = max((len(n) for n in nombres), default=18)
    w_lab = min(max_chars, W_LAB_COLUMN_RATIO_MAX)
    return w_lab, W_INP_COLUMN_RATIO_FIJO


def crear_layout_parametros(
    nombres: list[str],
    font_px: int,
    *,
    grupo_id: str = "",
    medidas_inp: tuple[int, int, int, int] | None = None,
) -> LayoutParametros:
    """Etiquetas por grupo; set box siempre del mismo tamaño que Datos."""
    w_lab, w_inp = _ratios_tabla_parametros(nombres, font_px)
    inp, campo, btn, altura = medidas_inp or medidas_input_estandar(font_px)
    ancho_label = _ancho_columna_label_px(nombres, font_px)
    gap_cols = 8
    ancho_tabla = min(1100, ancho_label + gap_cols + inp)
    col = colores_grupo_parametros(grupo_id)
    return LayoutParametros(
        w_lab=w_lab,
        w_inp=w_inp,
        altura_fila=altura,
        font_px=font_px,
        ancho_col_label_px=ancho_label,
        ancho_col_input_px=inp,
        ancho_campo_px=campo,
        btn_px=btn,
        ancho_tabla_px=ancho_tabla,
        grupo_id=grupo_id,
        color_texto=col.texto,
        color_valor=col.valor,
        color_fondo_input=col.fondo_input,
        color_borde_input=col.borde_input,
    )


def css_bloque_parametros(layout: LayoutParametros) -> str:
    """Grid por grupo: solo cambia ancho de etiquetas; input siempre estándar."""
    h = layout.altura_fila
    inp_h = max(44, h - 8)
    fs = layout.font_px
    g = _grupo_css_id(layout.grupo_id) if layout.grupo_id else "default"
    bloque = (
        f'{_CSS_FILA_PARAM}:has([data-grupo="{g}"])'
    )
    scope_inp = f"{bloque} > [data-testid=\"column\"]:nth-child(2)"
    lab = layout.ancho_col_label_px
    inp = layout.ancho_col_input_px
    pad_inp = _padding_celda(fs)
    setbox = _css_setbox_number_input(
        scope_inp,
        inp_px=inp,
        campo_px=layout.ancho_campo_px,
        btn_px=layout.btn_px,
        altura_px=h,
        font_px=fs,
        pad_inp=pad_inp,
        color_valor=layout.color_valor,
        color_fondo=layout.color_fondo_input,
        color_borde=layout.color_borde_input,
    )
    return f"""
<style>
{bloque} {{
    display: grid !important;
    grid-template-columns: {lab}px {inp}px !important;
    gap: 0 6px !important;
    width: max-content !important;
    max-width: 100% !important;
    align-items: center !important;
    margin: 0 !important;
}}
{bloque} > [data-testid="column"] {{
    flex: unset !important;
    width: auto !important;
    max-width: none !important;
    padding: 0 !important;
}}
{bloque} > [data-testid="column"]:nth-child(1) {{
    grid-column: 1 !important;
    width: {lab}px !important;
    max-width: {lab}px !important;
    min-width: 0 !important;
    overflow: visible !important;
}}
{bloque} > [data-testid="column"]:nth-child(2) {{
    grid-column: 2 !important;
    width: {inp}px !important;
    min-width: {inp}px !important;
    max-width: {inp}px !important;
    flex-shrink: 0 !important;
    padding-left: 0 !important;
    overflow: visible !important;
}}
{setbox}
{scope_inp} [data-testid="stSelectbox"] > div > div {{
    font-size: {fs}px !important;
    min-height: {inp_h}px !important;
    box-sizing: border-box !important;
}}
{bloque} .inv-param-celda-label {{
    font-size: {fs}px !important;
    color: {layout.color_texto} !important;
}}
.inv-param-bloque-tabla.inv-grupo-{g} {{
    max-width: {layout.ancho_tabla_px}px !important;
    width: 100% !important;
}}
.inv-param-bloque-tabla.inv-grupo-{g} > div[data-testid="stHorizontalBlock"]:last-of-type {{
    margin-bottom: 0 !important;
}}
</style>
"""


def _fila_parametro(
    nombre: str,
    layout: LayoutParametros,
    widget_fn,
) -> Any:
    """Col.1 atributo (izq.) | col.2 set box pegado, misma altura (boceto usuario)."""
    c_lab, c_val = st.columns(
        [layout.w_lab, layout.w_inp],
        gap="small",
        vertical_alignment="center",
    )
    h = layout.altura_fila
    g = _grupo_css_id(layout.grupo_id) if layout.grupo_id else "default"
    with c_lab:
        st.markdown(
            f'<div class="inv-param-label inv-param-celda-label inv-g-{g}" '
            f'data-grupo="{g}" '
            f'style="font-size:{layout.font_px}px;color:{layout.color_texto};'
            f'height:{h}px;min-height:{h}px;max-height:{h}px;'
            f'line-height:{TABLA_LINE_HEIGHT};">{nombre}</div>',
            unsafe_allow_html=True,
        )
    with c_val:
        st.markdown(
            f'<span class="inv-g-{g}" data-grupo="{g}" aria-hidden="true" '
            f'style="display:none;width:0;height:0;"></span>',
            unsafe_allow_html=True,
        )
        return widget_fn()


def _fila_driver_asignacion(
    nombre: str,
    widget_fn,
    fila_idx: int,
    font_px: int,
) -> Any:
    """Etiqueta con franja de color y selector debajo (sin grid de parámetros)."""
    borde, texto, fondo = ASIGNACION_LINEA_PALETA[fila_idx % len(ASIGNACION_LINEA_PALETA)]
    nombre_safe = html.escape(str(nombre))
    st.markdown(
        f'<div class="inv-driver-asig-label" style="border-left:4px solid {borde};'
        f"padding:3px 8px;margin:0 0 1px 0;background:{fondo};"
        f"border-radius:3px;font-size:{font_px}px;color:{texto};"
        f'line-height:1.25;font-weight:600;">'
        f"{nombre_safe}</div>",
        unsafe_allow_html=True,
    )
    return widget_fn()


def mapa_colores_driver(opciones: list[str]) -> dict[str, tuple[str, str, str]]:
    """Un color distinto por driver (fondo, texto, borde)."""
    out: dict[str, tuple[str, str, str]] = {}
    for i, nombre in enumerate(opciones):
        out[nombre] = PALETA_DRIVER_ASIGNACION[i % len(PALETA_DRIVER_ASIGNACION)]
    return out


def leyenda_drivers_asignacion(
    opciones: list[str],
    font_px: int | None = None,
) -> None:
    """Chips de colores por driver; títulos en blanco sobre fondo de color."""
    fs = font_px if font_px is not None else ASIGNACION_DRIVERS_FONT_PX
    fs_chip = max(12, int(fs * 0.88))
    mapa = mapa_colores_driver(opciones)
    chips = []
    for nombre in opciones:
        bg, _fg, borde = mapa[nombre]
        chips.append(
            f'<span style="display:inline-block;margin:0 10px 6px 0;padding:3px 10px;'
            f"border-radius:4px;border-left:4px solid {borde};"
            f"background:{bg};color:#ffffff;font-size:{fs_chip}px;font-weight:600;"
            f'">{html.escape(nombre)}</span>'
        )
    st.markdown(
        f'<div style="margin:6px 0 10px 0;"><span style="color:#ffffff;font-size:{fs_chip}px;">'
        f"Drivers · </span>{''.join(chips)}</div>",
        unsafe_allow_html=True,
    )


def css_selectores_asignacion_colores(
    reglas: list[tuple[str, str, str, str]],
    font_px: int | None = None,
) -> str:
    """CSS por clave ``st-key-inv_asig_drv_*``: fondo, texto y borde del selectbox."""
    if not reglas:
        return ""
    fs = font_px if font_px is not None else ASIGNACION_DRIVERS_FONT_PX
    h = max(30, int(fs * 1.25))
    bloques: list[str] = []
    for key, fondo, texto, borde in reglas:
        sel = f"body.inv-page-asignacion-drivers .st-key-{key}"
        bloques.append(
            f"{sel} [data-testid='stSelectbox'] {{ margin: 0 !important; }}"
            f"{sel} [data-testid='stSelectbox'] > div > div {{"
            f"min-height: {h}px !important; max-height: {h}px !important;"
            f"font-size: {fs}px !important; font-weight: 600 !important;"
            f"background: {fondo} !important; color: {texto} !important;"
            f"border: 2px solid {borde} !important; border-radius: 4px !important;"
            f"}}"
            f"{sel} [data-testid='stSelectbox'] span {{"
            f"color: {texto} !important; font-size: {fs}px !important;"
            f"}}"
        )
    return f"<style>{''.join(bloques)}</style>"


def css_asignacion_drivers_scroll(font_px: int | None = None) -> str:
    """Contenedor con un solo scroll vertical."""
    fs = font_px if font_px is not None else ASIGNACION_DRIVERS_FONT_PX
    fs_hdr = max(13, int(fs * 0.94))
    fs_est = max(11, int(fs * 0.82))
    return f"""
<style>
body.inv-page-asignacion-drivers .inv-asig-scroll {{
    max-height: 720px;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 4px 10px 4px 4px;
    border: 1px solid #334155;
    border-radius: 6px;
    background: #0a0f18;
}}
body.inv-page-asignacion-drivers .inv-asig-scroll [data-testid="stHorizontalBlock"] {{
    align-items: stretch !important;
    margin-bottom: 0.12rem !important;
    gap: 0.35rem !important;
}}
body.inv-page-asignacion-drivers .inv-asig-scroll-hdr {{
    color: #ffffff !important;
    font-weight: 600 !important;
    font-size: {fs_hdr}px !important;
}}
body.inv-page-asignacion-drivers .inv-asig-cuenta-label {{
    font-weight: 600 !important;
    word-break: break-word !important;
    line-height: 1.25 !important;
}}
body.inv-page-asignacion-drivers .inv-asig-estado {{
    font-size: {fs_est}px !important;
    line-height: 1.2 !important;
    padding-top: 6px !important;
    font-weight: 600 !important;
}}
</style>
<script>
document.body.classList.add("inv-page-asignacion-drivers");
</script>
"""


def css_asignacion_drivers_editor(opciones: list[str] | None = None) -> str:
    """Compatibilidad: delega en scroll con colores."""
    del opciones
    return css_asignacion_drivers_scroll()


def css_asignacion_drivers_bloque(font_px: int | None = None) -> str:
    """Legacy: lista de selectbox (ya no usada en asignación unificada)."""
    return css_asignacion_drivers_editor()


def selectores_driver_lista(
    nombres: list[str],
    opciones: list[str],
    drivers_actuales: list[str],
    clave_tabla: str,
    font_px: int | None = None,
) -> list[str]:
    """Lista vertical compacta: cuenta en color + driver en blanco."""
    fs = font_px if font_px is not None else ASIGNACION_DRIVERS_FONT_PX
    seleccionados: list[str] = []
    for i, nombre in enumerate(nombres):
        prev = drivers_actuales[i] if i < len(drivers_actuales) else opciones[0]
        ix = opciones.index(prev) if prev in opciones else 0

        def _sel(pi=i, idx_op=ix):
            return st.selectbox(
                "Driver",
                opciones,
                index=idx_op,
                key=f"{clave_tabla}_drv_{pi}",
                label_visibility="collapsed",
            )

        seleccionados.append(_fila_driver_asignacion(nombre, _sel, i, fs))
    return seleccionados


def selectores_driver_escuadron(
    nombres: list[str],
    opciones: list[str],
    drivers_actuales: list[str],
    clave_tabla: str,
    font_px: int,
) -> list[str]:
    """Tarjetas en escuadrón (2 columnas) para asignar driver por línea de costo."""
    st.markdown(
        f'<p style="font-size:{max(15, font_px - 2)}px;color:#94a3b8;margin:0 0 8px 0;">'
        "**Asignación de drivers** — una tarjeta por línea; los montos se recalculan al cambiar.</p>",
        unsafe_allow_html=True,
    )
    seleccionados: list[str] = []
    for i in range(0, len(nombres), 2):
        cols = st.columns(2, gap="medium")
        for j in range(2):
            idx = i + j
            if idx >= len(nombres):
                break
            nombre = nombres[idx]
            prev = drivers_actuales[idx] if idx < len(drivers_actuales) else opciones[0]
            ix = opciones.index(prev) if prev in opciones else 0
            _bg, acento = SCORECARD_DRIVER_CARD_COLORS[idx % len(SCORECARD_DRIVER_CARD_COLORS)]
            with cols[j]:
                with st.container(border=True):
                    st.markdown(
                        f'<div style="border-left:4px solid {acento};padding-left:10px;margin-bottom:6px;">'
                        f'<div style="font-size:{max(12, font_px - 8)}px;color:#94a3b8;">'
                        f"Línea {idx + 1}</div>"
                        f'<div style="font-size:{font_px}px;font-weight:600;color:#f8fafc;'
                        f'line-height:1.35;margin-top:2px;">{nombre}</div></div>',
                        unsafe_allow_html=True,
                    )
                    drv = st.selectbox(
                        "Driver",
                        opciones,
                        index=ix,
                        key=f"{clave_tabla}_esc_{idx}",
                        label_visibility="collapsed",
                    )
                    seleccionados.append(drv)
    return seleccionados


def selectores_driver_scorecard(
    nombres: list[str],
    opciones: list[str],
    drivers_actuales: list[str],
    clave_tabla: str,
    font_px: int,
    *,
    layout: LayoutParametros | None = None,
) -> list[str]:
    """Driver por línea — lista simple con franja de color."""
    del layout
    return selectores_driver_lista(
        nombres, opciones, drivers_actuales, clave_tabla, font_px
    )


def editor_parametros_compacto(
    base: pd.DataFrame,
    tag: str,
    font_px: int,
    *,
    es_porcentaje: bool = False,
    layout: LayoutParametros | None = None,
) -> pd.DataFrame:
    """Una fila por parámetro; layout compartido del tab (sin escalera ni desfase)."""
    nombres = [str(x) for x in base["Parámetro"]]
    if layout is None:
        layout = crear_layout_parametros(nombres, font_px, grupo_id=tag)
    elif not layout.grupo_id:
        layout = replace(layout, grupo_id=tag)

    g_tabla = _grupo_css_id(tag)
    st.markdown(css_bloque_parametros(layout), unsafe_allow_html=True)
    st.markdown(
        f'<div class="inv-param-wrap inv-param-editable inv-param-bloque-tabla inv-grupo-{g_tabla}"></div>',
        unsafe_allow_html=True,
    )
    import parametros as _param

    valores: list[float] = []

    for idx in range(len(base)):
        nombre = str(base.iloc[idx]["Parámetro"])
        actual = float(base.iloc[idx]["Valor"])
        _param.valor_inicial_widget(tag, idx, actual)

        def _input(
            pi=idx,
            nom=nombre,
            pct=es_porcentaje,
            ly=layout,
            dec=parametro_acepta_decimales(tag, nombre),
        ):
            key = _param.clave_widget_parametro(tag, pi)
            if pct:
                return st.number_input(
                    nom,
                    min_value=0.0,
                    max_value=100.0,
                    step=0.01,
                    format="%.2f",
                    key=key,
                    label_visibility="collapsed",
                )
            if dec:
                return st.number_input(
                    nom,
                    min_value=0.0,
                    step=0.01,
                    format="%.2f",
                    key=key,
                    label_visibility="collapsed",
                )
            return st.number_input(
                nom,
                min_value=0.0,
                step=1.0,
                format="%.0f",
                key=key,
                label_visibility="collapsed",
            )

        valores.append(float(_fila_parametro(nombre, layout, _input)))

    salida = base.copy()
    salida["Valor"] = valores
    return salida


def clave_widget_calculado_lectura(tag: str, indice: int) -> str:
    return f"inv_calc_lectura_{tag}_{indice}"


def editor_parametros_solo_lectura(
    base: pd.DataFrame,
    tag: str,
    font_px: int,
    *,
    layout: LayoutParametros | None = None,
    es_porcentaje: bool = False,
) -> None:
    """Set box (+/−) deshabilitado: mismo aspecto que editable, valor fijo desde Excel."""
    nombres = [str(x) for x in base["Parámetro"]]
    if layout is None:
        medidas = medidas_input_estandar(font_px)
        layout = crear_layout_parametros(nombres, font_px, grupo_id=tag, medidas_inp=medidas)
    elif not layout.grupo_id:
        layout = replace(layout, grupo_id=tag)

    g_tabla = _grupo_css_id(tag)
    st.markdown(css_bloque_parametros(layout), unsafe_allow_html=True)
    st.markdown(
        f'<div class="inv-param-wrap inv-param-calculado inv-param-bloque-tabla '
        f'inv-grupo-{g_tabla}"></div>',
        unsafe_allow_html=True,
    )

    for idx in range(len(base)):
        nombre = str(base.iloc[idx]["Parámetro"])
        actual = float(base.iloc[idx]["Valor"])
        key = clave_widget_calculado_lectura(tag, idx)
        st.session_state[key] = actual
        dec = parametro_acepta_decimales(tag, nombre)

        def _input(pi=idx, nom=nombre, pct=es_porcentaje, con_dec=dec):
            k = clave_widget_calculado_lectura(tag, pi)
            if pct:
                return st.number_input(
                    nom,
                    min_value=0.0,
                    max_value=100.0,
                    step=0.01,
                    format="%.2f",
                    key=k,
                    label_visibility="collapsed",
                    disabled=True,
                )
            if con_dec:
                return st.number_input(
                    nom,
                    min_value=0.0,
                    step=0.01,
                    format="%.2f",
                    key=k,
                    label_visibility="collapsed",
                    disabled=True,
                )
            return st.number_input(
                nom,
                min_value=0.0,
                step=1.0,
                format="%.0f",
                key=k,
                label_visibility="collapsed",
                disabled=True,
            )

        _fila_parametro(nombre, layout, _input)


def aplicar_estilo_pandas(styler: Any, font_px: int) -> Any:
    return styler
