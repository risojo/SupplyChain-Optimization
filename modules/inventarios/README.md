# Módulo 2 — Inventarios

## App oficial (la que va a GitHub y Render)

| Qué | Dónde |
|-----|--------|
| **Programa principal** | `modules/inventarios/inventario_app.py` |
| **Excel de datos** | `data/sources/template_inventarios.xlsx` |
| **Ejecutar en local** | `streamlit run modules/inventarios/inventario_app.py` |
| **Render** | `lri-inventarios` → mismo comando que arriba |

Archivos de soporte en esta carpeta: `data_loader.py`, `scorecard.py`,
`parametros.py`, `ui_theme.py`, assets.

## No confundir con

- **`view.py`** — solo un aviso para el orquestador `app.py`; **no** es la app de inventarios.
- **`_inbox_inventarios/`** (raíz del repo) — copia temporal del freelance; **no** se sube a GitHub (está en `.gitignore`).

## Parámetros (JSON)

| Archivo | Uso |
|---------|-----|
| `parametros_defaults.json` | Valores estándar al iniciar (versionado en git). |
| `parametros_backup.json` | Respaldo validado. |
| `parametros_guardados.json` | Últimos valores guardados en la UI (local, gitignored). |
