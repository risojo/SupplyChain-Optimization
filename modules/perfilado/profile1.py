import base64
import hashlib
import io
import os
import re
import shutil
import tempfile
import unicodedata
from textwrap import dedent
from datetime import datetime
from typing import Any, Iterable, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import speech_recognition as sr
import streamlit as st
import streamlit.components.v1 as components
from audio_recorder_streamlit import audio_recorder

# ==============================================================================
# CONFIGURACIÓN GLOBAL DE LA APLICACIÓN
# ==============================================================================
st.set_page_config(page_title="Profile Pro", page_icon="📊", layout="wide")

# ------------------------------------------------------------------------------
# Escala visual FIJA de la interfaz (independiente del zoom del navegador).
# Garantiza que la app se vea igual en local y en Render para cualquier usuario,
# sin que nadie tenga que tocar Ctrl +/-. Se expresa en PORCENTAJE de tamaño:
#   100 = nativo, 95 = 5% reducido, 90 = 10% reducido, etc.
# Ajusta solo este número para agrandar (subir) o achicar (bajar) toda la interfaz.
# ------------------------------------------------------------------------------
ESCALA_INTERFAZ_PCT = 97
st.markdown(
    f"<style>.stApp {{ zoom: {ESCALA_INTERFAZ_PCT / 100}; }}</style>",
    unsafe_allow_html=True,
)

REF_VIEWPORT_W = 1920
REF_VIEWPORT_H = 1080
# profile1.py vive en modules/perfilado/. La raíz del proyecto está 2 niveles
# arriba; los datos y los assets son carpetas compartidas en esa raíz.
_RAIZ_PROYECTO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARCHIVO_EXCEL_PATH = os.path.join(_RAIZ_PROYECTO, "data", "sources", "perfilado.xlsx")
ARCHIVO_LOGO_LRI = os.path.join(_RAIZ_PROYECTO, "assets", "LRI_logo.png")
TITULO_APP = "Profile Pro"
RESERVA_VERTICAL_REF = 320
MSG_ARCHIVO_EXCEL_ABIERTO = (
    "Archivo abierto: cierre el archivo Excel en su computadora y vuelva a cargar la aplicación."
)
_VOICE_PAUSA_SILENCIO_SEG = 3.0  # segundos de silencio para cerrar la grabación y procesar

# Pareto por cantidad de ítems en el eje X (orden descendente por la métrica del eje Y):
# primer tramo = % de ítems con mayor contribución → verde, siguiente → amarillo, cola → rojo.
COLOR_PARETO_TOP = "#22c55e"
COLOR_PARETO_MEDIO = "#eab308"
COLOR_PARETO_COLA = "#ef4444"

# -----------------------------------------------------------------------------
# Pareto invertido (menor es mejor)
# -----------------------------------------------------------------------------
# Por defecto el Pareto ordena de MAYOR a MENOR: los ítems con más valor van
# al tramo verde. Algunas métricas de inventario / cobertura son al revés:
# menos meses/días de inventario es deseable (verde) y más es riesgo (rojo).
# Registrar aquí columnas o patrones normalizados; ampliar según vayamos
# identificando variables contrarias a ventas, unidades o margen.
_PARETO_METRICAS_MENOR_ES_MEJOR: tuple[str, ...] = (
    "meses inventario",
    "meses de inventario",
    "dias inventario",
    "dias de inventario",
)
# Comparativo dos métricas: barras agrupadas por categoría
COLOR_BARRA_COMPARATIVO_1 = "#2196f3"
COLOR_BARRA_COMPARATIVO_2 = "#f59e0b"
COLOR_BARRA_COMPARATIVO_3 = "#22c55e"
_COLORES_BARRAS_MULTIMETRICA = (
    COLOR_BARRA_COMPARATIVO_1,
    COLOR_BARRA_COMPARATIVO_2,
    COLOR_BARRA_COMPARATIVO_3,
)
_TEXTOS_BARRAS_MULTIMETRICA = ("#ffffff", "#fef9c3", "#ecfdf5")
OPS_CALCULO = ("Suma", "Promedio")
# Fracciones de filas (suman 1): (top %, medio %, cola %)
PRESETS_PARETO = {
    "5% - 10% - 85%": (0.05, 0.10, 0.85),
    "10% - 15% - 75%": (0.10, 0.15, 0.75),
    "20% - 30% - 50%": (0.20, 0.30, 0.50),
    "30% - 30% - 40%": (0.30, 0.30, 0.40),
}
ETIQUETAS_BANDA_PARETO = {
    "30% - 30% - 40%": ("A", "B", "C"),
}
OPCIONES_PARETO_UI = ["Desactivado (Paleta Azul)"] + [
    f"{k} (ítems eje X: verde · amarillo · rojo)" for k in PRESETS_PARETO
]
MAPEO_PARETO_LEGACY = {
    "80% - 15% - 5% (Clásico)": "5% - 10% - 85% (ítems eje X: verde · amarillo · rojo)",
    "70% - 20% - 10% (Estricto)": "10% - 15% - 75% (ítems eje X: verde · amarillo · rojo)",
    "60% - 25% - 15% (Concentrado)": "20% - 30% - 50% (ítems eje X: verde · amarillo · rojo)",
    "5% - 10% - 85% (Núcleo · Medio · Cola)": "5% - 10% - 85% (ítems eje X: verde · amarillo · rojo)",
    "10% - 15% - 75% (Núcleo · Medio · Cola)": "10% - 15% - 75% (ítems eje X: verde · amarillo · rojo)",
    "20% - 30% - 50% (Núcleo · Medio · Cola)": "20% - 30% - 50% (ítems eje X: verde · amarillo · rojo)",
    "30% A - 30% B - 40% C (ítems eje X: verde · amarillo · rojo)": "30% - 30% - 40% (ítems eje X: verde · amarillo · rojo)",
}

METRICA_ADICIONAL_NINGUNA = "— Ninguna —"
# Bump al desplegar: limpia sesiones web con datos/ejes de builds anteriores.
LRI_PROFILE_REVISION = "2025-07-07-canet"

# Inicialización del Estado de la Sesión
ESTADOS_INICIALES = {
    "lri_man_eje_x": None,
    "lri_man_eje_y": None,
    "lri_man_eje_y2": METRICA_ADICIONAL_NINGUNA,
    "lri_man_eje_y3": METRICA_ADICIONAL_NINGUNA,
    "lri_man_operacion": "Suma",
    "lri_man_operacion_y": "Suma",
    "lri_man_operacion_y2": "Suma",
    "lri_man_operacion_y3": "Suma",
    "lri_man_top_n": 0,
    "lri_grafico_scroll_completo": False,
    "lri_default_seeded": False,
    "comando_voz_detectado": None,
    "drill_down_categoria": None,
    "lri_pareto_set": "Desactivado (Paleta Azul)",
    "lri_pareto_acumulado": False,
    "lri_tabla_fontsize": 18,
    "lri_etiqueta_barras_fontsize": 16,
    "prev_manual_x": None,
    "prev_manual_y": None,
    "prev_manual_op": None,
    "prev_manual_top": 0,
    "prev_drill_down_categoria": None,
    "lri_last_audio_hash": None,
    "lri_excel_bytes": None,
    "lri_excel_hojas": [],
    "lri_excel_hoja_activa": None,
}

for key, val in ESTADOS_INICIALES.items():
    if key not in st.session_state:
        st.session_state[key] = val


# ==============================================================================
# CAPA 1: ACCESO A DATOS / LECTURA DE ARCHIVOS
# ==============================================================================
def _normalizar_nombres_columnas_df(df: pd.DataFrame) -> pd.DataFrame:
    """Unifica nombres de categoría / subcategoría al cargar cualquier Excel LRI."""
    df_out = df.copy()
    nuevos_nombres: dict = {}
    for col in df_out.columns:
        col_norm = col.lower().strip()
        col_key = _norm_texto(col)
        if (
            "subcat" in col_norm
            or "sub_cat" in col_norm
            or col_key in ("subcategoria", "subcategoría", "subproducto")
            or (col_key.startswith("sub") and "categ" in col_key)
        ):
            nuevos_nombres[col] = "subcategoria"
        elif col_key in ("categoria", "categoría", "catproducto", "cat_producto"):
            nuevos_nombres[col] = "categoria"
        elif "cat_" in col_norm and "sub" not in col_norm:
            nuevos_nombres[col] = "categoria"
        elif "categ" in col_key and "sub" not in col_key and col not in nuevos_nombres:
            nuevos_nombres[col] = "categoria"
    if nuevos_nombres:
        df_out.rename(columns=nuevos_nombres, inplace=True)
    descartar = [c for c in df_out.columns if _es_columna_descartable(c)]
    if descartar:
        df_out = df_out.drop(columns=descartar)
    return df_out


def _es_columna_descartable(nombre: str) -> bool:
    """Columnas vacías o sin encabezado que Excel exporta como 'Unnamed: N'."""
    s = str(nombre).strip()
    return not s or s.lower().startswith("unnamed")


def _columnas_numericas_usables(df: pd.DataFrame) -> list:
    return [
        c
        for c in df.select_dtypes(include=["number"]).columns.tolist()
        if not _es_columna_descartable(c)
    ]


def _columna_parece_dimension_eje_y(nombre: str) -> bool:
    """Evita usar proveedor/país/etc. como métrica aunque Excel los guarde como número."""
    key = _norm_texto(nombre)
    return any(
        t in key
        for t in (
            "proveedor",
            "pais",
            "categoria",
            "subcategoria",
            "codigo",
            "descripcion",
            "producto",
            "sku",
            "articulo",
            "nombre",
        )
    )


def _columnas_metricas_y_preferidas(df: pd.DataFrame) -> list[str]:
    return [
        c
        for c in _columnas_numericas_usables(df)
        if not _columna_parece_dimension_eje_y(c)
    ]


def _resolver_eje_y_default(df: pd.DataFrame) -> Optional[str]:
    for candidato in (
        "ventas totales",
        "ventas totales $",
        "ventas total",
        "unidades vendidas anual",
        "bultos vendidos",
        "demanda unid mes 12",
        "demanda unid mes 1",
        "margen bruto total",
        "margen bruto",
        "margen utilidad",
        "ventas costo",
        "costo de ventas $",
        "rotacion unidades",
        "inventario promedio en unidades",
    ):
        hit = _resolver_columna_existente(df, candidato)
        if hit is not None:
            return hit
    cols_num = _columnas_metricas_y_preferidas(df)
    return cols_num[0] if cols_num else None


def _eje_y_valido(df: pd.DataFrame, columna: Optional[str]) -> bool:
    return (
        columna is not None
        and columna in df.columns
        and not _es_columna_descartable(columna)
    )


def _resetear_estado_tras_nuevo_archivo() -> None:
    """Al cambiar de Excel u hoja, los ejes del archivo anterior no aplican."""
    st.session_state["lri_default_seeded"] = False
    st.session_state["lri_man_eje_x"] = None
    st.session_state["lri_man_eje_y"] = None
    st.session_state["lri_man_eje_y2"] = METRICA_ADICIONAL_NINGUNA
    st.session_state["lri_man_eje_y3"] = METRICA_ADICIONAL_NINGUNA
    st.session_state["drill_down_categoria"] = None
    st.session_state.pop("lri_aplicar_voz_pendiente", None)
    st.session_state.pop("_lri_pending_man_eje_x", None)


def _sincronizar_revision_perfil() -> None:
    """Tras un deploy, evita que la sesión del navegador conserve hojas/ejes obsoletos."""
    if st.session_state.get("lri_profile_revision") == LRI_PROFILE_REVISION:
        return
    st.session_state["lri_profile_revision"] = LRI_PROFILE_REVISION
    st.session_state.pop("lri_df_datos", None)
    st.session_state.pop("lri_error_carga", None)
    st.session_state.pop("lri_upload_id", None)
    st.session_state.pop("lri_excel_bytes", None)
    st.session_state.pop("lri_excel_hojas", None)
    st.session_state.pop("lri_excel_hoja_activa", None)
    _resetear_estado_tras_nuevo_archivo()


def _sembrar_ejes_default_si_corresponde(df: pd.DataFrame) -> None:
    if st.session_state.get("lri_default_seeded", False):
        return
    columnas_df = df.columns.tolist()
    cols_texto = df.select_dtypes(include=["object", "category"]).columns.tolist()
    default_x = _resolver_columna_existente(df, "categoria", "categoría")
    if default_x is None:
        default_x = _resolver_columna_existente(df, "subcategoria", "subcategoría")
    if default_x is None:
        default_x = cols_texto[0] if cols_texto else (columnas_df[0] if columnas_df else None)
    default_y = _resolver_eje_y_default(df)
    if default_x in columnas_df:
        st.session_state["lri_man_eje_x"] = default_x
    if default_y is not None:
        st.session_state["lri_man_eje_y"] = default_y
    st.session_state["lri_man_operacion"] = "Suma"
    st.session_state["lri_man_operacion_y"] = "Suma"
    st.session_state["lri_man_operacion_y2"] = "Suma"
    st.session_state["lri_man_operacion_y3"] = "Suma"
    st.session_state["lri_man_eje_y2"] = METRICA_ADICIONAL_NINGUNA
    st.session_state["lri_man_eje_y3"] = METRICA_ADICIONAL_NINGUNA
    st.session_state["lri_man_top_n"] = 0
    st.session_state["lri_default_seeded"] = True


def _ajustar_ejes_a_dataframe(df: pd.DataFrame) -> None:
    columnas_df = df.columns.tolist()
    cols_texto = df.select_dtypes(include=["object", "category"]).columns.tolist()
    if (
        st.session_state["lri_man_eje_x"] is None
        or st.session_state["lri_man_eje_x"] not in columnas_df
    ):
        st.session_state["lri_man_eje_x"] = (
            cols_texto[0] if cols_texto else (columnas_df[0] if columnas_df else None)
        )
    if not _eje_y_valido(df, st.session_state.get("lri_man_eje_y")):
        st.session_state["lri_man_eje_y"] = _resolver_eje_y_default(df)


def _ajuste_puntuacion_nombre_hoja(nombre: str) -> float:
    key = _norm_texto(nombre)
    if any(t in key for t in ("parametro", "parameter", "config", "readme", "instruc", "leenda", "nota")):
        return -50.0
    if any(t in key for t in ("actual", "dato", "data", "producto", "inventario", "venta", "catalogo")):
        return 20.0
    return 0.0


def _puntuacion_hoja_datos(df: pd.DataFrame) -> float:
    df_n = _normalizar_nombres_columnas_df(df)
    cols = [c for c in df_n.columns if not _es_columna_descartable(c)]
    if len(cols) < 2 or len(df_n) < 2:
        return 0.0
    cols_num = _columnas_numericas_usables(df_n)
    cols_txt = [
        c
        for c in df_n.select_dtypes(include=["object", "category"]).columns.tolist()
        if c in cols
    ]
    score = len(df_n) * 0.1 + len(cols_num) * 5.0 + len(cols_txt) * 2.0
    if not cols_num:
        score *= 0.05
    return score


def _elegir_hoja_datos_automatica(xl: pd.ExcelFile) -> str:
    mejor_hoja = xl.sheet_names[0]
    mejor_score = -1.0
    for nombre in xl.sheet_names:
        try:
            df_raw = pd.read_excel(xl, sheet_name=nombre)
            score = _puntuacion_hoja_datos(df_raw) + _ajuste_puntuacion_nombre_hoja(nombre)
            if score > mejor_score:
                mejor_score = score
                mejor_hoja = nombre
        except Exception:
            continue
    return mejor_hoja


def _cargar_dataframe_excel(
    file_bytes: bytes,
    sheet_name: Optional[str] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[str], list[str], Optional[str]]:
    try:
        xl = pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl")
        hojas = xl.sheet_names
        if not hojas:
            return None, "El archivo Excel no contiene hojas.", [], None
        hoja_activa = (
            sheet_name
            if sheet_name in hojas
            else _elegir_hoja_datos_automatica(xl)
        )
        df_read = pd.read_excel(xl, sheet_name=hoja_activa)
        return _normalizar_nombres_columnas_df(df_read), None, hojas, hoja_activa
    except Exception as e:
        if _es_error_archivo_abierto(e):
            return None, MSG_ARCHIVO_EXCEL_ABIERTO, [], None
        return None, str(e), [], None


def _aplicar_resultado_carga_a_sesion(
    df: Optional[pd.DataFrame],
    err: Optional[str],
    hojas: list[str],
    hoja_activa: Optional[str],
    *,
    file_bytes: Optional[bytes] = None,
    reset_ejes: bool = False,
    limpiar_bytes_subida: bool = False,
) -> None:
    st.session_state["lri_df_datos"] = df
    st.session_state["lri_error_carga"] = err
    st.session_state["lri_excel_hojas"] = hojas
    st.session_state["lri_excel_hoja_activa"] = hoja_activa
    if limpiar_bytes_subida:
        st.session_state.pop("lri_excel_bytes", None)
    elif file_bytes is not None:
        st.session_state["lri_excel_bytes"] = file_bytes
    if reset_ejes:
        _resetear_estado_tras_nuevo_archivo()


def _obtener_bytes_excel_activos() -> Optional[bytes]:
    subidos = st.session_state.get("lri_excel_bytes")
    if subidos:
        return subidos
    if os.path.isfile(ARCHIVO_EXCEL_PATH):
        try:
            return _leer_bytes_archivo_excel(ARCHIVO_EXCEL_PATH)
        except Exception:
            return None
    return None


def _es_error_archivo_abierto(exc: BaseException) -> bool:
    if isinstance(exc, PermissionError):
        return True
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 13:
        return True
    msg = str(exc).lower()
    return "permission denied" in msg or "permiso denegado" in msg or "[errno 13]" in msg


def _mensaje_error_carga(exc: Optional[BaseException] = None, texto: Optional[str] = None) -> str:
    if exc is not None and _es_error_archivo_abierto(exc):
        return MSG_ARCHIVO_EXCEL_ABIERTO
    if texto:
        t = texto.lower()
        if (
            "archivo abierto" in t
            or "permission denied" in t
            or "permiso denegado" in t
            or "[errno 13]" in t
        ):
            return MSG_ARCHIVO_EXCEL_ABIERTO
        return texto
    return "No se pudieron cargar los datos."


