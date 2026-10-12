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
   botón de la alternativa calcula primero. Luego **⚙️ Nivel de servicio** (plegable) y los filtros.

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
| `pronostico_excel.py` | Escribe `fill rate deseado` en la hoja `data` del Excel (solo esa columna, editando el XML para conservar fórmulas y valores) |
| `view.py` | Solo aviso al orquestador; **no** es la app |
| `tests/test_pronostico_calculos.py` | Pruebas de fórmulas + certificación contra el Excel real |
| `tests/test_pronostico_excel.py` | Pruebas de la escritura de `fill rate deseado` (libro mínimo + copia del Excel real) |

### Pestañas

| Pestaña | Resultado |
|---------|-----------|
| Certificación | SKUs certificados (CV 0–30 %) vs no certificados (CV > 30 %), gráfico de CV con línea del límite, tablas (primero los no certificados, con casilla «📈 Ver gráfico» que sustituye el gráfico de arriba por la dispersión mensual del SKU), export Excel |
| Serie por SKU | Demanda real, tendencia, pronóstico y ajustado; comparación de métodos (MAD, MAPE, sesgo) |
| Estacionalidad | Índice mensual por total / categoría / subcategoría / proveedor |
| Distribución normal | Curva normal del SKU, zona cubierta por el nivel de servicio, probabilidad consultable |
| Monte Carlo | Demanda simulada, percentiles P50/P90/P95 y cobertura real del pronóstico ajustado |

## Fórmulas oficiales (igual que el Excel)

| Columna Excel | Fórmula |
|---------------|---------|
| `pronostico` | `AVERAGE(demanda mes 1..12)` |
| `desviacion standart` | `STDEV.S(demanda mes 1..12)` |
| `stock seguridad k` | **Nivel de servicio** (probabilidad, p. ej. 0.8), no un factor z |
| `pronostico ajustado` | `NORMINV(nivel, pronostico, desviacion)` = pronóstico + z·σ |

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
- «Cuadra con Excel = Sí» cuando el recálculo coincide con las tres columnas oficiales.
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
