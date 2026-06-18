# Módulo 4 — Perfilado (Profile)

Análisis y perfilado de productos/inventario: ranking por dimensión, métricas,
segmentación Pareto ABC, comparativos de dos métricas, control por voz y
exportación.

## Estado

**Operativo.** Implementación de producción en `modules/perfilado/profile1.py`,
que corre como app Streamlit independiente y está desplegada en Render.

## Datos

Usa la capa de datos compartida: lee `data/sources/perfilado.xlsx` (raíz del
repo). El día de mañana esa fuente será SQL sin cambiar el módulo.

## Ejecutar

```bash
streamlit run modules/perfilado/profile1.py
```

## Integración futura

`view.py` será el punto de entrada cuando se integre Perfilado dentro del
orquestador (`app.py`). La lógica de `profile1.py` se reorganizará entonces en
`logic.py` / `charts.py` / `voice.py` **sin alterar el comportamiento actual**.
