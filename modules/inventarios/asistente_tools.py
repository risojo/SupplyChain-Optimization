"""Herramientas de solo lectura para el Asistente Inteligente de Inventarios LRI.

Reutiliza las funciones oficiales de ``skus_a_comprar`` (sin alterar fórmulas).
El monto de compra se deriva aquí como cantidad × costo unitario.
"""
from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

import asistente_columnas as cols
import skus_a_comprar as skus

# Tope de filas enviadas al modelo (el UI puede usar el DF completo en sesión).
_MAX_FILAS_MODELO = 8
_MAX_FILAS_TABLA_UI = 500
_MAX_DESTACADOS = 5


def _norm(s: str) -> str:
    return " ".join(str(s or "").strip().lower().split())


def sanitizar_texto_respuesta(texto: str) -> str:
    """Elimina data URI, Base64 y basura técnica que no debe verse ni reenviarse."""
    import re

    if not texto:
        return ""
    t = str(texto)
    # Bloques data:image... (hasta espacio/fin o comilla)
    t = re.sub(
        r"data:image\/[a-zA-Z0-9+.-]+;base64,[A-Za-z0-9+/=\s]+",
        "[gráfico omitido — se muestra en el panel]",
        t,
        flags=re.I,
    )
    t = re.sub(
        r"data:[a-zA-Z0-9+.-]+\/[a-zA-Z0-9+.-]+;base64,[A-Za-z0-9+/=\s]+",
        "[dato binario omitido]",
        t,
        flags=re.I,
    )
    # Cadenas base64 largas sueltas (p. ej. iVBOR...)
    t = re.sub(
        r"(?<![A-Za-z0-9+/])(?:iVBOR|TVKY|UklGR|/9j/)[A-Za-z0-9+/]{80,}={0,2}",
        "[dato binario omitido]",
        t,
    )
    t = re.sub(r"base64,\s*[A-Za-z0-9+/]{40,}={0,2}", "[dato binario omitido]", t, flags=re.I)
    # JSON crudo enorme
    if t.strip().startswith("{") and len(t) > 2000:
        return "Resultado listo. Revise la tabla y el gráfico en el panel inferior."
    return t.strip()


def resumen_compacto_para_modelo(resultado: dict[str, Any]) -> dict[str, Any]:
    """Payload mínimo para OpenAI: sin DataFrames, sin imágenes, sin tabla completa."""
    if not isinstance(resultado, dict):
        return {"ok": False, "mensaje": "Resultado inválido"}
    res = resultado.get("resumen") or {}
    compact: dict[str, Any] = {
        "ok": bool(resultado.get("ok", True)),
        "tipo": resultado.get("tipo") or "resultado",
        "mensaje": resultado.get("mensaje"),
        "resumen": {
            k: res.get(k)
            for k in (
                "metrica",
                "dimension",
                "agregacion",
                "orden",
                "n_filas",
                "n_filas_totales",
                "n_skus",
                "mostrar_todos",
                "suma",
                "promedio",
                "min",
                "max",
                "formato",
                "filtros",
                "rotacion_objetivo",
                "suma_unidades",
                "monto_total",
                "advertencia_sin_costo",
            )
            if res.get(k) is not None
        },
    }
    # Destacados (no la tabla completa)
    preview = resultado.get("filas_preview") or []
    if isinstance(preview, list) and preview:
        compact["destacados_mayor"] = preview[:_MAX_DESTACADOS]
        if len(preview) > _MAX_DESTACADOS:
            compact["destacados_menor"] = preview[-_MAX_DESTACADOS:]
    # Compras / otros campos útiles y chicos
    for k in (
        "por_proveedor",
        "por_categoria",
        "tabla_comparativa",
        "diferencia_monto",
        "diferencia_unidades",
        "columnas",
    ):
        if resultado.get(k) is not None:
            val = resultado[k]
            if isinstance(val, list) and len(val) > 12:
                compact[k] = val[:12]
                compact[f"{k}_truncado"] = True
            else:
                compact[k] = val
    if resultado.get("_grafico_spec"):
        compact["grafico_preparado"] = True
        compact["grafico_titulo"] = (resultado["_grafico_spec"] or {}).get("titulo")
    compact["nota"] = (
        "La tabla completa y el gráfico se muestran solo en Streamlit. "
        "NO generes imágenes, Base64, data URI ni JSON extenso."
    )
    return compact


def payload_para_modelo(resultado: dict[str, Any]) -> dict[str, Any]:
    """Alias: siempre compacto (nunca DataFrames ni figuras)."""
    return resumen_compacto_para_modelo(resultado)


def serializar_para_modelo(resultado: dict[str, Any]) -> str:
    return json.dumps(resumen_compacto_para_modelo(resultado), ensure_ascii=False, default=str)


