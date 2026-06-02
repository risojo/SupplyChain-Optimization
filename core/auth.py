"""Autenticación y control de acceso por roles.

Estructura preparada para integrar un login real (por ejemplo
``streamlit-authenticator`` + una base de datos de usuarios). Mientras no
exista backend de usuarios, ``login`` devuelve un administrador por defecto
para no bloquear el desarrollo de los módulos.

Cuando se implemente el login, basta con reemplazar el cuerpo de ``login``
para que devuelva el ``Usuario`` autenticado (o ``None`` si falla), sin tocar
el resto de la aplicación.
"""
from dataclasses import dataclass
from typing import Optional

ROLES_VALIDOS = ("admin", "analista", "invitado")


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
