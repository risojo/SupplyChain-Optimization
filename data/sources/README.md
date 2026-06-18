# data/sources

Fuentes de datos compartidas. **Una por módulo** (orden LRI):

| Archivo | Módulo |
|---|---|
| `almacenaje.xlsx` | 1. Almacenaje *(pendiente)* |
| `compras.xlsx` | 2. Compras *(pendiente)* |
| `template_inventarios.xlsx` | 3. Inventarios ✅ |
| `perfilado.xlsx` | 4. Perfilado ✅ |
| `pronostico.xlsx` | 5. Pronóstico *(pendiente)* |
| `transportes.xlsx` | 6. Transportes *(pendiente)* |

Todos los módulos acceden a estos datos **a través de `data/loaders.py`**
(el "mostrador"), nunca leyendo el archivo directamente. Así, cuando al final
del proyecto se migre a una base de datos **SQL**, solo cambia `loaders.py` y
los módulos no se tocan.
