"""Helpers de interfaz compartidos por el orquestador y los módulos."""
import base64
from typing import Optional

import streamlit as st

from core import settings


def _logo_base64() -> Optional[str]:
    """Devuelve el logo LRI en base64, o ``None`` si no está disponible."""
    try:
        with open(settings.LOGO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")
    except OSError:
        return None


def cabecera(subtitulo: Optional[str] = None) -> None:
    """Pinta la cabecera con logo + título de la plataforma."""
    logo = _logo_base64()
    sub = subtitulo or settings.APP_SUBTITLE
    img_html = (
        f"<img src='data:image/png;base64,{logo}' style='height:64px;'>" if logo else ""
    )
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:16px;margin-bottom:8px;">
            {img_html}
            <div>
                <div style="font-size:1.9rem;font-weight:700;">{settings.APP_TITLE}</div>
                <div style="color:#94a3b8;">{sub}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
