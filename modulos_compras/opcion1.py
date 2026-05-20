"""Compras - Opción 1: Generar órdenes de compra.

Usa el ``punto_reorden`` calculado en el capítulo de Inventarios (opción 1).
"""
import streamlit as st


def render():
    st.subheader("Opción 1: Generar órdenes de compra")
    if "punto_reorden" in st.session_state.datos_inventarios:
        st.write(
            f"Basado en punto de reorden: "
            f"{st.session_state.datos_inventarios['punto_reorden']:.2f}"
        )
    else:
        st.write("Requiere datos de Inventarios (Opción 1: Punto de reorden).")
