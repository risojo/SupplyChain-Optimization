# Módulo 1 — Perfilado (Profile)

Análisis y perfilado de productos/inventario: ranking por dimensión, métricas,
segmentación Pareto ABC, comparativos de dos métricas, control por voz y
exportación.

## Estado

**Operativo.** Implementación de producción en `modules/perfilado/profile1.py`,
que corre como app Streamlit independiente y está desplegada en Render.

## Datos

Usa el Excel oficial: `data/sources/perfilado.xlsx`
(hojas `data` + `parametros`). Inventory Pro usa el mismo archivo.

## Ejecutar

```bash
streamlit run modules/perfilado/profile1.py
```

## Laboratorio (sin tocar Render)

`profile2.py` es copia de trabajo para experimentos (p. ej. ChatGPT).  
Render y producción siguen en `profile1.py`.

```bash
streamlit run modules/perfilado/profile2.py
```

En el laboratorio: panel **ChatGPT · perfilado** en el sidebar (interpretar cruces + narración).
Requiere `OPENAI_API_KEY` en `.streamlit/secrets.toml`.

### Matriz de perfilado (lab)

ChatGPT solo elige cruces dentro de una **matriz** generada del Excel cargado:

- **Eje X:** todos los atributos (categoría, subcategoría, descripción/SKU, proveedor, etc.)
- **Eje Y:** todas las métricas numéricas (ventas, márgenes, inventarios, demandas, costos…), **máximo 3** a la vez

Archivo de referencia (se regenera al interpretar): `modules/perfilado/matriz_perfilado_actual.json`.

## Integración futura

`view.py` será el punto de entrada cuando se integre Perfilado dentro del
orquestador (`app.py`). La lógica de `profile1.py` se reorganizará entonces en
`logic.py` / `charts.py` / `voice.py` **sin alterar el comportamiento actual**.
