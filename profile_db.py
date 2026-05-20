import html
import os
from typing import Optional

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

# 1. CONFIGURACIÓN DE PÁGINA Y ESTILO DARK
st.set_page_config(page_title="Business Intelligence Dashboard", layout="wide")

# Referencia visual Full HD 1920×1080 (Python no lee el viewport real sin JS).
# Opcional: LRI_VIEWPORT_H / LRI_VIEWPORT_W para otros monitores.
REF_VIEWPORT_W = int(os.environ.get("LRI_VIEWPORT_W", "1920"))
REF_VIEWPORT_H = int(os.environ.get("LRI_VIEWPORT_H", "1080"))
ARCHIVO_EXCEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "archivo2.xlsx")
# Espacio vertical ocupado fuera de la fila tabla+gráfico (cabecera Streamlit, título, KPIs, captions).
RESERVA_VERTICAL_REF = 320
# Alto útil de la fila principal en la referencia 1080p (ajustar si cambia mucho el UI).
USABLE_ROW_H_REF = max(520, REF_VIEWPORT_H - RESERVA_VERTICAL_REF)
# Subheader "Visualización" + hueco (la figura debe caber en el resto del panel 1080p).
CHART_HEADROOM_PX = 58
# Modo cod_producto: más reserva vertical para no salirse de 1080p (título + colorbar + Streamlit).
CHART_HEADROOM_COD_PX = 92
# Ancho máximo del lienzo Plotly (px) con miles de SKUs — scroll horizontal dentro del panel.
LIENZO_MAX_ANCHO_COD_PX = 120000


def _norm_col_ident(nombre: str) -> str:
    """Nombre de columna normalizado para coincidencias (ignora espacio, _, /, -, .)."""
    return (
        str(nombre)
        .lower()
        .replace(" ", "")
        .replace("_", "")
        .replace("/", "")
        .replace("-", "")
        .replace(".", "")
    )


def es_eje_cod_producto(nombre_columna: str) -> bool:
    """True si el eje es código de producto (reglas distintas a categoría / subcategoría)."""
    c = _norm_col_ident(nombre_columna)
    if "cod" in c and "prod" in c:
        return True
    if c == "sku" or c.startswith("sku"):
        return True
    return False


def es_metrica_promedio_bultos_desp_mes(nombre_columna: str) -> bool:
    """
    Métrica típica tipo 'promedio_bultos_desp/mes' (con barra en el nombre de Excel).
    Sirve para títulos/leyendas; el modo gráfico denso sigue gobernado por el eje código (eje X).
    """
    c = _norm_col_ident(nombre_columna)
    return "promedio" in c and "bulto" in c and "desp" in c and "mes" in c


def _titulo_plotly_con_barra(texto: str) -> str:
    """Parte nombres con '/' en líneas (Plotly/HTML) y escapa cada trozo por seguridad."""
    return "<br>".join(html.escape(p) for p in str(texto).split("/"))


