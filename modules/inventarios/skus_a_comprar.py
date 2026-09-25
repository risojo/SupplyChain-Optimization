"""SKUs a comprar — decisión de reposición (submódulo de Inventory Pro).

Viñeta hermana de «GMROI y EVAI» en el menú Decisiones.
Cuando esta decisión está activa, el sidebar muestra un menú de Herramientas
distinto (Base de datos + Stock de seguridad + Cantidad mínima por SKU).

Uso desde la app:
    import skus_a_comprar
    skus_a_comprar.render(df, params)
    skus_a_comprar.render_stock_seguridad(df, params)
    skus_a_comprar.render_demanda_tiempo_entrega(df, params)
    skus_a_comprar.render_cantidad_minima(df, params)
"""
from __future__ import annotations

import io
from typing import Any

import re
import unicodedata

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import analisis_chatgpt

# ---------------------------------------------------------------------------
# Identidad de la viñeta (navegación sidebar · Decisiones)
# ---------------------------------------------------------------------------
VISTA_NOMBRE = "SKUs a comprar"
VISTA_HELP = (
    "Decisión de compra: artículos a reponer / por debajo del mínimo. "
    "Activa el menú de herramientas de reposición."
)

# Herramientas propias de este modo (reemplazan Parámetros/Scorecard/…).
HERRAMIENTA_BASE_DATOS = "Base de datos"
HERRAMIENTA_STOCK_SEGURIDAD = "Stock de seguridad"
HERRAMIENTA_DEMANDA_TR = "Demanda en el tiempo de entrega"
HERRAMIENTA_CANTIDAD_MINIMA = "Cantidad mínima por SKU"
HERRAMIENTA_ASISTENTE = "Asistente Inteligente de Inventarios LRI"
HERRAMIENTAS_MODO = (
    HERRAMIENTA_BASE_DATOS,
    HERRAMIENTA_STOCK_SEGURIDAD,
    HERRAMIENTA_DEMANDA_TR,
    HERRAMIENTA_CANTIDAD_MINIMA,
    HERRAMIENTA_ASISTENTE,
)

COL_STOCK_SEGURIDAD = "stock de seguridad"
COL_DEMANDA_DIARIA = "demanda diaria"
COL_DEMANDA_TR = "demanda en el tiempo de entrega"
COL_CANTIDAD_MINIMA = "cantidad minima de inventario"
COL_CANTIDAD_COMPRAR = "cantidad a comprar"
COL_INVENTARIO_FINAL = "inventario final bulto"
_CLAVE_DIAS_TRABAJO = "inv_dias_trabajo_mes"
_CLAVE_ROTACION_DESEADA = "inv_rotacion_deseada"
_DIAS_TRABAJO_MIN = 20
_DIAS_TRABAJO_MAX = 30
_DIAS_TRABAJO_DEFAULT = 30
_ROTACION_DESEADA_MIN = 1
_ROTACION_DESEADA_MAX = 12
_ROTACION_DESEADA_DEFAULT = 4