def _validar_rotacion(rotacion: float | int | None) -> int:
    if rotacion is None:
        raise ValueError("Se requiere rotacion_objetivo > 0.")
    try:
        r = float(rotacion)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"rotacion_objetivo inválida: {rotacion!r}") from exc
    if r <= 0:
        raise ValueError("rotacion_objetivo debe ser mayor que cero.")
    return max(1, int(round(r)))


def _match_valor(consulta: str, opciones: list[str]) -> str | None:
    """Match exacto / contención / difuso ligero contra catálogo real."""
    from difflib import SequenceMatcher

    q = _norm(consulta)
    if not q or not opciones:
        return None
    norms = {op: _norm(op) for op in opciones}
    for op, n in norms.items():
        if n == q:
            return op
    hits = [op for op, n in norms.items() if q in n or n in q]
    if hits:
        return sorted(hits, key=lambda o: len(norms[o]), reverse=True)[0]
    mejores: list[tuple[float, str]] = []
    for op, n in norms.items():
        ratio = SequenceMatcher(None, q, n).ratio()
        for tok in n.replace("&", " ").split():
            if len(tok) >= 4:
                ratio = max(ratio, SequenceMatcher(None, q, tok).ratio())
        if ratio >= 0.72:
            mejores.append((ratio, op))
    if not mejores:
        return None
    mejores.sort(key=lambda x: x[0], reverse=True)
    return mejores[0][1]


def _dias_trabajo(df_ctx: dict[str, Any] | None) -> int:
    if df_ctx and df_ctx.get("dias_trabajo"):
        return int(df_ctx["dias_trabajo"])
    return int(getattr(skus, "_DIAS_TRABAJO_DEFAULT", 30))


def _anexar_costo_monto_transito(
    plan: pd.DataFrame, df_origen: pd.DataFrame, rotacion: int
) -> tuple[pd.DataFrame, list[str]]:
    """Añade costo, monto (derivado) y tránsito desde el DF origen. No cambia qty."""
    out = plan.copy()
    out["rotacion_objetivo"] = int(rotacion)

    idx_map = None
    if cols.COL_CODIGO in out.columns and cols.COL_CODIGO in df_origen.columns:
        base = df_origen.copy()
        base["_k"] = base[cols.COL_CODIGO].astype(str)
        lookup = base.drop_duplicates("_k").set_index("_k")
        keys = out[cols.COL_CODIGO].astype(str)

        if cols.COL_COSTO in lookup.columns:
            out[cols.COL_COSTO] = keys.map(lookup[cols.COL_COSTO])
        if cols.COL_TRANSITO in lookup.columns:
            out[cols.COL_TRANSITO] = keys.map(lookup[cols.COL_TRANSITO])

    sin_costo: list[str] = []
    if cols.COL_COSTO in out.columns and cols.COL_QTY in out.columns:
        costo = pd.to_numeric(out[cols.COL_COSTO], errors="coerce")
        qty = pd.to_numeric(out[cols.COL_QTY], errors="coerce").fillna(0)
        out[cols.COL_MONTO] = qty * costo
        mask_sin = costo.isna() & (qty > 0)
        if cols.COL_CODIGO in out.columns:
            sin_costo = out.loc[mask_sin, cols.COL_CODIGO].astype(str).tolist()
    else:
        out[cols.COL_MONTO] = np.nan

    return out, sin_costo


def _aplicar_filtros(
    tabla: pd.DataFrame,
    df_origen: pd.DataFrame,
    *,
    proveedor: str | None = None,
    sku: str | list[str] | None = None,
    categoria: str | None = None,
    incluir_transito: bool = True,
    solo_compra_positiva: bool = True,
) -> pd.DataFrame:
    out = tabla.copy()

    if proveedor and cols.COL_PROVEEDOR in out.columns:
        opts = sorted({str(p) for p in out[cols.COL_PROVEEDOR].dropna().unique()})
        hit = _match_valor(proveedor, opts)
        if hit is None and cols.COL_PROVEEDOR in df_origen.columns:
            opts_all = sorted(
                {str(p) for p in df_origen[cols.COL_PROVEEDOR].dropna().unique()}
            )
            hit = _match_valor(proveedor, opts_all)
        if hit is None:
            raise ValueError(
                f"Proveedor «{proveedor}» no encontrado. "
                f"Disponibles: {', '.join(opts[:12])}"
            )
        out = out.loc[out[cols.COL_PROVEEDOR].astype(str) == hit].copy()

    if categoria and "categoria" in out.columns:
        opts = sorted({str(c) for c in out["categoria"].dropna().unique()})
        hit = _match_valor(categoria, opts)
        if hit is None:
            raise ValueError(f"Categoría «{categoria}» no encontrada.")
        out = out.loc[out["categoria"].astype(str) == hit].copy()

    if sku is not None:
        lista = [sku] if isinstance(sku, str) else list(sku)
        lista = [str(s).strip() for s in lista if str(s).strip()]
        if lista and cols.COL_CODIGO in out.columns:
            keys = { _norm(s) for s in lista }
            mask = out[cols.COL_CODIGO].astype(str).map(_norm).isin(keys)
            # También match parcial
            if not mask.any():
                mask = out[cols.COL_CODIGO].astype(str).map(
                    lambda c: any(_norm(s) in _norm(c) or _norm(c) in _norm(s) for s in lista)
                )
            out = out.loc[mask].copy()

    if not incluir_transito and cols.COL_TRANSITO in out.columns:
        tr = pd.to_numeric(out[cols.COL_TRANSITO], errors="coerce").fillna(0)
        out = out.loc[tr <= 0].copy()

    if solo_compra_positiva and cols.COL_QTY in out.columns:
        qty = pd.to_numeric(out[cols.COL_QTY], errors="coerce").fillna(0)
        out = out.loc[qty > 0].copy()

    return out.reset_index(drop=True)


