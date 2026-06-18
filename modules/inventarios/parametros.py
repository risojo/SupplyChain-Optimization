"""Parámetros generales de Inventarios (sin base de datos).

Réplica la página ``02_Parámetros_generales`` del proyecto original:
datos de almacenaje, inventario y generales (personal, costos, inversiones,
ventas). Los valores editables viven en ``st.session_state``; los calculados
se actualizan desde el Excel ``template_inventarios.xlsx``.

Valores editables guardados en ``parametros_guardados.json`` al pulsar Guardar.
Al iniciar: estándar desde ``parametros_defaults.json``, sobrescrito por lo guardado.
"""
from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any

import pandas as pd

_DIR_MODULO = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_DEFAULTS = os.path.join(_DIR_MODULO, "parametros_defaults.json")
ARCHIVO_BACKUP = os.path.join(_DIR_MODULO, "parametros_backup.json")
ARCHIVO_GUARDADO = os.path.join(_DIR_MODULO, "parametros_guardados.json")

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


def cargar_backup() -> dict[str, list[dict[str, Any]]] | None:
    """Respaldo versionado en el repo (parametros_backup.json)."""
    if not os.path.isfile(ARCHIVO_BACKUP):
        return None
    try:
        with open(ARCHIVO_BACKUP, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return _filas_editables_desde_json(data)


def guardar_backup_editables(params: dict[str, list[dict[str, Any]]]) -> None:
    """Actualiza parametros_backup.json (respaldo versionado en el repo)."""
    payload: dict[str, Any] = {
        "_descripcion": (
            "Respaldo de parámetros editables. Copiar a parametros_defaults.json "
            "o parametros_guardados.json para restaurar."
        ),
        **_filas_editables_para_archivo(params),
    }
    with open(ARCHIVO_BACKUP, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _filas_editables_para_archivo(
    params: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    return {tag: deepcopy(params[tag]) for tag in _tags_editables(params) if tag in params}


def _fusionar_parametros_editables(
    base: dict[str, list[dict[str, Any]]],
    fuente: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    for tag in _tags_editables(base):
        if tag not in fuente:
            continue
        filas = fuente[tag]
        if not isinstance(filas, list):
            continue
        nombres_def = [r["name"] for r in base[tag]]
        por_nombre = {
            r["name"]: float(r["value"])
            for r in filas
            if isinstance(r, dict) and "name" in r and "value" in r
        }
        base[tag] = [
            {"name": n, "value": por_nombre.get(n, float(base[tag][i]["value"]))}
            for i, n in enumerate(nombres_def)
        ]
    return base


def cargar_parametros_inicio() -> dict[str, list[dict[str, Any]]]:
    """Estándar (defaults); si hay guardado local lo aplica; si no, el backup del repo."""
    base = cargar_defaults()
    if os.path.isfile(ARCHIVO_GUARDADO):
        try:
            with open(ARCHIVO_GUARDADO, encoding="utf-8") as f:
                guardado = json.load(f)
            if isinstance(guardado, dict):
                return _fusionar_parametros_editables(base, _filas_editables_desde_json(guardado))
        except (json.JSONDecodeError, OSError):
            pass
    backup = cargar_backup()
    if backup:
        return _fusionar_parametros_editables(base, backup)
    return base


def reiniciar_a_defaults(*, borrar_guardado_local: bool = True) -> dict[str, list[dict[str, Any]]]:
    """Restaura parámetros editables desde ``parametros_defaults.json``."""
    if borrar_guardado_local and os.path.isfile(ARCHIVO_GUARDADO):
        try:
            os.remove(ARCHIVO_GUARDADO)
        except OSError:
            pass
    return deepcopy(cargar_defaults())


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
    """Persiste solo secciones editables (manual) para la próxima ejecución."""
    payload: dict[str, list[dict[str, Any]]] = {}
    for tag in _tags_editables(params):
        payload[tag] = deepcopy(params[tag])
    with open(ARCHIVO_GUARDADO, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


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
    """Defaults o últimos guardados + calculados desde el Excel."""
    import streamlit as st

    if "inv_parametros" not in st.session_state:
        st.session_state["inv_parametros"] = cargar_parametros_inicio()
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
        st.session_state["inv_parametros"] = cargar_parametros_inicio()
        sincronizar_claves_widgets(st.session_state["inv_parametros"])
    return st.session_state["inv_parametros"]


def es_editable(tag: str) -> bool:
    return tag not in _TAGS_CALCULADOS


def extraer_tag(params: dict, tag: str) -> tuple[list[str], list[float]]:
    """Nombres y valores de una sección de parámetros."""
    return _nombres_tag(params, tag), _valores_tag(params, tag)
