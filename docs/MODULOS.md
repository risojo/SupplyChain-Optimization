# Módulos LRI — Supply Chain Optimization

Orden de negocio acordado para el desarrollo de la plataforma.
**Pronóstico es el módulo 1 (de inicio):** es el primero que se abre. Los demás se
habilitan después, en el orden que defina el usuario.

| # | Módulo | Carpeta | App / entrada | Estado |
|---|--------|---------|---------------|--------|
| 1 | **Pronóstico** | `modules/pronostico/` | **`pronostico_app.py`** | En desarrollo (activo) |
| 2 | **Almacenaje** | `modules/almacenaje/` | `view.py` (esqueleto) | En construcción |
| 3 | **Compras** | `modules/compras/` | `view.py` (esqueleto) | En construcción |
| 4 | **Inventarios** | `modules/inventarios/` | **`inventario_app.py`** | En desarrollo (activo) |
| 5 | **Perfilado** | `modules/perfilado/` | **`profile1.py`** | Terminado / operativo |
| 6 | **Transportes** | `modules/transportes/` | `view.py` (esqueleto) | Pendiente (último) |

## Datos (`data/sources/`)

Pronóstico, Inventarios, Compras y Perfilado leen el **mismo archivo compartido**:
`perfilado.xlsx` (hojas `data` + `parametros`). `inventarios.xlsx` es una copia idéntica.

| Archivo | Uso |
|---------|-----|
| `perfilado.xlsx` | Archivo compartido ✅ |
| `template_inventarios.xlsx` | Plantilla demo de Inventarios |
| `pronostico.xlsx` | *(futuro)* Archivo de resultados que llenarán los cálculos de Pronóstico |

## Ejecutar en local (apps operativas)

```bash
streamlit run modules/pronostico/pronostico_app.py
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