def _ordenar(tabla: pd.DataFrame, ordenar_por: str | None) -> pd.DataFrame:
    if tabla.empty or not ordenar_por:
        return tabla
    key = _norm(ordenar_por)
    mapa = {
        "monto": cols.COL_MONTO,
        "monto compra": cols.COL_MONTO,
        "cantidad": cols.COL_QTY,
        "cantidad a comprar": cols.COL_QTY,
        "proveedor": cols.COL_PROVEEDOR,
        "sku": cols.COL_CODIGO,
        "codigo": cols.COL_CODIGO,
    }
    col = mapa.get(key)
    if col is None:
        for c in tabla.columns:
            if key in _norm(c):
                col = c
                break
    if col and col in tabla.columns:
        asc = col in (cols.COL_PROVEEDOR, cols.COL_CODIGO)
        return tabla.sort_values(col, ascending=asc, na_position="last").reset_index(
            drop=True
        )
    return tabla


def _resumen(tabla: pd.DataFrame, rotacion: int, filtros: dict[str, Any]) -> dict[str, Any]:
    qty = (
        pd.to_numeric(tabla[cols.COL_QTY], errors="coerce").fillna(0)
        if cols.COL_QTY in tabla.columns
        else pd.Series(dtype=float)
    )
    monto = (
        pd.to_numeric(tabla[cols.COL_MONTO], errors="coerce")
        if cols.COL_MONTO in tabla.columns
        else pd.Series(dtype=float)
    )
    monto_sum = float(monto.sum(skipna=True)) if len(monto) else 0.0
    n_sin_monto = int(monto.isna().sum()) if len(monto) else 0
    return {
        "n_skus": int(len(tabla)),
        "suma_unidades": round(float(qty.sum()), 2) if len(qty) else 0.0,
        "monto_total": round(monto_sum, 2),
        "rotacion_objetivo": int(rotacion),
        "filtros": filtros,
        "filas_sin_monto": n_sin_monto,
    }


def _filas_para_modelo(tabla: pd.DataFrame, limite: int = _MAX_FILAS_MODELO) -> list[dict]:
    if tabla.empty:
        return []
    preferidas = [c for c in cols.COLUMNAS_TABLA_COMPRA if c in tabla.columns]
    vista = tabla.loc[:, preferidas].head(limite) if preferidas else tabla.head(limite)
    records: list[dict] = []
    for _, row in vista.iterrows():
        item: dict[str, Any] = {}
        for c in vista.columns:
            v = row[c]
            if pd.isna(v):
                item[c] = None
            elif isinstance(v, (np.floating, float)):
                item[c] = round(float(v), 2)
            elif isinstance(v, (np.integer, int)):
                item[c] = int(v)
            else:
                item[c] = str(v)
        records.append(item)
    return records


