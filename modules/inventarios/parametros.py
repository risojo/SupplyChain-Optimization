"""Parámetros generales de Inventarios (sin base de datos).

Fuente primaria: hoja ``parametros`` de ``data/sources/inventarios.xlsx``.
Al cargar la app se leen y se escriben en JSON (actuales / base / legado).
La UI es solo lectura; no hay edición manual en pantalla.

Estructura de casillas: ``parametros_defaults.json``.
Calculados (SKUs, ventas, etc.): desde la hoja de datos del Excel.
"""
from __future__ import annotations

import io
import json
import os
import re
import unicodedata
from copy import deepcopy
from typing import Any

import pandas as pd

_DIR_MODULO = os.path.dirname(os.path.abspath(__file__))
_RAIZ_PROYECTO = os.path.dirname(os.path.dirname(_DIR_MODULO))
ARCHIVO_DEFAULTS = os.path.join(_DIR_MODULO, "parametros_defaults.json")
# Legado (compatibilidad)
ARCHIVO_BACKUP = os.path.join(_DIR_MODULO, "parametros_backup.json")
ARCHIVO_GUARDADO = os.path.join(_DIR_MODULO, "parametros_guardados.json")

DIR_BASE = os.path.join(_DIR_MODULO, "parametros_base")
DIR_ACTUALES = os.path.join(_DIR_MODULO, "parametros_actuales")
ARCHIVO_BASE = os.path.join(DIR_BASE, "parametros.json")
ARCHIVO_ACTUALES = os.path.join(DIR_ACTUALES, "parametros.json")

# Excel maestro compartido (hoja data + hoja parametros).
ARCHIVO_EXCEL_PARAMETROS = os.path.join(
    _RAIZ_PROYECTO, "data", "sources", "inventarios.xlsx"
)
HOJA_PARAMETROS = "parametros"

# Secciones de solo lectura (se recalculan desde el Excel de datos).
_TAGS_CALCULADOS = frozenset({
    "inv_datos_calculados",
    "inv_inversiones_calculado",
    "gen_financieros_calculados",
})


def _tags_editables(defaults: dict) -> list[str]:
    return [t for t in defaults if t not in _TAGS_CALCULADOS]


def _norm_clave(texto: str) -> str:
    s = str(texto).lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", s)


def _es_encabezado_seccion(clave: str) -> bool:
    return clave in {
        "parametrosalmacenaje",
        "parametrosinventario",
        "parametrosgenerales",
        "datos",
        "costosygastos",
        "inversiones",
    }


def _asignar_valor(
    params: dict[str, list[dict[str, Any]]],
    tag: str,
    indice: int,
    valor: float,
) -> None:
    if tag not in params or indice < 0 or indice >= len(params[tag]):
        return
    params[tag][indice]["value"] = float(valor)


