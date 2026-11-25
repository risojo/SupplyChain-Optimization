# Módulo 6 — Transportes

**LRI Transportes PRO.** Gestión de transporte y distribución: perfil de clientes,
mapas, clusters y rutas por distrito o cantón.

**Entrada local:** `streamlit run modules/transportes/transportes_app.py`

## Menú (sidebar)

Misma idea que Inventory Pro: botones de acción y, debajo, el corte geográfico.

| Acción | Corte |
|--------|--------|
| Base de datos | Tabla completa de la hoja de clientes y rutas |
| Perfilado | Gráficos del perfil y, debajo, el mapa de esos clientes |
| Mapas | Distrito, Cantón, Otros. Se mantiene para el mapa de rutas |
| Cluster | Distrito o Cantón |
| Rutas | Distrito o Cantón |

## Archivos

| Archivo | Resultado |
|---------|-----------|
| `transportes_app.py` | Shell Streamlit: sidebar, título y vistas |
| `transportes_datos.py` | Lee la hoja `Template clientes y rutas` |
| `transportes_theme.css` | Paleta Premium Dark Blue (solo apariencia) |
| `view.py` | Aviso al orquestador; no es la app |

Datos: `modules/transportes/data/basedatos_ transporte.xlsx`.

Perfilado baja en escalera: provincia, cantón y distrito. Se elige el nivel, luego su nombre, y el gráfico muestra el peldaño siguiente (los cantones o los distritos de esa provincia; los distritos de ese cantón). El nombre del cliente aparece solo cuando ya hay un distrito. Hay hasta tres variables, en una sola vista, de mayor a menor. **Clientes** cuenta códigos. Las demás se suman o se promedian. Un TVA negativo se dibuja hacia abajo. El mapa de abajo muestra solo esos clientes. Se puede ver por zonas de color, como hasta ahora, o solo por puntos de tonalidades bien separadas. La tabla completa del Excel está en Base de datos.

## Estado

Menú operativo. Cluster y el diseño de rutas nuevas quedan para el siguiente paso;
hoy Cluster resume clientes por el corte y Rutas muestra las rutas ya cargadas.
