# Módulo Inventarios — Inventory Pro

## App oficial (GitHub + Render)

| Qué | Dónde |
|-----|--------|
| **Programa principal** | `inventario_app.py` |
| **Excel de datos** | `data/sources/perfilado.xlsx` (espejo: `inventarios.xlsx`) |
| **Ejecutar local** | `streamlit run modules/inventarios/inventario_app.py` |
| **Render** | mismo comando sobre `main` |

## Mapa de programas y resultados

### Núcleo

| Archivo | Resultado / responsabilidad |
|---------|-------------------------------|
| `inventario_app.py` | Orquestador Streamlit (Decisiones, Herramientas, carga Excel, voz sidebar) |
| `data_loader.py` | DataFrame final oficial (columnas canónicas + métricas) |
| `parametros.py` | Hoja `parametros` del Excel → JSON / sesión |
| `ui_theme.py` | Presentación de tablas y estilos |
| `view.py` | Solo aviso al orquestador raíz — **no** es la app |

### Scorecard · GMROI · EVAI

| Archivo | Resultado |
|---------|-----------|
| `scorecard.py` | ICC, GMROI, EVAI; pivotes por categoría **o** subcategoría; gráficos |
| `destruccion_valor.py` | Diagnóstico EVAI negativo |
| `analisis_chatgpt.py` | Narración EVAI / requerimiento de compra |

- Presentar por **subcategoría** ⇒ ICC por subcategoría.
- **Utilidad bruta** = `margen bruto total` ($).
- **Margen de utilidad** = `margen utilidad ventas` (%).

### SKUs a comprar

| Archivo | Resultado |
|---------|-----------|
| `skus_a_comprar.py` | Cantidad a comprar (columna en color), filtros, gráfico, export Excel |

Excel de compra: Ítem/SKU, Descripción, Proveedor, Categoría, Subcategoría, Cantidad a comprar.

### Asistente Inteligente (motor universal)

| Archivo | Resultado |
|---------|-----------|
| `asistente_ui.py` | Chat, verificación, tabla, Plotly, export si hay compra |
| `asistente_openai.py` | Solo interpreta NL → plan / tools |
| `asistente_query_plan.py` | `QueryPlan` + ejecución local determinista |
| `asistente_catalogo.py` | Catálogo semántico del DataFrame |
| `asistente_derivadas.py` | Reglas (qty según mínimo, presupuesto anual, …) |
| `asistente_tools.py` | Compras por rotación, enriquecimiento |
| `asistente_charts.py` | Gráficos Plotly |
| `asistente_columnas.py` | Alias → columnas oficiales |

Flujo: **pregunta → plan estructurado → validar catálogo → ejecutar en DF oficial → tabla + gráfico**.  
Voz = transcripción + mismo flujo. Sin Base64 ni cálculos inventados por el modelo.

### Pruebas

`tests/test_motor_universal.py`, `test_motor_general.py`, `test_asistente_inventarios.py`

## Parámetros (JSON)

| Archivo | Uso |
|---------|-----|
| `parametros_base/parametros.json` | Base versionada |
| `parametros_actuales/` | Sesión / Excel (gitignored) |
| `parametros_guardados.json` | Local (gitignored) |
| `drivers_guardados.json` | Drivers scorecard (gitignored) |

## No confundir

- `_inbox_inventarios/` — temporal freelance (gitignore).
- Profile Pro producción = `modules/perfilado/profile1.py` (no `profile2.py`).

## Al reorganizar

Actualizar **este README** y la regla Cursor `.cursor/rules/lri-python-organizacion.mdc`.
