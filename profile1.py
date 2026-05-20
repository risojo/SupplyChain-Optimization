import html
import io
import os
import unicodedata
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import speech_recognition as sr
import streamlit as st
from streamlit_mic_recorder import mic_recorder

# 1. CONFIGURACIÓN DE PÁGINA Y ESTILO DARK
st.set_page_config(page_title="Perfilado de Datos por Voz - LRI", layout="wide")

REF_VIEWPORT_W = 1920
REF_VIEWPORT_H = 1080

# Ruta fija al archivo oficial
ARCHIVO_EXCEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "LRI_data.xlsx")

RESERVA_VERTICAL_REF = 320
USABLE_ROW_H_REF = max(520, REF_VIEWPORT_H - RESERVA_VERTICAL_REF)

# === CORRECCIÓN MAESTRA: Inicializar estados de la sesión con valores por defecto ===
if "lri_man_eje_x" not in st.session_state:
    st.session_state["lri_man_eje_x"] = None
if "lri_man_eje_y" not in st.session_state:
    st.session_state["lri_man_eje_y"] = None
if "lri_man_operacion" not in st.session_state:
    st.session_state["lri_man_operacion"] = "Suma"
if "lri_man_top_n" not in st.session_state:
    st.session_state["lri_man_top_n"] = 0
if "comando_voz_detectado" not in st.session_state:
    st.session_state["comando_voz_detectado"] = None

# Variables para el soporte de Drill-Down (Análisis Multinivel / 3D)
if "drill_down_categoria" not in st.session_state:
    st.session_state["drill_down_categoria"] = None


def _norm_col_ident(nombre: str) -> str:
    """Normaliza cadenas eliminando acentos, espacios y caracteres especiales para comparar."""
    s = str(nombre).lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return (
        s.replace(" ", "")
        .replace("_", "")
        .replace("/", "")
        .replace("-", "")
        .replace(".", "")
    )


def altura_grafico_adaptativa(n: int, viewport_h: int) -> int:
    usable = max(520, viewport_h - RESERVA_VERTICAL_REF)
    if n <= 0: 
        return max(360, min(usable, int(viewport_h * 0.42)))
    px_por_barra = max(6.5, min(20.0, 620.0 / max(n, 6)))
    necesario = int(210 + n * px_por_barra * 1.9)
    relleno = int(usable * (0.88 if n <= 60 else 0.76))
    return int(max(480, min(usable, max(necesario, relleno))))