def consultar_reposicion_por_minimo(
    df: pd.DataFrame,
    *,
    dias_trabajo: int | None = None,
    proveedor: str | None = None,
    categoria: str | None = None,
    subcategoria: str | None = None,
    limite: int | None = None,
) -> dict[str, Any]:
    """Reposición según inventario mínimo — SIN rotación objetivo.

    Usa ``skus.calcular_cantidad_a_comprar_por_minimo`` /
    ``tabla_reposicion_por_minimo``. Filtra cantidad > 0.
    """
    dias = int(dias_trabajo) if dias_trabajo is not None else _dias_trabajo(None)

    faltan = []
    if skus.COL_INVENTARIO_FINAL not in df.columns:
        faltan.append(skus.COL_INVENTARIO_FINAL)
    # mínimo se puede calcular si hay SS/TR o columnas de pronóstico
    try:
        tabla = skus.tabla_reposicion_por_minimo(df, dias, solo_positivos=True)
    except ValueError as exc:
        return {
            "ok": False,
            "tipo": "reposicion_por_minimo",
            "mensaje": str(exc),
            "necesita_aclaracion": False,
        }
    except Exception as exc:
        return {
            "ok": False,
            "tipo": "reposicion_por_minimo",
            "mensaje": (
                "No se pudo calcular la reposición por mínimo. "
                f"Detalle técnico: {exc}. "
                "Verifique que existan «inventario final bulto» y "
                "«cantidad minima de inventario» (o stock de seguridad + demanda TR)."
            ),
        }

    if faltan:
        return {
            "ok": False,
            "tipo": "reposicion_por_minimo",
            "mensaje": (
                "Faltan columnas oficiales para reposición por mínimo: "
                + ", ".join(f"`{c}`" for c in faltan)
            ),
        }

    # Filtros opcionales de ESTA consulta (no heredar rotación)
    try:
        if proveedor and "proveedor" in tabla.columns:
            opts = sorted({str(p) for p in tabla["proveedor"].dropna().unique()})
            hit = _match_valor(proveedor, opts)
            if hit is None:
                return {
                    "ok": False,
                    "mensaje": f"Proveedor «{proveedor}» no encontrado en el resultado.",
                    "tipo": "reposicion_por_minimo",
                }
            tabla = tabla.loc[tabla["proveedor"].astype(str) == hit].copy()
        if categoria and "categoria" in tabla.columns:
            opts = sorted({str(c) for c in tabla["categoria"].dropna().unique()})
            hit = _match_valor(categoria, opts)
            if hit is None:
                return {
                    "ok": False,
                    "mensaje": f"Categoría «{categoria}» no encontrada en el resultado.",
                    "tipo": "reposicion_por_minimo",
                }
            tabla = tabla.loc[tabla["categoria"].astype(str) == hit].copy()
        if subcategoria and "subcategoria" in tabla.columns:
            opts = sorted({str(c) for c in tabla["subcategoria"].dropna().unique()})
            hit = _match_valor(subcategoria, opts)
            if hit is None:
                return {
                    "ok": False,
                    "mensaje": f"Subcategoría «{subcategoria}» no encontrada.",
                    "tipo": "reposicion_por_minimo",
                }
            tabla = tabla.loc[tabla["subcategoria"].astype(str) == hit].copy()
    except Exception as exc:
        return {"ok": False, "mensaje": str(exc), "tipo": "reposicion_por_minimo"}

    qty_col = skus.COL_CANTIDAD_COMPRAR
    tabla[qty_col] = pd.to_numeric(tabla[qty_col], errors="coerce").fillna(0)
    tabla = tabla.loc[tabla[qty_col] > 0].copy()
    tabla = tabla.sort_values(qty_col, ascending=False, na_position="last").reset_index(
        drop=True
    )

    # Solo columnas del gráfico pedido: artículo + cantidad
    cols_keep = []
    for c in ("codigo", "descripcion", qty_col):
        if c in tabla.columns and c not in cols_keep:
            cols_keep.append(c)
    vista = tabla.loc[:, cols_keep].copy()
    if limite is not None and int(limite) > 0:
        vista = vista.head(int(limite))

    n = int(len(vista))
    suma = float(pd.to_numeric(vista[qty_col], errors="coerce").sum()) if n else 0.0
    verificacion = (
        "Criterio: reposición según inventario mínimo | Rotación: no aplicada"
    )
    resumen = {
        "metrica": qty_col,
        "metrica_legible": "cantidad a comprar (según mínimo)",
        "dimension": "codigo" if "codigo" in vista.columns else "descripcion",
        "n_filas": n,
        "n_skus": n,
        "suma_unidades": round(suma, 2),
        "promedio": round(suma / n, 2) if n else None,
        "filtros": {
            k: v
            for k, v in {
                "proveedor": proveedor,
                "categoria": categoria,
                "subcategoria": subcategoria,
            }.items()
            if v
        },
        "formato": "numero",
        "unidad": "bultos",
        "mostrar_todos": limite is None,
        "orden": "desc",
        "intencion": "reposicion_por_minimo",
        # Explícitamente SIN rotación (la UI de compras busca rotacion_objetivo)
        "rotacion_objetivo": None,
        "rotacion_aplicada": False,
    }
    spec = {
        "tipo": "barras",
        "eje_x": "codigo" if "codigo" in vista.columns else cols_keep[0],
        "eje_y": qty_col,
        "titulo": "Cantidad a comprar según inventario mínimo",
        "agrupar_por": None,
        "top_n": None,
        "mostrar_todos": True,
        "orden_desc": True,
        "formato": "numero",
    }
    msg = (
        f"{verificacion}. "
        f"**{n}** artículo(s) con cantidad a comprar > 0 · "
        f"total **{suma:,.1f}** bultos."
    )
    return {
        "ok": True,
        "tipo": "reposicion_por_minimo",
        "mensaje": msg,
        "verificacion": verificacion,
        "resumen": resumen,
        "filas_preview": _filas_para_modelo(vista),
        "columnas": list(vista.columns),
        "_df": vista.head(_MAX_FILAS_TABLA_UI),
        "_df_completo": vista,
        "_grafico_spec": spec,
        "plan": {
            "intencion": "reposicion_por_minimo",
            "metrics": [qty_col],
            "rotacion": None,
        },
    }


