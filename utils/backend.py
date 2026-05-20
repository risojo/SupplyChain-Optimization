# Importación de módulos y librerías necesarios
import streamlit as st
import pandas as pd
import json
import copy
import io
import plotly.express as px
import database
import plotly.graph_objects as go

# Definición de una paleta de colores para usar en gráficos Plotly
plotly_palette = [
    "steelblue", "palegoldenrod", "mediumorchid", "lightgreen", "lightcoral", "greenyellow", "gold",
    "firebrick", "deepskyblue", "darkseagreen", "darkgoldenrod", "cornflowerblue", "chartreuse", "burlywood",
    "blueviolet", "beige", "aquamarine", "aliceblue"
]

# Función para comprobar la extensión de un archivo cargado
def check_extension(uploaded_data):
    # Realiza una copia profunda de los datos cargados para no modificar los datos originales
    copied_data = copy.deepcopy(uploaded_data)
    
    # Comprueba si la extensión del archivo es .xlsx (Excel)
    if copied_data.name.endswith('xlsx'):
        pass  # Puede hacer algo con el archivo, pero el código no muestra qué hacer
        # st.markdown(f"##### :heavy_check_mark: _:green[{copied_data.name}]_ subido correctamente ")
    else:
        # Muestra un mensaje de error si el formato del archivo no es válido
        st.error("Formato de archivo no válido. Por favor, carga un archivo Excel.")
        st.stop()  # Detiene la ejecución de la aplicación Streamlit si se encuentra un archivo con formato incorrecto

# Función para verificar si un DataFrame contiene las columnas esperadas
def check_dataframe_columns(uploaded_data):
    # Realiza una copia profunda de los datos cargados para no modificar los datos originales
    copied_data = copy.deepcopy(uploaded_data)
    
    # Lee el archivo Excel y carga su contenido en un DataFrame
    df = pd.read_excel(copied_data)
    
    # Obtiene la lista de nombres de columnas del DataFrame
    df_columns = df.columns.tolist()

    # ruta del JSON que contiene las columnas esperadas
    json_filename = 'json_files/database_names.json'
    
    # Abre y carga el contenido del archivo JSON en un diccionario
    with open(json_filename, 'r') as json_file:
        data_dictionary = json.load(json_file)
    
    # Obtiene la lista de columnas esperadas del diccionario cargado
    expected_columns = data_dictionary['expected_columns']

    # Encuentra las columnas que faltan en el DataFrame comparando con las columnas esperadas
    missing_columns = set(expected_columns) - set(df_columns)

    # Encuentra las columnas adicionales que no se esperaban en el DataFrame
    extra_columns = set(df_columns) - set(expected_columns)

    # Verifica si el DataFrame contiene exactamente las mismas columnas que se esperaban
    if len(missing_columns) == 0 and len(extra_columns) == 0:
        pass  # si cumple con las columnas se sigue con la ejecución normal
    else:
        # Muestra un mensaje de error si el DataFrame no contiene las mismas columnas que se esperaban
        st.error("El DataFrame no contiene exactamente las mismas columnas.")

        # Comprueba si hay columnas faltantes o columnas adicionales y muestra un mensaje de advertencia
        if len(missing_columns) > 0 or len(extra_columns) > 0:
            warning_message = ""  # Inicializa una cadena de advertencia vacía

            if len(missing_columns) > 0:
                # Si hay columnas faltantes, agrega un mensaje indicando cuáles son
                warning_message += f"Columnas faltantes: \n\n{list(missing_columns)}\n\n"

            if len(extra_columns) > 0:
                # Si hay columnas adicionales, agrega un mensaje indicando cuáles son
                warning_message += f"Columnas adicionales: \n\n{list(extra_columns)}"

            # Muestra una advertencia en la aplicación Streamlit con el mensaje construido
            st.warning(warning_message)

            # Detiene la ejecución de la aplicación Streamlit si las columnas no coinciden
            st.stop()

#funcion para calcular columnas extra en base a la información suministrada
def transform_dataframe(df):
    # Crear una copia del DataFrame para mantener el original sin cambios
    df_copy = df.copy()

    # Suma las filas de las columnas 'demanda_mes_X' y crea una nueva columna 'unidades_vendidas'
    demand_cols = [f'demanda_mes{i}' for i in range(1, 13)]
    df_copy['unidades_vendidas'] = df_copy[demand_cols].sum(axis=1)

    # Calcular la columna 'bultos_vendidos' como la división entre 'unidades_vendidas' y 'empaque'
    df_copy['bultos_vendidos'] = df_copy['unidades_vendidas'] / df_copy['empaque']
    
    # Calcular la columna 'margen_utilidad/ventas'
    df_copy['margen_utilidad/ventas'] = (df_copy['precio_uni/bulto'] - df_copy['costo_uni/bulto']) / df_copy['precio_uni/bulto']
    
    # Calcular la columna 'ventas_totales'
    df_copy['ventas_totales'] = df_copy['bultos_vendidos'] * df_copy['precio_uni/bulto']

    # Calcular la columna 'ventas_al_costo'
    df_copy['ventas_al_costo'] = df_copy['bultos_vendidos'] * df_copy['costo_uni/bulto']

    # Calcular la columna 'margen_bruto'
    df_copy['margen_bruto'] = df_copy['bultos_vendidos'] * (df_copy['precio_uni/bulto'] - df_copy['costo_uni/bulto'])

    # Calcular la columna 'valor_inv_prom_bultos'
    df_copy['valor_inv_prom_bultos'] = df_copy['inv_prom/bultos'] * df_copy['costo_uni/bulto']

    # Calcular la columna 'rotacion'
    df_copy['rotacion'] = df_copy['ventas_al_costo'] / df_copy['valor_inv_prom_bultos']

    # Calcular la columna 'meses_inv'
    df_copy['meses_inv'] = 12 / df_copy['rotacion']

    # Suma las filas de las columnas 'demanda_mes_X' y crea una nueva columna 'prom_bultos_desp/mes'
    demand_cols = [f'demanda_mes{i}' for i in range(1, 13)]
    df_copy['prom_bultos_desp/mes'] = df_copy[demand_cols].mean(axis=1)

    # Calcular la columna 'cubicaje_inv_prom'
    df_copy['cubicaje_inv_prom'] = df_copy['inv_final/bultos'] / df_copy['bultos/tarima'] * df_copy['cubicaje/tarima']

    return df_copy

