"""Diagnóstico de destrucción de valor (EVAI negativo) y guion para narración."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

_RAZON_MARGEN = "margen bruto bajo vs el promedio del grupo"
_RAZON_ICC = "inventario / costo de mantener alto vs el promedio del grupo"
_RAZON_VENTAS = "pocas ventas frente al costo de mantener inventario"
_RAZON_COMBO = "combinación de inventario, margen y ventas"

_RAZON_VOZ = {
    _RAZON_MARGEN: "margen bruto bajo frente al promedio del grupo",
    _RAZON_ICC: "alto costo de mantener inventario frente al promedio del grupo",
    _RAZON_VENTAS: "pocas ventas frente al costo de mantener inventario",
    _RAZON_COMBO: "una combinación de inventario, margen y ventas desfavorable",
}


@dataclass
class FilaDestruccion:
    codigo: str
    evai: float
    razon: str
    grupo: str


@dataclass
class GrupoDestruccion:
    nombre: str
    etiqueta_tipo: str
    productos: list[FilaDestruccion] = field(default_factory=list)

    @property
    def monto(self) -> float:
        return float(sum(p.evai for p in self.productos))

    @property
    def causa_frecuente(self) -> str:
        if not self.productos:
            return "—"
        conteos: dict[str, int] = {}
        for p in self.productos:
            conteos[p.razon] = conteos.get(p.razon, 0) + 1
        return max(conteos, key=conteos.get)


@dataclass
class AnalisisDestruccion:
    filas: list[FilaDestruccion]
    grupos: list[GrupoDestruccion]
    dimension_icc: str

    @property
    def n_productos(self) -> int:
        return len(self.filas)

    @property
    def monto_total(self) -> float:
        return float(sum(f.evai for f in self.filas))


def _señal_relativa(valor: float, promedio: float) -> float:
    if not np.isfinite(valor) or not np.isfinite(promedio):
        return 0.0
    base = max(abs(promedio), 1.0)
    return abs(valor - promedio) / base


def _diagnosticar_fila(row: pd.Series, peers: pd.DataFrame) -> str:
    ventas = float(row.get("ventas totales", 0) or 0)
    margen = float(row.get("margen bruto total", 0) or 0)
    icc = float(row.get("ICC asignado", 0) or 0)
    inv = float(row.get("valor inventario promedio", 0) or 0)

    pct_margen = margen / ventas if ventas > 0 else 0.0
    ratio_inv = inv / ventas if ventas > 0 else np.inf
    ratio_icc = icc / ventas if ventas > 0 else np.inf

    p_ventas = peers["ventas totales"].astype(float)
    p_margen = peers["margen bruto total"].astype(float)
    p_icc = peers["ICC asignado"].astype(float)
    p_inv = peers["valor inventario promedio"].astype(float)

    avg_ventas = float(p_ventas.mean())
    avg_pct_margen = float(
        (p_margen / p_ventas.replace(0, np.nan)).mean()
    )
    avg_ratio_inv = float(
        (p_inv / p_ventas.replace(0, np.nan)).mean()
    )
    avg_ratio_icc = float(
        (p_icc / p_ventas.replace(0, np.nan)).mean()
    )

    scores = {
        _RAZON_MARGEN: _señal_relativa(pct_margen, avg_pct_margen)
        if pct_margen < avg_pct_margen
        else 0.0,
        _RAZON_ICC: max(
            _señal_relativa(ratio_inv, avg_ratio_inv)
            if ratio_inv > avg_ratio_inv
            else 0.0,
            _señal_relativa(ratio_icc, avg_ratio_icc)
            if ratio_icc > avg_ratio_icc
            else 0.0,
        ),
        _RAZON_VENTAS: _señal_relativa(ventas, avg_ventas)
        if ventas < avg_ventas
        else 0.0,
    }
    ordenado = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    mejor, puntaje_top = ordenado[0]
    if puntaje_top <= 0:
        return _RAZON_COMBO
    _, puntaje_seg = ordenado[1]
    if puntaje_seg > 0 and puntaje_seg >= puntaje_top * 0.72:
        return _RAZON_COMBO
    return mejor


def analizar_destruccion_valor(
    tabla_sku: pd.DataFrame,
    *,
    dimension_icc: str = "categoria",
) -> AnalisisDestruccion:
    """SKUs con EVAI negativo, ordenados de mayor a menor destrucción."""
    dim = dimension_icc if dimension_icc in ("categoria", "subcategoria") else "categoria"
    etiqueta = "Categoría" if dim == "categoria" else "Subcategoría"

    neg = tabla_sku[tabla_sku["EVAI"].astype(float) < 0].copy()
    if neg.empty:
        return AnalisisDestruccion(filas=[], grupos=[], dimension_icc=dim)

    filas: list[FilaDestruccion] = []
    por_grupo: dict[str, list[FilaDestruccion]] = {}

    for _, row in neg.iterrows():
        grupo = str(row.get(dim, "—"))
        peers = tabla_sku[tabla_sku[dim].astype(str) == grupo]
        razon = _diagnosticar_fila(row, peers)
        item = FilaDestruccion(
            codigo=str(row["codigo"]),
            evai=float(row["EVAI"]),
            razon=razon,
            grupo=grupo,
        )
        filas.append(item)
        por_grupo.setdefault(grupo, []).append(item)

    filas.sort(key=lambda f: f.evai)
    grupos: list[GrupoDestruccion] = []
    for nombre in sorted(por_grupo):
        items = sorted(por_grupo[nombre], key=lambda f: f.evai)
        grupos.append(
            GrupoDestruccion(
                nombre=nombre,
                etiqueta_tipo=etiqueta,
                productos=items,
            )
        )
    return AnalisisDestruccion(filas=filas, grupos=grupos, dimension_icc=dim)


def _fmt_monto(v: float) -> str:
    return f"${abs(v):,.0f}"


def _fmt_monto_voz(v: float) -> str:
    n = int(round(abs(v)))
    return f"{n:,} dólares".replace(",", " ")


def guion_prosa(analisis: AnalisisDestruccion) -> str:
    if not analisis.filas:
        return (
            "No hay productos con destrucción de valor en el filtro actual. "
            "Todos los artículos visibles tienen EVAI positivo o cero."
        )
    partes = [
        f"Resumen. {analisis.n_productos} producto"
        f"{'s' if analisis.n_productos != 1 else ''} con destrucción de valor, "
        f"por un total de {_fmt_monto_voz(analisis.monto_total)}."
    ]
    for grupo in analisis.grupos:
        partes.append(
            f"{grupo.etiqueta_tipo} {grupo.nombre}. "
            f"{len(grupo.productos)} producto"
            f"{'s' if len(grupo.productos) != 1 else ''} destruyen valor, "
            f"monto {_fmt_monto_voz(grupo.monto)}. "
            f"La causa más frecuente es: {_RAZON_VOZ.get(grupo.causa_frecuente, grupo.causa_frecuente)}."
        )
        for item in grupo.productos:
            partes.append(
                f"Código {item.codigo}, pérdida de {_fmt_monto_voz(item.evai)}, "
                f"por {_RAZON_VOZ.get(item.razon, item.razon)}."
            )
    return " ".join(partes)


def markdown_resumen(analisis: AnalisisDestruccion) -> str:
    """Resumen visible al abrir el bloque (sin listado de códigos)."""
    if not analisis.filas:
        return (
            "**Sin destrucción de valor** en el filtro actual: "
            "ningún SKU con EVAI negativo."
        )

    lineas = [
        f"**Resumen:** {analisis.n_productos} producto(s) con destrucción de valor "
        f"(EVAI negativo), por un total de **−{_fmt_monto(analisis.monto_total)}**.",
        "",
    ]
    for grupo in analisis.grupos:
        lineas.extend(
            [
                f"**{grupo.etiqueta_tipo}: {grupo.nombre}**",
                f"- {len(grupo.productos)} producto(s) destruyen valor — "
                f"monto **−{_fmt_monto(grupo.monto)}**.",
                f"- Causa más frecuente en el grupo: **{grupo.causa_frecuente}**.",
                "",
            ]
        )
    return "\n".join(lineas)


def markdown_lista_articulos(analisis: AnalisisDestruccion) -> str:
    """Listado detallado de códigos con monto y causa."""
    if not analisis.filas:
        return ""

    lineas: list[str] = []
    for grupo in analisis.grupos:
        lineas.append(f"**{grupo.etiqueta_tipo}: {grupo.nombre}**")
        lineas.append("- **Principales códigos:**")
        for item in grupo.productos:
            lineas.append(
                f"  - `{item.codigo}`: **−{_fmt_monto(item.evai)}** ({item.razon})"
            )
        lineas.append("")
    lineas.append(
        "_Criterio: cada SKU se compara con el promedio de su "
        f"{'categoría' if analisis.dimension_icc == 'categoria' else 'subcategoría'} "
        "(inventario/ventas, % margen y ventas). "
        "La causa es la señal con mayor desviación._"
    )
    return "\n".join(lineas)


def markdown_analisis(analisis: AnalisisDestruccion) -> str:
    """Resumen + listado (compatibilidad)."""
    if not analisis.filas:
        return markdown_resumen(analisis)
    return markdown_resumen(analisis) + "\n" + markdown_lista_articulos(analisis)
