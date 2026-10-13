# Módulo 1 — Pronóstico (Forecast Pro)

Módulo de inicio de la plataforma (primero en `core/registry.py`).
Pronóstico de demanda: certificación del pronóstico oficial, tendencia,
estacionalidad, distribución normal y simulación Monte Carlo.

## Panel lateral (orden fijo, mismo formato que Profile Pro)

1. **📁 Cargar datos** — cargador de Excel opcional. Sin archivo subido se usa el
   compartido `perfilado.xlsx` (mismo de Inventarios, Compras y Profile Pro).
2. **Mostrar archivo** (casilla, activa al inicio) — muestra el archivo completo
   (todas las hojas) arriba del panel principal, resaltando las columnas que usa el pronóstico.
3. **Cálculo** — botón **📈 Cálculo del pronóstico** (formato de Inventarios: botón a todo
   el ancho, resaltado cuando ya se calculó). Calcula todo y desmarca «Mostrar archivo».
4. **Alternativas de cálculo** (botones verticales debajo) — ✅ Certificación, 📉 Serie por SKU,
   📅 Estacionalidad, 🔔 Distribución normal, 🎲 Monte Carlo. Si aún no se calculó, el
   botón de la alternativa calcula primero. Debajo, la casilla **📥 Mostrar reportes (Excel)**
   (apagada: los reportes se muestran solo si se piden). Luego **⚙️ Nivel de servicio** (plegable), **🎨 Gráficos** (plegable, slider «Ancho de barras»
para todos los gráficos de barras) y los filtros.

Futuro: un archivo de resultados en blanco (`pronostico.xlsx`) que llenarán los cálculos.

## Estado

**En desarrollo (local).** Aún no tiene servicio en Render ni está marcado
`disponible=True` en `core/registry.py`.

## Ejecutar

```bash
streamlit run modules/pronostico/pronostico_app.py
```

## Datos

Excel maestro compartido: `data/sources/perfilado.xlsx`, hoja `data`
(o un Excel subido desde el panel lateral con la misma estructura).

## Mapa de programas y resultados

| Archivo | Resultado / responsabilidad |
|---------|-----------------------------|
| `pronostico_app.py` | App Streamlit: panel lateral (archivo → calcular → vistas), filtros y vistas |
| `pronostico_calculos.py` | Cálculos sin UI: carga/normalización, pronóstico, certificación, métodos, estacionalidad, Monte Carlo |
| `pronostico_excel.py` | Escribe `fill rate deseado` y el pronóstico LRI (columna `pronostico`) en la hoja `data` del Excel, editando el XML para conservar el resto de fórmulas y valores |
| `view.py` | Solo aviso al orquestador; **no** es la app |
| `tests/test_pronostico_calculos.py` | Pruebas de fórmulas + certificación contra el Excel real |
| `tests/test_pronostico_excel.py` | Pruebas de la escritura de `fill rate deseado` y del pronóstico (libro mínimo, fórmulas compartidas y copia del Excel real) |

### Pestañas

| Pestaña | Resultado |
|---------|-----------|
| **Pronóstico** (botón «📈 Cálculo del pronóstico») | Pronóstico mensual = promedio 12 meses + K × σ solo de SKUs certificados; «Ver por» SKU (todos) o categoría / subcategoría / proveedor: al pulsarlo se abre un panel con los grupos; al elegir uno se muestran el gráfico de barras de **sus SKUs** (promedio + K × σ, mayor a menor) y la tabla de esos SKUs con descripción y pronóstico. Sin resúmenes por grupo: los pedidos son por SKU (administrador de categorías o comprador por proveedor). Con reportes activos, «📥 Artículos a pedir · …» exporta esos SKUs a Excel; excluidos (no certificados) en un plegable, pendientes de política; Excel si se piden reportes |
| Certificación | SKUs certificados (CV 0–30 %) vs no certificados (CV > 30 %), gráfico de CV con línea del límite, tablas (primero los no certificados, con casilla «📈 Ver gráfico» que sustituye el gráfico de arriba por la dispersión mensual del SKU), cada tabla con su «🔎 Ver por» (ventana con categorías / subcategorías / proveedores y su conteo; al elegir uno filtra esa tabla; ✕ vuelve a todos). Reportes Excel (por tabla, reporte de certificación con resúmenes por grupo y pronóstico completo) **solo si se marca «📥 Mostrar reportes (Excel)»** en el panel lateral |
| Serie por SKU | Demanda real, tendencia, pronóstico y ajustado; comparación de métodos (MAD, MAPE, sesgo) |
| Estacionalidad | Índice mensual por total / categoría / subcategoría / proveedor |
| Distribución normal | Curva normal del SKU, zona cubierta por el nivel de servicio, probabilidad consultable |
| Monte Carlo | Demanda simulada, percentiles P50/P90/P95 y cobertura real del pronóstico ajustado |