# Función para aplicar estilos y formato a un DataFrame
def style_dataframe(df):
    df = df.copy()  # Realiza una copia del DataFrame original para no modificarlo

    # ruta al JSON que contiene los nombres de las columnas
    json_filename = './json_files/database_names.json'
    
    # Carga el contenido del archivo JSON en un diccionario
    with open(json_filename, 'r') as json_file:
        data_dictionary = json.load(json_file)

    # Divide las columnas del DataFrame en dos grupos: esperadas y calculadas
    expected_columns = data_dictionary['expected_columns']
    calculated_columns = data_dictionary['calculated_columns']

    # Define los estilos para cada grupo de columnas
    column_styles = {
        col: {'background-color': 'black', 'color': 'lawngreen'} for col in expected_columns
    }
    column_styles.update({
        col: {'background-color': 'black', 'color': 'red'} for col in calculated_columns
    })

    # Crea una copia del DataFrame con los estilos aplicados
    styled_df = df.style

    # Aplica formato a columnas específicas del DataFrame
    cubicaje_format = "{:.2f} m³"
    currency_format = "$ {:,.2f}"
    integer_format = "{:.0f}"
    percent_format = "{:.0%}"  
    decimal_format = "{:.2f}"

    styled_df = styled_df.format({
        'cubicaje/tarima': cubicaje_format,
        'cubicaje_inv_prom': cubicaje_format,
        'precio_uni/bulto': currency_format,
        'costo_uni/bulto': currency_format,
        'ventas_totales': currency_format,
        'ventas_al_costo': currency_format,
        'margen_bruto': currency_format,
        'valor_inv_prom_bultos': currency_format,
        'empaque': integer_format,
        'bultos/tarima': integer_format,
        'demanda_mes1': integer_format,
        'demanda_mes2': integer_format,
        'demanda_mes3': integer_format,
        'demanda_mes4': integer_format,
        'demanda_mes5': integer_format,
        'demanda_mes6': integer_format,
        'demanda_mes7': integer_format,
        'demanda_mes8': integer_format,
        'demanda_mes9': integer_format,
        'demanda_mes10': integer_format,
        'demanda_mes11': integer_format,
        'demanda_mes12': integer_format,
        't_entrega_prom': integer_format,
        'inv_final/bultos': integer_format,
        'inv_prom/bultos': integer_format,
        'inv_trans/bultos': integer_format,
        'unidades_vendidas': integer_format,
        'bultos_vendidos': integer_format,
        'prom_bultos_desp/mes': integer_format,
        'factor_escazes': percent_format,
        'margen_utilidad/ventas': percent_format,
        'rotacion': decimal_format,
        'meses_inv': decimal_format
    })
    
    # Aplica estilos a las columnas basados en los grupos definidos
    for column, styles in column_styles.items():
        styled_df = styled_df.set_properties(subset=column, **styles)
    
    # Devuelve el DataFrame con estilos y formato aplicados
    return styled_df

# Función para obtener un DataFrame transformado a partir de una tabla Excel
def get_transformed_dataframe(table):
    # Lee el archivo Excel y carga su contenido en un DataFrame
    df = pd.read_excel(table, engine='openpyxl')
    
    # Aplica una función de transformación (transform_dataframe) al DataFrame
    df_transformed = transform_dataframe(df)
    
    # Devuelve el DataFrame transformado
    return df_transformed

# Función para obtener un DataFrame con estilos a partir de un DataFrame transformado
def get_styled_dataframe(df_transformed):
    # Aplica estilos al DataFrame transformado utilizando la función 'style_dataframe'
    df_styled = style_dataframe(df_transformed)
    
    # Devuelve el DataFrame con estilos aplicados
    return df_styled

# Función para exportar un DataFrame a un archivo CSV y devolverlo en formato binario
def export_csv(df):
    # Convierte el DataFrame a un archivo CSV con índice incluido y lo codifica en formato 'utf-8'
    return df.to_csv(index=True).encode('utf-8')

# Función para exportar un DataFrame a un archivo Excel y devolverlo en formato binario
def export_excel(df):
    # Crea un objeto de salida en formato binario
    output = io.BytesIO()
    
    # Crea un escritor de Excel utilizando el motor 'openpyxl'
    writer = pd.ExcelWriter(output, engine='openpyxl')
    
    # Guarda el DataFrame en una hoja de Excel llamada 'Base transformada' con índice incluido
    df.to_excel(writer, sheet_name='Base transformada', index=True)
    
    # Cierra el escritor y ajusta la posición del objeto de salida al principio
    writer.close()
    output.seek(0)
    
    # Devuelve el objeto de salida en formato binario
    return output

# Función para mostrar botones de descarga de datos en una aplicación Streamlit
def download_dataframe(df, name="Base"):
    # Exporta el DataFrame a formatos CSV y Excel
    csv = export_csv(df)
    excel = export_excel(df)

    # Muestra una leyenda en la aplicación Streamlit
    st.caption("Exportar datos:")
    
    # Crea botones de descarga para CSV y Excel en la aplicación Streamlit
    st.download_button(
        label="Descargar como CSV",
        data=csv,
        file_name=f'{name}.csv'
    )

    st.download_button(
        label="Descargar como Excel",
        data=excel,
        file_name=f'{name}.xlsx'
    )


# ------------- PARAMETROS GENERALES ---------------------------------------

#crea un dataframe para rellenar los datos de los parámetros
def parameter_edited_df(name: str, rows: list, values: list, format: str = None):
    # Crear un DataFrame con los datos proporcionados
    df = pd.DataFrame({
        name: rows,  # Columna con el nombre 'name' que contiene los valores de 'rows'
        'values': values  # Columna con el nombre 'values' que contiene los valores de 'values'
    })
    
    # Usar el editor de datos de Streamlit para editar el DataFrame
    edited_df = st.data_editor(df, use_container_width=True, hide_index=True, disabled=[name],
                               column_config={"values": st.column_config.NumberColumn(label="Ingresa los valores acá: 🔽",
                                                                                      format=format
                                                                                      )
                                              }
                               )
    # Se oculta el índice del DataFrame y se deshabilita la columna 'name' para evitar cambios en ella
    # Además, se configura la columna 'values' como una columna numérica
    
    return edited_df  # Se devuelve el DataFrame editado

# Esta función crea una tabla de datos en un entorno Streamlit, toma un nombre, una lista de filas y una lista de valores,
# y luego muestra la tabla con formato especial y estilo.
def parameter_table(name: str, rows: list, values: list):
    # Crear un DataFrame con los datos proporcionados
    df = pd.DataFrame({
        name: rows,  # Columna con el nombre proporcionado que contiene los valores de 'rows'
        'Valor calculado de la base de datos': values,  # Columna que contiene los valores calculados
    })

    # Formatear los valores como enteros
    df['Valor calculado de la base de datos'] = df['Valor calculado de la base de datos'].astype(int)

    # Aplicar formato a la tabla para separar miles con comas
    styled_df = df.style.format(thousands=",")

    # Definir una función para aplicar estilo de fuente roja a un valor
    def red_font(val):
        return 'color: red'

    # Aplicar el estilo de fuente roja a la columna específica
    styled_df = styled_df.applymap(red_font, subset=['Valor calculado de la base de datos'])

    # Mostrar la tabla en Streamlit sin el índice y ajustando al ancho del contenedor
    st.dataframe(styled_df, hide_index=True, use_container_width=True)