def _n_skus(df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    if "codigo" in df.columns:
        return int(df["codigo"].nunique(dropna=True))
    return int(len(df))


def _columna_inventario_disponible(df: pd.DataFrame) -> str | None:
    for cand in (
        "inventario promedio bultos",
        "inventario final bulto",
        "pronostico ajustado",
        "pronostico",
    ):
        if cand in df.columns:
            return cand
    return None


def _serie_num(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce")


def calcular_stock_seguridad(df: pd.DataFrame) -> pd.Series:
    """Stock de seguridad = pronóstico ajustado − pronóstico."""
    return _serie_num(df, "pronostico ajustado") - _serie_num(df, "pronostico")


def tabla_stock_seguridad(df: pd.DataFrame) -> pd.DataFrame:
    """Tabla de trabajo con la columna calculada ``stock de seguridad``."""
    cols = [
        c
        for c in (
            "codigo",
            "descripcion",
            "categoria",
            "subcategoria",
            "pronostico",
            "pronostico ajustado",
        )
        if c in df.columns
    ]
    out = df.loc[:, cols].copy() if cols else df.copy()
    out[COL_STOCK_SEGURIDAD] = calcular_stock_seguridad(df)
    preferido = [
        c
        for c in (
            "codigo",
            "descripcion",
            "categoria",
            "subcategoria",
            "pronostico",
            "pronostico ajustado",
            COL_STOCK_SEGURIDAD,
        )
        if c in out.columns
    ]
    extras = [c for c in out.columns if c not in preferido]
    return out.loc[:, preferido + extras]


def aplicar_stock_seguridad_en_sesion(df: pd.DataFrame) -> pd.DataFrame:
    """Escribe ``stock de seguridad`` en el DataFrame de sesión (copia)."""
    out = df.copy()
    out[COL_STOCK_SEGURIDAD] = calcular_stock_seguridad(df)
    return out


def _dias_trabajo_mes() -> int:
    """Días laborables del mes (slider 20–30; default 30)."""
    val = st.session_state.get(_CLAVE_DIAS_TRABAJO, _DIAS_TRABAJO_DEFAULT)
    try:
        n = int(val)
    except (TypeError, ValueError):
        n = _DIAS_TRABAJO_DEFAULT
    return max(_DIAS_TRABAJO_MIN, min(_DIAS_TRABAJO_MAX, n))


def _rotacion_deseada() -> int:
    """Rotación deseada de la compañía (slider 1–12)."""
    val = st.session_state.get(_CLAVE_ROTACION_DESEADA, _ROTACION_DESEADA_DEFAULT)
    try:
        n = int(val)
    except (TypeError, ValueError):
        n = _ROTACION_DESEADA_DEFAULT
    return max(_ROTACION_DESEADA_MIN, min(_ROTACION_DESEADA_MAX, n))


def calcular_demanda_diaria(
    df: pd.DataFrame, dias_trabajo: int = _DIAS_TRABAJO_DEFAULT
) -> pd.Series:
    """Demanda diaria = pronóstico ÷ días de trabajo del mes."""
    dias = max(1, int(dias_trabajo))
    return _serie_num(df, "pronostico") / dias


def calcular_demanda_tiempo_entrega(
    df: pd.DataFrame, dias_trabajo: int = _DIAS_TRABAJO_DEFAULT
) -> pd.Series:
    """Demanda en el TR = (pronóstico ÷ días trabajo) × tiempo de entrega."""
    return calcular_demanda_diaria(df, dias_trabajo) * _serie_num(df, "tiempo entrega")


def tabla_demanda_tiempo_entrega(
    df: pd.DataFrame, dias_trabajo: int = _DIAS_TRABAJO_DEFAULT
) -> pd.DataFrame:
    """Tabla con demanda diaria y demanda en el tiempo de entrega."""
    cols = [
        c
        for c in (
            "codigo",
            "descripcion",
            "categoria",
            "subcategoria",
            "pronostico",
            "tiempo entrega",
        )
        if c in df.columns
    ]
    out = df.loc[:, cols].copy() if cols else df.copy()
    out[COL_DEMANDA_DIARIA] = calcular_demanda_diaria(df, dias_trabajo)
    out[COL_DEMANDA_TR] = calcular_demanda_tiempo_entrega(df, dias_trabajo)
    preferido = [
        c
        for c in (
            "codigo",
            "descripcion",
            "categoria",
            "subcategoria",
            "pronostico",
            "tiempo entrega",
            COL_DEMANDA_DIARIA,
            COL_DEMANDA_TR,
        )
        if c in out.columns
    ]
    extras = [c for c in out.columns if c not in preferido]
    return out.loc[:, preferido + extras]


def aplicar_demanda_tr_en_sesion(
    df: pd.DataFrame, dias_trabajo: int = _DIAS_TRABAJO_DEFAULT
) -> pd.DataFrame:
    """Escribe demanda diaria y demanda en el TR en el DataFrame de sesión."""
    out = df.copy()
    out[COL_DEMANDA_DIARIA] = calcular_demanda_diaria(df, dias_trabajo)
    out[COL_DEMANDA_TR] = calcular_demanda_tiempo_entrega(df, dias_trabajo)
    return out


def _serie_stock_seguridad(df: pd.DataFrame) -> pd.Series:
    """Usa la columna de sesión si existe; si no, la recalcula."""
    if COL_STOCK_SEGURIDAD in df.columns:
        return _serie_num(df, COL_STOCK_SEGURIDAD)
    return calcular_stock_seguridad(df)


def _serie_demanda_tr(
    df: pd.DataFrame, dias_trabajo: int | None = None
) -> pd.Series:
    """Usa la columna de sesión si existe; si no, la recalcula."""
    if COL_DEMANDA_TR in df.columns:
        return _serie_num(df, COL_DEMANDA_TR)
    return calcular_demanda_tiempo_entrega(
        df, dias_trabajo if dias_trabajo is not None else _dias_trabajo_mes()
    )


def calcular_cantidad_minima(
    df: pd.DataFrame, dias_trabajo: int | None = None
) -> pd.Series:
    """Cantidad mínima de inventario = stock de seguridad + demanda en el TR."""
    return _serie_stock_seguridad(df) + _serie_demanda_tr(df, dias_trabajo)


def tabla_cantidad_minima(
    df: pd.DataFrame, dias_trabajo: int | None = None
) -> pd.DataFrame:
    """Tabla con inputs y la cantidad mínima de inventario por SKU."""
    dias = dias_trabajo if dias_trabajo is not None else _dias_trabajo_mes()
    ss = _serie_stock_seguridad(df)
    dtr = _serie_demanda_tr(df, dias)
    cols = [
        c
        for c in (
            "codigo",
            "descripcion",
            "categoria",
            "subcategoria",
            COL_STOCK_SEGURIDAD,
            COL_DEMANDA_TR,
        )
        if c in df.columns
    ]
    out = df.loc[:, cols].copy() if cols else pd.DataFrame(index=df.index)
    out[COL_STOCK_SEGURIDAD] = ss
    out[COL_DEMANDA_TR] = dtr
    out[COL_CANTIDAD_MINIMA] = ss + dtr
    preferido = [
        c
        for c in (
            "codigo",
            "descripcion",
            "categoria",
            "subcategoria",
            COL_STOCK_SEGURIDAD,
            COL_DEMANDA_TR,
            COL_CANTIDAD_MINIMA,
        )
        if c in out.columns
    ]
    extras = [c for c in out.columns if c not in preferido]
    return out.loc[:, preferido + extras]


def aplicar_cantidad_minima_en_sesion(
    df: pd.DataFrame, dias_trabajo: int | None = None
) -> pd.DataFrame:
    """Escribe stock SS, demanda TR (si faltan) y cantidad mínima en sesión."""
    dias = dias_trabajo if dias_trabajo is not None else _dias_trabajo_mes()
    out = df.copy()
    ss = _serie_stock_seguridad(df)
    dtr = _serie_demanda_tr(df, dias)
    out[COL_STOCK_SEGURIDAD] = ss
    if COL_DEMANDA_DIARIA not in out.columns:
        out[COL_DEMANDA_DIARIA] = calcular_demanda_diaria(df, dias)
    out[COL_DEMANDA_TR] = dtr
    out[COL_CANTIDAD_MINIMA] = ss + dtr
    return out


def _serie_cantidad_minima(
    df: pd.DataFrame, dias_trabajo: int | None = None
) -> pd.Series:
    if COL_CANTIDAD_MINIMA in df.columns:
        return _serie_num(df, COL_CANTIDAD_MINIMA)
    return calcular_cantidad_minima(df, dias_trabajo)


def calcular_cantidad_a_comprar(
    df: pd.DataFrame,
    rotacion: int,
    dias_trabajo: int | None = None,
) -> pd.Series:
    """Cantidad a comprar = (pronóstico ajustado × 12 / rotación) − mínimo.

    Solo aplica si inventario final < cantidad mínima; si no, 0.
    """
    rot = max(1, int(rotacion))
    minimo = _serie_cantidad_minima(df, dias_trabajo)
    inventario = _serie_num(df, COL_INVENTARIO_FINAL)
    objetivo = _serie_num(df, "pronostico ajustado") * 12.0 / rot
    qty = (objetivo - minimo).clip(lower=0)
    bajo_minimo = inventario < minimo
    return qty.where(bajo_minimo, 0.0)


def mascara_bajo_minimo(
    df: pd.DataFrame, dias_trabajo: int | None = None
) -> pd.Series:
    """True cuando inventario final < cantidad mínima de inventario."""
    minimo = _serie_cantidad_minima(df, dias_trabajo)
    inventario = _serie_num(df, COL_INVENTARIO_FINAL)
    return inventario < minimo


def calcular_cantidad_a_comprar_por_minimo(
    df: pd.DataFrame, dias_trabajo: int | None = None
) -> pd.Series:
    """Cantidad oficial a reponer según inventario mínimo (sin rotación).

    = max(0, cantidad minima de inventario − inventario final bulto).
    Solo es > 0 cuando el SKU está bajo el mínimo.
    No usa rotación objetivo ni pronóstico × 12 / rotación.
    """
    if COL_INVENTARIO_FINAL not in df.columns:
        raise ValueError(
            "Falta la columna oficial «inventario final bulto» "
            "para calcular la reposición por mínimo."
        )
    minimo = _serie_cantidad_minima(df, dias_trabajo)
    inventario = _serie_num(df, COL_INVENTARIO_FINAL)
    return (minimo - inventario).clip(lower=0)


def tabla_reposicion_por_minimo(
    df: pd.DataFrame,
    dias_trabajo: int | None = None,
    *,
    solo_positivos: bool = True,
) -> pd.DataFrame:
    """Tabla de artículos a reponer según mínimo (sin rotación)."""
    dias = dias_trabajo if dias_trabajo is not None else _dias_trabajo_mes()
    qty = calcular_cantidad_a_comprar_por_minimo(df, dias)
    minimo = _serie_cantidad_minima(df, dias)
    inventario = _serie_num(df, COL_INVENTARIO_FINAL)
    cols = [
        c
        for c in ("codigo", "descripcion", "categoria", "subcategoria", "proveedor")
        if c in df.columns
    ]
    out = df.loc[:, cols].copy() if cols else pd.DataFrame(index=df.index)
    out[COL_CANTIDAD_MINIMA] = minimo
    out[COL_INVENTARIO_FINAL] = inventario
    out[COL_CANTIDAD_COMPRAR] = qty
    if solo_positivos:
        out = out.loc[qty > 0].copy()
    return out.reset_index(drop=True)


def tabla_skus_a_comprar(
    df: pd.DataFrame,
    rotacion: int,
    dias_trabajo: int | None = None,
    *,
    solo_a_comprar: bool = True,
) -> pd.DataFrame:
    """Tabla de decisión: mínimo, inventario y cantidad a comprar."""
    dias = dias_trabajo if dias_trabajo is not None else _dias_trabajo_mes()
    rot = max(1, int(rotacion))
    minimo = _serie_cantidad_minima(df, dias)
    inventario = _serie_num(df, COL_INVENTARIO_FINAL)
    qty = calcular_cantidad_a_comprar(df, rot, dias)
    objetivo = _serie_num(df, "pronostico ajustado") * 12.0 / rot

    cols = [
        c
        for c in (
            "codigo",
            "descripcion",
            "categoria",
            "subcategoria",
            "proveedor",
            "pronostico ajustado",
            COL_INVENTARIO_FINAL,
            COL_STOCK_SEGURIDAD,
            COL_DEMANDA_TR,
            COL_CANTIDAD_MINIMA,
        )
        if c in df.columns
    ]
    out = df.loc[:, cols].copy() if cols else pd.DataFrame(index=df.index)
    out[COL_STOCK_SEGURIDAD] = _serie_stock_seguridad(df)
    out[COL_DEMANDA_TR] = _serie_demanda_tr(df, dias)
    out[COL_CANTIDAD_MINIMA] = minimo
    if COL_INVENTARIO_FINAL not in out.columns:
        out[COL_INVENTARIO_FINAL] = inventario
    out["inventario objetivo"] = objetivo
    out[COL_CANTIDAD_COMPRAR] = qty

    preferido = [
        c
        for c in (
            "codigo",
            "descripcion",
            "categoria",
            "subcategoria",
            "proveedor",
            "pronostico ajustado",
            COL_INVENTARIO_FINAL,
            COL_CANTIDAD_MINIMA,
            "inventario objetivo",
            COL_CANTIDAD_COMPRAR,
        )
        if c in out.columns
    ]
    extras = [c for c in out.columns if c not in preferido]
    out = out.loc[:, preferido + extras]

    if solo_a_comprar:
        out = out.loc[mascara_bajo_minimo(df, dias)].copy()
        out = out.loc[out[COL_CANTIDAD_COMPRAR] > 0].copy()
    return out.reset_index(drop=True)


def aplicar_cantidad_a_comprar_en_sesion(
    df: pd.DataFrame,
    rotacion: int,
    dias_trabajo: int | None = None,
) -> pd.DataFrame:
    """Persiste mínimo (si falta) y cantidad a comprar en la sesión."""
    dias = dias_trabajo if dias_trabajo is not None else _dias_trabajo_mes()
    out = aplicar_cantidad_minima_en_sesion(df, dias)
    out[COL_CANTIDAD_COMPRAR] = calcular_cantidad_a_comprar(out, rotacion, dias)
    return out


def _dataframe_misma_foto(df: pd.DataFrame) -> None:
    """``st.dataframe`` como en la foto; columna vacía al final para poder
    achicar también la última columna de datos (no queda pegada al borde)."""
    vista = df.copy()
    flex = " "
    while flex in vista.columns:
        flex += " "
    vista[flex] = pd.NA

    cfg: dict[str, Any] = {}
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(vista[c]):
            cfg[c] = st.column_config.NumberColumn(c, format="%.4f", width="medium")
        else:
            cfg[c] = st.column_config.TextColumn(c, width="medium")
    if COL_STOCK_SEGURIDAD in vista.columns:
        cfg[COL_STOCK_SEGURIDAD] = st.column_config.NumberColumn(
            COL_STOCK_SEGURIDAD,
            format="%.4f",
            width="small",
        )
    if COL_CANTIDAD_MINIMA in vista.columns:
        cfg[COL_CANTIDAD_MINIMA] = st.column_config.NumberColumn(
            COL_CANTIDAD_MINIMA,
            format="%.4f",
            width="medium",
        )
    # Esta columna es la que Streamlit estira al borde; las de datos quedan móviles.
    cfg[flex] = st.column_config.Column(label=" ", width="small", disabled=True)

    st.dataframe(
        vista,
        use_container_width=True,
        hide_index=True,
        column_config=cfg,
    )


def _bytes_excel_articulos_a_comprar(df: pd.DataFrame) -> bytes:
    """Excel de decisión: ítem, proveedor, categoría, subcategoría y cantidad."""
    cols = [
        c
        for c in (
            "codigo",
            "descripcion",
            "proveedor",
            "categoria",
            "subcategoria",
            COL_CANTIDAD_COMPRAR,
            "monto compra",
        )
        if c in df.columns
    ]
    if not cols:
        cols = list(df.columns)
    export = df.loc[:, cols].copy()
    # Solo filas con cantidad positiva a comprar
    if COL_CANTIDAD_COMPRAR in export.columns:
        qty = pd.to_numeric(export[COL_CANTIDAD_COMPRAR], errors="coerce").fillna(0)
        export = export.loc[qty > 0].copy()
    rename = {
        "codigo": "Ítem / SKU",
        "descripcion": "Descripción",
        "proveedor": "Proveedor",
        "categoria": "Categoría",
        "subcategoria": "Subcategoría",
        COL_CANTIDAD_COMPRAR: "Cantidad a comprar",
        "monto compra": "Monto de compra ($)",
    }
    export = export.rename(columns={k: v for k, v in rename.items() if k in export.columns})
    salida = io.BytesIO()
    with pd.ExcelWriter(salida, engine="openpyxl") as writer:
        export.to_excel(writer, sheet_name="Articulos a comprar", index=False)
    salida.seek(0)
    return salida.getvalue()


def _mostrar_tabla_final_comprar(df: pd.DataFrame) -> None:
    """Tabla final de SKUs a comprar: anchos compactos + columna compra resaltada."""
    orden = [
        c
        for c in (
            "codigo",
            "descripcion",
            "categoria",
            "subcategoria",
            "proveedor",
            "pronostico ajustado",
            COL_INVENTARIO_FINAL,
            COL_CANTIDAD_MINIMA,
            "inventario objetivo",
            COL_CANTIDAD_COMPRAR,
        )
        if c in df.columns
    ]
    extras = [c for c in df.columns if c not in orden]
    vista = df.loc[:, orden + extras].copy()

    flex = " "
    while flex in vista.columns:
        flex += " "
    vista[flex] = ""

    fmt = {
        c: "{:,.2f}"
        for c in vista.select_dtypes(include="number").columns
    }
    # Evitar Styler+Arrow issues: coloreamos vía HTML CSS en column_config no aplica;
    # usamos estilo pandas solo en la columna compra (sin dtype object raro).
    try:
        styler = vista.style.format(fmt, na_rep="—")
        if COL_CANTIDAD_COMPRAR in vista.columns:
            styler = styler.set_properties(
                subset=[COL_CANTIDAD_COMPRAR],
                **{
                    "background-color": "#14532d",
                    "color": "#bbf7d0",
                    "font-weight": "700",
                },
            )
        data_show: Any = styler
    except Exception:
        data_show = vista

    # Anchos compactos (px) — estilo foto / Base de datos, sin estirar la última.
    anchos_px: dict[str, int] = {
        "codigo": 88,
        "descripcion": 210,
        "categoria": 100,
        "subcategoria": 120,
        "proveedor": 110,
        "pronostico ajustado": 108,
        COL_INVENTARIO_FINAL: 108,
        COL_CANTIDAD_MINIMA: 120,
        "inventario objetivo": 118,
        COL_CANTIDAD_COMPRAR: 130,
        flex: 36,
    }

    cfg: dict[str, Any] = {}
    for c in vista.columns:
        w = anchos_px.get(c, 100)
        if c == flex:
            cfg[c] = st.column_config.Column(label=" ", width=w, disabled=True)
        elif c == COL_CANTIDAD_COMPRAR:
            cfg[c] = st.column_config.NumberColumn(
                c,
                format="%.2f",
                width=w,
                help="Cantidad sugerida a comprar (resaltada).",
            )
        elif pd.api.types.is_numeric_dtype(vista[c]):
            cfg[c] = st.column_config.NumberColumn(c, format="%.2f", width=w)
        else:
            cfg[c] = st.column_config.TextColumn(c, width=w)

    st.dataframe(
        data_show,
        use_container_width=True,
        hide_index=True,
        column_config=cfg,
        height=min(520, 56 + max(len(vista), 1) * 36),
    )

    # Viñeta: decidir si exportar a Excel los artículos a comprar
    st.checkbox(
        "Generar Excel de artículos a comprar",
        key="inv_skus_export_excel_check",
        help=(
            "Si lo marca, podrá descargar un Excel con ítem, proveedor, "
            "categoría, subcategoría y cantidad a comprar."
        ),
    )
    if st.session_state.get("inv_skus_export_excel_check"):
        n_pos = 0
        if COL_CANTIDAD_COMPRAR in df.columns:
            n_pos = int(
                (pd.to_numeric(df[COL_CANTIDAD_COMPRAR], errors="coerce").fillna(0) > 0).sum()
            )
        st.caption(
            f"Incluye **{n_pos:,}** artículo(s) con cantidad a comprar > 0 · "
            "columnas: Ítem/SKU, Descripción, Proveedor, Categoría, Subcategoría, "
            "Cantidad a comprar."
        )
        st.download_button(
            "Descargar Excel de compra",
            data=_bytes_excel_articulos_a_comprar(df),
            file_name="articulos_a_comprar.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="inv_skus_dl_excel_comprar",
            type="primary",
        )


_CLAVE_GRAFICO_NIVEL = "inv_skus_grafico_nivel"
_CLAVE_GRAFICO_CATEGORIA = "inv_skus_grafico_categoria"
_CLAVE_GRAFICO_SUBCATEGORIA = "inv_skus_grafico_subcategoria"
_CLAVE_GRAFICO_PROVEEDOR = "inv_skus_grafico_proveedor"
_CLAVE_GRAFICO_SKU_ITEM = "inv_skus_grafico_sku_item"
_CLAVE_GRAFICO_MAYOR_MENOR = "inv_skus_grafico_mayor_menor"
_CLAVE_GRAFICO_COMPLETO = "inv_skus_grafico_completo"
_CLAVE_GRAFICO_TOP_N = "inv_skus_grafico_top_n"
_CLAVE_GRAFICO_SCROLL_COMPLETO = "inv_skus_grafico_scroll_completo"
_NIVELES_GRAFICO = ("SKU", "Categoría", "Subcategoría", "Proveedor")

# Claves públicas (sidebar / voz).
CLAVE_NIVEL = _CLAVE_GRAFICO_NIVEL
CLAVE_CATEGORIA = _CLAVE_GRAFICO_CATEGORIA
CLAVE_SUBCATEGORIA = _CLAVE_GRAFICO_SUBCATEGORIA
CLAVE_PROVEEDOR = _CLAVE_GRAFICO_PROVEEDOR
CLAVE_TABLA_COMPRAR = "inv_skus_tabla_comprar"
CLAVE_ROTACION = _CLAVE_ROTACION_DESEADA
CLAVE_DIAS = _CLAVE_DIAS_TRABAJO
CLAVE_VOZ_PENDIENTE = "inv_skus_voz_pendiente"
CLAVE_FILTRO_CODIGO = "inv_skus_filtro_codigo"  # SKU / artículo puntual (voz o UI)


def _norm_voz(texto: str) -> str:
    s = unicodedata.normalize("NFKD", str(texto or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(s.split())


# Sinónimos hablados → texto a buscar en catálogo (antes del match difuso).
_ALIAS_VOZ: dict[str, str] = {
    "fleming": "flemming",
    "flemin": "flemming",
    "hyde": "hide",
    "malone and hyde": "malone hide",
    "malone and hide": "malone hide",
    "malone hyde": "malone hide",
    "costela": "cosntela",
    "constela": "cosntela",
    "distribuidora rs": "distrbuidora rs",
    "distribuidora": "distrbuidora rs",
}


def _aplicar_alias_voz(consulta: str) -> str:
    q = _norm_voz(consulta)
    # Más largos primero («malone and hyde» antes que «hyde»).
    for origen, destino in sorted(_ALIAS_VOZ.items(), key=lambda kv: len(kv[0]), reverse=True):
        if origen in q:
            q = q.replace(origen, destino)
    return q


def _mejor_coincidencia(consulta: str, opciones: list[str]) -> str | None:
    """Match exacto, por contención o parecido (difflib)."""
    from difflib import SequenceMatcher

    q = _aplicar_alias_voz(consulta)
    if not q or not opciones:
        return None
    norms = {op: _norm_voz(op) for op in opciones}

    def _clave_match(op: str) -> str:
        """Para «Cat · Sub», prioriza la subcategoría al comparar."""
        n = norms[op]
        if " " in n and "·" in str(op):
            # Usa solo el tramo después del separador visual
            partes = str(op).split(" · ", 1)
            if len(partes) == 2:
                return _norm_voz(partes[1])
        return n

    claves = {op: _clave_match(op) for op in opciones}

    for op, n in claves.items():
        if n == q:
            return op
    hits = [op for op, n in claves.items() if q in n or n in q]
    if not hits:
        for op, n in claves.items():
            toks = [t for t in n.split() if len(t) > 2]
            if toks and all(t in q for t in toks):
                hits.append(op)
    if hits:
        return sorted(hits, key=lambda o: len(claves[o]), reverse=True)[0]

    # Parecido: «Fleming» ≈ «Flemming», «harinas» ≈ «Harinas y Pastas», etc.
    mejores: list[tuple[float, str]] = []
    for op, n in claves.items():
        ratio = SequenceMatcher(None, q, n).ratio()
        for tok in n.split():
            if len(tok) >= 4:
                ratio = max(ratio, SequenceMatcher(None, q, tok).ratio())
                for qt in q.split():
                    if len(qt) >= 4:
                        ratio = max(ratio, SequenceMatcher(None, qt, tok).ratio())
        if ratio >= 0.72:
            mejores.append((ratio, op))
    if not mejores:
        return None
    mejores.sort(key=lambda x: (x[0], len(claves[x[1]])), reverse=True)
    return mejores[0][1]


def parsear_comando_voz_compra(
    texto: str, tabla: pd.DataFrame
) -> dict[str, str] | None:
    """Interpreta categoría / subcategoría / proveedor / SKU (código o descripción).

    Ejemplos:
      - «categoría alimentos»
      - «subcategoría harinas»
      - «proveedor Fleming»
      - «SKU 46-020023» / «artículo harina dura»
      - «quiero ver lo de Fleming»
    """
    if tabla is None or tabla.empty or not str(texto or "").strip():
        return None
    t = _norm_voz(texto)

    cats = (
        sorted({str(c) for c in tabla["categoria"].dropna().unique()})
        if "categoria" in tabla.columns
        else []
    )
    subs_opts: list[str] = []
    if "subcategoria" in tabla.columns:
        if "categoria" in tabla.columns:
            pares = (
                tabla.loc[:, ["categoria", "subcategoria"]]
                .dropna()
                .astype(str)
                .drop_duplicates()
            )
            subs_opts = [
                f"{r.categoria} · {r.subcategoria}"
                for r in pares.itertuples(index=False)
            ]
        else:
            subs_opts = sorted(
                {str(s) for s in tabla["subcategoria"].dropna().unique()}
            )
    provs = (
        sorted({str(p) for p in tabla["proveedor"].dropna().unique()})
        if "proveedor" in tabla.columns
        else []
    )
    codigos = (
        sorted({str(c) for c in tabla["codigo"].dropna().unique()})
        if "codigo" in tabla.columns
        else []
    )
    # Etiquetas para match por descripción: «CODIGO · descripción»
    sku_labels: list[str] = []
    if "codigo" in tabla.columns and "descripcion" in tabla.columns:
        for r in tabla.loc[:, ["codigo", "descripcion"]].dropna().itertuples(index=False):
            sku_labels.append(f"{r.codigo} · {r.descripcion}")
    elif codigos:
        sku_labels = list(codigos)

    def _resultado_sku(codigo: str) -> dict[str, str]:
        return {
            "nivel": "SKU",
            "valor": str(codigo),
            "campo": CLAVE_FILTRO_CODIGO,
        }

    # Prefijo SKU / artículo / producto / código
    m = re.search(
        r"(?:sku|skus|articulo|articulos|producto|productos|codigo|item|items)\s+(.+)$",
        t,
    )
    if m:
        consulta = m.group(1).strip()
        # Código exacto / contenido
        for c in sorted(codigos, key=len, reverse=True):
            cn = _norm_voz(c)
            if cn and (cn == consulta or cn in consulta or consulta in cn):
                return _resultado_sku(c)
        hit = _mejor_coincidencia(consulta, sku_labels)
        if hit:
            codigo = hit.split(" · ", 1)[0].strip() if " · " in hit else hit
            return _resultado_sku(codigo)

    # Prefijos explícitos (subcategoría ANTES que categoría: «categoria» ⊆ «subcategoria»).
    m = re.search(
        r"(?:subcategor[ií]a|subcategoria)\s+(.+)$", t
    )
    if m:
        consulta_sub = m.group(1)
        hit = _mejor_coincidencia(consulta_sub, subs_opts)
        if hit:
            return {
                "nivel": "Subcategoría",
                "valor": hit,
                "campo": CLAVE_SUBCATEGORIA,
            }
        hit = _mejor_coincidencia(consulta_sub, cats)
        if hit:
            return {"nivel": "Categoría", "valor": hit, "campo": CLAVE_CATEGORIA}

    m = re.search(
        r"(?<!sub)(?:categor[ií]a|categoria)\s+(.+)$", t
    )
    if m:
        hit = _mejor_coincidencia(m.group(1), cats)
        if hit:
            return {"nivel": "Categoría", "valor": hit, "campo": CLAVE_CATEGORIA}

    m = re.search(
        r"(?:del\s+proveedor|proveedor)\s+(.+)$", t
    )
    if m:
        hit = _mejor_coincidencia(m.group(1), provs)
        if hit:
            return {"nivel": "Proveedor", "valor": hit, "campo": CLAVE_PROVEEDOR}
        hit = _mejor_coincidencia(m.group(1), cats)
        if hit:
            return {"nivel": "Categoría", "valor": hit, "campo": CLAVE_CATEGORIA}

    if any(
        k in t
        for k in (
            "todos los skus",
            "todas las categorias",
            "lista completa",
            "sin filtro",
            "ver todos",
            "mostrar todos",
        )
    ):
        return {"nivel": "SKU", "valor": "", "campo": CLAVE_FILTRO_CODIGO}

    # «a comprar a Fleming», «comprar de Cosntela», etc.
    m = re.search(
        r"(?:a\s+comprar\s+(?:a|de|del)|comprar\s+(?:a|de|del)|del\s+proveedor)\s+(.+)$",
        t,
    )
    if m:
        hit = _mejor_coincidencia(m.group(1), provs)
        if hit:
            return {"nivel": "Proveedor", "valor": hit, "campo": CLAVE_PROVEEDOR}

    # Abarrotes (y similares) → categoría Alimentos si existe
    if "abarrotes" in t or "abarrote" in t:
        for c in cats:
            if _norm_voz(c) == "alimentos":
                return {
                    "nivel": "Categoría",
                    "valor": c,
                    "campo": CLAVE_CATEGORIA,
                }

    # Código embebido en la frase (p. ej. «46 020023» o «46-020023»)
    m = re.search(r"\b(\d{2}\s*\d{5,6})\b", t)
    if m and codigos:
        bruto = re.sub(r"\s+", "", m.group(1))
        # Normaliza a forma con guion si existe en catálogo
        for c in codigos:
            cn = re.sub(r"[^0-9]", "", str(c))
            if cn == bruto or _norm_voz(c).replace(" ", "") == bruto:
                return _resultado_sku(c)

    # Sin prefijo: proveedor → categoría → subcategoría → SKU (descripción)
    hit = _mejor_coincidencia(t, provs)
    if hit:
        return {"nivel": "Proveedor", "valor": hit, "campo": CLAVE_PROVEEDOR}
    for p in sorted(provs, key=lambda x: len(_norm_voz(x)), reverse=True):
        pn = _norm_voz(p)
        if len(pn) >= 3 and (t.endswith(pn) or f" {pn}" in f" {t}"):
            return {"nivel": "Proveedor", "valor": p, "campo": CLAVE_PROVEEDOR}
    hit = _mejor_coincidencia(t, cats)
    if hit:
        return {"nivel": "Categoría", "valor": hit, "campo": CLAVE_CATEGORIA}
    hit = _mejor_coincidencia(t, subs_opts)
    if hit:
        return {
            "nivel": "Subcategoría",
            "valor": hit,
            "campo": CLAVE_SUBCATEGORIA,
        }
    # Match por descripción de artículo (tokens significativos)
    hit = _mejor_coincidencia(t, sku_labels)
    if hit and " · " in hit:
        # Evita falsos positivos demasiado genéricos
        desc = _norm_voz(hit.split(" · ", 1)[1])
        toks = [x for x in desc.split() if len(x) >= 4]
        if toks and any(tok in t for tok in toks):
            return _resultado_sku(hit.split(" · ", 1)[0].strip())
    for p in sorted(provs, key=lambda x: len(_norm_voz(x)), reverse=True):
        pn = _norm_voz(p)
        if len(pn) >= 3 and pn in t:
            return {"nivel": "Proveedor", "valor": p, "campo": CLAVE_PROVEEDOR}
    for c in sorted(cats, key=lambda x: len(_norm_voz(x)), reverse=True):
        cn = _norm_voz(c)
        if len(cn) >= 3 and cn in t:
            return {"nivel": "Categoría", "valor": c, "campo": CLAVE_CATEGORIA}
    return None


def aplicar_filtro_voz_en_sesion(resultado: dict[str, str]) -> None:
    """Guarda filtro de voz para aplicarlo ANTES de crear los widgets (próximo rerun)."""
    # Limpia filtro de SKU puntual si el nuevo alcance no es un código.
    if resultado.get("campo") != CLAVE_FILTRO_CODIGO:
        st.session_state.pop(CLAVE_FILTRO_CODIGO, None)
    st.session_state[CLAVE_VOZ_PENDIENTE] = {
        "nivel": resultado.get("nivel") or "SKU",
        "campo": resultado.get("campo") or "",
        "valor": resultado.get("valor") or "",
    }


def _aplicar_filtro_voz_pendiente() -> None:
    """Inyecta nivel/valor de voz en session_state justo antes del radio/selectbox."""
    pending = st.session_state.pop(CLAVE_VOZ_PENDIENTE, None)
    if not pending or not isinstance(pending, dict):
        return
    nivel = pending.get("nivel") or "SKU"
    st.session_state[CLAVE_NIVEL] = nivel
    campo = pending.get("campo") or ""
    valor = pending.get("valor") or ""
    if campo == CLAVE_FILTRO_CODIGO:
        if valor:
            st.session_state[CLAVE_FILTRO_CODIGO] = valor
        else:
            st.session_state.pop(CLAVE_FILTRO_CODIGO, None)
    elif campo and valor:
        st.session_state[campo] = valor
        st.session_state.pop(CLAVE_FILTRO_CODIGO, None)


def filtrar_tabla_compra_por_nivel(
    tabla: pd.DataFrame, nivel: str, valor: str
) -> tuple[pd.DataFrame, str]:
    """Filtra sin widgets (para voz / ChatGPT)."""
    if tabla is None or tabla.empty:
        return tabla.copy() if tabla is not None else pd.DataFrame(), "Sin datos"
    if nivel == "Categoría" and valor and "categoria" in tabla.columns:
        out = tabla.loc[tabla["categoria"].astype(str) == str(valor)].copy()
        return out, f"SKUs a comprar · {valor}"
    if nivel == "Subcategoría" and valor and "subcategoria" in tabla.columns:
        if " · " in valor and "categoria" in tabla.columns:
            cat, sub = valor.split(" · ", 1)
            out = tabla.loc[
                (tabla["categoria"].astype(str) == cat)
                & (tabla["subcategoria"].astype(str) == sub)
            ].copy()
        else:
            out = tabla.loc[tabla["subcategoria"].astype(str) == str(valor)].copy()
        return out, f"SKUs a comprar · {valor}"
    if nivel == "Proveedor" and valor and "proveedor" in tabla.columns:
        out = tabla.loc[tabla["proveedor"].astype(str) == str(valor)].copy()
        return out, f"SKUs a comprar · {valor}"
    if nivel == "SKU" and valor and "codigo" in tabla.columns:
        out = tabla.loc[tabla["codigo"].astype(str) == str(valor)].copy()
        if out.empty:
            # Fallback: descripción contenida
            if "descripcion" in tabla.columns:
                q = _norm_voz(valor)
                mask = tabla["descripcion"].astype(str).map(_norm_voz).str.contains(
                    re.escape(q), na=False
                )
                out = tabla.loc[mask].copy()
        etiqueta = str(valor)
        if not out.empty and "descripcion" in out.columns:
            etiqueta = f"{out.iloc[0]['codigo']} · {out.iloc[0]['descripcion']}"
        return out, f"SKUs a comprar · {etiqueta}"
    return tabla.copy(), "SKUs a comprar (todos)"


# Degradado azul estilo Profile / GMROI (barras delgadas).
_AZUL_STOPS = (
    (0.0, "#93c5fd"),
    (0.35, "#3b82f6"),
    (0.7, "#1d4ed8"),
    (1.0, "#1e3a8a"),
)


def _interp_hex(c0: str, c1: str, t: float) -> str:
    def _rgb(h: str) -> tuple[int, int, int]:
        h = h.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    r0, g0, b0 = _rgb(c0)
    r1, g1, b1 = _rgb(c1)
    r = int(r0 + (r1 - r0) * t)
    g = int(g0 + (g1 - g0) * t)
    b = int(b0 + (b1 - b0) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _colores_azul_barras(n: int) -> list[str]:
    if n <= 0:
        return []
    if n == 1:
        return [_AZUL_STOPS[0][1]]
    out: list[str] = []
    for i in range(n):
        t = i / (n - 1)
        for j in range(len(_AZUL_STOPS) - 1):
            t0, c0 = _AZUL_STOPS[j]
            t1, c1 = _AZUL_STOPS[j + 1]
            if t0 <= t <= t1:
                local = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
                out.append(_interp_hex(c0, c1, local))
                break
        else:
            out.append(_AZUL_STOPS[-1][1])
    return out


def _angulo_etiquetas_x_skus(n: int, max_label_len: int) -> int:
    """Vertical si hay muchos códigos o etiquetas largas (estilo Profile)."""
    if n > 6 or max_label_len > 12:
        return -90
    if n > 4:
        return -45
    return 0


def _bargap_delgado(n: int) -> float:
    """bargap alto = barras más delgadas (Profile / GMROI)."""
    if n > 30:
        return 0.72
    if n > 15:
        return 0.55
    if n > 8:
        return 0.42
    return 0.32


def _ancho_figura_barras(n: int) -> int:
    if n <= 8:
        px = 52
    elif n <= 20:
        px = 34
    elif n <= 50:
        px = 24
    else:
        px = 18
    return max(640, int(n * px + 120))


def _font_ejes_px() -> int:
    """Mismo control del sidebar: «Tamaño letras ejes X e Y»."""
    return int(st.session_state.get("inv_gmroi_font_ejes", 14))


def _font_barras_px() -> int:
    """Mismo control del sidebar: «Tamaño números en barras»."""
    return int(st.session_state.get("inv_gmroi_font_barras", 10))


def _etiquetas_sku(tabla: pd.DataFrame) -> pd.Series:
    codigo = (
        tabla["codigo"].astype(str)
        if "codigo" in tabla.columns
        else pd.Series(tabla.index.astype(str), index=tabla.index)
    )
    if "descripcion" in tabla.columns:
        desc = tabla["descripcion"].astype(str).str.slice(0, 28)
        return codigo + " · " + desc
    return codigo


def _datos_grafico_skus(
    tabla: pd.DataFrame,
    *,
    mayor_a_menor: bool = True,
    completo: bool = True,
    top_n: int = 15,
) -> pd.DataFrame:
    """Barras por SKU; orden y recorte (completo / parcial)."""
    if tabla.empty or COL_CANTIDAD_COMPRAR not in tabla.columns:
        return pd.DataFrame(columns=["etiqueta", COL_CANTIDAD_COMPRAR])
    out = tabla.copy()
    out["etiqueta"] = _etiquetas_sku(out)
    out[COL_CANTIDAD_COMPRAR] = pd.to_numeric(
        out[COL_CANTIDAD_COMPRAR], errors="coerce"
    ).fillna(0)
    out = out.sort_values(
        COL_CANTIDAD_COMPRAR,
        ascending=not mayor_a_menor,
        na_position="last",
    )
    if not completo:
        n = max(1, int(top_n))
        out = out.head(n)
    return out.loc[:, ["etiqueta", COL_CANTIDAD_COMPRAR]].reset_index(drop=True)


def _selectbox_compacto(
    label: str,
    opciones: list[str],
    clave: str,
    *,
    help_txt: str,
) -> str:
    """Selectbox ~1/3 del ancho (no ocupa toda la fila)."""
    if clave not in st.session_state or st.session_state[clave] not in opciones:
        st.session_state[clave] = opciones[0]
    col, _ = st.columns([1, 2])
    with col:
        return st.selectbox(
            label,
            options=opciones,
            key=clave,
            help=help_txt,
        )


def _filtrar_tabla_grafico(tabla: pd.DataFrame, nivel: str) -> tuple[pd.DataFrame, str]:
    """Filtra SKUs por categoría, subcategoría, proveedor o artículo (código)."""
    if nivel == "SKU" and "codigo" in tabla.columns:
        # Opciones de artículo: todos + cada SKU
        filas = tabla.loc[:, [c for c in ("codigo", "descripcion") if c in tabla.columns]].copy()
        filas["codigo"] = filas["codigo"].astype(str)
        opciones = ["(Todos los SKUs)"]
        mapa: dict[str, str] = {"(Todos los SKUs)": ""}
        for r in filas.drop_duplicates("codigo").itertuples(index=False):
            cod = str(r.codigo)
            desc = str(getattr(r, "descripcion", "") or "")[:40]
            label = f"{cod} · {desc}" if desc else cod
            opciones.append(label)
            mapa[label] = cod
        # Si voz dejó un código, preseleccionarlo
        codigo_voz = st.session_state.get(CLAVE_FILTRO_CODIGO) or ""
        if codigo_voz:
            for lab, cod in mapa.items():
                if cod == str(codigo_voz):
                    st.session_state[_CLAVE_GRAFICO_SKU_ITEM] = lab
                    break
        if _CLAVE_GRAFICO_SKU_ITEM not in st.session_state or (
            st.session_state.get(_CLAVE_GRAFICO_SKU_ITEM) not in opciones
        ):
            st.session_state[_CLAVE_GRAFICO_SKU_ITEM] = opciones[0]
        elegido = _selectbox_compacto(
            "Artículo / SKU",
            opciones,
            _CLAVE_GRAFICO_SKU_ITEM,
            help_txt="Elija un SKU concreto o «Todos los SKUs».",
        )
        cod = mapa.get(elegido, "")
        st.session_state[CLAVE_FILTRO_CODIGO] = cod or None
        if not cod:
            return tabla.copy(), "SKUs a comprar (todos)"
        filtrada = tabla.loc[tabla["codigo"].astype(str) == cod].copy()
        return filtrada, f"SKUs a comprar · {elegido}"

    if nivel == "Categoría" and "categoria" in tabla.columns:
        cats = sorted(
            {str(c) for c in tabla["categoria"].dropna().unique()},
            key=str.lower,
        )
        if not cats:
            return tabla.iloc[0:0].copy(), "Sin categorías"
        elegido = _selectbox_compacto(
            "Categoría",
            cats,
            _CLAVE_GRAFICO_CATEGORIA,
            help_txt="Muestra solo los SKUs a comprar de esta categoría.",
        )
        filtrada = tabla.loc[tabla["categoria"].astype(str) == str(elegido)].copy()
        return filtrada, f"SKUs a comprar · {elegido}"

    if nivel == "Subcategoría" and "subcategoria" in tabla.columns:
        if "categoria" in tabla.columns:
            pares = (
                tabla.loc[:, ["categoria", "subcategoria"]]
                .dropna()
                .astype(str)
                .drop_duplicates()
                .sort_values(["categoria", "subcategoria"])
            )
            opciones = [
                f"{r.categoria} · {r.subcategoria}" for r in pares.itertuples(index=False)
            ]
            mapa = {
                f"{r.categoria} · {r.subcategoria}": (
                    str(r.categoria),
                    str(r.subcategoria),
                )
                for r in pares.itertuples(index=False)
            }
        else:
            subs = sorted(
                {str(s) for s in tabla["subcategoria"].dropna().unique()},
                key=str.lower,
            )
            opciones = subs
            mapa = {s: (None, s) for s in subs}

        if not opciones:
            return tabla.iloc[0:0].copy(), "Sin subcategorías"
        elegido = _selectbox_compacto(
            "Subcategoría",
            opciones,
            _CLAVE_GRAFICO_SUBCATEGORIA,
            help_txt="Muestra solo los SKUs a comprar de esta subcategoría.",
        )
        cat, sub = mapa[elegido]
        if cat is None:
            filtrada = tabla.loc[tabla["subcategoria"].astype(str) == sub].copy()
        else:
            filtrada = tabla.loc[
                (tabla["categoria"].astype(str) == cat)
                & (tabla["subcategoria"].astype(str) == sub)
            ].copy()
        return filtrada, f"SKUs a comprar · {elegido}"

    if nivel == "Proveedor" and "proveedor" in tabla.columns:
        provs = sorted(
            {str(p) for p in tabla["proveedor"].dropna().unique()},
            key=str.lower,
        )
        if not provs:
            return tabla.iloc[0:0].copy(), "Sin proveedores"
        elegido = _selectbox_compacto(
            "Proveedor",
            provs,
            _CLAVE_GRAFICO_PROVEEDOR,
            help_txt="Muestra solo los SKUs a comprar de este proveedor.",
        )
        filtrada = tabla.loc[tabla["proveedor"].astype(str) == str(elegido)].copy()
        return filtrada, f"SKUs a comprar · {elegido}"

    if nivel == "Proveedor" and "proveedor" not in tabla.columns:
        st.warning("No hay columna `proveedor` en los datos.")
        return tabla.iloc[0:0].copy(), "Sin proveedor"

    return tabla.copy(), "SKUs a comprar (todos)"


def _controles_filtro_vista_comprar(tabla: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Radio + menú: filtra tabla y gráfico por SKU / categoría / subcategoría / proveedor."""
    # Voz: aplicar ANTES de instanciar widgets (si no, Streamlit ignora el cambio).
    _aplicar_filtro_voz_pendiente()
    st.markdown("##### Vista de compras")
    nivel = st.radio(
        "Ver por",
        options=list(_NIVELES_GRAFICO),
        horizontal=True,
        key=_CLAVE_GRAFICO_NIVEL,
        help=(
            "SKU: elige un artículo concreto o todos. "
            "Categoría / Subcategoría / Proveedor: filtra y ChatGPT lista cada SKU."
        ),
    )
    return _filtrar_tabla_grafico(tabla, nivel)


def _grafico_cantidad_a_comprar(
    tabla: pd.DataFrame,
    *,
    titulo_base: str = "SKUs a comprar",
) -> None:
    """Barras verticales estilo Profile sobre la selección ya filtrada."""
    st.markdown("#### Gráfico · cantidad a comprar")
    n_disponibles = len(tabla)
    if n_disponibles == 0:
        st.info("No hay SKUs a comprar para esta selección.")
        return

    c1, c2, c3 = st.columns([1.2, 1.4, 1.2])
    with c1:
        mayor_a_menor = st.checkbox(
            "Mayor a menor",
            value=True,
            key=_CLAVE_GRAFICO_MAYOR_MENOR,
            help="Marcado: de mayor a menor cantidad. Desmarcado: de menor a mayor.",
        )
    with c2:
        completo = st.checkbox(
            "Ver gráfico completo",
            value=True,
            key=_CLAVE_GRAFICO_COMPLETO,
            help="Marcado: todos los SKUs de la selección. Desmarcado: solo Top N.",
        )
    with c3:
        scroll_completo = st.checkbox(
            "Todo en pantalla (sin scroll)",
            value=False,
            key=_CLAVE_GRAFICO_SCROLL_COMPLETO,
            help=(
                "Marcado: comprime todas las barras al ancho visible. "
                "Desmarcado: scroll horizontal con barras más legibles (estilo Profile)."
            ),
        )

    top_n = 15
    if not completo:
        if _CLAVE_GRAFICO_TOP_N not in st.session_state:
            st.session_state[_CLAVE_GRAFICO_TOP_N] = min(15, n_disponibles)
        else:
            st.session_state[_CLAVE_GRAFICO_TOP_N] = min(
                int(st.session_state[_CLAVE_GRAFICO_TOP_N]),
                n_disponibles,
            )
        top_n = int(
            st.number_input(
                "Top N (gráfico parcial)",
                min_value=1,
                max_value=max(1, n_disponibles),
                step=1,
                key=_CLAVE_GRAFICO_TOP_N,
            )
        )

    font_ejes = _font_ejes_px()
    font_barras = _font_barras_px()

    datos = _datos_grafico_skus(
        tabla,
        mayor_a_menor=mayor_a_menor,
        completo=completo,
        top_n=top_n,
    )
    if datos.empty:
        st.info("No hay SKUs a comprar para esta selección.")
        return

    n_bars = len(datos)
    xs = datos["etiqueta"].astype(str)
    ys = datos[COL_CANTIDAD_COMPRAR].astype(float)
    colores = _colores_azul_barras(n_bars)
    max_len = int(xs.str.len().max()) if len(xs) else 0
    angulo_x = _angulo_etiquetas_x_skus(n_bars, max_len)
    bargap = _bargap_delgado(n_bars)
    y_max = float(ys.max()) if len(ys) else 1.0
    y_hi = max(y_max * 1.28, 1.0)

    titulo = titulo_base
    if not completo:
        titulo += f" · top {n_bars}"
    titulo += " · mayor→menor" if mayor_a_menor else " · menor→mayor"

    fig = go.Figure(
        go.Bar(
            x=xs,
            y=ys,
            marker=dict(color=colores, cornerradius=4, line=dict(width=0)),
            text=ys,
            texttemplate="%{y:,.1f}",
            textposition="outside",
            textangle=-90 if n_bars > 20 else 0,
            textfont=dict(color="#e2e8f0", size=font_barras),
            cliponaxis=False,
            hovertemplate="<b>%{x}</b><br>Cantidad: %{y:,.2f}<extra></extra>",
            name="Cantidad a comprar",
        )
    )

    margen_b = 150 if angulo_x == -90 else 110 if angulo_x == -45 else 72
    layout_kw: dict[str, Any] = dict(
        title=dict(
            text=titulo,
            font=dict(size=max(13, font_ejes), color="#f8fafc"),
            x=0,
            xanchor="left",
        ),
        height=max(480, min(860, 460 + n_bars * 5)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0f1419",
        bargap=bargap,
        showlegend=False,
        margin=dict(l=56, r=28, t=56, b=margen_b),
        xaxis=dict(
            type="category",
            title="",
            tickangle=angulo_x,
            tickfont=dict(color="#e2e8f0", size=font_ejes),
            categoryorder="array",
            categoryarray=xs.tolist(),
            automargin=True,
        ),
        yaxis=dict(
            title=dict(
                text="Cantidad a comprar",
                font=dict(size=font_ejes, color="#e2e8f0"),
            ),
            tickfont=dict(color="#e2e8f0", size=font_ejes),
            gridcolor="#1e293b",
            range=[0.0, y_hi],
            zeroline=True,
            zerolinecolor="#334155",
        ),
    )
    if scroll_completo:
        layout_kw["autosize"] = True
    else:
        layout_kw["width"] = _ancho_figura_barras(n_bars)
        layout_kw["autosize"] = False

    fig.update_layout(**layout_kw)
    st.plotly_chart(
        fig,
        use_container_width=scroll_completo,
        config={"scrollZoom": True, "displayModeBar": True},
    )
    st.caption(
        f"{n_bars} SKU(s) de {n_disponibles} · total graficado: "
        f"**{float(ys.sum()):,.1f}** · etiquetas X a "
        f"{'vertical' if angulo_x == -90 else 'inclinado' if angulo_x else 'horizontal'} · "
        "tipografía: **Ajustes de interfaz** (ejes X/Y y números en barras)"
    )


def render(df: pd.DataFrame, params: dict[str, Any]) -> None:
    """Pantalla principal de la decisión «SKUs a comprar»."""
    del params
    st.markdown("### SKUs a comprar")
    st.caption(
        "Fórmula: **cantidad a comprar** = "
        "(`pronostico ajustado` × 12 ÷ rotación) − `cantidad minima de inventario`, "
        "solo si `inventario final bulto` < mínimo."
    )

    faltan = [
        c
        for c in ("pronostico ajustado", COL_INVENTARIO_FINAL)
        if c not in df.columns
    ]
    # SS / TR necesitan estas columnas si aún no están calculadas.
    if "pronostico" not in df.columns:
        faltan.append("pronostico")
    if "tiempo entrega" not in df.columns:
        faltan.append("tiempo entrega")
    faltan = list(dict.fromkeys(faltan))
    if faltan:
        st.error(
            "Faltan columnas en el Excel: "
            + ", ".join(f"`{c}`" for c in faltan)
        )
        return

    # ~1/3 del ancho; aspecto compacto.
    col_rot, _ = st.columns([1, 2])
    with col_rot:
        rot = st.slider(
            "Rotación deseada",
            min_value=_ROTACION_DESEADA_MIN,
            max_value=_ROTACION_DESEADA_MAX,
            value=_rotacion_deseada(),
            step=1,
            key=_CLAVE_ROTACION_DESEADA,
            help=(
                "Rotación de inventario que quiere la compañía (veces al año). "
                "Default 4 (= 3 meses de inventario máximo)."
            ),
        )
        meses = 12 / max(rot, 1)
        st.caption(f"**{rot}**× / año · ≈ **{meses:.1f}** meses máx.")

    dias = _dias_trabajo_mes()
    bajo = mascara_bajo_minimo(df, dias)
    qty = calcular_cantidad_a_comprar(df, rot, dias)
    a_comprar = bajo & (qty > 0)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SKUs en el Excel", f"{_n_skus(df):,}")
    c2.metric("Bajo mínimo", f"{int(bajo.sum()):,}")
    c3.metric("A comprar", f"{int(a_comprar.sum()):,}")
    c4.metric(
        "Suma a comprar",
        f"{float(qty.sum()):,.1f}" if qty.notna().any() else "—",
    )

    if st.button(
        "Calcular y guardar cantidad a comprar en la sesión",
        type="primary",
        use_container_width=True,
        key="inv_btn_guardar_cantidad_comprar",
        help="Guarda mínimo (si falta) y cantidad a comprar en Base de datos.",
    ):
        st.session_state["inv_df_datos"] = aplicar_cantidad_a_comprar_en_sesion(
            df, rot, dias
        )
        st.success(
            "Columna **cantidad a comprar** aplicada "
            "(y mínimo / SS / TR si hacían falta)."
        )
        st.rerun()

    tabla = tabla_skus_a_comprar(df, rot, dias, solo_a_comprar=True)
    # Disponible para el micrófono del sidebar (filtro por voz).
    st.session_state[CLAVE_TABLA_COMPRAR] = tabla
    if tabla.empty:
        st.info("Ningún SKU está bajo el mínimo con la rotación actual.")
    else:
        filtrada, titulo_vista = _controles_filtro_vista_comprar(tabla)
        n_total = len(tabla)
        n_vista = len(filtrada)
        if n_vista == 0:
            st.info(f"No hay SKUs a comprar para «{titulo_vista}».")
        else:
            st.caption(
                f"**{titulo_vista}** · mostrando **{n_vista:,}** de "
                f"**{n_total:,}** SKUs a comprar."
            )
            _mostrar_tabla_final_comprar(filtrada)
            _grafico_cantidad_a_comprar(filtrada, titulo_base=titulo_vista)
            # Contexto para el micrófono del sidebar (requerimiento + audio).
            try:
                hechos = analisis_chatgpt.hechos_requerimiento_compra(
                    filtrada,
                    titulo_vista=titulo_vista,
                    rotacion=rot,
                    dias_trabajo=dias,
                    col_cantidad=COL_CANTIDAD_COMPRAR,
                )
                import json as _json

                st.session_state["inv_skus_req_ctx"] = {
                    "titulo": titulo_vista,
                    "hechos": hechos,
                    "fingerprint": _json.dumps(
                        hechos, ensure_ascii=False, sort_keys=True
                    ),
                    "rotacion": rot,
                    "dias": dias,
                }
            except Exception:
                st.session_state.pop("inv_skus_req_ctx", None)
            st.divider()
            analisis_chatgpt.render_panel_requerimiento_compra(
                filtrada,
                titulo_vista=titulo_vista,
                rotacion=rot,
                dias_trabajo=dias,
                col_cantidad=COL_CANTIDAD_COMPRAR,
            )


def render_stock_seguridad(df: pd.DataFrame, params: dict[str, Any]) -> None:
    """Herramienta: calcula la columna ``stock de seguridad``."""
    del params
    st.markdown("### Stock de seguridad")
    st.caption(
        "Fórmula: **stock de seguridad** = "
        "`pronostico ajustado` − `pronostico`."
    )

    faltan = [
        c for c in ("pronostico", "pronostico ajustado") if c not in df.columns
    ]
    if faltan:
        st.error(
            "Faltan columnas en el Excel para calcular: "
            + ", ".join(f"`{c}`" for c in faltan)
        )
        return

    tabla = tabla_stock_seguridad(df)
    ss = tabla[COL_STOCK_SEGURIDAD]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SKUs", f"{_n_skus(df):,}")
    c2.metric("Con stock calculado", f"{int(ss.notna().sum()):,}")
    c3.metric("Promedio SS", f"{float(ss.mean()):,.2f}" if ss.notna().any() else "—")
    c4.metric("Máximo SS", f"{float(ss.max()):,.2f}" if ss.notna().any() else "—")

    if st.button(
        "Calcular y guardar columna en la sesión",
        type="primary",
        use_container_width=True,
        help="Agrega / actualiza la columna «stock de seguridad» en Base de datos.",
    ):
        st.session_state["inv_df_datos"] = aplicar_stock_seguridad_en_sesion(df)
        st.success("Columna **stock de seguridad** aplicada. Ya aparece en Base de datos.")
        st.rerun()

    if COL_STOCK_SEGURIDAD in df.columns:
        st.caption("La sesión ya tiene la columna `stock de seguridad`.")

    _dataframe_misma_foto(tabla)


def render_demanda_tiempo_entrega(df: pd.DataFrame, params: dict[str, Any]) -> None:
    """Herramienta: demanda durante el lead time (TR)."""
    del params
    st.markdown("### Demanda en el tiempo de entrega")
    st.caption(
        "Fórmula: **demanda diaria** = `pronostico` ÷ días de trabajo · "
        "**demanda en el tiempo de entrega** = demanda diaria × `tiempo entrega`."
    )

    faltan = [c for c in ("pronostico", "tiempo entrega") if c not in df.columns]
    if faltan:
        st.error(
            "Faltan columnas en el Excel para calcular: "
            + ", ".join(f"`{c}`" for c in faltan)
        )
        return

    dias = st.slider(
        "Días de trabajo del mes (empresa)",
        min_value=_DIAS_TRABAJO_MIN,
        max_value=_DIAS_TRABAJO_MAX,
        value=_dias_trabajo_mes(),
        step=1,
        key=_CLAVE_DIAS_TRABAJO,
        help=(
            "Por defecto 30. Si la empresa trabaja menos días (p. ej. 26), "
            "el pronóstico se divide entre ese número."
        ),
    )

    tabla = tabla_demanda_tiempo_entrega(df, dias)
    dtr = tabla[COL_DEMANDA_TR]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SKUs", f"{_n_skus(df):,}")
    c2.metric("Días de trabajo", f"{dias}")
    c3.metric(
        "Promedio demanda TR",
        f"{float(dtr.mean()):,.2f}" if dtr.notna().any() else "—",
    )
    c4.metric(
        "Máximo demanda TR",
        f"{float(dtr.max()):,.2f}" if dtr.notna().any() else "—",
    )

    if st.button(
        "Calcular y guardar columna en la sesión",
        type="primary",
        use_container_width=True,
        key="inv_btn_guardar_demanda_tr",
        help=(
            "Agrega / actualiza «demanda diaria» y "
            "«demanda en el tiempo de entrega» en Base de datos."
        ),
    ):
        st.session_state["inv_df_datos"] = aplicar_demanda_tr_en_sesion(df, dias)
        st.success(
            "Columnas **demanda diaria** y **demanda en el tiempo de entrega** "
            "aplicadas. Ya aparecen en Base de datos."
        )
        st.rerun()

    if COL_DEMANDA_TR in df.columns:
        st.caption("La sesión ya tiene la columna `demanda en el tiempo de entrega`.")

    _dataframe_misma_foto(tabla)


def render_cantidad_minima(df: pd.DataFrame, params: dict[str, Any]) -> None:
    """Herramienta: cantidad mínima de inventario por SKU."""
    del params
    st.markdown("### Cantidad mínima por SKU")
    st.caption(
        "Fórmula: **cantidad minima de inventario** = "
        "`stock de seguridad` + `demanda en el tiempo de entrega`."
    )

    # Inputs mínimos para poder armar SS y demanda TR si aún no están en sesión.
    faltan_ss = [
        c for c in ("pronostico", "pronostico ajustado") if c not in df.columns
    ]
    faltan_tr = [c for c in ("pronostico", "tiempo entrega") if c not in df.columns]
    if faltan_ss or faltan_tr:
        faltan = list(dict.fromkeys([*faltan_ss, *faltan_tr]))
        st.error(
            "Faltan columnas en el Excel para calcular: "
            + ", ".join(f"`{c}`" for c in faltan)
        )
        return

    dias = _dias_trabajo_mes()
    tabla = tabla_cantidad_minima(df, dias)
    minimo = tabla[COL_CANTIDAD_MINIMA]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SKUs", f"{_n_skus(df):,}")
    c2.metric("Días trabajo (TR)", f"{dias}")
    c3.metric(
        "Promedio mínimo",
        f"{float(minimo.mean()):,.2f}" if minimo.notna().any() else "—",
    )
    c4.metric(
        "Máximo mínimo",
        f"{float(minimo.max()):,.2f}" if minimo.notna().any() else "—",
    )

    if st.button(
        "Calcular y guardar columna en la sesión",
        type="primary",
        use_container_width=True,
        key="inv_btn_guardar_cantidad_minima",
        help="Agrega / actualiza «cantidad minima de inventario» en Base de datos.",
    ):
        st.session_state["inv_df_datos"] = aplicar_cantidad_minima_en_sesion(df, dias)
        st.success(
            "Columna **cantidad minima de inventario** aplicada. "
            "Ya aparece en Base de datos."
        )
        st.rerun()

    if COL_CANTIDAD_MINIMA in df.columns:
        st.caption("La sesión ya tiene la columna `cantidad minima de inventario`.")

    _dataframe_misma_foto(tabla)