def _resolver_destino_parametro(
    bloque: str,
    clave: str,
) -> tuple[str, int] | None:
    """Mapea etiqueta Excel (normalizada) → (tag JSON, índice) según el bloque activo."""
    if bloque == "alm_datos":
        if "persona" in clave and "almacen" in clave:
            return "alm_datos", 0
        if "metro" in clave and "almacen" in clave:
            return "alm_datos", 1
        if "equipo" in clave and "fax" not in clave and "comput" not in clave:
            return "alm_datos", 2
        if "posicion" in clave:
            return "alm_datos", 3
        if "otrosgastos" in clave and "almacen" in clave:
            return "alm_datos", 4
        return None

    if bloque == "alm_costos":
        if "manodeobra" in clave or ("mano" in clave and "obra" in clave):
            return "alm_costosgastos", 0
        if "alquiler" in clave or "espacio" in clave:
            return "alm_costosgastos", 1
        if "suministro" in clave:
            return "alm_costosgastos", 2
        if "energia" in clave:
            return "alm_costosgastos", 3
        if "3pl" in clave or "tercer" in clave:
            return "alm_costosgastos", 4
        if "seguro" in clave:
            return "alm_costosgastos", 6
        if "otrosgasto" in clave:
            return "alm_costosgastos", 5
        return None

    if bloque == "alm_inv":
        if "terreno" in clave or "edificio" in clave:
            return "alm_inversiones", 0
        if "manejo" in clave or "montacarga" in clave:
            return "alm_inversiones", 1
        if "almacenaje" in clave or "almacenamiento" in clave or "rack" in clave:
            return "alm_inversiones", 2
        if "wms" in clave:
            return "alm_inversiones", 3
        # Seguro = gasto directo (driver), no inversión × capital.
        if "seguro" in clave:
            return "alm_costosgastos", 6
        if "otrasinversion" in clave or clave == "otrasinversiones":
            return "alm_inversiones", 4
        return None

    if bloque == "inv_datos":
        if "sku" in clave or "proveedor" in clave:
            return None  # calculados desde hoja data
        if "persona" in clave or "encargado" in clave or "planeador" in clave:
            return "inv_datos", 0
        if "metro" in clave and "oficina" in clave:
            return "inv_datos", 1
        if "equipo" in clave:
            return "inv_datos", 2
        return None

    if bloque == "inv_costos":
        # El seguro operativo está en inversiones de almacén (Excel) → alm_costosgastos.
        # No pisar con la fila vacía «Seguros de Inventarios» de costos de inventario.
        if "seguro" in clave:
            return None
        if "manodeobra" in clave or ("mano" in clave and "obra" in clave):
            return "inv_costosgastos", 0
        if "energia" in clave:
            return "inv_costosgastos", 1
        if "suministro" in clave:
            return "inv_costosgastos", 2
        if "espacio" in clave and "oficina" in clave:
            return "inv_costosgastos", 3
        if "otrosgasto" in clave:
            return "inv_costosgastos", 4
        return None

    if bloque == "inv_inv":
        if "inventoryinvestment" in clave or (
            "inversion" in clave and "inventario" in clave and "hardware" not in clave
        ):
            return None  # calculado
        if "hardware" in clave:
            return "inv_inversiones", 0
        if (
            "management" in clave
            or "software" in clave
            or "inventorymanagement" in clave
        ):
            return "inv_inversiones", 1
        return None

    if bloque == "gen":
        if "capital" in clave:
            return "gen_financieros", 0
        if "hora" in clave or "fte" in clave:
            return "gen_operativos", 0
        return None

    return None


def _parsear_hoja_parametros_df(
    df_raw: pd.DataFrame,
) -> dict[str, list[dict[str, Any]]]:
    """Convierte la hoja parametros (2 columnas etiqueta/valor) a la estructura JSON."""
    params = deepcopy(cargar_defaults())
    if df_raw is None or df_raw.empty:
        return params

    bloque = "alm_datos"
    ambito = "alm"  # alm | inv | gen

    for _, row in df_raw.iterrows():
        etiqueta = row.iloc[0] if len(row) > 0 else None
        valor = row.iloc[1] if len(row) > 1 else None
        if etiqueta is None or (isinstance(etiqueta, float) and pd.isna(etiqueta)):
            continue
        texto = str(etiqueta).strip()
        if not texto or texto == "-":
            continue
        clave = _norm_clave(texto)

        if clave.startswith("parametrosalmacenaje"):
            ambito = "alm"
            bloque = "alm_datos"
            continue
        if clave.startswith("parametrosinventario"):
            ambito = "inv"
            bloque = "inv_datos"
            continue
        if clave in {"datos"}:
            bloque = "alm_datos" if ambito == "alm" else "inv_datos"
            continue
        if clave in {"costosygastos"}:
            bloque = "alm_costos" if ambito == "alm" else "inv_costos"
            continue
        if clave in {"inversiones"}:
            bloque = "alm_inv" if ambito == "alm" else "inv_inv"
            continue

        # Filas generales al final (FTE / capital) sin bloque dedicado
        if "capital" in clave or "hora" in clave or "fte" in clave:
            destino = _resolver_destino_parametro("gen", clave)
        else:
            destino = _resolver_destino_parametro(bloque, clave)

        if destino is None:
            continue
        if valor is None or (isinstance(valor, float) and pd.isna(valor)):
            continue
        try:
            num = float(valor)
        except (TypeError, ValueError):
            continue

        tag, idx = destino
        if tag == "gen_financieros" and abs(num) <= 1.0:
            # Excel en fracción (0.12) → JSON en porcentaje (12)
            num = num * 100.0
        _asignar_valor(params, tag, idx, num)

    return params


