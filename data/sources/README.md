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
`pronostico` de los SKUs certificados lo escribe Forecast Pro (promedio 12 meses + K × σ); los no certificados conservan `AVERAGE`.

No alterar el orden de columnas base. Ambos módulos leen `perfilado.xlsx`.

Valores de `clase`: `A+`, `A`, `B`, `C`, `C-`. Al cargar, Pronóstico escribe la columna
`fill rate deseado` después de `EVAI` (columna AW) según la clase: A+ 99.7 %, A 97 %,
B 90 %, C 60 %, C- 50 %. `EVAI` queda en blanco.

Las apps leen **esta** carpeta (`Documents\LRI SupplyChain optimization\data\sources`).
Las copias del proyecto dentro de OneDrive no las ven las apps; si edita allí, copie el archivo aquí.
