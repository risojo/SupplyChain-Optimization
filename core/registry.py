"""Registro central de los módulos de la aplicación.

El orquestador (``app.py``) recorre este registro e importa cada módulo de
forma dinámica. Para añadir un módulo nuevo basta con: (1) crear su carpeta en
``modules/<clave>/`` con un ``view.py`` que exponga ``render()`` y (2) marcar
``disponible=True`` en su entrada.

El campo ``roles`` deja preparado el control de acceso por roles: cuando se
integre el login, el orquestador mostrará solo los módulos permitidos al rol
del usuario autenticado.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Modulo:
    clave: str
    etiqueta: str
    ruta_modulo: str  # ruta de import, p.ej. "modules.inventarios.view"
    roles: tuple[str, ...] = ("admin",)
    disponible: bool = False


# Orden de negocio definido por el equipo LRI.
MODULOS: tuple[Modulo, ...] = (
    Modulo("perfilado", "1. Perfilado", "modules.perfilado.view", ("admin", "analista"), True),
    Modulo("inventarios", "2. Inventarios", "modules.inventarios.view", ("admin", "analista"), False),
    Modulo("pronostico", "3. Pronóstico", "modules.pronostico.view", ("admin", "analista"), False),
    Modulo("compras", "4. Compras", "modules.compras.view", ("admin", "analista"), False),
    Modulo("almacenaje", "5. Almacenaje", "modules.almacenaje.view", ("admin", "analista"), False),
    Modulo("transportes", "6. Transportes", "modules.transportes.view", ("admin", "analista"), False),
)


def modulos_para_rol(rol: str) -> tuple[Modulo, ...]:
    """Devuelve los módulos visibles para un rol dado (filtro para login)."""
    return tuple(m for m in MODULOS if rol in m.roles)
