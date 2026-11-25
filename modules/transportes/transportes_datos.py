"""Carga del Excel de Transportes (solo lectura).

Hoja oficial de clientes y rutas: ``Template clientes y rutas`` en
``data/basedatos_ transporte.xlsx``.
"""
from __future__ import annotations

import os

import pandas as pd

_DIR_MODULO = os.path.dirname(os.path.abspath(__file__))
NOMBRE_ARCHIVO = "basedatos_ transporte.xlsx"
HOJA_CLIENTES = "Template clientes y rutas"
RUTA_DEFECTO = os.path.join(_DIR_MODULO, "data", NOMBRE_ARCHIVO)

COL_CLIENTE = "Código de cliente"
COL_NOMBRE = "Nombre del cliente"
COL_SEGMENTO = "Segmento"
COL_DESPACHO = "Despachados desde:"
COL_PROVINCIA = "Provincia"
COL_CANTON = "Cantón"
COL_DISTRITO = "Distrito"
COL_LONGITUD = "Longitud"
COL_LATITUD = "Latitud"
COL_RUTA = "# de Ruta"
COL_NOMBRE_RUTA = "Nombre de la Ruta"
COL_UNIDADES = "Unidades vendidas"
COL_MARGEN = "Margen Bruto anual $"
COL_KM = "KM desde el origen"
COL_KM_ANIO = "# de km por año por cliente"
COL_PCT_DISTRIBUCION = "% Distribución"
COL_COSTO_DISTRIBUCION = "Costo Dist x cliente 1"
COL_TVA = "TVA"

# Perfilado: atributos del cliente y variables numéricas, en ese orden.
ATRIBUTOS_PERFIL: tuple[tuple[str, str], ...] = (
    (COL_CLIENTE, "Código de cliente"),
    (COL_NOMBRE, "Nombre del cliente"),
    (COL_SEGMENTO, "Segmento"),
    (COL_DESPACHO, "Despachados desde"),
    (COL_PROVINCIA, "Provincia"),
    (COL_CANTON, "Cantón"),
    (COL_DISTRITO, "Distrito"),
)
VARIABLES_PERFIL: tuple[tuple[str, str], ...] = (
    (COL_UNIDADES, "Unidades vendidas"),
    (COL_MARGEN, "Margen bruto"),
    (COL_KM, "Km desde el origen"),
    (COL_KM_ANIO, "Km por año por cliente"),
    (COL_PCT_DISTRIBUCION, "% Distribución"),
    (COL_COSTO_DISTRIBUCION, "Costo de distribución"),
    (COL_TVA, "TVA"),
)

VARIABLE_CLIENTES = "Clientes"
OPS_CALCULO = ("Suma", "Promedio")
CORTES_OTROS = (COL_PROVINCIA, COL_SEGMENTO, COL_DESPACHO)


def existe_archivo(ruta: str | None = None) -> bool:
    return os.path.isfile(ruta or RUTA_DEFECTO)


_COLUMNAS_TEXTO = (
    COL_CLIENTE,
    COL_NOMBRE,
    COL_SEGMENTO,
    COL_DESPACHO,
    COL_PROVINCIA,
    COL_CANTON,
    COL_DISTRITO,
    COL_RUTA,
    COL_NOMBRE_RUTA,
)


