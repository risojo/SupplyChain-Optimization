"""Cálculo de Scorecard (tablero financiero / ICC) — sin base de datos.

Réplica la lógica de ``utils/backend.py`` del proyecto original, con nombres
de columna alineados a Perfilado y parámetros en ``st.session_state``.
"""
from __future__ import annotations

import html
import json
import os

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import parametros

from ui_theme import (
    TABLA_FONT_SIZE_DEFAULT,
    altura_tabla_px,
    leyenda_scorecard_colores,
    leyenda_scorecard_columnas,
    mostrar_tabla_html,
    selectores_driver_lista,
)


_DIR_MODULO = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_DRIVERS_GUARDADO = os.path.join(_DIR_MODULO, "drivers_guardados.json")

TABLA_DRIVERS_ALMACEN = "Costos del almacén"
TABLA_DRIVERS_INVENTARIO = "Costos del inventario"


def _tabla_font_px() -> int:
    from ui_theme import font_campos_px

    return font_campos_px()

_MAPA_PIVOT = {
    "codigo": "count",
    "inventario promedio bultos": "sum",
    "bultos vendidos": "sum",
    "valor inventario promedio": "sum",
    "ventas totales": "sum",
    "margen bruto total": "sum",
    "cubicaje inventario": "sum",
    "ordenes anual": "sum",
}

_ETIQUETAS_PCT = [
    "% SKUs",
    "% inv prom/bult",
    "% bult vendidos",
    "% valor inv prom $",
    "% ventas totales",
    "% margen bruto",
    "% cub inv prom",
    "% ordenes anual",
]


def tabla_pivote_valores(df: pd.DataFrame, dimension: str) -> pd.DataFrame:
    pivote = pd.pivot_table(
        df,
        index=dimension,
        values=list(_MAPA_PIVOT.keys()),
        aggfunc=_MAPA_PIVOT,
        margins=True,
        margins_name="Total",
        sort=False,
    )
    pivote.columns = [f"{agg}({key})" for key, agg in _MAPA_PIVOT.items()]
    return pivote.sort_values(by=dimension).round(0)


def tabla_pivote_porcentajes(tabla_valores: pd.DataFrame) -> pd.DataFrame:
    df = tabla_valores.copy()
    df.columns = _ETIQUETAS_PCT
    if "Total" in df.index:
        df = df.drop("Total")
    pct = pd.DataFrame()
    for col in df.columns:
        pct[col] = df[col] / df[col].sum()
    pct = pct.T
    pct.index.name = "Driver"
    pct["Total"] = pct.sum(axis=1)
    return pct


def _drivers_por_defecto(n: int, percent_table: pd.DataFrame) -> list[str]:
    opciones = percent_table.index.tolist()
    if not opciones:
        return ["% ventas totales"] * n
    return [opciones[i % len(opciones)] for i in range(n)]


def scorecard_completo(
    percent_table: pd.DataFrame,
    table_name: str,
    inver_nombres: list[str],
    inver_valores: list[float],
    capital_cost_pct: float,
    cost_nombres: list[str],
    cost_valores: list[float],
) -> pd.DataFrame:
    df_all = pd.DataFrame()
    cols_categoria = [c for c in percent_table.columns if c != "Total"]

    for driver in percent_table.index.tolist():
        driver_dict = percent_table.loc[driver, cols_categoria].to_dict()

        df_inv = pd.DataFrame({table_name: inver_nombres, "Valor": inver_valores})
        for key, pct in driver_dict.items():
            df_inv[key] = df_inv["Valor"] * pct * (capital_cost_pct / 100)

        df_cost = pd.DataFrame({table_name: cost_nombres, "Valor": cost_valores})
        for key, pct in driver_dict.items():
            df_cost[key] = df_cost["Valor"] * pct

        bloque = pd.concat([df_inv, df_cost], ignore_index=True)
        bloque.insert(1, "Drivers", driver)
        bloque.drop("Valor", axis=1, inplace=True)
        bloque["Costo Totales"] = bloque[list(driver_dict.keys())].sum(axis=1)
        df_all = pd.concat([df_all, bloque], ignore_index=True)

    return df_all


def clave_drivers_sesion(table_name: str) -> str:
    return f"inv_sc_drv_{table_name}"


