"""Vista del módulo Transportes (orquestador ``app.py``).

La app operativa es ``transportes_app.py`` — misma convención que Inventarios
(``inventario_app.py``).

Ejecutar:

    streamlit run modules/transportes/transportes_app.py
"""
import streamlit as st


def render() -> None:
    st.subheader("6. Transportes")
    st.success("Módulo en desarrollo. Implementación: `transportes_app.py`.")
    st.markdown(
        "La versión de trabajo de **Transportes** es la app independiente:\n\n"
        "```bash\n"
        "streamlit run modules/transportes/transportes_app.py\n"
        "```\n\n"
        "Datos: `modules/transportes/data/basedatos_ transporte.xlsx` "
        "(hoja `Template clientes y rutas`)."
    )
