"""Parámetros generales de Inventarios (sin base de datos).

Editables en disco (dos carpetas):
- ``parametros_base/parametros.json`` — inicio/base (solo con «Actualizar parámetros base»).
- ``parametros_actuales/parametros.json`` — últimos guardados (se cargan al abrir la app).

Estructura de casillas: ``parametros_defaults.json``.
Calculados: desde el Excel.
"""
from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any

import pandas as pd

_DIR_MODULO = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_DEFAULTS = os.path.join(_DIR_MODULO, "parametros_defaults.json")
# Legado (compatibilidad)
ARCHIVO_BACKUP = os.path.join(_DIR_MODULO, "parametros_backup.json")
ARCHIVO_GUARDADO = os.path.join(_DIR_MODULO, "parametros_guardados.json")

DIR_BASE = os.path.join(_DIR_MODULO, "parametros_base")
DIR_ACTUALES = os.path.join(_DIR_MODULO, "parametros_actuales")
ARCHIVO_BASE = os.path.join(DIR_BASE, "parametros.json")
ARCHIVO_ACTUALES = os.path.join(DIR_ACTUALES, "parametros.json")

# Secciones de solo lectura (se recalculan desde el Excel).
_TAGS_CALCULADOS = frozenset({
    "inv_datos_calculados",
    "inv_inversiones_calculado",
    "gen_financieros_calculados",
})


def _tags_editables(defaults: dict) -> list[str]:
    return [t for t in defaults if t not in _TAGS_CALCULADOS]


def cargar_defaults() -> dict[str, list[dict[str, Any]]]:
    with open(ARCHIVO_DEFAULTS, encoding="utf-8") as f:
        return json.load(f)


def _filas_editables_desde_json(data: dict) -> dict[str, list[dict[str, Any]]]:
    """Ignora metadatos (_descripcion, etc.) y deja solo tags editables."""
    defaults = cargar_defaults()
    out: dict[str, list[dict[str, Any]]] = {}
    for tag in _tags_editables(defaults):
        filas = data.get(tag)
        if isinstance(filas, list):
            out[tag] = filas
    return out


