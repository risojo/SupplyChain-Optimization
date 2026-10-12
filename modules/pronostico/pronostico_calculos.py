"""Cálculos del módulo Pronóstico (sin Streamlit).

Fórmulas oficiales del Excel maestro (``data/sources/perfilado.xlsx``, hoja ``data``):

- ``pronostico``           = AVERAGE(demanda mes 1..12)
- ``desviacion standart``  = STDEV.S(demanda mes 1..12)
- ``stock seguridad k``    = nivel de servicio (probabilidad, p. ej. 0.8)
- ``pronostico ajustado``  = NORMINV(nivel de servicio, pronostico, desviacion)

Columna derivada (la escribe ``pronostico_excel`` al cargar la app, después de ``EVAI``):

- ``fill rate deseado``    = según ``clase``: A+ 99.7 %, A 97 %, B 90 %, C 60 %, C- 50 %

El resto (tendencia, métodos alternativos, estacionalidad, Monte Carlo) son
análisis de apoyo; no reemplazan las columnas oficiales.
"""
from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np
import pandas as pd

_RAIZ_PROYECTO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARCHIVO_EXCEL_PATH = os.path.join(_RAIZ_PROYECTO, "data", "sources", "perfilado.xlsx")
HOJA_DATOS = "data"

COLUMNAS_ATRIBUTO = ("codigo", "descripcion", "categoria", "subcategoria", "proveedor", "clase")

COL_PRONOSTICO = "pronostico"
COL_DESVIACION = "desviacion estandar"
COL_NIVEL_SERVICIO = "stock seguridad k"
COL_PRONOSTICO_AJUSTADO = "pronostico ajustado"

NIVEL_SERVICIO_DEFECTO = 0.8
TOLERANCIA_CERTIFICACION = 1e-6

COL_CLASE = "clase"
COL_FILL_RATE = "fill rate deseado"
# Fill rate deseado por clase ABC (definido por el usuario); base del stock de seguridad en Inventarios.
FILL_RATE_POR_CLASE = {
    "A+": 0.997,
    "A": 0.97,
    "B": 0.90,
    "C": 0.60,
    "C-": 0.50,
}

# Certificación: CV (desviación / pronóstico) entre 0 y este límite → apto para modelo estadístico.
CV_MAX_CERTIFICADO = 0.30
COL_CERTIFICACION = "certificacion"
COL_MODELO_SUGERIDO = "modelo sugerido"
COL_CUADRA_EXCEL = "cuadra con excel"
CERTIFICADO = "Certificado"
NO_CERTIFICADO = "No certificado"
SIN_DEMANDA = "Sin demanda"
MODELO_ESTADISTICO = "Estadístico (distribución normal)"
MODELO_ALTERNATIVO = "Otro modelo o demanda anual"

# Pronóstico LRI (solo SKUs certificados): promedio 12 meses + K × σ, K = NORMSINV(fill rate deseado).
COL_K = "k"
COL_SEGURIDAD_K = "seguridad k sigma"
COL_PRONOSTICO_LRI = "pronostico lri"

_RE_MES = re.compile(r"^dem[a-z]*[\s_]*mes[\s_]*(\d{1,2})$")

_ALIAS_COLUMNAS = {
    "desviacion standart": COL_DESVIACION,
    "desviacion standard": COL_DESVIACION,
    "desviación standart": COL_DESVIACION,
    "desviación estándar": COL_DESVIACION,
    "desviacion estandar": COL_DESVIACION,
    "pronóstico": COL_PRONOSTICO,
    "forecast": COL_PRONOSTICO,
    "pronóstico ajustado": COL_PRONOSTICO_AJUSTADO,
    "forecast ajustado": COL_PRONOSTICO_AJUSTADO,
    "stock de seguridad k": COL_NIVEL_SERVICIO,
    "stock seguridad k'": COL_NIVEL_SERVICIO,
    "cod_producto": "codigo",
    "cat_producto": "categoria",
    "subcat_producto": "subcategoria",
    "desc_producto": "descripcion",
}


def _nombre_canonico(col: object) -> str:
    nombre = str(col).strip().lower()
    nombre = re.sub(r"\s+", " ", nombre)
    m = _RE_MES.match(nombre)
    if m:
        return f"demanda mes {int(m.group(1))}"
    return _ALIAS_COLUMNAS.get(nombre, nombre)


def normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """Unifica encabezados (``demada mes 1`` → ``demanda mes 1``, etc.)."""
    out = df.copy()
    out.columns = [_nombre_canonico(c) for c in out.columns]
    return out.loc[:, ~out.columns.duplicated()]


def columnas_meses(df: pd.DataFrame) -> list[str]:
    """Columnas ``demanda mes N`` ordenadas por N."""
    meses = []
    for c in df.columns:
        m = re.fullmatch(r"demanda mes (\d{1,2})", str(c))
        if m:
            meses.append((int(m.group(1)), c))
    return [c for _, c in sorted(meses)]


MSG_ARCHIVO_ABIERTO = "El archivo Excel está abierto en otra aplicación. Ciérrelo o suba una copia."


def _origen(fuente: str | bytes | None) -> str | io.BytesIO | None:
    origen = fuente if fuente is not None else ARCHIVO_EXCEL_PATH
    if isinstance(origen, (bytes, bytearray)):
        return io.BytesIO(origen)
    return origen if os.path.isfile(origen) else None


def es_columna_pronostico(nombre: object) -> bool:
    """True si la columna del Excel la usa el pronóstico (identificación o demanda mensual)."""
    canon = _nombre_canonico(nombre)
    return canon in COLUMNAS_ATRIBUTO or bool(re.fullmatch(r"demanda mes \d{1,2}", canon))


def fill_rate_deseado(clase: pd.Series) -> pd.Series:
    """Fill rate deseado según la clase (``A+``, ``A``, ``B``, ``C``, ``C-``); otra clase → vacío."""
    normalizada = clase.astype("string").str.strip().str.upper()
    return normalizada.map(FILL_RATE_POR_CLASE).astype(float)


def agregar_fill_rate(df: pd.DataFrame) -> pd.DataFrame:
    """Recalcula ``fill rate deseado`` según ``clase``: en su lugar si existe, si no al final."""
    col_clase = next((c for c in df.columns if _nombre_canonico(c) == COL_CLASE), None)
    if col_clase is None:
        return df
    out = df.copy()
    col_fill = next((c for c in out.columns if _nombre_canonico(c) == COL_FILL_RATE), COL_FILL_RATE)
    out[col_fill] = fill_rate_deseado(out[col_clase])
    return out


def leer_archivo_completo(
    fuente: str | bytes | None = None,
) -> tuple[dict[str, pd.DataFrame] | None, str | None]:
    """Todas las hojas del Excel tal como vienen (sin renombrar ni recalcular)."""
    origen = _origen(fuente)
    if origen is None:
        return None, f"No se encontró el archivo de datos: {fuente or ARCHIVO_EXCEL_PATH}"
    try:
        xl = pd.ExcelFile(origen, engine="openpyxl")
        hojas = {}
        for hoja in xl.sheet_names:
            es_datos = str(hoja).strip().lower() == HOJA_DATOS
            df = pd.read_excel(xl, sheet_name=hoja, header=0 if es_datos else None)
            df = df.dropna(how="all")
            if not es_datos:
                df = df.dropna(axis=1, how="all")
            hojas[hoja] = df
        return hojas, None
    except PermissionError:
        return None, MSG_ARCHIVO_ABIERTO


def cargar_demanda(fuente: str | bytes | None = None) -> tuple[pd.DataFrame | None, str | None]:
    """Lee la hoja ``data`` y deja solo filas de SKU con demanda mensual numérica."""
    origen = _origen(fuente)
    if origen is None:
        return None, f"No se encontró el archivo de datos: {fuente or ARCHIVO_EXCEL_PATH}"
    try:
        df = pd.read_excel(origen, sheet_name=HOJA_DATOS)
    except PermissionError:
        return None, MSG_ARCHIVO_ABIERTO
    except ValueError as exc:
        return None, f"El Excel no tiene la hoja '{HOJA_DATOS}': {exc}"

    df = normalizar_columnas(df)
    meses = columnas_meses(df)
    if len(meses) < 3:
        return None, "El Excel necesita al menos 3 columnas 'demanda mes N'."
    if "codigo" not in df.columns:
        return None, "El Excel no tiene la columna 'codigo'."

    df = df[df["codigo"].notna()].copy()
    df["codigo"] = df["codigo"].astype(str).str.strip()
    for c in COLUMNAS_ATRIBUTO:
        if c in df.columns and c != "codigo":
            df[c] = df[c].astype("string").str.strip()
    for c in [*meses, COL_PRONOSTICO, COL_DESVIACION, COL_NIVEL_SERVICIO, COL_PRONOSTICO_AJUSTADO]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=meses, how="all").reset_index(drop=True)
    return df, None