def fig_ranking_barras(df_resumen: pd.DataFrame, col_cat: str, col_val: str, operacion: str, viewport_h: int, viewport_w: int, base_font_size: int) -> go.Figure:
    d = df_resumen.copy()
    n = len(d)
    chart_col_px = max(260, int((viewport_w - 96) * 0.66))

    if n == 0:
        fig = go.Figure()
        fig.update_layout(height=400, width=chart_col_px, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0f1419")
        return fig

    ys = d[col_val].astype(float).to_numpy()
    
    size_valores = base_font_size - 2
    size_ejes = base_font_size
    size_titulos = base_font_size + 4

    # Añadir un título dinámico si estamos en modo Drill-Down
    titulo_grafico = f"Análisis de {operacion}: {col_val} por {col_cat}"
    if st.session_state["drill_down_categoria"]:
        titulo_grafico += f" (Filtrado por: {st.session_state['drill_down_categoria']})"

    fig = go.Figure(
        go.Bar(
            x=d[col_cat].astype(str), 
            y=ys, 
            text=ys,
            texttemplate='%{text:,.2f}' if ys.max() < 100 else '%{text:,.0f}',
            textposition='outside',       
            textfont=dict(size=size_valores, color="#ffffff"), 
            marker=dict(
                color=ys, 
                colorscale=[
                    [0.0, "#ffffff"], [0.18, "#e8f4fc"], [0.38, "#90caf9"],
                    [0.62, "#2196f3"], [0.82, "#1565c0"], [1.0, "#0d47a1"]
                ], 
                cornerradius=6
            )
        )
    )
    
    fig.update_layout(
        title=dict(
            text=titulo_grafico,
            font=dict(size=size_titulos, color="#ffffff") 
        ),
        height=max(400, altura_grafico_adaptativa(n, viewport_h)), 
        width=chart_col_px, 
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="#0f1419", 
        showlegend=False,
        xaxis=dict(
            tickfont=dict(size=size_ejes, color="#e2e8f0"), 
            title=dict(text=col_cat, font=dict(size=size_ejes + 2, color="#ffffff"))
        ),
        yaxis=dict(
            tickfont=dict(size=size_ejes, color="#e2e8f0"), 
            title=dict(text=operacion, font=dict(size=size_ejes + 2, color="#ffffff"))
        )
    )
    return fig


def render_perfilado_manual_panel(df: pd.DataFrame, dict_ops: dict, viewport_h_ui: int, base_font_size: int) -> None:
    # Título principal adaptativo si hay Drill-Down
    if st.session_state["drill_down_categoria"]:
        st.title(f"Panel de Perfilado: Detalle de Artículos en '{st.session_state['drill_down_categoria']}'")
        if st.button("⬅️ Volver a vista general (Categorías)"):
            st.session_state["drill_down_categoria"] = None
            st.session_state["lri_man_eje_x"] = "categoria"  # Forzar regreso al eje macro
            st.rerun()
    else:
        st.title("Panel de Perfilado de Datos (LRI_data)")
    
    eje_x_real = st.session_state["lri_man_eje_x"]
    eje_y_real = st.session_state["lri_man_eje_y"]
    operacion_real = st.session_state["lri_man_operacion"]
    top_n_real = st.session_state["lri_man_top_n"]

    df_filtrado = df.copy()

    # === APLICACIÓN DE LA LÓGICA DRILL-DOWN (3D) ===
    # Si tenemos guardada una categoría en memoria, filtramos el Excel para ver solo sus artículos
    if st.session_state["drill_down_categoria"] and "categoria" in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado["categoria"] == st.session_state["drill_down_categoria"]]

    val_total = df_filtrado[eje_y_real].sum()
    cats_count = df_filtrado[eje_x_real].nunique()

    c1, c2, c3 = st.columns(3)
    with c1: 
        st.markdown(f"<div class='kpi-card'><div class='kpi-title'>Total {eje_y_real}</div><div class='kpi-value'>{val_total:,.0f}</div></div>", unsafe_allow_html=True)
    with c2: 
        st.markdown(f"<div class='kpi-card'><div class='kpi-title'>Registros Únicos ({eje_x_real})</div><div class='kpi-value'>{cats_count}</div></div>", unsafe_allow_html=True)
    with c3: 
        st.markdown(f"<div class='kpi-card'><div class='kpi-title'>Máximo Detectado</div><div class='kpi-value'>{df_filtrado[eje_y_real].max():,.0f}</div></div>", unsafe_allow_html=True)

    col_tabla, col_grafico = st.columns([1, 2])
    
    df_agrup = df_filtrado.groupby(eje_x_real)[eje_y_real].agg(dict_ops[operacion_real]).reset_index().sort_values(by=eje_y_real, ascending=False)
    
    if top_n_real > 0: 
        df_resumen = df_agrup.head(top_n_real)
    else: 
        df_resumen = df_agrup

    with col_tabla:
        st.markdown(f'<div class="lri-tabla-col"><div class="lri-tabla-title" style="font-size: {base_font_size + 2}px;">Tabla de {operacion_real}</div>', unsafe_allow_html=True)
        
        fmt_string = "{:,.2f}" if df_resumen[eje_y_real].max() < 100 else "{:,.0f}"
        styled_df = df_resumen.style.format({eje_y_real: fmt_string}).hide(axis="index")
        
        st.markdown('<div class="lri-html-table-scroll-container">', unsafe_allow_html=True)
        st.table(styled_df)
        st.markdown('</div></div>', unsafe_allow_html=True)

    with col_grafico:
        fig = fig_ranking_barras(df_resumen, eje_x_real, eje_y_real, operacion_real, viewport_h=viewport_h_ui, viewport_w=REF_VIEWPORT_W, base_font_size=base_font_size)
        st.plotly_chart(fig, use_container_width=True)