def preparar(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza nombres y tipos. Distrito mezcla texto y números en el Excel."""
    salida = df.copy()
    salida.columns = [str(c).strip() for c in salida.columns]
    for col in (
        COL_LATITUD,
        COL_LONGITUD,
        COL_UNIDADES,
        COL_MARGEN,
        COL_KM,
        COL_KM_ANIO,
        COL_PCT_DISTRIBUCION,
        COL_COSTO_DISTRIBUCION,
        COL_TVA,
    ):
        if col in salida.columns:
            salida[col] = pd.to_numeric(salida[col], errors="coerce")
    for col in _COLUMNAS_TEXTO:
        if col in salida.columns:
            salida[col] = salida[col].map(
                lambda v: "" if pd.isna(v) else str(v).strip()
            )
    return salida


def tabla_perfilado(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Arma el perfil: atributos y variables juntos. Devuelve la tabla y las etiquetas ausentes."""
    pares = list(ATRIBUTOS_PERFIL) + list(VARIABLES_PERFIL)
    faltantes = [etiqueta for origen, etiqueta in pares if origen not in df.columns]
    presentes = [(origen, etiqueta) for origen, etiqueta in pares if origen in df.columns]
    tabla = df[[origen for origen, _ in presentes]].rename(
        columns={origen: etiqueta for origen, etiqueta in presentes}
    )
    return tabla, faltantes


def etiquetas_atributos(df: pd.DataFrame) -> list[str]:
    return [etiqueta for origen, etiqueta in ATRIBUTOS_PERFIL if origen in df.columns]


def etiquetas_variables(df: pd.DataFrame) -> list[str]:
    """Clientes (conteo) más las variables numéricas presentes en la base."""
    presentes = [etiqueta for origen, etiqueta in VARIABLES_PERFIL if origen in df.columns]
    return [VARIABLE_CLIENTES, *presentes]


def _columna_de_etiqueta(pares: tuple[tuple[str, str], ...], etiqueta: str) -> str | None:
    for origen, nombre in pares:
        if nombre == etiqueta:
            return origen
    return None


def agregar_perfil(
    df: pd.DataFrame,
    atributos: list[str],
    variables: list[str],
    operacion: str = "Suma",
    acotar: str | dict[str, str] | None = None,
) -> pd.DataFrame:
    """Cruce de perfilado, de mayor a menor según la primera variable.

    Hasta tres atributos arman el grupo. «Clientes» cuenta códigos. Las demás
    variables se suman o se promedian. ``acotar`` deja un valor de cada atributo
    (una provincia, un cantón o el nombre de un distrito).
    """
    if not atributos or not variables:
        return pd.DataFrame()
    origenes: list[str] = []
    for etiqueta in atributos:
        columna = _columna_de_etiqueta(ATRIBUTOS_PERFIL, etiqueta)
        if columna is None or columna not in df.columns:
            return pd.DataFrame()
        origenes.append(columna)

    cortes = _cortes(atributos, acotar)
    if cortes:
        df = _filtrar_acotar(df, list(cortes), cortes)
        if df.empty:
            return pd.DataFrame()

    def _texto(serie: pd.Series) -> pd.Series:
        return serie.map(
            lambda v: "Sin dato" if pd.isna(v) or str(v).strip() == "" else str(v).strip()
        )

    trabajo = pd.DataFrame(
        {etiqueta: _texto(df[columna]) for etiqueta, columna in zip(atributos, origenes)}
    )
    trabajo["_codigo"] = df[COL_CLIENTE].to_numpy()
    for variable in variables:
        if variable == VARIABLE_CLIENTES:
            continue
        columna = _columna_de_etiqueta(VARIABLES_PERFIL, variable)
        if columna is None or columna not in df.columns:
            return pd.DataFrame()
        trabajo[variable] = pd.to_numeric(df[columna], errors="coerce").to_numpy()

    trabajo = _filtrar_acotar(trabajo, atributos, acotar)
    if trabajo.empty:
        return pd.DataFrame()

    nombre_x = " · ".join(atributos)
    if len(atributos) == 1:
        trabajo["_grupo"] = trabajo[atributos[0]]
    else:
        trabajo["_grupo"] = trabajo[atributos].astype(str).agg(" · ".join, axis=1)

    funcion = "mean" if operacion == "Promedio" else "sum"
    filas: list[dict[str, object]] = []
    for grupo, parte in trabajo.groupby("_grupo", dropna=False):
        fila: dict[str, object] = {nombre_x: grupo}
        for variable in variables:
            if variable == VARIABLE_CLIENTES:
                fila[variable] = int(parte["_codigo"].nunique())
            else:
                fila[variable] = getattr(parte[variable], funcion)()
        filas.append(fila)
    salida = pd.DataFrame(filas)
    return salida.sort_values(variables[0], ascending=False, kind="mergesort")


def recorte_perfil(
    df: pd.DataFrame,
    atributos: list[str],
    acotar: str | dict[str, str] | None = None,
) -> pd.DataFrame:
    """Clientes del cruce de perfilado, con la columna ``Zona`` para el mapa.

    La zona es el atributo más fino entre distrito, cantón y provincia. Si el
    cruce no usa ninguno de esos, usa el último atributo elegido.
    """
    if not atributos:
        return df.iloc[0:0].assign(Zona="")
    origenes: list[tuple[str, str]] = []
    for etiqueta in atributos:
        columna = _columna_de_etiqueta(ATRIBUTOS_PERFIL, etiqueta)
        if columna is None or columna not in df.columns:
            return df.iloc[0:0].assign(Zona="")
        origenes.append((etiqueta, columna))

    vista = _filtrar_acotar(df, [etiqueta for etiqueta, _ in origenes], acotar, origenes)
    if vista.empty:
        return vista.assign(Zona="")

    zona = next(
        (etiqueta for etiqueta in ("Distrito", "Cantón", "Provincia") if etiqueta in atributos),
        atributos[-1],
    )
    columna_zona = dict(origenes)[zona]
    vista = vista.copy()
    vista["Zona"] = vista[columna_zona].map(
        lambda v: "Sin dato" if pd.isna(v) or str(v).strip() == "" else str(v).strip()
    )
    return vista


def _cortes(atributos: list[str], acotar: str | dict[str, str] | None) -> dict[str, str]:
    if not acotar or not atributos:
        return {}
    if isinstance(acotar, str):
        return {atributos[0]: acotar}
    return {etiqueta: valor for etiqueta, valor in acotar.items() if valor}


def _filtrar_acotar(
    tabla: pd.DataFrame,
    atributos: list[str],
    acotar: str | dict[str, str] | None,
    origenes: list[tuple[str, str]] | None = None,
) -> pd.DataFrame:
    """Deja las filas de los nombres elegidos. ``origenes`` traduce etiqueta → columna."""
    columnas = dict(origenes) if origenes else {}
    vista = tabla
    for etiqueta, valor in _cortes(atributos, acotar).items():
        columna = columnas.get(etiqueta)
        if columna is None and etiqueta in vista.columns:
            columna = etiqueta
        if columna is None:
            columna = _columna_de_etiqueta(ATRIBUTOS_PERFIL, etiqueta)
        if columna is None or columna not in vista.columns:
            continue
        texto = vista[columna].map(lambda v: "" if pd.isna(v) else str(v).strip())
        vista = vista.loc[texto == valor]
    return vista


def valores_atributo(
    df: pd.DataFrame,
    etiqueta: str,
    filtros: dict[str, str] | None = None,
) -> list[str]:
    """Nombres distintos de un atributo. ``filtros`` reduce al cantón o la provincia ya elegidos."""
    columna = _columna_de_etiqueta(ATRIBUTOS_PERFIL, etiqueta)
    if columna is None or columna not in df.columns:
        return []
    vista = _filtrar_acotar(df, list(filtros or {}), filtros or None)
    if columna not in vista.columns:
        return []
    serie = vista[columna].map(lambda v: "" if pd.isna(v) else str(v).strip())
    return sorted(v for v in serie.unique() if v)


def cargar_clientes(ruta: str | None = None) -> pd.DataFrame:
    """Lee la hoja de clientes y normaliza nombres de columna (espacios)."""
    origen = ruta or RUTA_DEFECTO
    return preparar(pd.read_excel(origen, sheet_name=HOJA_CLIENTES))


def columna_corte(accion: str, corte: str, otro: str | None = None) -> str:
    """Columna del DataFrame que corresponde al corte elegido en el menú."""
    if accion == "mapas" and corte == "Otros":
        if otro in CORTES_OTROS:
            return otro
        return COL_PROVINCIA
    if corte == "Cantón":
        return COL_CANTON
    return COL_DISTRITO