# Esta función calcula diversos parámetros a partir de un DataFrame de respuesta y parámetros específicos.
# Luego, actualiza la base de datos del usuario con los resultados calculados.
def calculated_params(response, param_res):
    # Obtener un DataFrame transformado a partir de la respuesta
    df_transformed = get_transformed_dataframe(response)
    
    # Extraer los parámetros del objeto param_res
    parameters = param_res["parameters"]
    
    # Calcular el valor total de la inversión promedio en bultos y su variante financiera
    sum_valor_inv_prom_bultos = df_transformed["valor_inv_prom_bultos"].sum().round(0)
    sum_valor_inv_prom_bultos_gen_financieros = sum_valor_inv_prom_bultos * parameters["gen_financieros"][0] / 100
    
    # Actualizar los parámetros con los resultados calculados
    parameters["inv_inversiones_calculado"] = [sum_valor_inv_prom_bultos, sum_valor_inv_prom_bultos_gen_financieros]
    
    # Calcular el total de ventas totales y ventas al costo
    sum_ventas_totales = df_transformed["ventas_totales"].sum().round(0)
    sum_ventas_al_costo = df_transformed["ventas_al_costo"].sum().round(0)
    
    # Actualizar los parámetros con los resultados calculados
    parameters["gen_financieros_calculados"] = [sum_ventas_totales, sum_ventas_al_costo]
    
    # Calcular el número de SKU (productos) y el número de proveedores
    number_of_skus = len(df_transformed["cod_producto"].unique())
    number_of_prov = len(df_transformed["proveedor"].unique())
    
    # Actualizar los parámetros con los resultados calculados
    parameters["inv_datos_calculados"] = [number_of_skus, number_of_prov]
    
    # Actualizar la base de datos del usuario con los parámetros actualizados
    database.update_user(username=st.session_state["username"], updates={"parameters": parameters})

# ------------- DATA MINING DRIVERS ---------------------------------------

#crea una tabla pivote con los valores brutos
def pivot_value_table(df, index:str):
    # Realiza una copia del DataFrame de entrada para evitar cambios inesperados
    df = df.copy()
    
    # Define un diccionario que mapea columnas y operaciones de agregación
    map_for_pivot = {'cod_producto': 'count',
                     'inv_prom/bultos': 'sum',
                     'bultos_vendidos': 'sum',
                     'valor_inv_prom_bultos': 'sum',
                     'ventas_totales': 'sum',
                     'margen_bruto': 'sum',
                     'cubicaje_inv_prom': 'sum',
                     'ordenes_anual': 'sum'}
    
    # Crea una tabla dinámica utilizando pandas con las columnas y operaciones definidas
    pivot_table = pd.pivot_table(df, 
                                index=index, 
                                values=map_for_pivot.keys(),
                                aggfunc=map_for_pivot,
                                margins=True,  # Agrega una fila "Total" al final
                                margins_name="Total",
                                sort=False)  # Ordena las filas en orden alfabético por producto
                                
    # Cambia los nombres de las columnas en la tabla pivot_table
    pivot_table.columns = [f"{agg}({key})" for key, agg in map_for_pivot.items()]
    
    # Ordena las filas alfabéticamente
    pivot_table = pivot_table.sort_values(by=index)
    
    # Redondea los valores en la tabla a números enteros
    pivot_table = pivot_table.round(0)
    
    # Devuelve la tabla pivot resultante
    return pivot_table

#muestra la tabla pivote con el formato y color que deben tener
def show_pivot_value_table(pivot_table):
    # Crear el DataFrame con los estilos aplicados a las columnas
    styled_pivot_table = pivot_table.style

    # Aplicar formato a las columnas
    cubicaje_format = "{:.0f} m³"
    currency_format = "$ {:,.0f}"
    integer_format = "{:.0f}"
    styled_pivot_table = styled_pivot_table.format({
        'count(cod_producto)': integer_format,
        'sum(inv_prom/bultos)': integer_format,
        'sum(bultos_vendidos)': integer_format,
        'sum(valor_inv_prom_bultos)': currency_format,
        'sum(ventas_totales)': currency_format,
        'sum(margen_bruto)': currency_format,
        'sum(cubicaje_inv_prom)': cubicaje_format,
        'sum(ordenes_anual)': integer_format
    })
    
    # Crear un diccionario para definir los estilos de las columnas
    column_styles = {}
    
    # Iterar a través de las columnas del DataFrame y pone colores intercalados
    for idx, col in enumerate(styled_pivot_table.columns):
        if idx % 2 == 0:
            column_styles[col] = { 'color': 'Aqua'}
        else:
            column_styles[col] = { 'color': 'orange'}
    
    # Aplicar los estilos definidos a las columnas
    for column, styles in column_styles.items():
        styled_pivot_table = styled_pivot_table.set_properties(subset=column, **styles)
    
    # Define una función que aplique el estilo a las filas
    def estilo_fila(s):
        return ['background-color: maroon' if s.name == "Total" else None] * len(s)

    # Aplica el estilo a las filas utilizando la función apply
    styled_pivot_table = styled_pivot_table.apply(estilo_fila, axis=1)
    
    # Mostrar el DataFrame con los estilos aplicados
    st.dataframe(styled_pivot_table, use_container_width=True)

#crea una tabla pivote con los valores porcentuales
def pivot_percent_table(df):
    # Realiza una copia del DataFrame de entrada para evitar cambios inesperados
    df = df.copy()
    
    # Cambia los nombres de las columnas del DataFrame
    df.columns = ["% Sku's","% inv prom/bult","% bult vendidos",
                  "% valor inv prom $","% ventas totales","% margen bruto",
                  "% cub inv prom","% ordenes anual"] 
    
    # Elimina la fila "Total" del DataFrame
    df.drop("Total", inplace=True)
    
    # Crea un DataFrame vacío llamado percent_table
    percent_table = pd.DataFrame()
    
    # Calcula los porcentajes de cada columna dividiendo por la suma de la columna
    for column in df.columns:
        percent_table[column] = (df[column] / df[column].sum()) 
    
    # Transpone el DataFrame para que los "Drivers" sean el índice
    percent_table = percent_table.T
    
    # Establece el nombre del índice como "Driver"
    percent_table.index.name = "Driver"
    
    # Agrega una columna "Total" que contiene la suma de los porcentajes de cada fila
    percent_table['Total'] = percent_table.sum(axis=1)
    
    # Devuelve el DataFrame con los porcentajes calculados
    return percent_table

#muestra la tabla pivote con el formato y color que deben tener
def show_pivot_percent_table(percent_table):
    # Formatea los valores en el DataFrame para mostrar los porcentajes con dos decimales
    # excepto la última columna que se muestra sin decimales
    percent_table = percent_table.style.format({col: '{:.2%}' if col != percent_table.columns[-1] else '{:.0%}' for col in percent_table.columns})
    
    # Crea un diccionario para definir los estilos de las columnas
    column_styles = {}
    
    # Itera a través de las columnas del DataFrame estilizado
    for idx, col in enumerate(percent_table.columns):
        # Alterna los colores de las columnas basado en su índice
        if idx % 2 == 0:
            column_styles[col] = { 'color': 'Aqua'}
        else:
            column_styles[col] = { 'color': 'orange'}
    
    # Aplica los estilos definidos a las columnas del DataFrame estilizado
    for column, styles in column_styles.items():
        percent_table = percent_table.set_properties(subset=column, **styles)

    # Define una función que aplique el estilo a la última columna
    def estilo_ultima_columna(s):
        estilos = ['background-color: midnightblue' if col == s.index[-1] else '' for col in s.index]
        return estilos

    # Aplica el estilo a las columnas utilizando la función apply
    percent_table = percent_table.apply(estilo_ultima_columna, axis=1)
    
    # Muestra el DataFrame estilizado utilizando Streamlit
    st.dataframe(percent_table, use_container_width=True)

