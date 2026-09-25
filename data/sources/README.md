# data/sources

Excel oficial compartido (orden de columnas **fijo** según foto del usuario):

| Archivo | Uso |
|---|---|
| `perfilado.xlsx` | Fuente oficial: hojas `data` + `parametros` — **Profile Pro** (`profile1.py` / `profile2.py`) e **Inventory Pro** |
| `inventarios.xlsx` | Copia idéntica de `perfilado.xlsx` (mismo contenido y mismo orden de columnas) |
| `template_inventarios.xlsx` | Plantilla histórica / referencia |

Orden fijo de `data` (inicio):  
`codigo → categoria → clase → subcategoria → descripcion → proveedor → pais → …`  
Al final opcionales de control: `EVAI`.  
Tras demanda 1–12 (posición del Excel): `pronostico`, `desviacion estandar` (también «standart»), `stock seguridad k`, `pronostico ajustado`.

No alterar el orden de columnas base. Ambos módulos leen `perfilado.xlsx`.
