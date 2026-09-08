# Módulo 1 — Perfilado (Profile)

Análisis y perfilado de productos/inventario: ranking por dimensión, métricas,
segmentación Pareto ABC, comparativos de dos métricas, control por voz y
exportación.

## Estado

**Operativo.** Implementación de producción en `modules/perfilado/profile1.py`,
que corre como app Streamlit independiente y está desplegada en Render.

## Datos

Usa el Excel oficial compartido: `data/sources/inventarios.xlsx`
(hojas `data` + `parametros`). Inventory Pro usa el mismo archivo.

## Ejecutar

```bash
streamlit run modules/perfilado/profile1.py
```

## Integración futura

`view.py` será el punto de entrada cuando se integre Perfilado dentro del
orquestador (`app.py`). La lógica de `profile1.py` se reorganizará entonces en
`logic.py` / `charts.py` / `voice.py` **sin alterar el comportamiento actual**.
