"""Vista del módulo Pronóstico (orquestador ``app.py``).

La app operativa es ``pronostico_app.py`` — misma convención que Inventarios
(``inventario_app.py``) y Perfilado (``profile1.py``).

Ejecutar:

    streamlit run modules/pronostico/pronostico_app.py
"""
import streamlit as st


def render() -> None:
    st.subheader("1. Pronóstico")
    st.success("Módulo en desarrollo. Implementación: `pronostico_app.py`.")
    st.markdown(
        "La versión de trabajo de **Pronóstico** es la app independiente:\n\n"
        "```bash\n"
        "streamlit run modules/pronostico/pronostico_app.py\n"
        "```\n\n"
        "Datos: `data/sources/perfilado.xlsx` (hoja `data`, columnas `demanda mes 1..12`)"
    )