def _leer_bytes_excel_windows_shared(path: str) -> Optional[bytes]:
    """En Windows, lectura compartida aunque Excel tenga el archivo abierto."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    GENERIC_READ = 0x80000000
    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_WRITE = 0x00000002
    FILE_SHARE_DELETE = 0x00000004
    OPEN_EXISTING = 3

    kernel32 = ctypes.windll.kernel32
    CreateFileW = kernel32.CreateFileW
    CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    CreateFileW.restype = wintypes.HANDLE

    handle = CreateFileW(
        os.path.abspath(path),
        GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        None,
        OPEN_EXISTING,
        0,
        None,
    )
    if handle in (wintypes.HANDLE(-1).value, None):
        return None

    data = bytearray()
    buf = (ctypes.c_char * 65536)()
    read_n = wintypes.DWORD(0)
    try:
        while kernel32.ReadFile(handle, buf, 65536, ctypes.byref(read_n), None) and read_n.value:
            data.extend(buf[: read_n.value])
    finally:
        kernel32.CloseHandle(handle)
    return bytes(data) if data else None


def _leer_bytes_archivo_excel(path: str) -> bytes:
    """Lee el Excel en memoria; tolera bloqueo por Excel abierto o sincronización OneDrive."""
    errores: list[str] = []

    try:
        with open(path, "rb") as f:
            return f.read()
    except (PermissionError, OSError) as e:
        if getattr(e, "errno", None) not in (None, 13):
            raise
        errores.append(str(e))

    fd, tmp = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    try:
        shutil.copyfile(path, tmp)
        with open(tmp, "rb") as f:
            return f.read()
    except (PermissionError, OSError) as e:
        errores.append(str(e))
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass

    shared = _leer_bytes_excel_windows_shared(path)
    if shared:
        return shared

    raise PermissionError(MSG_ARCHIVO_EXCEL_ABIERTO) from None


def cargar_datos(
    sheet_name: Optional[str] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[str], list[str], Optional[str]]:
    if not os.path.isfile(ARCHIVO_EXCEL_PATH):
        msg = f"No se encontró el archivo '{os.path.basename(ARCHIVO_EXCEL_PATH)}' en el directorio."
        return None, msg, [], None
    try:
        file_bytes = _leer_bytes_archivo_excel(ARCHIVO_EXCEL_PATH)
        return _cargar_dataframe_excel(file_bytes, sheet_name=sheet_name)
    except (PermissionError, OSError) as e:
        if _es_error_archivo_abierto(e):
            return None, MSG_ARCHIVO_EXCEL_ABIERTO, [], None
        return None, str(e), [], None
    except Exception as e:
        if _es_error_archivo_abierto(e):
            return None, MSG_ARCHIVO_EXCEL_ABIERTO, [], None
        return None, str(e), [], None


def cargar_datos_desde_upload(
    file_bytes: bytes,
    sheet_name: Optional[str] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[str], list[str], Optional[str]]:
    return _cargar_dataframe_excel(file_bytes, sheet_name=sheet_name)


# ==============================================================================
# CAPA 2: MOTOR SEMÁNTICO DE AUTO-APRENDIZAJE EN SUPPLY CHAIN Y LOGÍSTICA
# ==============================================================================
def _norm_texto(texto: str) -> str:
    """Normaliza texto removiendo acentos, espacios, mayúsculas y caracteres especiales."""
    s = str(texto).lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.replace(" ", "").replace("_", "").replace("/", "").replace("-", "").replace(".", "")


def _normalizar_comando_voz(texto: str) -> str:
    """Como _norm_texto pero conserva espacios (necesario para «ventas y utilidad … por …»)."""
    s = str(texto).lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"[_/.\-]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def generar_diccionario_semantico_dinamico(df: pd.DataFrame) -> dict:
    """
    Construye de forma automática el mapa de sinónimos enfocado en Supply Chain de punta a punta:
    Pronóstico, Inventarios, Customer Service, Compras, Almacenaje, Transporte y Canales de Venta.
    """
    cols_texto = df.select_dtypes(include=["object", "category"]).columns.tolist()
    cols_num = df.select_dtypes(include=["number"]).columns.tolist()
    
    # Biblioteca maestra expandida con los pilares logísticos y canales de distribución regionales
    sinonimos_maestros_x = {
        "categoria": ["categoria", "familia", "linea", "grupo", "segmento", "clase"],
        "subcategoria": ["subcategoria", "subfamilia", "subgrupo", "sublinea", "subclase"],
        "descripcion": ["articulo", "producto", "item", "sku", "codigo", "descripcion", "material", "nombre", "clave"],
        "cliente": ["cliente", "puntodeventa", "pdv", "pulperias", "supermercados", "canal", "tradicional", "moderno", "detallista", "retail", "destino", "ruta"],
        "pais": ["pais", "país", "country", "nacion", "nación", "origen", "region", "región", "geografia"],
        "proveedor": ["proveedor", "supplier", "fabricante", "vendor"],
    }
    
    diccionario = {"eje_x": {}, "eje_y": {}}
    
    # 1. Mapeo de Dimensiones (Eje X)
    for col in cols_texto:
        col_norm = _norm_texto(col)
        sinonimos_detectados = [col_norm, col.lower()]
        
        for clave, lista_sinonimos in sinonimos_maestros_x.items():
            if clave in col_norm or col_norm in clave:
                sinonimos_detectados.extend(lista_sinonimos)
                
        diccionario["eje_x"][col] = list(set(sinonimos_detectados))
        
    # 2. Mapeo de Métricas Especializadas (Eje Y)
    for col in cols_num:
        col_norm = _norm_texto(col)
        sinonimos_detectados = [col_norm, col.lower(), col_norm.replace("anual", "").strip()]
        
        # PILAR: Gestión de Pedidos, Demandas y Picking
        if "orden" in col_norm or "pedido" in col_norm or "pick" in col_norm:
            sinonimos_detectados.extend(["ordenes", "pedidos", "solicitudes", "compras", "demanda", "picking", "pickinglist", "listadepicking"])
        
        # PILAR: Almacenaje, Volumetría y Transporte
        elif "bulto" in col_norm or "caja" in col_norm or "pack" in col_norm or "tarima" in col_norm or "flete" in col_norm:
            sinonimos_detectados.extend(["bultos", "cajas", "paquetes", "volumen", "cantidad", "bultosvendidos", "tarimas", "pallets", "fletes", "transporte"])
        
        # PILAR: Inventarios y Tránsito
        elif "transit" in col_norm or "camino" in col_norm or "inventario" in col_norm or "stock" in col_norm:
            sinonimos_detectados.extend(["transito", "camino", "flotante", "importacion", "valorinventariotransito", "inventario", "stock", "existencias", "cobertura", "diasdeinventario"])
        
        # PILAR: Pronóstico y Planeación (Exactitud / Error)
        elif "pronostico" in col_norm or "forecast" in col_norm or "error" in col_norm or "exactitud" in col_norm:
            sinonimos_detectados.extend(["pronostico", "forecast", "exactitud", "error", "errordepronostico", "exactituddepronostico", "mape", "desviacion"])
        
        # PILAR: Customer Service Logístico y Fill Rate
        elif "servicio" in col_norm or "customer" in col_norm or "otif" in col_norm or "rate" in col_norm:
            sinonimos_detectados.extend(["servicio", "customerservice", "niveldeservicio", "otif", "fillrate", "cumplimiento", "entregas"])
            
        # PILAR: Financiero Comercial Logístico (Costos / Ventas / Utilidades)
        elif (
            "venta" in col_norm
            or "costo" in col_norm
            or "ingreso" in col_norm
            or "utili" in col_norm
            or "marge" in col_norm
            or "margen" in col_norm
            or "precio" in col_norm
        ):
            if "inventario" not in col_norm:
                if "venta" in col_norm:
                    sinonimos_detectados.extend(
                        ["ventas", "ingresos", "facturacion", "ventastotales"]
                    )
                if "costo" in col_norm:
                    sinonimos_detectados.extend(["costo", "costologistico"])
                if "precio" in col_norm:
                    sinonimos_detectados.extend(["precio", "preciounitario"])
                if any(k in col_norm for k in ("utili", "marge", "margen")):
                    sinonimos_detectados.extend(
                        ["utilidad", "margen", "margendeutilidad", "margendeutilidadventas"]
                    )
            elif "mantener" in col_norm:
                sinonimos_detectados.extend(["costomantenerinventario", "costodeinventario", "mantenerinventario"])
        
        elif "unid" in col_norm or "cant" in col_norm:
            sinonimos_detectados.extend(["unidades", "piezas", "cantidades", "unidadesvendidas"])

        # Columnas mixtas (p. ej. inventario promedio bultos): sinónimos de inventario
        if "inventario" in col_norm or "stock" in col_norm:
            sinonimos_detectados.extend(
                ["inventario", "stock", "existencias", "inventariopromedio", "inventariofinal"]
            )
            if "valor" in col_norm and "inventario" in col_norm and "promedio" in col_norm:
                sinonimos_detectados.extend(
                    [
                        "valorinventario",
                        "valordinventario",
                        "inventariovalor",
                        "inventariopromedioendolares",
                        "inventarioendolares",
                        "montoinventario",
                        "valordelinventario",
                    ]
                )
                sinonimos_detectados.extend(["dolares", "dolar", "usd"])
            elif "valor" in col_norm or "promedio" in col_norm:
                sinonimos_detectados.extend(
                    ["montoinventario", "valorinventario", "importeinventario"]
                )
        if "promedio" in col_norm and "inventario" in col_norm:
            sinonimos_detectados.extend(["inventariopromedio", "promedioinventario", "inventariopromediobultos"])

        diccionario["eje_y"][col] = list(set(sinonimos_detectados))
        
    return diccionario


def _resolver_columna_existente(df: pd.DataFrame, *candidatos: str) -> Optional[str]:
    """Devuelve el primer nombre de columna presente en df (comparación normalizada)."""
    mapa = {_norm_texto(c): c for c in df.columns}
    for cand in candidatos:
        hit = mapa.get(_norm_texto(cand))
        if hit is not None:
            return hit
    return None


def _comando_solicita_inventario(cmd_limpio: str) -> bool:
    """True si el dictado trata de inventario/stock (prioridad sobre ventas)."""
    return any(
        k in cmd_limpio
        for k in (
            "inventario",
            "inventariopromedio",
            "inventariofinal",
            "inventariotransito",
            "valorinventario",
            "valordinventario",
            "stock",
            "existencias",
            "mesesdeinventario",
        )
    )


def _comando_pide_valor_inventario_voz(cmd_limpio: str) -> bool:
    """Valor del inventario / inventario promedio en dólares → valor inventario promedio."""
    if not _comando_solicita_inventario(cmd_limpio):
        return False
    if any(k in cmd_limpio for k in ("valorinventario", "valordinventario", "inventariovalor")):
        return True
    if any(k in cmd_limpio for k in ("dolar", "dolares", "usd")):
        return True
    if any(k in cmd_limpio for k in ("monto", "valor", "importe", "dinero")):
        return "mantener" not in cmd_limpio
    return False


def _columna_valor_inventario_promedio(df: pd.DataFrame) -> Optional[str]:
    return _resolver_columna_existente(
        df,
        "valor inventario promedio",
        "valor inventario promedio ",
        "inventario promedio en dolares",
        "inventario promedio dolares",
    )


def _comando_solicita_ventas(cmd_limpio: str) -> bool:
    """True si pidió ventas. «inventario» contiene «venta» como subcadena: no confundir."""
    if _comando_solicita_inventario(cmd_limpio):
        return False
    if _comando_solicita_margen(cmd_limpio):
        return False
    return any(tok in cmd_limpio for tok in ("ventas", "ventastotales", "facturacion", "ingresos", "venta"))


def _comando_solicita_margen(cmd_limpio: str) -> bool:
    """True si el dictado pide margen / utilidad bruta (no precio)."""
    return any(
        k in cmd_limpio
        for k in (
            "margen",
            "margbrut",
            "margutil",
            "utilidadbruta",
            "utilbruta",
            "margenbruto",
            "margenutilidad",
        )
    )


def _comando_solicita_precio(cmd_limpio: str) -> bool:
    return "precio" in cmd_limpio and not _comando_solicita_margen(cmd_limpio)


def _resolver_metrica_margen_voz(cmd_limpio: str, df: pd.DataFrame) -> Optional[str]:
    """Prioriza columnas de margen cuando el dictado lo menciona explícitamente."""
    if not _comando_solicita_margen(cmd_limpio):
        return None
    hit = _resolver_columna_existente(
        df,
        "margen bruto total",
        "margen utilidad ventas",
        "margen utilidad ",
        "margen utilidad",
        "margen de utilidad",
        "% margen",
    )
    if hit:
        return hit
    for col in df.select_dtypes(include="number").columns:
        col_n = _norm_texto(col)
        if "margen" in col_n or ("utilidad" in col_n and "precio" not in col_n):
            return col
    return None


def _resolver_metrica_precio_voz(cmd_limpio: str, df: pd.DataFrame) -> Optional[str]:
    if not _comando_solicita_precio(cmd_limpio):
        return None
    return _resolver_columna_existente(
        df,
        "precio por producto",
        "precio unitario bulto",
        "precio unitario",
        "precio",
    )


def _preprocesar_comando_voz(cmd_limpio: str) -> str:
    """Corrige errores frecuentes del reconocimiento de voz (p. ej. 'su categoría' → subcategoría)."""
    s = cmd_limpio
    s = s.replace("utilda", "utilidad").replace("utilida bruta", "utilidad bruta")
    s = s.replace("sucategoria", "subcategoria")
    s = s.replace("sucat", "subcat")
    s = re.sub(r"valor\s+del\s+inventario", "valor inventario promedio", s, flags=re.I)
    s = re.sub(
        r"inventario\s+promedio\s+en\s+(dolares?|usd)",
        "valor inventario promedio",
        s,
        flags=re.I,
    )
    s = re.sub(
        r"inventario\s+promedio\s+(en\s+)?(dolares?|usd)",
        "valor inventario promedio",
        s,
        flags=re.I,
    )
    if "porsub" in s and "subcategoria" not in s:
        s = s.replace("porsub", "porsubcategoria", 1)
    if "inventario" in s and ("promedio" in s or "promedi" in s) and "inventariopromedio" not in s:
        s = s.replace("inventario", "inventariopromedio", 1)
    for relleno in (
        "deseoel", "deseo", "quieroel", "quiero", "muestrame", "mostrarme",
        "graficar", "grafico", "grafica", "necesito", "dame",
    ):
        if s.startswith(relleno):
            s = s[len(relleno):].lstrip()
            break
    for articulo in ("las ", "los ", "la ", "el ", "una ", "un "):
        if s.startswith(articulo):
            s = s[len(articulo) :]
            break
    return s.strip()


def _comando_menciona_subcategoria(cmd_limpio: str) -> bool:
    return (
        "subcategoria" in cmd_limpio
        or "porsubcategoria" in cmd_limpio
        or "subfamilia" in cmd_limpio
        or "subgrupo" in cmd_limpio
    )


_SINONIMOS_CORTOS_EJE_X = frozenset({"pais", "sku", "pdv"})
# Palabras de dimensión (eje X) que no deben resolver una métrica (eje Y) por sí solas.
_SINONIMOS_DIMENSION_NO_METRICA = frozenset(
    {
        "producto",
        "articulo",
        "codigo",
        "descripcion",
        "categoria",
        "subcategoria",
        "proveedor",
        "pais",
        "sku",
        "item",
        "material",
        "nombre",
    }
)


def _coincide_sinonimo_en_comando(cmd_limpio: str, sinonimo: str) -> bool:
    """Evita falsos positivos con sinónimos muy cortos (p. ej. 'cat' dentro de 'categoria')."""
    s = _norm_texto(sinonimo)
    if len(s) < 5 and s not in _SINONIMOS_CORTOS_EJE_X:
        return False
    return s in cmd_limpio


def _sinonimo_valido_para_metrica_voz(col: str, sinonimo: str) -> bool:
    """Evita que «producto» o «margen» genérico resuelvan la columna equivocada."""
    sn = _norm_texto(sinonimo)
    col_n = _norm_texto(col)
    if sn in _SINONIMOS_DIMENSION_NO_METRICA and sn not in col_n:
        return False
    if sn == "margen" and not any(k in col_n for k in ("margen", "marge", "utilidad")):
        return False
    if sn in ("costo", "utilidad", "ventas") and sn not in col_n:
        if sn == "utilidad" and "utilidad" not in col_n:
            return False
        if sn == "costo" and "costo" not in col_n:
            return False
        if sn == "ventas" and "venta" not in col_n:
            return False
    return True


def _puntuar_coincidencia_metrica_voz(cmd_limpio: str, col: str, sinonimo: str) -> Optional[tuple[int, int]]:
    """Mayor puntaje = mejor match. None si no aplica."""
    if not _sinonimo_valido_para_metrica_voz(col, sinonimo):
        return None
    if not _coincide_sinonimo_en_comando(cmd_limpio, sinonimo):
        return None
    sn = _norm_texto(sinonimo)
    col_n = _norm_texto(col)
    score = len(sn)
    if col_n in cmd_limpio:
        score += 120
    if _comando_solicita_margen(cmd_limpio):
        if any(k in col_n for k in ("margen", "utilidad")) and "precio" not in col_n:
            score += 80
        if "precio" in col_n:
            score -= 100
    if _comando_solicita_precio(cmd_limpio) and "precio" in col_n:
        score += 60
    if _comando_pide_valor_inventario_voz(cmd_limpio):
        if any(k in col_n for k in ("valorinventario", "valordinventario")) and "precio" not in col_n:
            score += 70
        if "valor" in col_n and "inventario" in col_n and "promedio" in col_n:
            score += 90
    return (score, 1 if col_n in cmd_limpio else 0)


def _resolver_dimension_eje_x_voz(cmd_limpio: str, df: pd.DataFrame) -> Optional[str]:
    """Resuelve dimensión del eje X con patrones explícitos 'por …'."""
    if any(
        k in cmd_limpio
        for k in ("porproducto", "porarticulo", "poritem", "porsku", "pordescripcion", "porcodigo")
    ):
        return _resolver_columna_existente(df, "descripcion", "codigo")
    if _comando_menciona_subcategoria(cmd_limpio):
        return _resolver_columna_existente(df, "subcategoria")
    if "porcategoria" in cmd_limpio or (
        "categoria" in cmd_limpio and not _comando_menciona_subcategoria(cmd_limpio)
    ):
        return _resolver_columna_existente(df, "categoria")
    if "porpais" in cmd_limpio or (
        "pais" in cmd_limpio and any(p in cmd_limpio for p in ("por", "pais", "region", "nacion"))
    ):
        return _resolver_columna_existente(df, "pais")
    if "porproveedor" in cmd_limpio or "proveedor" in cmd_limpio:
        return _resolver_columna_existente(df, "proveedor")
    return None


def _resolver_metrica_inventario_voz(cmd_limpio: str, df: pd.DataFrame) -> Optional[str]:
    """Inventario promedio / final / tránsito / valor según el dictado."""
    if not _comando_solicita_inventario(cmd_limpio):
        return None
    if _comando_pide_valor_inventario_voz(cmd_limpio):
        hit = _columna_valor_inventario_promedio(df)
        if hit:
            return hit
        return _resolver_columna_existente(df, "valor inventario transito")
    if "promedio" in cmd_limpio or "promedi" in cmd_limpio or "inventariopromedio" in cmd_limpio:
        return _resolver_columna_existente(
            df,
            "inventario promedio bultos",
            "inventario promedio bultos ",
            "valor inventario promedio",
        )
    if "final" in cmd_limpio:
        return _resolver_columna_existente(df, "inventario final bulto")
    if any(k in cmd_limpio for k in ["transito", "transit", "camino", "flotante"]):
        return _resolver_columna_existente(df, "valor inventario transito")
    if "meses" in cmd_limpio or "cobertura" in cmd_limpio or "diasdeinventario" in cmd_limpio:
        return _resolver_columna_existente(df, "meses inventario")
    return _resolver_columna_existente(
        df,
        "inventario promedio bultos",
        "inventario promedio bultos ",
        "inventario final bulto",
        "valor inventario promedio",
    )


def _recortar_sufijo_dimension_voz(cmd_voz: str) -> str:
    """Quita la parte «por categoría / país / …» para aislar las métricas del dictado."""
    s = cmd_voz.strip()
    patrones_con_espacio = (
        r"\s+por\s+subcategor\w*",
        r"\s+por\s+categor\w*",
        r"\s+por\s+pais\w*",
        r"\s+por\s+proveedor\w*",
        r"\s+por\s+region\w*",
        r"\s+por\s+articulo\w*",
        r"\s+por\s+producto\w*",
        r"\s+por\s+cliente\w*",
    )
    for pat in patrones_con_espacio:
        m = re.search(pat, s, flags=re.I)
        if m:
            return s[: m.start()].strip()
    s_compact = _norm_texto(s)
    marcadores = (
        "porsubcategoria",
        "porcategoria",
        "porpais",
        "porproveedor",
        "porregion",
        "porarticulo",
        "porproducto",
        "porcliente",
        "porsku",
    )
    for marcador in sorted(marcadores, key=len, reverse=True):
        if marcador in s_compact:
            dim = marcador[3:]  # quita «por»
            m = re.search(rf"\s+por\s+{re.escape(dim)}\w*", s, flags=re.I)
            if m:
                return s[: m.start()].strip()
            return re.split(r"\s+por\s+", s, maxsplit=1, flags=re.I)[0].strip()
    m = re.search(r"\s+por\s+([a-z0-9]{3,24})\s*$", s, flags=re.I)
    if m:
        return s[: m.start()].strip()
    return s


def _limpiar_fragmento_metrica_voz(fragmento: str) -> str:
    frag = fragmento.strip()
    for articulo in ("las ", "los ", "la ", "el ", "una ", "un "):
        if frag.lower().startswith(articulo):
            frag = frag[len(articulo) :]
            break
    return frag.strip()


def _extraer_fragmentos_doble_metrica(cmd_voz: str) -> Tuple[Optional[str], Optional[str]]:
    """«ventas y utilidad bruta» → dos fragmentos antes del «por …»."""
    base = _recortar_sufijo_dimension_voz(cmd_voz)
    partes = re.split(r"\s+y\s+|\s+e\s+", base, maxsplit=1, flags=re.I)
    if len(partes) != 2:
        return None, None
    a = _limpiar_fragmento_metrica_voz(partes[0])
    b = _limpiar_fragmento_metrica_voz(partes[1])
    return (a, b) if a and b else (None, None)


def _extraer_doble_metrica_compacta(cmd_compact: str) -> Tuple[Optional[str], Optional[str]]:
    """Respaldo si el dictado llegó sin espacios (p. ej. lasventasyutilidadbrutaporsubcategoria)."""
    s = cmd_compact
    for marcador in (
        "porsubcategoria",
        "porcategoria",
        "porpais",
        "porproveedor",
        "porregion",
        "porarticulo",
        "porproducto",
    ):
        if marcador in s:
            s = s.split(marcador, 1)[0]
            break
    for pref in ("las", "los", "la", "el", "deseo", "quiero", "muestrame", "mostrarme"):
        if s.startswith(pref):
            s = s[len(pref) :]
    if "y" not in s[3:]:
        return None, None
    idx = s.find("y", 3)
    if idx <= 0:
        return None, None
    return s[:idx].strip() or None, s[idx + 1 :].strip() or None


def _comando_tiene_patron_doble_metrica(cmd_voz: str, cmd_compact: str) -> bool:
    if re.search(r"\s+y\s+|\s+e\s+", f" {cmd_voz.strip()} ", flags=re.I):
        return True
    if "venta" in cmd_compact and "y" in cmd_compact:
        if any(k in cmd_compact for k in ["util", "marg", "brut", "orden", "pedid", "bult", "invent"]):
            return True
    return False


def _resolver_metrica_fragmento_voz(
    fragmento: str, df: pd.DataFrame, diccionario: dict
) -> Optional[str]:
    """Resuelve una métrica aislada (p. ej. «ventas», «utilidad bruta», «órdenes»)."""
    frag = _norm_texto(fragmento)
    if not frag:
        return None
    if any(k in frag for k in ["orden", "pedid", "pick"]):
        hit = _resolver_columna_existente(df, "ordenes", "órdenes", "orden", "pedidos")
        if hit:
            return hit
    if any(k in frag for k in ["inventario", "stock", "existencias"]):
        return _resolver_metrica_inventario_voz(frag, df)
    if _comando_solicita_ventas(frag) and not any(k in frag for k in ["util", "marg", "brut"]):
        return _resolver_columna_existente(df, "ventas totales", "ventas total")
    if any(k in frag for k in ["util", "marg", "brut"]):
        return _resolver_columna_existente(
            df,
            "margen bruto total",
            "margen utilidad",
            "margen utilidad ",
            "utilidad bruta",
        )
    if "rotacion" in frag or "rotación" in frag:
        return _resolver_columna_existente(df, "rotacion", "rotación", "rotacion inventario")
    coincidencias: list = []
    for col_real, sinonimos in diccionario["eje_y"].items():
        for sinonimo in sinonimos:
            sn = _norm_texto(sinonimo)
            if len(sn) >= 4 and (sn in frag or frag in sn):
                if not _sinonimo_valido_para_metrica_voz(col_real, sinonimo):
                    continue
                coincidencias.append((col_real, len(sn), sn == frag))
    if coincidencias:
        coincidencias.sort(key=lambda x: (x[1], x[2]), reverse=True)
        return coincidencias[0][0]
    return None


def _resolver_metrica_ventas_voz(cmd_limpio: str, df: pd.DataFrame) -> Optional[str]:
    """Desambigua 'ventas' frente a columnas que solo comparten el sinónimo genérico."""
    if not _comando_solicita_ventas(cmd_limpio):
        return None
    if any(k in cmd_limpio for k in ["util", "marg", "brut"]):
        if "cost" in cmd_limpio:
            return _resolver_columna_existente(df, "ventas costo")
        return _resolver_columna_existente(df, "margen utilidad ", "margen utilidad", "margen bruto total")
    if "cost" in cmd_limpio or "alcost" in cmd_limpio:
        return _resolver_columna_existente(df, "ventas costo")
    return _resolver_columna_existente(df, "ventas totales")


def aplicar_config_perfil_en_sesion(config: dict) -> None:
    """Aplica perfil (voz o botón rápido) sin pisar widgets ya instanciados."""
    st.session_state["lri_aplicar_voz_pendiente"] = config
    for clave, valor in config.items():
        st.session_state[clave] = valor
    forzar_sincronizacion_espejo()


def procesar_comando_voz_estructurado(comando_texto: str, df: pd.DataFrame) -> dict:
    """Interpreta el dictado y devuelve la configuración a aplicar en session_state."""
    cmd_voz = _preprocesar_comando_voz(_normalizar_comando_voz(comando_texto))
    cmd_limpio = _norm_texto(cmd_voz)
    config = {"comando_voz_detectado": comando_texto}

    # 1. DETECCIÓN MATEMÁTICA DE LA OPERACIÓN
    if any(kw in cmd_limpio for kw in ["prom", "avera", "media", "error", "desvia"]):
        config["lri_man_operacion"] = "Promedio"
        config["lri_man_operacion_y"] = "Promedio"
    elif any(
        kw in cmd_limpio
        for kw in [
            "sum", "tot", "unid", "bult", "cant", "deman", "cost", "transit",
            "orden", "pedi", "pick", "exact", "servi", "fill", "margen", "utili",
        ]
    ) or _comando_solicita_ventas(cmd_limpio):
        config["lri_man_operacion"] = "Suma"
        config["lri_man_operacion_y"] = "Suma"

    # 2. GENERACIÓN DEL MAPA SEMÁNTICO DINÁMICO
    diccionario = generar_diccionario_semantico_dinamico(df)

    columna_seleccionada_x = _resolver_dimension_eje_x_voz(cmd_limpio, df)

    if _comando_tiene_patron_doble_metrica(cmd_voz, cmd_limpio):
        frag_a, frag_b = _extraer_fragmentos_doble_metrica(cmd_voz)
        if not (frag_a and frag_b):
            frag_a, frag_b = _extraer_doble_metrica_compacta(cmd_limpio)
        if frag_a and frag_b:
            metrica_a = _resolver_metrica_fragmento_voz(frag_a, df, diccionario)
            metrica_b = _resolver_metrica_fragmento_voz(frag_b, df, diccionario)
            if metrica_a and metrica_b and metrica_a != metrica_b:
                config["lri_man_eje_y"] = metrica_a
                config["lri_man_eje_y2"] = metrica_b
                config["lri_man_eje_y3"] = METRICA_ADICIONAL_NINGUNA
                if columna_seleccionada_x:
                    config["lri_man_eje_x"] = columna_seleccionada_x
                elif _comando_menciona_subcategoria(cmd_limpio):
                    sub = _resolver_columna_existente(df, "subcategoria")
                    if sub:
                        config["lri_man_eje_x"] = sub
                else:
                    for col_real, sinonimos in diccionario["eje_x"].items():
                        if any(
                            _coincide_sinonimo_en_comando(cmd_limpio, s) for s in sinonimos
                        ):
                            config["lri_man_eje_x"] = col_real
                            break
                return config

    columna_seleccionada_y = _resolver_metrica_inventario_voz(cmd_limpio, df)
    if not columna_seleccionada_y:
        columna_seleccionada_y = _resolver_metrica_margen_voz(cmd_limpio, df)
    if not columna_seleccionada_y:
        columna_seleccionada_y = _resolver_metrica_precio_voz(cmd_limpio, df)
    if not columna_seleccionada_y:
        columna_seleccionada_y = _resolver_metrica_ventas_voz(cmd_limpio, df)

    # 3. ESCANEO DEL EJE Y (solo si no se pidió ventas de forma explícita)
    if not columna_seleccionada_y and not _comando_solicita_ventas(cmd_limpio):
        coincidencias_y = []
        for col_real, sinonimos in diccionario["eje_y"].items():
            for sinonimo in sinonimos:
                puntaje = _puntuar_coincidencia_metrica_voz(cmd_limpio, col_real, sinonimo)
                if puntaje is not None:
                    coincidencias_y.append((col_real, puntaje[0], puntaje[1]))

        if coincidencias_y:
            coincidencias_y.sort(key=lambda x: (x[1], x[2]), reverse=True)
            columna_seleccionada_y = coincidencias_y[0][0]

    if not columna_seleccionada_y and _comando_solicita_ventas(cmd_limpio):
        columna_seleccionada_y = _resolver_columna_existente(df, "ventas totales")

    if columna_seleccionada_y:
        config["lri_man_eje_y"] = columna_seleccionada_y
        config["lri_man_eje_y2"] = METRICA_ADICIONAL_NINGUNA
        config["lri_man_eje_y3"] = METRICA_ADICIONAL_NINGUNA

    # 4. CONTEXTO DE CONVERGENCIA PARA DRILL-DOWN LOGÍSTICO
    if any(kw in cmd_limpio for kw in ["articulo", "producto", "item", "sku", "codigo"]):
        if st.session_state.get("drill_down_categoria"):
            for col_real in diccionario["eje_x"].keys():
                if any(kw in _norm_texto(col_real) for kw in ["desc", "prod", "articulo", "item", "sku"]):
                    config["lri_man_eje_x"] = col_real
                    return config

    # 5. ESCANEO DEL EJE X (respaldo semántico)
    if not columna_seleccionada_x:
        if _comando_menciona_subcategoria(cmd_limpio):
            for col_real, sinonimos in diccionario["eje_x"].items():
                if "sub" in _norm_texto(col_real) and any(
                    _coincide_sinonimo_en_comando(cmd_limpio, s) for s in sinonimos
                ):
                    columna_seleccionada_x = col_real
                    break
        else:
            for col_real, sinonimos in diccionario["eje_x"].items():
                if "sub" not in _norm_texto(col_real) and any(
                    _coincide_sinonimo_en_comando(cmd_limpio, s) for s in sinonimos
                ):
                    columna_seleccionada_x = col_real
                    break

    if columna_seleccionada_x:
        config["lri_man_eje_x"] = columna_seleccionada_x

    return config


def aplicar_config_voz_pendiente() -> bool:
    """Aplica la configuración de voz antes de dibujar widgets (evita que los pisen)."""
    pendiente = st.session_state.pop("lri_aplicar_voz_pendiente", None)
    if not pendiente:
        return False
    for clave, valor in pendiente.items():
        st.session_state[clave] = valor
    return True


def procesar_grabacion_voz_sidebar(df: pd.DataFrame, audio_bytes: bytes) -> None:
    """Transcribe el audio y aplica el perfilado (mismo flujo que antes con mic_recorder)."""
    audio_hash = hashlib.md5(audio_bytes, usedforsecurity=False).hexdigest()
    if audio_hash == st.session_state.get("lri_last_audio_hash"):
        return
    st.session_state["lri_last_audio_hash"] = audio_hash
    r = sr.Recognizer()
    try:
        with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
            r.adjust_for_ambient_noise(source, duration=0.2)
            audio_data = r.record(source)
        texto_dictado = r.recognize_google(audio_data, language="es-CR")
        config_voz = procesar_comando_voz_estructurado(texto_dictado, df)
        aplicar_config_perfil_en_sesion(config_voz)
        eje_x = config_voz.get("lri_man_eje_x", st.session_state.get("lri_man_eje_x"))
        eje_y = config_voz.get("lri_man_eje_y", st.session_state.get("lri_man_eje_y"))
        st.sidebar.success(
            f"Comando aplicado: **{eje_y}** por **{eje_x}**."
            if eje_x and eje_y
            else "Comando analizado aplicado con éxito."
        )
        st.rerun()
    except sr.UnknownValueError:
        st.sidebar.error("No se entendió la instrucción de voz.")
    except sr.RequestError:
        st.sidebar.error("Error en conexión con el motor de voz.")
    except Exception as e:
        st.sidebar.error(f"Error: {e}")


def _css_control_voz_sidebar() -> str:
    """Micrófono compacto en fila con el título (ahorra espacio en el sidebar)."""
    return """
