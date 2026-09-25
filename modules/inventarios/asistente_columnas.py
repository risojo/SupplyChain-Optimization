"""Mapeo centralizado: conceptos del asistente → columnas reales de Inventory Pro.

No inventa columnas. Solo documenta lo que existe en data_loader / skus_a_comprar.
``monto compra`` es una columna *derivada* en la capa del asistente
(qty × costo unitario); no modifica las fórmulas oficiales de reposición.
"""
from __future__ import annotations

# Concepto lógico → nombre canónico en el DataFrame de sesión
COLUMNAS = {
    "sku": "codigo",
    "descripcion": "descripcion",
    "proveedor": "proveedor",
    "categoria": "categoria",
    "subcategoria": "subcategoria",
    "inventario_actual": "inventario final bulto",
    "inventario_transito": "valor inventario transito",  # valor monetario, no unidades
    "inventario_seguridad": "stock de seguridad",
    "inventario_minimo": "cantidad minima de inventario",
    "inventario_maximo": "inventario objetivo",  # calculado en tabla de compra
    "rotacion_observada": "rotacion",  # métrica histórica (data_loader)
    "cantidad_recomendada": "cantidad a comprar",
    "costo_unitario": "costo unitario bulto",
    "monto_compra": "monto compra",  # derivada (asistente)
    "pronostico_ajustado": "pronostico ajustado",
}

# Columnas preferidas al mostrar plan de compras (solo si existen).
COLUMNAS_TABLA_COMPRA = (
    "proveedor",
    "codigo",
    "descripcion",
    "inventario final bulto",
    "valor inventario transito",
    "stock de seguridad",
    "cantidad minima de inventario",
    "inventario objetivo",
    "rotacion_objetivo",
    "cantidad a comprar",
    "costo unitario bulto",
    "monto compra",
)

COL_CODIGO = COLUMNAS["sku"]
COL_PROVEEDOR = COLUMNAS["proveedor"]
COL_COSTO = COLUMNAS["costo_unitario"]
COL_MONTO = COLUMNAS["monto_compra"]
COL_QTY = COLUMNAS["cantidad_recomendada"]
COL_TRANSITO = COLUMNAS["inventario_transito"]
COL_INV = COLUMNAS["inventario_actual"]