# Muestra una gráfica de barras usando plotly en base a los datos de la tabla de porcentaje
def show_barchart_dataminnigdrivers(percent_produc_table):
    # Realiza una copia del DataFrame de porcentajes de productos para evitar cambios inesperados
    percent_produc_table = percent_produc_table.copy()
    
    # Elimina la fila "Total" del DataFrame
    percent_produc_table.drop("Total", axis=1, inplace=True)
    
    # Utiliza la paleta de colores personalizada para la gráfica de barras
    colores = plotly_palette[:len(percent_produc_table.columns)]
    
    # Crea una gráfica de barras utilizando Plotly Express
    fig = px.bar(percent_produc_table, 
                x=percent_produc_table.index, 
                y=percent_produc_table.columns, 
                barmode='group',
                title='Porcentaje de drivers por categoría de producto', 
                labels={'index': 'Drivers', 'value': 'Valor (%)'}, 
                color_discrete_sequence=colores)
    
    # Formatea el eje y para mostrar valores en formato de porcentaje
    fig.update_layout( yaxis_tickformat='.0%')
    
    # Agrega etiquetas a las barras que muestran el valor en porcentaje
    fig.update_traces(
        texttemplate='%{y:.0%}',
        textposition='outside'
    )
    
    # Muestra la gráfica de barras utilizando Streamlit (representado por 'st')
    st.plotly_chart(fig, use_container_width=True)

# ------------- SCORECARD ---------------------------------------
#calcula el scorecard de inversiones y costos
def scorecard_all(percent_produc_table, table_name, inver_param_names, inver_param_values, capital_cost_value, cost_param_names, cost_param_values):
    # Obtener la lista de drivers a partir del índice de percent_produc_table.
    drivers_list = percent_produc_table.index.to_list()
    
    # Crear un DataFrame vacío para almacenar el scorecard.
    df_scorecard_all = pd.DataFrame()
    
    # Iterar a través de cada driver en la lista.
    for driver in drivers_list:
        # Obtener un diccionario que representa los valores de porcentaje del driver actual.
        driver_dict = percent_produc_table.loc[driver].to_dict()
        
        # Crear un DataFrame para almacenar los parametros de inversiones.
        gen_params_inv = {
            table_name: inver_param_names,
            "Valor": inver_param_values
        }
        df_inver = pd.DataFrame(gen_params_inv)
        
        # Calcular los valores de inversión para cada parámetro basado en el porcentaje del driver.
        for key, value in driver_dict.items():
            df_inver[f"{key}"] = df_inver["Valor"] * value * (capital_cost_value / 100)
        
        # Crear un DataFrame para almacenar los parametros de costos.
        gen_params_cost = {
            table_name: cost_param_names,
            "Valor": cost_param_values
        }
        df_cost = pd.DataFrame(gen_params_cost)
        
        # Calcular los valores de costos para cada parámetro basado en el porcentaje del driver.
        for key, value in driver_dict.items():
            df_cost[f"{key}"] = df_cost["Valor"] * value      
        
        # Combinar los DataFrames de inversiones y costos en uno solo.
        df_inver_cost = pd.concat([df_inver, df_cost], ignore_index=True)
        
        # Agregar una columna "Drivers" que contiene el nombre del driver.
        df_inver_cost.insert(loc=1, column='Drivers', value=driver)
        
        # Eliminar la columna "Valor" ya que no es necesaria.
        df_inver_cost.drop("Valor", axis=1, inplace=True)
        
        # Calcular el costo total sumando los valores de costos para cada parámetro.
        df_inver_cost["Costo Totales"] = df_inver_cost[driver_dict.keys()].sum(axis=1)
        
        # Concatenar el DataFrame de detalles del driver actual al scorecard general.
        df_scorecard_all = pd.concat([df_scorecard_all, df_inver_cost], ignore_index=True)
    
    # Devolver el scorecard completo como resultado.
    return df_scorecard_all

# Muestra el scorecard en streamlit con la funcionalidad de seleccionar el driver a gusto
def show_scorecard(percent_produc_table, table_name, inver_param_names, cost_param_names, drivers_list, df_scorecard_all):
    # Crear un diccionario de parámetros que incluye los nombres de inversión y costos.
    params = {
                table_name: inver_param_names + cost_param_names
            }

    # Crear un DataFrame para el scorecard filtrado con los parámetros y la lista de drivers.
    df_scorecard_filtered = pd.DataFrame(params)
    df_scorecard_filtered["Drivers"] = drivers_list
    
    # Combinar el DataFrame filtrado con el scorecard completo basado en el nombre de la tabla y los drivers.
    df_scorecard_filtered = df_scorecard_filtered.merge(df_scorecard_all, 
                                                        on=[table_name, "Drivers"], 
                                                        how="left")
    
    # Calcular el porcentaje de costo en función de los costos totales.
    df_scorecard_filtered["% Costo"] = df_scorecard_filtered["Costo Totales"] / df_scorecard_filtered["Costo Totales"].sum()
    
    # Obtener las columnas numéricas (excluyendo "Drivers" y el nombre de la tabla).
    columnas_numericas = [column for column in df_scorecard_filtered.columns if column not in ["Drivers", table_name]]
    
    # Calcular la fila de totales y crear un DataFrame para ella.
    fila_totales = df_scorecard_filtered[columnas_numericas].sum()
    df_totales = pd.DataFrame([fila_totales], columns=df_scorecard_filtered.columns)
    
    # Concatenar la fila de totales al DataFrame filtrado.
    df_scorecard_filtered = pd.concat([df_scorecard_filtered, df_totales])
    
    # Modificar el nombre de la última fila para indicar "Costo total anual del almacenaje".
    df_scorecard_filtered.iloc[-1, 0] = f"{table_name} total anual "
    
    # Definir las columnas que deben estar deshabilitadas en el editor de datos.
    disable_column = [column for column in df_scorecard_filtered.columns if column != "Drivers"]
    
    # Crear un DataFrame con estilos aplicados a las columnas.
    df_scorecard_filtered = df_scorecard_filtered.set_index(df_scorecard_filtered.columns[0])
    styled_df_scorecard_filtered = df_scorecard_filtered.style
    
    # Aplicar formatos a las columnas, como formato de moneda y formato de porcentaje.
    currency_format = "$ {:,.0f}"
    percent_format = "{:.2%}"

    format_dic = {col: currency_format for col in percent_produc_table.columns}
    format_dic["Costo Totales"] = currency_format
    format_dic["% Costo"] = percent_format
    styled_df_scorecard_filtered = styled_df_scorecard_filtered.format(format_dic)
    
    # Crear un diccionario para definir estilos de las columnas, alternando colores entre columnas.
    column_styles = {}
    for idx, col in enumerate(styled_df_scorecard_filtered.columns):
        if idx % 2 == 0:
            column_styles[col] = {'color': "orange"}
        else:
            column_styles[col] = {'color': "lightblue"}
    
    # Aplicar los estilos definidos a las columnas del DataFrame.
    for column, styles in column_styles.items():
        styled_df_scorecard_filtered.set_properties(subset=column, **styles)

    # Define una función que aplique el estilo a la última columna
    def estilo_ultima_columna(s):
        estilos = ['background-color: midnightblue' if col == s.index[-2] else '' for col in s.index]
        return estilos

    # Aplica el estilo a las columnas utilizando la función apply
    styled_df_scorecard_filtered = styled_df_scorecard_filtered.apply(estilo_ultima_columna, axis=1)

    # Define una función que aplique el estilo a las filas
    def estilo_fila(s):
        return ['background-color: maroon' if s.name == "Costo total anual del almacenaje" else None] * len(s)

    # Aplica el estilo a las filas utilizando la función apply
    styled_df_scorecard_filtered = styled_df_scorecard_filtered.apply(estilo_fila, axis=1)
    
    
    # Devolver el DataFrame estilizado como un editor de datos de Streamlit.
    return st.data_editor(styled_df_scorecard_filtered,
                         hide_index=True,
                         use_container_width=True,
                         disabled=disable_column,
                         height=(len(df_scorecard_filtered) + 1) * 35 + 3, 
                         column_config=
                         {
                            "Drivers": st.column_config.SelectboxColumn("Selecciona tú driver",
                                                        width="medium",
                                                        options=percent_produc_table.index.to_list(),
                                                        required=False)
                        }
                    )

