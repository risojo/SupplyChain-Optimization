"""Helpers puros del experimento (sin Streamlit ni Excel)."""
from __future__ import annotations

from statistics import NormalDist

import numpy as np


def rango_eje_x_demanda(media: float, desv: float, consulta: float, n: int = 300) -> np.ndarray:
    """Eje X centrado en media±4σ; se amplía si la consulta queda fuera."""
    lo = max(0.0, float(media) - 4.0 * float(desv))
    hi = float(media) + 4.0 * float(desv)
    c = float(consulta)
    if c < lo:
        lo = max(0.0, c * 0.95)
    if c > hi:
        hi = c * 1.05 if c > 0 else hi
    if hi <= lo:
        hi = lo + max(1.0, abs(float(desv)) or 1.0)
    return np.linspace(lo, hi, n)


def bultos_desde_probabilidad(media: float, desv: float, probabilidad: float) -> float:
    """
    Camino inverso: P(demanda ≤ x) = probabilidad → x (bultos).
    Usa ``NormalDist.inv_cdf`` (misma familia que el CDF de la vista; no reescribe el motor).
    """
    p = float(probabilidad)
    # Evitar 0 y 1 exactos (inv_cdf no está definido en los extremos).
    p = min(max(p, 1e-9), 1.0 - 1e-9)
    sigma = float(desv)
    if not (sigma > 0 and np.isfinite(sigma)):
        return float(media)
    return float(NormalDist(float(media), sigma).inv_cdf(p))


def probabilidad_desde_bultos(media: float, desv: float, bultos: float) -> float:
    """P(demanda ≤ bultos) con la normal del SKU."""
    sigma = float(desv)
    if not (sigma > 0 and np.isfinite(sigma)):
        return float("nan")
    return float(NormalDist(float(media), sigma).cdf(float(bultos)))


def zonas_probabilidad_delimitadores(
    media: float,
    desv: float,
    x_izq: float,
    x_der: float,
) -> tuple[float, float, float, float, float]:
    """
    Estilo @RISK: tres zonas definidas por dos delimitadores verticales.

    Returns:
        (p_izquierda, p_centro, p_derecha, x_lo, x_hi)
        con x_lo ≤ x_hi.
    """
    lo = float(min(x_izq, x_der))
    hi = float(max(x_izq, x_der))
    p_lo = probabilidad_desde_bultos(media, desv, lo)
    p_hi = probabilidad_desde_bultos(media, desv, hi)
    if not (np.isfinite(p_lo) and np.isfinite(p_hi)):
        return float("nan"), float("nan"), float("nan"), lo, hi
    p_izq = p_lo
    p_centro = max(0.0, p_hi - p_lo)
    p_der = max(0.0, 1.0 - p_hi)
    return p_izq, p_centro, p_der, lo, hi


def discretizar_normal_barras(
    media: float,
    desv: float,
    x_min: float,
    x_max: float,
    n_bins: int = 48,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Barras de densidad (PDF evaluada en el centro de cada bin)."""
    x_min, x_max = float(x_min), float(x_max)
    if x_max <= x_min:
        x_max = x_min + max(1.0, abs(float(desv)) or 1.0)
    n_bins = max(8, int(n_bins))
    edges = np.linspace(x_min, x_max, n_bins + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    width = float(edges[1] - edges[0])
    dist = NormalDist(float(media), float(desv))
    heights = np.array([dist.pdf(float(c)) for c in centers], dtype=float)
    return centers, heights, width


def colores_barras_zonas(
    centers: np.ndarray,
    x_lo: float,
    x_hi: float,
    *,
    color_centro: str = "#EA580C",
    color_cola: str = "rgba(253, 186, 116, 0.55)",
) -> list[str]:
    """Centro sólido (anaranjado); colas más claras (efecto visual tipo @RISK)."""
    lo, hi = float(x_lo), float(x_hi)
    out: list[str] = []
    for c in centers:
        out.append(color_centro if lo <= float(c) <= hi else color_cola)
    return out
