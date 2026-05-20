"""Módulo de distribución normal del capítulo Pronóstico.

Expone ``render()`` para usarse desde ``LRI_inventarios2.0.py``.
"""
import os
import time

import numpy as np
import pandas as pd
import plotly.graph_objs as go
import streamlit as st

import database
from utils import backend


def _localizar_base_datos():
    username = st.session_state.get("username", "admin")
    ruta = database.get_drive(username)
    if ruta and os.path.exists(ruta):
        return ruta
    fallback = "base_de_datos.xlsx"
    if os.path.exists(fallback):
        return fallback
    return None


def _graficar_dist(promedio, stdev, nombre="Distribución"):
    media = promedio
    desviacion = stdev
    intervalo_tiempo = 0.5
    num_datos = [50, 100, 250, 500, 1000, 1500, 2500]
    container = st.empty()
    for cantidad_datos in num_datos:
        datos = np.random.normal(media, desviacion, cantidad_datos)
        histograma = go.Histogram(
            x=datos,
            marker=dict(line=dict(color="black", width=1)),
            marker_color="lightgreen",
        )
        layout = go.Layout(title=f"{nombre}", showlegend=False)
        fig = go.Figure(data=[histograma], layout=layout)
        container.plotly_chart(fig, use_container_width=True)
        time.sleep(intervalo_tiempo)


def render():
    """Pinta la sección de distribución normal del producto seleccionado."""
    st.title("Distribución normal")

    if "producto" not in st.session_state:
        st.error(
            "Debes escoger un producto primero en la opción 'Demanda' del menú "
            "de Pronóstico."
        )
        return

    ruta_bd = _localizar_base_datos()
    if ruta_bd is None:
        st.error(
            "No se encontró la base de datos. Coloca 'base_de_datos.xlsx' en la "
            "carpeta del programa o configura la ruta en database.get_drive()."
        )
        return

    saved_database = backend.get_transformed_dataframe(ruta_bd)
    saved_database["cod_producto"] = saved_database["cod_producto"].astype(str)
    producto = str(st.session_state["producto"])

    columnas_demanda_mes = [c for c in saved_database.columns if c.startswith("demanda_mes")]
    fila = saved_database[saved_database["cod_producto"] == producto]
    if fila.empty:
        st.error(f"El producto '{producto}' no se encuentra en la base de datos.")
        return

    df_demanda = fila[columnas_demanda_mes].iloc[0].astype(int)
    df_demanda.index = [f"mes {n}" for n in range(1, 13)]
    df_demanda.name = "Demanda"

    df_demanda_horizontal = df_demanda.to_frame().T
    st.dataframe(df_demanda_horizontal, use_container_width=True)

    col1, col2 = st.columns([0.3, 0.7])
    with col1:
        descripcion = fila["desc_producto"].iloc[0]
        promedio = round(df_demanda.mean())
        stdev = round(df_demanda.std(), 2)
        mas3_sigma = round(promedio + stdev * 3, 2)
        menos3_sigma = round(promedio - stdev * 3, 2)
        stats = {
            "Descripción": descripcion,
            "Promedio": promedio,
            "Desv estandar": stdev,
            "+3 sigma": mas3_sigma,
            "-3 sigma": menos3_sigma,
        }
        stats_df = pd.DataFrame(stats, index=[f"{producto}"]).T
        stats_df.index.name = "Código"
        st.dataframe(stats_df, use_container_width=True)

    with col2:
        with st.form("normal_form"):
            with st.container():
                c1, c2, c3 = st.columns([0.6, 0.2, 0.2])
                with c1:
                    st.write("")
                with c2:
                    st.write("Mean %")
                with c3:
                    st.write("Desviación %")
            with st.container():
                c1, c2, c3 = st.columns([0.6, 0.2, 0.2])
                with c1:
                    st.write("Historico")
                with c2:
                    st.write(round(promedio, 2))
                with c3:
                    st.write(round(stdev, 2))
            with st.container():
                c1, c2, c3 = st.columns([0.6, 0.2, 0.2])
                with c1:
                    st.write("Crecimiento")
                with c2:
                    mean_perc_cre = st.number_input(
                        "", step=1, label_visibility="collapsed", key="cremean"
                    )
                with c3:
                    std_perc_cre = st.number_input(
                        "", step=1, label_visibility="collapsed", key="crestd"
                    )
            with st.container():
                c1, c2, c3 = st.columns([0.6, 0.2, 0.2])
                with c1:
                    st.write("Historico con crecimiento")
                with c2:
                    meanh_con_creci = round(promedio * (mean_perc_cre / 100), 2)
                    st.write(meanh_con_creci)
                with c3:
                    stdh_con_creci = round(stdev * (std_perc_cre / 100), 2)
                    st.write(stdh_con_creci)
            with st.container():
                c1, c2, c3 = st.columns([0.6, 0.2, 0.2])
                with c1:
                    st.write("Competencia")
                with c2:
                    mean_perc_com = st.number_input(
                        "", step=1, label_visibility="collapsed", key="commean"
                    )
                with c3:
                    std_perc_com = st.number_input(
                        "", step=1, label_visibility="collapsed", key="comstd"
                    )
            with st.container():
                c1, c2, c3 = st.columns([0.6, 0.2, 0.2])
                with c1:
                    st.write("Historico con competencia")
                with c2:
                    incre_comp_mean = round(promedio * (mean_perc_com / 100), 2)
                    st.write(incre_comp_mean)
                with c3:
                    incre_comp_std = round(stdev * (std_perc_com / 100), 2)
                    st.write(incre_comp_std)
            with st.container():
                c1, c2, c3 = st.columns([0.6, 0.2, 0.2])
                with c1:
                    st.write("Distribución con crecimiento")
                with c2:
                    meanh_con_creciyprom = round(promedio + meanh_con_creci, 2)
                    st.write(meanh_con_creciyprom)
                with c3:
                    var_resta = stdev ** 2 - stdh_con_creci ** 2
                    stdh_con_creciystd = round(var_resta ** 0.5 if var_resta > 0 else 0, 2)
                    st.write(stdh_con_creciystd)
            with st.container():
                c1, c2, c3 = st.columns([0.6, 0.2, 0.2])
                with c1:
                    st.write("Distribución con crecimiento y competencia")
                with c2:
                    meanh_con_creciyprom_con_com = round(
                        meanh_con_creciyprom - incre_comp_mean, 2
                    )
                    st.write(meanh_con_creciyprom_con_com)
                with c3:
                    var_resta2 = stdh_con_creciystd ** 2 - incre_comp_std ** 2
                    stdh_con_creciystd_con_com = round(
                        var_resta2 ** 0.5 if var_resta2 > 0 else 0, 2
                    )
                    st.write(stdh_con_creciystd_con_com)

            submitted = st.form_submit_button("Enviar")

    if submitted:
        c1, c2, c3 = st.columns(3)
        with c1:
            _graficar_dist(promedio, stdev)
        with c2:
            _graficar_dist(
                meanh_con_creciyprom,
                stdh_con_creciystd,
                "Distribución con crecimiento",
            )
        with c3:
            _graficar_dist(
                meanh_con_creciyprom_con_com,
                stdh_con_creciystd_con_com,
                "Distribución con crecimiento y competencia",
            )


if __name__ == "__main__":
    st.set_page_config(page_title="Normal", page_icon="🏗️", layout="wide")
    render()