# Calcula el scorecard total que tiene en cuenta el scorecard para inversiones y costos
def total_scorecard(alm_scorecard, inv_scorecard, value_produc_table_total):
    # Cambiar el nombre del índice "Total" a "Costo Totales" en value_produc_table_total.
    value_produc_table_total.rename(index={"Total": "Costo Totales"}, inplace=True)
    
    # Calcular el costo total sumando los valores de alm_scorecard e inv_scorecard, excluyendo las primeras y últimas columnas.
    total_cost = alm_scorecard.iloc[-1].iloc[1:-1] + inv_scorecard.iloc[-1].iloc[1:-1]
    total_cost.rename("Costo total de mantener inventario (ICC)", inplace=True)
    
    # Crear un DataFrame para almacenar el costo total.
    total_cost_df = pd.DataFrame([total_cost])
    
    # Calcular y agregar métricas adicionales relacionadas con el inventario.
    total_cost_df.loc["Tasa de mantener el inventario (ICR)"] = total_cost / value_produc_table_total["sum(valor_inv_prom_bultos)"]
    total_cost_df.loc["Rotación"] = value_produc_table_total["sum(ventas_totales)"] / value_produc_table_total["sum(valor_inv_prom_bultos)"]
    total_cost_df.loc["Días de inventario - 250 días al año"] = 250 / total_cost_df.loc["Rotación"]
    total_cost_df.loc["Días de inventario - 360 días al año"] = 360 / total_cost_df.loc["Rotación"]
    total_cost_df.loc["Meses de inventario"] = 12 / total_cost_df.loc["Rotación"]
    total_cost_df.loc["Costo de mantener inventarios/ventas"] = total_cost / value_produc_table_total["sum(ventas_totales)"]
    total_cost_df.loc["Valor del inventario/ventas"] = value_produc_table_total["sum(valor_inv_prom_bultos)"] / value_produc_table_total["sum(ventas_totales)"]
    total_cost_df.loc["GMROI - Gross Margin Return on Inventory"] = value_produc_table_total["sum(margen_bruto)"] / value_produc_table_total["sum(valor_inv_prom_bultos)"]
    total_cost_df.loc["EVAI - Valor agregado del inventario"] = value_produc_table_total["sum(margen_bruto)"] - total_cost
    
    # Copiar el resultado antes de aplicar formatos para devolverlo sin cambios.
    result = total_cost_df.copy()
    
    # Aplicar formatos específicos a las celdas del DataFrame.
    total_cost_df.iloc[[0, 9]] = total_cost_df.iloc[[0, 9]].applymap(lambda x: f"$ {x:,.0f}")
    total_cost_df.iloc[[1, 6, 7, 8]] = total_cost_df.iloc[[1, 6, 7, 8]].applymap(lambda x: f"{x:.2%}")
    total_cost_df.iloc[[2, 3, 4, 5]] = total_cost_df.iloc[[2, 3, 4, 5]].applymap(lambda x: f"{x:.2f}")
    
    # Estilizar el DataFrame con colores alternos para las columnas.
    styled_df = style_df(total_cost_df, colo1="lightblue", color2="orange")

    # Define una función que aplique el estilo a la última columna
    def estilo_ultima_columna(s):
        estilos = ['background-color: midnightblue' if col == s.index[-1] else '' for col in s.index]
        return estilos

    # Aplica el estilo a las columnas utilizando la función apply
    styled_df = styled_df.apply(estilo_ultima_columna, axis=1)
    
    # Mostrar el DataFrame estilizado en Streamlit.
    st.dataframe(styled_df, use_container_width=True)
    
    # Devolver el resultado original sin cambios.
    return result

# Crea un grafico de barras horizontal que muestra el ICC
def horizontal_bar_chart(alm_scorecard, inv_scorecard):
    # Extraer los valores de costo total de los DataFrames de alm_scorecard e inv_scorecard.
    total_cost_alm = alm_scorecard[:-1].iloc[:, [-2]]
    total_cost_inv = inv_scorecard[:-1].iloc[:, [-2]]
    
    # Concatenar los valores de costo total de ambos DataFrames.
    total_cost_all = pd.concat([total_cost_alm, total_cost_inv])
    total_cost_all = total_cost_all["Costo Totales"]
    
    # Crear un gráfico de barras horizontales utilizando Plotly Express.
    fig = px.bar(
        y=total_cost_all.index,  # Índices como etiquetas en el eje y.
        x=total_cost_all.values.reshape(-1),  # Valores como posiciones en el eje x.
        title="Costo de los recursos de mantener el inventario (ICC)",  # Título del gráfico.
        labels={"x": "", "y": ""},  # Etiquetas para los ejes x e y.
        height=500  # Altura del gráfico.
    )
    
    # Configurar el formato del texto que se muestra en las barras.
    fig.update_traces(
        texttemplate='$ %{value:,.0f}',  # Formato de moneda.
        textposition='outside'  # Posición del texto fuera de las barras.
    )
    
    # Mostrar el gráfico de barras horizontal en Streamlit.
    st.plotly_chart(fig, use_container_width=True)

