# LRI Supply Chain Optimization

Plataforma modular de optimización de cadena de suministro (Streamlit).

La aplicación se organiza en **módulos independientes** que el orquestador
(`app.py`) carga de forma dinámica. Cada módulo se desarrolla por separado y se
"enchufa" mediante el registro central, dejando todo listo para login y
control de acceso por roles.

## Módulos

| # | Módulo | Estado |
|---|--------|--------|
| 1 | Perfilado (Profile) | ✅ Operativo (`modules/perfilado/profile1.py`) |
| 2 | Inventarios | ✅ Operativo (`modules/inventarios/inventario_app.py`) |
| 3 | Pronóstico | 🚧 En construcción |
| 4 | Compras | 🚧 En construcción |
| 5 | Almacenaje | 🚧 En construcción |
| 6 | Transportes | 🚧 En construcción |

## Estructura

```
.
├── app.py                  # Orquestador: login + roles + router de módulos
├── core/                   # Framework compartido
│   ├── settings.py         # Rutas y constantes centrales
│   ├── registry.py         # Registro de módulos (clave, etiqueta, roles)
│   ├── auth.py             # Login + control de acceso por roles
│   └── ui.py               # Cabecera y helpers visuales
├── data/                   # Capa de datos compartida (separada de la UI)
│   ├── loaders.py          # "El mostrador": obtener_datos() — Excel hoy, SQL mañana
│   ├── transform.py        # Transformaciones y métricas
│   └── sources/            # Una base por módulo (perfilado.xlsx, ...)
├── modules/                # Los 6 módulos (cada uno con view.py -> render())
│   ├── perfilado/          # incluye profile1.py (app operativa)
│   ├── inventarios/
│   ├── pronostico/
│   ├── compras/
│   ├── almacenaje/
│   └── transportes/
├── assets/                 # Logo, imágenes (compartidos)
├── .streamlit/             # Configuración de Streamlit
├── requirements.txt
├── runtime.txt             # Versión de Python (Render)
└── render.yaml             # Despliegue en Render
```

## Ejecutar en local

```bash
# Módulo Perfilado (producción)
streamlit run modules/perfilado/profile1.py

# Módulo Inventarios (producción)
streamlit run modules/inventarios/inventario_app.py

# Orquestador modular (armazón con todos los módulos)
streamlit run app.py
```

## Cómo añadir un módulo nuevo

1. Crea `modules/<clave>/view.py` con una función `render()`.
2. Marca `disponible=True` en la entrada del módulo en `core/registry.py`.
3. El orquestador lo mostrará automáticamente en su pestaña.

Ver detalles en [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md).

## Despliegue (Render)

Hay **dos apps** en `render.yaml`:

| Servicio | Módulo | Comando |
|----------|--------|---------|
| `lri-supply-chain-optimization` | Perfilado | `streamlit run modules/perfilado/profile1.py` |
| `lri-inventarios` | Inventarios | `streamlit run modules/inventarios/inventario_app.py` |

**Subir a GitHub no basta:** hay que crear o sincronizar el Blueprint en Render.
Instrucciones paso a paso: [`docs/DEPLOY_RENDER.md`](docs/DEPLOY_RENDER.md).

```bash
streamlit run modules/inventarios/inventario_app.py
```
