# Despliegue en Render

Subir `render.yaml` a GitHub **no crea** servicios en Render automáticamente.
Hay que **conectar el repositorio** y **sincronizar el Blueprint** (o crear el servicio manualmente).

Repositorio: https://github.com/risojo/SupplyChain-Optimization

## URLs esperadas (tras crear los servicios)

| Servicio | URL |
|----------|-----|
| Perfilado | https://lri-supply-chain-optimization.onrender.com |
| Inventarios | https://lri-inventarios.onrender.com |

Si la URL responde **404 Not Found**, el servicio **aún no existe** en Render.

---

## Opción A — Blueprint (recomendada, crea ambos módulos)

1. Entre a [Render Dashboard](https://dashboard.render.com).
2. **New → Blueprint**.
3. Conecte el repo `risojo/SupplyChain-Optimization` (rama `main`).
4. Render leerá `render.yaml` y propondrá crear:
   - `lri-supply-chain-optimization` (Perfilado)
   - `lri-inventarios` (Inventarios)
5. Confirme **Apply** / **Sync**.
6. Espere a que cada servicio termine el deploy (Build → Live).

Enlace directo para nuevo Blueprint:

https://dashboard.render.com/blueprint/new?repo=https://github.com/risojo/SupplyChain-Optimization

Si ya tiene un Blueprint del mismo repo: abra el Blueprint → **Manual Sync** (o active Auto Sync).

---

## Opción B — Solo Inventarios (servicio manual)

Si ya tiene Perfilado desplegado y solo falta Inventarios:

1. **New → Web Service**.
2. Repo: `risojo/SupplyChain-Optimization`, rama `main`.
3. **Name:** `lri-inventarios`
4. **Runtime:** Python
5. **Build command:** `pip install -r requirements.txt`
6. **Start command:**

   ```bash
   streamlit run modules/inventarios/inventario_app.py --server.port $PORT --server.address 0.0.0.0
   ```

7. **Create Web Service** y espere el deploy.

---

## Plan free

- El primer acceso tras inactividad puede tardar ~30–60 s (cold start).
- Cada módulo es un **servicio aparte** (dos URLs distintas).

## Verificación local

```bash
streamlit run modules/inventarios/inventario_app.py
```
