"""Vista del módulo Perfilado.

La versión operativa vive en ``profile1.py`` (raíz) y funciona como app
independiente. Para no alterar ese código probado, aquí solo se documenta
cómo ejecutarlo; la integración completa dentro del orquestador se hará en un
paso posterior y controlado.
"""
import streamlit as st


def render() -> None:
    st.subheader("Perfilado (Profile)")
    st.success("Módulo operativo. Implementación: `profile1.py`.")
    st.markdown(
        "La versión en producción de **Perfilado** se ejecuta hoy como "
        "aplicación independiente:\n\n"
        "```bash\nstreamlit run modules/perfilado/profile1.py\n```\n\n"
        "Se integrará dentro de este orquestador más adelante, sin modificar "
        "el código que ya está validado y desplegado."
    )