# CSS para crear las tarjetas oscuras y mejorar la tipografía
st.markdown(
    f"""
    <style>
    :root {{
        --lri-ref-w: {REF_VIEWPORT_W}px;
        --lri-ref-h: {REF_VIEWPORT_H}px;
        --lri-row-min-h: min({USABLE_ROW_H_REF}px, calc(100dvh - 18rem), calc(100vh - 18rem));
    }}
    .stApp {{ background-color: #0e1117; color: white; }}
    .kpi-card {{
        background-color: #1e2130;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #2d3142;
        text-align: center;
        transition: transform 0.3s;
    }}
    .kpi-card:hover {{ transform: translateY(-5px); border-color: #00d4ff; }}
    .kpi-title {{ font-size: 14px; color: #a1a1aa; text-transform: uppercase; margin-bottom: 10px; }}
    .kpi-value {{ font-size: 28px; font-weight: bold; color: #ffffff; }}
    /* Contenido acotado al ancho Full HD para que proporciones tabla/gráfico coincidan con 1920. */
    .block-container {{
        padding-top: 0.75rem !important;
        padding-bottom: 0.5rem !important;
        max-width: min(100%, var(--lri-ref-w)) !important;
        margin-left: auto !important;
        margin-right: auto !important;
    }}
    /* Fila tabla + gráfico: alinear arriba para que una tabla muy alta no estire el gráfico fuera del panel 1080p. */
    section.main [data-testid="stHorizontalBlock"]:has(.lri-tabla-col) {{
        align-items: flex-start !important;
        min-height: var(--lri-row-min-h) !important;
        gap: 0.75rem !important;
    }}
    /* Tabla: puede crecer con muchos ítems (scroll interno o página); sin tope rígido al alto del gráfico. */
    section.main [data-testid="stHorizontalBlock"]:has(.lri-tabla-col) > [data-testid="column"]:has(.lri-tabla-col) {{
        max-height: none !important;
        overflow: visible !important;
    }}
    section.main [data-testid="stHorizontalBlock"]:has(.lri-tabla-col) > [data-testid="column"] {{
        display: flex !important;
        flex-direction: column !important;
        min-height: var(--lri-row-min-h) !important;
    }}
    section.main [data-testid="stHorizontalBlock"]:has(.lri-tabla-col) > [data-testid="column"] > div {{
        flex: 1 1 auto !important;
        min-height: 0 !important;
        height: 100% !important;
        display: flex !important;
        flex-direction: column !important;
    }}
    .lri-tabla-col {{
        box-sizing: border-box !important;
        flex: 0 1 auto !important;
        min-height: var(--lri-row-min-h) !important;
        height: auto !important;
        max-height: none !important;
        display: flex !important;
        flex-direction: column !important;
        border: 1px solid #2d3142;
        border-radius: 10px;
        background: #131722;
        overflow: hidden !important;
    }}
    .lri-tabla-title {{
        flex: 0 0 auto;
        font-size: 1.35rem;
        font-weight: 600;
        color: #f8fafc;
        padding: 0.65rem 1rem 0.55rem;
        border-bottom: 1px solid #2d3142;
        background: #161b26;
        line-height: 1.25;
    }}
    .lri-tabla-scroll {{
        flex: 1 1 auto;
        overflow: auto;
        overflow-x: auto;
        min-height: 0;
        -webkit-overflow-scrolling: touch;
    }}
    /* Tabla: el contenedor de markdown puede crecer con muchas filas. */
    section.main [data-testid="stHorizontalBlock"]:has(.lri-tabla-col) > [data-testid="column"]:has(.lri-tabla-col) [data-testid="stMarkdownContainer"],
    section.main [data-testid="stHorizontalBlock"]:has(.lri-tabla-col) > [data-testid="column"]:has(.lri-tabla-col) div.stMarkdown {{
        min-height: var(--lri-row-min-h) !important;
        height: auto !important;
        max-height: none !important;
        overflow: visible !important;
        display: flex !important;
        flex-direction: column !important;
    }}
    section.main [data-testid="stHorizontalBlock"]:has(.lri-tabla-col) > [data-testid="column"]:has(.lri-tabla-col) [data-testid="stMarkdownContainer"] > div,
    section.main [data-testid="stHorizontalBlock"]:has(.lri-tabla-col) > [data-testid="column"]:has(.lri-tabla-col) div.stMarkdown > div {{
        flex: 0 1 auto !important;
        min-height: 0 !important;
        height: auto !important;
        max-height: none !important;
        overflow: visible !important;
        display: flex !important;
        flex-direction: column !important;
    }}
    .lri-prof-table {{
        width: 100%;
        max-width: 100%;
        table-layout: fixed;
        border-collapse: collapse;
        font-family: "Segoe UI", system-ui, sans-serif;
    }}
    .lri-prof-table col.lri-col-idx {{ width: 3.25rem; }}
    .lri-prof-table col.lri-col-num {{ width: 30%; }}
    .lri-prof-table th {{
        font-size: var(--lri-th-size, 1.45rem);
        font-weight: 700;
        padding: var(--lri-cell-pad-y, 0.85rem) var(--lri-cell-pad-x, 1rem);
        text-align: left;
        color: #94a3b8;
        background: #1a1f2e;
        border-bottom: 2px solid #334155;
        position: sticky;
        top: 0;
        z-index: 1;
    }}
    .lri-prof-table th.num,
    .lri-prof-table td.num {{
        text-align: right;
        font-variant-numeric: tabular-nums;
    }}
    /* Columnas 2 y 3: títulos centrados (nombres con varias líneas o /). */
    .lri-prof-table th.lri-th-dim,
    .lri-prof-table th.lri-th-metric {{
        text-align: center !important;
        line-height: 1.35;
        overflow-wrap: break-word;
        word-break: normal;
        hyphens: manual;
        text-wrap: balance;
    }}
    .lri-prof-table th.lri-metric,
    .lri-prof-table td.lri-metric {{
        font-size: var(--lri-td-val-size, 1.62rem);
    }}
    .lri-prof-table td {{
        font-size: var(--lri-td-num-size, 1.90rem);
        font-weight: 600;
        padding: var(--lri-cell-pad-y, 0.85rem) var(--lri-cell-pad-x, 1rem);
        color: #f8fafc;
        border-bottom: 1px solid #252a3a;
    }}
    .lri-prof-table td.cat {{
        font-size: var(--lri-td-cat-size, 1.90rem);
        font-weight: 500;
        color: #e2e8f0;
        word-wrap: break-word;
        overflow-wrap: anywhere;
    }}
    .lri-prof-table tbody tr:hover td {{
        background: rgba(56, 189, 248, 0.09);
    }}
    /* Gráfico: alto mínimo tipo panel 1080p aunque la tabla sea baja (categoría / subcategoría). */
    section.main [data-testid="stHorizontalBlock"]:has(.lri-tabla-col) > [data-testid="column"]:nth-child(2) {{
        max-height: var(--lri-row-min-h) !important;
        min-height: var(--lri-row-min-h) !important;
        max-width: min(100%, calc((min(var(--lri-ref-w), 100vw) - 3rem) * 0.667)) !important;
        min-width: 0 !important;
        overflow: hidden !important;
    }}
    section.main [data-testid="stHorizontalBlock"]:has(.lri-tabla-col) [data-testid="stPlotlyChart"] {{
        flex: 1 1 auto !important;
        min-height: calc(var(--lri-row-min-h) - 3.35rem) !important;
        max-height: 100% !important;
        width: 100% !important;
        max-width: 100% !important;
        overflow-x: auto !important;
        overflow-y: hidden !important;
    }}
    section.main [data-testid="stHorizontalBlock"]:has(.lri-tabla-col) [data-testid="stPlotlyChart"] > div {{
        min-height: calc(var(--lri-row-min-h) - 3.35rem) !important;
        max-height: 100% !important;
        min-width: 100% !important;
        width: auto !important;
        height: 100% !important;
        overflow-x: visible !important;
        overflow-y: hidden !important;
    }}
    section.main [data-testid="stHorizontalBlock"]:has(.lri-tabla-col) [data-testid="stPlotlyChart"] .plotly-graph-div {{
        max-width: none !important;
    }}
    /* Modo cod_producto / cod_prod: no superar alto 1080p; scroll horizontal en el panel. */
    section.main [data-testid="stHorizontalBlock"]:has(.lri-tabla-col) > [data-testid="column"]:has(.lri-chart-mode-codprod) {{
        max-height: min(var(--lri-row-min-h), calc(100dvh - 19.25rem), calc(100vh - 19.25rem)) !important;
        min-height: 0 !important;
    }}
    section.main [data-testid="stHorizontalBlock"]:has(.lri-tabla-col) > [data-testid="column"]:has(.lri-chart-mode-codprod) [data-testid="stPlotlyChart"] {{
        max-height: min(calc(100dvh - 22.25rem), calc(100vh - 22.25rem), calc(var(--lri-row-min-h) - 3.6rem)) !important;
        min-height: 0 !important;
        flex: 0 1 auto !important;
    }}
    section.main [data-testid="stHorizontalBlock"]:has(.lri-tabla-col) > [data-testid="column"]:has(.lri-chart-mode-codprod) [data-testid="stPlotlyChart"] > div {{
        max-height: min(calc(100dvh - 22.25rem), calc(100vh - 22.25rem), calc(var(--lri-row-min-h) - 3.6rem)) !important;
        min-height: 0 !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


def altura_grafico_adaptativa(n: int, viewport_h: int) -> int:
    """
    Alto en px del layout Plotly alineado al área útil Full HD (1920×1080 por defecto):
    - Tope: viewport_h − reserva fija (título, KPIs, captions, chrome).
    - Crece con el número de barras hasta ese tope; con muchas categorías se capa y hay scroll.
    """
    vph = int(viewport_h)
    usable = max(520, vph - RESERVA_VERTICAL_REF)
    if n <= 0:
        return max(360, min(usable, int(vph * 0.42)))
    h_cap = usable
    px_por_barra = max(6.5, min(20.0, 620.0 / max(n, 6)))
    necesario = int(210 + n * px_por_barra * 1.9)
    # Con pocas categorías, ocupar más del alto útil (1080p); con muchas, priorizar relleno hasta el tope.
    relleno_ratio = 0.88 if n <= 60 else 0.76 if n <= 140 else 0.72
    relleno = int(h_cap * relleno_ratio)
    return int(max(480, min(h_cap, max(necesario, relleno))))


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def estilos_css_variables_tabla(n_filas: int, viewport_h: int) -> str:
    """
    Variables CSS (--lri-*) en el contenedor de la tabla: pocas filas → tipografía grande;
    muchas filas o menos alto de referencia → reduce tamaño para aprovechar 1920×1080 sin desbordes.
    """
    vph = int(viewport_h)
    usable = max(400, vph - RESERVA_VERTICAL_REF - 48)
    filas_efectivas = max(1, int(n_filas))
    fila_budget = usable / (filas_efectivas + 1.2)
    # Tablas muy grandes: escala fuerte para que quepa en el panel 1080p (el scroll cubre el resto).
    scale = _clamp(fila_budget / 46.0, 0.36, 1.14)
    # Tope global 1.90 rem. La columna de métrica (valores tipo 2,822.10) va algo más pequeña.
    td_num_rem = _clamp(1.88 * scale, 0.58, 1.90)
    td_val_rem = min(
        _clamp(1.88 * scale * 0.86, 0.50, 1.68),
        max(0.52, td_num_rem - 0.06),
    )
    th = f"{_clamp(1.42 * scale, 0.68, 1.90):.2f}rem"
    td_num = f"{td_num_rem:.2f}rem"
    td_val = f"{td_val_rem:.2f}rem"
    td_cat = f"{_clamp(1.78 * scale, 0.56, 1.90):.2f}rem"
    py = f"{_clamp(0.82 * scale, 0.26, 1.08):.2f}rem"
    px = f"{_clamp(1.0 * scale, 0.40, 1.18):.2f}rem"
    return (
        f"--lri-th-size: {th}; --lri-td-num-size: {td_num}; --lri-td-val-size: {td_val}; "
        f"--lri-td-cat-size: {td_cat}; --lri-cell-pad-y: {py}; --lri-cell-pad-x: {px}"
    )


def _margen_inferior_x_rotado(
    n: int, tickfont_px: int, max_lab_len: int, viewport_h: int
) -> int:
    """Margen inferior Plotly para eje X con etiquetas rotadas (muchas categorías, cod_producto largos)."""
    vph = int(viewport_h)
    hlim = max(112, min(480, int(vph * 0.44)))
    tf = int(_clamp(float(tickfont_px), 7.0, 16.0))
    chars = int(_clamp(float(max_lab_len), 4.0, 48.0))
    m = int(44 + tf * 0.58 * chars + min(max(0, n - 16), 160) * 0.40)
    return int(_clamp(m, 108, hlim))


def _tamanos_tipografia_grafico(n: int, viewport_h: int) -> dict:
    """Tamaños de fuente y márgenes coherentes con el alto útil (1080p y otros)."""
    vph = int(viewport_h)
    usable = max(480, vph - RESERVA_VERTICAL_REF)
    densidad = max(n, 1) / max(usable / 520.0, 0.35)
    esc = _clamp(1.15 - 0.018 * (densidad - 1.0), 0.78, 1.12)
    title_sz = int(_clamp(17 * esc, 14, 20))
    axis_title = int(_clamp(14 * esc, 11, 17))
    tick_x = int(_clamp(15 - n / 32.0, 8, 14) * esc)
    tick_y = int(_clamp(13 * esc, 10, 15))
    text_bar = int(_clamp(15 * esc, 11, 18))
    margin_t = int(_clamp(76 - n * 0.08, 58, 92))
    return {
        "title_sz": title_sz,
        "axis_title": axis_title,
        "tick_x": tick_x,
        "tick_y": tick_y,
        "text_bar": text_bar,
        "margin_t": margin_t,
    }


def _fmt_celda_num_tabla(val) -> str:
    """Formato legible para celdas numéricas en la tabla HTML."""
    try:
        if pd.isna(val):
            return "—"
    except (TypeError, ValueError):
        pass
    try:
        v = float(val)
    except (TypeError, ValueError):
        return html.escape(str(val))
    if np.isnan(v):
        return "—"
    if abs(v - round(v)) < 1e-9 * max(1.0, abs(v)):
        return f"{int(round(v)):,}"
    av = abs(v)
    if av >= 1e9:
        return f"{v / 1e9:,.2f}B"
    if av >= 1e6:
        return f"{v / 1e6:,.2f}M"
    return f"{v:,.2f}"


def df_resumen_a_html_tabla(d: pd.DataFrame, col_cat: str, col_val: str) -> str:
    """Tabla HTML con tipografía grande (el grid de st.dataframe no escala texto por CSS)."""
    h_cat = html.escape(str(col_cat))
    h_val = html.escape(str(col_val))
    parts = [
        '<div class="lri-tabla-scroll"><table class="lri-prof-table">'
        '<colgroup><col class="lri-col-idx" /><col class="lri-col-cat" /><col class="lri-col-num" /></colgroup>'
        "<thead><tr>",
        f'<th class="num">#</th><th class="lri-th-dim">{h_cat}</th><th class="num lri-metric lri-th-metric">{h_val}</th>',
        "</tr></thead><tbody>",
    ]
    for i, (_, row) in enumerate(d.iterrows(), start=1):
        cat = html.escape(str(row[col_cat]))
        num_html = _fmt_celda_num_tabla(row[col_val])
        parts.append(
            f'<tr><td class="num">{i}</td><td class="cat">{cat}</td><td class="num lri-metric">{num_html}</td></tr>'
        )
    parts.append("</tbody></table></div>")
    return "".join(parts)


def _fmt_etiqueta_barra(val: float) -> str:
    """Texto encima de cada barra (compacto, legible)."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    v = float(val)
    av = abs(v)
    if av >= 1e9:
        return f"{v / 1e9:.2f}B"
    if av >= 1e6:
        return f"{v / 1e6:.2f}M"
    if av >= 1e3:
        return f"{v / 1e3:.1f}k"
    if abs(v - round(v)) < 1e-6:
        return f"{int(round(v)):,}"
    return f"{v:,.1f}"


def _lienzo_ancho_barras(
    n: int, chart_col_px: int, max_lab: int, modo_cod_producto: bool
) -> tuple[Optional[int], bool]:
    """
    Ancho del layout Plotly.
    modo_cod_producto: miles de SKUs → lienzo muy ancho (hasta LIENZO_MAX_ANCHO_COD_PX) + scroll horizontal.
    Categoría / subcategoría: pocas barras → columna sin ensanchar.
    """
    if n <= 0:
        return None, False
    if modo_cod_producto:
        px_por = 4.55
        extra = 140
        natural = int(n * px_por + extra)
        if natural <= chart_col_px and n <= 32:
            return None, False
        w = int(max(chart_col_px, min(LIENZO_MAX_ANCHO_COD_PX, natural)))
        return w, True
    px_por_barra = 7.85
    extra = int(168 + min(max_lab * 2, 160))
    natural = int(n * px_por_barra + extra)
    if n <= 44 and natural <= chart_col_px:
        return None, False
    w = int(max(chart_col_px, min(14000, natural)))
    return w, True


def fig_ranking_barras(
    df_resumen: pd.DataFrame,
    col_cat: str,
    col_val: str,
    operacion: str,
    viewport_h: Optional[int] = None,
    viewport_w: Optional[int] = None,
    modo_cod_producto: bool = False,
) -> go.Figure:
    """
    Barras verticales con color por magnitud: blanco / azul muy claro → azul
    saturado (misma idea que la referencia) y barra de color vertical.
    `modo_cod_producto`: reglas de alto estrictas 1080p + lienzo ancho y scroll horizontal para miles de códigos.
    """
    # Escala similar a la foto: valores bajos claros, altos azul intenso
    COLOR_SCALE_FOTO = [
        [0.0, "#ffffff"],
        [0.18, "#e8f4fc"],
        [0.38, "#90caf9"],
        [0.62, "#2196f3"],
        [0.82, "#1565c0"],
        [1.0, "#0d47a1"],
    ]
    d = df_resumen.copy()
    d[col_cat] = d[col_cat].astype(str)
    n = len(d)
    vph = int(viewport_h) if viewport_h is not None else REF_VIEWPORT_H
    vpw = int(viewport_w) if viewport_w is not None else REF_VIEWPORT_W
    # Ancho aproximado de la columna del gráfico (2/3 de 1920 menos paddings).
    chart_col_px = max(680, int((vpw - 96) * (2.0 / 3.0)))
    if n == 0:
        fig = go.Figure()
        fig.add_annotation(
            text="Sin datos para graficar",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=16, color="#94a3b8"),
        )
        fig.update_layout(
            height=max(360, int(vph * 0.36)),
            width=chart_col_px,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="#0f1419",
        )
        return fig

    d = d.sort_values(col_val, ascending=False).reset_index(drop=True)
    xs = d[col_cat].tolist()
    ys = d[col_val].astype(float).to_numpy()
    y_min = float(np.min(ys))
    y_max = float(np.max(ys))
    if y_max <= y_min:
        y_max = y_min + 1e-9

    textos = [_fmt_etiqueta_barra(float(y)) for y in ys]

    tp = _tamanos_tipografia_grafico(n, vph)
    cb_title = max(10, int(tp["axis_title"] * 0.95))
    cb_tick = max(9, int(tp["tick_y"] * 0.88))
    max_lab = max((len(str(t)) for t in xs), default=1)
    col_val_tit = _titulo_plotly_con_barra(col_val)
    col_cat_tit = _titulo_plotly_con_barra(col_cat)
    plot_w, _scroll_x = _lienzo_ancho_barras(n, chart_col_px, max_lab, modo_cod_producto)
    headroom = CHART_HEADROOM_COD_PX if modo_cod_producto else CHART_HEADROOM_PX
    usable_chart_h = max(380, int(vph) - RESERVA_VERTICAL_REF - headroom)
    altura_raw = int(min(altura_grafico_adaptativa(n, vph), usable_chart_h))
    if modo_cod_producto:
        altura = int(min(altura_raw, usable_chart_h, int(vph) - RESERVA_VERTICAL_REF - headroom - 6))
    else:
        altura = int(min(max(altura_raw, int(usable_chart_h * 0.92)), usable_chart_h))
    tick_x_eff = int(
        max(
            6,
            min(
                tp["tick_x"],
                chart_col_px / max(n * 1.05, 18),
                max(260, chart_col_px * 0.22) / max(max_lab, 6),
            ),
        )
    )
    tickangle_x = -90
    lab_for_margin = max_lab
    if modo_cod_producto:
        lab_for_margin = min(max_lab, 22)
    elif max_lab > 18 and n <= 80:
        tickangle_x = -45
        lab_for_margin = min(max_lab, 28)
    margin_b_raw = _margen_inferior_x_rotado(n, tick_x_eff, lab_for_margin, vph)
    margin_b_cap = max(112, int(altura * (0.40 if modo_cod_producto else 0.44)))
    margin_b = int(min(margin_b_raw, margin_b_cap))

    if modo_cod_producto:
        if n <= 12:
            bar_text, bar_tpos = textos, "outside"
        elif n <= 28:
            bar_text, bar_tpos = textos, "inside"
        else:
            bar_text, bar_tpos = None, None
    elif n <= 22:
        bar_text, bar_tpos = textos, "outside"
    elif n <= 50:
        bar_text, bar_tpos = textos, "inside"
    else:
        bar_text, bar_tpos = None, None

    cb_thick = 16 if (modo_cod_producto and n > 180) else 22
    bar_kwargs: dict = dict(
        x=xs,
        y=ys,
        marker=dict(
            color=ys,
            cmin=y_min,
            cmax=y_max,
            colorscale=COLOR_SCALE_FOTO,
            colorbar=dict(
                title=dict(
                    text=col_val_tit,
                    side="right",
                    font=dict(size=cb_title, color="#f1f5f9"),
                ),
                tickfont=dict(size=cb_tick, color="#94a3b8"),
                bgcolor="rgba(19, 23, 34, 0.92)",
                bordercolor="#475569",
                borderwidth=1,
                thickness=cb_thick,
                len=0.78,
                outlinewidth=0,
            ),
            line=dict(width=0),
            cornerradius=6,
        ),
        hovertemplate=(
            f"<b>%{{x}}</b><br>{html.escape(str(operacion))} de <b>{col_val_tit}</b>: "
            "<b>%{y:,.2f}</b><extra></extra>"
        ),
        cliponaxis=bool(modo_cod_producto or n > 35),
    )
    if bar_text is not None:
        bar_kwargs["text"] = bar_text
        bar_kwargs["textposition"] = bar_tpos
        bar_kwargs["textfont"] = dict(color="#f8fafc", size=tp["text_bar"])

    fig = go.Figure()
    fig.add_trace(go.Bar(**bar_kwargs))

    bargap = float(max(0.14, min(0.48, 0.44 - n * 0.0016)))

    _mr = 82 if (modo_cod_producto and n > 150) else 96
    _op_t = html.escape(str(operacion))
    _layout = dict(
        title=dict(
            text=f"<span style='color:#94a3b8'>{_op_t}</span> · "
            f"<span style='color:#f8fafc'>{col_val_tit}</span> "
            f"<span style='color:#64748b'>por</span> "
            f"<span style='color:#f8fafc'>{col_cat_tit}</span>",
            font=dict(family="Segoe UI, system-ui, sans-serif", size=tp["title_sz"]),
            x=0.02,
            xanchor="left",
            y=0.97,
            yanchor="top",
        ),
        height=altura,
        margin=dict(l=56, r=_mr, t=tp["margin_t"], b=margin_b),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0f1419",
        bargap=bargap,
        showlegend=False,
        font=dict(
            family="Segoe UI, system-ui, sans-serif",
            color="#94a3b8",
            size=tp["tick_y"],
        ),
        hoverlabel=dict(
            bgcolor="#1e293b",
            bordercolor="#334155",
            font_size=max(11, int(tp["tick_y"])),
            font_color="#f1f5f9",
        ),
    )
    if plot_w is not None:
        _layout["width"] = plot_w
        _layout["autosize"] = False
    else:
        _layout["autosize"] = True
    fig.update_layout(**_layout)

    lienz_w = plot_w if plot_w is not None else chart_col_px
    max_ticks = max(24, min(120, int(lienz_w // max(8, tick_x_eff + 2))))
    tick_extra: dict = {}
    if n > max_ticks:
        idx = np.unique(np.round(np.linspace(0, n - 1, max_ticks)).astype(int))
        tv = [xs[int(i)] for i in idx]
        tick_extra = dict(tickmode="array", tickvals=tv, ticktext=[str(x) for x in tv])

    fig.update_xaxes(
        title=dict(text=col_cat_tit, font=dict(color="#94a3b8", size=tp["axis_title"])),
        tickangle=tickangle_x,
        tickfont=dict(size=tick_x_eff, color="#e2e8f0"),
        automargin=False,
        showline=True,
        linewidth=1,
        linecolor="rgba(148,163,184,0.35)",
        showgrid=False,
        zeroline=False,
        **tick_extra,
    )
    fig.update_yaxes(
        title=dict(text=col_val_tit, font=dict(color="#94a3b8", size=tp["axis_title"])),
        tickfont=dict(size=tp["tick_y"], color="#cbd5e1"),
        automargin=False,
        showgrid=True,
        gridcolor="rgba(148,163,184,0.12)",
        zeroline=True,
        zerolinewidth=1,
        zerolinecolor="rgba(148,163,184,0.25)",
        showline=False,
        separatethousands=True,
        tickformat=",.0f",
    )
    return fig


def cargar_datos() -> tuple[Optional[pd.DataFrame], Optional[str]]:
    if not os.path.isfile(ARCHIVO_EXCEL_PATH):
        return None, f"En la ruta esperada no hay archivo:\n`{ARCHIVO_EXCEL_PATH}`"
    try:
        return pd.read_excel(ARCHIVO_EXCEL_PATH, engine="openpyxl"), None
    except PermissionError:
        return None, (
            "**Permiso denegado al leer el .xlsx.** Suele ocurrir si:\n\n"
            "- El libro **está abierto en Excel** → ciérrelo y use *Rerun* en Streamlit.\n"
            "- **OneDrive** solo tiene una copia en la nube → «Mantener siempre en este dispositivo».\n"
            "- Otro programa tiene el archivo bloqueado."
        )
    except ImportError as e:
        return None, f"Falta el motor para .xlsx ({e}). Instale: `pip install openpyxl`"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


df, _error_carga_excel = cargar_datos()

if df is not None:
    with st.sidebar:
        st.title("⚙️ Configuración")
        cols_texto = df.select_dtypes(include=["object", "category"]).columns.tolist()
        cols_num = df.select_dtypes(include=["number"]).columns.tolist()

        eje_x = st.selectbox("Categoría / Dimensión", options=cols_texto)
        eje_y = st.selectbox("Métrica / Valor", options=cols_num)

        operacion = st.radio("Cálculo de Análisis", ["Suma", "Promedio", "Máximo", "Mínimo"])
        dict_ops = {"Suma": "sum", "Promedio": "mean", "Máximo": "max", "Mínimo": "min"}
        top_n = st.number_input(
            "Top N filas (0 = todas)",
            min_value=0,
            max_value=50000,
            value=0,
            step=10,
            help="Orden por métrica de mayor a menor. 0 = todos los códigos/categorías del agrupado.",
        )
        _vp_opts = [720, 768, 900, 1080, 1200, 1440]
        _vp_default = (
            REF_VIEWPORT_H
            if REF_VIEWPORT_H in _vp_opts
            else min(_vp_opts, key=lambda h: abs(h - REF_VIEWPORT_H))
        )
        viewport_h_ui = st.select_slider(
            "Alto pantalla referencia (px)",
            options=_vp_opts,
            value=_vp_default,
            help="Diseño orientado a 1920×1080 (ancho vía LRI_VIEWPORT_W, alto aquí o LRI_VIEWPORT_H). "
            "El gráfico y la tabla escalan según este alto y el número de filas/categorías.",
        )

    st.title("Panel de Perfilado de Datos")
    st.markdown(
        f"<p style='color: #a1a1aa; margin-top: -20px;'>Resumen general del análisis: "
        f"<b>{eje_y}</b> por <b>{eje_x}</b></p>",
        unsafe_allow_html=True,
    )

    val_total = df[eje_y].sum()
    cats_count = df[eje_x].nunique()
    val_avg = df[eje_y].mean()
    val_max = df[eje_y].max()

    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-title'>Total {eje_y}</div>"
            f"<div class='kpi-value'>{val_total:,.0f}</div></div>",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-title'>Subcategorías</div>"
            f"<div class='kpi-value'>{cats_count}</div></div>",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-title'>Promedio</div>"
            f"<div class='kpi-value'>{val_avg:,.1f}</div></div>",
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-title'>Valor Máximo</div>"
            f"<div class='kpi-value'>{val_max:,.0f}</div></div>",
            unsafe_allow_html=True,
        )
    with c5:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-title'>Valor Mínimo</div>"
            f"<div class='kpi-value'>{df[eje_y].min():,.0f}</div></div>",
            unsafe_allow_html=True,
        )

    col_tabla, col_grafico = st.columns([1, 2])

    df_agrup = df.groupby(eje_x)[eje_y].agg(dict_ops[operacion]).reset_index()
    df_agrup = df_agrup.sort_values(by=eje_y, ascending=False)
    total_grupos = len(df_agrup)
    if top_n and top_n > 0:
        df_resumen = df_agrup.head(int(top_n))
    else:
        df_resumen = df_agrup

    if top_n and top_n > 0 and total_grupos > len(df_resumen):
        st.caption(
            f"Mostrando las {len(df_resumen)} categorías con mayor {eje_y} "
            f"de {total_grupos} grupos en total."
        )
    else:
        st.caption(f"Mostrando {len(df_resumen)} categorías (todas las del agrupado).")

    with col_tabla:
        _est_tabla = estilos_css_variables_tabla(len(df_resumen), viewport_h_ui)
        _op_t = html.escape(str(operacion))
        st.markdown(
            f'<div class="lri-tabla-col" style="{_est_tabla}">'
            f'<div class="lri-tabla-title">Tabla de {_op_t}</div>'
            f"{df_resumen_a_html_tabla(df_resumen, eje_x, eje_y)}</div>",
            unsafe_allow_html=True,
        )

    with col_grafico:
        _modo_cod = es_eje_cod_producto(eje_x)
        if _modo_cod:
            st.markdown(
                '<span class="lri-chart-mode-codprod" aria-hidden="true"></span>',
                unsafe_allow_html=True,
            )
        st.subheader("Visualización")
        fig = fig_ranking_barras(
            df_resumen,
            eje_x,
            eje_y,
            operacion,
            viewport_h=viewport_h_ui,
            viewport_w=REF_VIEWPORT_W,
            modo_cod_producto=_modo_cod,
        )
        st.plotly_chart(
            fig,
            use_container_width=True,
            width="stretch",
            height="content" if _modo_cod else "stretch",
            config={"displayModeBar": True, "responsive": False},
        )

else:
    st.error(f"No se pudo cargar el Excel. Ruta esperada:\n`{ARCHIVO_EXCEL_PATH}`")
    if _error_carga_excel:
        st.markdown(_error_carga_excel)
