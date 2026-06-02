# Arquitectura

## Objetivo

Una plataforma Streamlit **modular** donde cada área de la cadena de suministro
(Perfilado, Inventarios, Pronóstico, Compras, Almacenaje, Transportes) es un
módulo independiente, desarrollado y probado por separado, e integrado sin
tocar el resto.

## Principios

1. **No romper lo que funciona.** `profile1.py` (Perfilado) queda intacto. La
   arquitectura crece *alrededor* de él; su integración al orquestador será un
   paso posterior y controlado.
2. **Bajo acoplamiento.** Los módulos no se importan entre sí. Comparten solo
   el `core/` (framework) y el `data/` (pipeline).
3. **Carga dinámica.** El orquestador descubre los módulos por el registro
   (`core/registry.py`) e importa cada uno con `importlib`. Añadir/quitar un
   módulo no requiere tocar `app.py`.
4. **Preparado para roles.** Cada módulo declara qué roles pueden verlo; el
   login (cuando se implemente) filtra el menú según el rol del usuario.

## Capas

```
┌─────────────────────────────────────────────┐
│  app.py  (orquestador: login + router)        │
├─────────────────────────────────────────────┤
│  modules/*  (UI por módulo: view.render())    │
├─────────────────────────────────────────────┤
│  core/*  (settings, registry, auth, ui)       │
├─────────────────────────────────────────────┤
│  data/*  (loaders, transform — pipeline)      │
└─────────────────────────────────────────────┘
```

- **core/settings.py** — rutas y constantes (logo, datos, título). Evita
  rutas frágiles basadas en `__file__` dentro de cada módulo.
- **core/registry.py** — fuente de verdad de qué módulos existen, su orden,
  etiqueta, ruta de import, roles y si están `disponible`.
- **core/auth.py** — `login()` y `puede_acceder()`. Hoy devuelve un admin por
  defecto; se reemplazará por un login real con base de usuarios.
- **core/ui.py** — cabecera y helpers visuales compartidos.
- **data/** — lectura y transformación de datos, desacopladas de la UI para
  reutilizarlas en varios módulos.

## Contrato de un módulo

Cada módulo vive en `modules/<clave>/` y **debe** exponer en `view.py`:

```python
def render() -> None:
    ...  # dibuja la UI del módulo con Streamlit
```

Opcionalmente puede separar su lógica en archivos internos
(`logic.py`, `charts.py`, etc.) que solo `view.py` consume.

## Flujo de integración de Perfilado (futuro)

1. Extraer la lógica de `profile1.py` a `modules/perfilado/` en
   `logic.py` / `charts.py` / `voice.py`, dejando `view.render()` como
   entrada.
2. Resolver rutas (logo, datos) vía `core/settings.py`.
3. Resolver `st.set_page_config` solo en `app.py` (un único punto).
4. Acotar el CSS de Perfilado a su panel para no afectar a otros módulos.
5. Marcar `disponible=True` y cambiar el `startCommand` de Render a `app.py`.

Hasta entonces, Perfilado se despliega como `profile1.py` sin cambios.
