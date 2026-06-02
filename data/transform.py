"""Transformaciones y métricas derivadas sobre los datos.

Esqueleto del pipeline. Aquí se centralizarán los cálculos compartidos entre
módulos (normalización de columnas, métricas de inventario, etc.).
"""
import pandas as pd


def normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza nombres de columnas (minúsculas, sin espacios extremos)."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df
