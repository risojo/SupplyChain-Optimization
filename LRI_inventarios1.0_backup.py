import os

import matplotlib.pyplot as plt
import streamlit as st
import pandas as pd
import numpy as np

# Configuración de la página
st.set_page_config(page_title="Sistema de Info Logistica -  LRI", layout="wide")

# Gráfico demanda mes 1–12: ~mitad de tamaño (pulgadas) que (10, 3.8); se muestra en media columna
LRI_GRAF_TEND_FIGSIZE = (5.0, 1.9)
LRI_BUSQUEDA_MAX_WIDTH_PX = 400

# Cambiar fondo a negro y estilos de botones
st.markdown(
    """
    <style>
    /* Estilos generales */
    .stApp {
        background-color: black;
        color: white;
        padding-top: 0 !important;
    }
    
    /* Eliminar espacio superior */
    .main .block-container {
        padding-top: 0rem !important;
        padding-bottom: 0rem !important;
        margin-top: -1rem !important;
    }
    
    /* Ocultar header de Streamlit definitivamente */
    header[data-testid="stHeader"] {
        display: none !important;
    }
    div[data-testid="stToolbar"] {
        display: none !important;
    }
    div[data-testid="stDecoration"] {
        display: none !important;
    }
    #MainMenu {
        visibility: hidden !important;
    }
    footer {
        visibility: hidden !important;
    }
    
    /* Títulos pegados arriba */
    h1, h2, h3 {
        margin-top: 0 !important;
        padding-top: 0 !important;
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        background-color: black !important;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: black !important;
        color: white !important;
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        background-color: #111111 !important;
        color: white !important;
    }
    
    /* Radio buttons del sidebar */
    .stRadio [data-baseweb="radio"] {
        color: white;
    }
    
    /* Sidebar */
    .stSidebar {
        background-color: #8B0000 !important;
        color: white !important;
    }
    .stSidebar * {
        color: white !important;
    }
    
    /* ===== TABLAS - ESTILO VERDE TERMINAL ===== */
    /* Todas las celdas de DataFrame */
    .stDataFrame td, 
    div[data-testid="stDataFrame"] td,
    .stDataFrameResizable div[data-testid="stDataFrameCell"] {
        background-color: #000000 !important;
        color: #00FF00 !important;
        font-family: 'Courier New', monospace !important;
        border: 1px solid #003300 !important;
    }
    
    /* Encabezados de tabla */
    .stDataFrame th,
    div[data-testid="stDataFrame"] th,
    .stDataFrameResizable div[data-testid="stDataFrameCellHeader"] {
        background-color: #000000 !important;
        color: #00FF00 !important;
        font-family: 'Courier New', monospace !important;
        border: 1px solid #00FF00 !important;
        font-weight: bold !important;
    }
    
    /* Contenedor del DataFrame */
    .stDataFrame div[data-testid="stDataFrameResizable"],
    div[data-testid="stDataFrame"] {
        border: 1px solid #00FF00 !important;
        background-color: #000000 !important;
    }
    
    /* ===== ESTILOS PARA SIDEBAR ===== */
    
    /* Títulos de capítulos - estáticos con markdown */
    .sidebar-title {
        background-color: #000000 !important;
        color: white !important;
        padding: 10px 12px;
        font-weight: bold;
        font-size: 20px;
        border-radius: 4px;
        margin-top: 0 !important;
        margin-bottom: 6px;
        display: block;
        width: 100%;
        text-align: center !important;
    }
    
    /* Botones del sidebar - opciones en una línea */
    .stSidebar [data-testid="stButton"] button {
        background-color: #8B0000 !important;
        color: white !important;
        border-radius: 6px;
        padding: 6px 10px !important;
        margin: 3px 0;
        border: 2px solid #5a0000 !important;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
        transition: all 0.3s ease;
        font-size: 11px !important;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        width: 100%;
        text-align: left;
    }
    
    /* Hover - aclarar fondo */
    .stSidebar [data-testid="stButton"] button:hover {
        background-color: #A52A2A !important;
        border-color: #FF6B35 !important;
        box-shadow: 0 3px 6px rgba(255, 107, 53, 0.4);
    }
    
    /* Botón seleccionado - diferente color */
    .stSidebar [data-testid="stButton"] button[kind="secondary"]:focus {
        background-color: #FF6B35 !important;
        border-color: #FF6B35 !important;
    }
    
    /* Estilo general para botones de Streamlit */
    .stButton > button {
        background-color: #2D2D2D !important;
        color: white !important;
        border: 1px solid #555555 !important;
        border-radius: 6px;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        background-color: #3D3D3D !important;
        border-color: #FF6B35 !important;
        box-shadow: 0 2px 8px rgba(255, 107, 53, 0.3);
    }
    /* Formulario de búsqueda: inputs más cortos y alineados */
    .main [class*="st-key-tend_search_form"] {
        --lri-search-max: 400px;
    }
    .main [class*="st-key-tend_search_form"] .stSelectbox,
    .main [class*="st-key-tend_search_form"] [data-testid="element-container"]:has(.stSelectbox) {
        width: var(--lri-search-max) !important;
        max-width: var(--lri-search-max) !important;
        min-width: 0 !important;
        box-sizing: border-box !important;
    }
    .main [class*="st-key-tend_search_form"] [data-testid="element-container"] {
        width: var(--lri-search-max) !important;
        max-width: var(--lri-search-max) !important;
    }
    .main [class*="st-key-tend_search_form"] [data-baseweb="select"],
    .main [class*="st-key-tend_search_form"] [data-baseweb="select"] > div {
        width: 100% !important;
        max-width: 100% !important;
        box-sizing: border-box !important;
    }
    .main [class*="st-key-tend_search_form"] [data-testid="stVerticalBlock"] {
        gap: 0.25rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)
if 'datos_pronostico' not in st.session_state:
    st.session_state.datos_pronostico = {}
if 'datos_inventarios' not in st.session_state:
    st.session_state.datos_inventarios = {}
if 'datos_compras' not in st.session_state:
    st.session_state.datos_compras = {}
if 'datos_almacenaje' not in st.session_state:
    st.session_state.datos_almacenaje = {}

# Función principal
def main():
    st.title("Sistema de Información de Logística LRI")
    st.write("Selecciona el capítulo en la barra superior y luego elige la opción en el sidebar.")

    tab1, tab2, tab3, tab4 = st.tabs(["Pronóstico", "Inventarios", "Compras", "Almacenaje"])

    with tab1:
        pronostico()
    with tab2:
        inventarios()
    with tab3:
        compras()
    with tab4:
        almacenaje()

# Capítulo 1: Pronóstico
def pronostico():
    """
    Capítulo: Pronóstico
    Este capítulo se enfoca en predecir la demanda futura.
    """
    st.header("Capítulo: Pronóstico")
    st.write("Descripción: Este capítulo maneja el pronóstico de demanda.")

    # Título estático del sidebar
    st.sidebar.markdown('<p class="sidebar-title">Pronóstico</p>', unsafe_allow_html=True)
    
    # Botones individuales para cada opción
    if st.sidebar.button("Opción 1: Lectura de archivo data", key="btn_op1_pronostico"):
        st.session_state.pronostico_seleccion = "Opción 1: Lectura de archivo data"
    
    if st.sidebar.button("Opción 2: Grafico de tendencia", key="btn_op2_pronostico"):
        st.session_state.pronostico_seleccion = "Opción 2: Grafico de tendencia"
    
    if st.sidebar.button("Opción 3: Pronóstico estacional", key="btn_op3_pronostico"):
        st.session_state.pronostico_seleccion = "Opción 3: Pronóstico estacional"
    
    if st.sidebar.button("Opción 4: Simulación Monte Carlo", key="btn_op4_pronostico"):
        st.session_state.pronostico_seleccion = "Opción 4: Simulación Monte Carlo"
    
    if st.sidebar.button("Opción 5: Validación y ajuste", key="btn_op5_pronostico"):
        st.session_state.pronostico_seleccion = "Opción 5: Validación y ajuste"

    # Obtener la selección actual
    opcion = st.session_state.get('pronostico_seleccion', None)

    # Solo mostrar contenido cuando una opción esté seleccionada
    if opcion == "Opción 1: Lectura de archivo data":
        pronostico_opcion1()
    elif opcion == "Opción 2: Grafico de tendencia":
        pronostico_opcion2()
    elif opcion == "Opción 3: Pronóstico estacional":
        pronostico_opcion3()
    elif opcion == "Opción 4: Simulación Monte Carlo":
        pronostico_opcion4()
    elif opcion == "Opción 5: Validación y ajuste":
        pronostico_opcion5()
    else:
        st.info("Selecciona una opción del menú lateral.")

def pronostico_opcion1():
    st.subheader("Opción 1: Lectura de archivo data")
    # Leer archivo Excel ubicado en la misma carpeta del script.
    # En algunos entornos interactivos __file__ puede no estar disponible.
    base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
    archivo_path = os.path.join(base_dir, "archivo2.xlsx")
    
    if not os.path.exists(archivo_path):
        st.error(f"No se encontró el archivo Excel esperado: {archivo_path}")
        return
    
    try:
        # Leer archivo Excel con pandas
        df = pd.read_excel(archivo_path)
        st.markdown("<h3 style='color:#00FF00;'>Datos del archivo</h3>", unsafe_allow_html=True)
        # Convertir todas las columnas object a string para evitar error de Arrow
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str)
        # Render HTML para asegurar estilo fijo en encabezados y numeración de filas.
        tabla_html = df.to_html(index=True, classes="tabla-terminal")
        st.markdown(
            """
            <style>
            .tabla-terminal, .tabla-terminal * {
                background-color: #000000 !important;
                color: #00FF00 !important;
                font-family: "Courier New", monospace !important;
            }
            .tabla-terminal {
                border-collapse: collapse !important;
                width: 100% !important;
            }
            .tabla-terminal th,
            .tabla-terminal td {
                border: 1px solid #003300 !important;
                padding: 6px 10px !important;
                text-align: left !important;
                white-space: nowrap !important;
            }
            </style>
            """,
            unsafe_allow_html=True
        )
        st.markdown(tabla_html, unsafe_allow_html=True)
        # Guardar con la clave usada por las otras opciones del flujo.
        st.session_state.datos_pronostico['tendencias'] = df
    except Exception as e:
        st.error(f"Error al leer el archivo: {e}")


def _ruta_archivo_pronostico():
    base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
    return os.path.join(base_dir, "archivo2.xlsx")


def _cargar_dataframe_tendencias():
    if st.session_state.datos_pronostico.get("tendencias") is not None:
        return st.session_state.datos_pronostico["tendencias"].copy()
    p = _ruta_archivo_pronostico()
    if not os.path.exists(p):
        return None
    return pd.read_excel(p)


def _grafico_barras_tendencia_demanda(mes_labels, demandas, titulo=""):
    """Barras color celeste, figura y ejes con fondo negro. Tamaño compacto (mitad del diseño base)."""
    n = len(mes_labels)
    x = range(n)
    y_max = max(demandas) if demandas and max(demandas) > 0 else 1
    fig, ax = plt.subplots(
        figsize=LRI_GRAF_TEND_FIGSIZE, facecolor="black", dpi=110
    )
    fig.patch.set_facecolor("black")
    ax.set_facecolor("black")
    color_barra = "#5DADE2"
    ax.bar(
        x,
        demandas,
        color=color_barra,
        edgecolor="#3D8AB8",
        linewidth=0.35,
    )
    ax.set_xticks(list(x))
    ax.set_xticklabels(mes_labels, color="white", fontsize=7)
    ax.tick_params(axis="y", colors="white", labelsize=7)
    ax.set_ylabel("Demanda", color="white", fontsize=8)
    if titulo:
        ax.set_title(titulo, color="white", fontsize=8, pad=4)
    for s in ax.spines.values():
        s.set_color("#333333")
    ax.grid(True, axis="y", color="#2a2a2a", linestyle="--", alpha=0.8)
    y_pad = max(y_max * 0.02, 0.5)
    for i, v in enumerate(demandas):
        ax.text(
            i,
            v + y_pad,
            str(int(v)),
            ha="center",
            va="bottom",
            color="white",
            fontsize=6,
            fontweight="bold",
        )
    ax.set_ylim(0, (y_max + y_pad) * 1.08 if y_max else 1)
    fig.tight_layout()
    col_g, _ = st.columns([1, 1])
    with col_g:
        st.pyplot(fig, width="stretch")
    plt.close(fig)


def pronostico_opcion2():
    st.subheader("Opción 2: Gráfico de tendencia")
    st.caption(
        "Demanda de cada mes (demanda_mes1 … demanda_mes12) por artículo. "
        "Elija el artículo por código, categoría o subcategoría. "
        "Use la Opción 1 para cargar datos, o deje archivo2.xlsx en la carpeta del programa."
    )
    data = _cargar_dataframe_tendencias()
    if data is None or data.empty:
        st.info("Cargue los datos con la Opción 1 o coloque el archivo archivo2.xlsx en la misma carpeta del script.")
        return

    data = data.copy()
    data.columns = [str(c).strip() for c in data.columns]
    cols_dem = [f"demanda_mes{i}" for i in range(1, 13)]
    faltan = [c for c in cols_dem if c not in data.columns]
    if faltan:
        st.error("Faltan columnas requeridas: " + ", ".join(faltan))
        st.write("Columnas actuales:", list(data.columns))
        return

    for c in cols_dem:
        data[c] = pd.to_numeric(data[c], errors="coerce")

    mes_labels = [f"Mes {i}" for i in range(1, 13)]

    with st.container(key="tend_search_form"):
        if "cod_producto" not in data.columns:
            st.warning("No hay columna cod_producto; elija la fila por posición.")
            idx = st.selectbox(
                "Fila (índice 0 a N-1)",
                list(range(len(data))),
                key="graf_tendencia_idx",
                width=LRI_BUSQUEDA_MAX_WIDTH_PX,
            )
            fila = data.iloc[idx]
            titulo = f"Tendencia de demanda — fila {idx}"
        else:
            data = data.dropna(subset=["cod_producto"])
            if data.empty:
                st.warning("No hay filas con cod_producto.")
                return

            modo = st.selectbox(
                "Buscar artículo por",
                (
                    "Código de producto",
                    "Categoría",
                    "Subcategoría",
                ),
                key="graf_tendencia_modo",
                width=LRI_BUSQUEDA_MAX_WIDTH_PX,
            )

            if modo == "Código de producto":
                cods = sorted({str(x) for x in data["cod_producto"]}, key=str)
                if not cods:
                    st.warning("No hay códigos de producto en los datos.")
                    return
                cod_sel = st.selectbox(
                    "Código de producto",
                    cods,
                    key="graf_tendencia_cod",
                    width=LRI_BUSQUEDA_MAX_WIDTH_PX,
                )
                filas = data[data["cod_producto"].astype(str) == str(cod_sel)]
                if filas.empty:
                    st.error("No se encontró el artículo.")
                    return
                if len(filas) > 1:
                    st.caption("Varias filas con el mismo código; se usa la primera.")
                fila = filas.iloc[0]
                titulo = f"Tendencia — código {cod_sel}"

            elif modo == "Categoría":
                if "cat_producto" not in data.columns:
                    st.error("Falta la columna cat_producto para buscar por categoría.")
                    return
                cats = (
                    data["cat_producto"]
                    .dropna()
                    .astype(str)
                    .drop_duplicates()
                    .sort_values()
                    .tolist()
                )
                if not cats:
                    st.warning("No hay categorías en los datos.")
                    return
                cat_sel = st.selectbox(
                    "Categoría",
                    cats,
                    key="graf_tendencia_cat",
                    width=LRI_BUSQUEDA_MAX_WIDTH_PX,
                )
                sub = data[data["cat_producto"].astype(str) == str(cat_sel)]
                if sub.empty:
                    st.warning("No hay artículos en esta categoría.")
                    return

                def _etiqueta_art_cat(i):
                    r = sub.iloc[i]
                    if "desc_producto" in sub.columns:
                        return f"{r['cod_producto']} — {str(r['desc_producto'])[:64]}"
                    return str(r["cod_producto"])

                idx = st.selectbox(
                    "Artículo",
                    list(range(len(sub))),
                    format_func=_etiqueta_art_cat,
                    key="graf_tendencia_cat_item",
                    width=LRI_BUSQUEDA_MAX_WIDTH_PX,
                )
                fila = sub.iloc[idx]
                titulo = f"Tendencia — cat. {cat_sel} — {fila['cod_producto']}"

            else:
                if "subcat_producto" not in data.columns:
                    st.error("Falta la columna subcat_producto para buscar por subcategoría.")
                    return
                subs = (
                    data["subcat_producto"]
                    .dropna()
                    .astype(str)
                    .drop_duplicates()
                    .sort_values()
                    .tolist()
                )
                if not subs:
                    st.warning("No hay subcategorías en los datos.")
                    return
                subcat_sel = st.selectbox(
                    "Subcategoría",
                    subs,
                    key="graf_tendencia_sub",
                    width=LRI_BUSQUEDA_MAX_WIDTH_PX,
                )
                sub = data[data["subcat_producto"].astype(str) == str(subcat_sel)]
                if sub.empty:
                    st.warning("No hay artículos en esta subcategoría.")
                    return

                def _etiqueta_art_sub(i):
                    r = sub.iloc[i]
                    if "desc_producto" in sub.columns:
                        return f"{r['cod_producto']} — {str(r['desc_producto'])[:64]}"
                    return str(r["cod_producto"])

                idx = st.selectbox(
                    "Artículo",
                    list(range(len(sub))),
                    format_func=_etiqueta_art_sub,
                    key="graf_tendencia_sub_item",
                    width=LRI_BUSQUEDA_MAX_WIDTH_PX,
                )
                fila = sub.iloc[idx]
                titulo = f"Tendencia — subcat. {subcat_sel} — {fila['cod_producto']}"

    demandas = []
    for c in cols_dem:
        v = fila.get(c)
        if pd.isna(v):
            demandas.append(0)
        else:
            demandas.append(int(round(float(v))))

    st.subheader("Demanda mensual (12 meses)")
    _grafico_barras_tendencia_demanda(mes_labels, demandas, titulo)

def pronostico_opcion3():
    st.subheader("Opción 3: Pronóstico estacional")
    # Algoritmo placeholder
    st.write("Algoritmo: Detectar patrones estacionales.")

def pronostico_opcion4():
    st.subheader("Opción 4: Simulación Monte Carlo")
    # Algoritmo placeholder
    st.write("Algoritmo: Simular escenarios de demanda.")

def pronostico_opcion5():
    st.subheader("Opción 5: Validación y ajuste")
    # Algoritmo placeholder
    st.write("Algoritmo: Validar modelos y ajustar parámetros.")

# Capítulo 2: Inventarios
def inventarios():
    """
    Capítulo: Inventarios
    Gestiona los niveles de inventario basados en pronósticos.
    """
    st.header("Capítulo: Inventarios")
    st.write("Descripción: Gestión de inventarios.")

    # Título estático del sidebar
    st.sidebar.markdown('<p class="sidebar-title">Inventarios</p>', unsafe_allow_html=True)
    
    # Botones individuales para cada opción
    if st.sidebar.button("Opción 1: Punto de reorden", key="btn_op1_inventarios"):
        st.session_state.inventarios_seleccion = "Opción 1: Punto de reorden"
    
    if st.sidebar.button("Opción 2: Stock mínimo", key="btn_op2_inventarios"):
        st.session_state.inventarios_seleccion = "Opción 2: Stock mínimo"
    
    if st.sidebar.button("Opción 3: Rotación", key="btn_op3_inventarios"):
        st.session_state.inventarios_seleccion = "Opción 3: Rotación"
    
    if st.sidebar.button("Opción 4: Optimización", key="btn_op4_inventarios"):
        st.session_state.inventarios_seleccion = "Opción 4: Optimización"
    
    if st.sidebar.button("Opción 5: Reportes", key="btn_op5_inventarios"):
        st.session_state.inventarios_seleccion = "Opción 5: Reportes"

    # Obtener la selección actual
    opcion = st.session_state.get('inventarios_seleccion', None)

    if opcion == "Opción 1: Punto de reorden":
        inventarios_opcion1()
    elif opcion == "Opción 2: Stock mínimo":
        inventarios_opcion2()
    elif opcion == "Opción 3: Rotación":
        inventarios_opcion3()
    elif opcion == "Opción 4: Optimización":
        inventarios_opcion4()
    elif opcion == "Opción 5: Reportes":
        inventarios_opcion5()
    else:
        st.info("Selecciona una opción del menú lateral.")

def inventarios_opcion1():
    st.subheader("Opción 1: Cálculo de punto de reorden")
    # Usar datos de pronóstico
    if 'tendencias' in st.session_state.datos_pronostico:
        demanda_promedio = st.session_state.datos_pronostico['tendencias']['Demanda'].mean()
        st.write(f"Demanda promedio: {demanda_promedio}")
        # Algoritmo: Punto de reorden = demanda * tiempo de entrega
        tiempo_entrega = st.number_input("Tiempo de entrega (días)", value=7)
        punto_reorden = demanda_promedio * tiempo_entrega / 30  # mensual approx
        st.write(f"Punto de reorden: {punto_reorden}")
        st.session_state.datos_inventarios['punto_reorden'] = punto_reorden
    else:
        st.write("Requiere datos de Pronóstico.")

# Agregar funciones similares para otras opciones y capítulos
# Por brevedad, placeholders para los demás

def inventarios_opcion2():
    st.subheader("Opción 2: Gestión de stock mínimo")
    st.write("Algoritmo placeholder.")

def inventarios_opcion3():
    st.subheader("Opción 3: Análisis de rotación")
    st.write("Algoritmo placeholder.")

def inventarios_opcion4():
    st.subheader("Opción 4: Optimización")
    st.write("Algoritmo placeholder.")

def inventarios_opcion5():
    st.subheader("Opción 5: Reportes")
    st.write("Algoritmo placeholder.")

# Capítulo 3: Compras
def compras():
    """
    Capítulo: Compras
    Maneja las órdenes de compra basadas en inventarios.
    """
    st.header("Capítulo: Compras")
    st.write("Descripción: Gestión de compras.")

    # Título estático del sidebar
    st.sidebar.markdown('<p class="sidebar-title">Compras</p>', unsafe_allow_html=True)
    
    # Botones individuales para cada opción
    if st.sidebar.button("Opción 1: Órdenes de compra", key="btn_op1_compras"):
        st.session_state.compras_seleccion = "Opción 1: Órdenes de compra"
    
    if st.sidebar.button("Opción 2: Proveedores", key="btn_op2_compras"):
        st.session_state.compras_seleccion = "Opción 2: Proveedores"
    
    if st.sidebar.button("Opción 3: Precios", key="btn_op3_compras"):
        st.session_state.compras_seleccion = "Opción 3: Precios"
    
    if st.sidebar.button("Opción 4: Entregas", key="btn_op4_compras"):
        st.session_state.compras_seleccion = "Opción 4: Entregas"
    
    if st.sidebar.button("Opción 5: Seguimiento", key="btn_op5_compras"):
        st.session_state.compras_seleccion = "Opción 5: Seguimiento"

    # Obtener la selección actual
    opcion = st.session_state.get('compras_seleccion', None)

    if opcion == "Opción 1: Órdenes de compra":
        compras_opcion1()
    elif opcion == "Opción 2: Proveedores":
        compras_opcion2()
    elif opcion == "Opción 3: Precios":
        compras_opcion3()
    elif opcion == "Opción 4: Entregas":
        compras_opcion4()
    elif opcion == "Opción 5: Seguimiento":
        compras_opcion5()
    else:
        st.info("Selecciona una opción del menú lateral.")

def compras_opcion1():
    st.subheader("Opción 1: Generar órdenes de compra")
    if 'punto_reorden' in st.session_state.datos_inventarios:
        st.write(f"Basado en punto de reorden: {st.session_state.datos_inventarios['punto_reorden']}")
        # Algoritmo placeholder
    else:
        st.write("Requiere datos de Inventarios.")

def compras_opcion2():
    st.subheader("Opción 2: Evaluación de proveedores")
    st.write("Algoritmo placeholder.")

def compras_opcion3():
    st.subheader("Opción 3: Negociación de precios")
    st.write("Algoritmo placeholder.")

def compras_opcion4():
    st.subheader("Opción 4: Programación de entregas")
    st.write("Algoritmo placeholder.")

def compras_opcion5():
    st.subheader("Opción 5: Seguimiento de pedidos")
    st.write("Algoritmo placeholder.")

# Funciones para Almacenaje
def almacenaje_opcion1():
    st.subheader("Opción 1: Diseño de layout")
    st.write("Algoritmo placeholder.")

def almacenaje_opcion2():
    st.subheader("Opción 2: Control de calidad")
    st.write("Algoritmo placeholder.")

def almacenaje_opcion3():
    st.subheader("Opción 3: Gestión de espacios")
    st.write("Algoritmo placeholder.")

def almacenaje_opcion4():
    st.subheader("Opción 4: Logística de salida")
    st.write("Algoritmo placeholder.")

def almacenaje_opcion5():
    st.subheader("Opción 5: Reportes de almacén")
    st.write("Algoritmo placeholder.")

# Capítulo 4: Almacenaje
def almacenaje():
    """
    Capítulo: Almacenaje
    Gestiona el almacenamiento y distribución.
    """
    st.header("Capítulo: Almacenaje")
    st.write("Descripción: Gestión de almacén.")

    # Título estático del sidebar
    st.sidebar.markdown('<p class="sidebar-title">Almacenaje</p>', unsafe_allow_html=True)
    
    # Botones individuales para cada opción
    if st.sidebar.button("Opción 1: Layout", key="btn_op1_almacenaje"):
        st.session_state.almacenaje_seleccion = "Opción 1: Layout"
    
    if st.sidebar.button("Opción 2: Calidad", key="btn_op2_almacenaje"):
        st.session_state.almacenaje_seleccion = "Opción 2: Calidad"
    
    if st.sidebar.button("Opción 3: Espacios", key="btn_op3_almacenaje"):
        st.session_state.almacenaje_seleccion = "Opción 3: Espacios"
    
    if st.sidebar.button("Opción 4: Logística", key="btn_op4_almacenaje"):
        st.session_state.almacenaje_seleccion = "Opción 4: Logística"
    
    if st.sidebar.button("Opción 5: Reportes", key="btn_op5_almacenaje"):
        st.session_state.almacenaje_seleccion = "Opción 5: Reportes"

    # Obtener la selección actual
    opcion = st.session_state.get('almacenaje_seleccion', None)

    if opcion == "Opción 1: Layout":
        almacenaje_opcion1()
    elif opcion == "Opción 2: Calidad":
        almacenaje_opcion2()
    elif opcion == "Opción 3: Espacios":
        almacenaje_opcion3()
    elif opcion == "Opción 4: Logística":
        almacenaje_opcion4()
    elif opcion == "Opción 5: Reportes":
        almacenaje_opcion5()
    else:
        st.info("Selecciona una opción del menú lateral.")

if __name__ == "__main__":
    main()