# Gráfico de pie que muestra el porcentaje por cat o subcat
def pie_chart(total_cost_df):
    # Obtener los totales de costo excluyendo "Costo Totales" del DataFrame total_cost_df.
    totals = total_cost_df.loc["Costo total de mantener inventario (ICC)"]
    totals_nocost = totals.drop("Costo Totales")
    
    # Etiquetas y valores para el gráfico de pastel.
    labels = totals_nocost.index
    values = totals_nocost.values
    
    # Crear un gráfico de pastel (pie chart) utilizando Plotly Express.
    fig = px.pie(
        values=values,
        names=labels,
        title='Costo total de mantener el inventario por categoría',
        hole=0.4,  # Tamaño del agujero en el centro del pastel.
    )
    
    # Configurar el formato del texto en las secciones del pastel.
    fig.update_traces(
        texttemplate='%{percent:.1%}<br> $ %{value:,.0f}',  # Formato del texto con porcentaje y valor en moneda.
        marker=dict(colors=plotly_palette[:len(labels)]),  # Colores personalizados.
    )
    
    # Configurar el fondo y el estilo de fuente del gráfico.
    fig.update_layout(
        paper_bgcolor='black',
        plot_bgcolor='black',
        font=dict(color='white'),  # Fuente blanca.
    )
    
    # Mostrar el gráfico de pastel en Streamlit.
    st.plotly_chart(fig, use_container_width=True)

# Crea un grafico vertical de los valores en bruto
def vertical_chart_value(total_cost_df):
    # Obtener los totales de costo excluyendo "Costo Totales" del DataFrame total_cost_df.
    totals = total_cost_df.loc["Costo total de mantener inventario (ICC)"]
    
    # Almacenar el costo total de todos los valores.
    total_of_totals = totals["Costo Totales"]
    
    # Eliminar "Costo Totales" del DataFrame para el gráfico de barras.
    totals.drop("Costo Totales", inplace=True)

    # Calcular los porcentajes del total para cada categoría.
    percentages = (totals / total_of_totals) * 100
    
    # Crear un gráfico de barras verticales utilizando Plotly Express.
    fig = px.bar(
        x=totals.index,  # Categorías en el eje x.
        y=totals.values,  # Valores en el eje y.
        title=f"Costo de mantener el inventario (ICC)<br>Costo Totales: <span style='color:red;'>{total_of_totals:,.0f}</span>",  # Título del gráfico con formato HTML.
        labels={"x": "", "y": ""},  # Etiquetas para los ejes x e y.
    )
    
    # Configurar el color de las barras, formato de texto y posición del texto.
    fig.update_traces(
        marker_color="chartreuse",  # Color de las barras.
        text=['$ {:,.0f} ({:.1f}%)'.format(value, percentages[i]) for i, value in enumerate(totals.values)],  # Texto con valor y porcentaje.
        textposition='outside'  # Posición del texto fuera de las barras.
    )
    
    # Mostrar el gráfico de barras verticales en Streamlit.
    st.plotly_chart(fig, use_container_width=True)

# Crea un grafico vertical de los porcentajes
def vertical_chart_percent(total_cost_df):
    # Obtener los valores de la tasa de mantener el inventario (ICR) del DataFrame total_cost_df.
    icr = total_cost_df.loc["Tasa de mantener el inventario (ICR)"]

    # Crear un gráfico de barras verticales utilizando Plotly Express.
    fig = px.bar(
        x=icr.index,  # Categorías en el eje x.
        y=icr.values,  # Valores en el eje y.
        title="Tasa de mantener el inventario (ICR)",  # Título del gráfico.
        labels={"x": "", "y": ""},  # Etiquetas para los ejes x e y.
    )
    
    # Configurar el formato del eje y para mostrar los valores en formato de porcentaje.
    fig.update_layout(
        yaxis_tickformat='.0%'  # Formato de porcentaje para el eje y.
    )
    
    # Configurar el color de las barras, formato de texto y posición del texto.
    fig.update_traces(
        marker_color="gold",  # Color de las barras.
        texttemplate='%{value:.1%}',  # Formato de porcentaje en el texto.
        textposition='outside'  # Posición del texto fuera de las barras.
    )
    
    # Mostrar el gráfico de barras verticales en Streamlit.
    st.plotly_chart(fig, use_container_width=True)

# ------------- EVAI ---------------------------------------

# Fusiona el dataframe transformado con el dataframe de los ICRs
def merge_icrs(df_transformed, ICRs):
    # Realiza una fusión izquierda de df_transformed con ICRs
    df_transformed = df_transformed.merge(ICRs, how="left", left_on="subcat_producto", right_on=ICRs.index)
    
    # Calcula el costo de mantener inventario para cada fila
    df_transformed["Costo de mantener inventario"] = df_transformed["valor_inv_prom_bultos"] * df_transformed["Tasa de mantener el inventario (ICR)"]
    
    # Calcula el valor agregado del inventario (EVAI) para cada fila
    df_transformed["EVAI (valor agregado del inventario)"] = df_transformed["margen_bruto"] - df_transformed["Costo de mantener inventario"]
    
    # Devuelve el DataFrame modificado
    return df_transformed

# Transforma un dataframe y le pone colores alternantes a sus columnas
def style_df(df, colo1='red', color2='green'):
    # Convierte el DataFrame en un objeto de estilo (Styler)
    df = df.style
    # Crea un diccionario para definir los estilos de las columnas
    column_styles = {}
    # Itera a través de las columnas del DataFrame
    for idx, col in enumerate(df.columns):
        if idx % 2 == 0:
            # Si el índice es par, establece el estilo de color a colo1
            column_styles[col] = {'color': colo1}
        else:
            # Si el índice es impar, establece el estilo de color a color2
            column_styles[col] = {'color': color2}
    # Aplica los estilos al DataFrame utilizando set_properties
    for column, styles in column_styles.items():
        df = df.set_properties(subset=column, **styles)
    # Retorna el DataFrame estilizado
    return df

# Muestra el dataframe con los respectivos cálculos del EVAI
def show_df_evai(df_filtered):
    # Crea una copia del DataFrame
    df = df_filtered.copy()
    # Filtrar las columnas deseadas del DataFrame
    df = df[["cod_producto", "desc_producto", "margen_bruto", "Costo de mantener inventario", "EVAI (valor agregado del inventario)"]]
    
    # Aplicar el estilo personalizado al DataFrame filtrado
    df_styled = style_df(df, colo1="orange", color2="lawngreen")

    # Definir el formato de las columnas en formato de moneda
    currency_format = "$ {:,.0f}"
    df_styled = df_styled.format({
        'margen_bruto': currency_format,
        'Costo de mantener inventario': currency_format,
        'EVAI (valor agregado del inventario)': currency_format,
    })

    # Mostrar el DataFrame estilizado sin el índice y con el ancho del contenedor ajustado
    st.dataframe(df_styled, hide_index=True, use_container_width=True)




# ------------- Reporte_EVAI_negativo ---------------------------------------