def construir_plan_compras(
    df: pd.DataFrame,
    *,
    rotacion_objetivo: float | int,
    dias_trabajo: int | None = None,
    proveedor: str | None = None,
    sku: str | list[str] | None = None,
    categoria: str | None = None,
    incluir_transito: bool = True,
    solo_compra_positiva: bool = True,
    ordenar_por: str | None = "monto compra",
    limite: int | None = None,
    agrupacion: str | None = None,
) -> dict[str, Any]:
    """Plan de compras oficial + monto derivado. Devuelve dict serializable + DF completo."""
    rot = _validar_rotacion(rotacion_objetivo)
    dias = int(dias_trabajo) if dias_trabajo is not None else _dias_trabajo(None)

    # Si piden solo positivos → tabla oficial; si no, todos los SKUs con qty calculada.
    solo = bool(solo_compra_positiva)
    plan = skus.tabla_skus_a_comprar(df, rot, dias, solo_a_comprar=solo)
    if not solo:
        # Incluir también qty=0 (ya vienen de tabla con solo_a_comprar=False)
        pass

    plan, sin_costo = _anexar_costo_monto_transito(plan, df, rot)
    filtros = {
        "proveedor": proveedor,
        "sku": sku,
        "categoria": categoria,
        "incluir_transito": incluir_transito,
        "solo_compra_positiva": solo_compra_positiva,
        "ordenar_por": ordenar_por,
        "limite": limite,
        "agrupacion": agrupacion,
    }
    plan = _aplicar_filtros(
        plan,
        df,
        proveedor=proveedor,
        sku=sku,
        categoria=categoria,
        incluir_transito=incluir_transito,
        solo_compra_positiva=solo_compra_positiva,
    )
    plan = _ordenar(plan, ordenar_por)

    agrupado = None
    if agrupacion:
        agrupado = _agrupar(plan, agrupacion)

    lim = int(limite) if limite is not None else None
    plan_ui = plan.head(lim) if lim and lim > 0 else plan.head(_MAX_FILAS_TABLA_UI)

    resumen = _resumen(plan, rot, filtros)
    if sin_costo:
        resumen["advertencia_sin_costo"] = (
            f"{len(sin_costo)} SKU(s) con compra > 0 sin costo unitario; "
            "su monto no entra en el total. Ej.: " + ", ".join(sin_costo[:8])
        )

    payload = {
        "ok": True,
        "mensaje": (
            f"Plan de compras con rotación {rot}. "
            f"{resumen['n_skus']} SKUs · "
            f"{resumen['suma_unidades']:,.1f} unidades · "
            f"monto ${resumen['monto_total']:,.0f}."
            if resumen["n_skus"]
            else f"Sin resultados para rotación {rot} con los filtros indicados."
        ),
        "resumen": resumen,
        "filas_preview": _filas_para_modelo(plan_ui),
        "n_filas_totales": int(len(plan)),
        "agrupacion": agrupado,
        "columnas_disponibles": list(plan.columns),
    }
    # DF completo para la UI (no se serializa al modelo tal cual).
    payload["_df"] = plan_ui
    payload["_df_completo"] = plan
    return payload


def _agrupar(tabla: pd.DataFrame, dimension: str) -> list[dict[str, Any]]:
    dim = _norm(dimension)
    col_map = {
        "proveedor": cols.COL_PROVEEDOR,
        "categoria": "categoria",
        "subcategoria": "subcategoria",
        "sku": cols.COL_CODIGO,
    }
    col = col_map.get(dim)
    if col is None or col not in tabla.columns:
        return []
    qty = pd.to_numeric(tabla[cols.COL_QTY], errors="coerce").fillna(0)
    monto = (
        pd.to_numeric(tabla[cols.COL_MONTO], errors="coerce")
        if cols.COL_MONTO in tabla.columns
        else pd.Series(0.0, index=tabla.index)
    )
    tmp = tabla.copy()
    tmp["_qty"] = qty
    tmp["_monto"] = monto
    g = (
        tmp.groupby(tmp[col].astype(str), dropna=False)
        .agg(n_skus=("_qty", "count"), unidades=("_qty", "sum"), monto=("_monto", "sum"))
        .reset_index()
        .rename(columns={col: "grupo"})
        .sort_values("monto", ascending=False)
    )
    total = float(g["monto"].sum()) or 1.0
    out = []
    for _, row in g.iterrows():
        out.append(
            {
                "grupo": str(row["grupo"]),
                "n_skus": int(row["n_skus"]),
                "unidades": round(float(row["unidades"]), 2),
                "monto": round(float(row["monto"]), 2),
                "pct_monto": round(100.0 * float(row["monto"]) / total, 2),
            }
        )
    return out