# 3. CEREBRO DE VOZ 
def procesar_comando_voz_estructurado(comando_texto: str, df: pd.DataFrame):
    cmd = _norm_col_ident(comando_texto)
    st.session_state["comando_voz_detectado"] = comando_texto

    if "prom" in cmd: 
        st.session_state["lri_man_operacion"] = "Promedio"
    elif "max" in cmd: 
        st.session_state["lri_man_operacion"] = "Máximo"
    elif "min" in cmd: 
        st.session_state["lri_man_operacion"] = "Mínimo"
    elif "sum" in cmd or "vent" in cmd or "tot" in cmd or "unid" in cmd or "bult" in cmd or "cant" in cmd or "deman" in cmd: 
        st.session_state["lri_man_operacion"] = "Suma"

    cols_texto = df.select_dtypes(include=["object", "category"]).columns.tolist()
    cols_num = df.select_dtypes(include=["number"]).columns.tolist()

    columna_seleccionada = None

    if "bult" in cmd:
        if "vend" in cmd: columna_seleccionada = "bultos vendidos"
        elif "tarim" in cmd: columna_seleccionada = "bultos tarima"
        elif "prom" in cmd: columna_seleccionada = "inventario promedio bultos"
        elif "fin" in cmd: columna_seleccionada = "inventario final bulto"
        else: columna_seleccionada = "bultos vendidos" if "bultos vendidos" in cols_num else cols_num[0]
    elif "unid" in cmd or "cant" in cmd:
        columna_seleccionada = "unidades vendidas"
    elif "util" in cmd or "marg" in cmd or "brut" in cmd:
        if "cost" in cmd: columna_seleccionada = "ventas costo"
        elif "vent" in cmd: columna_seleccionada = "margen utilidad ventas"
        else: columna_seleccionada = "margen bruto total"
    elif "vent" in cmd:
        if "cost" in cmd or "al cost" in cmd: columna_seleccionada = "ventas costo"
        else: columna_seleccionada = "ventas totales"
    elif "deman" in cmd:
        for i in range(1, 13):
            if f"mes{i}" in cmd or f"mes {i}" in cmd or f" {i}" in cmd:
                columna_seleccionada = f"demanda mes {i}"
                break
        if not columna_seleccionada: columna_seleccionada = "demanda mes 1"

    if not columna_seleccionada:
        for cn in cols_num:
            if _norm_col_ident(cn) in cmd:
                columna_seleccionada = cn
                break

    if columna_seleccionada and columna_seleccionada in cols_num:
        st.session_state["lri_man_eje_y"] = columna_seleccionada

    # === CAPTURA DE COMANDO POR VOZ PARA EL DRILL-DOWN ===
    # Si el usuario dice por ejemplo "desplegame los artículos" o "ver artículos", activamos el cambio dinámico
    if "articulo" in cmd or "producto" in cmd:
        if st.session_state["drill_down_categoria"]:
            # Si ya hay una categoría guardada, forzamos el eje X a la descripción detallada
            for ct in cols_texto:
                norm_ct = _norm_col_ident(ct)
                if "desc" in norm_ct or "prod" in norm_ct or "cod" in norm_ct:
                    st.session_state["lri_man_eje_x"] = ct
                    return

    # Mapeo Inteligente Eje X estándar
    for ct in cols_texto:
        norm_ct = _norm_col_ident(ct)
        
        if "sub" in cmd:
            if "sub" in norm_ct:
                st.session_state["lri_man_eje_x"] = ct  
                break
        elif "cat" in cmd and "sub" not in cmd:
            if "cat" in norm_ct and "sub" not in norm_ct:
                st.session_state["lri_man_eje_x"] = ct  
                break
        elif ("cod" in cmd or "prod" in cmd) and "cod" in norm_ct:
            st.session_state["lri_man_eje_x"] = ct  
            break
        elif "desc" in cmd and "desc" in norm_ct:
            st.session_state["lri_man_eje_x"] = ct  
            break
        elif "prov" in cmd and "prov" in norm_ct:
            st.session_state["lri_man_eje_x"] = ct  
            break
        elif "pais" in cmd and "pais" in norm_ct:
            st.session_state["lri_man_eje_x"] = ct  
            break
        elif "clas" in cmd and "clase" in norm_ct:
            st.session_state["lri_man_eje_x"] = ct  
            break
        elif norm_ct in cmd:
            st.session_state["lri_man_eje_x"] = ct
            break