def _filas_editables_para_archivo(
    params: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    return {tag: deepcopy(params[tag]) for tag in _tags_editables(params) if tag in params}


def _fusionar_parametros_editables(
    base: dict[str, list[dict[str, Any]]],
    fuente: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    out = deepcopy(base)
    for tag in _tags_editables(out):
        if tag not in fuente:
            continue
        filas = fuente[tag]
        if not isinstance(filas, list):
            continue
        nombres_def = [r["name"] for r in out[tag]]
        por_nombre = {
            r["name"]: float(r["value"])
            for r in filas
            if isinstance(r, dict) and "name" in r and "value" in r
        }
        out[tag] = [
            {"name": n, "value": por_nombre.get(n, float(out[tag][i]["value"]))}
            for i, n in enumerate(nombres_def)
        ]
    return out


def _leer_json_editables(ruta: str) -> dict[str, list[dict[str, Any]]] | None:
    if not os.path.isfile(ruta):
        return None
    try:
        with open(ruta, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return _filas_editables_desde_json(data)


def _escribir_json_editables(
    ruta: str,
    params: dict[str, list[dict[str, Any]]],
    *,
    descripcion: str,
) -> None:
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    payload: dict[str, Any] = {
        "_descripcion": descripcion,
        **_filas_editables_para_archivo(params),
    }
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _semilla_inicial_editables() -> dict[str, list[dict[str, Any]]]:
    base = cargar_defaults()
    for ruta in (ARCHIVO_BACKUP, ARCHIVO_GUARDADO):
        legado = _leer_json_editables(ruta)
        if legado:
            return _fusionar_parametros_editables(base, legado)
    return deepcopy(base)


def asegurar_archivos_parametros() -> None:
    os.makedirs(DIR_BASE, exist_ok=True)
    os.makedirs(DIR_ACTUALES, exist_ok=True)
    if not os.path.isfile(ARCHIVO_BASE):
        _escribir_json_editables(
            ARCHIVO_BASE,
            _semilla_inicial_editables(),
            descripcion=(
                "Parámetros BASE (inicio). Solo con «Actualizar parámetros base»."
            ),
        )
    if not os.path.isfile(ARCHIVO_ACTUALES):
        fuente = _leer_json_editables(ARCHIVO_BASE) or _filas_editables_desde_json(
            cargar_defaults()
        )
        _escribir_json_editables(
            ARCHIVO_ACTUALES,
            _fusionar_parametros_editables(cargar_defaults(), fuente),
            descripcion="Parámetros ACTUALES (últimos). Se cargan al abrir la app.",
        )


def cargar_parametros_base() -> dict[str, list[dict[str, Any]]]:
    asegurar_archivos_parametros()
    estructura = cargar_defaults()
    base = _leer_json_editables(ARCHIVO_BASE)
    if base:
        return _fusionar_parametros_editables(estructura, base)
    return deepcopy(estructura)


def cargar_parametros_actuales() -> dict[str, list[dict[str, Any]]]:
    asegurar_archivos_parametros()
    estructura = cargar_defaults()
    actuales = _leer_json_editables(ARCHIVO_ACTUALES)
    if actuales:
        return _fusionar_parametros_editables(estructura, actuales)
    return cargar_parametros_base()


def guardar_parametros_actuales(params: dict[str, list[dict[str, Any]]]) -> None:
    asegurar_archivos_parametros()
    _escribir_json_editables(
        ARCHIVO_ACTUALES,
        params,
        descripcion="Parámetros ACTUALES (últimos). Se cargan al abrir la app.",
    )


def actualizar_parametros_base(params: dict[str, list[dict[str, Any]]]) -> None:
    asegurar_archivos_parametros()
    _escribir_json_editables(
        ARCHIVO_BASE,
        params,
        descripcion=(
            "Parámetros BASE (inicio). Solo con «Actualizar parámetros base»."
        ),
    )


def restablecer_a_parametros_base() -> dict[str, list[dict[str, Any]]]:
    """Carga la base y la deja también en actuales."""
    params = cargar_parametros_base()
    guardar_parametros_actuales(params)
    return params


def cargar_backup() -> dict[str, list[dict[str, Any]]] | None:
    legado = _leer_json_editables(ARCHIVO_BACKUP)
    if legado:
        return legado
    asegurar_archivos_parametros()
    return _leer_json_editables(ARCHIVO_BASE)


def guardar_backup_editables(params: dict[str, list[dict[str, Any]]]) -> None:
    actualizar_parametros_base(params)


def cargar_parametros_inicio() -> dict[str, list[dict[str, Any]]]:
    return cargar_parametros_actuales()


def cargar_parametros_demo() -> dict[str, list[dict[str, Any]]]:
    return cargar_parametros_actuales()


def cargar_parametros_archivo_subido() -> dict[str, list[dict[str, Any]]]:
    """Excel nuevo: mismos actuales en disco (no se borran). Calculados salen del Excel."""
    return cargar_parametros_actuales()


def reiniciar_a_defaults(*, borrar_guardado_local: bool = True) -> dict[str, list[dict[str, Any]]]:
    del borrar_guardado_local
    return restablecer_a_parametros_base()


def restaurar_en_session_state(
    params: dict[str, list[dict[str, Any]]],
    df: pd.DataFrame | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Aplica params en sesión, widgets y calculados desde el Excel (si hay df)."""
    import streamlit as st

    limpiar_claves_widgets()
    invalidar_cache_calculados()
    st.session_state.pop("inv_widgets_param_ok", None)
    if df is not None:
        actualizar_calculados_desde_df(params, df, inplace=True)
        costo_capital_pct = _valores_tag(params, "gen_financieros")[0]
        st.session_state["inv_calc_fingerprint"] = _fingerprint_calculados(
            df, costo_capital_pct
        )
    st.session_state["inv_parametros"] = params
    sincronizar_claves_widgets(params, force=True)
    return params


def guardar_parametros_editables(params: dict[str, list[dict[str, Any]]]) -> None:
    """Guardar → parámetros actuales."""
    guardar_parametros_actuales(params)


def clave_widget_parametro(tag: str, indice: int) -> str:
    return f"inv_param_{tag}_{indice}"


def sincronizar_claves_widgets(
    params: dict[str, list[dict[str, Any]]],
    *,
    force: bool = False,
) -> None:
    """Alinea number_input con params. Solo llamar antes de instanciar los widgets."""
    for tag in _tags_editables(params):
        sincronizar_claves_tag(params, tag, force=force)


def sincronizar_claves_tag(params: dict, tag: str, *, force: bool = False) -> None:
    """Refresca claves de widgets desde params (defaults, guardados o Excel nuevo)."""
    import streamlit as st

    if tag not in params:
        return
    for i, fila in enumerate(params[tag]):
        key = clave_widget_parametro(tag, i)
        if not force and key in st.session_state:
            continue
        st.session_state[key] = float(fila["value"])


def params_desde_widgets(params: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Lee los number_input actuales (session_state) para persistir lo que ve el usuario."""
    import streamlit as st

    out = deepcopy(params)
    for tag in _tags_editables(out):
        if tag not in out:
            continue
        for i in range(len(out[tag])):
            key = clave_widget_parametro(tag, i)
            if key in st.session_state:
                out[tag][i]["value"] = float(st.session_state[key])
    return out


def limpiar_claves_widgets() -> None:
    """Quita claves de widgets al recargar Excel o reiniciar parámetros."""
    import streamlit as st

    for key in list(st.session_state.keys()):
        if isinstance(key, str) and key.startswith("inv_param_"):
            del st.session_state[key]


def valor_inicial_widget(tag: str, indice: int, valor: float) -> float:
    """Inicializa la clave del widget sin chocar con value= en number_input."""
    import streamlit as st

    key = clave_widget_parametro(tag, indice)
    if key not in st.session_state:
        st.session_state[key] = float(valor)
    return float(st.session_state[key])


def _valores_tag(params: dict, tag: str) -> list[float]:
    return [float(x["value"]) for x in params[tag]]


def _nombres_tag(params: dict, tag: str) -> list[str]:
    return [x["name"] for x in params[tag]]


def _fingerprint_calculados(df: pd.DataFrame, costo_capital_pct: float) -> str:
    """Huella rápida: datos Excel + % costo de capital (afecta costo financiero inv.)."""
    import streamlit as st

    upload_id = st.session_state.get("inv_upload_id")
    origen = str(upload_id) if upload_id else "default"
    return (
        f"{origen}|{len(df)}|"
        f"{float(df['valor inventario promedio'].sum()):.0f}|"
        f"{float(df['ventas totales'].sum()):.0f}|"
        f"{float(df['ventas costo'].sum()):.0f}|"
        f"{int(df['codigo'].nunique())}|"
        f"{int(df['proveedor'].nunique())}|"
        f"{float(costo_capital_pct):.6f}"
    )


def actualizar_calculados_desde_df(
    params: dict[str, list[dict[str, Any]]],
    df: pd.DataFrame,
    *,
    inplace: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    """Misma lógica que ``backend.calculate_*`` del proyecto original."""
    out = params if inplace else deepcopy(params)
    sum_valor_inv = round(float(df["valor inventario promedio"].sum()), 0)
    sum_ventas = round(float(df["ventas totales"].sum()), 0)
    sum_ventas_costo = round(float(df["ventas costo"].sum()), 0)
    n_skus = int(df["codigo"].nunique())
    n_prov = int(df["proveedor"].nunique())
    costo_capital_pct = _valores_tag(out, "gen_financieros")[0]
    costo_fin_inv = round(sum_valor_inv * costo_capital_pct / 100, 0)

    out["inv_datos_calculados"] = [
        {"name": _nombres_tag(out, "inv_datos_calculados")[0], "value": n_skus},
        {"name": _nombres_tag(out, "inv_datos_calculados")[1], "value": n_prov},
    ]
    out["gen_financieros_calculados"] = [
        {"name": _nombres_tag(out, "gen_financieros_calculados")[0], "value": sum_ventas},
        {"name": _nombres_tag(out, "gen_financieros_calculados")[1], "value": sum_ventas_costo},
    ]
    out["inv_inversiones_calculado"] = [
        {"name": _nombres_tag(out, "inv_inversiones_calculado")[0], "value": sum_valor_inv},
        {"name": _nombres_tag(out, "inv_inversiones_calculado")[1], "value": costo_fin_inv},
    ]
    return out


def actualizar_calculados_si_necesario(
    params: dict[str, list[dict[str, Any]]],
    df: pd.DataFrame,
) -> dict[str, list[dict[str, Any]]]:
    """Recalcula solo si cambió el Excel o el % de costo de capital."""
    import streamlit as st

    costo_capital_pct = _valores_tag(params, "gen_financieros")[0]
    fp = _fingerprint_calculados(df, costo_capital_pct)
    if st.session_state.get("inv_calc_fingerprint") != fp:
        actualizar_calculados_desde_df(params, df, inplace=True)
        st.session_state["inv_calc_fingerprint"] = fp
    return params


def invalidar_cache_calculados() -> None:
    """Tras cargar otro Excel o reiniciar parámetros."""
    import streamlit as st

    st.session_state.pop("inv_calc_fingerprint", None)


def tag_a_dataframe(params: dict, tag: str) -> pd.DataFrame:
    filas = params[tag]
    return pd.DataFrame({"Parámetro": [r["name"] for r in filas], "Valor": [r["value"] for r in filas]})


def dataframe_editable_a_tag(
    params: dict,
    tag: str,
    edited: pd.DataFrame,
    columna_valor: str = "Valor",
    *,
    inplace: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    out = params if inplace else deepcopy(params)
    nombres = [r["name"] for r in out[tag]]
    valores = [float(v) for v in edited[columna_valor].tolist()]
    out[tag] = [{"name": n, "value": v} for n, v in zip(nombres, valores)]
    return out


def inicializar_parametros(df: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    """Demo (template) o estándar limpio (archivo subido) + calculados desde el Excel."""
    import streamlit as st

    if "inv_parametros" not in st.session_state:
        if st.session_state.get("inv_upload_id"):
            st.session_state["inv_parametros"] = cargar_parametros_archivo_subido()
        else:
            st.session_state["inv_parametros"] = cargar_parametros_demo()
        sincronizar_claves_widgets(st.session_state["inv_parametros"])
        invalidar_cache_calculados()
    actualizar_calculados_si_necesario(st.session_state["inv_parametros"], df)
    return st.session_state["inv_parametros"]


def obtener_parametros(df: pd.DataFrame | None = None) -> dict[str, list[dict[str, Any]]]:
    """Devuelve parámetros ya inicializados (recalcula calculados si hay DataFrame)."""
    import streamlit as st

    if df is not None:
        return inicializar_parametros(df)
    if "inv_parametros" not in st.session_state:
        if st.session_state.get("inv_upload_id"):
            st.session_state["inv_parametros"] = cargar_parametros_archivo_subido()
        else:
            st.session_state["inv_parametros"] = cargar_parametros_demo()
        sincronizar_claves_widgets(st.session_state["inv_parametros"])
    return st.session_state["inv_parametros"]


def es_editable(tag: str) -> bool:
    return tag not in _TAGS_CALCULADOS


def extraer_tag(params: dict, tag: str) -> tuple[list[str], list[float]]:
    """Nombres y valores de una sección de parámetros."""
    return _nombres_tag(params, tag), _valores_tag(params, tag)