def comparar_escenarios_compra(
    df: pd.DataFrame,
    *,
    rotaciones: list[float | int],
    dias_trabajo: int | None = None,
    proveedor: str | None = None,
    categoria: str | None = None,
    incluir_transito: bool = True,
) -> dict[str, Any]:
    if not rotaciones or len(rotaciones) < 2:
        raise ValueError("Indique al menos dos rotaciones, p. ej. [3, 4].")
    rots = [_validar_rotacion(r) for r in rotaciones]
    planes: dict[int, pd.DataFrame] = {}
    resumenes: list[dict[str, Any]] = []
    for r in rots:
        p = construir_plan_compras(
            df,
            rotacion_objetivo=r,
            dias_trabajo=dias_trabajo,
            proveedor=proveedor,
            categoria=categoria,
            incluir_transito=incluir_transito,
            solo_compra_positiva=True,
            ordenar_por="monto compra",
        )
        planes[r] = p["_df_completo"]
        resumenes.append({"rotacion": r, **p["resumen"]})

    r_a, r_b = rots[0], rots[1]
    a, b = planes[r_a], planes[r_b]
    cod_a = set(a[cols.COL_CODIGO].astype(str)) if not a.empty else set()
    cod_b = set(b[cols.COL_CODIGO].astype(str)) if not b.empty else set()
    monto_a = float(pd.to_numeric(a[cols.COL_MONTO], errors="coerce").sum()) if not a.empty and cols.COL_MONTO in a.columns else 0.0
    monto_b = float(pd.to_numeric(b[cols.COL_MONTO], errors="coerce").sum()) if not b.empty and cols.COL_MONTO in b.columns else 0.0
    qty_a = float(pd.to_numeric(a[cols.COL_QTY], errors="coerce").sum()) if not a.empty else 0.0
    qty_b = float(pd.to_numeric(b[cols.COL_QTY], errors="coerce").sum()) if not b.empty else 0.0

    comp = {
        "ok": True,
        "rotaciones": rots,
        "por_rotacion": resumenes,
        "diferencia_unidades": round(qty_b - qty_a, 2),
        "diferencia_monto": round(monto_b - monto_a, 2),
        "skus_solo_en_rotacion_a": sorted(cod_a - cod_b)[:30],
        "skus_solo_en_rotacion_b": sorted(cod_b - cod_a)[:30],
        "skus_en_ambas": sorted(cod_a & cod_b)[:30],
        "mensaje": (
            f"Comparación rotación {r_a} vs {r_b}: "
            f"Δ unidades {qty_b - qty_a:,.1f}, Δ monto ${monto_b - monto_a:,.0f}."
        ),
    }
    # Tabla comparativa compacta
    filas = []
    for r in rots:
        s = next(x for x in resumenes if x["rotacion"] == r)
        filas.append(
            {
                "rotacion": r,
                "n_skus": s["n_skus"],
                "unidades": s["suma_unidades"],
                "monto_total": s["monto_total"],
            }
        )
    comp["tabla_comparativa"] = filas
    comp["_df"] = pd.DataFrame(filas)
    return comp


def resumir_compras_por_proveedor(
    df: pd.DataFrame,
    *,
    rotacion_objetivo: float | int,
    dias_trabajo: int | None = None,
    categoria: str | None = None,
    incluir_transito: bool = True,
) -> dict[str, Any]:
    plan = construir_plan_compras(
        df,
        rotacion_objetivo=rotacion_objetivo,
        dias_trabajo=dias_trabajo,
        categoria=categoria,
        incluir_transito=incluir_transito,
        solo_compra_positiva=True,
        agrupacion="proveedor",
    )
    grupos = plan.get("agrupacion") or []
    return {
        "ok": True,
        "rotacion_objetivo": plan["resumen"]["rotacion_objetivo"],
        "monto_total": plan["resumen"]["monto_total"],
        "n_skus": plan["resumen"]["n_skus"],
        "por_proveedor": grupos,
        "mensaje": plan["mensaje"],
        "advertencia_sin_costo": plan["resumen"].get("advertencia_sin_costo"),
        "_df": pd.DataFrame(grupos) if grupos else pd.DataFrame(),
        "_df_detalle": plan.get("_df_completo"),
    }