def cargar_datos() -> tuple[Optional[pd.DataFrame], Optional[str]]:
    if not os.path.isfile(ARCHIVO_EXCEL_PATH): 
        return None, f"No se encontró el archivo '{os.path.basename(ARCHIVO_EXCEL_PATH)}' en el directorio."
    try: 
        df_read = pd.read_excel(ARCHIVO_EXCEL_PATH, engine="openpyxl")
        
        # Limpieza interna automática de nombres
        nuevos_nombres = {}
        for col in df_read.columns:
            col_norm = col.lower().strip()
            if "subcat" in col_norm or "sub_cat" in col_norm:
                nuevos_nombres[col] = "subcategoria"
            elif "cat_" in col_norm and "sub" not in col_norm:
                nuevos_nombres[col] = "categoria"
                
        if nuevos_nombres:
            df_read.rename(columns=nuevos_nombres, inplace=True)
            
        return df_read, None
    except Exception as e: 
        return None, str(e)


# CONTROL DE FLUJO PRINCIPAL
df, error_carga = cargar_datos()

if df is not None:
    cols_texto = df.select_dtypes(include=["object", "category"]).columns.tolist()
    cols_num = df.select_dtypes(include=["number"]).columns.tolist()

    # Garantizar estados iniciales válidos
    if st.session_state["lri_man_eje_x"] not in cols_texto:
        st.session_state["lri_man_eje_x"] = cols_texto[0] if cols_texto else None
    if st.session_state["lri_man_eje_y"] not in cols_num:
        st.session_state["lri_man_eje_y"] = cols_num[0] if cols_num else None

    with st.sidebar:
        st.title("⚙️ Configuración LRI")
        st.markdown("### 🎙️ Control por Voz Activo")
        
        audio = mic_recorder(
            start_prompt="Presiona para Hablar 🎙️",
            stop_prompt="Procesar Comando 🛑",
            key="lri_mic_console",
            format="wav"
        )
        
        if audio is not None:
            r = sr.Recognizer()
            try:
                with sr.AudioFile(io.BytesIO(audio["bytes"])) as source:
                    r.adjust_for_ambient_noise(source, duration=0.2)
                    audio_data = r.record(source)
                texto_dictado = r.recognize_google(audio_data, language="es-CR")
                procesar_comando_voz_estructurado(texto_dictado, df)
                st.sidebar.success("Comando aplicado.")
            except sr.UnknownValueError:
                st.sidebar.error("No se entendió el audio. Intente de nuevo, más claro.")
            except sr.RequestError:
                st.sidebar.error("Error de conexión con el servicio.")
            except Exception as e:
                st.sidebar.error(f"Error al procesar audio: {e}")

        if st.session_state["comando_voz_detectado"]:
            st.info(f"Escuchado: *\"{st.session_state['comando_voz_detectado']}\"*")

        st.divider()
        st.markdown("##### Ajustes Manuales")
        
        # === SOLUCIÓN AL CONFLICTO SINCRO (Voz vs Manual) ===
        # Leemos el estado actual del session_state para colocarlo como índice predeterminado
        idx_x = cols_texto.index(st.session_state["lri_man_eje_x"]) if st.session_state["lri_man_eje_x"] in cols_texto else 0
        idx_y = cols_num.index(st.session_state["lri_man_eje_y"]) if st.session_state["lri_man_eje_y"] in cols_num else 0
        
        ops_lista = ["Suma", "Promedio", "Máximo", "Mínimo"]
        idx_op = ops_lista.index(st.session_state["lri_man_operacion"]) if st.session_state["lri_man_operacion"] in ops_lista else 0

        # Almacenamos la selección del usuario en variables normales y luego actualizamos el estado
        sel_x = st.selectbox("Dimensión de Análisis (Eje X)", options=cols_texto, index=idx_x)
        sel_y = st.selectbox("Métrica de Negocio (Eje Y)", options=cols_num, index=idx_y)
        sel_op = st.radio("Operación", ops_lista, index=idx_op)
        
        st.session_state["lri_man_eje_x"] = sel_x
        st.session_state["lri_man_eje_y"] = sel_y
        st.session_state["lri_man_operacion"] = sel_op
        
        dict_ops = {"Suma": "sum", "Promedio": "mean", "Máximo": "max", "Mínimo": "min"}
        
        st.number_input("Top N elementos (0 = ver todos)", min_value=0, max_value=50000, value=int(st.session_state["lri_man_top_n"]), step=5, key="lri_man_top_n_widget")
        st.session_state["lri_man_top_n"] = st.session_state["lri_man_top_n_widget"]

        # Selector manual extra para controlar el Drill-Down desde el menú lateral si se desea
        st.divider()
        st.markdown("##### Filtro 3D (Drill-Down)")
        if "categoria" in cols_texto:
            lista_cats = ["Ver Todas"] + sorted(df["categoria"].dropna().unique().tolist())
            idx_cat_drill = lista_cats.index(st.session_state["drill_down_categoria"]) if st.session_state["drill_down_categoria"] in lista_cats else 0
            sel_drill = st.selectbox("Profundizar por Categoría", options=lista_cats, index=idx_cat_drill)
            
            if sel_drill == "Ver Todas":
                st.session_state["drill_down_categoria"] = None
            else:
                st.session_state["drill_down_categoria"] = sel_drill
                # Si el usuario selecciona manualmente una categoría para profundizar, le sugerimos ver artículos
                for ct in cols_texto:
                    if _norm_col_ident(ct) in ["descripcion", "descripcionarticulo", "articulo"]:
                        st.session_state["lri_man_eje_x"] = ct

        st.divider()
        st.markdown("##### Visibilidad")
        base_font_size = st.slider("Tamaño de Letra (px)", min_value=12, max_value=32, value=15, step=1, key="lri_fontsize_ui")
        viewport_h_ui = st.select_slider("Alto Pantalla (px)", options=[720, 768, 900, 1080, 1200, 1440], value=1080, key="lri_man_viewport_h")

    st.markdown(
        f"""
        <style>
        .stApp {{ background-color: #0e1117; color: white; }}
        .kpi-card {{ background-color: #1e2130; padding: 18px; border-radius: 8px; border: 1px solid #2d3142; text-align: center; margin-bottom: 12px; }}
        .kpi-title {{ font-size: 13px; color: #a1a1aa; text-transform: uppercase; margin-bottom: 8px; letter-spacing: 0.5px; }}
        .kpi-value {{ font-size: 26px; font-weight: bold; color: #ffffff; }}
        .block-container {{ padding-top: 1rem !important; padding-bottom: 0.5rem !important; max-width: min(100%, {REF_VIEWPORT_W}px) !important; margin: auto !important; }}
        
        .lri-tabla-col {{ border: 1px solid #2d3142; border-radius: 8px; background: #131722; padding: 8px; }}
        .lri-tabla-title {{ font-weight: 600; color: #f8fafc; padding: 0.5rem 1rem; border-bottom: 1px solid #2d3142; background: #161b26; margin-bottom: 8px; }}
        .lri-html-table-scroll-container {{ max-height: 520px; overflow-y: auto; }}
        
        [data-testid="stTable"] table {{ width: 100% !important; font-size: {base_font_size}px !important; border-collapse: collapse !important; }}
        [data-testid="stTable"] th {{ background-color: #1e293b !important; color: #ffffff !important; font-size: {base_font_size}px !important; padding: 8px !important; text-align: left; }}
        [data-testid="stTable"] td {{ color: #cbd5e1 !important; font-size: {base_font_size}px !important; padding: 8px !important; border-bottom: 1px solid #2d3142 !important; }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    render_perfilado_manual_panel(df=df, dict_ops=dict_ops, viewport_h_ui=viewport_h_ui, base_font_size=base_font_size)
else:
    st.error(f"Error al inicializar la aplicación: {error_carga}")
