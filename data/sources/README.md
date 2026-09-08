# data/sources

Excel oficial compartido (Profile Pro + Inventory Pro):

| Archivo | Uso |
|---|---|
| `inventarios.xlsx` | Oficial: hojas `data` + `parametros` (Profile e Inventarios) |
| `template_inventarios.xlsx` | Plantilla histórica / referencia |

Otros módulos (pendientes): `almacenaje.xlsx`, `compras.xlsx`, `pronostico.xlsx`, `transportes.xlsx`.

Los módulos leen estos archivos de forma directa en su app (o vía loaders).
Cuando se migre a SQL, el punto de cambio será la capa de datos.