def leer_parametros_desde_excel(
    *,
    ruta: str | None = None,
    file_bytes: bytes | None = None,
) -> dict[str, list[dict[str, Any]]] | None:
    """Lee la hoja ``parametros``. None si no existe o falla."""
    try:
        if file_bytes is not None:
            xl = pd.ExcelFile(io.BytesIO(file_bytes))
        else:
            path = ruta or ARCHIVO_EXCEL_PARAMETROS
            if not os.path.isfile(path):
                return None
            xl = pd.ExcelFile(path)
        hojas = {str(h).strip().lower(): h for h in xl.sheet_names}
        nombre = hojas.get(HOJA_PARAMETROS.lower())
        if nombre is None:
            # tolerancia sin acento / plural
            for k, h in hojas.items():
                if "parametro" in k:
                    nombre = h
                    break
        if nombre is None:
            return None
        df_raw = pd.read_excel(xl, sheet_name=nombre, header=None)
        return _parsear_hoja_parametros_df(df_raw)
    except (OSError, ValueError, ImportError):
        return None


def sincronizar_json_desde_excel(
    *,
    ruta: str | None = None,
    file_bytes: bytes | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Lee Excel → escribe JSON actuales/base/legado. Si no hay hoja, usa actuales."""
    leidos = leer_parametros_desde_excel(ruta=ruta, file_bytes=file_bytes)
    if leidos is None:
        return cargar_parametros_actuales()
    guardar_parametros_actuales(leidos)
    actualizar_parametros_base(leidos)
    # Legado: mismos valores para quien aún lea parametros_guardados.json
    try:
        payload = _filas_editables_para_archivo(leidos)
        with open(ARCHIVO_GUARDADO, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError:
        pass
    return leidos


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
    return sincronizar_json_desde_excel()


def cargar_parametros_demo() -> dict[str, list[dict[str, Any]]]:
    return sincronizar_json_desde_excel()


def cargar_parametros_archivo_subido() -> dict[str, list[dict[str, Any]]]:
    """Si el Excel subido trae hoja parametros, la usa; si no, perfilado.xlsx."""
    return sincronizar_json_desde_excel()


def reiniciar_a_defaults(*, borrar_guardado_local: bool = True) -> dict[str, list[dict[str, Any]]]:
    del borrar_guardado_local
    return sincronizar_json_desde_excel()


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
    """Carga parámetros desde hoja Excel ``parametros`` → JSON; calculados desde datos."""
    import streamlit as st

    if "inv_parametros" not in st.session_state:
        bytes_up = st.session_state.get("inv_excel_bytes")
        if bytes_up:
            st.session_state["inv_parametros"] = sincronizar_json_desde_excel(
                file_bytes=bytes_up
            )
        else:
            st.session_state["inv_parametros"] = sincronizar_json_desde_excel()
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
        st.session_state["inv_parametros"] = sincronizar_json_desde_excel()
        sincronizar_claves_widgets(st.session_state["inv_parametros"])
    return st.session_state["inv_parametros"]


def es_editable(tag: str) -> bool:
    return tag not in _TAGS_CALCULADOS


def extraer_tag(params: dict, tag: str) -> tuple[list[str], list[float]]:
    """Nombres y valores de una sección de parámetros."""
    return _nombres_tag(params, tag), _valores_tag(params, tag)
