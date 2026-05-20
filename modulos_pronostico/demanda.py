"""Módulo de certificación de demanda del capítulo Pronóstico.

Expone ``render()`` para usarse desde ``LRI_inventarios2.0.py``.
"""
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import database
from utils import backend


def _localizar_base_datos():
    """Devuelve la ruta del Excel base intentando varias ubicaciones.

    Primero la ruta configurada en ``database.get_drive``; si no existe,
    cae al ``base_de_datos.xlsx`` que esté junto al script principal.
    """
    username = st.session_state.get("username", "admin")
    ruta = database.get_drive(username)
    if ruta and os.path.exists(ruta):
        return ruta
    fallback = "base_de_datos.xlsx"
    if os.path.exists(fallback):
        return fallback
    return None


def render():
    """Pinta la sección de certificación de datos para pronóstico."""
    st.title("CERTIFICACIÓN DE DATOS PARA PRONÓSTICO")

    ruta_bd = _localizar_base_datos()
    if ruta_bd is None:
        st.error(
            "No se encontró la base de datos. Coloca 'base_de_datos.xlsx' en la "
            "carpeta del programa o configura la ruta en database.get_drive()."
        )
        return

    saved_database = backend.get_transformed_dataframe(ruta_bd)
    saved_database["cod_producto"] = saved_database["cod_producto"].astype(str)

    container = st.container()
    col1, col2, col3 = st.columns(3)

    with col1:
        cat = st.selectbox(
            "Ingresa la categoría que quieres filtrar",
            ["Todos"] + saved_database["cat_producto"].unique().tolist(),
            key="demanda_cat",
        )
        if cat != "Todos":
            df_filtered = saved_database[saved_database["cat_producto"] == cat]
        else:
            df_filtered = saved_database

        subcat = st.selectbox(
            "Ingresa la subcategoría que quieres filtrar",
            ["Todos"] + df_filtered["subcat_producto"].unique().tolist(),
            key="demanda_subcat",
        )
        if subcat != "Todos":
            df_filtered = df_filtered[df_filtered["subcat_producto"] == subcat]

        cod_options = df_filtered["cod_producto"].tolist()
        if not cod_options:
            st.warning("No hay productos para los filtros seleccionados.")
            return

        if "producto" not in st.session_state or st.session_state["producto"] not in cod_options:
            st.session_state["producto"] = cod_options[0]

        selected_prod = st.selectbox(
            "Selecciona un código de producto",
            cod_options,
            index=cod_options.index(st.session_state["producto"]),
            key="demanda_prod",
        )
        st.session_state["producto"] = selected_prod

        descripcion = saved_database[saved_database["cod_producto"] == selected_prod]["desc_producto"].iloc[0]
        categoria = saved_database[saved_database["cod_producto"] == selected_prod]["cat_producto"].iloc[0]
        subcategoria = saved_database[saved_database["cod_producto"] == selected_prod]["subcat_producto"].iloc[0]
        descr = {
            "Descripción": descripcion,
            "Categoría": categoria,
            "Subcategoría": subcategoria,
        }
        descr_df = pd.DataFrame(descr, index=[f"{selected_prod}"]).T
        descr_df.index.name = "Código"
        st.dataframe(descr_df, use_container_width=True)

        columnas_demanda_mes = [c for c in saved_database.columns if c.startswith("demanda_mes")]
        df_demanda = (
            saved_database[saved_database["cod_producto"] == selected_prod][columnas_demanda_mes]
            .iloc[0]
            .astype(int)
        )
        df_demanda.index.name = "Período"
        df_demanda.name = "Demanda"
        st.dataframe(df_demanda, height=458, use_container_width=True)

        promedio = round(df_demanda.mean())
        stdev = round(df_demanda.std(), 2)
        var_coef = round(stdev / promedio, 2) if promedio else 0
        aceptacion = "Si" if var_coef <= 0.3 else "No"
        stats = {
            "Promedio": promedio,
            "Desv estandar": stdev,
            "Coeficiente variac.": var_coef,
            "Se aceptan los datos": aceptacion,
        }
        stats_df = pd.DataFrame(stats, index=["Estadísticas"]).T
        st.dataframe(stats_df, use_container_width=True)

    if aceptacion == "No":
        container.error("Data histórica no apta para hacer pronóstico")

    with col2:
        fig = go.Figure(
            data=[
                go.Bar(
                    x=list(range(1, 13)),
                    y=df_demanda,
                    text=df_demanda,
                    textposition="auto",
                    marker_color="lightgreen",
                )
            ]
        )
        fig.update_traces(texttemplate="%{text}", textposition="outside")
        fig.update_layout(
            title_text="Demanda Mensual",
            xaxis_title="Mes",
            yaxis_title="Demanda",
            xaxis=dict(tickmode="linear", dtick=1),
        )
        st.plotly_chart(fig, use_container_width=True)

        fig = go.Figure(
            data=go.Scatter(
                x=list(range(1, 13)),
                y=df_demanda,
                mode="lines+markers+text",
                text=df_demanda,
                textposition="top center",
                line=dict(color="green"),
                marker=dict(color="green"),
            )
        )
        fig.update_layout(
            title_text="Demanda Mensual",
            xaxis_title="Mes",
            yaxis_title="Demanda",
            xaxis=dict(tickmode="linear", dtick=1),
        )
        st.plotly_chart(fig)

    with col3:
        fig = go.Figure(data=go.Box(y=df_demanda, boxmean=True, name="", marker_color="green"))
        for _, val in enumerate(df_demanda):
            fig.add_annotation(
                x=0,
                y=val,
                text=str(val),
                showarrow=False,
                yshift=10,
                font=dict(color="red", size=10),
            )
        fig.update_layout(
            title_text="Distribución de la Demanda",
            yaxis_title="Demanda",
            showlegend=False,
            yaxis=dict(title="Valores de Demanda", zeroline=False),
            xaxis=dict(tickmode="linear", dtick=1, showticklabels=False),
        )
        st.plotly_chart(fig, use_container_width=True)


if __name__ == "__main__":
    st.set_page_config(page_title="Demanda", page_icon="🏗️", layout="wide")
    render()
