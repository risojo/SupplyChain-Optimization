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

El perfilado abre con el número de clientes por distrito: el grupo de la barra es el distrito y la variable es **Clientes** (cuenta códigos). Distrito no es una variable numérica. **Todos** en el nombre incluye todos los distritos; un distrito elegido baja a sus clientes. Cantón agrupa por cantón. Hay hasta tres variables, en una sola vista, de mayor a menor. Las demás variables se suman o se promedian. Un TVA negativo se dibuja hacia abajo. Los valores van sobre la barra y, si se pegarían, giran en vertical. Dos controles ajustan el tamaño de esos números y la altura del eje Y. El gráfico tiene su propia barra vertical para subir y bajar; la rueda del mouse no mueve las barras. A la derecha se puede marcar una zona y volver al tamaño original. El mapa de Cluster es más alto. El mapa de abajo muestra solo esos clientes, por zonas de color o por puntos de tonalidades bien separadas. El centro de distribución (latitud 9.968705177, longitud -84.13418) sale en los mapas como un triángulo rojo con borde negro, más grande que los clientes: de ahí salen las rutas. La tabla completa del Excel está en Base de datos.

## Estado

Menú operativo. Cluster y el diseño de rutas nuevas quedan para el siguiente paso;
hoy Cluster arma segmentos de 15 a 25 clientes por cercanía. Cada segmento sale del centro de distribución con una línea punteada negra hasta su cliente más cercano. Rutas muestra las rutas ya cargadas.