## Fórmulas oficiales (igual que el Excel)

| Columna Excel | Fórmula |
|---------------|---------|
| `pronostico` | Certificados: **valor del pronóstico LRI** (lo escribe la app). No certificados: `AVERAGE(demanda mes 1..12)` |
| `desviacion standart` | `STDEV.S(demanda mes 1..12)` |
| `stock seguridad k` | **Nivel de servicio** (probabilidad, p. ej. 0.8), no un factor z |
| `pronostico ajustado` | Certificados: `=pronostico` (escrito por la app). No certificados: `NORMINV(nivel, pronostico, desviacion)` = pronóstico + z·σ |

### Pronóstico LRI (acordado con el usuario)

`pronostico lri = promedio 12 meses + K × σ`, donde σ = desviación estándar de los 12 meses y
**K = NORMSINV(fill rate deseado)** de la clase (`pronostico_calculos.factor_k`):
A+ 99.7 % → K 2.75 · A 97 % → 1.88 · B 90 % → 1.28 · C 60 % → 0.25 · C- 50 % → 0.
Solo se calcula para SKUs **certificados** (CV ≤ 30 %); los no certificados quedan sin pronóstico
hasta definir su política. Consolidado por grupo (`consolidar_pronostico`) = suma de los SKUs.

### El pronóstico se escribe en el Excel

Al pulsar «📈 Cálculo del pronóstico» con el archivo compartido, `pronostico_excel.escribir_pronostico_excel()`
pone el pronóstico LRI como **valor** en la columna `pronostico` (W) de cada SKU certificado: sustituye la
fórmula `AVERAGE` o llena la celda si está vacía. Los no certificados conservan su fórmula.
En esas filas `pronostico ajustado` (Z) pasa a `=pronostico` (W): el pronóstico LRI ya incluye K × σ y
`NORMINV(nivel, pronostico, σ)` sumaría un segundo margen (p. ej. 77001046: 280.4 → 317.9). Los no
certificados conservan `NORMINV`.
Se quita `calcChain.xml` (Excel lo reconstruye) y se copia `perfilado.xlsx` → `inventarios.xlsx`.
Inventarios lee estas columnas: el pronóstico nuevo llega a Compras (demanda diaria e inventario objetivo).
Respaldo previo a la primera escritura: `data/sources/respaldos/` (no se versiona).

### Columna `fill rate deseado` (se escribe en el Excel)

Al cargar la app, `pronostico_excel.actualizar_fill_rate_excel()` escribe la columna
`fill rate deseado` en `perfilado.xlsx`, hoja `data`, **después de `EVAI`** (columna AW),
según `clase`, con formato `0.0%`. No toca ninguna otra celda; `EVAI` sigue en blanco.
Solo reescribe si el archivo cambió (por fecha de modificación) y si algún valor difiere.
Si el Excel está abierto, avisa y muestra el valor calculado en pantalla.
Servirá para el stock de seguridad en Inventarios.

| Clase | A+ | A | B | C | C- |
|-------|----|---|---|---|----|
| Fill rate deseado | 99.7 % | 97 % | 90 % | 60 % | 50 % |

Mapeo en `pronostico_calculos.FILL_RATE_POR_CLASE`. Clase no reconocida → vacío.

- Los encabezados mal escritos (`demada mes 1`, `demanda_mes2`) se normalizan a `demanda mes N`.
- **Certificación por CV** (`pronostico_calculos.certificar_cv`, límite `CV_MAX_CERTIFICADO = 0.30`):
  CV = desviación estándar ÷ pronóstico. **Certificado** si 0 ≤ CV ≤ 30 % → modelo estadístico
  (distribución normal). **No certificado** si CV > 30 % → otro modelo o demanda anual.
  Sin demanda promedio → «Sin demanda».
- «Cuadra con Excel = Sí» cuando el recálculo coincide con las tres columnas oficiales
  (`pronostico` = promedio o pronóstico LRI; `pronostico ajustado` = NORMINV sobre el `pronostico` del Excel,
  o igual al `pronostico` cuando ya se escribió el pronóstico LRI).
- Promedio móvil, suavizamiento exponencial y regresión lineal son **comparativos**; no reemplazan el pronóstico oficial.
## Administración de `pronostico_calculos.py`

Lo mantiene el agente de Cursor (acuerdo con el usuario):

- Fórmulas y cálculos nuevos van en `pronostico_calculos.py`; `pronostico_app.py` solo presenta.
- Cada cambio de fórmula lleva su prueba y se corren las pruebas antes de entregar.
- Si cambia una fórmula oficial del Excel, se actualizan este README y la regla de organización.

## Pruebas

```bash
python -m unittest discover -s modules/pronostico/tests -v
```

## Al reorganizar

Actualizar **este README** y la regla Cursor `.cursor/rules/lri-python-organizacion.mdc`.