<style>
section[data-testid="stSidebar"] .lri-voz-row [data-testid="column"] {
    padding-top: 0 !important;
    padding-bottom: 0 !important;
}
section[data-testid="stSidebar"] .lri-voz-row [data-testid="stCustomComponent"] {
    margin: 0 !important;
    padding: 0 !important;
    background: transparent !important;
}
section[data-testid="stSidebar"] .lri-voz-row [data-testid="stCustomComponent"] iframe {
  height: 3.25rem !important;
  min-height: 3.25rem !important;
  max-height: 3.25rem !important;
  background: transparent !important;
  border: none !important;
}
section[data-testid="stSidebar"] .lri-voz-row [data-testid="stCustomComponent"] {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}
</style>
"""


def _render_control_voz_sidebar(df: pd.DataFrame) -> None:
    """Título y micrófono en la misma fila: blanco → verde al grabar → blanco al terminar."""
    st.markdown(_css_control_voz_sidebar(), unsafe_allow_html=True)
    st.divider()
    st.markdown('<div class="lri-voz-row">', unsafe_allow_html=True)
    col_tit, col_mic = st.columns([1.2, 0.55], gap="small", vertical_alignment="center")
    with col_tit:
        st.markdown(
            dedent(
                """\
                <div style="color:#ffffff;line-height:1.25;">
                  <div style="font-size:1.02rem;font-weight:700;margin:0;">🎙️ Control por Voz Activo</div>
                  <div style="font-size:0.78rem;font-weight:400;color:#e2e8f0;margin-top:2px;">
                    Darle un clic para hablar
                  </div>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )
    with col_mic:
        audio = audio_recorder(
            text="",
            pause_threshold=_VOICE_PAUSA_SILENCIO_SEG,
            energy_threshold=0.01,
            sample_rate=44100,
            neutral_color="#FFFFFF",
            recording_color="#22c55e",
            icon_name="microphone",
            icon_size="4x",
            key="lri_mic_console",
        )
        audio_bytes = audio.get("bytes") if isinstance(audio, dict) else audio

    st.markdown("</div>", unsafe_allow_html=True)

    if audio_bytes:
        procesar_grabacion_voz_sidebar(df, audio_bytes)

    if st.session_state.get("comando_voz_detectado"):
        st.info(f'Instrucción: *"{st.session_state["comando_voz_detectado"]}"*')


def _sincronizar_operaciones_metricas() -> None:
    """Migra el cálculo global legacy y mantiene lri_man_operacion alineado al eje Y principal."""
    legacy = st.session_state.get("lri_man_operacion", "Suma")
    for key in ("lri_man_operacion_y", "lri_man_operacion_y2", "lri_man_operacion_y3"):
        if key not in st.session_state or st.session_state[key] not in OPS_CALCULO:
            st.session_state[key] = legacy if legacy in OPS_CALCULO else "Suma"
    st.session_state["lri_man_operacion"] = st.session_state.get("lri_man_operacion_y", "Suma")


def forzar_sincronizacion_espejo():
    st.session_state["prev_manual_x"] = st.session_state["lri_man_eje_x"]
    st.session_state["prev_manual_y"] = st.session_state["lri_man_eje_y"]
    st.session_state["prev_manual_op"] = st.session_state["lri_man_operacion"]
    st.session_state["prev_manual_top"] = st.session_state["lri_man_top_n"]