# Cálcula el reporte de los EVAI y los ordena como positivos, negativos o todos
def negative_report(df_transformed, ICRs, range):
    # Combinar df_transformed con ICRs utilizando la columna "subcat_producto" como clave de unión
    df_transformed = df_transformed.merge(ICRs, how="left", left_on="subcat_producto", right_on=ICRs.index)
    
    # Calcular el costo de mantener el inventario multiplicando el valor promedio del inventario en bultos por la tasa de mantener el inventario (ICR)
    df_transformed["Costo de mantener inventario"] = df_transformed["valor_inv_prom_bultos"] * df_transformed["Tasa de mantener el inventario (ICR)"]
    
    # Calcular el valor agregado del inventario restando el margen bruto al costo de mantener el inventario
    df_transformed["EVAI (valor agregado del inventario)"] = df_transformed["margen_bruto"] - df_transformed["Costo de mantener inventario"]
    
    # Seleccionar las columnas deseadas en el DataFrame
    df_transformed = df_transformed[["cod_producto", "cat_producto", "subcat_producto", "desc_producto", "proveedor", "EVAI (valor agregado del inventario)"]]
    
    if range == "negative":
        # Ordenar el DataFrame en orden ascendente según la columna "EVAI (valor agregado del inventario)"
        df_transformed = df_transformed.sort_values(by=['EVAI (valor agregado del inventario)'], ascending=True)
        # Filtrar las filas donde "EVAI (valor agregado del inventario)" es negativo
        df_transformed = df_transformed[df_transformed["EVAI (valor agregado del inventario)"] < 0]
    elif range == "positive":
        # Ordenar el DataFrame en orden descendente según la columna "EVAI (valor agregado del inventario)"
        df_transformed = df_transformed.sort_values(by=['EVAI (valor agregado del inventario)'], ascending=False)
        # Filtrar las filas donde "EVAI (valor agregado del inventario)" es positivo
        df_transformed = df_transformed[df_transformed["EVAI (valor agregado del inventario)"] > 0]
    else:
        # Ordenar el DataFrame en orden descendente por defecto (sin filtrar)
        df_transformed = df_transformed.sort_values(by=['EVAI (valor agregado del inventario)'], ascending=False)
    
    # Retorna el DataFrame transformado según el rango especificado
    return df_transformed

# Muestra el dataframe del EVAI pero estilizado y con formatos
def show_df_repevai(df_transformed, ICRs, range="all"):
    # Utilizar la función 'negative_report' para obtener el DataFrame transformado
    df_transformed = negative_report(df_transformed, ICRs, range)
    
    # Aplicar estilo personalizado al DataFrame transformado
    df_transformed_styled = style_df(df_transformed, colo1="orange", color2="lawngreen")
    
    # Definir el formato de las columnas en formato de moneda
    currency_format = "$ {:,.0f}"
    df_transformed_styled = df_transformed_styled.format({
        'EVAI (valor agregado del inventario)': currency_format,
    })
    
    # Mostrar el DataFrame estilizado
    st.dataframe(df_transformed_styled, hide_index=True, use_container_width=True)
    
    # Retorna el DataFrame transformado
    return df_transformed

# Crea un barchart en base a las subcategorias escogidas
def barchart_evai(df_filtered, subcat):
    # Crear una copia del DataFrame
    df = df_filtered.copy()
    # # Convertir la columna "cod_producto" a tipo de datos string
    df["cod_producto"] = df["cod_producto"].astype(str)
    # Crear un DataFrame auxiliar
    data = {'cod_producto': df["cod_producto"], 'EVAI (valor agregado del inventario)': df["EVAI (valor agregado del inventario)"]}
    df_to_plot = pd.DataFrame(data)

    # Crear un gráfico de barras utilizando Plotly Express (px)
    fig = px.bar(
        data_frame=df_to_plot,
        x='cod_producto',
        y='EVAI (valor agregado del inventario)',
        title=f"EVAI por subcategoría {subcat}",
        labels={"x": "cod_producto", "y": "EVAI (valor agregado del inventario)"},
    )
    
    # Actualizar las propiedades de las barras
    fig.update_traces(
        marker_color="tomato",  # Establecer el color de las barras
        texttemplate='$ %{value:,.0f}',  # Formato del texto en las barras
        textposition='outside'  # Posición del texto en las barras
    )
    
    # Mostrar el gráfico de barras
    st.plotly_chart(fig, use_container_width=True)

# Función para crear un gráfico de barras que muestra el valor agregado del inventario por código de producto.
def barchart_all_products(df_all):
    # Crear un gráfico de barras utilizando Plotly Express (px)
    fig = px.bar(df_all,
                 x='cod_producto',  # Establecer los códigos de producto en el eje x
                 y='EVAI (valor agregado del inventario)',  # Establecer el EVAI en el eje y
                 title='Valor Agregado del Inventario por Código de Producto'  # Establecer el título del gráfico
                 )

    # Actualizar el eje x para tratar los códigos de productos como categorías (para mantener su orden)
    fig.update_xaxes(type='category')

    # Mostrar el gráfico en una aplicación web (posiblemente utilizando Streamlit) con el ancho del contenedor ajustado.
    st.plotly_chart(fig, use_container_width=True)

# Muestra la distribución de productos positivos y negativos en función del EVAI.
def piechart_all_products(df_all):
    # Calcular el total de productos en el DataFrame
    total = len(df_all)
    
    # Contar la cantidad de productos con EVAI positivo y negativo
    conteo_positivos = len(df_all[df_all['EVAI (valor agregado del inventario)'] > 0])
    conteo_negativos = len(df_all[df_all['EVAI (valor agregado del inventario)'] < 0])

    # Crear el gráfico de pastel utilizando Plotly
    fig_pie = go.Figure(go.Pie(
        labels=['Positivos', 'Negativos'],  # Etiquetas para las secciones del gráfico
        values=[conteo_positivos, conteo_negativos],  # Valores de las secciones del gráfico
        pull=[0, 0.1],  # Para separar ligeramente la sección "Negativos" del centro del pastel
        textinfo="percent+value"  # Mostrar el porcentaje y el valor en cada sección
    ))
    
    # Actualizar el título del gráfico para mostrar el total de productos en rojo
    fig_pie.update_layout(title=f"Total de productos <span style='color:red;'>{total}</span>",
                          legend=dict(orientation="h", y=1.1)) # Colocar la leyenda horizontalmente encima del gráfico
    
    # Mostrar el gráfico de pastel 
    st.plotly_chart(fig_pie, use_container_width=True)


# ------------- GMROI ---------------------------------------

# Fusiona el dataframe transformado con el dataframe de los ICRs
def merge_icrs_gmroi(df_transformed, ICRs):
    # Realiza una fusión izquierda de df_transformed con ICRs
    df_transformed = df_transformed.merge(ICRs, how="left", left_on="subcat_producto", right_on=ICRs.index)
    
    df_transformed["Valor inventario promedio"] = df_transformed["valor_inv_prom_bultos"] 
    
    df_transformed["GMROI"] = df_transformed["margen_bruto"] / df_transformed["Valor inventario promedio"]
    
    # Devuelve el DataFrame modificado
    return df_transformed

