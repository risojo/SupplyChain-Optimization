"""Gráficos Plotly del Asistente Inteligente — estilo Inventory Pro."""
from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

import asistente_columnas as cols

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None  # type: ignore

_COLORES = [
    "#3b82f6",
    "#10b981",
    "#f59e0b",
    "#ef4444",
    "#8b5cf6",
    "#06b6d4",
    "#ec4899",
]


def _fmt_moneda(v: float) -> str:
    return f"$ {v:,.0f}"


def _font_ejes() -> int:
    if st is None:
        return 12
    return int(st.session_state.get("inv_gmroi_font_ejes", 12))


def _font_barras() -> int:
    if st is None:
        return 10
    return int(st.session_state.get("inv_gmroi_font_barras", 10))


def _texttemplate(formato: str | None) -> str:
    f = (formato or "numero").lower()
    if f == "moneda":
        return "$%{y:,.0f}"
    if f == "porcentaje":
        return "%{y:.1%}"
    if f in ("decimal", "rotacion", "meses"):
        return "%{y:.2f}"
    return "%{y:,.2f}"


def _titulo_eje(nombre: str, unidad: str | None, formato: str | None) -> str:
    u = unidad
    if not u and formato == "moneda":
        u = "dólares"
    if u:
        return f"{nombre} ({u})"
    return nombre