def consultar_detalle_sku(
    df: pd.DataFrame,
    *,
    sku: str | list[str],
    rotacion_objetivo: float | int | None = None,
    dias_trabajo: int | None = None,
) -> dict[str, Any]:
    rot = _validar_rotacion(rotacion_objetivo) if rotacion_objetivo else _validar_rotacion(4)
    dias = int(dias_trabajo) if dias_trabajo is not None else _dias_trabajo(None)
    plan = skus.tabla_skus_a_comprar(df, rot, dias, solo_a_comprar=False)
    plan, sin_costo = _anexar_costo_monto_transito(plan, df, rot)
    plan = _aplicar_filtros(
        plan,
        df,
        sku=sku,
        incluir_transito=True,
        solo_compra_positiva=False,
    )
    if plan.empty:
        return {
            "ok": False,
            "mensaje": f"No se encontró el SKU solicitado: {sku!r}.",
            "filas_preview": [],
            "_df": plan,
        }
    # Enriquecer con columnas de origen útiles
    extras = [
        c
        for c in (
            "pronostico",
            "pronostico ajustado",
            "tiempo entrega",
            "rotacion",
            "precio unitario bulto",
        )
        if c in df.columns and c not in plan.columns
    ]
    if extras and cols.COL_CODIGO in plan.columns:
        base = df.copy()
        base["_k"] = base[cols.COL_CODIGO].astype(str)
        look = base.drop_duplicates("_k").set_index("_k")
        for c in extras:
            plan[c] = plan[cols.COL_CODIGO].astype(str).map(look[c])

    return {
        "ok": True,
        "mensaje": f"Detalle de {len(plan)} SKU(s) con rotación objetivo {rot}.",
        "resumen": _resumen(plan, rot, {"sku": sku}),
        "filas_preview": _filas_para_modelo(plan, limite=20),
        "advertencia_sin_costo": (
            f"Sin costo: {', '.join(sin_costo[:8])}" if sin_costo else None
        ),
        "_df": plan,
    }


def preparar_visualizacion(
    *,
    tipo: str = "barras",
    eje_x: str = "codigo",
    eje_y: str = "monto compra",
    titulo: str | None = None,
    agrupar_por: str | None = None,
    top_n: int | None = 20,
    mostrar_todos: bool = False,
    orden_desc: bool = True,
    formato: str | None = None,
    usar_ultimo_resultado: bool = True,
) -> dict[str, Any]:
    """Especificación de gráfico; los datos reales los aporta la UI desde sesión."""
    tipo_n = _norm(tipo)
    tipo_map = {
        "barras": "barras",
        "bar": "barras",
        "vertical": "barras",
        "horizontal": "horizontal",
        "barras horizontales": "horizontal",
        "lineas": "lineas",
        "líneas": "lineas",
        "line": "lineas",
        "pareto": "pareto",
        "tabla": "tabla",
    }
    tipo_final = tipo_map.get(tipo_n, "barras")
    lim = None if mostrar_todos or top_n is None else max(1, int(top_n))
    return {
        "ok": True,
        "spec": {
            "tipo": tipo_final,
            "eje_x": eje_x,
            "eje_y": eje_y,
            "titulo": titulo or "Análisis Inventory Pro",
            "agrupar_por": agrupar_por,
            "top_n": lim,
            "mostrar_todos": bool(mostrar_todos or lim is None),
            "orden_desc": bool(orden_desc),
            "formato": formato,
            "usar_ultimo_resultado": bool(usar_ultimo_resultado),
        },
        "mensaje": (
            f"Visualización preparada: {tipo_final}"
            + (" (todos los registros)." if lim is None else f" (top {lim}).")
        ),
    }


def enriquecer_dataframe_consulta(
    df: pd.DataFrame,
    *,
    dias_trabajo: int = 30,
    rotacion: int = 4,
) -> pd.DataFrame:
    """Copia de solo lectura con columnas calculadas oficiales si faltan.

    No modifica el DataFrame de sesión ni altera fórmulas: solo enriquece
    una vista para el asistente (GMROI simple, SS, TR, mínimo, qty, monto).
    """
    out = df.copy()
    # GMROI oficial (misma fórmula que scorecard.tabla_gmroi_por_sku)
    if "GMROI" not in out.columns:
        if "margen bruto total" in out.columns and "valor inventario promedio" in out.columns:
            mb = pd.to_numeric(out["margen bruto total"], errors="coerce")
            vi = pd.to_numeric(out["valor inventario promedio"], errors="coerce")
            out["GMROI"] = mb / vi.replace(0, np.nan)

    # Columnas de reposición (funciones oficiales) si aún no están en el DF
    try:
        if "stock de seguridad" not in out.columns:
            out["stock de seguridad"] = skus.calcular_stock_seguridad(out)
    except Exception:
        pass
    try:
        if "demanda en el tiempo de entrega" not in out.columns:
            out["demanda en el tiempo de entrega"] = skus.calcular_demanda_tiempo_entrega(
                out, dias_trabajo
            )
    except Exception:
        pass
    try:
        if "cantidad minima de inventario" not in out.columns:
            out["cantidad minima de inventario"] = skus.calcular_cantidad_minima(
                out, dias_trabajo
            )
    except Exception:
        pass
    try:
        rot = max(1, int(rotacion))
        if "inventario objetivo" not in out.columns and "pronostico ajustado" in out.columns:
            out["inventario objetivo"] = (
                pd.to_numeric(out["pronostico ajustado"], errors="coerce") * 12.0 / rot
            )
        if "cantidad a comprar" not in out.columns:
            out["cantidad a comprar"] = skus.calcular_cantidad_a_comprar(
                out, rot, dias_trabajo
            )
    except Exception:
        pass
    if "monto compra" not in out.columns and "cantidad a comprar" in out.columns:
        qty = pd.to_numeric(out["cantidad a comprar"], errors="coerce")
        if "costo unitario bulto" in out.columns:
            costo = pd.to_numeric(out["costo unitario bulto"], errors="coerce")
            out["monto compra"] = qty * costo
    return out