def nivel_servicio_excel(df: pd.DataFrame) -> float:
    """Nivel de servicio más frecuente en el Excel (o el valor por defecto)."""
    if COL_NIVEL_SERVICIO in df.columns:
        serie = df[COL_NIVEL_SERVICIO].dropna()
        serie = serie[(serie > 0) & (serie < 1)]
        if not serie.empty:
            return float(serie.mode().iloc[0])
    return NIVEL_SERVICIO_DEFECTO


def pronostico_ajustado(media: float, desviacion: float, nivel_servicio: float) -> float:
    """Equivalente a ``NORMINV(nivel, media, desviacion)`` de Excel."""
    if not np.isfinite(media):
        return float("nan")
    if not np.isfinite(desviacion) or desviacion <= 0:
        return float(media)
    return NormalDist(media, desviacion).inv_cdf(nivel_servicio)


def _pendiente(valores: np.ndarray) -> float:
    mask = np.isfinite(valores)
    if mask.sum() < 2:
        return float("nan")
    x = np.arange(len(valores))[mask]
    return float(np.polyfit(x, valores[mask], 1)[0])


def certificar_cv(cv: float) -> str:
    """«Certificado» si 0 ≤ CV ≤ ``CV_MAX_CERTIFICADO``; sin demanda promedio no hay CV."""
    if not np.isfinite(cv):
        return SIN_DEMANDA
    return CERTIFICADO if 0 <= cv <= CV_MAX_CERTIFICADO else NO_CERTIFICADO


def modelo_sugerido(certificacion: str) -> str:
    if certificacion == CERTIFICADO:
        return MODELO_ESTADISTICO
    if certificacion == NO_CERTIFICADO:
        return MODELO_ALTERNATIVO
    return "—"


def factor_k(fill_rate) -> np.ndarray:
    """Factor de seguridad K = NORMSINV(fill rate deseado); fuera de (0, 1) o vacío → NaN."""
    valores = np.atleast_1d(pd.to_numeric(pd.Series(fill_rate), errors="coerce").to_numpy(dtype=float))
    return np.array([NormalDist().inv_cdf(p) if 0 < p < 1 else np.nan for p in valores])


def calcular_pronostico(df: pd.DataFrame, nivel_servicio: float | None = None) -> pd.DataFrame:
    """Recalcula el pronóstico por SKU, lo certifica por CV y lo compara con el Excel.

    ``pronostico lri`` = promedio 12 meses + K × σ, con K según el fill rate deseado de la
    clase; solo para SKUs certificados (los demás quedan vacíos hasta definir su política).
    Si ``nivel_servicio`` es None se usa el de cada fila del Excel.
    """
    meses = columnas_meses(df)
    demanda = df[meses].to_numpy(dtype=float)
    out = agregar_fill_rate(df[[c for c in COLUMNAS_ATRIBUTO if c in df.columns]].copy())

    media = np.nanmean(demanda, axis=1)
    desv = pd.DataFrame(demanda).std(axis=1, ddof=1).to_numpy()
    if nivel_servicio is None and COL_NIVEL_SERVICIO in df.columns:
        nivel = df[COL_NIVEL_SERVICIO].fillna(NIVEL_SERVICIO_DEFECTO).to_numpy(dtype=float)
    else:
        nivel = np.full(len(df), nivel_servicio or NIVEL_SERVICIO_DEFECTO, dtype=float)

    out["demanda total"] = np.nansum(demanda, axis=1)
    out["pronostico calc"] = media
    out["desviacion calc"] = desv
    out["nivel servicio"] = nivel
    out["z"] = [NormalDist().inv_cdf(n) for n in nivel]
    out["pronostico ajustado calc"] = [
        pronostico_ajustado(m, s, n) for m, s, n in zip(media, desv, nivel)
    ]
    out["stock seguridad mes"] = out["pronostico ajustado calc"] - out["pronostico calc"]
    with np.errstate(divide="ignore", invalid="ignore"):
        cv = np.where(media > 0, desv / media, np.nan)
    out["cv"] = cv
    out[COL_CERTIFICACION] = [certificar_cv(v) for v in cv]
    out[COL_MODELO_SUGERIDO] = out[COL_CERTIFICACION].map(modelo_sugerido)

    k = factor_k(out[COL_FILL_RATE]) if COL_FILL_RATE in out.columns else np.full(len(out), np.nan)
    certificado = (out[COL_CERTIFICACION] == CERTIFICADO).to_numpy()
    seguridad = k * desv
    out[COL_K] = k
    out[COL_SEGURIDAD_K] = np.where(certificado, seguridad, np.nan)
    out[COL_PRONOSTICO_LRI] = np.where(certificado, media + seguridad, np.nan)

    pendientes = np.array([_pendiente(fila) for fila in demanda])
    out["tendencia mensual"] = pendientes
    with np.errstate(divide="ignore", invalid="ignore"):
        out["tendencia % mes"] = np.where(media > 0, pendientes / media, np.nan)

    out[COL_CUADRA_EXCEL] = _cuadra_con_excel(df, out)
    return out


