"""Capa de datos file-based del módulo Inventarios.

Lee el Excel maestro (``data/sources/template_inventarios.xlsx``) y lo deja con
los **mismos nombres de columna que usa Perfilado** (``perfilado.xlsx``), para
que los criterios y nombres de columnas sean idénticos entre módulos.

Convención de nombres (igual a Perfilado): minúsculas, separadas por espacios,
sin guiones ni acentos (p. ej. ``codigo``, ``ventas totales``,
``valor inventario promedio``).

Las fórmulas de las columnas calculadas replican las de Perfilado (base "por
bulto"):
    ventas totales            = bultos vendidos × precio unitario bulto
    ventas costo              = bultos vendidos × costo unitario bulto
    valor inventario promedio = inventario promedio bultos × costo unitario bulto
"""
from __future__ import annotations

import io
import os
from typing import Optional

import numpy as np
import pandas as pd

_RAIZ_PROYECTO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARCHIVO_EXCEL_PATH = os.path.join(
    _RAIZ_PROYECTO, "data", "sources", "template_inventarios.xlsx"
)
# Alias por compatibilidad interna
ARCHIVO_EXCEL_DEFECTO = ARCHIVO_EXCEL_PATH
NOMBRE_ARCHIVO_DEFECTO = os.path.basename(ARCHIVO_EXCEL_PATH)

MSG_ARCHIVO_EXCEL_ABIERTO = (
    "El archivo Excel está abierto en otra aplicación. Ciérrelo o suba una copia con otro nombre."
)

# Nombres del Excel del freelance -> nombres de Perfilado (perfilado.xlsx).
MAPA_COLUMNAS = {
    "cod_producto": "codigo",
    "cat_producto": "categoria",
    "subcat_producto": "subcategoria",
    "desc_producto": "descripcion",
    "proveedor": "proveedor",
    "pais": "pais",
    "empaque": "empaque",
    "bultos/tarima": "bultos tarima",
    "cubicaje/tarima": "cubicaje tarima",
    "demanda_mes1": "demanda mes 1",
    "demanda_mes2": "demanda mes 2",
    "demanda_mes3": "demanda mes 3",
    "demanda_mes4": "demanda mes 4",
    "demanda_mes5": "demanda mes 5",
    "demanda_mes6": "demanda mes 6",
    "demanda_mes7": "demanda mes 7",
    "demanda_mes8": "demanda mes 8",
    "demanda_mes9": "demanda mes 9",
    "demanda_mes10": "demanda mes 10",
    "demanda_mes11": "demanda mes 11",
    "demanda_mes12": "demanda mes 12",
    "ordenes_anual": "ordenes anual",
    "t_entrega_prom": "tiempo entrega",
    "inv_final/bultos": "inventario final bulto",
    "inv_prom/bultos": "inventario promedio bultos",
    "inv_trans/bultos": "valor inventario transito",
    "precio_uni/bulto": "precio unitario bulto",
    "costo_uni/bulto": "costo unitario bulto",
    "factor_escazes": "factor escazes",
}

COLUMNAS_DEMANDA = [f"demanda mes {i}" for i in range(1, 13)]

COLUMNAS_NUMERICAS = [
    "empaque", "bultos tarima", "cubicaje tarima",
    *COLUMNAS_DEMANDA,
    "ordenes anual", "tiempo entrega",
    "inventario final bulto", "inventario promedio bultos", "valor inventario transito",
    "precio unitario bulto", "costo unitario bulto", "factor escazes",
]

COLUMNAS_TEXTO = ["codigo", "categoria", "subcategoria", "descripcion", "proveedor", "pais"]

# Misma estructura que template_inventarios; el archivo puede llamarse distinto.
COLUMNAS_ENTRADA_OBLIGATORIAS = list(dict.fromkeys(COLUMNAS_TEXTO + COLUMNAS_NUMERICAS))

# Columnas calculadas que agrega este módulo (nombres de Perfilado).
COLUMNAS_CALCULADAS = [
    "unidades vendidas", "bultos vendidos", "margen utilidad ventas",
    "ventas totales", "ventas costo", "margen bruto total",
    "valor inventario promedio", "rotacion", "meses inventario",
    "bultos despachados mes", "cubicaje inventario",
]

_NO_NEGATIVAS = [c for c in COLUMNAS_NUMERICAS if c != "factor escazes"]


def _div_segura(numerador: pd.Series, denominador: pd.Series) -> pd.Series:
    """División que evita inf/NaN cuando el denominador es 0."""
    resultado = numerador / denominador.replace({0: np.nan})
    return resultado.replace([np.inf, -np.inf], np.nan).fillna(0)


