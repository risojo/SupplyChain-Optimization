import io
import os
import unicodedata

import pandas as pd
import plotly.express as px
import speech_recognition as sr
import streamlit as st
from streamlit_mic_recorder import mic_recorder

# Configuración de página para usar todo el ancho
st.set_page_config(layout="wide")

ARCHIVO_EXCEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "archivo2.xlsx")
# Nombre alternativo que a veces se usa en pruebas
ARCHIVO_EXCEL_ALT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "archivo 2.xlsx")


def _normalizar_nombre_columna(nombre: str) -> str:
    """Minúsculas, sin espacios en los extremos y sin tildes."""
    s = str(nombre).strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")

def _normalizar_texto_comando(texto: str) -> str:
    return _normalizar_nombre_columna(texto)


def _detectar_metrica_voz(cmd: str, df: pd.DataFrame) -> str | None:
    if any(p in cmd for p in ("venta", "ventas")):
        return _resolver_columna(df, "ventas_totales", "ventas totales", "ventas", "ventas_al_costo")
    if any(p in cmd for p in ("stock", "inventario")):
        return _resolver_columna(df, "inv_final/bultos", "inv_prom/bultos", "inv_final", "inventario")
    if "rotacion" in cmd:
        return _resolver_columna(df, "rotacion", "ROTACION")
    if "utilidad" in cmd or "margen" in cmd:
        return _resolver_columna(df, "margen_bruto", "utilidad_bruta", "margen bruto")
    for cn in df.select_dtypes(include=["number"]).columns:
        if _normalizar_nombre_columna(cn) in cmd:
            return str(cn)
    return None


def _detectar_dimension_voz(cmd: str, df: pd.DataFrame) -> str | None:
    reglas: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
        (("subcategoria", "subcat"), ("subcat_producto", "sub_categoria", "subcategoria")),
        (("categoria", "categorias"), ("cat_producto", "categoria_producto", "categoria")),
        (("pais", "country", "origen"), ("pais", "país", "pais_origen", "country")),
        (("proveedor", "supplier"), ("proveedor", "nombre_proveedor")),
        (("codigo", "sku", "codproducto"), ("cod_producto", "sku")),
        (("descripcion", "producto"), ("desc_producto", "descripcion", "descripción")),
        (("empaque",), ("empaque",)),
    )
    for palabras, aliases in reglas:
        if any(p in cmd for p in palabras):
            col = _resolver_columna(df, *aliases)
            if col:
                return col
    for ct in df.select_dtypes(include=["object", "category"]).columns:
        nc = _normalizar_nombre_columna(ct)
        if len(nc) >= 4 and nc in cmd:
            return str(ct)
    return None


def _resolver_columna(df: pd.DataFrame, *candidatos: str) -> str | None:
    """Devuelve el nombre real de columna en `df` si coincide con algún candidato normalizado."""
    mapa = {_normalizar_nombre_columna(c): c for c in df.columns}
    for cand in candidatos:
        k = _normalizar_nombre_columna(cand)
        if k in mapa:
            return mapa[k]
    return None


st.title("Perfilado por Voz")
st.write(
    "Grabe su consulta con el micrófono; el sistema transcribe el audio y genera el gráfico."
)

# 1. Carga de datos
df: pd.DataFrame | None = None
_ruta_excel = ARCHIVO_EXCEL_PATH if os.path.isfile(ARCHIVO_EXCEL_PATH) else ARCHIVO_EXCEL_ALT

try:
    if not os.path.isfile(_ruta_excel):
        st.warning(
            "No se encontró el archivo Excel. Verifique que exista **`archivo2.xlsx`** "
            f"(o `archivo 2.xlsx`) en la misma carpeta que este script.\n\n"
            f"Ruta buscada: `{ARCHIVO_EXCEL_PATH}`"
        )
    else:
        df = pd.read_excel(_ruta_excel, engine="openpyxl")
        df.columns = [_normalizar_nombre_columna(c) for c in df.columns]
        st.success(f"Archivo cargado: `{os.path.basename(_ruta_excel)}` ({len(df):,} filas).")
except PermissionError:
    st.error(
        "No se pudo leer el Excel (permiso denegado). Cierre el archivo en Excel u otro programa "
        "y vuelva a cargar la página."
    )
except ImportError as e:
    st.error(f"Falta el motor para leer .xlsx: {e}. Instale con: `pip install openpyxl`")
except Exception as e:
    st.error(
        f"No se pudo leer el archivo Excel. Verifique el nombre (**archivo2.xlsx**) y que no esté dañado.\n\n"
        f"Detalle: {type(e).__name__}: {e}"
    )

# 2. Consulta por voz (micrófono)
st.subheader("Consulta por voz")
audio = mic_recorder(
    start_prompt="🎙️ Hacer consulta por Voz",
    stop_prompt="🛑 Detener y Procesar",
    key="extractor_audio",
    format="wav",  # Forzamos al componente a entregar un WAV estándar
)

comando: str | None = None

if audio is not None:
    audio_bytes = audio["bytes"]
    r = sr.Recognizer()
    try:
        # Al ser un WAV real empaquetado por el componente, io.BytesIO funcionará con sr.AudioFile
        audio_file = io.BytesIO(audio_bytes)
        with sr.AudioFile(audio_file) as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio_data = r.record(source)

        comando_voz = r.recognize_google(audio_data, language="es-CR")
        st.success(f"Te escuché: '{comando_voz}'")

        comando = comando_voz.lower()

    except sr.UnknownValueError:
        st.error("No logré entender el audio, ¿puedes repetirlo de forma más clara?")
    except sr.RequestError:
        st.error("Error de conexión con el servicio de reconocimiento de voz.")
    except Exception as e:
        st.error(f"Error al procesar: {str(e)}")

if comando and df is not None and not df.empty:
    comando_norm = _normalizar_texto_comando(comando)

    metrica = _detectar_metrica_voz(comando_norm, df)
    dimension = _detectar_dimension_voz(comando_norm, df)

    if metrica and dimension:
        st.info(
            f"Procesando comando: graficando **{metrica}** por **{dimension}**"
        )
        try:
            df_plot = (
                df.groupby(dimension, as_index=False)[metrica]
                .sum()
                .sort_values(metrica, ascending=False)
            )
        except KeyError:
            st.error(
                f"No se pudo agrupar por «{dimension}» con métrica «{metrica}». "
                f"Columnas disponibles: {', '.join(df.columns)}"
            )
        else:
            if df_plot.empty:
                st.warning("No hay datos numéricos para graficar con ese comando.")
            else:
                fig = px.bar(
                    df_plot,
                    x=dimension,
                    y=metrica,
                    title=f"Total de {metrica} por {dimension}",
                    text_auto=".2s",
                    color=dimension,
                )
                fig.update_layout(
                    height=600,
                    font=dict(size=18),
                    title_font=dict(size=24),
                )
                st.plotly_chart(fig, width="stretch")
    elif comando.strip():
        st.warning(
            "No identifiqué la métrica o la dimensión. Pruebe, por ejemplo: "
            "«ventas por país», «ventas por categoría», «stock por proveedor», "
            "«rotación por país»."
        )
        with st.expander("Columnas detectadas en el Excel"):
            st.write(list(df.columns))
elif comando and (df is None or df.empty):
    st.warning("Cargue primero el Excel para procesar comandos.")

# 3. Vista de datos
with st.expander("Ver tabla de datos"):
    if df is not None and not df.empty:
        st.dataframe(df, width="stretch")
    else:
        st.caption("Sin datos cargados.")
