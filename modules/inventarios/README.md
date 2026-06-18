# Módulo 2 — Inventarios

Gestión y optimización de inventarios: punto de reorden, stock de seguridad,
rotación, EOQ, clasificación ABC, reportes.

## Parámetros (JSON en esta carpeta)

| Archivo | Uso |
|---------|-----|
| `parametros_defaults.json` | Valores estándar al iniciar (versionado en git). |
| `parametros_backup.json` | Respaldo validado; restaurar copiando a defaults o guardados. |
| `parametros_guardados.json` | Últimos valores del botón «Guardar parámetros» (local, gitignored). |

## Estado

En construcción. Coloca aquí el script del módulo y expón una función
`render()` en `view.py`; luego marca `disponible=True` en `core/registry.py`.