def consultar_datos(
    df: pd.DataFrame,
    *,
    metrica: str,
    dimension: str | None = None,
    agregacion: str = "none",
    orden: str = "desc",
    limite: int | None = None,
    mostrar_todos: bool = False,
    proveedor: str | None = None,
    categoria: str | None = None,
    subcategoria: str | None = None,
    clase: str | None = None,
    sku: str | list[str] | None = None,
    columnas_extra: list[str] | None = None,
    dias_trabajo: int = 30,
    rotacion_enriquecer: int = 4,
    generar_grafico: bool = True,
    titulo: str | None = None,
    contexto_frase: str | None = None,
    metricas: list[str] | None = None,
) -> dict[str, Any]:
    """Adaptador hacia el ejecutor de QueryPlan (compatibilidad)."""
    import asistente_catalogo as cat
    import asistente_query_plan as qp

    base = enriquecer_dataframe_consulta(
        df, dias_trabajo=dias_trabajo, rotacion=rotacion_enriquecer
    )
    frase = contexto_frase or metrica
    mets = list(metricas or [])
    if metrica and metrica not in mets:
        if metrica in base.columns:
            mets.insert(0, metrica)
        else:
            col, err = cat.resolver_columna(metrica, base, contexto_frase=frase)
            if err and not col:
                return {
                    "ok": False,
                    "mensaje": err,
                    "tipo": "consulta_datos",
                    "necesita_aclaracion": True,
                }
            if col:
                mets.insert(0, col)
    mets = list(dict.fromkeys(mets))

    filters: list[qp.FilterSpec] = []
    for col, val in (
        ("proveedor", proveedor),
        ("categoria", categoria),
        ("subcategoria", subcategoria),
        ("clase", clase),
    ):
        if val:
            filters.append(qp.FilterSpec(column=col, operator="eq", value=val))
    if sku is not None:
        lista = [sku] if isinstance(sku, str) else list(sku)
        for s in lista:
            if s:
                filters.append(qp.FilterSpec(column="codigo", operator="eq", value=str(s)))

    agg_n = _norm(agregacion or "none")
    group_by: list[str] = []
    dimensions: list[str] = []
    if dimension:
        if agg_n and agg_n not in ("none", "ninguna", ""):
            group_by = [dimension]
            dimensions = [dimension]
        else:
            dimensions = [dimension]
    else:
        dimensions = ["codigo"] if "codigo" in base.columns else []

    aggregations = {}
    for m in mets:
        if group_by:
            aggregations[m] = (
                "mean"
                if agg_n in ("mean", "promedio", "avg", "media")
                else ("median" if agg_n in ("median", "mediana") else "sum")
            )
        else:
            aggregations[m] = "none"

    plan = qp.QueryPlan(
        metrics=mets,
        dimensions=dimensions,
        filters=filters,
        group_by=group_by,
        aggregations=aggregations,
        sort_by=mets[0] if mets else None,
        sort_order="asc"
        if _norm(orden) in ("asc", "ascendente", "menor", "menor a mayor", "ascending")
        else "desc",
        limit=limite,
        mostrar_todos=mostrar_todos,
        output="combinacion" if generar_grafico else "tabla",
        chart_type="barras_agrupadas" if len(mets) > 1 else "barras",
        comparison=mets if len(mets) > 1 else [],
        titulo=titulo,
        raw_question=frase or "",
    )
    # columnas_extra: conservar vía detalle (se incluyen si existen en DF)
    result = qp.ejecutar_plan(
        df, plan, dias_trabajo=dias_trabajo, rotacion=rotacion_enriquecer
    )
    if (
        result.get("ok")
        and columnas_extra
        and isinstance(result.get("_df_completo"), pd.DataFrame)
    ):
        extra_cols = []
        for raw in columnas_extra:
            c2, _ = cat.resolver_columna(str(raw), base)
            if c2 and c2 in base.columns:
                extra_cols.append(c2)
        if extra_cols and not plan.group_by:
            vista = result["_df_completo"]
            # re-merge extras from filtered base by codigo
            pass  # detalle ya trae columnas estándar
    return result