def _logo_lri_base64() -> Optional[str]:
    if not os.path.isfile(ARCHIVO_LOGO_LRI):
        return None
    with open(ARCHIVO_LOGO_LRI, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _render_cabecera_app(subtitulo: Optional[str] = None) -> None:
    """Logo + título compactos arriba; no reduce el área de gráficos/tablas/ABC."""
    logo_b64 = _logo_lri_base64()
    img_html = (
        f'<img src="data:image/png;base64,{logo_b64}" alt="LRI" class="lri-app-logo" />'
        if logo_b64
        else ""
    )
    sub = (
        f'<div class="lri-app-sub">{subtitulo}</div>'
        if subtitulo
        else ""
    )
    st.markdown(
        f"""<div class="lri-app-header">
  {img_html}
  <div class="lri-app-brand">
    <span class="lri-app-title">Profile <span class="lri-app-pro">Pro</span></span>
    {sub}
  </div>
</div>""",
        unsafe_allow_html=True,
    )


# ==============================================================================
# CAPA 3: LÓGICA DE NEGOCIO / PROCESAMIENTO DE PERFILES Y PARETO
# ==============================================================================
def _columna_ventas_totales(df: pd.DataFrame) -> Optional[str]:
    return _resolver_columna_existente(df, "ventas totales")


def _columna_margen_bruto(df: pd.DataFrame) -> Optional[str]:
    return _resolver_columna_existente(df, "margen bruto total")


def _columna_margen_utilidad_ratio(df: pd.DataFrame) -> Optional[str]:
    return _resolver_columna_existente(
        df,
        "margen utilidad ",
        "margen utilidad",
        "margen utilidad ventas",
        "margen de utilidad",
        "porcentaje utilidad bruta",
        "utilidad bruta",
        "pct utilidad bruta",
    )


def _columna_costo_mantener_inventario(df: pd.DataFrame) -> Optional[str]:
    return _resolver_columna_existente(
        df,
        "costo mantener inventario",
        "tasa mantener inventario",
        "tasa mantener inventarios",
        "tasa de mantener inventario",
        "tasa costo mantener inventario",
        "tasa costo inventario",
        "tasa de costo inventario",
    )


def _metrica_margen_sobre_ventas(df: pd.DataFrame, eje_y: str) -> bool:
    mb = _columna_margen_bruto(df)
    mu = _columna_margen_utilidad_ratio(df)
    return (mb is not None and eje_y == mb) or (mu is not None and eje_y == mu)


def _metrica_costo_mantener_pct(df: pd.DataFrame, eje_y: str) -> bool:
    cm = _columna_costo_mantener_inventario(df)
    if cm is not None and eje_y == cm:
        return True
    n = _norm_texto(eje_y)
    return any(
        p in n
        for p in (
            "costomantener",
            "mantenerinventario",
            "tasamantener",
            "tasamantenimiento",
            "tasacostoinventario",
            "tasadecosto",
            "tasacosto",
        )
    )


def _nombre_eje_y_es_porcentual(eje_y: str) -> bool:
    """Margen/utilidad/tasa/porcentaje en el nombre de columna → presentación %."""
    raw = str(eje_y).strip().lower()
    if "%" in raw or "pct" in raw or "porcent" in raw or "percent" in raw:
        return True
    n = _norm_texto(eje_y)
    patrones = (
        "margenutilidad",
        "margendautilidad",
        "margenbruto",
        "utilidadbruta",
        "utilidadneta",
        "pctutilidad",
        "porcentajeutilidad",
        "margenbrutopct",
        "margensobreventas",
        "margenventas",
        "costomantenerinventario",
        "mantenerinventario",
        "costoinventario",
        "tasacosto",
        "tasamantenimiento",
        "tasamantener",
        "tasadecosto",
        "tasacostoinventario",
    )
    if any(p in n for p in patrones):
        return True
    if "margen" in n and ("pct" in n or "porcent" in n or "ratio" in n or "tasa" in n or "util" in n):
        return True
    if "utilidad" in n:
        return True
    if "tasa" in n and any(k in n for k in ("costo", "manten", "invent", "margen", "util")):
        return True
    return False


def _metrica_eje_y_en_porcentaje(df: pd.DataFrame, eje_y: str) -> bool:
    if _metrica_margen_sobre_ventas(df, eje_y) or _metrica_costo_mantener_pct(df, eje_y):
        return True
    if _nombre_eje_y_es_porcentual(eje_y):
        return True
    mb = _columna_margen_bruto(df)
    mu = _columna_margen_utilidad_ratio(df)
    cm = _columna_costo_mantener_inventario(df)
    return eje_y in {c for c in (mb, mu, cm) if c}


def _porcentaje_en_escala_0_100(serie: pd.Series) -> bool:
    """True si los valores parecen 0–100 (p. ej. 15.5 = 15,5%) y no fracción 0–1."""
    v = pd.to_numeric(serie, errors="coerce").dropna()
    if v.empty:
        return False
    return float(v.abs().max()) > 1.5


def _info_presentacion_porcentaje_eje_y(
    df: pd.DataFrame,
    eje_y: str,
    df_valores: Optional[pd.DataFrame] = None,
) -> Tuple[bool, bool]:
    """(es_porcentaje, escala_0_100) para KPI, tabla, gráfico y export."""
    es_pct = _metrica_eje_y_en_porcentaje(df, eje_y)
    if not es_pct:
        return False, False
    fuente = df_valores if df_valores is not None and eje_y in df_valores.columns else df
    if eje_y not in fuente.columns:
        return es_pct, False
    return es_pct, _porcentaje_en_escala_0_100(fuente[eje_y])


def _formatear_valor_porcentaje(val: float, escala_0_100: bool) -> str:
    if escala_0_100:
        return f"{val:.2f}%"
    return f"{val:.2%}"


def _fmt_pandas_columna_porcentaje(escala_0_100: bool) -> str:
    return "{:.2f}%" if escala_0_100 else "{:.2%}"


def _ratio_margen_por_fila(df: pd.DataFrame, eje_y: str) -> pd.Series:
    """Ratio 0–1 margen sobre ventas a nivel fila (margen bruto absoluto o columna ya en ratio)."""
    vt = _columna_ventas_totales(df)
    mb = _columna_margen_bruto(df)
    mu = _columna_margen_utilidad_ratio(df)
    if vt is None or vt not in df.columns:
        return pd.Series(np.nan, index=df.index)
    v = df[vt].replace(0, np.nan)
    if mb is not None and eje_y == mb:
        return df[eje_y] / v
    if mu is not None and eje_y == mu:
        return df[eje_y]
    return pd.Series(np.nan, index=df.index)


def calcular_metricas_encabezado(
    df_filtrado: pd.DataFrame, eje_y: str, operacion: str
) -> Tuple[str, str]:
    if _metrica_margen_sobre_ventas(df_filtrado, eje_y):
        ratios = _ratio_margen_por_fila(df_filtrado, eje_y).dropna()
        if ratios.empty:
            val_total = 0.0
        elif operacion == "Suma":
            vt = _columna_ventas_totales(df_filtrado)
            mb = _columna_margen_bruto(df_filtrado)
            mu = _columna_margen_utilidad_ratio(df_filtrado)
            if vt is None:
                val_total = 0.0
            elif mb is not None and eje_y == mb:
                num = df_filtrado[eje_y].sum()
                den = df_filtrado[vt].sum()
                val_total = float(num / den) if den else 0.0
            elif mu is not None and eje_y == mu:
                num = (df_filtrado[eje_y] * df_filtrado[vt]).sum()
                den = df_filtrado[vt].sum()
                val_total = float(num / den) if den else 0.0
            else:
                val_total = 0.0
        else:
            val_total = float(ratios.mean())
        label = (
            f"{'Total' if operacion == 'Suma' else 'Promedio'} {eje_y} (% sobre ventas)"
        )
        val_formateado = _formatear_valor_porcentaje(val_total, False)
        return label, val_formateado

    if _metrica_costo_mantener_pct(df_filtrado, eje_y):
        s = df_filtrado[eje_y].dropna()
        val_total = float(s.mean()) if len(s) else 0.0
        label = f"Tasa media {eje_y}"
        val_formateado = _formatear_valor_porcentaje(
            val_total, _porcentaje_en_escala_0_100(s)
        )
        return label, val_formateado

    if _nombre_eje_y_es_porcentual(eje_y) and eje_y in df_filtrado.columns:
        s = pd.to_numeric(df_filtrado[eje_y], errors="coerce").dropna()
        escala = _porcentaje_en_escala_0_100(s)
        if operacion == "Suma":
            val_total = float(s.sum()) if len(s) else 0.0
            label = f"Total {eje_y}"
        else:
            val_total = float(s.mean()) if len(s) else 0.0
            label = f"Promedio {eje_y}"
        return label, _formatear_valor_porcentaje(val_total, escala)

    if operacion == "Suma":
        val_total = df_filtrado[eje_y].sum() if eje_y in df_filtrado.columns else 0
        label = f"Total {eje_y}"
        val_formateado = f"{val_total:,.0f}"
    else:
        val_total = df_filtrado[eje_y].mean() if eje_y in df_filtrado.columns else 0
        label = f"Promedio {eje_y}"
        val_formateado = f"{val_total:,.2f}"

    return label, val_formateado


def _extremos_eje_y_perfilado(df_resumen: pd.DataFrame, eje_y: str) -> Tuple[float, float]:
    """Máximo y mínimo del eje Y entre las barras del perfilado (valores agrupados)."""
    if df_resumen.empty or eje_y not in df_resumen.columns:
        return 0.0, 0.0
    s = df_resumen[eje_y].astype(float).dropna()
    if s.empty:
        return 0.0, 0.0
    return float(s.max()), float(s.min())


def _formatear_valor_kpi_eje_y(val: float, y_pct: bool, escala_0_100: bool = False) -> str:
    if y_pct:
        return _formatear_valor_porcentaje(val, escala_0_100)
    if abs(val) < 100:
        return f"{val:,.2f}"
    return f"{val:,.0f}"


def _metrica_pareto_menor_es_mejor(col: str) -> bool:
    """True si la métrica debe clasificarse con Pareto invertido (poco = verde, mucho = rojo)."""
    key = _norm_texto(col)
    for patron in _PARETO_METRICAS_MENOR_ES_MEJOR:
        p = _norm_texto(patron)
        if key == p or key.startswith(p):
            return True
    return False


def _resolver_fracciones_pareto_por_item(set_seleccionado: str) -> Optional[Tuple[float, float, float]]:
    """Fracciones (top, medio, cola) del número de filas del eje X, ordenadas por métrica."""
    if "Desactivado" in set_seleccionado:
        return None
    for clave, fracciones in PRESETS_PARETO.items():
        if clave in set_seleccionado:
            return fracciones
    if "80%" in set_seleccionado:
        return PRESETS_PARETO["5% - 10% - 85%"]
    if "70%" in set_seleccionado:
        return PRESETS_PARETO["10% - 15% - 75%"]
    if "60%" in set_seleccionado:
        return PRESETS_PARETO["20% - 30% - 50%"]
    return None


def _conteos_tres_segmentos(n: int, f1: float, f2: float, f3: float) -> Tuple[int, int, int]:
    """Reparte n filas en tres grupos según fracciones (mayor resto para cuadrar suma n)."""
    if n <= 0:
        return (0, 0, 0)
    raw = [n * f1, n * f2, n * f3]
    base = [int(x) for x in raw]
    rem = n - sum(base)
    frac_rem = [raw[i] - base[i] for i in range(3)]
    order = sorted(range(3), key=lambda i: -frac_rem[i])
    i = 0
    while rem > 0:
        base[order[i % 3]] += 1
        rem -= 1
        i += 1
    return (base[0], base[1], base[2])


def _tamanos_segmentos_pareto(n: int, f1: float, f2: float, f3: float) -> Tuple[int, int, int]:
    """Mismos cortes que en `aplicar_logica_colores_pareto` (incl. mínimo 1 ítem en top si aplica)."""
    n1, n2, n3 = _conteos_tres_segmentos(n, f1, f2, f3)
    if n >= 1 and n1 == 0 and f1 > 0:
        n1 = 1
        n3 = max(0, n - n1 - n2)
    if n3 < 0:
        n2 = max(0, n2 + n3)
        n3 = 0
    return (n1, n2, n3)


def _etiquetas_tramos_pareto(set_pareto: str) -> Tuple[str, str, str]:
    for clave, letras in ETIQUETAS_BANDA_PARETO.items():
        if clave in set_pareto:
            return letras
    return ("Tramo 1", "Tramo 2", "Tramo 3")


def _eje_x_es_codigo_producto(eje_x: str) -> bool:
    nx = _norm_texto(eje_x)
    return nx in ("codigo", "sku", "claveproducto", "clavesku") or (
        "codigo" in nx and "categoria" not in nx
    )


def _resolver_columna_descripcion(df: pd.DataFrame) -> Optional[str]:
    for cand in ("descripcion", "descripción", "articulo", "producto", "nombre", "material"):
        hit = _resolver_columna_existente(df, cand)
        if hit is not None:
            return hit
    return None


_ALTURA_MIN_TABLA_SCROLL = 220
_TABLA_PANEL_OVERHEAD_PX = 62  # título + padding del panel (dentro del borde)
_TABLA_BOTON_EXCEL_PX = 46  # botón «Guardar en Excel» encima del panel


def _altura_scroll_tabla_metricas(
    n_filas: int,
    clase_css: str,
    tabla_font_size: int,
    viewport_h: int,
    n_filas_grafico: Optional[int] = None,
    eje_x: str = "",
    max_label_len: int = 0,
    ver_completo_pantalla: bool = False,
) -> int:
    """Altura del scroll alineada al gráfico (hasta el eje X, p. ej. «código»)."""
    n_chart = n_filas_grafico if n_filas_grafico is not None else n_filas
    if _scroll_grafico_activo(n_chart, eje_x, ver_completo_pantalla=ver_completo_pantalla):
        altura_graf = _altura_grafico_scroll_horizontal(n_chart, viewport_h)
    else:
        altura_graf = altura_grafico_adaptativa(n_chart, viewport_h)
    overhead = _TABLA_PANEL_OVERHEAD_PX + _TABLA_BOTON_EXCEL_PX
    return int(max(_ALTURA_MIN_TABLA_SCROLL, altura_graf - overhead))


def _preparar_tabla_metricas_detalle(
    df_resumen: pd.DataFrame,
    df_origen: pd.DataFrame,
    eje_x: str,
    eje_y: str,
    viewport_h: int = 1080,
    tabla_font_size: int = 14,
    eje_y2: Optional[str] = None,
    metricas_extra: Optional[list[str]] = None,
    ver_completo_pantalla: bool = False,
) -> Tuple[pd.DataFrame, list, str, int]:
    """
    Arma la tabla lateral: dimensión + métrica(s); código + producto si aplica.
    Devuelve (df, columnas, clase CSS, altura scroll sugerida).
    """
    out = df_resumen.copy()
    extras = [
        m
        for m in (metricas_extra or [])
        if m and m in out.columns and m not in (eje_y, eje_y2)
    ]
    if eje_y2 and eje_y2 in out.columns and eje_y2 != eje_y and eje_y2 not in extras:
        extras.insert(0, eje_y2)
    columnas = [eje_x, eje_y] + [m for m in extras if m != eje_y]
    n_metricas = len(columnas) - 1
    clase_css = "lri-tabla-col-2col"
    if n_metricas >= 2:
        clase_css = "lri-tabla-col-3col-dual"
    if n_metricas >= 3:
        clase_css = "lri-tabla-col-multimetrica"
    n_filas = len(out)

    if _eje_x_es_codigo_producto(eje_x):
        col_desc = _resolver_columna_descripcion(df_origen)
        if col_desc and col_desc in df_origen.columns and eje_x in out.columns:
            mapa_prod = (
                df_origen[[eje_x, col_desc]]
                .dropna(subset=[eje_x])
                .astype({eje_x: str})
                .drop_duplicates(subset=[eje_x], keep="first")
                .set_index(eje_x)[col_desc]
                .astype(str)
            )
            out.insert(
                1,
                "producto",
                out[eje_x].astype(str).map(mapa_prod).fillna("—"),
            )
            columnas = [eje_x, "producto", eje_y] + [m for m in extras if m != eje_y]
            if n_metricas >= 3:
                clase_css = "lri-tabla-col-multimetrica-prod"
            elif n_metricas >= 2:
                clase_css = "lri-tabla-col-4col"
            else:
                clase_css = "lri-tabla-col-3col"

    out = out[columnas].copy()
    xs_graf = out[eje_x].astype(str).tolist() if eje_x in out.columns else []
    max_label_len = max((len(x) for x in xs_graf), default=0)
    altura_scroll = _altura_scroll_tabla_metricas(
        n_filas,
        clase_css,
        tabla_font_size,
        viewport_h,
        eje_x=eje_x,
        max_label_len=max_label_len,
        ver_completo_pantalla=ver_completo_pantalla,
    )
    return out, columnas, clase_css, altura_scroll


# Anchos fijos de columnas (px); el slider solo cambia el tamaño de letra en celdas.
_ANCHOS_TABLA_3COL = (72, 248, 102)
_ANCHOS_TABLA_2COL = (158, 102)
_ANCHOS_TABLA_3COL_DUAL = (128, 96, 96)  # dimensión + 2 métricas
_ANCHOS_TABLA_4COL = (68, 200, 92, 92)  # código + producto + 2 métricas
_FS_TITULO_PANEL_TABLA = 15  # fijo; no sigue al slider de texto de tabla


# Resumen ABC Pareto: no modificar ancho ni tipografías del panel lateral.
_ANCHO_MAX_RESUMEN_PARETO = 268
_ANCHO_GRAFICO_PARETO_PX = 920  # un poco menos que antes; el ancho sobrante va a la tabla
_ANCHO_SIDEBAR_APROX = 300
_SEPARACION_TABLA_GRAFICO_PX = 12


def _pesos_columnas_pareto(dims_tabla: dict[str, Any]) -> Tuple[float, float, float, int]:
    """Tabla fija; gráfico ocupa el espacio central; resumen ABC un poco más ancho."""
    n = int(dims_tabla.get("n_cols", 2))
    margen_tabla = 64 + (56 if n >= 5 else (28 if n >= 4 else 0))
    w_tabla = float(dims_tabla["ancho_tabla"] + margen_tabla)
    w_resumen = float(_ANCHO_MAX_RESUMEN_PARETO + 40)
    ancho_util = max(900, REF_VIEWPORT_W - _ANCHO_SIDEBAR_APROX)
    min_graf = _ANCHO_GRAFICO_PARETO_PX - (48 if n >= 5 else (16 if n >= 4 else 0))
    ancho_graf = int(
        max(min_graf, ancho_util - w_tabla - w_resumen - _SEPARACION_TABLA_GRAFICO_PX)
    )
    w_grafico = float(ancho_graf)
    return w_tabla, w_grafico, w_resumen, ancho_graf


def _proporcion_tabla_vs_grafico(n_cols_tabla: int, pareto_activo: bool) -> Tuple[float, float]:
    """Sin Pareto: más peso a la columna tabla; gráfico sigue con ancho fijo en fig_ranking_barras."""
    if n_cols_tabla >= 5:
        return 1.05, 2.05
    if n_cols_tabla >= 4:
        return 0.98, 2.05
    if n_cols_tabla >= 3:
        return 0.85, 2.28
    return 0.82, 2.22


def _dims_tabla_metricas(clase: str, tabla_font_size: int) -> dict[str, Any]:
    """Anchos fijos; fs_celda compacta para ver más filas (ABC Pareto usa base_font_size)."""
    fs = max(10, min(28, tabla_font_size))
    fs_celda = max(10, fs)
    pad_v, pad_h = 1, 3
    if clase == "lri-tabla-col-4col":
        anchos = list(_ANCHOS_TABLA_4COL)
    elif clase in ("lri-tabla-col-multimetrica", "lri-tabla-col-multimetrica-prod"):
        anchos = [118, 88, 88, 92] if clase == "lri-tabla-col-multimetrica" else [64, 124, 84, 84, 104]
    elif clase == "lri-tabla-col-3col-dual":
        anchos = list(_ANCHOS_TABLA_3COL_DUAL)
    elif clase == "lri-tabla-col-3col":
        anchos = list(_ANCHOS_TABLA_3COL)
    else:
        anchos = list(_ANCHOS_TABLA_2COL)
    ancho_tabla = sum(anchos) + len(anchos) * pad_h * 2 + 16
    return {
        "fs": fs,
        "fs_celda": fs_celda,
        "pad_v": pad_v,
        "pad_h": pad_h,
        "anchos_cols": anchos,
        "ancho_tabla": ancho_tabla,
        "n_cols": len(anchos),
        "col_producto_idx": 1
        if clase in ("lri-tabla-col-3col", "lri-tabla-col-4col", "lri-tabla-col-multimetrica-prod")
        else None,
        "tiene_dos_metricas": clase
        in ("lri-tabla-col-3col-dual", "lri-tabla-col-4col", "lri-tabla-col-multimetrica", "lri-tabla-col-multimetrica-prod"),
    }


def _extraer_tabla_html_pandas(html: str) -> str:
    """Elimina <style> de pandas (en Streamlit se mostraba como código visible)."""
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.S | re.I)
    m = re.search(r"<table[^>]*>.*?</table>", html, flags=re.S | re.I)
    return m.group(0) if m else html


def _merge_style_attr(tag: str, estilo: str) -> str:
    if 'style="' in tag:
        return tag.replace('style="', f'style="{estilo}', 1)
    return tag[:-1] + f' style="{estilo}">'


def _aplicar_estilo_celdas_html(
    html: str,
    fs: int,
    estilos_por_fila: Optional[list[str]] = None,
    estilos_por_celda: Optional[list[list[str]]] = None,
) -> str:
    """Font-size inline en th/td (Streamlit ignora CSS externo al quitar el <style> de pandas)."""
    estilo_th = f"font-size:{fs}px;color:#ffffff;text-align:left;"
    estilo_td = f"font-size:{fs}px;color:#f8fafc;text-align:center;"

    html = re.sub(
        r"<th[^>]*>",
        lambda m: _merge_style_attr(m.group(0), estilo_th),
        html,
        flags=re.I,
    )

    if not estilos_por_fila and not estilos_por_celda:
        return re.sub(
            r"<td[^>]*>",
            lambda m: _merge_style_attr(m.group(0), estilo_td),
            html,
            flags=re.I,
        )

    tbody_m = re.search(r"(<tbody[^>]*>)(.*?)(</tbody>)", html, flags=re.S | re.I)
    if not tbody_m:
        return re.sub(
            r"<td[^>]*>",
            lambda m: _merge_style_attr(m.group(0), estilo_td),
            html,
            flags=re.I,
        )

    prefix, body, suffix = tbody_m.group(1), tbody_m.group(2), tbody_m.group(3)
    filas = re.findall(r"<tr[^>]*>.*?</tr>", body, flags=re.S | re.I)
    cuerpo_nuevo = []
    for i, tr in enumerate(filas):
        if estilos_por_celda and i < len(estilos_por_celda):
            estilos_fila = estilos_por_celda[i]
            j = 0

            def repl_celda(m, estilos=estilos_fila):
                nonlocal j
                est = estilos[j] if j < len(estilos) else estilo_td
                j += 1
                if "font-size" not in est:
                    est = f"font-size:{fs}px;" + est
                if "text-align" not in est:
                    est = "text-align:center;" + est
                return _merge_style_attr(m.group(0), est)

            cuerpo_nuevo.append(re.sub(r"<td[^>]*>", repl_celda, tr, flags=re.I))
            continue

        est = estilos_por_fila[i] if estilos_por_fila and i < len(estilos_por_fila) else estilo_td
        if "font-size" not in est:
            est = f"font-size:{fs}px;" + est
        if "text-align" not in est:
            est = "text-align:center;" + est
        cuerpo_nuevo.append(
            re.sub(
                r"<td[^>]*>",
                lambda m, e=est: _merge_style_attr(m.group(0), e),
                tr,
                flags=re.I,
            )
        )
    cuerpo = prefix + "".join(cuerpo_nuevo) + suffix
    return html[: tbody_m.start()] + cuerpo + html[tbody_m.end() :]


def _anotar_indices_columna_html(html: str) -> str:
    """Añade clases col0, col1… a th/td para que apliquen los anchos CSS."""

    def _anotar_fila(match: re.Match[str]) -> str:
        apertura, cuerpo, cierre = match.group(1), match.group(2), match.group(3)
        celdas = re.findall(r"<t[hd][^>]*>.*?</t[hd]>", cuerpo, flags=re.S | re.I)
        nuevas: list[str] = []
        for i, celda in enumerate(celdas):
            if re.search(r'\bclass="', celda, flags=re.I):
                celda = re.sub(r'class="', f'class="col{i} ', celda, count=1, flags=re.I)
            else:
                celda = re.sub(r"<t([hd])", rf'<t\1 class="col{i}"', celda, count=1, flags=re.I)
            nuevas.append(celda)
        return apertura + "".join(nuevas) + cierre

    return re.sub(r"(<tr[^>]*>)(.*?)(</tr>)", _anotar_fila, html, flags=re.S | re.I)


def _tabla_usa_layout_fluido(pareto_activo: bool, dims: dict[str, Any]) -> bool:
    """Tablas anchas (3+ métricas) usan 100% del contenedor para no recortar columnas."""
    if not pareto_activo:
        return True
    return int(dims.get("n_cols", 2)) >= 4 or bool(dims.get("tiene_dos_metricas"))


def _css_tabla_metricas(dims: dict[str, Any], fluido: bool = False) -> str:
    # Fluido: la tabla llena el ancho del contenedor (mismo ancho que el botón
    # «Guardar en Excel», que usa use_container_width) y las columnas conservan
    # su proporción actual mediante porcentajes. Fijo: anchos en px (modo Pareto).
    ancho_total_px = sum(dims["anchos_cols"])
    ancho_tabla_css = "100%" if fluido else f"{dims['ancho_tabla']}px"
    reglas = [
        ".lri-tabla-wrap table.lri-perfil-table {",
        f"table-layout: fixed !important;",
        f"width: {ancho_tabla_css} !important;",
        f"border-collapse: collapse !important;",
        "background-color: #131722 !important;",
        "}",
        ".lri-tabla-wrap table.lri-perfil-table th {",
        "background-color: #1e293b !important;",
        "font-weight: 600 !important;",
        "text-align: left !important;",
        f"padding: {dims['pad_v']}px {dims['pad_h']}px !important;",
        "line-height: 1.12 !important;",
        "}",
        ".lri-tabla-wrap table.lri-perfil-table td {",
        "border-bottom: 1px solid #2d3142 !important;",
        "text-align: center !important;",
        f"padding: {dims['pad_v']}px {dims['pad_h']}px !important;",
        "line-height: 1.12 !important;",
        "}",
    ]
    for i, w in enumerate(dims["anchos_cols"]):
        nth = i + 1
        sel_col = (
            f".lri-tabla-wrap table.lri-perfil-table .col{i}, "
            f".lri-tabla-wrap table.lri-perfil-table th:nth-child({nth}), "
            f".lri-tabla-wrap table.lri-perfil-table td:nth-child({nth})"
        )
        if fluido and ancho_total_px > 0:
            pct = round(w / ancho_total_px * 100, 4)
            regla_ancho = f"width: {pct}% !important;"
        else:
            regla_ancho = (
                f"width: {w}px !important; min-width: {w}px !important; max-width: {w}px !important;"
            )
        reglas.append(
            f"{sel_col} {{"
            f"{regla_ancho}"
            "overflow: hidden !important; text-overflow: ellipsis !important;"
            "}}"
        )
        if dims.get("col_producto_idx") == i:
            reglas.append(
                f"{sel_col} {{"
                "white-space: normal !important; word-break: break-word !important;"
                "}}"
            )
        elif dims.get("tiene_dos_metricas") and i >= max(1, dims["n_cols"] - 3):
            reglas.append(
                f".lri-tabla-wrap table.lri-perfil-table th.col{i}, "
                f".lri-tabla-wrap table.lri-perfil-table th:nth-child({nth}) {{"
                "white-space: normal !important; word-break: break-word !important;"
                "line-height: 1.15 !important; vertical-align: bottom !important;"
                "}}"
            )
            reglas.append(
                f".lri-tabla-wrap table.lri-perfil-table td.col{i}, "
                f".lri-tabla-wrap table.lri-perfil-table td:nth-child({nth}) {{"
                "text-align: center !important; font-weight: 600 !important; white-space: nowrap !important;"
                "}}"
            )
        elif i == dims["n_cols"] - 1:
            reglas.append(
                f".lri-tabla-wrap table.lri-perfil-table th.col{i}, "
                f".lri-tabla-wrap table.lri-perfil-table th:nth-child({nth}) {{"
                "white-space: normal !important; word-break: break-word !important;"
                "line-height: 1.15 !important;"
                "}}"
            )
            reglas.append(
                f".lri-tabla-wrap table.lri-perfil-table td.col{i}, "
                f".lri-tabla-wrap table.lri-perfil-table td:nth-child({nth}) {{"
                "text-align: center !important; font-weight: 600 !important; white-space: nowrap !important;"
                "}}"
            )
        else:
            reglas.append(
                f"{sel_col} {{"
                "white-space: nowrap !important;"
                "}}"
            )
    if not fluido:
        reglas.append(
            f".lri-tabla-wrap table.lri-perfil-table {{"
            f"min-width: {dims['ancho_tabla']}px !important;"
            "}}"
        )
    return "<style>" + "\n".join(reglas) + "</style>"


