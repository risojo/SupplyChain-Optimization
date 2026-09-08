"""Capa de datos file-based del módulo Inventarios.

Lee el Excel maestro de Inventarios (``data/sources/inventarios.xlsx``):
- hoja ``data`` — SKUs y métricas
- hoja ``parametros`` — costos / capital (vía ``parametros.py``)

Convención de nombres: minúsculas, espacios, sin guiones ni acentos
(p. ej. ``codigo``, ``ventas totales``, ``valor inventario promedio``).
"""
from __future__ import annotations

import io
import os
from typing import Optional

import numpy as np
import pandas as pd

_RAIZ_PROYECTO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARCHIVO_EXCEL_PATH = os.path.join(
    _RAIZ_PROYECTO, "data", "sources", "inventarios.xlsx"
)
# Alias por compatibilidad interna
ARCHIVO_EXCEL_DEFECTO = ARCHIVO_EXCEL_PATH
NOMBRE_ARCHIVO_DEFECTO = os.path.basename(ARCHIVO_EXCEL_PATH)
HOJA_DATOS = "data"

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

# Tipografía histórica en perfilado.xlsx (demada → demanda).
for _i in (1, 3, 5):
    MAPA_COLUMNAS[f"demada mes {_i}"] = f"demanda mes {_i}"

COLUMNAS_DEMANDA = [f"demanda mes {i}" for i in range(1, 13)]

COLUMNAS_NUMERICAS = [
    "empaque", "bultos tarima", "cubicaje tarima",
    *COLUMNAS_DEMANDA,
    "ordenes anual", "tiempo entrega",
    "inventario final bulto", "inventario promedio bultos", "valor inventario transito",
    "precio unitario bulto", "costo unitario bulto", "factor escazes",
]

COLUMNAS_TEXTO = ["codigo", "categoria", "subcategoria", "descripcion", "proveedor", "pais"]

# Misma estructura que Perfilado; el archivo puede llamarse distinto.
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


def _renombrar_columnas_entrada(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica MAPA_COLUMNAS y unifica tipografías (demada→demanda, espacios)."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    renombres = {k: v for k, v in MAPA_COLUMNAS.items() if k in df.columns}
    if renombres:
        df = df.rename(columns=renombres)
    extras = {}
    for c in df.columns:
        cl = str(c).strip().lower()
        if cl.startswith("demada mes"):
            extras[c] = cl.replace("demada mes", "demanda mes")
    if extras:
        df = df.rename(columns=extras)
    # Tras strip pueden quedar encabezados duplicados (p. ej. dos «factor escazes»).
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated(keep="first")].copy()
    return df


def limpiar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza tipos: numéricas a float (comas->puntos), texto saneado."""
    df = df.copy()

    for col in COLUMNAS_NUMERICAS:
        if col not in df.columns:
            continue
        serie = df[col]
        if isinstance(serie, pd.DataFrame):
            serie = serie.iloc[:, 0]
        serie = serie.astype(str).str.replace(",", ".", regex=False).str.strip()
        serie = serie.str.replace(r"[^\d\.\-\+]", "", regex=True)
        serie = pd.to_numeric(serie, errors="coerce")
        if col in _NO_NEGATIVAS:
            serie = serie.mask(serie < 0, 0)
        df[col] = serie.fillna(0)

    for col in COLUMNAS_TEXTO:
        if col not in df.columns:
            continue
        serie = df[col]
        if isinstance(serie, pd.DataFrame):
            serie = serie.iloc[:, 0]
        serie = serie.astype(str).str.strip()
        serie = serie.replace(["nan", "NaN", "NAN", ""], "Sin especificar")
        df[col] = serie

    return df


def transformar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega/recalcula columnas derivadas (mismas fórmulas que Perfilado)."""
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


def _elegir_hoja_datos(xl: pd.ExcelFile) -> str:
    """Preferir hoja ``data`` (Perfilado); si no, la primera hoja."""
    por_nombre = {str(h).strip().lower(): h for h in xl.sheet_names}
    if HOJA_DATOS in por_nombre:
        return por_nombre[HOJA_DATOS]
    for clave, nombre in por_nombre.items():
        if clave in {"data", "datos", "hoja1", "sheet1"} or "dato" in clave:
            return nombre
    return xl.sheet_names[0]


def _leer_excel_datos(origen: str | bytes) -> pd.DataFrame:
    if isinstance(origen, (bytes, bytearray)):
        xl = pd.ExcelFile(io.BytesIO(origen), engine="openpyxl")
    else:
        xl = pd.ExcelFile(origen, engine="openpyxl")
    hoja = _elegir_hoja_datos(xl)
    return pd.read_excel(xl, sheet_name=hoja)


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
    df = _leer_excel_datos(ruta)
    return preparar_dataframe_inventario(df)


def cargar_datos(
    ruta: Optional[str] = None,
) -> tuple[Optional[pd.DataFrame], Optional[str]]:
    """Carga por defecto desde ``data/sources/perfilado.xlsx`` (hoja data)."""
    ruta = ruta or ARCHIVO_EXCEL_PATH
    if not os.path.isfile(ruta):
        return None, (
            f"No se encontró `{NOMBRE_ARCHIVO_DEFECTO}` en data/sources. "
            "Suba un Excel con la misma estructura de columnas (hoja data)."
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
    """Mismo esquema; prioriza hoja ``data`` si existe."""
    try:
        df = _leer_excel_datos(file_bytes)
        return preparar_dataframe_inventario(df), None
    except ValueError as exc:
        return None, str(exc)
    except Exception as exc:  # noqa: BLE001
        if _es_error_archivo_abierto(exc):
            return None, MSG_ARCHIVO_EXCEL_ABIERTO
        return None, f"Error al leer el archivo subido: {exc}"


def existe_archivo(ruta: Optional[str] = None) -> bool:
    return os.path.isfile(ruta or ARCHIVO_EXCEL_PATH)
