"""Rutas y constantes centrales del proyecto.

Centralizar las rutas aquí evita que cada módulo dependa de su ubicación en
el árbol de carpetas. Si un módulo se mueve a un subpaquete más profundo,
sigue resolviendo el logo y los datos a través de estas constantes en lugar
de calcular rutas con ``__file__`` relativas (que es lo que hace hoy
``profile1.py`` y por lo que conviene no moverlo).
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
DATA_DIR = BASE_DIR / "data" / "sources"
LOGO_PATH = ASSETS_DIR / "LRI_logo.png"

APP_TITLE = "LRI Supply Chain Optimization"
APP_SUBTITLE = "Plataforma modular de optimización de cadena de suministro"