def _styler_tabla_metricas(
    df_mostrar: pd.DataFrame,
    fmt_cols: dict[str, str],
) -> Any:
    return df_mostrar.style.format(fmt_cols).hide(axis="index")


def _html_tabla_metricas_panel(
    styler: Any,
    clase_tabla: str,
    titulo_tabla: str,
    altura_scroll: int,
    dims: dict[str, Any],
    estilos_por_fila: Optional[list[str]] = None,
    estilos_por_celda: Optional[list[list[str]]] = None,
    fluido: bool = False,
) -> str:
    tabla_html = _extraer_tabla_html_pandas(
        styler.to_html(index=False, border=0, classes="lri-perfil-table")
    )
    tabla_html = _anotar_indices_columna_html(tabla_html)
    tabla_html = _aplicar_estilo_celdas_html(
        tabla_html,
        dims["fs_celda"],
        estilos_por_fila=estilos_por_fila,
        estilos_por_celda=estilos_por_celda,
    )
    ancho = dims["ancho_tabla"]
    css = _css_tabla_metricas(dims, fluido=fluido)
    # En modo fluido el panel ocupa el 100% del contenedor (igual que el botón
    # «Guardar en Excel»); en fijo conserva el ancho en px (modo Pareto).
    ancho_panel_css = "100%" if fluido else f"{ancho + 14}px"
    return dedent(
        f"""\
{css}
<div class="lri-tabla-wrap {clase_tabla}">
<div class="lri-tabla-col" style="padding:5px;border:1px solid #2d3142;border-radius:8px;background:#131722;width:{ancho_panel_css};box-sizing:border-box;">
<div class="lri-tabla-title" style="font-size:{_FS_TITULO_PANEL_TABLA}px;font-weight:600;color:#f8fafc;padding:0.4rem 0.55rem;border-bottom:1px solid #2d3142;background:#161b26;margin-bottom:6px;">{titulo_tabla}</div>
<div class="lri-html-table-scroll-container" style="height:{altura_scroll}px;min-height:{altura_scroll}px;max-height:{altura_scroll}px;overflow-y:auto;overflow-x:auto;-webkit-overflow-scrolling:touch;">
{tabla_html}
</div>
</div>
</div>
"""
    )


def _etiqueta_unidad_eje_x(eje_x: str) -> str:
    nx = _norm_texto(eje_x)
    if any(k in nx for k in ["descripcion", "articulo", "producto", "sku", "codigo", "material", "nombre"]):
        return "productos"
    if "subcategoria" in nx:
        return "subcategorías"
    if "categoria" in nx:
        return "categorías"
    if "proveedor" in nx:
        return "proveedores"
    if "cliente" in nx:
        return "clientes"
    return "ítems"


def _participacion_tramos_pareto(
    df_resumen: pd.DataFrame, eje_y: str, n1: int, n2: int, n3: int
) -> Tuple[float, float, float, float]:
    """% de contribución (peso Pareto) y total mostrado para el resumen ejecutivo."""
    ys = pd.to_numeric(df_resumen[eje_y], errors="coerce").fillna(0.0)
    if "porcentaje" in df_resumen.columns:
        pesos = pd.to_numeric(df_resumen["porcentaje"], errors="coerce").fillna(0.0)
        p1 = 100.0 * float(pesos.iloc[0:n1].sum())
        p2 = 100.0 * float(pesos.iloc[n1 : n1 + n2].sum())
        p3 = 100.0 * float(pesos.iloc[n1 + n2 :].sum())
        suma_pesos = float(pesos.sum())
        if suma_pesos > 0:
            total_mostrar = float((ys * pesos).sum() / suma_pesos)
        else:
            total_mostrar = float(ys.sum())
        return p1, p2, p3, total_mostrar
    total = float(ys.sum())
    if total == 0:
        return 0.0, 0.0, 0.0, 0.0
    s1 = float(ys.iloc[0:n1].sum())
    s2 = float(ys.iloc[n1 : n1 + n2].sum())
    s3 = float(ys.iloc[n1 + n2 :].sum())
    return 100.0 * s1 / total, 100.0 * s2 / total, 100.0 * s3 / total, total


def _bloque_tramo_pareto_html(
    color_txt: str,
    fondo: str,
    borde: str,
    etiqueta_tramo: str,
    pct_cupo: float,
    unidad: str,
    n_items: int,
    pct_part: float,
    es_abc: bool,
    etiqueta_banda: str,
    fs_tramo: int,
    fs_pct: int,
    fs_det: int,
) -> str:
    titulo = (
        f"{pct_cupo:.0f}% · Banda {etiqueta_banda} · cupo {unidad}"
        if es_abc
        else f"{pct_cupo:.0f}% cupo {unidad}"
    )
    return f"""
<div style="background:{fondo};border:1px solid {borde};border-radius:8px;
            padding:10px 12px;margin:8px 0;color:{color_txt};">
  <p style="margin:0 0 8px 0;font-size:{fs_tramo}px;font-weight:700;line-height:1.25;">
    {etiqueta_tramo} {titulo}
  </p>
  <p style="margin:0;font-size:{fs_pct}px;font-weight:800;color:#f8fafc;line-height:1.1;">
    {pct_part:.1f}%
  </p>
  <p style="margin:6px 0 0 0;font-size:{fs_det}px;color:#cbd5e1;">
    {n_items} {unidad} · participación del total Y
  </p>
</div>"""


def _mostrar_resumen_pareto_ejecutivo(
    df_resumen: pd.DataFrame,
    eje_x: str,
    eje_y: str,
    set_pareto: str,
    base_font_size: int,
    y_en_porcentaje: bool,
    y_escala_0_100: bool = False,
) -> None:
    """Resumen lateral Pareto: tipografía grande y bloques destacados (solo div/p; sin tablas HTML)."""
    try:
        fracciones = _resolver_fracciones_pareto_por_item(set_pareto)
        if fracciones is None or df_resumen.empty or eje_y not in df_resumen.columns:
            return
        f1, f2, f3 = fracciones
        n = len(df_resumen)
        n1, n2, n3 = _tamanos_segmentos_pareto(n, f1, f2, f3)
        unidad = _etiqueta_unidad_eje_x(eje_x)
        p1, p2, p3, total = _participacion_tramos_pareto(df_resumen, eje_y, n1, n2, n3)
        fmt_val = (
            (lambda x: _formatear_valor_porcentaje(x, y_escala_0_100))
            if y_en_porcentaje
            else (lambda x: f"{x:,.2f}" if abs(x) < 100 else f"{x:,.0f}")
        )

        fs_titulo = max(17, base_font_size + 5)
        fs_ref = max(16, base_font_size + 4)
        fs_sub = max(12, base_font_size)
        fs_tramo = max(14, base_font_size + 2)
        fs_pct = max(22, base_font_size + 8)
        fs_det = max(13, base_font_size + 1)
        fs_pie = max(11, base_font_size - 1)

        if total == 0 or np.isnan(total):
            st.markdown(
                f"<p style='font-size:{fs_sub}px;color:#94a3b8;'>Sin total en eje Y (suma 0).</p>",
                unsafe_allow_html=True,
            )
            return

        banda_a, banda_b, banda_c = _etiquetas_tramos_pareto(set_pareto)
        es_abc = "30% - 30% - 40%" in set_pareto
        tramos_cfg = [
            ("●", "#86efac", "rgba(34,197,94,0.18)", "#22c55e", banda_a, f1 * 100, n1, p1),
            ("●", "#fde047", "rgba(234,179,8,0.18)", "#eab308", banda_b, f2 * 100, n2, p2),
            ("●", "#fca5a5", "rgba(239,68,68,0.18)", "#ef4444", banda_c, f3 * 100, n3, p3),
        ]
        bloques = "".join(
            _bloque_tramo_pareto_html(
                color, fondo, borde, marca, pct_cupo, unidad, n_items, pct_part,
                es_abc, etiqueta, fs_tramo, fs_pct, fs_det,
            )
            for marca, color, fondo, borde, etiqueta, pct_cupo, n_items, pct_part in tramos_cfg
        )

        panel = f"""
<div class="lri-resumen-pareto" style="max-width:{_ANCHO_MAX_RESUMEN_PARETO}px;width:100%;margin:0 auto;">
<div style="border:2px solid #3b4258;border-radius:10px;background:linear-gradient(180deg,#1a2030 0%,#121826 100%);
            padding:12px 14px;box-shadow:0 4px 20px rgba(0,0,0,0.3);">
  <p style="margin:0 0 10px 0;font-size:{fs_titulo}px;font-weight:800;color:#f8fafc;
            letter-spacing:0.02em;border-bottom:2px solid #334155;padding-bottom:8px;">
    Resumen ejecutivo Pareto
  </p>
  <p style="margin:0 0 4px 0;font-size:{fs_sub}px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.06em;">
    Referencia eje Y
  </p>
  <p style="margin:0 0 10px 0;font-size:{fs_ref}px;font-weight:700;color:#e2e8f0;">
    {fmt_val(total)}
  </p>
  <p style="margin:0 0 12px 0;font-size:{fs_sub}px;color:#94a3b8;line-height:1.35;">
    % del valor total (misma base que colorea las barras)
  </p>
  {bloques}
  <p style="margin:10px 0 0 0;font-size:{fs_pie}px;color:#64748b;">
    Σ valor: {p1 + p2 + p3:.1f}% · {eje_y}
  </p>
</div>
</div>
"""
        st.markdown(panel, unsafe_allow_html=True)
    except Exception as exc:
        st.warning(f"No se pudo generar el resumen Pareto: {exc}")


def aplicar_logica_colores_pareto(
    df_agrup: pd.DataFrame,
    col_val: str,
    set_seleccionado: str,
    col_peso: Optional[str] = None,
    menor_es_mejor: Optional[bool] = None,
) -> pd.DataFrame:
    fracciones = _resolver_fracciones_pareto_por_item(set_seleccionado)
    if fracciones is None or df_agrup.empty:
        df_agrup["color_pareto"] = None
        return df_agrup

    if menor_es_mejor is None:
        menor_es_mejor = _metrica_pareto_menor_es_mejor(col_val)

    f1, f2, f3 = fracciones
    peso_col = col_peso if col_peso and col_peso in df_agrup.columns else col_val

    df_agrup = df_agrup.sort_values(
        by=col_val,
        ascending=bool(menor_es_mejor),
        na_position="last",
    ).reset_index(drop=True)
    n = len(df_agrup)
    n1, n2, n3 = _tamanos_segmentos_pareto(n, f1, f2, f3)

    suma_total = float(df_agrup[peso_col].sum())
    if suma_total == 0:
        df_agrup["color_pareto"] = COLOR_PARETO_COLA
        df_agrup["porcentaje"] = 0.0
        df_agrup["porcentaje_acumulado"] = 0.0
        return df_agrup

    df_agrup["porcentaje"] = df_agrup[peso_col] / suma_total
    df_agrup["porcentaje_acumulado"] = df_agrup["porcentaje"].cumsum()

    colores: list[str] = []
    for i in range(n):
        if i < n1:
            colores.append(COLOR_PARETO_TOP)
        elif i < n1 + n2:
            colores.append(COLOR_PARETO_MEDIO)
        else:
            colores.append(COLOR_PARETO_COLA)
    df_agrup["color_pareto"] = colores
    return df_agrup


def _mapa_colores_pareto_metrica(
    df_valores: pd.DataFrame,
    eje_x: str,
    eje_y: str,
    set_pareto: str,
    menor_es_mejor: Optional[bool] = None,
) -> dict[str, str]:
    """ABC por métrica: cada categoría recibe su banda según el ranking de esa columna."""
    if df_valores.empty or eje_x not in df_valores.columns or eje_y not in df_valores.columns:
        return {}
    if _resolver_fracciones_pareto_por_item(set_pareto) is None:
        return {}
    if menor_es_mejor is None:
        menor_es_mejor = _metrica_pareto_menor_es_mejor(eje_y)
    tmp = df_valores[[eje_x, eje_y]].copy()
    coloreado = aplicar_logica_colores_pareto(
        tmp, eje_y, set_pareto, menor_es_mejor=menor_es_mejor
    )
    return (
        coloreado.assign(_kx=coloreado[eje_x].astype(str))
        .set_index("_kx")["color_pareto"]
        .to_dict()
    )


def _estilo_texto_pareto_tabla(color: Optional[str], fs_celda: str) -> str:
    mapa = {
        COLOR_PARETO_TOP: f"color: {COLOR_PARETO_TOP}; font-weight: 600; {fs_celda}",
        COLOR_PARETO_MEDIO: f"color: {COLOR_PARETO_MEDIO}; font-weight: 600; {fs_celda}",
        COLOR_PARETO_COLA: f"color: {COLOR_PARETO_COLA}; font-weight: 600; {fs_celda}",
    }
    return mapa.get(color, fs_celda)


def _matriz_estilos_tabla_pareto_multimetrica(
    df_resumen: pd.DataFrame,
    eje_x: str,
    eje_y_principal: str,
    metricas_extras: list[dict[str, Any]],
    columnas_visibles: list[str],
    set_pareto: str,
    fs_celda: str,
) -> list[list[str]]:
    """Estilos por celda: dimensión neutra; cada métrica con su propio ABC."""
    cats = df_resumen[eje_x].astype(str).tolist()
    mapa_principal = (
        df_resumen.assign(_kx=df_resumen[eje_x].astype(str))
        .set_index("_kx")["color_pareto"]
        .to_dict()
    )
    mapas: dict[str, dict[str, Optional[str]]] = {eje_y_principal: mapa_principal}
    for m in metricas_extras:
        col = m["columna"]
        df_m = df_resumen[[eje_x]].copy()
        df_m[col] = m["valores"]
        mapas[col] = _mapa_colores_pareto_metrica(df_m, eje_x, col, set_pareto)

    cols_metricas = [eje_y_principal] + [m["columna"] for m in metricas_extras]
    indices = {
        col: columnas_visibles.index(col)
        for col in cols_metricas
        if col in columnas_visibles
    }

    estilo_dim = f"{fs_celda}color:#f8fafc;text-align:center;"
    matriz: list[list[str]] = []
    for cat in cats:
        fila = [estilo_dim] * len(columnas_visibles)
        for col in cols_metricas:
            idx = indices.get(col)
            if idx is None:
                continue
            color = mapas[col].get(cat)
            if color is None and col != eje_y_principal:
                color = COLOR_PARETO_COLA
            fila[idx] = _estilo_texto_pareto_tabla(color, fs_celda)
        matriz.append(fila)
    return matriz


def _matriz_estilos_tabla_pareto_dual(
    df_resumen: pd.DataFrame,
    eje_x: str,
    eje_y1: str,
    eje_y2: str,
    ys_y2: np.ndarray,
    columnas_visibles: list[str],
    set_pareto: str,
    fs_celda: str,
) -> list[list[str]]:
    """Compatibilidad: delega en la matriz multi-métrica."""
    return _matriz_estilos_tabla_pareto_multimetrica(
        df_resumen,
        eje_x,
        eje_y1,
        [{"columna": eje_y2, "valores": ys_y2}],
        columnas_visibles,
        set_pareto,
        fs_celda,
    )


MSG_PERFIL_NO_COMPUTABLE = "No es computable ese perfilado"


# Dimensiones del eje X que deben ser nombres (texto), no códigos numéricos en el Excel.
_ETIQUETA_DIMENSION_SOLO_TEXTO = {
    "pais": "nombre de país",
    "proveedor": "nombre de proveedor",
}


def _etiqueta_dimension_solo_texto(col: str) -> Optional[str]:
    return _ETIQUETA_DIMENSION_SOLO_TEXTO.get(_norm_texto(col))


def _serie_contiene_valores_numericos(serie: pd.Series) -> bool:
    """True si la mayoría de valores no vacíos son numéricos (no nombres descriptivos)."""
    if pd.api.types.is_numeric_dtype(serie):
        return True
    valores = serie.dropna()
    if valores.empty:
        return False
    texto = valores.astype(str).str.strip()
    texto = texto[texto != ""]
    if texto.empty:
        return False
    convertidos = pd.to_numeric(texto, errors="coerce")
    return float(convertidos.notna().sum()) / len(texto) >= 0.8


def _validar_dimension_como_texto(df: pd.DataFrame, col: str) -> Tuple[bool, Optional[str]]:
    etiqueta = _etiqueta_dimension_solo_texto(col)
    if not etiqueta or col not in df.columns:
        return True, None
    if _serie_contiene_valores_numericos(df[col]):
        return False, (
            f"«{col}» debe ser un {etiqueta} (texto), no un número. "
            "Corrija la columna en el archivo Excel y vuelva a cargar los datos."
        )
    return True, None


def _columna_es_atributo_dimension(df: pd.DataFrame, col: str) -> bool:
    """Dimensión descriptiva (texto/categoría), no métrica numérica para graficar en eje Y."""
    if col not in df.columns:
        return False
    return not pd.api.types.is_numeric_dtype(df[col])


def _evaluar_perfilado_computable(
    df: pd.DataFrame, eje_x: str, eje_y: str, operacion: str = "Suma"
) -> Tuple[bool, Optional[str]]:
    """
    Válido: dimensión (eje X) × métrica numérica (eje Y).
    No válido: misma columna o cruce atributo × atributo (categoría/subcategoría/código/etc.).
    """
    if eje_x not in df.columns or eje_y not in df.columns:
        partes: list[str] = []
        if eje_x is None:
            partes.append("eje X sin asignar")
        elif eje_x not in df.columns:
            partes.append(f"eje X «{eje_x}»")
        if eje_y is None:
            partes.append("eje Y sin columna numérica en esta hoja")
        elif eje_y not in df.columns:
            partes.append(f"eje Y «{eje_y}»")
        muestra = ", ".join(str(c) for c in list(df.columns)[:10])
        if len(df.columns) > 10:
            muestra += f" … (+{len(df.columns) - 10} más)"
        hoja = st.session_state.get("lri_excel_hoja_activa")
        prefijo_hoja = f"Hoja «{hoja}»: " if hoja else ""
        return False, (
            f"{prefijo_hoja}{' y '.join(partes)} no están en los datos cargados. "
            f"Revise la hoja del Excel o elija columnas en el panel lateral. "
            f"Columnas detectadas: {muestra or '(ninguna)'}."
        )
    if eje_x == eje_y:
        return False, "El eje X y el eje Y no pueden ser la misma columna."
    ok_texto, aviso_texto = _validar_dimension_como_texto(df, eje_x)
    if not ok_texto:
        return False, aviso_texto
    if _columna_es_atributo_dimension(df, eje_x) and _columna_es_atributo_dimension(df, eje_y):
        return False, (
            f"No se puede cruzar «{eje_x}» (atributo) con «{eje_y}» (atributo). "
            "Seleccione una métrica numérica en el eje Y (ventas, bultos, margen, etc.)."
        )
    if operacion in ("Suma", "Promedio") and not pd.api.types.is_numeric_dtype(df[eje_y]):
        return False, (
            f"«{eje_y}» no admite la operación «{operacion}». "
            "Elija una columna numérica en el eje Y."
        )
    return True, None


