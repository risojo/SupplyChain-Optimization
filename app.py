"""Orquestador de LRI Supply Chain Optimization.

Punto de entrada que arma la navegación a partir del registro de módulos
(``core/registry.py``) y los carga de forma DINÁMICA con ``importlib``. Está
preparado para login y control de acceso por roles: solo muestra los módulos
permitidos al rol del usuario autenticado.

IMPORTANTE: el módulo Perfilado en producción se ejecuta hoy como
``profile1.py`` (app independiente, intacta). Este orquestador es el armazón
para integrar todos los módulos de forma progresiva sin tocar lo que ya
funciona. Para correrlo:

    streamlit run app.py
"""
import importlib

import streamlit as st

from core import auth, settings, ui
from core.registry import modulos_para_rol


def main() -> None:
    st.set_page_config(page_title=settings.APP_TITLE, layout="wide")

    usuario = auth.login()
    if usuario is None:
        st.warning("Inicia sesión para continuar.")
        st.stop()

    with st.sidebar:
        st.markdown(f"**👤 {usuario.nombre}**  \n`{usuario.rol}`")

    ui.cabecera()

    modulos = modulos_para_rol(usuario.rol)
    if not modulos:
        st.error("Tu rol no tiene módulos asignados.")
        return

    tabs = st.tabs([m.etiqueta for m in modulos])
    for tab, modulo in zip(tabs, modulos):
        with tab:
            if not modulo.disponible:
                st.info(f"Módulo **{modulo.etiqueta}** — próximamente.")
                continue
            try:
                vista = importlib.import_module(modulo.ruta_modulo)
                vista.render()
            except Exception as exc:  # noqa: BLE001 - mostrar el error en la UI
                st.error(f"No se pudo cargar el módulo '{modulo.clave}': {exc}")


if __name__ == "__main__":
    main()
