"""Capa de acceso a datos ("el mostrador").

Punto ÚNICO por el que los módulos obtienen sus datos. Hoy lee archivos Excel
de ``data/sources/<modulo>.xlsx``; el día de mañana esta misma función leerá
de una base de datos SQL, sin que los módulos tengan que cambiar.

Ejemplo de uso desde un módulo:

    from data import loaders
    df = loaders.obtener_datos("inventarios")
"""
import io
from pathlib import Path

import pandas as pd

from core import settings


def ruta_fuente(modulo: str) -> Path:
    """Ruta del Excel de un módulo dentro de la carpeta de datos compartida."""
    return settings.DATA_DIR / f"{modulo}.xlsx"


def obtener_datos(modulo: str) -> pd.DataFrame:
    """Devuelve los datos de un módulo. Hoy: Excel. Mañana: SQL (mismo contrato)."""
    return pd.read_excel(ruta_fuente(modulo), engine="openpyxl")


def cargar_desde_bytes(file_bytes: bytes) -> pd.DataFrame:
    """Lee un Excel subido por el usuario (bytes) a DataFrame."""
    return pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
