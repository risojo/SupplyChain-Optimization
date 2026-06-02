"""Módulos funcionales de la plataforma.

Cada subpaquete (``perfilado``, ``inventarios``, ``pronostico``, ``compras``,
``almacenaje``, ``transportes``) expone una función ``render()`` en su
``view.py``. El orquestador los carga dinámicamente según el registro en
``core/registry.py``.
"""
