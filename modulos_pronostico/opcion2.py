"""Pronóstico - Opción 2: Gráfico de tendencia.

Permite escoger un artículo (por código, categoría o subcategoría) y
dibuja la demanda mensual de los 12 meses con una barra resaltada para
el máximo (verde) y el mínimo (rojo).

Los datos provienen de ``st.session_state.datos_pronostico['tendencias']``,
poblado por la Opción 1 (Carga de datos). Si todavía no se han cargado,
intenta leer directamente ``base_de_datos.xlsx``.
"""
import os

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from utils import backend


LRI_GRAF_TEND_FIGSIZE = (5.0, 1.9)
LRI_BUSQUEDA_MAX_WIDTH_PX = 400


def _ruta_archivo_pronostico():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    proyecto_dir = os.path.dirname(base_dir)
    return os.path.join(proyecto_dir, "base_de_datos.xlsx")


def _cargar_dataframe_tendencias():
    if st.session_state.datos_pronostico.get("tendencias") is not None:
        return st.session_state.datos_pronostico["tendencias"].copy()
    p = _ruta_archivo_pronostico()
    if not os.path.exists(p):
        return None
    try:
        df = backend.get_transformed_dataframe(p)
    except Exception:
        df = pd.read_excel(p)
    if "cod_producto" in df.columns:
        df["cod_producto"] = df["cod_producto"].astype(str)
    return df


def _grafico_barras_tendencia_demanda(mes_labels, demandas, titulo=""):
    """Barras color celeste, figura y ejes con fondo negro."""
    n = len(mes_labels)
    x = range(n)
    y_max = max(demandas) if demandas and max(demandas) > 0 else 1
    fig, ax = plt.subplots(
        figsize=LRI_GRAF_TEND_FIGSIZE, facecolor="black", dpi=110
    )
    fig.patch.set_facecolor("black")
    ax.set_facecolor("black")
    color_barra = "#5DADE2"
    color_max = "#7DFF7D"
    color_min = "#FF3B30"
    colores = [color_barra for _ in demandas]
    if demandas:
        idx_max = max(range(len(demandas)), key=lambda i: demandas[i])
        idx_min = min(range(len(demandas)), key=lambda i: demandas[i])
        colores[idx_min] = color_min
        colores[idx_max] = color_max
    ax.bar(x, demandas, color=colores, edgecolor="#3D8AB8", linewidth=0.35)
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


def render():
    st.subheader("Opción 2: Gráfico de tendencia")
    st.caption(
        "Demanda de cada mes (demanda_mes1 … demanda_mes12) por artículo. "
        "Elija el artículo por código, categoría o subcategoría. "
        "Use la Opción 1 para cargar datos, o deje archivo2.xlsx en la carpeta del programa."
    )
    data = _cargar_dataframe_tendencias()
    if data is None or data.empty:
        st.info(
            "Cargue los datos con la Opción 1 (Carga de datos) o coloque "
            "'base_de_datos.xlsx' en la carpeta del proyecto."
        )
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
                ("Código de producto", "Categoría", "Subcategoría"),
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