def _cuadra_con_excel(df: pd.DataFrame, calc: pd.DataFrame) -> pd.Series:
    """«Sí» si los valores oficiales del Excel coinciden con el recálculo."""
    pares = [
        (COL_PRONOSTICO, "pronostico calc"),
        (COL_DESVIACION, "desviacion calc"),
        (COL_PRONOSTICO_AJUSTADO, "pronostico ajustado calc"),
    ]
    pares = [(o, c) for o, c in pares if o in df.columns]
    if not pares:
        return pd.Series("Sin columnas oficiales", index=calc.index)
    ok = pd.Series(True, index=calc.index)
    for oficial, calculado in pares:
        a = df[oficial].to_numpy(dtype=float)
        b = calc[calculado].to_numpy(dtype=float)
        escala = np.maximum(1.0, np.abs(b))
        ok &= pd.Series(np.isfinite(a) & (np.abs(a - b) <= TOLERANCIA_CERTIFICACION * escala), index=calc.index)
    return ok.map({True: "Sí", False: "No"})


def resumen_certificacion(calc: pd.DataFrame, columna: str) -> pd.DataFrame:
    """SKUs certificados y no certificados por grupo (categoría, subcategoría o proveedor).

    Ordenado para ver primero los grupos con más SKUs de demanda inestable.
    """
    grupos = calc[columna].fillna("(sin dato)").astype(str).str.strip()
    no_cert = calc[COL_CERTIFICACION] != CERTIFICADO
    resumen = (
        pd.DataFrame({"grupo": grupos, "no_certificados": no_cert.astype(int)})
        .groupby("grupo", sort=False)
        .agg(skus=("no_certificados", "size"), no_certificados=("no_certificados", "sum"))
        .reset_index()
    )
    resumen["certificados"] = resumen["skus"] - resumen["no_certificados"]
    resumen["pct_no_certificados"] = resumen["no_certificados"] / resumen["skus"]
    return resumen.sort_values(
        ["no_certificados", "pct_no_certificados", "grupo"], ascending=[False, False, True]
    ).reset_index(drop=True)[["grupo", "skus", "certificados", "no_certificados", "pct_no_certificados"]]


def consolidar_pronostico(calc: pd.DataFrame, columna: str) -> pd.DataFrame:
    """Pronóstico mensual de los SKUs certificados sumado por grupo (categoría, subcategoría, proveedor)."""
    base = calc[np.isfinite(calc[COL_PRONOSTICO_LRI].to_numpy(dtype=float))]
    grupos = base[columna].fillna("(sin dato)").astype(str).str.strip()
    resumen = (
        pd.DataFrame(
            {
                "grupo": grupos,
                "promedio": base["pronostico calc"],
                "seguridad": base[COL_SEGURIDAD_K],
                "pronostico": base[COL_PRONOSTICO_LRI],
            }
        )
        .groupby("grupo", sort=False)
        .agg(
            skus=("pronostico", "size"),
            promedio=("promedio", "sum"),
            seguridad=("seguridad", "sum"),
            pronostico=("pronostico", "sum"),
        )
        .reset_index()
    )
    total = resumen["pronostico"].sum()
    resumen["pct_total"] = resumen["pronostico"] / total if total else np.nan
    return resumen.sort_values(["pronostico", "grupo"], ascending=[False, True]).reset_index(drop=True)


@dataclass(frozen=True)
class ResumenDispersion:
    media: float
    desviacion: float
    cv: float
    minimo: float
    maximo: float
    meses: int
    meses_fuera_1sigma: int
    meses_sin_demanda: int


