# ⚠️ La URL da «Not Found» hasta que USTED cree el servicio en Render

**Git push NO crea la página web.** Render es un servicio aparte (como alquilar un local:
el mueble está en GitHub, pero hay que abrir la tienda en Render).

---

## Inventarios — 3 minutos (haga esto ahora)

### Paso 1 — Abra este enlace (iniciar sesión en Render)

👉 **https://dashboard.render.com/blueprint/new?repo=https://github.com/risojo/SupplyChain-Optimization**

### Paso 2 — Conecte GitHub

- Autorice acceso al repo `risojo/SupplyChain-Optimization`
- Rama: **main**

### Paso 3 — Aplique el Blueprint

Render leerá `render.yaml` y mostrará **2 servicios**:

| Nombre en Render | App |
|------------------|-----|
| `lri-inventarios` | `modules/inventarios/inventario_app.py` |
| `lri-supply-chain-optimization` | `modules/perfilado/profile1.py` |

Pulse **Apply** (Aplicar).

### Paso 4 — Espere «Live»

En el dashboard, servicio **lri-inventarios** → Events → cuando diga **Live** (verde).

### Paso 5 — Abra las URLs

| App | URL |
|-----|-----|
| **Inventarios** | https://lri-inventarios.onrender.com |
| **Perfilado** | https://lri-supply-chain-optimization.onrender.com |

(Primera visita en plan free: puede tardar 30–60 segundos en arrancar.)

---

## Si NO quiere Blueprint — solo Inventarios (manual)

1. https://dashboard.render.com → **New +** → **Web Service**
2. Repo: **SupplyChain-Optimization**, rama **main**
3. **Name:** `lri-inventarios` ← el nombre define la URL
4. **Build:** `pip install -r requirements.txt`
5. **Start:**

```bash
streamlit run modules/inventarios/inventario_app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false
```

6. **Environment:** `PYTHON_VERSION` = `3.13.4`
7. **Create Web Service**

---

## Comprobar en local (mismo programa que Render)

```bash
streamlit run modules/inventarios/inventario_app.py
```

---

## Si sigue en Not Found después de crear el servicio

1. En Render, ¿el servicio se llama exactamente **`lri-inventarios`**?
   - Si el nombre es otro, la URL es `https://<ese-nombre>.onrender.com`
2. ¿Estado **Failed** (rojo)? → abra **Logs** y copie el error.
3. ¿Nunca entró a dashboard.render.com? → el servicio **no existe**; la URL siempre dará 404.