def _cargar_drivers_guardados() -> dict[str, dict[str, str]]:
    """Asignación persistida: tabla → {nombre cuenta: driver}."""
    if not os.path.isfile(ARCHIVO_DRIVERS_GUARDADO):
        return {}
    try:
        with open(ARCHIVO_DRIVERS_GUARDADO, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for tabla, mapa in data.items():
        if str(tabla).startswith("_") or not isinstance(mapa, dict):
            continue
        out[str(tabla)] = {
            str(cuenta): str(driver)
            for cuenta, driver in mapa.items()
            if isinstance(cuenta, str) and isinstance(driver, str)
        }
    return out


def _guardar_drivers_archivo(asignaciones: dict[str, dict[str, str]]) -> None:
    payload: dict[str, object] = {
        "_descripcion": (
            "Asignación driver por línea contable (almacén e inventario). "
            "Se carga al abrir la app; use «Grabar asignación» para actualizar."
        ),
        **asignaciones,
    }
    with open(ARCHIVO_DRIVERS_GUARDADO, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _drivers_desde_mapa(
    nombres: list[str],
    mapa: dict[str, str],
    percent_table: pd.DataFrame,
) -> list[str]:
    opciones = percent_table.index.tolist()
    defaults = _drivers_por_defecto(len(nombres), percent_table)
    drivers: list[str] = []
    for i, nombre in enumerate(nombres):
        elegido = mapa.get(nombre)
        if elegido in opciones:
            drivers.append(elegido)
        else:
            drivers.append(defaults[i])
    return drivers


def _drivers_en_sesion(
    table_name: str,
    nombres: list[str],
    percent_table: pd.DataFrame,
) -> list[str]:
    clave = clave_drivers_sesion(table_name)
    n_filas = len(nombres)
    if clave in st.session_state and len(st.session_state[clave]) == n_filas:
        return list(st.session_state[clave])

    guardado = _cargar_drivers_guardados()
    mapa = guardado.get(table_name, {})
    if mapa:
        drivers = _drivers_desde_mapa(nombres, mapa, percent_table)
    else:
        drivers = _drivers_por_defecto(n_filas, percent_table)
    st.session_state[clave] = drivers
    return drivers


def existe_asignacion_guardada() -> bool:
    return os.path.isfile(ARCHIVO_DRIVERS_GUARDADO)


CLAVE_EDITOR_ASIGNACION = "inv_asignacion_drivers_editor"
CLAVE_DF_ASIGNACION = "inv_asignacion_drivers_df"


def _estado_en_archivo(nombre: str, driver: str, mapa_archivo: dict[str, str]) -> str:
    if nombre not in mapa_archivo:
        return "— sin grabar"
    if mapa_archivo[nombre] == driver:
        return "✓ grabado"
    return "● cambio pendiente"


def construir_dataframe_asignacion(
    percent_table: pd.DataFrame,
    inv_alm_n: list[str],
    cost_alm_n: list[str],
    inv_inv_n: list[str],
    cost_inv_n: list[str],
) -> pd.DataFrame:
    """Tabla única almacén + inventario para el editor."""
    guardado = _cargar_drivers_guardados()
    filas: list[dict[str, str]] = []
    bloques = (
        ("Almacenaje", TABLA_DRIVERS_ALMACEN, inv_alm_n + cost_alm_n),
        ("Inventario", TABLA_DRIVERS_INVENTARIO, inv_inv_n + cost_inv_n),
    )
    for bloque, tabla, nombres in bloques:
        drivers = _drivers_en_sesion(tabla, nombres, percent_table)
        mapa = guardado.get(tabla, {})
        for nombre, driver in zip(nombres, drivers):
            filas.append({
                "Bloque": bloque,
                "Cuenta": nombre,
                "Driver": driver,
                "En archivo": _estado_en_archivo(nombre, driver, mapa),
            })
    return pd.DataFrame(filas)


def sincronizar_sesion_desde_asignacion(df: pd.DataFrame) -> None:
    """Actualiza listas de sesión usadas por el Scorecard."""
    if df.empty or "Bloque" not in df.columns:
        return
    alm = df[df["Bloque"] == "Almacenaje"]
    inv = df[df["Bloque"] == "Inventario"]
    if not alm.empty:
        st.session_state[clave_drivers_sesion(TABLA_DRIVERS_ALMACEN)] = [
            str(x) for x in alm["Driver"].tolist()
        ]
    if not inv.empty:
        st.session_state[clave_drivers_sesion(TABLA_DRIVERS_INVENTARIO)] = [
            str(x) for x in inv["Driver"].tolist()
        ]
    st.session_state[CLAVE_DF_ASIGNACION] = df.copy()


def _dataframe_asignacion_actual(
    percent_table: pd.DataFrame,
    inv_alm_n: list[str],
    cost_alm_n: list[str],
    inv_inv_n: list[str],
    cost_inv_n: list[str],
) -> pd.DataFrame:
    fp = (
        tuple(inv_alm_n + cost_alm_n),
        tuple(inv_inv_n + cost_inv_n),
    )
    esperadas = len(inv_alm_n) + len(cost_alm_n) + len(inv_inv_n) + len(cost_inv_n)
    prev_fp = st.session_state.get("inv_asignacion_fingerprint")
    df_prev = st.session_state.get(CLAVE_DF_ASIGNACION)
    if (
        prev_fp == fp
        and isinstance(df_prev, pd.DataFrame)
        and len(df_prev) == esperadas
    ):
        guardado = _cargar_drivers_guardados()
        df = df_prev.copy()
        for idx, row in df.iterrows():
            tabla = (
                TABLA_DRIVERS_ALMACEN
                if row["Bloque"] == "Almacenaje"
                else TABLA_DRIVERS_INVENTARIO
            )
            df.at[idx, "En archivo"] = _estado_en_archivo(
                str(row["Cuenta"]),
                str(row["Driver"]),
                guardado.get(tabla, {}),
            )
        return df
    st.session_state["inv_asignacion_fingerprint"] = fp
    return construir_dataframe_asignacion(
        percent_table, inv_alm_n, cost_alm_n, inv_inv_n, cost_inv_n
    )


def _clave_select_asignacion(indice: int) -> str:
    return f"inv_asig_drv_{indice}"


def _inicializar_selectores_asignacion(df: pd.DataFrame, opciones: list[str]) -> None:
    for i, row in df.iterrows():
        key = _clave_select_asignacion(int(i))
        drv = str(row["Driver"])
        if key not in st.session_state:
            st.session_state[key] = drv if drv in opciones else opciones[0]


def _dataframe_desde_selectores(
    df_base: pd.DataFrame,
    opciones: list[str],
) -> pd.DataFrame:
    filas: list[dict[str, str]] = []
    guardado = _cargar_drivers_guardados()
    for i, row in df_base.iterrows():
        key = _clave_select_asignacion(int(i))
        drv = st.session_state.get(key, row["Driver"])
        if not isinstance(drv, str) or drv not in opciones:
            drv = str(row["Driver"])
        bloque = str(row["Bloque"])
        cuenta = str(row["Cuenta"])
        tabla = (
            TABLA_DRIVERS_ALMACEN if bloque == "Almacenaje" else TABLA_DRIVERS_INVENTARIO
        )
        filas.append({
            "Bloque": bloque,
            "Cuenta": cuenta,
            "Driver": drv,
            "En archivo": _estado_en_archivo(cuenta, drv, guardado.get(tabla, {})),
        })
    return pd.DataFrame(filas)


def mostrar_asignacion_drivers_unificada(
    percent_table: pd.DataFrame,
    inv_alm_n: list[str],
    cost_alm_n: list[str],
    inv_inv_n: list[str],
    cost_inv_n: list[str],
) -> pd.DataFrame:
    """Un solo scroll: cuentas en un color, drivers asignados en otro."""
    from ui_theme import (
        ASIGNACION_DRIVERS_FONT_PX,
        ASIGNACION_LINEA_PALETA,
        PALETA_DRIVER_ASIGNACION,
        css_asignacion_drivers_scroll,
        css_selectores_asignacion_colores,
        leyenda_drivers_asignacion,
        mapa_colores_driver,
    )

    fs = ASIGNACION_DRIVERS_FONT_PX
    opciones = percent_table.index.tolist()
    mapa_drv = mapa_colores_driver(opciones)
    df_base = _dataframe_asignacion_actual(
        percent_table, inv_alm_n, cost_alm_n, inv_inv_n, cost_inv_n
    )
    _inicializar_selectores_asignacion(df_base, opciones)

    st.markdown(css_asignacion_drivers_scroll(fs), unsafe_allow_html=True)
    leyenda_drivers_asignacion(opciones, font_px=fs)

    st.markdown('<div class="inv-asig-scroll">', unsafe_allow_html=True)

    hdr = st.columns([0.52, 0.34, 0.14])
    hdr[0].markdown(
        '<span class="inv-asig-scroll-hdr">Cuenta / inversión</span>',
        unsafe_allow_html=True,
    )
    hdr[1].markdown(
        '<span class="inv-asig-scroll-hdr">Driver asignado</span>',
        unsafe_allow_html=True,
    )
    hdr[2].markdown(
        '<span class="inv-asig-scroll-hdr">Archivo</span>',
        unsafe_allow_html=True,
    )

    reglas_color_select: list[tuple[str, str, str, str]] = []
    fs_bloque = max(10, int(fs * 0.72))
    for i, row in df_base.iterrows():
        idx = int(i)
        bloque = str(row["Bloque"])
        cuenta = str(row["Cuenta"])
        estado = str(row.get("En archivo", ""))
        drv_prev = str(st.session_state.get(_clave_select_asignacion(idx), row["Driver"]))
        ix = opciones.index(drv_prev) if drv_prev in opciones else 0

        borde_c, texto_c, fondo_c = ASIGNACION_LINEA_PALETA[idx % len(ASIGNACION_LINEA_PALETA)]
        drv_actual = opciones[ix]
        fondo_d, texto_d, borde_d = mapa_drv.get(
            drv_actual, PALETA_DRIVER_ASIGNACION[0]
        )
        clave_drv = _clave_select_asignacion(idx)
        reglas_color_select.append((clave_drv, fondo_d, texto_d, borde_d))

        c1, c2, c3 = st.columns([0.52, 0.34, 0.14], gap="small")
        with c1:
            st.markdown(
                f'<div class="inv-asig-cuenta-label" style="border-left:4px solid {borde_c};'
                f"padding:4px 8px;background:{fondo_c};color:{texto_c};"
                f'border-radius:3px;font-size:{fs}px;">{html.escape(cuenta)}</div>'
                f'<div style="font-size:{fs_bloque}px;color:{texto_c};opacity:0.85;margin-top:1px;">'
                f"{html.escape(bloque)}</div>",
                unsafe_allow_html=True,
            )
        with c2:
            st.selectbox(
                "Driver",
                opciones,
                index=ix,
                key=clave_drv,
                label_visibility="collapsed",
            )
        with c3:
            color_est = "#86efac" if "grabado" in estado else (
                "#fbbf24" if "pendiente" in estado else "#94a3b8"
            )
            st.markdown(
                f'<div class="inv-asig-estado" style="color:{color_est};">'
                f"{html.escape(estado)}</div>",
                unsafe_allow_html=True,
            )

    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown(
        css_selectores_asignacion_colores(reglas_color_select, font_px=fs),
        unsafe_allow_html=True,
    )

    df_editado = _dataframe_desde_selectores(df_base, opciones)
    sincronizar_sesion_desde_asignacion(df_editado)
    return df_editado


def guardar_asignacion_drivers(
    percent_table: pd.DataFrame,
    inv_alm_n: list[str],
    cost_alm_n: list[str],
    inv_inv_n: list[str],
    cost_inv_n: list[str],
) -> None:
    """Persiste almacén + inventario en ``drivers_guardados.json``."""
    opciones = percent_table.index.tolist()
    df_base = _dataframe_asignacion_actual(
        percent_table, inv_alm_n, cost_alm_n, inv_inv_n, cost_inv_n
    )
    df = _dataframe_desde_selectores(df_base, opciones)
    if df.empty:
        return

    alm = df[df["Bloque"] == "Almacenaje"]
    inv = df[df["Bloque"] == "Inventario"]
    mapa_alm = dict(zip(alm["Cuenta"].astype(str), alm["Driver"].astype(str)))
    mapa_inv = dict(zip(inv["Cuenta"].astype(str), inv["Driver"].astype(str)))

    st.session_state[clave_drivers_sesion(TABLA_DRIVERS_ALMACEN)] = list(
        mapa_alm.values()
    )
    st.session_state[clave_drivers_sesion(TABLA_DRIVERS_INVENTARIO)] = list(
        mapa_inv.values()
    )

    _guardar_drivers_archivo({
        TABLA_DRIVERS_ALMACEN: mapa_alm,
        TABLA_DRIVERS_INVENTARIO: mapa_inv,
    })

    df_guardado = df.copy()
    for idx, row in df_guardado.iterrows():
        df_guardado.at[idx, "En archivo"] = "✓ grabado"
    st.session_state[CLAVE_DF_ASIGNACION] = df_guardado


def construir_vista_scorecard(
    table_name: str,
    nombres: list[str],
    drivers_list: list[str],
    df_scorecard_all: pd.DataFrame,
) -> pd.DataFrame:
    filtro = pd.DataFrame({table_name: nombres, "Drivers": drivers_list})
    vista = filtro.merge(df_scorecard_all, on=[table_name, "Drivers"], how="left")
    vista["% Costo"] = vista["Costo Totales"] / vista["Costo Totales"].sum()

    cols_num = [c for c in vista.columns if c not in ("Drivers", table_name)]
    totales = vista[cols_num].sum()
    vista = pd.concat([vista, pd.DataFrame([totales], columns=vista.columns)], ignore_index=True)
    vista.iloc[-1, 0] = f"{table_name} total anual "
    return vista


def mostrar_tabla_distribucion_scorecard(
    vista: pd.DataFrame,
    percent_table: pd.DataFrame,
) -> None:
    """Solo tabla de montos (sin selectores de driver)."""
    fs = _tabla_font_px()
    columnas_cat = [c for c in percent_table.columns if c != "Total"]
    formato = {c: "$ {:,.0f}" for c in columnas_cat}
    formato["Costo Totales"] = "$ {:,.0f}"
    formato["% Costo"] = "{:.2%}"

    leyenda_scorecard_colores(min(len(vista) - 1, 8))
    mostrar_tabla_html(
        vista.style.format(formato),
        fs,
        n_filas=len(vista),
        altura_px=altura_tabla_px(len(vista), fs, min_h=280, max_h=920),
        layout="scorecard",
    )


def asignar_drivers_bloque(
    percent_table: pd.DataFrame,
    table_name: str,
    inver_nombres: list[str],
    cost_nombres: list[str],
) -> list[str]:
    """Selectores compactos para un bloque (almacén o inventario)."""
    opciones = percent_table.index.tolist()
    nombres = inver_nombres + cost_nombres
    clave = clave_drivers_sesion(table_name)
    actuales = _drivers_en_sesion(table_name, nombres, percent_table)
    drivers_list = selectores_driver_lista(
        nombres,
        opciones,
        actuales,
        clave,
        None,
    )
    st.session_state[clave] = drivers_list
    return drivers_list


def mostrar_asignacion_drivers_doble(
    percent_table: pd.DataFrame,
    inv_alm_n: list[str],
    cost_alm_n: list[str],
    inv_inv_n: list[str],
    cost_inv_n: list[str],
) -> tuple[list[str], list[str]]:
    """Compatibilidad: delega en la tabla unificada con un solo scroll."""
    df = mostrar_asignacion_drivers_unificada(
        percent_table, inv_alm_n, cost_alm_n, inv_inv_n, cost_inv_n
    )
    alm = df[df["Bloque"] == "Almacenaje"]["Driver"].tolist()
    inv = df[df["Bloque"] == "Inventario"]["Driver"].tolist()
    return alm, inv


def mostrar_scorecard(
    percent_table: pd.DataFrame,
    table_name: str,
    inver_nombres: list[str],
    cost_nombres: list[str],
    df_scorecard_all: pd.DataFrame,
    drivers_asignados: list[str] | None = None,
) -> pd.DataFrame:
    """Tabla de montos usando drivers ya asignados (sin selectores)."""
    nombres = inver_nombres + cost_nombres
    if drivers_asignados is None:
        drivers_list = _drivers_en_sesion(table_name, nombres, percent_table)
    else:
        drivers_list = drivers_asignados
        st.session_state[clave_drivers_sesion(table_name)] = drivers_list

    vista = construir_vista_scorecard(table_name, nombres, drivers_list, df_scorecard_all)
    mostrar_tabla_distribucion_scorecard(vista, percent_table)
    return vista


def _columnas_categorias(tabla_scorecard: pd.DataFrame) -> list[str]:
    """Columnas de categoría en la tabla del scorecard (sin metadatos)."""
    excluir = {"Drivers", "Costo Totales", "% Costo"}
    return [c for c in tabla_scorecard.columns if c not in excluir and c != tabla_scorecard.columns[0]]


def _metricas_por_categoria(
    totales_valor: pd.DataFrame, cols: list[str]
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Ventas, inventario y margen por categoría (no totales globales)."""
    tv = totales_valor.drop(index=["Costo Totales", "Total"], errors="ignore")
    inv_col = "sum(valor inventario promedio)"
    ventas_col = "sum(ventas totales)"
    margen_col = "sum(margen bruto total)"
    inv = pd.to_numeric(tv.reindex(cols)[inv_col], errors="coerce").fillna(0)
    ventas = pd.to_numeric(tv.reindex(cols)[ventas_col], errors="coerce").fillna(0)
    margen = pd.to_numeric(tv.reindex(cols)[margen_col], errors="coerce").fillna(0)
    return inv, ventas, margen


def _div_seguro(a: pd.Series, b: pd.Series) -> pd.Series:
    return a / b.replace(0, np.nan)


def _parametros_scorecard(params: dict) -> dict[str, object]:
    """Extrae listas de inversiones/costos y % capital para el scorecard."""
    capital_pct = float(parametros.extraer_tag(params, "gen_financieros")[1][0])
    inv_alm_n, inv_alm_v = parametros.extraer_tag(params, "alm_inversiones")
    cost_alm_n, cost_alm_v = parametros.extraer_tag(params, "alm_costosgastos")
    cost_alm_vals = cost_alm_v[1:] + [capital_pct]
    inv_inv_n, inv_inv_v = parametros.extraer_tag(params, "inv_inversiones")
    inv_calc_n, inv_calc_v = parametros.extraer_tag(params, "inv_inversiones_calculado")
    inv_cost_n, inv_cost_v = parametros.extraer_tag(params, "inv_costosgastos")
    cost_inv_n = inv_calc_n[1:] + inv_cost_n
    cost_inv_v = inv_calc_v[1:] + inv_cost_v
    return {
        "capital_pct": capital_pct,
        "inv_alm_n": inv_alm_n,
        "inv_alm_v": inv_alm_v,
        "cost_alm_n": cost_alm_n,
        "cost_alm_vals": cost_alm_vals,
        "inv_inv_n": inv_inv_n,
        "inv_inv_v": inv_inv_v,
        "cost_inv_n": cost_inv_n,
        "cost_inv_v": cost_inv_v,
    }


def construir_tablas_scorecard(
    df: pd.DataFrame,
    params: dict,
    dimension: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Tablas de almacenaje e inventario (sin render UI)."""
    p = _parametros_scorecard(params)
    tabla_valor = tabla_pivote_valores(df, dimension)
    tabla_pct = tabla_pivote_porcentajes(tabla_valor)
    pct_sin_total = tabla_pct.drop(columns=["Total"], errors="ignore")

    sc_alm_all = scorecard_completo(
        pct_sin_total,
        TABLA_DRIVERS_ALMACEN,
        p["inv_alm_n"],
        p["inv_alm_v"],
        p["capital_pct"],
        p["cost_alm_n"],
        p["cost_alm_vals"],
    )
    sc_inv_all = scorecard_completo(
        pct_sin_total,
        TABLA_DRIVERS_INVENTARIO,
        p["inv_inv_n"],
        p["inv_inv_v"],
        p["capital_pct"],
        p["cost_inv_n"],
        p["cost_inv_v"],
    )

    nombres_alm = p["inv_alm_n"] + p["cost_alm_n"]
    nombres_inv = p["inv_inv_n"] + p["cost_inv_n"]
    drivers_alm = _drivers_en_sesion(TABLA_DRIVERS_ALMACEN, nombres_alm, pct_sin_total)
    drivers_inv = _drivers_en_sesion(TABLA_DRIVERS_INVENTARIO, nombres_inv, pct_sin_total)

    alm_tabla = construir_vista_scorecard(
        TABLA_DRIVERS_ALMACEN, nombres_alm, drivers_alm, sc_alm_all
    )
    inv_tabla = construir_vista_scorecard(
        TABLA_DRIVERS_INVENTARIO, nombres_inv, drivers_inv, sc_inv_all
    )
    return alm_tabla, inv_tabla, tabla_valor


def icc_por_grupo(alm_tabla: pd.DataFrame, inv_tabla: pd.DataFrame) -> pd.Series:
    """ICC (costo total de mantener inventario) por categoría o subcategoría."""
    cols = _columnas_categorias(alm_tabla)
    costo_alm = alm_tabla.iloc[-1][cols].astype(float)
    costo_inv = inv_tabla.iloc[-1][cols].astype(float)
    return costo_alm + costo_inv


def tabla_gmroi_evai_por_sku(
    df: pd.DataFrame,
    params: dict,
    dimension: str = "categoria",
) -> pd.DataFrame:
    """GMROI y EVAI por SKU con variables de cálculo visibles."""
    alm_tabla, inv_tabla, _ = construir_tablas_scorecard(df, params, dimension)
    icc_grupo = icc_por_grupo(alm_tabla, inv_tabla)

    columnas = [
        "codigo",
        "descripcion",
        "categoria",
        "subcategoria",
        "inventario promedio bultos",
        "valor inventario promedio",
        "ventas totales",
        "margen bruto total",
    ]
    out = df[columnas].copy()
    grupo = out[dimension]
    totales_grupo = out.groupby(grupo, sort=False)["valor inventario promedio"].transform("sum")
    participacion = _div_seguro(out["valor inventario promedio"], totales_grupo)
    icc_map = icc_grupo.to_dict()
    out["ICC asignado"] = participacion * grupo.map(icc_map).fillna(0)
    out["GMROI"] = _div_seguro(out["margen bruto total"], out["valor inventario promedio"])
    out["EVAI"] = out["margen bruto total"] - out["ICC asignado"]
    return out.sort_values("EVAI", ascending=False).round(
        {
            "inventario promedio bultos": 0,
            "valor inventario promedio": 0,
            "ventas totales": 0,
            "margen bruto total": 0,
            "ICC asignado": 0,
            "GMROI": 4,
            "EVAI": 0,
        }
    ).fillna(0)


def tabla_gmroi_por_sku(df: pd.DataFrame) -> pd.DataFrame:
    """Compatibilidad: GMROI por SKU sin EVAI (sin parámetros de scorecard)."""
    columnas = [
        "codigo",
        "descripcion",
        "categoria",
        "subcategoria",
        "inventario promedio bultos",
        "valor inventario promedio",
        "margen bruto total",
    ]
    out = df[columnas].copy()
    out["GMROI"] = _div_seguro(out["margen bruto total"], out["valor inventario promedio"])
    return out.sort_values("GMROI", ascending=False).round(
        {
            "inventario promedio bultos": 0,
            "valor inventario promedio": 0,
            "margen bruto total": 0,
            "GMROI": 4,
        }
    ).fillna(0)


_FMT_METRICAS_SKU = {
    "inventario promedio bultos": "{:,.0f}",
    "valor inventario promedio": "$ {:,.0f}",
    "ventas totales": "$ {:,.0f}",
    "margen bruto total": "$ {:,.0f}",
    "ICC asignado": "$ {:,.0f}",
    "GMROI": "{:.2f}",
    "EVAI": "$ {:,.0f}",
}

_NIVELES_GMROI = ("codigo", "categoria", "subcategoria")
_ETIQUETAS_NIVEL = {
    "codigo": "Código (SKU / producto)",
    "categoria": "Categoría",
    "subcategoria": "Subcategoría",
}
# Compatibilidad con sesiones previas.
_ALIASES_NIVEL_GMROI = {"producto": "codigo"}


def normalizar_nivel_gmroi(nivel: str) -> str:
    return _ALIASES_NIVEL_GMROI.get(nivel, nivel)


def filtrar_tabla_gmroi_sku(
    tabla_sku: pd.DataFrame,
    *,
    categoria: str | None = None,
    subcategoria: str | None = None,
    codigo: str | None = None,
) -> pd.DataFrame:
    """Filtra SKUs por categoría, subcategoría y/o código (None = sin filtro)."""
    out = tabla_sku
    if categoria:
        out = out[out["categoria"].astype(str) == categoria]
    if subcategoria:
        out = out[out["subcategoria"].astype(str) == subcategoria]
    if codigo:
        out = out[out["codigo"].astype(str) == codigo]
    return out

COLOR_PARETO_TOP = "#22c55e"
COLOR_PARETO_MEDIO = "#eab308"
COLOR_PARETO_COLA = "#ef4444"
PRESETS_PARETO_GMROI = {
    "5% - 10% - 85%": (0.05, 0.10, 0.85),
    "10% - 15% - 75%": (0.10, 0.15, 0.75),
    "20% - 30% - 50%": (0.20, 0.30, 0.50),
    "30% - 30% - 40% (ABC)": (0.30, 0.30, 0.40),
}
OPCIONES_PARETO_GMROI = ["Desactivado (Paleta Azul)"] + list(PRESETS_PARETO_GMROI.keys())
_DEGRADADO_AZUL_STOPS = (
    (0.0, "#0d47a1"),
    (0.35, "#2196f3"),
    (0.65, "#90caf9"),
    (1.0, "#ffffff"),
)


def _resolver_fracciones_pareto(set_seleccionado: str) -> tuple[float, float, float] | None:
    if "Desactivado" in set_seleccionado:
        return None
    for clave, fracciones in PRESETS_PARETO_GMROI.items():
        if clave in set_seleccionado:
            return fracciones
    return None


def _conteos_tres_segmentos(n: int, f1: float, f2: float, f3: float) -> tuple[int, int, int]:
    if n <= 0:
        return (0, 0, 0)
    raw = [n * f1, n * f2, n * f3]
    base = [int(x) for x in raw]
    rem = n - sum(base)
    frac_rem = [raw[i] - base[i] for i in range(3)]
    order = sorted(range(3), key=lambda i: -frac_rem[i])
    i = 0
    while rem > 0:
        base[order[i % 3]] += 1
        rem -= 1
        i += 1
    return (base[0], base[1], base[2])


def _tamanos_segmentos_pareto(n: int, f1: float, f2: float, f3: float) -> tuple[int, int, int]:
    n1, n2, n3 = _conteos_tres_segmentos(n, f1, f2, f3)
    if n >= 1 and n1 == 0 and f1 > 0:
        n1 = 1
        n3 = max(0, n - n1 - n2)
    if n3 < 0:
        n2 = max(0, n2 + n3)
        n3 = 0
    return (n1, n2, n3)


def _hex_a_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_a_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def _interp_color_hex(c1: str, c2: str, t: float) -> str:
    r1, g1, b1 = _hex_a_rgb(c1)
    r2, g2, b2 = _hex_a_rgb(c2)
    t = max(0.0, min(1.0, t))
    return _rgb_a_hex(
        int(r1 + (r2 - r1) * t),
        int(g1 + (g2 - g1) * t),
        int(b1 + (b2 - b1) * t),
    )


def _color_en_escala(t: float) -> str:
    stops = _DEGRADADO_AZUL_STOPS
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        if t <= t1 or i == len(stops) - 2:
            local = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return _interp_color_hex(c0, c1, local)
    return stops[-1][1]


def _colores_degradado_azul(n: int) -> list[str]:
    if n <= 0:
        return []
    if n == 1:
        return [_DEGRADADO_AZUL_STOPS[0][1]]
    return [_color_en_escala(i / (n - 1)) for i in range(n)]


def _aplicar_colores_pareto(
    df: pd.DataFrame,
    col_val: str,
    set_pareto: str,
) -> pd.DataFrame:
    fracciones = _resolver_fracciones_pareto(set_pareto)
    out = df.copy()
    if fracciones is None or out.empty:
        out["color_pareto"] = None
        return out
    f1, f2, f3 = fracciones
    out = out.sort_values(by=col_val, ascending=False, na_position="last").reset_index(drop=True)
    n = len(out)
    n1, n2, _n3 = _tamanos_segmentos_pareto(n, f1, f2, f3)
    colores: list[str | None] = []
    for i in range(n):
        if i < n1:
            colores.append(COLOR_PARETO_TOP)
        elif i < n1 + n2:
            colores.append(COLOR_PARETO_MEDIO)
        else:
            colores.append(COLOR_PARETO_COLA)
    out["color_pareto"] = colores
    total = float(out[col_val].sum())
    out["porcentaje_acumulado"] = out[col_val].cumsum() / total if total else 0.0
    return out


def _color_texto_barra(hex_bg: str) -> str:
    r, g, b = _hex_a_rgb(hex_bg)
    luminancia = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#0f172a" if luminancia > 0.72 else "#ffffff"


def tabla_gmroi_evai_resumen(tabla_sku: pd.DataFrame, nivel: str) -> pd.DataFrame:
    """Agrega la tabla por SKU a código, categoría o subcategoría."""
    nivel = normalizar_nivel_gmroi(nivel)
    if nivel not in _NIVELES_GMROI:
        raise ValueError(f"Nivel inválido: {nivel}")
    if nivel == "codigo":
        out = tabla_sku.copy()
        out["_etiqueta"] = out["codigo"].astype(str)
        return out.sort_values("GMROI", ascending=False).round(
            {
                "inventario promedio bultos": 0,
                "valor inventario promedio": 0,
                "ventas totales": 0,
                "margen bruto total": 0,
                "ICC asignado": 0,
                "GMROI": 4,
                "EVAI": 0,
            }
        ).fillna(0)

    cols_agg = {
        "inventario promedio bultos": "sum",
        "valor inventario promedio": "sum",
        "ventas totales": "sum",
        "margen bruto total": "sum",
        "ICC asignado": "sum",
    }
    if nivel == "categoria":
        out = (
            tabla_sku.groupby("categoria", sort=False)
            .agg(cols_agg)
            .reset_index()
        )
        out["_etiqueta"] = out["categoria"].astype(str)
    else:
        out = (
            tabla_sku.groupby(["subcategoria", "categoria"], sort=False)
            .agg(cols_agg)
            .reset_index()
        )
        out["_etiqueta"] = out["subcategoria"].astype(str)

    out["GMROI"] = _div_seguro(out["margen bruto total"], out["valor inventario promedio"])
    out["EVAI"] = out["margen bruto total"] - out["ICC asignado"]
    return out.sort_values("GMROI", ascending=False).round(
        {
            "inventario promedio bultos": 0,
            "valor inventario promedio": 0,
            "ventas totales": 0,
            "margen bruto total": 0,
            "ICC asignado": 0,
            "GMROI": 4,
            "EVAI": 0,
        }
    ).fillna(0)


def _ancho_figura_gmroi(n: int) -> int:
    """Ancho total: barras delgadas + scroll horizontal (estilo Perfilado)."""
    if n <= 8:
        px = 52
    elif n <= 20:
        px = 34
    elif n <= 50:
        px = 24
    else:
        px = 18
    return max(640, int(n * px + 100))


def _altura_figura_gmroi(n: int) -> int:
    """Altura generosa para que las barras no se vean achatadas."""
    return int(max(540, min(920, 500 + n * 6)))


def _rango_eje_y_gmroi(ys: pd.Series, metrica: str) -> tuple[float, float]:
    """Escala Y con margen superior/inferior para lectura profesional."""
    if ys.empty:
        return (0.0, 1.0)
    y_max = float(ys.max())
    y_min = float(ys.min())
    if metrica == "GMROI":
        techo = max(y_max * 1.28, 0.35)
        return (0.0, techo)
    span = y_max - y_min
    pad = max(span * 0.18, abs(y_max) * 0.12, 1.0)
    return (y_min - pad, y_max + pad)


def _angulo_etiquetas_x(n: int) -> int:
    if n > 35:
        return -90
    if n > 12:
        return -45
    return 0


def grafico_gmroi_barras(
    tabla: pd.DataFrame,
    *,
    nivel: str,
    top_n: int = 20,
    metrica: str = "GMROI",
    set_pareto: str = "Desactivado (Paleta Azul)",
    mostrar_acumulado: bool = False,
    mostrar_todos: bool = False,
) -> None:
    """Barras verticales mayor → menor; todos los códigos o top N; barras delgadas."""
    if tabla.empty:
        st.info("No hay datos para graficar.")
        return
    n_total = len(tabla)
    if mostrar_todos or nivel == "codigo":
        n = n_total
    else:
        n = min(max(1, top_n), n_total)

    datos = (
        tabla.nlargest(n, metrica)
        .sort_values(metrica, ascending=False, na_position="last")
        .reset_index(drop=True)
    )
    coloreado = _aplicar_colores_pareto(datos, metrica, set_pareto)
    pareto_activo = coloreado["color_pareto"].iloc[0] is not None
    colores = (
        coloreado["color_pareto"].astype(str).tolist()
        if pareto_activo
        else _colores_degradado_azul(len(coloreado))
    )

    xs = coloreado["_etiqueta"].astype(str)
    ys = coloreado[metrica].astype(float)
    titulo_metrica = "GMROI" if metrica == "GMROI" else "EVAI"
    etiqueta_n = f"todos ({n})" if n == n_total else f"top {n}"

    texttemplate = "%{y:.2f}" if metrica == "GMROI" else "$%{y:,.0f}"
    y_tick = ".2f" if metrica == "GMROI" else "$,.0f"
    text_colors = [_color_texto_barra(c) for c in colores]
    angulo_x = _angulo_etiquetas_x(n)
    y_lo, y_hi = _rango_eje_y_gmroi(ys, metrica)
    ancho_fig = _ancho_figura_gmroi(n)
    alto_fig = _altura_figura_gmroi(n)
    bargap = 0.72 if n > 30 else 0.55 if n > 15 else 0.38
    font_px = _tabla_font_px()
    tick_px = max(9, font_px - 2) if n > 40 else max(10, font_px - 1)
    titulo_txt = f"{titulo_metrica} · {etiqueta_n}"
    if pareto_activo:
        titulo_txt += " · Pareto"
    if pareto_activo and mostrar_acumulado:
        titulo_txt += " + acum."

    fig = go.Figure(
        go.Bar(
            x=xs,
            y=ys,
            marker=dict(color=colores, cornerradius=4, line=dict(width=0)),
            text=ys,
            texttemplate=texttemplate,
            textposition="outside",
            textangle=-90 if n > 35 else 0,
            textfont=dict(color=text_colors, size=9 if n > 40 else 10),
            cliponaxis=False,
            name=titulo_metrica,
        )
    )

    margen_b = 140 if angulo_x == -90 else 110 if angulo_x == -45 else 72
    margen_t = max(36, int(font_px * 1.6))
    layout_kw: dict = dict(
        title=dict(
            text=titulo_txt,
            font=dict(size=font_px, color="#f8fafc"),
            x=0,
            xanchor="left",
            pad=dict(t=0, b=4),
        ),
        width=ancho_fig,
        height=alto_fig,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0f1419",
        bargap=bargap,
        xaxis=dict(
            title="",
            tickangle=angulo_x,
            tickfont=dict(color="#e2e8f0", size=tick_px),
            categoryorder="array",
            categoryarray=xs.tolist(),
        ),
        yaxis=dict(
            title=dict(
                text=titulo_metrica,
                font=dict(size=font_px, color="#e2e8f0"),
            ),
            tickformat=y_tick,
            tickfont=dict(color="#e2e8f0", size=font_px),
            gridcolor="#1e293b",
            range=[y_lo, y_hi],
            zeroline=True,
            zerolinecolor="#334155",
        ),
        margin=dict(l=56, r=40, t=margen_t, b=margen_b),
        showlegend=False,
    )

    if pareto_activo and mostrar_acumulado and float(ys.sum()) != 0:
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=coloreado["porcentaje_acumulado"],
                mode="lines+markers",
                name="% acumulado",
                yaxis="y2",
                line=dict(color="#fbbf24", width=2),
                marker=dict(size=6),
            )
        )
        layout_kw["yaxis2"] = dict(
            title="% acumulado",
            overlaying="y",
            side="right",
            tickformat=".0%",
            range=[0, 1.05],
            showgrid=False,
            tickfont=dict(color="#fbbf24"),
        )
        layout_kw["margin"] = dict(l=56, r=72, t=margen_t, b=margen_b)
        layout_kw["showlegend"] = True
        layout_kw["legend"] = dict(font=dict(color="#e2e8f0"))

    fig.update_layout(**layout_kw)
    st.markdown(
        '<div style="overflow-x:auto;overflow-y:hidden;width:100%;'
        'border:1px solid #1e3a5f;border-radius:6px;padding:4px 0;">',
        unsafe_allow_html=True,
    )
    st.plotly_chart(fig, use_container_width=False)
    st.markdown("</div>", unsafe_allow_html=True)


def render_tabla_gmroi_evai(
    tabla: pd.DataFrame,
    *,
    anchos_manual: dict[str, int] | None = None,
) -> None:
    """Muestra la tabla detallada (solo si el usuario la solicita)."""
    cols = [c for c in tabla.columns if c != "_etiqueta"]
    vista = tabla[cols].copy()
    sort_cols = [c for c in ("GMROI", "EVAI") if c in vista.columns]
    if sort_cols:
        vista = vista.sort_values(
            sort_cols,
            ascending=[True] * len(sort_cols),
            na_position="last",
        ).reset_index(drop=True)
    evai_neg_filas: frozenset[int] | None = None
    if "EVAI" in vista.columns:
        neg = {
            i
            for i, v in enumerate(vista["EVAI"])
            if pd.notna(v) and float(v) < 0
        }
        if neg:
            evai_neg_filas = frozenset(neg)
    fmt = {k: v for k, v in _FMT_METRICAS_SKU.items() if k in vista.columns}
    fs = _tabla_font_px()
    mostrar_tabla_html(
        vista.style.format(fmt),
        fs,
        n_filas=len(vista),
        altura_px=altura_tabla_px(len(vista), fs, min_h=480, max_h=860),
        layout="alternada",
        anchos_manual=anchos_manual or {"codigo": 128, "descripcion": 280, "subcategoria": 175},
        evai_neg_filas=evai_neg_filas,
        colores_columna={"GMROI": "#facc15"},
    )


def mostrar_tabla_gmroi_evai_sku(
    df: pd.DataFrame,
    params: dict,
    dimension: str = "categoria",
    *,
    anchos_manual: dict[str, int] | None = None,
) -> pd.DataFrame:
    """Calcula GMROI/EVAI por SKU y muestra la tabla detallada."""
    tabla = tabla_gmroi_evai_por_sku(df, params, dimension)
    render_tabla_gmroi_evai(tabla, anchos_manual=anchos_manual)
    return tabla


def mostrar_tabla_gmroi_sku(df: pd.DataFrame) -> None:
    """Tabla GMROI por producto con filas alternadas celeste/gris."""
    tabla = tabla_gmroi_por_sku(df)
    fs = _tabla_font_px()
    fmt = {k: v for k, v in _FMT_METRICAS_SKU.items() if k in tabla.columns}
    mostrar_tabla_html(
        tabla.style.format(fmt),
        fs,
        n_filas=len(tabla),
        altura_px=altura_tabla_px(len(tabla), fs, min_h=320, max_h=640),
        layout="alternada",
        anchos_manual={"descripcion": 280},
    )


def scorecard_total(
    alm_tabla: pd.DataFrame,
    inv_tabla: pd.DataFrame,
    tabla_valores: pd.DataFrame,
) -> pd.DataFrame:
    """ICC + ICR + rotación + GMROI + EVAI por categoría."""
    totales_valor = tabla_valores.rename(index={"Total": "Costo Totales"})
    cols = _columnas_categorias(alm_tabla)

    costo_alm = alm_tabla.iloc[-1][cols].astype(float)
    costo_inv = inv_tabla.iloc[-1][cols].astype(float)
    total_cost = costo_alm + costo_inv
    total_cost.name = "Costo total de mantener inventario (ICC)"

    out = pd.DataFrame([total_cost.reindex(cols).values], columns=cols)
    out.index = [total_cost.name]
    inv_prom, ventas, margen = _metricas_por_categoria(totales_valor, cols)

    out.loc["Tasa de mantener el inventario (ICR)"] = _div_seguro(out.iloc[0], inv_prom)
    out.loc["Rotación"] = _div_seguro(ventas, inv_prom)
    rot = out.loc["Rotación"].replace(0, np.nan)
    out.loc["Días de inventario - 250 días al año"] = 250 / rot
    out.loc["Días de inventario - 360 días al año"] = 360 / rot
    out.loc["Meses de inventario"] = 12 / rot
    out.loc["Costo de mantener inventarios/ventas"] = _div_seguro(out.iloc[0], ventas)
    out.loc["Valor del inventario/ventas"] = _div_seguro(inv_prom, ventas)
    out.loc["GMROI - Gross Margin Return on Inventory"] = _div_seguro(margen, inv_prom)
    out.loc["EVAI - Valor agregado del inventario"] = margen - out.iloc[0]

    return out.fillna(0)


def _grafico_barras_horizontal(alm: pd.DataFrame, inv: pd.DataFrame) -> None:
    alm_costos = alm.iloc[:-1].groupby(alm.columns[0], as_index=True)["Costo Totales"].sum()
    inv_costos = inv.iloc[:-1].groupby(inv.columns[0], as_index=True)["Costo Totales"].sum()
    todos = pd.concat([alm_costos, inv_costos])
    fig = px.bar(
        y=todos.index,
        x=todos.values,
        title="Costo de los recursos de mantener el inventario (ICC)",
        labels={"x": "", "y": ""},
        height=500,
    )
    fig.update_traces(texttemplate="$ %{x:,.0f}", textposition="outside")
    st.plotly_chart(fig, use_container_width=True)


def _grafico_barras_valor_icc(total_df: pd.DataFrame) -> None:
    fila = total_df.loc["Costo total de mantener inventario (ICC)"].astype(float)
    total_of_totals = float(fila.sum())
    datos = fila
    pct = (datos / total_of_totals * 100) if total_of_totals else datos * 0
    fig = px.bar(
        x=datos.index,
        y=datos.values,
        title=f"Costo de mantener el inventario (ICC) · Total: $ {total_of_totals:,.0f}",
        labels={"x": "", "y": ""},
    )
    fig.update_traces(
        marker_color="chartreuse",
        text=[f"$ {v:,.0f} ({p:.1f}%)" for v, p in zip(datos.values, pct)],
        textposition="outside",
    )
    st.plotly_chart(fig, use_container_width=True)


def _grafico_barras_icr(total_df: pd.DataFrame) -> None:
    icr = total_df.loc["Tasa de mantener el inventario (ICR)"].astype(float)
    fig = px.bar(x=icr.index, y=icr.values, title="Tasa de mantener el inventario (ICR)")
    fig.update_layout(yaxis_tickformat=".0%")
    fig.update_traces(marker_color="gold", texttemplate="%{y:.1%}", textposition="outside")
    st.plotly_chart(fig, use_container_width=True)


def mostrar_kpis_totales(total_df: pd.DataFrame) -> None:
    """Presenta el scorecard total con formato legible."""
    display = total_df.copy()
    # Sin index.name: pandas duplica thead y tapa los nombres de categoría a color.
    display.index.name = None
    cols = list(display.columns)

    metricas_moneda = {
        "Costo total de mantener inventario (ICC)",
        "EVAI - Valor agregado del inventario",
    }
    metricas_pct = {
        "Tasa de mantener el inventario (ICR)",
        "Costo de mantener inventarios/ventas",
        "Valor del inventario/ventas",
        "GMROI - Gross Margin Return on Inventory",
    }
    metricas_decimal = {
        "Rotación",
        "Días de inventario - 250 días al año",
        "Días de inventario - 360 días al año",
        "Meses de inventario",
    }

    styler = display.style
    for metric in display.index:
        if metric in metricas_moneda:
            fmt = {c: "$ {:,.0f}" for c in cols}
            styler = styler.format(fmt, subset=pd.IndexSlice[metric, cols])
        elif metric in metricas_pct:
            fmt = {c: "{:.2%}" for c in cols}
            styler = styler.format(fmt, subset=pd.IndexSlice[metric, cols])
        elif metric in metricas_decimal:
            fmt = {c: "{:,.2f}" for c in cols}
            styler = styler.format(fmt, subset=pd.IndexSlice[metric, cols])
        else:
            fmt = {c: "{:,.2f}" for c in cols}
            styler = styler.format(fmt, subset=pd.IndexSlice[metric, cols])

    fs = _tabla_font_px()
    leyenda_scorecard_columnas(len(display.columns), cols)
    mostrar_tabla_html(
        styler,
        fs,
        n_filas=len(display),
        hide_index=False,
        layout="scorecard",
        mostrar_completa=True,
    )