def resumen_dispersion(valores) -> ResumenDispersion:
    """Qué tan dispersa es la demanda mensual de un SKU (apoyo a la certificación por CV)."""
    serie = np.asarray(valores, dtype=float)
    serie = serie[np.isfinite(serie)]
    if serie.size == 0:
        nan = float("nan")
        return ResumenDispersion(nan, nan, nan, nan, nan, 0, 0, 0)
    media = float(serie.mean())
    desv = float(serie.std(ddof=1)) if serie.size > 1 else 0.0
    return ResumenDispersion(
        media=media,
        desviacion=desv,
        cv=desv / media if media > 0 else float("nan"),
        minimo=float(serie.min()),
        maximo=float(serie.max()),
        meses=int(serie.size),
        meses_fuera_1sigma=int((np.abs(serie - media) > desv).sum()),
        meses_sin_demanda=int((serie <= 0).sum()),
    )


@dataclass(frozen=True)
class ResultadoMetodo:
    metodo: str
    pronostico: float
    mad: float
    mape: float
    sesgo: float


def _pronostico_siguiente(historia: np.ndarray, metodo: str, ventana: int, alpha: float) -> float:
    if len(historia) == 0:
        return float("nan")
    if metodo == "Promedio simple (oficial)":
        return float(np.mean(historia))
    if metodo == "Promedio móvil":
        return float(np.mean(historia[-ventana:]))
    if metodo == "Suavizamiento exponencial":
        nivel = historia[0]
        for v in historia[1:]:
            nivel = alpha * v + (1 - alpha) * nivel
        return float(nivel)
    if metodo == "Regresión lineal":
        if len(historia) < 2:
            return float(historia[-1])
        b, a = np.polyfit(np.arange(len(historia)), historia, 1)
        return float(max(0.0, a + b * len(historia)))
    raise ValueError(f"Método desconocido: {metodo}")


METODOS = (
    "Promedio simple (oficial)",
    "Promedio móvil",
    "Suavizamiento exponencial",
    "Regresión lineal",
)


def comparar_metodos(
    serie: np.ndarray | list[float],
    ventana: int = 3,
    alpha: float = 0.3,
    inicio_backtest: int = 3,
) -> list[ResultadoMetodo]:
    """Pronóstico del siguiente mes por método + error de backtest un paso adelante."""
    valores = np.asarray(serie, dtype=float)
    valores = valores[np.isfinite(valores)]
    resultados = []
    for metodo in METODOS:
        errores, pct = [], []
        for t in range(inicio_backtest, len(valores)):
            pred = _pronostico_siguiente(valores[:t], metodo, ventana, alpha)
            err = valores[t] - pred
            errores.append(err)
            if valores[t] != 0:
                pct.append(abs(err) / abs(valores[t]))
        errores_arr = np.asarray(errores, dtype=float)
        resultados.append(
            ResultadoMetodo(
                metodo=metodo,
                pronostico=_pronostico_siguiente(valores, metodo, ventana, alpha),
                mad=float(np.mean(np.abs(errores_arr))) if errores else float("nan"),
                mape=float(np.mean(pct)) if pct else float("nan"),
                sesgo=float(np.mean(errores_arr)) if errores else float("nan"),
            )
        )
    return resultados


def indices_estacionales(df: pd.DataFrame, agrupar_por: str | None = None) -> pd.DataFrame:
    """Índice mensual = demanda del mes / promedio mensual del grupo (1.0 = normal)."""
    meses = columnas_meses(df)
    if agrupar_por and agrupar_por in df.columns:
        totales = df.groupby(agrupar_por, dropna=True)[meses].sum()
    else:
        totales = pd.DataFrame([df[meses].sum()], index=["Total"])
    promedio = totales.mean(axis=1).replace(0, np.nan)
    indices = totales.div(promedio, axis=0)
    indices.columns = [f"Mes {i + 1}" for i in range(len(meses))]
    return indices


def simular_montecarlo(
    media: float,
    desviacion: float,
    n_simulaciones: int = 10_000,
    semilla: int | None = 42,
) -> np.ndarray:
    """Demanda mensual simulada ~ Normal(media, desviación), truncada en 0."""
    rng = np.random.default_rng(semilla)
    sigma = desviacion if np.isfinite(desviacion) and desviacion > 0 else 0.0
    return np.maximum(0.0, rng.normal(media, sigma, n_simulaciones))
