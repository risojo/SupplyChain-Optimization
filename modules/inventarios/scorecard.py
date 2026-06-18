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
import streamlit as st

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
