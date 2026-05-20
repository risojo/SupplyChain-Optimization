"""Pronóstico - Opción 1: Carga de datos.

Este es el punto de entrada de datos del capítulo Pronóstico.
- Lee ``base_de_datos.xlsx`` desde la carpeta del proyecto.
- Lo transforma con ``utils.backend.get_transformed_dataframe``.
- Lo guarda en ``st.session_state.datos_pronostico['tendencias']`` para
  que las demás opciones del capítulo lo reutilicen.
- Muestra una vista previa y opciones de exportación.
"""
import os

import streamlit as st

from utils import backend


def _ruta_base_datos():
    """Localiza ``base_de_datos.xlsx`` en la carpeta raíz del proyecto."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    proyecto_dir = os.path.dirname(base_dir)
    return os.path.join(proyecto_dir, "base_de_datos.xlsx")


def render():
    """Pinta la sección de carga de datos del capítulo Pronóstico."""
    st.subheader("Opción 1: Carga de datos")
    st.caption(
        "Lee 'base_de_datos.xlsx' y deja los datos disponibles para todas las "
        "opciones del capítulo Pronóstico."
    )

    ruta = _ruta_base_datos()

    if not os.path.exists(ruta):
        st.error(f"No se encontró el archivo '{os.path.basename(ruta)}' en: {ruta}")
        st.info("Asegúrate de que el archivo Excel esté en la carpeta del proyecto.")
        return

    try:
        df_transformed_full = backend.get_transformed_dataframe(ruta)
    except Exception as e:
        st.error(f"Error al leer/transformar el archivo: {e}")
        return

    # Aseguramos tipos compatibles con Arrow para evitar errores de visualización
    if "cod_producto" in df_transformed_full.columns:
        df_transformed_full["cod_producto"] = df_transformed_full["cod_producto"].astype(str)

    st.session_state.datos_pronostico["tendencias"] = df_transformed_full
    st.success(
        f"Datos cargados correctamente: {len(df_transformed_full)} filas, "
        f"{len(df_transformed_full.columns)} columnas."
    )

    tab_1, tab_2 = st.tabs(["Tabla 📄", "Exportar 📁"])

    with tab_1:
        # CSS local: quita los bordes verdes globales y agranda la letra
        # sólo en la tabla de Carga de datos.
        st.markdown(
            """
            <style>
            /* Quitar bordes y ocupar todo el ancho del contenedor */
            .main [class*="st-key-carga_datos_tabla"] div[data-testid="stDataFrame"],
            .main [class*="st-key-carga_datos_tabla"] div[data-testid="stDataFrameResizable"],
            .main [class*="st-key-carga_datos_tabla"] .stDataFrame,
            .main [class*="st-key-carga_datos_tabla"] .stDataFrameResizable {
                border: none !important;
                outline: none !important;
                box-shadow: none !important;
                width: 100% !important;
                max-width: 100% !important;
            }
            /* Quitar bordes en cualquier elemento descendiente del dataframe */
            .main [class*="st-key-carga_datos_tabla"] [data-testid="stDataFrame"] *,
            .main [class*="st-key-carga_datos_tabla"] [data-testid="stDataFrameResizable"] * {
                border-color: transparent !important;
                outline: none !important;
            }
            /* Letra más grande en celdas y encabezados */
            .main [class*="st-key-carga_datos_tabla"] [data-testid="stDataFrame"] td,
            .main [class*="st-key-carga_datos_tabla"] [data-testid="stDataFrame"] th,
            .main [class*="st-key-carga_datos_tabla"] [data-testid="stDataFrameCell"],
            .main [class*="st-key-carga_datos_tabla"] [data-testid="stDataFrameCellHeader"] {
                border: none !important;
                font-size: 18px !important;
                line-height: 1.4 !important;
            }
            /* Soporte para el grid basado en canvas (Glide Data Grid)
               Streamlit lo expone con una clase glide-data-grid */
            .main [class*="st-key-carga_datos_tabla"] .glide-data-grid,
            .main [class*="st-key-carga_datos_tabla"] .glide-data-grid * {
                border: none !important;
                outline: none !important;
                font-size: 18px !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        with st.container(key="carga_datos_tabla"):
            try:
                df_styled = backend.get_styled_dataframe(df_transformed_full)
                st.dataframe(
                    df_styled,
                    hide_index=True,
                    width="stretch",
                    height=900,
                )
            except Exception:
                st.dataframe(
                    df_transformed_full,
                    hide_index=True,
                    width="stretch",
                    height=900,
                )

    with tab_2:
        st.write("### Opciones de descarga")
        backend.download_dataframe(df_transformed_full, name="base_de_datos_export")


if __name__ == "__main__":
    st.set_page_config(page_title="Carga de datos", page_icon="🏗️", layout="wide")
    if "datos_pronostico" not in st.session_state:
        st.session_state.datos_pronostico = {}
    render()
