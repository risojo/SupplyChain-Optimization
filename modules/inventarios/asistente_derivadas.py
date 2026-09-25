"""Registro de métricas derivadas y reglas empresariales auditables.

Separado de las columnas originales del DataFrame. Solo se aplican
reglas explícitamente registradas — nunca se inventan fórmulas.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd


@dataclass(frozen=True)
class ReglaDerivada:
    id: str
    nombre_visible: str
    columna_resultado: str
    sinonimos: tuple[str, ...]
    unidad: str
    formato: str
    formula_descripcion: str
    requiere_columnas: tuple[str, ...]
    aplicar: Callable[[pd.DataFrame], pd.Series]


def _pronostico_anual_desde_mensual(df: pd.DataFrame) -> pd.Series:
    """Si hay un único pronóstico ajustado mensual → × 12 (no sumar 12 periodos inexistentes)."""
    col = "pronostico ajustado"
    if col not in df.columns:
        raise ValueError(f"Falta la columna oficial «{col}» para anualizar el pronóstico.")
    # ¿Existen 12 periodos mensuales distintos?
    meses = [c for c in df.columns if str(c).lower().startswith("demanda mes")]
    if len(meses) >= 12 and "pronostico" not in "".join(meses):
        # El pronóstico ajustado sigue siendo mensual único oficial → × 12
        pass
    return pd.to_numeric(df[col], errors="coerce") * 12.0


def _presupuesto_anual_ventas(df: pd.DataFrame) -> pd.Series:
    """pronóstico ajustado mensual × 12 × precio unitario bulto."""
    if "pronostico ajustado" not in df.columns:
        raise ValueError("Falta «pronostico ajustado».")
    if "precio unitario bulto" not in df.columns:
        raise ValueError("Falta «precio unitario bulto» para presupuesto anual de ventas.")
    anual = pd.to_numeric(df["pronostico ajustado"], errors="coerce") * 12.0
    precio = pd.to_numeric(df["precio unitario bulto"], errors="coerce")
    return anual * precio


def _presupuesto_anual_costo(df: pd.DataFrame) -> pd.Series:
    """pronóstico ajustado mensual × 12 × costo unitario bulto."""
    if "pronostico ajustado" not in df.columns:
        raise ValueError("Falta «pronostico ajustado».")
    if "costo unitario bulto" not in df.columns:
        raise ValueError("Falta «costo unitario bulto» para presupuesto anual al costo.")
    anual = pd.to_numeric(df["pronostico ajustado"], errors="coerce") * 12.0
    costo = pd.to_numeric(df["costo unitario bulto"], errors="coerce")
    return anual * costo


def _cantidad_comprar_segun_minimo(df: pd.DataFrame) -> pd.Series:
    """Reutiliza la función oficial (sin rotación)."""
    import skus_a_comprar as skus

    return skus.calcular_cantidad_a_comprar_por_minimo(df)


_REGLAS: list[ReglaDerivada] = [
    ReglaDerivada(
        id="pronostico_anual",
        nombre_visible="pronóstico anual (desde mensual × 12)",
        columna_resultado="pronostico anual",
        sinonimos=(
            "pronostico anual",
            "pronóstico anual",
            "forecast anual",
            "pronostico ajustado anual",
        ),
        unidad="bultos",
        formato="numero",
        formula_descripcion="pronostico ajustado (mensual) × 12",
        requiere_columnas=("pronostico ajustado",),
        aplicar=_pronostico_anual_desde_mensual,
    ),
    ReglaDerivada(
        id="presupuesto_anual_ventas",
        nombre_visible="presupuesto anual de ventas",
        columna_resultado="presupuesto anual ventas",
        sinonimos=(
            "presupuesto anual de ventas",
            "presupuesto anual ventas",
            "presupuesto de ventas anual",
            "ventas presupuestadas anuales",
        ),
        unidad="moneda",
        formato="moneda",
        formula_descripcion="pronostico ajustado × 12 × precio unitario bulto",
        requiere_columnas=("pronostico ajustado", "precio unitario bulto"),
        aplicar=_presupuesto_anual_ventas,
    ),
    ReglaDerivada(
        id="presupuesto_anual_costo",
        nombre_visible="presupuesto anual al costo",
        columna_resultado="presupuesto anual costo",
        sinonimos=(
            "presupuesto anual al costo",
            "presupuesto anual costo",
            "presupuesto anual de costo",
        ),
        unidad="moneda",
        formato="moneda",
        formula_descripcion="pronostico ajustado × 12 × costo unitario bulto",
        requiere_columnas=("pronostico ajustado", "costo unitario bulto"),
        aplicar=_presupuesto_anual_costo,
    ),
    ReglaDerivada(
        id="qty_comprar_minimo",
        nombre_visible="cantidad a comprar según mínimo",
        columna_resultado="cantidad a comprar segun minimo",
        sinonimos=(
            "cantidad a comprar segun minimo",
            "cantidad a comprar según el mínimo",
            "cantidad a comprar segun el minimo",
            "compra segun minimo",
            "reposicion segun minimo",
        ),
        unidad="bultos",
        formato="numero",
        formula_descripcion="max(0, cantidad minima de inventario − inventario final bulto)",
        requiere_columnas=("inventario final bulto",),
        aplicar=_cantidad_comprar_segun_minimo,
    ),
]


def listar_reglas() -> list[dict[str, Any]]:
    return [
        {
            "id": r.id,
            "nombre_visible": r.nombre_visible,
            "columna_resultado": r.columna_resultado,
            "sinonimos": list(r.sinonimos),
            "unidad": r.unidad,
            "formato": r.formato,
            "formula": r.formula_descripcion,
            "requiere": list(r.requiere_columnas),
        }
        for r in _REGLAS
    ]


def resolver_derivada(consulta: str) -> ReglaDerivada | None:
    from asistente_catalogo import _norm

    q = _norm(consulta)
    mejores: list[tuple[int, ReglaDerivada]] = []
    for r in _REGLAS:
        for s in r.sinonimos:
            sn = _norm(s)
            if sn and sn in q:
                mejores.append((len(sn), r))
        if _norm(r.columna_resultado) in q:
            mejores.append((len(_norm(r.columna_resultado)), r))
    if not mejores:
        return None
    mejores.sort(key=lambda x: x[0], reverse=True)
    return mejores[0][1]


def aplicar_derivadas_necesarias(
    df: pd.DataFrame, columnas: list[str]
) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    """Materializa columnas derivadas pedidas. Devuelve (df, fórmulas aplicadas)."""
    out = df.copy()
    formulas: list[dict[str, str]] = []
    for col in columnas:
        for r in _REGLAS:
            if col == r.columna_resultado or col in r.sinonimos:
                if r.columna_resultado not in out.columns:
                    for req in r.requiere_columnas:
                        if req not in out.columns:
                            raise ValueError(
                                f"No se puede calcular «{r.nombre_visible}»: "
                                f"falta la columna oficial «{req}»."
                            )
                    out[r.columna_resultado] = r.aplicar(out)
                formulas.append(
                    {
                        "columna": r.columna_resultado,
                        "formula": r.formula_descripcion,
                        "id": r.id,
                    }
                )
                break
    return out, formulas


def enriquecer_catalogo_derivadas(catalogo: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Añade entradas de derivadas al catálogo semántico (aunque aún no estén en el DF)."""
    cat = dict(catalogo)
    for r in _REGLAS:
        if r.columna_resultado in cat:
            continue
        cat[r.columna_resultado] = {
            "nombre": r.columna_resultado,
            "nombre_visible": r.nombre_visible,
            "normalizado": r.columna_resultado,
            "dtype": "float64",
            "formato": r.formato,
            "unidad": r.unidad,
            "rol": "metrica",
            "sinonimos": list(r.sinonimos),
            "operaciones": ["sum", "mean", "min", "max", "count"],
            "valores_unicos": None,
            "n_nulos": 0,
            "n_valores": 0,
            "n_unicos": 0,
            "funcion_empresarial": r.formula_descripcion,
            "derivada": True,
            "regla_id": r.id,
        }
    return cat
