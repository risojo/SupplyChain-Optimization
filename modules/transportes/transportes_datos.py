"""Carga del Excel de Transportes (solo lectura).

Hoja oficial de clientes y rutas: ``Template clientes y rutas`` en
``data/basedatos_ transporte.xlsx``.
"""
from __future__ import annotations

import math
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


MIN_SEGMENTO = 15
MAX_SEGMENTO = 25


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distancia aproximada en km entre dos puntos (lat, lon)."""
    dlat = (a[0] - b[0]) * 111.0
    coseno = math.cos(math.radians((a[0] + b[0]) / 2))
    dlon = (a[1] - b[1]) * 111.0 * max(0.2, coseno)
    return math.hypot(dlat, dlon)


def orden_por_cercania(latitudes: list[float], longitudes: list[float]) -> list[int]:
    """Recorre cada cliente y sigue al más cercano que aún no visitó."""
    n = len(latitudes)
    if n == 0:
        return []
    puntos = list(zip(latitudes, longitudes, strict=False))
    actual = max(range(n), key=lambda i: puntos[i][0])
    vistos = {actual}
    orden = [actual]
    while len(orden) < n:
        actual = min(
            (i for i in range(n) if i not in vistos),
            key=lambda i: _km(puntos[orden[-1]], puntos[i]),
        )
        vistos.add(actual)
        orden.append(actual)
    return orden


def _tamaños_segmento(n: int, objetivo: int, minimo: int, maximo: int) -> list[int]:
    """Parte n clientes en grupos de minimo a maximo, lo más cerca posible del objetivo.

    Si no caben todos en ese rango, el último número es el sobrante (menor que minimo)
    y se une después a un distrito vecino.
    """
    if n <= maximo:
        return [n]
    k_min = math.ceil(n / maximo)
    k_max = n // minimo
    opciones: list[list[int]] = []
    if k_max >= k_min:
        for k in range(k_min, k_max + 1):
            base, extra = divmod(n, k)
            tamanos = [base + 1] * extra + [base] * (k - extra)
            if min(tamanos) >= minimo and max(tamanos) <= maximo:
                opciones.append(tamanos)
    if opciones:
        opciones.sort(key=lambda tamanos: (sum(abs(t - objetivo) for t in tamanos), len(tamanos)))
        return opciones[0]

    grupos: list[int] = []
    resta = n
    while resta > maximo:
        grupos.append(objetivo)
        resta -= objetivo
    if resta:
        grupos.append(resta)
    return grupos


def _compacto(puntos: list[tuple[float, float]], cantidad: int) -> list[int]:
    """Los `cantidad` puntos más juntos, medidos desde su centro más cerrado."""
    n = len(puntos)
    if cantidad >= n:
        return list(range(n))
    mejor: tuple[float, list[int]] | None = None
    for i, origen in enumerate(puntos):
        orden = sorted(range(n), key=lambda j: _km(origen, puntos[j]))[:cantidad]
        radio = sum(_km(origen, puntos[j]) for j in orden)
        if mejor is None or radio < mejor[0]:
            mejor = (radio, orden)
    return mejor[1] if mejor else list(range(cantidad))


def _partir_puntos(
    puntos: list[tuple[float, float]],
    tamanos: list[int],
) -> list[list[int]]:
    """Reparte los puntos en grupos de esos tamaños, cada uno lo más cerrado posible."""
    if len(tamanos) == 1:
        return [list(range(len(puntos)))]
    validos = [t for t in tamanos if t >= MIN_SEGMENTO]
    sobra = [t for t in tamanos if t < MIN_SEGMENTO]
    if sobra or len(validos) != len(tamanos):
        grupos: list[list[int]] = []
        libres = list(range(len(puntos)))
        for cantidad in validos:
            coords = [puntos[i] for i in libres]
            elegidos = _compacto(coords, cantidad)
            grupos.append([libres[i] for i in elegidos])
            quitar = set(grupos[-1])
            libres = [i for i in libres if i not in quitar]
        if libres:
            grupos.append(libres)
        return grupos

    # Semillas lejanas y cupo exacto. Se repite para acercar cada grupo a su centro.
    n = len(puntos)
    k = len(tamanos)
    centro = (
        sum(p[0] for p in puntos) / n,
        sum(p[1] for p in puntos) / n,
    )
    semillas = [max(range(n), key=lambda i: _km(puntos[i], centro))]
    while len(semillas) < k:
        semillas.append(
            max(
                (i for i in range(n) if i not in semillas),
                key=lambda i: min(_km(puntos[i], puntos[s]) for s in semillas),
            )
        )
    centros = [puntos[i] for i in semillas]
    mejor: tuple[float, list[int]] | None = None
    for _ in range(10):
        distancias = [
            ( _km(puntos[i], centros[j]), i, j) for i in range(n) for j in range(k)
        ]
        distancias.sort()
        asignado = [-1] * n
        cupo = list(tamanos)
        for _, i, j in distancias:
            if asignado[i] != -1 or cupo[j] <= 0:
                continue
            asignado[i] = j
            cupo[j] -= 1
        for i in range(n):
            if asignado[i] != -1:
                continue
            for j in sorted(range(k), key=lambda h: _km(puntos[i], centros[h])):
                if cupo[j] > 0:
                    asignado[i] = j
                    cupo[j] -= 1
                    break
        costo = 0.0
        nuevos: list[tuple[float, float]] = []
        for j in range(k):
            miembros = [puntos[i] for i in range(n) if asignado[i] == j]
            if not miembros:
                nuevos.append(centros[j])
                continue
            nuevo = (
                sum(p[0] for p in miembros) / len(miembros),
                sum(p[1] for p in miembros) / len(miembros),
            )
            nuevos.append(nuevo)
            costo += sum(_km(p, nuevo) for p in miembros)
        if mejor is None or costo < mejor[0]:
            mejor = (costo, asignado[:])
        if nuevos == centros:
            break
        centros = nuevos
    grupos = [[] for _ in tamanos]
    for i, j in enumerate(mejor[1] if mejor else [0] * n):
        grupos[j].append(i)
    return grupos


def segmentar_por_cercania(
    df: pd.DataFrame,
    columna: str,
    objetivo: int,
    minimo: int = MIN_SEGMENTO,
    maximo: int = MAX_SEGMENTO,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Segmentos de clientes cercanos, de `minimo` a `maximo`, apuntando a `objetivo`.

    Un distrito (o cantón) que ya cae en el rango queda entero. Uno más grande se
    parte en grupos apretados por latitud y longitud. Uno más chico se pega al
    distrito vecino que todavía tenga cupo.
    """
    vacio = pd.DataFrame()
    if columna not in df.columns or COL_LATITUD not in df.columns or COL_LONGITUD not in df.columns:
        return vacio, vacio
    objetivo = min(maximo, max(minimo, int(objetivo)))
    puntos = df.dropna(subset=[COL_LATITUD, COL_LONGITUD]).copy()
    if puntos.empty:
        return vacio, vacio
    puntos["_zona"] = puntos[columna].map(
        lambda v: "Sin dato" if pd.isna(v) or str(v).strip() == "" else str(v).strip()
    )
    if columna == COL_DISTRITO and COL_CANTON in puntos.columns:
        canton = puntos[COL_CANTON].map(
            lambda v: "Sin dato" if pd.isna(v) or str(v).strip() == "" else str(v).strip()
        )
        puntos["_zona"] = canton + " · " + puntos["_zona"]

    piezas: list[dict[str, object]] = []
    for zona, grupo in puntos.groupby("_zona", sort=False):
        idx = list(grupo.index)
        coords = list(zip(grupo[COL_LATITUD].astype(float), grupo[COL_LONGITUD].astype(float)))
        tamanos = _tamaños_segmento(len(idx), objetivo, minimo, maximo)
        if len(tamanos) == 1 and minimo <= tamanos[0] <= maximo:
            tipo = "completo"
        elif any(t < minimo for t in tamanos):
            tipo = "partido"
        else:
            tipo = "partido"
        for miembros in _partir_puntos(coords, tamanos):
            elegidos = [idx[i] for i in miembros]
            filas = puntos.loc[elegidos]
            n = len(elegidos)
            piezas.append(
                {
                    "idx": elegidos,
                    "centro": (
                        float(filas[COL_LATITUD].mean()),
                        float(filas[COL_LONGITUD].mean()),
                    ),
                    "zonas": [str(zona)],
                    "tipo": "pequeño" if n < minimo else tipo,
                }
            )

    def _unir(a: dict[str, object], b: dict[str, object]) -> dict[str, object]:
        idx = list(a["idx"]) + list(b["idx"])
        filas = puntos.loc[idx]
        zonas = list(dict.fromkeys(list(a["zonas"]) + list(b["zonas"])))
        return {
            "idx": idx,
            "centro": (float(filas[COL_LATITUD].mean()), float(filas[COL_LONGITUD].mean())),
            "zonas": zonas,
            "tipo": "unido",
        }

    while any(len(p["idx"]) < minimo for p in piezas):
        chicos = [i for i, p in enumerate(piezas) if len(p["idx"]) < minimo]
        mejor: tuple[float, int, int] | None = None
        for i in chicos:
            for j in range(len(piezas)):
                if i == j:
                    continue
                if len(piezas[i]["idx"]) + len(piezas[j]["idx"]) > maximo:
                    continue
                distancia = _km(piezas[i]["centro"], piezas[j]["centro"])
                if mejor is None or distancia < mejor[0]:
                    mejor = (distancia, i, j)
        if mejor is None:
            break
        _, i, j = mejor
        piezas[i] = _unir(piezas[i], piezas[j])
        del piezas[j]

    def _refrescar(pieza: dict[str, object]) -> None:
        filas = puntos.loc[list(pieza["idx"])]
        pieza["centro"] = (
            float(filas[COL_LATITUD].mean()),
            float(filas[COL_LONGITUD].mean()),
        )
        pieza["zonas"] = list(dict.fromkeys(filas["_zona"].astype(str).tolist()))

    while any(len(p["idx"]) < minimo for p in piezas):
        chicos = [i for i, p in enumerate(piezas) if len(p["idx"]) < minimo]
        prestamo: tuple[float, int, int, int] | None = None
        for i in chicos:
            falta = minimo - len(piezas[i]["idx"])
            for j in range(len(piezas)):
                if i == j or len(piezas[j]["idx"]) - falta < minimo:
                    continue
                distancia = _km(piezas[i]["centro"], piezas[j]["centro"])
                if prestamo is None or distancia < prestamo[0]:
                    prestamo = (distancia, i, j, falta)
        if prestamo is None:
            break
        _, i, j, falta = prestamo
        orden = sorted(
            list(piezas[j]["idx"]),
            key=lambda ix: _km(
                (float(puntos.at[ix, COL_LATITUD]), float(puntos.at[ix, COL_LONGITUD])),
                piezas[i]["centro"],
            ),
        )
        mudan = orden[:falta]
        piezas[i]["idx"] = list(piezas[i]["idx"]) + mudan
        piezas[i]["tipo"] = "unido"
        _refrescar(piezas[i])
        piezas[j]["idx"] = orden[falta:]
        _refrescar(piezas[j])

    piezas.sort(key=lambda p: (-p["centro"][0], p["centro"][1]))
    salida = puntos.copy()
    salida["Segmento"] = ""
    filas_resumen: list[dict[str, object]] = []
    for numero, pieza in enumerate(piezas, start=1):
        nombre = f"S{numero:02d}"
        salida.loc[pieza["idx"], "Segmento"] = nombre
        zonas = list(pieza["zonas"])
        filas_resumen.append(
            {
                "Segmento": nombre,
                "Clientes": len(pieza["idx"]),
                "Lugares": " · ".join(zonas),
                "Zonas": len(zonas),
                "Forma": {
                    "completo": "En rango",
                    "partido": "Partido por cercanía",
                    "pequeño": "Por debajo de 15",
                    "unido": "Unido al vecino",
                }[str(pieza["tipo"])],
            }
        )
    resumen = pd.DataFrame(filas_resumen)
    if not resumen.empty:
        resumen = resumen.sort_values(["Clientes", "Segmento"], ascending=[False, True], kind="mergesort")
    return salida, resumen


def columna_corte(accion: str, corte: str, otro: str | None = None) -> str:
    """Columna del DataFrame que corresponde al corte elegido en el menú."""
    if accion == "mapas" and corte == "Otros":
        if otro in CORTES_OTROS:
            return otro
        return COL_PROVINCIA
    if corte == "Cantón":
        return COL_CANTON
    return COL_DISTRITO
