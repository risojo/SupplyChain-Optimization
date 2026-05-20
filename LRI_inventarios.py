import streamlit as st
import pandas as pd
import numpy as np

# Configuración de la página
st.set_page_config(page_title="Sistema de Inventarios LRI", layout="wide")

# Cambiar fondo a negro
st.markdown(
    """
    <style>
    .stApp {
        background-color: black;
        color: white;
    }
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
    .stRadio [data-baseweb="radio"] {
        color: white;
    }
    .stSidebar {
        background-color: #8B0000 !important;
        color: white !important;
    }
    .stSidebar * {
        color: white !important;
    }
    .stTable td, .stDataFrame td {
        background-color: black !important;
        color: #00ff00 !important;
        white-space: nowrap !important;
    }
    .stTable th, .stDataFrame th {
        background-color: #000000 !important;
        color: #ffffff !important;
    }
    /* Sidebar radio button hover */
    .stRadio > div > label:hover {
        background-color: white !important;
        color: black !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Inicializar session_state para almacenar datos entre capítulos
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
    st.title("Sistema de Inventarios LRI")
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

    opcion = st.sidebar.radio("Opciones - Pronóstico", 
                              ["Opción 1: Lectura de archivo data", 
                               "Opción 2: Modelos de regresión", 
                               "Opción 3: Pronóstico estacional", 
                               "Opción 4: Simulación Monte Carlo", 
                               "Opción 5: Validación y ajuste"],
                              key="pronostico_opcion")

    if opcion == "Opción 1: Lectura de archivo data":
        pronostico_opcion1()
    elif opcion == "Opción 2: Modelos de regresión":
        pronostico_opcion2()
    elif opcion == "Opción 3: Pronóstico estacional":
        pronostico_opcion3()
    elif opcion == "Opción 4: Simulación Monte Carlo":
        pronostico_opcion4()
    elif opcion == "Opción 5: Validación y ajuste":
        pronostico_opcion5()

def pronostico_opcion1():
    st.subheader("Opción 1: Lectura de archivo data")
    # Leer archivo Excel "archivo1.xlsx" ubicado en la carpeta inventarios con pandas
    import os
    archivo_path = "archivo2.xlsx"
    
    if not os.path.exists(archivo_path):
        # Crear archivo de ejemplo si no existe
        data_ejemplo = pd.DataFrame({
            'Producto': ['Producto A', 'Producto B', 'Producto C'],
            'Demanda': [100, 150, 200],
            'Año': [2023, 2023, 2023]
        })
        data_ejemplo.to_excel(archivo_path, index=False)
        st.info(f"Archivo '{archivo_path}' creado con datos de ejemplo en la carpeta inventarios.")
    
    # Botón para recargar datos
    if st.button("Recargar datos del archivo"):
        st.rerun()
    
    try:
        # Leer archivo Excel con pandas
        df = pd.read_excel(archivo_path)
        st.write("📊 Datos del archivo:")
        # Convertir todas las columnas object a string para evitar error de Arrow
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str)
        st.dataframe(df)
        st.session_state.datos_pronostico['archivo_data'] = df
    except Exception as e:
        st.error(f"Error al leer el archivo: {e}")

def pronostico_opcion2():
    st.subheader("Opción 2: Modelos de regresión")
    # Algoritmo: Modelo de regresión lineal
    st.write("Algoritmo: Aplicar regresión lineal a los datos.")
    # Usar datos de opción 1 si existen
    if 'tendencias' in st.session_state.datos_pronostico:
        data = st.session_state.datos_pronostico['tendencias']
        # Placeholder regresión
        slope = np.polyfit(data['Año'], data['Demanda'], 1)[0]
        st.write(f"Pendiente de la regresión: {slope}")
    else:
        st.write("Primero ejecuta Opción 1.")

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

    opcion = st.sidebar.radio("Opciones - Inventarios", 
                              ["Opción 1: Punto de reorden", 
                               "Opción 2: Stock mínimo", 
                               "Opción 3: Rotación", 
                               "Opción 4: Optimización", 
                               "Opción 5: Reportes"],
                              key="inventarios_opcion")

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

    opcion = st.sidebar.radio("Opciones - Compras", 
                              ["Opción 1: Órdenes de compra", 
                               "Opción 2: Proveedores", 
                               "Opción 3: Precios", 
                               "Opción 4: Entregas", 
                               "Opción 5: Seguimiento"],
                              key="compras_opcion")

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

    opcion = st.sidebar.radio("Opciones - Almacenaje", 
                              ["Opción 1: Layout", 
                               "Opción 2: Calidad", 
                               "Opción 3: Espacios", 
                               "Opción 4: Logística", 
                               "Opción 5: Reportes"],
                              key="almacenaje_opcion")

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

if __name__ == "__main__":
    main()