def figura_desde_spec(
    df: pd.DataFrame,
    spec: dict[str, Any],
    *,
    resumen: dict[str, Any] | None = None,
) -> go.Figure | None:
    if df is None or df.empty or not spec:
        return None

    tipo = str(spec.get("tipo") or "barras")
    if tipo == "tabla":
        return None

    ejes_y = spec.get("ejes_y") or []
    if isinstance(ejes_y, str):
        ejes_y = [ejes_y]
    ejes_y = [str(y) for y in ejes_y if y]
    eje_y = str(spec.get("eje_y") or (ejes_y[0] if ejes_y else ""))
    if eje_y and eje_y not in ejes_y:
        ejes_y = [eje_y] + [y for y in ejes_y if y != eje_y]
    if not ejes_y and eje_y:
        ejes_y = [eje_y]

    mostrar_todos = bool(spec.get("mostrar_todos"))
    top_n = spec.get("top_n")
    titulo = str(spec.get("titulo") or "Análisis Inventory Pro")
    agrupar = spec.get("agrupar_por")
    eje_x = str(spec.get("eje_x") or "")
    orden_desc = bool(spec.get("orden_desc", True))
    formato = spec.get("formato") or (resumen or {}).get("formato")
    formatos = spec.get("formatos") or (resumen or {}).get("formatos") or {}
    unidades = spec.get("unidades") or (resumen or {}).get("unidades") or {}

    data = df.copy()

    if agrupar and len(ejes_y) == 1:
        gcol = {
            "proveedor": cols.COL_PROVEEDOR,
            "categoria": "categoria",
            "subcategoria": "subcategoria",
            "clase": "clase",
            "sku": cols.COL_CODIGO,
        }.get(str(agrupar).lower(), str(agrupar))
        ey = ejes_y[0]
        if gcol in data.columns and ey in data.columns:
            ynum = pd.to_numeric(data[ey], errors="coerce").fillna(0)
            data = (
                data.assign(_y=ynum)
                .groupby(data[gcol].astype(str), dropna=False)["_y"]
                .sum()
                .reset_index()
                .rename(columns={gcol: "etiqueta", "_y": ey})
            )
            eje_x = "etiqueta"

    for ey in list(ejes_y):
        if ey not in data.columns:
            ejes_y = [y for y in ejes_y if y in data.columns]
    if not ejes_y:
        for cand in (cols.COL_MONTO, cols.COL_QTY, "rotacion", "ventas totales"):
            if cand in data.columns:
                ejes_y = [cand]
                break
        else:
            return None

    primary = ejes_y[0]
    for ey in ejes_y:
        data[ey] = pd.to_numeric(data[ey], errors="coerce")
    data = data.sort_values(primary, ascending=not orden_desc, na_position="last")

    if not eje_x or eje_x not in data.columns:
        for cand in ("etiqueta", "codigo", "proveedor", "categoria", "descripcion"):
            if cand in data.columns:
                eje_x = cand
                break
        else:
            return None

    if mostrar_todos or top_n is None:
        plot_df = data.copy()
        nota_recorte = ""
    else:
        n = max(1, int(top_n))
        plot_df = data.head(n).copy()
        nota_recorte = (
            f"Mostrando top {n} de {len(data)} (tabla con detalle completo)"
            if len(data) > n
            else ""
        )

    plot_df = plot_df.copy()
    if "descripcion" in data.columns and eje_x == "codigo":
        plot_df["etiqueta"] = (
            plot_df["codigo"].astype(str)
            + " · "
            + plot_df["descripcion"].astype(str).str[:28]
        )
    else:
        plot_df["etiqueta"] = plot_df[eje_x].astype(str)
    eje_plot = "etiqueta"

    sub_parts = []
    if resumen:
        mets = resumen.get("metricas") or ([resumen["metrica"]] if resumen.get("metrica") else [])
        if mets:
            sub_parts.append("Métricas: " + ", ".join(str(m) for m in mets))
        if resumen.get("n_filas") is not None:
            sub_parts.append(f"{resumen.get('n_filas')} filas")
        if resumen.get("rotacion_objetivo") is not None:
            sub_parts.append(f"Rotación {resumen['rotacion_objetivo']}")
            if resumen.get("monto_total") is not None:
                sub_parts.append(_fmt_moneda(float(resumen["monto_total"])))
    if nota_recorte:
        sub_parts.append(nota_recorte)
    sub = " · ".join(sub_parts)

    n = len(plot_df)

    # --- Multi-métrica ---
    if len(ejes_y) >= 2 and tipo in ("barras_agrupadas", "dual_axis", "barras"):
        def _norm_u(u: Any) -> str:
            s = str(u or "").lower()
            if s in ("moneda", "dólares", "dolares", "$"):
                return "moneda"
            if "bulto" in s:
                return "bultos"
            return s or "numero"

        unidades_set = {
            _norm_u(unidades.get(y) or formatos.get(y) or formato) for y in ejes_y
        }
        # barras_agrupadas fuerza mismo eje aunque el tipo diga dual por error
        usar_dual = (tipo == "dual_axis" or len(unidades_set) > 1) and tipo != "barras_agrupadas"
        if usar_dual and len(ejes_y) >= 2:
            fig = go.Figure()
            y1, y2 = ejes_y[0], ejes_y[1]
            f1 = formatos.get(y1) or formato
            f2 = formatos.get(y2) or "numero"
            fig.add_bar(
                x=plot_df[eje_plot],
                y=plot_df[y1],
                name=y1,
                text=plot_df[y1],
                texttemplate=_texttemplate(str(f1) if f1 else None),
                textposition="outside",
                marker_color=_COLORES[0],
                cliponaxis=False,
            )
            fig.add_scatter(
                x=plot_df[eje_plot],
                y=plot_df[y2],
                name=y2,
                yaxis="y2",
                mode="lines+markers",
                marker_color=_COLORES[1],
            )
            fig.update_layout(
                yaxis=dict(
                    title=_titulo_eje(y1, unidades.get(y1), f1),
                ),
                yaxis2=dict(
                    title=_titulo_eje(y2, unidades.get(y2), f2),
                    overlaying="y",
                    side="right",
                ),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                barmode="group",
            )
        else:
            fig = go.Figure()
            for i, ey in enumerate(ejes_y):
                f = formatos.get(ey) or formato
                fig.add_bar(
                    x=plot_df[eje_plot],
                    y=plot_df[ey],
                    name=ey,
                    text=plot_df[ey],
                    texttemplate=_texttemplate(str(f) if f else None),
                    textposition="outside",
                    marker_color=_COLORES[i % len(_COLORES)],
                    cliponaxis=False,
                )
            fig.update_layout(
                barmode="group",
                yaxis_title="Valores",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
            )
    elif tipo == "horizontal":
        tmpl = _texttemplate(str(formato) if formato else None)
        fig = go.Figure(
            go.Bar(
                x=plot_df[primary],
                y=plot_df[eje_plot],
                orientation="h",
                text=plot_df[primary],
                texttemplate=tmpl.replace("%{y", "%{x"),
                textposition="outside",
                marker_color=_COLORES[0],
            )
        )
        fig.update_layout(
            xaxis_title=_titulo_eje(primary, unidades.get(primary), formato),
            yaxis_title=eje_x,
        )
    elif tipo == "lineas":
        fig = px.line(plot_df, x=eje_plot, y=primary, markers=True, title=titulo)
    elif tipo == "pareto":
        tmpl = _texttemplate(str(formato) if formato else None)
        plot_df = plot_df.copy()
        total = float(plot_df[primary].sum()) or 1.0
        plot_df["pct_acum"] = plot_df[primary].cumsum() / total * 100.0
        fig = go.Figure()
        fig.add_bar(
            x=plot_df[eje_plot],
            y=plot_df[primary],
            name=primary,
            text=plot_df[primary],
            texttemplate=tmpl,
            textposition="outside",
            marker_color=_COLORES[0],
        )
        fig.add_scatter(
            x=plot_df[eje_plot],
            y=plot_df["pct_acum"],
            name="% acum.",
            yaxis="y2",
            mode="lines+markers",
        )
        fig.update_layout(
            yaxis2=dict(title="% acum.", overlaying="y", side="right", range=[0, 100])
        )
    else:
        tmpl = _texttemplate(str(formato) if formato else None)
        fig = go.Figure(
            go.Bar(
                x=plot_df[eje_plot],
                y=plot_df[primary],
                text=plot_df[primary],
                texttemplate=tmpl,
                textposition="outside",
                marker_color=_COLORES[0],
                cliponaxis=False,
            )
        )
        fig.update_layout(
            yaxis_title=_titulo_eje(primary, unidades.get(primary), formato),
        )

    fig.update_layout(
        title=titulo,
        margin=dict(l=40, r=40, t=80, b=110),
        height=max(420, min(780, 300 + n * 4)),
        bargap=0.35 if n <= 20 else 0.22,
        xaxis_tickangle=-35,
        xaxis_title=eje_x if eje_x != "etiqueta" else "",
        font=dict(size=_font_ejes()),
        uniformtext_minsize=8,
        uniformtext_mode="hide",
        annotations=(
            [
                dict(
                    text=sub,
                    xref="paper",
                    yref="paper",
                    x=0,
                    y=1.16,
                    showarrow=False,
                    font=dict(size=11, color="#64748b"),
                )
            ]
            if sub
            else []
        ),
    )
    if "yaxis_title" not in (fig.layout.to_plotly_json().get("yaxis") or {}) and len(ejes_y) == 1:
        fig.update_layout(
            yaxis_title=_titulo_eje(primary, unidades.get(primary), formato)
        )
    fig.update_traces(textfont_size=_font_barras())
    return fig
