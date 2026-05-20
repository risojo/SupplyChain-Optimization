import streamlit as st
import streamlit_authenticator as stauth

import database

# Módulos del capítulo Pronóstico
from modulos_pronostico import (
    carga_de_datos as pron_carga_datos,
    opcion2 as pron_op2,
    opcion3 as pron_op3,
    opcion4 as pron_op4,
    opcion5 as pron_op5,
    demanda as pron_demanda,
    normal as pron_normal,
)

# Módulos del capítulo Inventarios
from modulos_inventarios import (
    opcion1 as inv_op1,
    opcion2 as inv_op2,
    opcion3 as inv_op3,
    opcion4 as inv_op4,
    opcion5 as inv_op5,
)

# Módulos del capítulo Compras
from modulos_compras import (
    opcion1 as com_op1,
    opcion2 as com_op2,
    opcion3 as com_op3,
    opcion4 as com_op4,
    opcion5 as com_op5,
)

# Módulos del capítulo Almacenaje
from modulos_almacenaje import (
    opcion1 as alm_op1,
    opcion2 as alm_op2,
    opcion3 as alm_op3,
    opcion4 as alm_op4,
    opcion5 as alm_op5,
)


# Configuración de la página
st.set_page_config(page_title="Sistema de Info Logistica -  LRI", layout="wide")

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
    .stDataFrame td, 
    div[data-testid="stDataFrame"] td,
    .stDataFrameResizable div[data-testid="stDataFrameCell"] {
        background-color: #000000 !important;
        color: #00FF00 !important;
        font-family: 'Courier New', monospace !important;
        border: none !important;
    }
    .stDataFrame th,
    div[data-testid="stDataFrame"] th,
    .stDataFrameResizable div[data-testid="stDataFrameCellHeader"] {
        background-color: #000000 !important;
        color: #00FF00 !important;
        font-family: 'Courier New', monospace !important;
        border: none !important;
        font-weight: bold !important;
    }
    .stDataFrame div[data-testid="stDataFrameResizable"],
    div[data-testid="stDataFrame"] {
        border: none !important;
        outline: none !important;
        box-shadow: none !important;
        background-color: #000000 !important;
    }
    
    /* ===== ESTILOS PARA SIDEBAR ===== */
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
    .stSidebar [data-testid="stButton"] button:hover {
        background-color: #A52A2A !important;
        border-color: #FF6B35 !important;
        box-shadow: 0 3px 6px rgba(255, 107, 53, 0.4);
    }
    .stSidebar [data-testid="stButton"] button[kind="secondary"]:focus {
        background-color: #FF6B35 !important;
        border-color: #FF6B35 !important;
    }
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
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Estado compartido (cada capítulo guarda aquí lo que produce)
# ---------------------------------------------------------------------------
if "datos_pronostico" not in st.session_state:
    st.session_state.datos_pronostico = {}
if "datos_inventarios" not in st.session_state:
    st.session_state.datos_inventarios = {}
if "datos_compras" not in st.session_state:
    st.session_state.datos_compras = {}
if "datos_almacenaje" not in st.session_state:
    st.session_state.datos_almacenaje = {}


# ---------------------------------------------------------------------------
# Login (entrada del programa, fuera de los capítulos)
# ---------------------------------------------------------------------------
def _autenticar():
    """Muestra el formulario de login y devuelve (auth_status, authenticator)."""
    try:
        credentials = database.fetch_all_users()
    except Exception as e:
        st.error(f"Error en la base de datos: {e}")
        return None, None

    authenticator = stauth.Authenticate(
        credentials,
        "scorecard_software",
        "abcdef",
        cookie_expiry_days=30,
    )

    authenticator.login(location="main")
    return st.session_state.get("authentication_status"), authenticator


# ---------------------------------------------------------------------------
# Helper: pinta un capítulo con sidebar de opciones y enruta a su módulo
# ---------------------------------------------------------------------------
def _render_capitulo(titulo, descripcion, sidebar_titulo, opciones, key_seleccion, key_btn_prefix):
    """Pinta un capítulo genérico.

    ``opciones`` es una lista de tuplas (etiqueta, modulo) donde ``modulo``
    es un objeto Python con una función ``render()``.
    """
    st.header(f"Capítulo: {titulo}")
    st.write(f"Descripción: {descripcion}")

    st.sidebar.markdown(
        f'<p class="sidebar-title">{sidebar_titulo}</p>', unsafe_allow_html=True
    )

    for i, (etiqueta, _modulo) in enumerate(opciones, start=1):
        if st.sidebar.button(etiqueta, key=f"{key_btn_prefix}{i}"):
            st.session_state[key_seleccion] = etiqueta

    seleccion = st.session_state.get(key_seleccion, None)
    if seleccion is None:
        st.info("Selecciona una opción del menú lateral.")
        return

    for etiqueta, modulo in opciones:
        if seleccion == etiqueta:
            modulo.render()
            return

    st.warning(f"Opción no reconocida: {seleccion}")