def limpiar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza tipos: numéricas a float (comas->puntos), texto saneado."""
    df = df.copy()

    for col in COLUMNAS_NUMERICAS:
        if col in df.columns:
            serie = df[col].astype(str).str.replace(",", ".", regex=False).str.strip()
            serie = serie.str.replace(r"[^\d\.\-\+]", "", regex=True)
            serie = pd.to_numeric(serie, errors="coerce")
            if col in _NO_NEGATIVAS:
                serie = serie.mask(serie < 0, 0)
            df[col] = serie.fillna(0)

    for col in COLUMNAS_TEXTO:
        if col in df.columns:
            serie = df[col].astype(str).str.strip()
            serie = serie.replace(["nan", "NaN", "NAN", ""], "Sin especificar")
            df[col] = serie

    return df


def transformar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega las columnas calculadas con las mismas fórmulas que Perfilado."""
    df = df.copy()

    df["unidades vendidas"] = df[COLUMNAS_DEMANDA].sum(axis=1)
    df["bultos vendidos"] = _div_segura(df["unidades vendidas"], df["empaque"])
    df["margen utilidad ventas"] = _div_segura(
        df["precio unitario bulto"] - df["costo unitario bulto"], df["precio unitario bulto"]
    )
    df["ventas totales"] = df["bultos vendidos"] * df["precio unitario bulto"]
    df["ventas costo"] = df["bultos vendidos"] * df["costo unitario bulto"]
    df["margen bruto total"] = df["ventas totales"] - df["ventas costo"]
    df["valor inventario promedio"] = df["inventario promedio bultos"] * df["costo unitario bulto"]
    df["rotacion"] = _div_segura(df["ventas costo"], df["valor inventario promedio"])
    df["meses inventario"] = _div_segura(pd.Series(12, index=df.index), df["rotacion"])
    df["bultos despachados mes"] = df[COLUMNAS_DEMANDA].mean(axis=1)
    df["cubicaje inventario"] = _div_segura(
        df["inventario final bulto"], df["bultos tarima"]
    ) * df["cubicaje tarima"]

    return df


def _es_error_archivo_abierto(exc: BaseException) -> bool:
    if isinstance(exc, PermissionError):
        return True
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 13:
        return True
    msg = str(exc).lower()
    return "permission denied" in msg or "permiso denegado" in msg or "[errno 13]" in msg


def _renombrar_columnas_entrada(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica MAPA_COLUMNAS solo para columnas presentes (acepta nombres ya estilo Perfilado)."""
    renombres = {k: v for k, v in MAPA_COLUMNAS.items() if k in df.columns}
    if renombres:
        df = df.rename(columns=renombres)
    return df


def validar_columnas_entrada(df: pd.DataFrame) -> list[str]:
    """Devuelve columnas obligatorias ausentes (estructura estricta, nombre de archivo libre)."""
    return [c for c in COLUMNAS_ENTRADA_OBLIGATORIAS if c not in df.columns]


def _mensaje_columnas_faltantes(faltantes: list[str]) -> str:
    muestra = ", ".join(faltantes[:8])
    extra = f" (+{len(faltantes) - 8} más)" if len(faltantes) > 8 else ""
    return (
        f"El Excel puede tener **otro nombre de archivo**, pero debe traer las mismas "
        f"**{len(COLUMNAS_ENTRADA_OBLIGATORIAS)} columnas de entrada** que "
        f"`{NOMBRE_ARCHIVO_DEFECTO}` (nombres alineados a Perfilado). "
        f"Faltan: {muestra}{extra}."
    )


def preparar_dataframe_inventario(df: pd.DataFrame) -> pd.DataFrame:
    """Renombra, valida esquema, limpia y calcula columnas derivadas."""
    df = _renombrar_columnas_entrada(df.copy())
    faltantes = validar_columnas_entrada(df)
    if faltantes:
        raise ValueError(_mensaje_columnas_faltantes(faltantes))
    df = limpiar_dataframe(df)
    return transformar_dataframe(df)


def cargar_inventario(ruta: Optional[str] = None) -> pd.DataFrame:
    """Carga el Excel por ruta (uso interno; preferir ``cargar_datos`` en la app)."""
    ruta = ruta or ARCHIVO_EXCEL_PATH
    df = pd.read_excel(ruta, engine="openpyxl")
    return preparar_dataframe_inventario(df)


def cargar_datos(
    ruta: Optional[str] = None,
) -> tuple[Optional[pd.DataFrame], Optional[str]]:
    """Carga por defecto desde ``data/sources/template_inventarios.xlsx``."""
    ruta = ruta or ARCHIVO_EXCEL_PATH
    if not os.path.isfile(ruta):
        return None, (
            f"No se encontró `{NOMBRE_ARCHIVO_DEFECTO}` en data/sources. "
            "Suba un Excel con la misma estructura de columnas."
        )
    try:
        return cargar_inventario(ruta), None
    except ValueError as exc:
        return None, str(exc)
    except Exception as exc:  # noqa: BLE001
        if _es_error_archivo_abierto(exc):
            return None, MSG_ARCHIVO_EXCEL_ABIERTO
        return None, f"Error al leer el Excel: {exc}"


def cargar_datos_desde_upload(file_bytes: bytes) -> tuple[Optional[pd.DataFrame], Optional[str]]:
    """Mismo esquema estricto de columnas; el nombre del archivo puede ser cualquiera."""
    try:
        df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
        return preparar_dataframe_inventario(df), None
    except ValueError as exc:
        return None, str(exc)
    except Exception as exc:  # noqa: BLE001
        if _es_error_archivo_abierto(exc):
            return None, MSG_ARCHIVO_EXCEL_ABIERTO
        return None, f"Error al leer el archivo subido: {exc}"


def existe_archivo(ruta: Optional[str] = None) -> bool:
    return os.path.isfile(ruta or ARCHIVO_EXCEL_PATH)
