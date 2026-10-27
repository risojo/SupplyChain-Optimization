"""Autenticación y control de acceso por roles.

``exigir_clave_web`` protege las tres apps públicas en Render (Profile Pro,
Inventory Pro y Forecast Pro) con la misma clave. ``login`` sigue disponible
para el orquestador ``app.py`` (admin por defecto hasta haber usuarios reales).
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from typing import Optional

import streamlit as st

ROLES_VALIDOS = ("admin", "analista", "invitado")

# Clave compartida de las 3 apps en Render. Preferir LRI_APP_PASSWORD en el
# entorno (render.yaml / secrets); este valor es el respaldo acordado.
_CLAVE_WEB_DEFECTO = "lri1975"
_CLAVE_SESION = "lri_web_auth_ok"


@dataclass
class Usuario:
    username: str
    nombre: str
    rol: str


def login() -> Optional[Usuario]:
    """Punto único de autenticación. Hoy: admin por defecto (sin backend)."""
    # TODO: integrar login real con roles (streamlit-authenticator + DB).
    return Usuario(username="admin", nombre="Administrador", rol="admin")


def puede_acceder(usuario: Optional[Usuario], roles_modulo: tuple[str, ...]) -> bool:
    """True si el usuario tiene un rol permitido para el módulo."""
    return usuario is not None and usuario.rol in roles_modulo


def _clave_web_esperada() -> str:
    env = (os.environ.get("LRI_APP_PASSWORD") or "").strip()
    if env:
        return env
    try:
        sec = st.secrets.get("LRI_APP_PASSWORD", "")
        if sec:
            return str(sec).strip()
    except Exception:
        pass
    return _CLAVE_WEB_DEFECTO


def exigir_clave_web(*, titulo: str = "LRI Supply Chain") -> None:
    """Pide la clave compartida y detiene la app hasta que sea correcta.

    Misma clave para Profile Pro, Inventory Pro y Forecast Pro en Render.
    """
    if st.session_state.get(_CLAVE_SESION):
        return

    st.markdown(f"### {titulo}")
    st.caption("Acceso restringido · introduzca la clave para continuar.")
    with st.form("lri_web_login"):
        ingreso = st.text_input("Clave", type="password", autocomplete="current-password")
        enviado = st.form_submit_button("Entrar", type="primary")

    if enviado:
        esperado = _clave_web_esperada()
        if secrets.compare_digest(ingreso.strip(), esperado):
            st.session_state[_CLAVE_SESION] = True
            st.rerun()
        st.error("Clave incorrecta.")
    st.stop()