# ---------------------------------------------------------------------------
# Capítulos
# ---------------------------------------------------------------------------
def pronostico():
    opciones = [
        ("Opción 1: Carga de datos", pron_carga_datos),
        ("Opción 2: Grafico de tendencia", pron_op2),
        ("Opción 3: Pronóstico estacional", pron_op3),
        ("Opción 4: Simulación Monte Carlo", pron_op4),
        ("Opción 5: Validación y ajuste", pron_op5),
        ("Opción 6: Certificación de demanda", pron_demanda),
        ("Opción 7: Distribución normal", pron_normal),
    ]
    _render_capitulo(
        titulo="Pronóstico",
        descripcion="Este capítulo maneja el pronóstico de demanda.",
        sidebar_titulo="Pronóstico",
        opciones=opciones,
        key_seleccion="pronostico_seleccion",
        key_btn_prefix="btn_op_pronostico_",
    )


def inventarios():
    opciones = [
        ("Opción 1: Punto de reorden", inv_op1),
        ("Opción 2: Stock mínimo", inv_op2),
        ("Opción 3: Rotación", inv_op3),
        ("Opción 4: Optimización", inv_op4),
        ("Opción 5: Reportes", inv_op5),
    ]
    _render_capitulo(
        titulo="Inventarios",
        descripcion="Gestión de inventarios.",
        sidebar_titulo="Inventarios",
        opciones=opciones,
        key_seleccion="inventarios_seleccion",
        key_btn_prefix="btn_op_inventarios_",
    )


def compras():
    opciones = [
        ("Opción 1: Órdenes de compra", com_op1),
        ("Opción 2: Proveedores", com_op2),
        ("Opción 3: Precios", com_op3),
        ("Opción 4: Entregas", com_op4),
        ("Opción 5: Seguimiento", com_op5),
    ]
    _render_capitulo(
        titulo="Compras",
        descripcion="Gestión de compras.",
        sidebar_titulo="Compras",
        opciones=opciones,
        key_seleccion="compras_seleccion",
        key_btn_prefix="btn_op_compras_",
    )


def almacenaje():
    opciones = [
        ("Opción 1: Layout", alm_op1),
        ("Opción 2: Calidad", alm_op2),
        ("Opción 3: Espacios", alm_op3),
        ("Opción 4: Logística", alm_op4),
        ("Opción 5: Reportes", alm_op5),
    ]
    _render_capitulo(
        titulo="Almacenaje",
        descripcion="Gestión de almacén.",
        sidebar_titulo="Almacenaje",
        opciones=opciones,
        key_seleccion="almacenaje_seleccion",
        key_btn_prefix="btn_op_almacenaje_",
    )


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------
def main():
    auth_status, authenticator = _autenticar()

    if auth_status is False:
        st.error("Usuario o contraseña incorrectos")
        return
    if auth_status is None:
        st.warning("Por favor ingresa tu usuario y contraseña")
        return

    with st.sidebar:
        st.markdown(
            f"<div style='color:white;font-weight:bold;padding:6px 0;'>"
            f"👤 {st.session_state.get('name', '')}</div>",
            unsafe_allow_html=True,
        )
        if authenticator is not None:
            authenticator.logout("Cerrar sesión", "sidebar", key="logout_lri")
        st.markdown("<hr style='border-color:#5a0000;'>", unsafe_allow_html=True)

    st.title("Sistema de Información de Logística LRI")
    st.write(
        "Selecciona el capítulo en la barra superior y luego elige la opción en el sidebar."
    )

    tab1, tab2, tab3, tab4 = st.tabs(["Pronóstico", "Inventarios", "Compras", "Almacenaje"])

    with tab1:
        pronostico()
    with tab2:
        inventarios()
    with tab3:
        compras()
    with tab4:
        almacenaje()


if __name__ == "__main__":
    main()
