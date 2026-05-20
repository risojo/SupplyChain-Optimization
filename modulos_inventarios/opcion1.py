"""Inventarios - Opción 1: Cálculo de punto de reorden.

Usa los datos cargados en ``st.session_state.datos_pronostico['tendencias']``
(opción 1 del capítulo Pronóstico) y calcula un punto de reorden básico.
"""
import streamlit as st


def render():
    st.subheader("Opción 1: Cálculo de punto de reorden")
    if "tendencias" in st.session_state.datos_pronostico:
        df = st.session_state.datos_pronostico["tendencias"]
        if "Demanda" in df.columns:
            demanda_promedio = df["Demanda"].mean()
        else:
            cols_dem = [c for c in df.columns if str(c).startswith("demanda_mes")]
            if not cols_dem:
                st.error(
                    "No se encontró la columna 'Demanda' ni columnas 'demanda_mes*' "
                    "en los datos cargados."
                )
                return
            demanda_promedio = df[cols_dem].mean(axis=1).mean()

        st.write(f"Demanda promedio: {demanda_promedio:.2f}")
        tiempo_entrega = st.number_input("Tiempo de entrega (días)", value=7)
        punto_reorden = demanda_promedio * tiempo_entrega / 30
        st.write(f"Punto de reorden: {punto_reorden:.2f}")
        st.session_state.datos_inventarios["punto_reorden"] = punto_reorden
    else:
        st.write("Requiere datos de Pronóstico (Opción 1: Lectura de archivo data).")