# Muestra el dataframe con los respectivos cálculos del GMROI
def show_df_gmroi(df_filtered):
    # Crea una copia del DataFrame
    df = df_filtered.copy()
    # Filtrar las columnas deseadas del DataFrame
    df = df[["cod_producto", "desc_producto", "margen_bruto", "Valor inventario promedio", "GMROI"]]
    
    # Aplicar el estilo personalizado al DataFrame filtrado
    df_styled = style_df(df, colo1="orange", color2="lawngreen")

    # Definir el formato de las columnas en formato de moneda
    currency_format = "$ {:,.0f}"
    percent_format = "{:.0%}" 
    df_styled = df_styled.format({
        'margen_bruto': currency_format,
        'Valor inventario promedio': currency_format,
        'GMROI': percent_format,
    })

    # Mostrar el DataFrame estilizado sin el índice y con el ancho del contenedor ajustado
    st.dataframe(df_styled, hide_index=True, use_container_width=True)

# Crea un barchart en base a las subcategorias escogidas
def barchart_gmroi(df_filtered, subcat):
    # Crear una copia del DataFrame
    df = df_filtered.copy()
    # # Convertir la columna "cod_producto" a tipo de datos string
    df["cod_producto"] = df["cod_producto"].astype(str)
    # Crear un gráfico de barras utilizando Plotly Express (px)
    # Crear un DataFrame auxiliar
    data = {'cod_producto': df["cod_producto"], 'GMROI': df["GMROI"]}
    df_to_plot = pd.DataFrame(data)
    fig = px.bar(
        data_frame=df_to_plot,
        x='cod_producto',
        y='GMROI',
        title=f"GMROI por subcategoría {subcat}",
        labels={"x": "cod_producto", "y": "GMROI"},
    )
    fig.update_layout(
        yaxis_tickformat='.0%'  # Formato de porcentaje para el eje y.
    )
    # Actualizar las propiedades de las barras
    fig.update_traces(
        marker_color="tomato",  # Establecer el color de las barras
        texttemplate='%{value:.1%}',  # Formato de porcentaje en el texto.
        textposition='outside'  # Posición del texto en las barras
    )
    
    # Mostrar el gráfico de barras
    st.plotly_chart(fig, use_container_width=True)

# ------------- Reporte_GMROI_negativo ---------------------------------------

# Cálcula el reporte de los EVAI y los ordena como positivos, negativos o todos
def negative_report_gmroi(df_transformed, ICRs, range):
    # Combinar df_transformed con ICRs utilizando la columna "subcat_producto" como clave de unión
    df_transformed = df_transformed.merge(ICRs, how="left", left_on="subcat_producto", right_on=ICRs.index)
    
    # Calcular el costo de mantener el inventario multiplicando el valor promedio del inventario en bultos por la tasa de mantener el inventario (ICR)
    df_transformed["Valor inventario promedio"] = df_transformed["valor_inv_prom_bultos"] 
    
    # Calcular el valor agregado del inventario restando el margen bruto al costo de mantener el inventario
    df_transformed["GMROI"] = df_transformed["margen_bruto"] / df_transformed["Valor inventario promedio"]
    
    # Seleccionar las columnas deseadas en el DataFrame
    df_transformed = df_transformed[["cod_producto", "cat_producto", "subcat_producto", "desc_producto", "proveedor", "GMROI"]]
    
    if range == "negative":
        # Ordenar el DataFrame en orden ascendente según la columna "EVAI (valor agregado del inventario)"
        df_transformed = df_transformed.sort_values(by=['GMROI'], ascending=True)
        # Filtrar las filas donde "EVAI (valor agregado del inventario)" es negativo
        df_transformed = df_transformed[df_transformed["GMROI"] < 0]
    elif range == "positive":
        # Ordenar el DataFrame en orden descendente según la columna "EVAI (valor agregado del inventario)"
        df_transformed = df_transformed.sort_values(by=['GMROI'], ascending=False)
        # Filtrar las filas donde "EVAI (valor agregado del inventario)" es positivo
        df_transformed = df_transformed[df_transformed["GMROI"] > 0]
    else:
        # Ordenar el DataFrame en orden descendente por defecto (sin filtrar)
        df_transformed = df_transformed.sort_values(by=['GMROI'], ascending=False)
    # Retorna el DataFrame transformado según el rango especificado
    return df_transformed

# Muestra el dataframe del EVAI pero estilizado y con formatos
def show_df_repgmroi(df_transformed, ICRs, range="all"):
    # Utilizar la función 'negative_report' para obtener el DataFrame transformado
    df_transformed = negative_report_gmroi(df_transformed, ICRs, range)
    
    # Aplicar estilo personalizado al DataFrame transformado
    df_transformed_styled = style_df(df_transformed, colo1="orange", color2="lawngreen")
    
    # Definir el formato de las columnas en formato de moneda
    percent_format = "{:.0%}" 
    df_transformed_styled = df_transformed_styled.format({
        'GMROI': percent_format,
    })
    
    # Mostrar el DataFrame estilizado
    st.dataframe(df_transformed_styled, hide_index=True, use_container_width=True)
    
    # Retorna el DataFrame transformado
    return df_transformed

# Función para crear un gráfico de barras que muestra el valor agregado del inventario por código de producto.
def barchart_all_products_gmroi(df_all):
    # Crear un gráfico de barras utilizando Plotly Express (px)
    fig = px.bar(df_all,
                 x='cod_producto',  # Establecer los códigos de producto en el eje x
                 y='GMROI',  # Establecer el EVAI en el eje y
                 title='Valor Agregado del Inventario por Código de Producto'  # Establecer el título del gráfico
                 )

    # Actualizar el eje x para tratar los códigos de productos como categorías (para mantener su orden)
    fig.update_xaxes(type='category')
    
    fig.update_layout(
        yaxis_tickformat='.0%'  # Formato de porcentaje para el eje y.
    )
    fig.update_traces(
        texttemplate='%{value:.1%}',  # Formato de porcentaje en el texto.
        textposition='outside'  # Posición del texto en las barras
    )
    # Mostrar el gráfico en una aplicación web (posiblemente utilizando Streamlit) con el ancho del contenedor ajustado.
    st.plotly_chart(fig, use_container_width=True)

# Muestra la distribución de productos positivos y negativos en función del EVAI.
def piechart_all_products_gmroi(df_all):
    # Calcular el total de productos en el DataFrame
    total = len(df_all)
    
    # Contar la cantidad de productos con EVAI positivo y negativo
    conteo_positivos = len(df_all[df_all['GMROI'] > 0])
    conteo_negativos = len(df_all[df_all['GMROI'] < 0])

    # Crear el gráfico de pastel utilizando Plotly
    fig_pie = go.Figure(go.Pie(
        labels=['Positivos', 'Negativos'],  # Etiquetas para las secciones del gráfico
        values=[conteo_positivos, conteo_negativos],  # Valores de las secciones del gráfico
        pull=[0, 0.1],  # Para separar ligeramente la sección "Negativos" del centro del pastel
        textinfo="percent+value"  # Mostrar el porcentaje y el valor en cada sección
    ))
    
    # Actualizar el título del gráfico para mostrar el total de productos en rojo
    fig_pie.update_layout(title=f"Total de productos <span style='color:red;'>{total}</span>",
                          legend=dict(orientation="h", y=1.1)) # Colocar la leyenda horizontalmente encima del gráfico
    
    # Mostrar el gráfico de pastel 
    st.plotly_chart(fig_pie, use_container_width=True)






