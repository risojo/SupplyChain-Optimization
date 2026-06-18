# Desplegar Perfilado e Inventarios en Render

## Por qué sale «Not Found» (404)

**GitHub ≠ Render.** El código ya está en GitHub, pero la URL
`https://lri-analytics-pro.onrender.com` solo existe **después**
de crear el servicio web en [Render](https://dashboard.render.com).

Un 404 significa: **ese servicio aún no está creado** (o fue eliminado).

---

## URLs finales (cuando el deploy esté Live)

| Módulo | URL |
|--------|-----|
| **Perfilado** (`profile1.py`) | https://lri-analytics-pro.onrender.com |
| **Inventarios** (`inventario_app.py`) | https://lri-inventarios.onrender.com |

Repositorio GitHub: https://github.com/risojo/SupplyChain-Optimization

---

## Opción 1 — Blueprint (crea los dos módulos a la vez)

1. Abra: https://dashboard.render.com/blueprint/new?repo=https://github.com/risojo/SupplyChain-Optimization
2. Inicie sesión y autorice acceso a GitHub si lo pide.
3. Render mostrará 2 servicios del archivo `render.yaml`:
   - `lri-analytics-pro`
   - `lri-inventarios`
4. Pulse **Apply** (o **Create**).
5. Espere 3–8 minutos hasta que cada servicio diga **Live** (verde).

Si ya tiene un Blueprint del mismo repo: **Blueprints → su blueprint → Manual Sync**.

---

## Opción 2 — Solo Perfilado (un servicio manual)

1. https://dashboard.render.com → **New +** → **Web Service**
2. Conecte el repo **risojo/SupplyChain-Optimization**, rama **main**
3. Complete:

| Campo | Valor |
|-------|--------|
| **Name** | `lri-analytics-pro` |
| **Region** | Oregon (o la más cercana) |
| **Branch** | `main` |
| **Runtime** | Python |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | ver abajo |

**Start Command (Perfilado):**

```bash
streamlit run modules/perfilado/profile1.py --server.port $PORT --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false
```

4. En **Environment** agregue: `PYTHON_VERSION` = `3.13.4`
5. Plan **Free** → **Create Web Service**
6. Cuando diga **Live**, abra: https://lri-analytics-pro.onrender.com

Repita **New → Web Service** con name `lri-inventarios` y este Start Command para Inventarios:

```bash
streamlit run modules/inventarios/inventario_app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false
```

---

## Comprobar que funcionó

- En Render, el servicio debe estar **Live** (no Failed).
- La primera visita en plan free puede tardar ~30–60 s (arranque en frío).
- Local (misma app): `streamlit run modules/perfilado/profile1.py`

---

## Si el deploy falla (Failed en Render)

Abra **Logs** del servicio y busque el error. Causas frecuentes:

- Nombre del servicio distinto al esperado → la URL cambia (`https://<nombre>.onrender.com`).
- Rama incorrecta (debe ser `main`).
- Falta `PYTHON_VERSION=3.13.4` en variables de entorno.
