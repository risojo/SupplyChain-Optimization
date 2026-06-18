"""Vista del módulo Inventarios (orquestador ``app.py``).

La app operativa es ``inventario_app.py`` — misma convención que Perfilado
(``profile1.py``). No usar la carpeta local ``_inbox_inventarios/`` (proyecto
viejo del freelance, ignorada por git).

Ejecutar / desplegar:

    streamlit run modules/inventarios/inventario_app.py
"""
import streamlit as st


def render() -> None:
    st.subheader("2. Inventarios")
    st.success("Módulo operativo. Implementación: `inventario_app.py`.")
    st.markdown(
        "La versión de trabajo de **Inventarios** es la app independiente:\n\n"
        "```bash\n"
        "streamlit run modules/inventarios/inventario_app.py\n"
        "```\n\n"
        "**Render:** servicio `lri-inventarios` → "
        "`modules/inventarios/inventario_app.py`\n\n"
        "Datos: `data/sources/template_inventarios.xlsx`"
    )