def procesar_agrupacion_perfil(df: pd.DataFrame, eje_x: str, eje_y: str, operacion: str, top_n: int, set_pareto: str) -> pd.DataFrame:
    computable, _ = _evaluar_perfilado_computable(df, eje_x, eje_y, operacion)
    if not computable:
        return "ERROR_NO_COMPUTABLE"
    df_filtrado = df.copy()

    if st.session_state["drill_down_categoria"] and "categoria" in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado["categoria"] == st.session_state["drill_down_categoria"]]

    dict_ops = {"Suma": "sum", "Promedio": "mean"}
    pareto_peso: Optional[str] = None

    vt = _columna_ventas_totales(df_filtrado)
    mb = _columna_margen_bruto(df_filtrado)
    mu = _columna_margen_utilidad_ratio(df_filtrado)

    if _metrica_margen_sobre_ventas(df_filtrado, eje_y) and vt is not None and vt in df_filtrado.columns:
        t = df_filtrado[[eje_x, eje_y, vt]].copy()
        if mb is not None and eje_y == mb:
            t["__num"] = t[eje_y]
        elif mu is not None and eje_y == mu:
            t["__num"] = t[eje_y] * t[vt]
        else:
            t["__num"] = np.nan
        t["__rr"] = np.where(t[vt].astype(float) != 0, t["__num"] / t[vt], np.nan)
        if operacion == "Suma":
            agg = t.groupby(eje_x, as_index=False).agg(snum=("__num", "sum"), svt=(vt, "sum"))
            agg[eje_y] = np.where(agg["svt"].astype(float) != 0, agg["snum"] / agg["svt"], np.nan)
            agg["__pareto_peso__"] = agg["svt"]
            df_agrup = agg[[eje_x, eje_y, "__pareto_peso__"]]
        else:
            agg = t.groupby(eje_x, as_index=False).agg(mr=("__rr", "mean"), svt=(vt, "sum"))
            agg[eje_y] = agg["mr"]
            agg["__pareto_peso__"] = agg["svt"]
            df_agrup = agg[[eje_x, eje_y, "__pareto_peso__"]]
        pareto_peso = "__pareto_peso__"
    elif _metrica_costo_mantener_pct(df_filtrado, eje_y) and vt is not None and vt in df_filtrado.columns:
        t = df_filtrado[[eje_x, eje_y, vt]].copy()
        df_agrup = t.groupby(eje_x, as_index=False).agg({eje_y: "mean", vt: "sum"})
        df_agrup = df_agrup.rename(columns={vt: "__pareto_peso__"})
        pareto_peso = "__pareto_peso__"
    elif _metrica_eje_y_en_porcentaje(df_filtrado, eje_y) and eje_y in df_filtrado.columns:
        t = df_filtrado[[eje_x, eje_y]].copy()
        if vt is not None and vt in df_filtrado.columns:
            t[vt] = df_filtrado[vt]
            df_agrup = t.groupby(eje_x, as_index=False).agg({eje_y: "mean", vt: "sum"})
            df_agrup = df_agrup.rename(columns={vt: "__pareto_peso__"})
            pareto_peso = "__pareto_peso__"
        else:
            df_agrup = t.groupby(eje_x, as_index=False).agg({eje_y: "mean"})
    else:
        df_agrup = df_filtrado.groupby(eje_x)[eje_y].agg(dict_ops[operacion]).reset_index()

    df_agrup = df_agrup.sort_values(
        by=eje_y,
        ascending=_metrica_pareto_menor_es_mejor(eje_y),
    )
    df_agrup[eje_x] = df_agrup[eje_x].astype(str)

    invertir = _metrica_pareto_menor_es_mejor(eje_y)
    if pareto_peso:
        df_agrup = aplicar_logica_colores_pareto(
            df_agrup, eje_y, set_pareto, col_peso=pareto_peso, menor_es_mejor=invertir
        )
        df_agrup = df_agrup.drop(columns=["__pareto_peso__"], errors="ignore")
    else:
        df_agrup = aplicar_logica_colores_pareto(
            df_agrup, eje_y, set_pareto, menor_es_mejor=invertir
        )

    if top_n > 0:
        return df_agrup.head(top_n)
    return df_agrup


# --- Exportación de resultados del perfilado (Capa 3) ---
_MAPA_ETIQUETA_BANDA_PARETO = {
    COLOR_PARETO_TOP: "Top (verde)",
    COLOR_PARETO_MEDIO: "Medio (amarillo)",
    COLOR_PARETO_COLA: "Cola (rojo)",
}


def _slug_nombre_archivo(texto: str, max_len: int = 32) -> str:
    s = unicodedata.normalize("NFD", str(texto))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.lower().strip().replace(" ", "_")
    s = re.sub(r"[^a-z0-9._-]+", "", s)
    return (s[:max_len] or "perfilado").strip("_.")


def _sanitizar_nombre_archivo(nombre: str) -> str:
    invalid = '<>:"/\\|?*'
    limpio = "".join(c if c not in invalid else "_" for c in nombre)
    return limpio[:200] if len(limpio) > 200 else limpio


def _nombre_archivo_perfilado(
    eje_x: str,
    eje_y: str,
    operacion: str,
    drill_categoria: Optional[str] = None,
) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    partes = [
        _slug_nombre_archivo(operacion, 12),
        _slug_nombre_archivo(eje_y, 28),
        "por",
        _slug_nombre_archivo(eje_x, 28),
    ]
    if drill_categoria:
        partes.append(_slug_nombre_archivo(drill_categoria, 20))
    base = "_".join(p for p in partes if p)
    return _sanitizar_nombre_archivo(f"LRI_perfilado_{base}_{ts}.xlsx")


def _preparar_df_exportacion_perfil(
    df_resumen: pd.DataFrame,
    df_origen: pd.DataFrame,
    eje_x: str,
    eje_y: str,
    operacion: str,
    pareto_activo: bool,
    metricas_extra: Optional[list[str]] = None,
) -> pd.DataFrame:
    """Misma información que la tabla en pantalla, lista para Excel."""
    df_tabla, _, _, _ = _preparar_tabla_metricas_detalle(
        df_resumen, df_origen, eje_x, eje_y, metricas_extra=metricas_extra
    )
    export = df_tabla.copy()
    if pareto_activo and "color_pareto" in df_resumen.columns:
        export["banda_pareto"] = (
            df_resumen["color_pareto"].map(_MAPA_ETIQUETA_BANDA_PARETO).fillna("")
        )
    if "porcentaje" in df_resumen.columns:
        export["pct_participacion"] = (
            pd.to_numeric(df_resumen["porcentaje"], errors="coerce") * 100.0
        ).round(2)
    export.insert(0, "operacion_metrica_principal", operacion)
    y_pct, y_escala = _info_presentacion_porcentaje_eje_y(df_origen, eje_y, export)
    if y_pct and eje_y in export.columns:
        vals = pd.to_numeric(export[eje_y], errors="coerce")
        export[eje_y] = vals.map(
            lambda x: _formatear_valor_porcentaje(float(x), y_escala) if pd.notna(x) else ""
        )
    for col in metricas_extra or []:
        if col not in export.columns:
            continue
        col_pct, col_escala = _info_presentacion_porcentaje_eje_y(df_origen, col, export)
        if col_pct:
            vals_col = pd.to_numeric(export[col], errors="coerce")
            export[col] = vals_col.map(
                lambda x, esc=col_escala: _formatear_valor_porcentaje(float(x), esc)
                if pd.notna(x)
                else ""
            )
    return export


