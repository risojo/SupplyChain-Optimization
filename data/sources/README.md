# data/sources

Fuentes de datos compartidas de la plataforma. **Una por módulo**, con el
nombre de la clave del módulo:

| Archivo | Módulo |
|---|---|
| `perfilado.xlsx` | 1. Perfilado |
| `template_inventarios.xlsx` | 2. Inventarios |
| `pronostico.xlsx` | 3. Pronóstico *(pendiente)* |
| `compras.xlsx` | 4. Compras *(pendiente)* |
| `almacenaje.xlsx` | 5. Almacenaje *(pendiente)* |
| `transportes.xlsx` | 6. Transportes *(pendiente)* |

Todos los módulos acceden a estos datos **a través de `data/loaders.py`**
(el "mostrador"), nunca leyendo el archivo directamente. Así, cuando al final
del proyecto se migre a una base de datos **SQL**, solo cambia `loaders.py` y
los módulos no se tocan.
