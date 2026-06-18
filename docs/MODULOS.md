# Módulos LRI — Supply Chain Optimization

Orden de negocio acordado para el desarrollo de la plataforma.

| # | Módulo | Carpeta | App / entrada | Estado |
|---|--------|---------|---------------|--------|
| 1 | **Almacenaje** | `modules/almacenaje/` | `view.py` (esqueleto) | En construcción |
| 2 | **Compras** | `modules/compras/` | `view.py` (esqueleto) | En construcción |
| 3 | **Inventarios** | `modules/inventarios/` | **`inventario_app.py`** | En desarrollo (activo) |
| 4 | **Perfilado** | `modules/perfilado/` | **`profile1.py`** | Terminado / operativo |
| 5 | **Pronóstico** | `modules/pronostico/` | `view.py` (esqueleto) | En construcción |
| 6 | **Transportes** | `modules/transportes/` | `view.py` (esqueleto) | Pendiente (último) |

## Datos (`data/sources/`)

| Archivo | Módulo |
|---------|--------|
| `almacenaje.xlsx` | 1. Almacenaje *(pendiente)* |
| `compras.xlsx` | 2. Compras *(pendiente)* |
| `template_inventarios.xlsx` | 3. Inventarios ✅ |
| `perfilado.xlsx` | 4. Perfilado ✅ |
| `pronostico.xlsx` | 5. Pronóstico *(pendiente)* |
| `transportes.xlsx` | 6. Transportes *(pendiente)* |

## Ejecutar en local (apps operativas)

```bash
streamlit run modules/inventarios/inventario_app.py
streamlit run modules/perfilado/profile1.py
```

## Render (solo módulos operativos hoy)

| Servicio | URL | Programa |
|----------|-----|----------|
| `lri-inventarios` | https://lri-inventarios.onrender.com | `inventario_app.py` |
| `lri-analytics-pro` | https://lri-analytics-pro.onrender.com | `profile1.py` |

Crear servicios: ver [DEPLOY_AHORA.md](../DEPLOY_AHORA.md).

## Registro central

El orquestador `app.py` usa `core/registry.py` con el mismo orden de módulos.