def _meta_exportacion_perfil(
    eje_x: str,
    eje_y: str,
    operacion: str,
    set_pareto: str,
    drill_categoria: Optional[str],
    n_filas: int,
    metricas_extra: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    meta = {
        "fecha_exportacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "eje_x": eje_x,
        "eje_y": eje_y,
        "operacion_metrica_principal": operacion,
        "pareto": set_pareto,
        "drill_down_categoria": drill_categoria or "Ver todas",
        "filas_exportadas": n_filas,
    }
    for i, m in enumerate(metricas_extra or [], start=2):
        meta[f"metrica_adicional_{i}"] = m["columna"]
        meta[f"operacion_metrica_adicional_{i}"] = m["operacion"]
    return meta


def _bytes_excel_perfilado(df_datos: pd.DataFrame, meta: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_datos.to_excel(writer, sheet_name="Perfilado", index=False)
        df_meta = pd.DataFrame({"Campo": list(meta.keys()), "Valor": list(meta.values())})
        df_meta.to_excel(writer, sheet_name="Info", index=False)
    return buffer.getvalue()


# ==============================================================================
# CAPA 4: CAPA DE PRESENTACIÓN (INTERFAZ DE USUARIO STREAMLIT)
# ==============================================================================
def altura_grafico_adaptativa(n: int, viewport_h: int) -> int:
    usable = max(520, viewport_h - RESERVA_VERTICAL_REF)
    if n <= 0: 
        return max(360, min(usable, int(viewport_h * 0.42)))
    px_por_barra = max(6.5, min(20.0, 620.0 / max(n, 6)))
    necesario = int(210 + n * px_por_barra * 1.9)
    relleno = int(usable * (0.88 if n <= 60 else 0.76))
    return int(max(480, min(usable, max(necesario, relleno))))


# A partir de cuántas columnas se giran las etiquetas de valor a 90° (vertical).
# Con pocas barras se dejan horizontales (0°) y con su tamaño original; con muchas
# barras se giran para que no se peguen entre sí.
UMBRAL_GIRO_ETIQUETAS_BARRA = 30


def _fs_etiquetas_valor_barras(
    base_font_size: int,
    *,
    multimetrica: bool = False,
    etiqueta_font_size: Optional[int] = None,
) -> int:
    """Tamaño del valor sobre cada barra; control independiente vía slider de interfaz."""
    if etiqueta_font_size is not None and etiqueta_font_size > 0:
        return max(8, min(28, int(etiqueta_font_size)))
    fs = max(13, base_font_size + 5)
    if multimetrica:
        return max(12, min(fs, 15))
    return fs


def _textfont_etiqueta_barras(fs: int, color: str) -> dict[str, Any]:
    """Fuente uniforme para etiquetas de valor (todas las series del gráfico)."""
    return dict(size=fs, color=color, family="Arial, sans-serif")


def _texttemplates_valores_barras(
    series: list[tuple[np.ndarray, bool]],
) -> list[str]:
    """Plantillas de texto; formato numérico compartido entre métricas no-% del mismo gráfico."""
    arrays_num = [ys for ys, es_pct in series if not es_pct and len(ys) > 0]
    mx_global = 0.0
    if arrays_num:
        mx_global = max(float(np.nanmax(np.abs(a))) for a in arrays_num)
    fmt_num = "%{text:,.2f}" if mx_global < 100 else "%{text:,.0f}"
    return ["%{text:.2%}" if es_pct else fmt_num for _, es_pct in series]


def _texttemplate_valores_barras(ys: np.ndarray, es_pct: bool) -> str:
    if es_pct:
        return "%{text:.2%}"
    mx = float(np.nanmax(np.abs(ys))) if len(ys) else 0.0
    return "%{text:,.2f}" if mx < 100 else "%{text:,.0f}"


def _angulo_etiquetas_valor_barras(n_barras: int) -> int:
    """0° (horizontal) con pocas barras; -90° (vertical) cuando hay muchas."""
    return -90 if n_barras > UMBRAL_GIRO_ETIQUETAS_BARRA else 0


def _tipo_dimension_catalogo(eje_x: str) -> str:
    """Clasifica el eje X para ajustar scroll: categoría, subcategoría, código o descripción."""
    nx = _norm_texto(eje_x)
    if "subcategoria" in nx:
        return "subcategoria"
    if "categoria" in nx:
        return "categoria"
    if _eje_x_es_codigo_producto(eje_x):
        return "codigo"
    if any(k in nx for k in ["descripcion", "articulo", "producto", "sku", "material", "nombre", "item"]):
        return "descripcion"
    return "otro"


def _eje_x_es_codigo_o_descripcion(eje_x: str) -> bool:
    """Solo código o descripción/producto admiten gráfico extendido manual."""
    return _tipo_dimension_catalogo(eje_x) in ("codigo", "descripcion")


def _umbral_scroll_dimension(tipo: str) -> int:
    """Cuántas barras activan scroll según tipo de dimensión (visualización extendida)."""
    return {
        "categoria": 15,
        "subcategoria": 20,
        "codigo": 35,
        "descripcion": 35,
    }.get(tipo, 8)


def _px_por_barra_dimension(
    n: int, *, dual: bool, eje_x: str, max_label_len: int
) -> int:
    """Ancho por barra según cantidad y longitud de etiquetas (códigos/descripciones)."""
    if n <= 8:
        px = 88 if not dual else 104
    elif n <= 20:
        px = 68 if not dual else 82
    elif n <= 50:
        px = 54 if not dual else 66
    else:
        px = 58 if not dual else 70
    tipo = _tipo_dimension_catalogo(eje_x)
    if tipo == "descripcion":
        px = max(px, min(130, 52 + int(max_label_len * 1.6)))
    elif tipo == "codigo":
        px = max(px, min(100, 44 + int(max_label_len * 0.85)))
    elif tipo == "subcategoria":
        px = max(px, min(92, 40 + int(max_label_len * 0.65)))
    elif tipo == "categoria":
        px = max(px, min(86, 38 + int(max_label_len * 0.5)))
    return px


def _ancho_figura_barras(
    n: int,
    *,
    dual: bool = False,
    eje_x: str = "",
    max_label_len: int = 0,
) -> int:
    """Ancho total del gráfico extendido con scroll horizontal."""
    px = _px_por_barra_dimension(n, dual=dual, eje_x=eje_x, max_label_len=max_label_len)
    return max(960, int(n * px + 160))


def _bargap_por_n(n: int, *, dual: bool = False) -> tuple[float, float]:
    """Menor separación = barras más gruesas (bargap alto = barras delgadas)."""
    if dual:
        if n > 40:
            return 0.28, 0.08
        if n > 15:
            return 0.22, 0.06
        return 0.18, 0.10
    if n > 50:
        return 0.12, 0.0
    if n > 15:
        return 0.16, 0.0
    return 0.10, 0.0


def _angulo_etiquetas_x_grafico(n: int, eje_x: str = "", max_label_len: int = 0) -> int:
    tipo = _tipo_dimension_catalogo(eje_x)
    if tipo in ("descripcion", "codigo") and (n > 8 or max_label_len > 14):
        return -90 if n > 18 or max_label_len > 28 else -45
    if n > 35:
        return -90
    if n > 12:
        return -45
    return 0


def _altura_grafico_scroll_horizontal(n: int, viewport_h: int) -> int:
    """Altura estable cuando el ancho crece con scroll horizontal."""
    usable = max(520, viewport_h - RESERVA_VERTICAL_REF)
    if n <= 12:
        return int(max(440, min(usable, 560)))
    return int(max(520, min(920, usable * 0.88)))


def _margen_inferior_grafico(n: int, eje_x: str = "", max_label_len: int = 0) -> int:
    ang = _angulo_etiquetas_x_grafico(n, eje_x, max_label_len)
    extra = min(80, max(0, max_label_len - 12) * 2)
    if ang == -90:
        return 140 + extra
    if ang == -45:
        return 110 + extra // 2
    return 72 + extra // 3


def _ver_grafico_completo_en_pantalla(eje_x: str) -> bool:
    """True si el usuario pidió ver todo el gráfico en pantalla (sin scroll)."""
    if not _eje_x_es_codigo_o_descripcion(eje_x):
        return False
    return bool(st.session_state.get("lri_grafico_scroll_completo", False))


def _scroll_grafico_activo(
    n: int, eje_x: str = "", *, ver_completo_pantalla: bool = False
) -> bool:
    """¿Usar gráfico extendido con scroll horizontal? False = todo visible en pantalla."""
    if n < 2:
        return False
    tipo = _tipo_dimension_catalogo(eje_x)
    if tipo in ("codigo", "descripcion"):
        if ver_completo_pantalla:
            return False
        return n > _umbral_scroll_dimension(tipo)
    if tipo == "otro":
        return n > 8
    return n > _umbral_scroll_dimension(tipo)


def _usar_scroll_horizontal_grafico(
    n: int, eje_x: str = "", max_label_len: int = 0, *, ver_completo_pantalla: bool = False
) -> bool:
    """Compatibilidad: delega en _scroll_grafico_activo."""
    return _scroll_grafico_activo(n, eje_x, ver_completo_pantalla=ver_completo_pantalla)


def _mostrar_grafico_barras(
    fig: go.Figure,
    n_barras: int,
    *,
    dual: bool = False,
    eje_x: str = "",
    max_label_len: int = 0,
    ver_completo_pantalla: bool = False,
) -> None:
    """Render: scroll extendido o gráfico completo ajustado al ancho visible."""
    scroll_activo = _scroll_grafico_activo(
        n_barras, eje_x, ver_completo_pantalla=ver_completo_pantalla
    )
    if not scroll_activo:
        fig.update_layout(autosize=True, width=None)
        st.plotly_chart(fig, use_container_width=True)
        return

    ancho = _ancho_figura_barras(
        n_barras,
        dual=dual,
        eje_x=eje_x,
        max_label_len=max_label_len,
    )
    altura = int(fig.layout.height or _altura_grafico_scroll_horizontal(n_barras, REF_VIEWPORT_H))
    fig.update_layout(width=ancho, height=altura, autosize=False)

    plot_html = fig.to_html(
        full_html=False,
        include_plotlyjs="cdn",
        config={"displayModeBar": True, "responsive": False, "scrollZoom": False},
    )
    wrapped = f"""
    <div class="lri-grafico-scroll-h" style="
        overflow-x:auto;overflow-y:hidden;width:100%;max-width:100%;
        border:1px solid #1e3a5f;border-radius:8px;padding:8px 4px;
        -webkit-overflow-scrolling:touch;background:#0f1419;">
      <div style="width:{ancho}px;min-width:{ancho}px;height:{altura}px;">
        {plot_html}
      </div>
    </div>
    <style>
      .lri-grafico-scroll-h .plotly-graph-div,
      .lri-grafico-scroll-h .js-plotly-plot {{
        width: {ancho}px !important;
        min-width: {ancho}px !important;
        max-width: none !important;
      }}
    </style>
    """
    components.html(wrapped, height=altura + 52, scrolling=False)
    unidad = _etiqueta_unidad_eje_x(eje_x) if eje_x else "ítems"
    st.caption(
        f"Gráfico extendido ({n_barras} {unidad}, {ancho:,} px) — "
        "use la barra horizontal debajo del gráfico (← →) para recorrer las barras."
    )


def _metrica_adicional_activa(valor: Optional[str]) -> bool:
    return valor not in (None, "", METRICA_ADICIONAL_NINGUNA)


def _opciones_metrica_adicional(
    df: pd.DataFrame, excluir: Optional[Iterable[str]] = None
) -> list[str]:
    cols = _columnas_numericas_usables(df)
    bloqueados = {
        c
        for c in (excluir or [])
        if c and c not in (None, METRICA_ADICIONAL_NINGUNA)
    }
    return [METRICA_ADICIONAL_NINGUNA] + [c for c in cols if c not in bloqueados]


def _intentar_resolver_metrica_adicional(
    df: pd.DataFrame,
    eje_x: str,
    col: str,
    operacion: str,
    top_n: int,
    set_pareto: str,
    df_resumen_base: pd.DataFrame,
    eje_y_principal: str,
    ys_principal: np.ndarray,
    y_pct_principal: bool,
    excluir: set[str],
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Resuelve una métrica adicional con su propio Suma/Promedio."""
    if not _metrica_adicional_activa(col):
        return None, None
    if col in excluir:
        return None, f"«{col}» ya está seleccionada en otra métrica del eje Y."
    computable, aviso = _evaluar_perfilado_computable(df, eje_x, col, operacion)
    if not computable:
        return None, aviso or f"«{col}» no es válida como métrica adicional."
    df_resumen_m = procesar_agrupacion_perfil(df, eje_x, col, operacion, top_n, set_pareto)
    if isinstance(df_resumen_m, str):
        return None, f"«{col}» no admite «{operacion}»."
    ys = _alinear_serie_metrica_secundaria(df_resumen_base, df_resumen_m, eje_x, col)
    y_pct, y_escala = _info_presentacion_porcentaje_eje_y(df, col, df_resumen_m)
    y_tasa = _metrica_costo_mantener_pct(df, col)
    en_eje_sec = _comparativo_usa_doble_eje_y(y_pct_principal, y_pct, ys_principal, ys)
    return {
        "columna": col,
        "operacion": operacion,
        "valores": ys,
        "y_pct": y_pct,
        "y_escala_0_100": y_escala,
        "y_tasa_mant": y_tasa,
        "en_eje_secundario": en_eje_sec,
    }, None


def _alinear_serie_metrica_secundaria(
    df_primario: pd.DataFrame,
    df_secundario: pd.DataFrame,
    eje_x: str,
    col_sec: str,
) -> np.ndarray:
    orden = df_primario[eje_x].astype(str).tolist()
    idx = df_secundario.set_index(df_secundario[eje_x].astype(str))
    return idx.reindex(orden)[col_sec].astype(float).to_numpy()


def _serie_parece_fraccion_o_porcentaje(ys: np.ndarray) -> bool:
    """Valores típicamente entre 0 y 1 (o poco por encima) frente a montos grandes."""
    if len(ys) == 0:
        return False
    v = np.abs(ys.astype(float))
    v = v[np.isfinite(v)]
    if len(v) == 0:
        return False
    mx = float(np.max(v))
    med = float(np.median(v))
    return mx <= 2.0 and med <= 1.0


def _comparativo_usa_doble_eje_y(
    y1_pct: bool,
    y2_pct: bool,
    ys1: np.ndarray,
    ys2: np.ndarray,
    umbral_ratio: float = 20.0,
) -> bool:
    """
    Dos ejes Y: % vs colones/unidades, o mismas unidades con magnitudes muy distintas.
    """
    if y1_pct != y2_pct:
        return True
    p1 = y1_pct or _serie_parece_fraccion_o_porcentaje(ys1)
    p2 = y2_pct or _serie_parece_fraccion_o_porcentaje(ys2)
    if p1 != p2:
        return True
    m1 = float(np.nanmax(np.abs(ys1))) if len(ys1) else 0.0
    m2 = float(np.nanmax(np.abs(ys2))) if len(ys2) else 0.0
    if m1 <= 0 or m2 <= 0:
        return False
    return max(m1, m2) / min(m1, m2) > umbral_ratio


def _layout_eje_y_metrica(
    nombre_columna: str,
    es_pct: bool,
    escala_0_100: bool,
    es_tasa_mant: bool,
    operacion: str,
    color: str,
    base_font_size: int,
) -> dict[str, Any]:
    if es_pct:
        suf = "tasa %" if es_tasa_mant else "%"
        titulo = f"{nombre_columna} ({suf})"
        kw: dict[str, Any] = dict(
            title=dict(text=titulo, font=dict(size=base_font_size + 2, color=color)),
            tickfont=dict(size=base_font_size, color=color),
            tickformat=".1%",
        )
        if escala_0_100:
            kw["ticksuffix"] = "%"
        return kw
    titulo = nombre_columna if operacion == "Suma" else f"{nombre_columna} ({operacion})"
    return dict(
        title=dict(text=titulo, font=dict(size=base_font_size + 2, color=color)),
        tickfont=dict(size=base_font_size, color=color),
    )


def _etiqueta_metrica_grafico(
    columna: str, operacion: str, es_pct: bool, es_tasa_mant: bool
) -> str:
    suf = ""
    if es_pct:
        suf = " (tasa %)" if es_tasa_mant else " (% sobre ventas)"
    op_txt = "" if operacion == "Suma" else f" · {operacion}"
    return f"{columna}{suf}{op_txt}"


def fig_ranking_barras(
    df_resumen: pd.DataFrame,
    col_cat: str,
    col_val: str,
    operacion: str,
    viewport_h: int,
    base_font_size: int,
    y_en_porcentaje: bool = False,
    y_es_tasa_mantenimiento: bool = False,
    y_escala_0_100: bool = False,
    mostrar_acumulado: bool = False,
    ancho_fig_px: Optional[int] = None,
    metricas_extras: Optional[list[dict[str, Any]]] = None,
    ver_completo_pantalla: bool = False,
    etiqueta_barras_font_size: Optional[int] = None,
) -> go.Figure:
    n = len(df_resumen)
    chart_col_px = max(260, int((REF_VIEWPORT_W - 96) * 0.66))
    extras = [m for m in (metricas_extras or []) if m.get("valores") is not None]
    multimetrica = len(extras) > 0

    if n == 0:
        fig = go.Figure()
        fig.update_layout(height=400, width=chart_col_px, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0f1419")
        return fig

    ys = df_resumen[col_val].astype(float).to_numpy()
    colores_barras = df_resumen["color_pareto"].tolist()

    if multimetrica:
        marker_config = dict(color=_COLORES_BARRAS_MULTIMETRICA[0], cornerradius=6)
        titulo_adicional = ""
        pareto_activo = False
    elif colores_barras[0] is None:
        marker_config = dict(
            color=ys,
            colorscale=[
                [0.0, "#ffffff"], [0.18, "#e8f4fc"], [0.38, "#90caf9"],
                [0.62, "#2196f3"], [0.82, "#1565c0"], [1.0, "#0d47a1"]
            ],
            cornerradius=6,
        )
        titulo_adicional = ""
        pareto_activo = False
    else:
        marker_config = dict(color=colores_barras, cornerradius=6)
        titulo_adicional = " (Segmentación Pareto ABC"
        if mostrar_acumulado:
            titulo_adicional += " · curva acumulada"
        titulo_adicional += ")"
        pareto_activo = True

    if multimetrica:
        partes = [_etiqueta_metrica_grafico(col_val, operacion, y_en_porcentaje, y_es_tasa_mantenimiento)]
        for m in extras:
            partes.append(
                _etiqueta_metrica_grafico(
                    m["columna"], m["operacion"], m["y_pct"], m["y_tasa_mant"]
                )
            )
        titulo_grafico = f"Comparativo: {' · '.join(partes)} por {col_cat}{titulo_adicional}"
    else:
        sufijo_pct = ""
        if y_en_porcentaje:
            sufijo_pct = " (tasa %)" if y_es_tasa_mantenimiento else " (% sobre ventas)"
        titulo_grafico = f"Análisis de {operacion}: {col_val}{sufijo_pct} por {col_cat}{titulo_adicional}"
    if st.session_state["drill_down_categoria"]:
        titulo_grafico += f" (Filtrado por: {st.session_state['drill_down_categoria']})"

    texttemplate = _texttemplate_valores_barras(ys, y_en_porcentaje)
    if multimetrica:
        series_texto = [(ys, y_en_porcentaje)]
        for m in extras:
            series_texto.append((m["valores"], m["y_pct"]))
        templates = _texttemplates_valores_barras(series_texto)
        texttemplate = templates[0]
    if y_en_porcentaje:
        yaxis_title = "%"
        yaxis_tickformat = ".1%"
    else:
        yaxis_title = operacion
        yaxis_tickformat = None

    yaxis_kw = dict(
        tickfont=dict(size=base_font_size, color="#e2e8f0"),
        title=dict(text=yaxis_title, font=dict(size=base_font_size + 2, color="#ffffff")),
    )
    if yaxis_tickformat is not None:
        yaxis_kw["tickformat"] = yaxis_tickformat
    if y_en_porcentaje and y_escala_0_100:
        yaxis_kw["ticksuffix"] = "%"

    fs_etiqueta_barra = _fs_etiquetas_valor_barras(
        base_font_size,
        multimetrica=multimetrica,
        etiqueta_font_size=etiqueta_barras_font_size,
    )
    angulo_etiqueta_barra = _angulo_etiquetas_valor_barras(n)

    xs_cat = df_resumen[col_cat].astype(str)
    max_label_len = int(xs_cat.str.len().max()) if len(xs_cat) else 0
    scroll_h = _scroll_grafico_activo(n, col_cat, ver_completo_pantalla=ver_completo_pantalla)
    bargap, bargroupgap = _bargap_por_n(n, dual=multimetrica)
    angulo_x = _angulo_etiquetas_x_grafico(n, col_cat, max_label_len)
    margen_b = _margen_inferior_grafico(n, col_cat, max_label_len)

    barra1_kw: dict[str, Any] = dict(
        x=xs_cat,
        y=ys,
        text=ys,
        texttemplate=texttemplate,
        textposition="outside",
        textangle=angulo_etiqueta_barra,
        textfont=_textfont_etiqueta_barras(fs_etiqueta_barra, _TEXTOS_BARRAS_MULTIMETRICA[0]),
        cliponaxis=False,
        marker=marker_config,
        name=_etiqueta_metrica_grafico(col_val, operacion, y_en_porcentaje, y_es_tasa_mantenimiento),
    )
    if multimetrica:
        barra1_kw["yaxis"] = "y"
        barra1_kw["offsetgroup"] = 1
    fig = go.Figure(go.Bar(**barra1_kw))

    usa_eje_secundario = False
    metrica_eje_sec: Optional[dict[str, Any]] = None
    for i, m in enumerate(extras, start=2):
        ys_m = m["valores"]
        color = _COLORES_BARRAS_MULTIMETRICA[min(i - 1, len(_COLORES_BARRAS_MULTIMETRICA) - 1)]
        txt_color = _TEXTOS_BARRAS_MULTIMETRICA[min(i - 1, len(_TEXTOS_BARRAS_MULTIMETRICA) - 1)]
        tmpl_m = templates[i - 1] if multimetrica else _texttemplate_valores_barras(ys_m, m["y_pct"])
        en_sec = bool(m.get("en_eje_secundario"))
        if en_sec:
            usa_eje_secundario = True
            if metrica_eje_sec is None:
                metrica_eje_sec = m
        fig.add_trace(
            go.Bar(
                x=xs_cat,
                y=ys_m,
                text=ys_m,
                texttemplate=tmpl_m,
                textposition="outside",
                textangle=angulo_etiqueta_barra,
                textfont=_textfont_etiqueta_barras(fs_etiqueta_barra, txt_color),
                cliponaxis=False,
                marker=dict(color=color, cornerradius=6),
                name=_etiqueta_metrica_grafico(
                    m["columna"], m["operacion"], m["y_pct"], m["y_tasa_mant"]
                ),
                offsetgroup=i,
                yaxis="y2" if en_sec else "y",
            )
        )

    if multimetrica and usa_eje_secundario:
        yaxis_kw = _layout_eje_y_metrica(
            col_val,
            y_en_porcentaje,
            y_escala_0_100,
            y_es_tasa_mantenimiento,
            operacion,
            COLOR_BARRA_COMPARATIVO_1,
            base_font_size,
        )

    layout_kw: dict[str, Any] = dict(
        title=dict(text=titulo_grafico, font=dict(size=base_font_size + 4, color="#ffffff")),
        height=(
            _altura_grafico_scroll_horizontal(n, viewport_h)
            if scroll_h
            else max(400, altura_grafico_adaptativa(n, viewport_h))
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0f1419",
        showlegend=multimetrica,
        barmode="group" if multimetrica else "relative",
        bargap=bargap,
        bargroupgap=bargroupgap,
        uniformtext=dict(minsize=fs_etiqueta_barra, mode="show"),
        margin=dict(l=52, r=28, t=max(76, 52 + fs_etiqueta_barra), b=margen_b),
        xaxis=dict(
            type="category",
            tickangle=angulo_x,
            tickfont=dict(size=base_font_size, color="#e2e8f0"),
            title=dict(text=col_cat, font=dict(size=base_font_size + 2, color="#ffffff")),
            categoryorder="array",
            categoryarray=xs_cat.tolist(),
        ),
        yaxis=yaxis_kw,
    )
    if multimetrica:
        layout_kw["legend"] = dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(color="#e2e8f0", size=base_font_size - 1),
            bgcolor="rgba(0,0,0,0)",
        )
        if usa_eje_secundario and metrica_eje_sec is not None:
            layout_kw["yaxis2"] = _layout_eje_y_metrica(
                metrica_eje_sec["columna"],
                metrica_eje_sec["y_pct"],
                metrica_eje_sec["y_escala_0_100"],
                metrica_eje_sec["y_tasa_mant"],
                metrica_eje_sec["operacion"],
                COLOR_BARRA_COMPARATIVO_2,
                base_font_size,
            )
            layout_kw["yaxis2"]["overlaying"] = "y"
            layout_kw["yaxis2"]["side"] = "right"
            layout_kw["yaxis2"]["showgrid"] = False
            layout_kw["margin"]["r"] = max(layout_kw["margin"]["r"], 88)
    ancho_scroll = _ancho_figura_barras(
        n,
        dual=multimetrica,
        eje_x=col_cat,
        max_label_len=max_label_len,
    )
    if scroll_h:
        layout_kw["width"] = ancho_scroll
        layout_kw["autosize"] = False
    elif ancho_fig_px is not None:
        layout_kw["width"] = ancho_fig_px
    elif ver_completo_pantalla:
        layout_kw["autosize"] = True
    elif not pareto_activo:
        layout_kw["width"] = chart_col_px

    if pareto_activo and mostrar_acumulado and not multimetrica:
        total_y = float(np.nansum(ys))
        if total_y > 0:
            cum_pct = np.cumsum(ys) / total_y
            xs = df_resumen[col_cat].astype(str)
            fig.add_trace(
                go.Scatter(
                    x=xs,
                    y=cum_pct,
                    name="% acumulado",
                    mode="lines+markers",
                    line=dict(color="#38bdf8", width=2.5),
                    marker=dict(size=7, color="#38bdf8", line=dict(width=1, color="#0f172a")),
                    yaxis="y2",
                    hovertemplate="%{x}<br>Acumulado: %{y:.1%}<extra></extra>",
                )
            )
            layout_kw["showlegend"] = True
            layout_kw["legend"] = dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                font=dict(color="#e2e8f0", size=base_font_size - 1),
                bgcolor="rgba(0,0,0,0)",
            )
            layout_kw["yaxis2"] = dict(
                title=dict(text="% acumulado", font=dict(size=base_font_size + 2, color="#38bdf8")),
                tickfont=dict(size=base_font_size, color="#38bdf8"),
                overlaying="y",
                side="right",
                tickformat=".0%",
                showgrid=False,
            )

    fig.update_layout(**layout_kw)
    return fig


def _mostrar_error_perfil_no_computable(aviso: Optional[str] = None) -> None:
    if aviso:
        st.warning(aviso)
    _, col_grafico = st.columns([1, 2])
    with col_grafico:
        st.error(MSG_PERFIL_NO_COMPUTABLE)


def render_perfilado_manual_panel(
    df: pd.DataFrame,
    viewport_h_ui: int,
    base_font_size: int,
    tabla_font_size: int,
    etiqueta_barras_font_size: int,
) -> None:
    eje_x_real = st.session_state["lri_man_eje_x"]
    eje_y_real = st.session_state["lri_man_eje_y"]
    eje_y2_real = st.session_state.get("lri_man_eje_y2", METRICA_ADICIONAL_NINGUNA)
    eje_y3_real = st.session_state.get("lri_man_eje_y3", METRICA_ADICIONAL_NINGUNA)
    operacion_y = st.session_state.get("lri_man_operacion_y", "Suma")
    operacion_y2 = st.session_state.get("lri_man_operacion_y2", "Suma")
    operacion_y3 = st.session_state.get("lri_man_operacion_y3", "Suma")
    top_n_real = st.session_state["lri_man_top_n"]
    set_pareto_real = st.session_state["lri_pareto_set"]
    ver_completo_graf = _ver_grafico_completo_en_pantalla(eje_x_real or "")

    if st.session_state["drill_down_categoria"]:
        if st.button("⬅️ Volver a vista general (Categorías)"):
            st.session_state["drill_down_categoria"] = None
            if "categoria" in df.columns:
                st.session_state["_lri_pending_man_eje_x"] = "categoria"
            st.rerun()

    computable, aviso_perfil = _evaluar_perfilado_computable(
        df, eje_x_real, eje_y_real, operacion_y
    )
    if not computable:
        _mostrar_error_perfil_no_computable(aviso_perfil)
        return

    df_filtrado_base = df.copy()
    if st.session_state["drill_down_categoria"] and "categoria" in df_filtrado_base.columns:
        df_filtrado_base = df_filtrado_base[df_filtrado_base["categoria"] == st.session_state["drill_down_categoria"]]

    df_resumen = procesar_agrupacion_perfil(df, eje_x_real, eje_y_real, operacion_y, top_n_real, set_pareto_real)

    if isinstance(df_resumen, str) and df_resumen == "ERROR_NO_COMPUTABLE":
        _mostrar_error_perfil_no_computable(
            f"«{eje_y_real}» no admite la operación «{operacion_y}» en este perfilado."
        )
        return

    y_pct, y_escala_0_100 = _info_presentacion_porcentaje_eje_y(df, eje_y_real, df_resumen)
    y_tasa_mant = _metrica_costo_mantener_pct(df, eje_y_real)
    ys_principal = df_resumen[eje_y_real].astype(float).to_numpy()

    metricas_extras: list[dict[str, Any]] = []
    avisos_extra: list[str] = []
    seleccionadas = {eje_y_real}
    for col, op in (
        (eje_y2_real, operacion_y2),
        (eje_y3_real, operacion_y3),
    ):
        resuelta, aviso = _intentar_resolver_metrica_adicional(
            df,
            eje_x_real,
            col,
            op,
            top_n_real,
            set_pareto_real,
            df_resumen,
            eje_y_real,
            ys_principal,
            y_pct,
            seleccionadas,
        )
        if aviso:
            avisos_extra.append(aviso)
        if resuelta:
            metricas_extras.append(resuelta)
            seleccionadas.add(resuelta["columna"])

    for aviso in avisos_extra:
        st.caption(f"⚠️ Métrica adicional: {aviso}")

    if metricas_extras:
        escala_dual = [m for m in metricas_extras if m.get("en_eje_secundario")]
        if escala_dual:
            nombres_sec = ", ".join(f"**{m['columna']}** ({m['operacion']})" for m in escala_dual)
            st.caption(
                f"📐 Escala dual: eje izquierdo = **{eje_y_real}** ({operacion_y}) · "
                f"eje derecho = {nombres_sec}"
            )

    label_metrica, val_total_formateado = calcular_metricas_encabezado(
        df_filtrado_base, eje_y_real, operacion_y
    )
    cats_count = df_filtrado_base[eje_x_real].nunique() if eje_x_real in df_filtrado_base.columns else 0
    y_max, y_min = _extremos_eje_y_perfilado(df_resumen, eje_y_real)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-title'>{label_metrica}</div>"
            f"<div class='kpi-value'>{val_total_formateado}</div></div>",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-title'>Elementos Únicos ({eje_x_real})</div>"
            f"<div class='kpi-value'>{cats_count}</div></div>",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-title'>Máximo {eje_y_real}</div>"
            f"<div class='kpi-value'>{_formatear_valor_kpi_eje_y(y_max, y_pct, y_escala_0_100)}</div></div>",
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-title'>Mínimo {eje_y_real}</div>"
            f"<div class='kpi-value'>{_formatear_valor_kpi_eje_y(y_min, y_pct, y_escala_0_100)}</div></div>",
            unsafe_allow_html=True,
        )

    pareto_activo_prev = (
        "color_pareto" in df_resumen.columns
        and len(df_resumen) > 0
        and df_resumen["color_pareto"].iloc[0] is not None
    )
    df_resumen_tabla = df_resumen.copy()
    cols_extra_graf = [m["columna"] for m in metricas_extras]
    for m in metricas_extras:
        df_resumen_tabla[m["columna"]] = m["valores"]

    df_mostrar, columnas_visibles, clase_tabla, altura_tabla = _preparar_tabla_metricas_detalle(
        df_resumen_tabla,
        df_filtrado_base,
        eje_x_real,
        eje_y_real,
        viewport_h_ui,
        tabla_font_size,
        metricas_extra=cols_extra_graf,
        ver_completo_pantalla=ver_completo_graf,
    )
    df_export = _preparar_df_exportacion_perfil(
        df_resumen_tabla,
        df_filtrado_base,
        eje_x_real,
        eje_y_real,
        operacion_y,
        pareto_activo_prev,
        metricas_extra=cols_extra_graf,
    )
    meta_export = _meta_exportacion_perfil(
        eje_x_real,
        eje_y_real,
        operacion_y,
        set_pareto_real,
        st.session_state.get("drill_down_categoria"),
        len(df_export),
        metricas_extra=metricas_extras,
    )
    nombre_excel = _nombre_archivo_perfilado(
        eje_x_real,
        eje_y_real,
        operacion_y,
        st.session_state.get("drill_down_categoria"),
    )
    bytes_excel = _bytes_excel_perfilado(df_export, meta_export)
    dims_tabla = _dims_tabla_metricas(clase_tabla, tabla_font_size)
    ancho_fig_pareto = 0

    if pareto_activo_prev:
        w_tabla, w_graf, w_sum, ancho_fig_pareto = _pesos_columnas_pareto(dims_tabla)
        col_tabla, col_chart, col_sum = st.columns(
            [w_tabla, w_graf, w_sum], gap="small"
        )
    else:
        ratio_tabla, ratio_graf = _proporcion_tabla_vs_grafico(
            len(columnas_visibles), pareto_activo_prev
        )
        col_tabla, col_chart = st.columns([ratio_tabla, ratio_graf], gap="small")
        col_sum = None

    with col_tabla:
        st.markdown(
            f'<div class="lri-bloque-tabla" style="display:flex;flex-direction:column;'
            f'align-items:flex-start;width:100%;max-width:100%;overflow:visible;">',
            unsafe_allow_html=True,
        )
        st.session_state.pop("lri_ultimo_excel_guardado", None)
        st.session_state.pop("lri_ultimo_excel_error", None)
        firma_perfil = (
            f"{eje_x_real}|{eje_y_real}|{'|'.join(cols_extra_graf)}|{operacion_y}|"
            f"{operacion_y2}|{operacion_y3}|{set_pareto_real}|{top_n_real}"
        )
        st.download_button(
            label="Guardar en Excel",
            data=bytes_excel,
            file_name=nombre_excel,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=not pareto_activo_prev,
            key=f"lri_excel_{hashlib.md5(firma_perfil.encode(), usedforsecurity=False).hexdigest()[:12]}",
        )

        titulo_tabla = f"Métricas Detalladas · {eje_y_real} ({operacion_y})"
        if "producto" in columnas_visibles:
            titulo_tabla += " · código y producto"
        if cols_extra_graf:
            titulo_tabla += " · " + " · ".join(
                f"{m['columna']} ({m['operacion']})" for m in metricas_extras
            )

        operaciones_por_col = {eje_y_real: operacion_y}
        flags_por_col = {eje_y_real: (y_pct, y_escala_0_100)}
        for m in metricas_extras:
            operaciones_por_col[m["columna"]] = m["operacion"]
            flags_por_col[m["columna"]] = (m["y_pct"], m["y_escala_0_100"])

        def _fmt_columna_metrica(col: str, es_pct: bool, escala_100: bool) -> str:
            if es_pct:
                return _fmt_pandas_columna_porcentaje(escala_100)
            op_col = operaciones_por_col.get(col, operacion_y)
            if op_col == "Promedio" or col not in df_resumen_tabla.columns:
                return "{:,.2f}"
            try:
                mx = float(pd.to_numeric(df_resumen_tabla[col], errors="coerce").max())
            except (TypeError, ValueError):
                mx = 0.0
            return "{:,.2f}" if mx < 100 else "{:,.0f}"

        fmt_cols = {
            c: _fmt_columna_metrica(c, *flags_por_col[c])
            for c in columnas_visibles
            if c in flags_por_col
        }

        colores_pareto_filas = None
        estilos_por_celda = None
        if pareto_activo_prev:
            fs_celda = f"font-size: {dims_tabla['fs_celda']}px;"
            estilos_por_celda = _matriz_estilos_tabla_pareto_multimetrica(
                df_resumen,
                eje_x_real,
                eje_y_real,
                metricas_extras,
                columnas_visibles,
                set_pareto_real,
                fs_celda,
            )

        styler_tabla = _styler_tabla_metricas(df_mostrar, fmt_cols)
        fluido_tabla = _tabla_usa_layout_fluido(pareto_activo_prev, dims_tabla)
        st.markdown(
            _html_tabla_metricas_panel(
                styler_tabla,
                clase_tabla,
                titulo_tabla,
                altura_tabla,
                dims_tabla,
                estilos_por_fila=colores_pareto_filas,
                estilos_por_celda=estilos_por_celda,
                fluido=fluido_tabla,
            ),
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    mostrar_acumulado = (
        st.session_state.get("lri_pareto_acumulado", False)
        and not metricas_extras
    )
    fig = fig_ranking_barras(
        df_resumen,
        eje_x_real,
        eje_y_real,
        operacion_y,
        viewport_h=viewport_h_ui,
        base_font_size=base_font_size,
        y_en_porcentaje=y_pct,
        y_es_tasa_mantenimiento=y_tasa_mant,
        y_escala_0_100=y_escala_0_100,
        mostrar_acumulado=mostrar_acumulado,
        ancho_fig_px=ancho_fig_pareto if pareto_activo_prev and ancho_fig_pareto > 0 else None,
        metricas_extras=metricas_extras,
        ver_completo_pantalla=ver_completo_graf,
        etiqueta_barras_font_size=etiqueta_barras_font_size,
    )

    n_barras_graf = len(df_resumen)
    dual_graf = bool(metricas_extras)
    max_label_graf = (
        int(df_resumen[eje_x_real].astype(str).str.len().max())
        if eje_x_real in df_resumen.columns and len(df_resumen) > 0
        else 0
    )

    if pareto_activo_prev:
        with col_chart:
            _mostrar_grafico_barras(
                fig,
                n_barras_graf,
                dual=dual_graf,
                eje_x=eje_x_real,
                max_label_len=max_label_graf,
                ver_completo_pantalla=ver_completo_graf,
            )
        with col_sum:
            st.markdown(
                '<div style="display:flex;justify-content:flex-end;width:100%;">',
                unsafe_allow_html=True,
            )
            _mostrar_resumen_pareto_ejecutivo(
                df_resumen,
                eje_x_real,
                eje_y_real,
                set_pareto_real,
                base_font_size,
                y_pct,
                y_escala_0_100,
            )
            st.markdown("</div>", unsafe_allow_html=True)
    else:
        with col_chart:
            _mostrar_grafico_barras(
                fig,
                n_barras_graf,
                dual=dual_graf,
                eje_x=eje_x_real,
                max_label_len=max_label_graf,
                ver_completo_pantalla=ver_completo_graf,
            )


# ==============================================================================
# CONTROL DE FLUJO Y ORQUESTACIÓN PRINCIPAL
# ==============================================================================
_sincronizar_revision_perfil()

if "lri_df_datos" not in st.session_state:
    _df0, _err0, _hojas0, _hoja0 = cargar_datos()
    _aplicar_resultado_carga_a_sesion(_df0, _err0, _hojas0, _hoja0)

df = st.session_state.get("lri_df_datos")
error_carga = st.session_state.get("lri_error_carga")

if df is not None:
    cols_texto = df.select_dtypes(include=["object", "category"]).columns.tolist()
    cols_num = df.select_dtypes(include=["number"]).columns.tolist()
    columnas_df = df.columns.tolist()

    aplicar_config_voz_pendiente()

    _sincronizar_operaciones_metricas()

    _sembrar_ejes_default_si_corresponde(df)
    _ajustar_ejes_a_dataframe(df)

    # Eje X diferido (p. ej. botón "Volver"): no tocar lri_man_eje_x tras instanciar el selectbox.
    pend_eje_x = st.session_state.pop("_lri_pending_man_eje_x", None)
    if pend_eje_x is not None and pend_eje_x in columnas_df:
        st.session_state["lri_man_eje_x"] = pend_eje_x

    with st.sidebar:
        st.title("⚙️ Operaciones LRI")
        st.markdown("##### 📁 Cargar datos")
        archivo_subido = st.file_uploader(
            "Archivo Excel",
            type=["xlsx", "xls"],
            help=(
                "Puede elegir cualquier .xlsx desde su PC (Documentos, OneDrive, etc.). "
                f"Si no sube archivo, se usa {os.path.basename(ARCHIVO_EXCEL_PATH)} del proyecto."
            ),
        )
        if archivo_subido is not None:
            upload_id = (archivo_subido.name, len(archivo_subido.getvalue()))
            if st.session_state.get("lri_upload_id") != upload_id:
                df_up, err_up, hojas_up, hoja_up = cargar_datos_desde_upload(
                    archivo_subido.getvalue()
                )
                if err_up:
                    st.error(err_up)
                else:
                    _aplicar_resultado_carga_a_sesion(
                        df_up,
                        None,
                        hojas_up,
                        hoja_up,
                        file_bytes=archivo_subido.getvalue(),
                        reset_ejes=True,
                    )
                    st.session_state["lri_upload_id"] = upload_id
                    st.rerun()
            st.caption(f"Archivo: {archivo_subido.name}")
        else:
            if st.session_state.get("lri_upload_id") is not None:
                st.session_state.pop("lri_upload_id", None)
                df_def, err_def, hojas_def, hoja_def = cargar_datos()
                _aplicar_resultado_carga_a_sesion(
                    df_def,
                    err_def,
                    hojas_def,
                    hoja_def,
                    limpiar_bytes_subida=True,
                    reset_ejes=True,
                )
                st.rerun()
            st.caption(f"Por defecto: {os.path.basename(ARCHIVO_EXCEL_PATH)}")

        hojas_excel = st.session_state.get("lri_excel_hojas") or []
        hoja_activa = st.session_state.get("lri_excel_hoja_activa")
        if len(hojas_excel) > 1:
            idx_hoja = hojas_excel.index(hoja_activa) if hoja_activa in hojas_excel else 0
            hoja_elegida = st.selectbox(
                "Hoja del Excel",
                options=hojas_excel,
                index=idx_hoja,
                help="Profile Pro elige automáticamente la hoja con más datos; puede cambiarla aquí.",
            )
            if hoja_elegida != hoja_activa:
                bytes_hoja = _obtener_bytes_excel_activos()
                if bytes_hoja:
                    df_hoja, err_hoja, hojas_hoja, hoja_ok = _cargar_dataframe_excel(
                        bytes_hoja, sheet_name=hoja_elegida
                    )
                    if err_hoja:
                        st.error(err_hoja)
                    else:
                        _aplicar_resultado_carga_a_sesion(
                            df_hoja,
                            None,
                            hojas_hoja,
                            hoja_ok,
                            reset_ejes=True,
                        )
                        st.rerun()
        elif hoja_activa:
            st.caption(f"Hoja: {hoja_activa}")

        _render_control_voz_sidebar(df)

        st.divider()
        st.markdown("##### Selectores de Respaldo")

        st.selectbox("Eje X (Dimensión Logística)", options=columnas_df, key="lri_man_eje_x")
        st.selectbox("Eje Y (Métrica principal)", options=columnas_df, key="lri_man_eje_y")
        st.radio(
            "Cálculo · métrica principal",
            list(OPS_CALCULO),
            key="lri_man_operacion_y",
            horizontal=True,
        )

        opciones_y2 = _opciones_metrica_adicional(df, st.session_state.get("lri_man_eje_y"))
        if st.session_state.get("lri_man_eje_y2") not in opciones_y2:
            st.session_state["lri_man_eje_y2"] = METRICA_ADICIONAL_NINGUNA
        st.selectbox(
            "Métrica adicional 2 (opcional)",
            options=opciones_y2,
            key="lri_man_eje_y2",
            help=(
                "Hasta 3 métricas en el gráfico (azul, ámbar, verde). "
                "Cada una puede usar Suma o Promedio por separado."
            ),
        )
        if _metrica_adicional_activa(st.session_state.get("lri_man_eje_y2")):
            st.radio(
                "Cálculo · métrica adicional 2",
                list(OPS_CALCULO),
                key="lri_man_operacion_y2",
                horizontal=True,
            )

        opciones_y3 = _opciones_metrica_adicional(
            df,
            [
                st.session_state.get("lri_man_eje_y"),
                st.session_state.get("lri_man_eje_y2"),
            ],
        )
        if st.session_state.get("lri_man_eje_y3") not in opciones_y3:
            st.session_state["lri_man_eje_y3"] = METRICA_ADICIONAL_NINGUNA
        st.selectbox(
            "Métrica adicional 3 (opcional)",
            options=opciones_y3,
            key="lri_man_eje_y3",
        )
        if _metrica_adicional_activa(st.session_state.get("lri_man_eje_y3")):
            st.radio(
                "Cálculo · métrica adicional 3",
                list(OPS_CALCULO),
                key="lri_man_operacion_y3",
                horizontal=True,
            )

        st.session_state["lri_man_operacion"] = st.session_state.get("lri_man_operacion_y", "Suma")
        st.number_input(
            "Filtrar Top N elementos (0 = Todos)",
            min_value=0,
            max_value=50000,
            step=5,
            key="lri_man_top_n",
        )
        if _eje_x_es_codigo_o_descripcion(st.session_state.get("lri_man_eje_x") or ""):
            st.checkbox(
                "Ver gráfico completo en pantalla (sin scroll)",
                key="lri_grafico_scroll_completo",
                help=(
                    "Marcado: todas las barras se ajustan al ancho visible, sin barra de desplazamiento. "
                    "Desmarcado: con más de 35 ítems se usa scroll horizontal para barras más legibles."
                ),
                on_change=st.rerun,
            )
        forzar_sincronizacion_espejo()

        st.divider()
        st.markdown("##### Filtro de Profundización (Drill-Down)")
        if "categoria" in cols_texto:
            lista_cats = ["Ver Todas"] + sorted(df["categoria"].dropna().unique().tolist())
            idx_cat_drill = lista_cats.index(st.session_state["drill_down_categoria"]) if st.session_state["drill_down_categoria"] in lista_cats else 0
            sel_drill = st.selectbox("Aislar por Categoría", options=lista_cats, index=idx_cat_drill)
            
            drill_anterior = st.session_state.get("prev_drill_down_categoria")
            if sel_drill == "Ver Todas":
                st.session_state["drill_down_categoria"] = None
            else:
                st.session_state["drill_down_categoria"] = sel_drill

            drill_actual = st.session_state["drill_down_categoria"]
            if drill_actual != drill_anterior and drill_actual is not None:
                for ct in cols_texto:
                    if _norm_texto(ct) in ["descripcion", "descripcionarticulo", "articulo", "sku"]:
                        st.session_state["_lri_pending_man_eje_x"] = ct
                        st.session_state["prev_drill_down_categoria"] = drill_actual
                        st.rerun()
            st.session_state["prev_drill_down_categoria"] = drill_actual

        st.divider()
        st.markdown("##### 📊 Distribución Pareto ABC")
        if st.session_state["lri_pareto_set"] in MAPEO_PARETO_LEGACY:
            st.session_state["lri_pareto_set"] = MAPEO_PARETO_LEGACY[st.session_state["lri_pareto_set"]]
        opciones_pareto = OPCIONES_PARETO_UI
        idx_pareto = opciones_pareto.index(st.session_state["lri_pareto_set"]) if st.session_state["lri_pareto_set"] in opciones_pareto else 0
        st.session_state["lri_pareto_set"] = st.selectbox("Segmentar Inventario / Demanda", options=opciones_pareto, index=idx_pareto)
        pareto_habilitado = st.session_state["lri_pareto_set"] != "Desactivado (Paleta Azul)"
        if pareto_habilitado:
            st.session_state["lri_pareto_acumulado"] = st.checkbox(
                "Acumulado",
                value=st.session_state.get("lri_pareto_acumulado", False),
                help="Activado: muestra la curva de % acumulado en el gráfico. Desactivado: solo barras Pareto.",
            )
        elif st.session_state.get("lri_pareto_acumulado"):
            st.session_state["lri_pareto_acumulado"] = False

        st.divider()
        st.markdown("##### Ajustes de Interfaz")
        base_font_size = st.slider(
            "Escalar el texto del gráfico",
            min_value=12,
            max_value=32,
            value=16,
            step=1,
            key="lri_fontsize_ui",
            help="Título, ejes y leyenda del gráfico. El resumen ABC Pareto sigue esta escala.",
        )
        etiqueta_barras_font_size = st.slider(
            "Texto sobre las barras (px)",
            min_value=8,
            max_value=24,
            value=int(st.session_state.get("lri_etiqueta_barras_fontsize", 16)),
            step=1,
            key="lri_etiqueta_barras_fontsize_ui",
            help="Tamaño de los números que aparecen encima de cada barra (todas las métricas).",
        )
        st.session_state["lri_etiqueta_barras_fontsize"] = etiqueta_barras_font_size
        tabla_font_size = st.slider(
            "Texto de la tabla (px)",
            min_value=10,
            max_value=28,
            value=int(st.session_state.get("lri_tabla_fontsize", 19)),
            step=1,
            key="lri_tabla_fontsize_ui",
            help="Solo la tabla de métricas detalladas (datos y encabezados).",
        )
        st.session_state["lri_tabla_fontsize"] = tabla_font_size
        viewport_h_ui = st.select_slider("Resolución Vertical (px)", options=[720, 768, 900, 1080, 1200, 1440], value=1080, key="lri_man_viewport_h")

    subtitulo_panel = None
    if st.session_state.get("drill_down_categoria"):
        subtitulo_panel = (
            f"Detalle por artículo · filtro: {st.session_state['drill_down_categoria']}"
        )

    st.markdown(
        f"""
        <style>
        .stApp {{ background-color: #0e1117; color: white; }}
        .kpi-card {{ background-color: #1e2130; padding: 18px; border-radius: 8px; border: 1px solid #2d3142; text-align: center; margin-bottom: 12px; }}
        .kpi-title {{ font-size: 13px; color: #a1a1aa; text-transform: uppercase; margin-bottom: 8px; letter-spacing: 0.5px; }}
        .kpi-value {{ font-size: 26px; font-weight: bold; color: #ffffff; }}
        .block-container {{
            padding-top: 0.35rem !important;
            padding-bottom: 0.5rem !important;
            padding-left: 0.85rem !important;
            padding-right: 1.15rem !important;
            max-width: min(100%, {REF_VIEWPORT_W}px) !important;
            margin-left: 0.35rem !important;
            margin-right: auto !important;
        }}
        section[data-testid="stMain"] > div {{
            padding-left: 0.75rem !important;
            padding-right: 0.85rem !important;
        }}
        [data-testid="stHorizontalBlock"] {{
            gap: 0.45rem !important;
        }}
        .lri-bloque-tabla {{
            width: 100% !important;
            max-width: 100% !important;
            overflow: visible !important;
            margin-left: 0 !important;
            padding-left: 0 !important;
        }}
        .lri-tabla-wrap .lri-tabla-col {{
            max-width: 100% !important;
        }}
        .lri-tabla-wrap .lri-html-table-scroll-container {{
            overflow-x: auto !important;
            overflow-y: auto !important;
        }}
        .lri-grafico-scroll-h {{
            scrollbar-width: auto;
            scrollbar-color: #3b82f6 #0a0f1a;
        }}
        .lri-grafico-scroll-h::-webkit-scrollbar {{
            height: 22px;
        }}
        .lri-grafico-scroll-h::-webkit-scrollbar-track {{
            background: #0a0f1a;
            border-radius: 8px;
        }}
        .lri-grafico-scroll-h::-webkit-scrollbar-thumb {{
            background: linear-gradient(180deg, #60a5fa 0%, #2563eb 100%);
            border-radius: 8px;
            border: 3px solid #0a0f1a;
        }}
        .lri-app-header {{
            display: flex;
            align-items: center;
            gap: 18px;
            min-height: 96px;
            margin: 0 0 10px 0;
            padding: 6px 0;
        }}
        .lri-app-logo {{
            height: 88px;
            width: auto;
            max-width: 280px;
            object-fit: contain;
            flex-shrink: 0;
        }}
        .lri-app-brand {{
            display: flex;
            flex-direction: column;
            justify-content: center;
            min-width: 0;
        }}
        .lri-app-title {{
            font-size: 2.55rem;
            font-weight: 700;
            color: #f8fafc;
            line-height: 1.1;
            letter-spacing: 0.02em;
        }}
        .lri-app-pro {{
            color: #38bdf8;
            font-weight: 800;
            font-size: 1.08em;
        }}
        .lri-app-sub {{
            font-size: 1rem;
            color: #94a3b8;
            margin-top: 4px;
            line-height: 1.25;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    _render_cabecera_app(subtitulo_panel)

    # Tras la carga en sidebar, re-sincronizar df y ejes antes del gráfico.
    df = st.session_state.get("lri_df_datos")
    if df is not None:
        _sembrar_ejes_default_si_corresponde(df)
        _ajustar_ejes_a_dataframe(df)

    render_perfilado_manual_panel(
        df=df,
        viewport_h_ui=viewport_h_ui,
        base_font_size=base_font_size,
        tabla_font_size=tabla_font_size,
        etiqueta_barras_font_size=etiqueta_barras_font_size,
    )
else:
    mensaje = _mensaje_error_carga(texto=error_carga)
    st.error(f"⚠️ {mensaje}")
    if mensaje == MSG_ARCHIVO_EXCEL_ABIERTO:
        st.info(
            f"El archivo `{os.path.basename(ARCHIVO_EXCEL_PATH)}` está en uso. "
            "Guarde y cierre Excel, luego pulse **Reintentar lectura del archivo**."
        )
    else:
        st.markdown(
            f"También puede subir una copia del Excel (`{os.path.basename(ARCHIVO_EXCEL_PATH)}`) "
            "desde el panel de abajo."
        )
    col_retry, _ = st.columns([1, 3])
    with col_retry:
        if st.button("Reintentar lectura del archivo"):
            df_retry, err_retry, hojas_retry, hoja_retry = cargar_datos()
            _aplicar_resultado_carga_a_sesion(
                df_retry, err_retry, hojas_retry, hoja_retry, reset_ejes=True
            )
            st.rerun()
    archivo_rescate = st.file_uploader(
        "Subir Excel manualmente",
        type=["xlsx", "xls"],
        key="lri_rescate_excel",
    )
    if archivo_rescate is not None:
        df_rescate, err_rescate, hojas_rescate, hoja_rescate = cargar_datos_desde_upload(
            archivo_rescate.getvalue()
        )
        if err_rescate:
            st.error(err_rescate)
        else:
            _aplicar_resultado_carga_a_sesion(
                df_rescate,
                None,
                hojas_rescate,
                hoja_rescate,
                file_bytes=archivo_rescate.getvalue(),
                reset_ejes=True,
            )
            st.session_state["lri_upload_id"] = (
                archivo_rescate.name,
                len(archivo_rescate.getvalue()),
            )
            st.rerun()