"""LRI Inventarios — app Streamlit file-based (sin login ni base de datos).

Versión de trabajo del módulo de Inventarios. Reusa la lógica analítica del
proyecto original del freelance, pero leyendo directamente el Excel maestro en
``data/sources/template_inventarios.xlsx`` (mismo enfoque que Perfilado).

Ejecutar:
    streamlit run modules/inventarios/inventario_app.py

    En el navegador: http://localhost:8501 (o el puerto que indique la terminal)
"""
from __future__ import annotations

import io
import os
import sys
from textwrap import dedent
from typing import Callable

import pandas as pd
import numpy as np
import plotly.express as px
import streamlit as st

try:
    from audio_recorder_streamlit import audio_recorder

    _AUDIO_RECORDER_DISPONIBLE = True
except ImportError:
    audio_recorder = None  # type: ignore[misc, assignment]
    _AUDIO_RECORDER_DISPONIBLE = False

# Permite importar data_loader tanto si se ejecuta como script suelto
# (streamlit run modules/inventarios/inventario_app.py) como dentro del paquete.
_DIR_ACTUAL = os.path.dirname(os.path.abspath(__file__))
if _DIR_ACTUAL not in sys.path:
    sys.path.insert(0, _DIR_ACTUAL)

import data_loader  # noqa: E402
import parametros  # noqa: E402
import scorecard  # noqa: E402
import ui_theme  # noqa: E402

ARCHIVO_DRIVERS_GUARDADO = scorecard.ARCHIVO_DRIVERS_GUARDADO

st.set_page_config(page_title="LRI Inventory Pro", page_icon="📦", layout="wide")

ESCALA_INTERFAZ_PCT = 100
# Activar cuando exista procesamiento de comandos de voz para Inventarios.
INV_CONTROL_VOZ_HABILITADO = False
_VOICE_PAUSA_SILENCIO_SEG = 3.0


def _tabla_font_px() -> int:
    """Tamaño de letra de campos (controlado por slider en sidebar)."""
    return ui_theme.font_campos_px()


def _limpiar_claves_widgets_parametros() -> None:
    parametros.limpiar_claves_widgets()


def _inyectar_css_ui() -> None:
    st.markdown(
        ui_theme.css_interfaz(ESCALA_INTERFAZ_PCT, _tabla_font_px()),
        unsafe_allow_html=True,
    )


PALETA = [
    "#2196f3", "#22c55e", "#eab308", "#ef4444", "#a855f7", "#06b6d4",
    "#f97316", "#84cc16", "#ec4899", "#14b8a6",
]


def _inicializar_datos_en_sesion() -> None:
    """Carga por defecto la primera vez (mismo patrón que profile1)."""
    if "inv_df_datos" in st.session_state:
        return
    df, err = _cargar_datos_con_cache()
    st.session_state["inv_df_datos"] = df
    st.session_state["inv_error_carga"] = err
    st.session_state["inv_nombre_archivo"] = (
        data_loader.NOMBRE_ARCHIVO_DEFECTO if df is not None else None
    )


@st.cache_data(show_spinner=False)
def _cargar_datos_con_cache() -> tuple[pd.DataFrame | None, str | None]:
    """Evita releer el Excel en cada rerun si el archivo no cambió."""
    ruta = data_loader.ARCHIVO_EXCEL_PATH
    if not os.path.isfile(ruta):
        return None, (
            f"No se encontró `{data_loader.NOMBRE_ARCHIVO_DEFECTO}` en data/sources. "
            "Suba un Excel con la misma estructura de columnas."
        )
    mtime = os.path.getmtime(ruta)
    return _cargar_excel_cached(ruta, mtime)


@st.cache_data(show_spinner=False)
def _cargar_excel_cached(ruta: str, mtime: float) -> tuple[pd.DataFrame | None, str | None]:
    del mtime  # clave de invalidación por fecha de modificación
    return data_loader.cargar_datos(ruta)


def _limpiar_estado_sesion_inventarios(*, incluir_datos: bool = True) -> None:
    """Quita claves de parámetros, drivers y (opcional) datos Excel de session_state."""
    prefixes = ("inv_param_", "inv_sc_drv_", "inv_asig_drv_")
    exactas = {
        "inv_parametros",
        "inv_widgets_param_ok",
        "inv_calc_fingerprint",
        "inv_upload_id",
        "inv_asignacion_fingerprint",
        scorecard.CLAVE_EDITOR_ASIGNACION,
        scorecard.CLAVE_DF_ASIGNACION,
    }
    if incluir_datos:
        exactas |= {"inv_df_datos", "inv_error_carga", "inv_nombre_archivo"}
    for key in list(st.session_state.keys()):
        if not isinstance(key, str):
            continue
        if key in exactas or key.startswith(prefixes):
            del st.session_state[key]


def _reiniciar_plantilla_completa() -> None:
    """Excel ``template_inventarios.xlsx`` + parámetros estándar (sin guardados locales)."""
    _limpiar_estado_sesion_inventarios(incluir_datos=True)
    _cargar_datos_con_cache.clear()
    _cargar_excel_cached.clear()

    params = parametros.reiniciar_a_defaults(borrar_guardado_local=True)
    if os.path.isfile(ARCHIVO_DRIVERS_GUARDADO):
        try:
            os.remove(ARCHIVO_DRIVERS_GUARDADO)
        except OSError:
            pass

    df, err = _cargar_datos_con_cache()
    st.session_state["inv_df_datos"] = df
    st.session_state["inv_error_carga"] = err
    st.session_state["inv_nombre_archivo"] = (
        data_loader.NOMBRE_ARCHIVO_DEFECTO if df is not None else None
    )
    if df is not None:
        parametros.restaurar_en_session_state(params, df)
    else:
        parametros.restaurar_en_session_state(params, None)
    st.rerun()


def _sidebar_cargar_datos() -> None:
    """Subir Excel; si no hay archivo, usa el designado en data/sources/."""
    st.markdown("##### 📁 Cargar datos")
    archivo_subido = st.file_uploader(
        "Archivo Excel",
        type=["xlsx", "xls"],
        help=(
            f"Si no sube archivo, se usa `{data_loader.NOMBRE_ARCHIVO_DEFECTO}` del proyecto."
        ),
    )
    if archivo_subido is not None:
        upload_id = (archivo_subido.name, len(archivo_subido.getvalue()))
        if st.session_state.get("inv_upload_id") != upload_id:
            df_up, err_up = data_loader.cargar_datos_desde_upload(archivo_subido.getvalue())
            if err_up:
                st.session_state["inv_error_carga"] = err_up
                st.error(err_up)
            else:
                st.session_state["inv_df_datos"] = df_up
                st.session_state["inv_error_carga"] = None
                st.session_state["inv_upload_id"] = upload_id
                st.session_state["inv_nombre_archivo"] = archivo_subido.name
                st.session_state.pop("inv_parametros", None)
                st.session_state.pop("inv_widgets_param_ok", None)
                parametros.invalidar_cache_calculados()
                _limpiar_claves_widgets_parametros()
                st.rerun()
        st.caption(f"Archivo: {archivo_subido.name}")
    else:
        if st.session_state.get("inv_upload_id") is not None:
            st.session_state.pop("inv_upload_id", None)
            df_def, err_def = _cargar_datos_con_cache()
            st.session_state["inv_df_datos"] = df_def
            st.session_state["inv_error_carga"] = err_def
            st.session_state["inv_nombre_archivo"] = (
                data_loader.NOMBRE_ARCHIVO_DEFECTO if df_def is not None else None
            )
            st.session_state.pop("inv_parametros", None)
            st.session_state.pop("inv_widgets_param_ok", None)
            parametros.invalidar_cache_calculados()
            _limpiar_claves_widgets_parametros()
            st.rerun()
        nombre_def = os.path.basename(data_loader.ARCHIVO_EXCEL_PATH)
        st.caption(f"Por defecto: {nombre_def}")

    if st.button(
        "↺ Restaurar plantilla (Excel + parámetros)",
        use_container_width=True,
        help=(
            f"Recarga `{data_loader.NOMBRE_ARCHIVO_DEFECTO}` y restaura los valores "
            "estándar de parámetros (borra guardados locales y asignación de drivers)."
        ),
    ):
        _reiniciar_plantilla_completa()


def _css_control_voz_sidebar() -> str:
    """Micrófono compacto en fila con el título (mismo patrón que profile1)."""
    return """
<style>
section[data-testid="stSidebar"] .lri-voz-row [data-testid="column"] {
    padding-top: 0 !important;
    padding-bottom: 0 !important;
}
section[data-testid="stSidebar"] .lri-voz-row [data-testid="stCustomComponent"] {
    margin: 0 !important;
    padding: 0 !important;
    background: transparent !important;
}
section[data-testid="stSidebar"] .lri-voz-row [data-testid="stCustomComponent"] iframe {
  height: 3.25rem !important;
  min-height: 3.25rem !important;
  max-height: 3.25rem !important;
  background: transparent !important;
  border: none !important;
}
section[data-testid="stSidebar"] .lri-voz-row [data-testid="stCustomComponent"] {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}
</style>
"""


def _render_control_voz_sidebar(_df: pd.DataFrame) -> None:
    """Control por voz (misma fila título + micrófono que profile1)."""
    if not INV_CONTROL_VOZ_HABILITADO or not _AUDIO_RECORDER_DISPONIBLE:
        return

    st.markdown(_css_control_voz_sidebar(), unsafe_allow_html=True)
    st.divider()
    st.markdown('<div class="lri-voz-row">', unsafe_allow_html=True)
    col_tit, col_mic = st.columns([1.2, 0.55], gap="small", vertical_alignment="center")
    with col_tit:
        st.markdown(
            dedent(
                """\
                <div style="color:#ffffff;line-height:1.25;">
                  <div style="font-size:1.02rem;font-weight:700;margin:0;">🎙️ Control por Voz Activo</div>
                  <div style="font-size:0.78rem;font-weight:400;color:#e2e8f0;margin-top:2px;">
                    Darle un clic para hablar
                  </div>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )
    with col_mic:
        audio = audio_recorder(
            text="",
            pause_threshold=_VOICE_PAUSA_SILENCIO_SEG,
            energy_threshold=0.01,
            sample_rate=44100,
            neutral_color="#FFFFFF",
            recording_color="#22c55e",
            icon_name="microphone",
            icon_size="4x",
            key="inv_mic_console",
        )
        audio_bytes = audio.get("bytes") if isinstance(audio, dict) else audio

    st.markdown("</div>", unsafe_allow_html=True)

    if audio_bytes:
        st.info("Comandos de voz para Inventarios: en desarrollo.")

    if st.session_state.get("inv_comando_voz_detectado"):
        st.info(f'Instrucción: *"{st.session_state["inv_comando_voz_detectado"]}"*')


def _fmt_moneda(v: float) -> str:
    return f"$ {v:,.0f}"


def _exportar_excel(df: pd.DataFrame, hoja: str = "datos") -> bytes:
    salida = io.BytesIO()
    with pd.ExcelWriter(salida, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=hoja, index=False)
    salida.seek(0)
    return salida.getvalue()


def _formatos_tabla_completa(df: pd.DataFrame) -> dict[str, str]:
    """Formato por columna para la tabla completa (mismos nombres que Perfilado)."""
    fmt: dict[str, str] = {}
    for col in df.columns:
        if col not in df.select_dtypes(include="number").columns:
            continue
        cl = col.lower()
        if "demanda mes" in cl:
            fmt[col] = "{:,.0f}"
        elif cl in ("margen utilidad ventas", "factor escazes"):
            fmt[col] = "{:.0%}"
        elif cl in ("rotacion", "meses inventario"):
            fmt[col] = "{:.2f}" if col == "rotacion" else "{:.1f}"
        elif "cubicaje" in cl:
            fmt[col] = "{:.2f}"
        elif any(
            k in cl
            for k in (
                "ventas", "costo", "margen", "precio", "valor inventario",
                "inventario promedio", "inventario final", "transito",
            )
        ):
            fmt[col] = "$ {:,.2f}" if "precio" in cl or "costo unitario" in cl else "$ {:,.0f}"
        elif "empaque" in cl or "bultos tarima" in cl or "ordenes" in cl or "tiempo" in cl:
            fmt[col] = "{:,.0f}"
        else:
            fmt[col] = "{:,.2f}"
    return fmt


# ---------------------------------------------------------------------------
# Vistas
# ---------------------------------------------------------------------------
def vista_base_datos(df: pd.DataFrame, _params: dict) -> None:
    st.caption(
        "Tabla completa desde `template_inventarios.xlsx`. "
        "Revise el paso 1 (parámetros) antes de analizar drivers."
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("SKUs", f"{df['codigo'].nunique():,}")
    c2.metric("Categorías", f"{df['categoria'].nunique():,}")
    c3.metric("Ventas totales", _fmt_moneda(df["ventas totales"].sum()))
    c4.metric("Margen bruto", _fmt_moneda(df["margen bruto total"].sum()))
    c5.metric("Valor inv. promedio", _fmt_moneda(df["valor inventario promedio"].sum()))

    st.divider()

    n_entrada = len(data_loader.COLUMNAS_NUMERICAS) + len(data_loader.COLUMNAS_TEXTO)
    n_calc = len(data_loader.COLUMNAS_CALCULADAS)
    st.caption(
        f"Tabla completa: **{len(df.columns)} columnas** "
        f"({n_entrada} de entrada + {n_calc} calculadas). "
        "Desplácese horizontalmente para ver demanda, inventarios y métricas financieras."
    )
    anchos_manual = ui_theme.controles_ancho_columnas_tabla()
    st.caption(
        "Columnas fijas: **código, categoría, subcategoría, descripción**. "
        "Los **títulos permanecen visibles** al desplazar vertical u horizontalmente. "
        "Desde **país** los datos van centrados. Use **Ajustar ancho de columnas** para lectura."
    )

    fs = _tabla_font_px()
    fmt = _formatos_tabla_completa(df)
    ui_theme.mostrar_tabla_html(
        df.style.format(fmt),
        fs,
        n_filas=len(df),
        altura_px=ui_theme.altura_tabla_px(len(df), fs, min_h=420, max_h=720),
        layout="ancha",
        anchos_manual=anchos_manual,
        format_items=tuple(sorted(fmt.items())),
    )

    st.caption("Exportar la base transformada:")
    col_a, col_b = st.columns(2)
    col_a.download_button(
        "Descargar CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="inventario_transformado.csv",
        use_container_width=True,
    )
    col_b.download_button(
        "Descargar Excel",
        data=_exportar_excel(df, "base_transformada"),
        file_name="inventario_transformado.xlsx",
        use_container_width=True,
    )


def _tabla_pivote(df: pd.DataFrame, dimension: str) -> pd.DataFrame:
    mapa = {
        "codigo": "count",
        "inventario promedio bultos": "sum",
        "bultos vendidos": "sum",
        "valor inventario promedio": "sum",
        "ventas totales": "sum",
        "margen bruto total": "sum",
        "cubicaje inventario": "sum",
        "ordenes anual": "sum",
    }
    pivote = pd.pivot_table(
        df, index=dimension, values=list(mapa.keys()), aggfunc=mapa, sort=False
    )
    pivote.columns = [f"{agg}({key})" for key, agg in mapa.items()]
    pivote = pivote.sort_values(by="sum(ventas totales)", ascending=False).round(0)
    return pivote


def _escuadron_drivers_resumen(
    pct: pd.DataFrame,
    dimension: str,
    *,
    cols_por_fila: int = 4,
) -> None:
    """Tarjetas por driver con la categoría líder y su participación."""
    st.markdown("**Escuadrón de drivers**")
    st.caption("Participación por driver: categoría con mayor peso en cada métrica.")
    drivers = list(pct.columns)
    for i in range(0, len(drivers), cols_por_fila):
        cols = st.columns(cols_por_fila, gap="medium")
        for j, col in enumerate(cols):
            idx = i + j
            if idx >= len(drivers):
                break
            driver = drivers[idx]
            serie = pct[driver]
            if serie.empty:
                continue
            top_idx = serie.idxmax()
            top_val = float(serie.max())
            acento = PALETA[idx % len(PALETA)]
            with col:
                with st.container(border=True):
                    st.markdown(
                        f'<div style="border-left:4px solid {acento};padding-left:8px;">'
                        f'<div style="font-size:14px;color:#94a3b8;">Driver</div>'
                        f'<div style="font-size:17px;font-weight:700;color:#f8fafc;">{driver}</div></div>',
                        unsafe_allow_html=True,
                    )
                    st.metric(
                        label=str(top_idx),
                        value=f"{top_val:.1%}",
                        help=f"Mayor participación en «{driver}» ({dimension})",
                    )


def vista_drivers(df: pd.DataFrame, params: dict) -> None:
    ventas = parametros.tag_a_dataframe(params, "gen_financieros_calculados")["Valor"].iloc[0]
    st.caption(
        f"Base transformada y parámetros del paso 1 "
        f"(ventas calculadas: $ {float(ventas):,.0f}). "
        "Use las ventanas laterales para comparar valores y participación."
    )
    dimension = st.radio(
        "Agrupar por:",
        options=["categoria", "subcategoria"],
        format_func=lambda x: "Categoría" if x == "categoria" else "Subcategoría",
        horizontal=True,
    )

    pivote = _tabla_pivote(df, dimension)
    fs = _tabla_font_px()

    fmt_abs = {
        "count(codigo)": "{:,.0f}",
        "sum(inventario promedio bultos)": "{:,.0f}",
        "sum(bultos vendidos)": "{:,.0f}",
        "sum(valor inventario promedio)": "$ {:,.0f}",
        "sum(ventas totales)": "$ {:,.0f}",
        "sum(margen bruto total)": "$ {:,.0f}",
        "sum(cubicaje inventario)": "{:,.0f} m³",
        "sum(ordenes anual)": "{:,.0f}",
    }

    pct = pivote.copy()
    pct.columns = [
        "% SKUs", "% inv prom/bult", "% bult vendidos", "% valor inv prom",
        "% ventas totales", "% margen bruto", "% cub inv prom", "% ordenes anual",
    ]
    pct = pct.div(pct.sum(axis=0), axis=1)

    col_abs, col_pct = st.columns(2, gap="large")
    with col_abs:
        st.markdown("**Valores absolutos**")
        ui_theme.mostrar_tabla_html(
            pivote.style.format(fmt_abs),
            fs,
            n_filas=len(pivote),
            altura_px=ui_theme.altura_tabla_px(len(pivote), fs, min_h=320, max_h=560),
        )
    with col_pct:
        st.markdown("**Participación % por driver**")
        ui_theme.mostrar_tabla_html(
            pct.style.format("{:.1%}"),
            fs,
            n_filas=len(pct),
            altura_px=ui_theme.altura_tabla_px(len(pct), fs, min_h=320, max_h=560),
        )

    _escuadron_drivers_resumen(pct, dimension)

    fig = px.bar(
        pct.reset_index().melt(id_vars=dimension, var_name="Driver", value_name="pct"),
        x="Driver",
        y="pct",
        color=dimension,
        barmode="group",
        title="Participación por driver",
        color_discrete_sequence=PALETA,
    )
    fig.update_layout(yaxis_tickformat=".0%", height=460)
    st.plotly_chart(fig, use_container_width=True)


def vista_asignacion_drivers(df: pd.DataFrame, params: dict) -> None:
    """Asignación de drivers a líneas contables (tabla única con scroll)."""
    st.caption(
        "Almacenaje e inventario en **una sola tabla**. Edite la columna **Driver** "
        "y revise **En archivo** antes de grabar al final."
    )

    tabla_valor = scorecard.tabla_pivote_valores(df, "categoria")
    tabla_pct = scorecard.tabla_pivote_porcentajes(tabla_valor)
    pct_sin_total = tabla_pct.drop(columns=["Total"], errors="ignore")

    inv_alm_n, _ = parametros.extraer_tag(params, "alm_inversiones")
    cost_alm_n, _ = parametros.extraer_tag(params, "alm_costosgastos")
    inv_inv_n, _ = parametros.extraer_tag(params, "inv_inversiones")
    inv_calc_n, _ = parametros.extraer_tag(params, "inv_inversiones_calculado")
    inv_cost_n, _ = parametros.extraer_tag(params, "inv_costosgastos")
    cost_inv_n = inv_calc_n[1:] + inv_cost_n

    scorecard.mostrar_asignacion_drivers_unificada(
        pct_sin_total,
        inv_alm_n,
        cost_alm_n,
        inv_inv_n,
        cost_inv_n,
    )

    st.divider()
    if st.button(
        "Grabar las nuevas asignaciones de drivers",
        type="primary",
        use_container_width=True,
        key="inv_btn_grabar_drivers",
    ):
        scorecard.guardar_asignacion_drivers(
            pct_sin_total,
            inv_alm_n,
            cost_alm_n,
            inv_inv_n,
            cost_inv_n,
        )
        st.success(
            "Asignación grabada en `drivers_guardados.json`. "
            "Permanece hasta que la cambie y vuelva a grabar."
        )
        st.rerun()

    if scorecard.existe_asignacion_guardada():
        st.caption(
            f"Última versión persistente: `{os.path.basename(scorecard.ARCHIVO_DRIVERS_GUARDADO)}`. "
            "**● cambio pendiente** = distinto al archivo; **✓ grabado** = coincide."
        )
    else:
        st.caption(
            "Aún no hay archivo guardado. Los cambios en sesión aplican al Scorecard; "
            "use el botón de arriba para conservarlos al cerrar la app."
        )


def _inicializar_controles_gmroi() -> None:
    """Valores por defecto de los controles GMROI/EVAI (sidebar)."""
    for clave, valor in (
        ("inv_gmroi_nivel", "codigo"),
        ("inv_gmroi_icc_por", "categoria"),
        ("inv_gmroi_mostrar_tabla", False),
        ("inv_gmroi_top_n", 20),
        ("inv_gmroi_pareto_set", "Desactivado (Paleta Azul)"),
        ("inv_gmroi_pareto_acumulado", False),
        ("inv_gmroi_filtro_categoria", "— Todas las categorías —"),
        ("inv_gmroi_filtro_subcategoria", "— Todas las subcategorías —"),
        ("inv_gmroi_filtro_codigo", "— Todos los códigos —"),
    ):
        if clave not in st.session_state:
            st.session_state[clave] = valor
    st.session_state["inv_gmroi_nivel"] = scorecard.normalizar_nivel_gmroi(
        str(st.session_state["inv_gmroi_nivel"])
    )


_CLAVE_TOGGLE_TABLA_GMROI = "_inv_gmroi_tabla_toggle_pendiente"


def _aplicar_toggle_tabla_gmroi_pendiente() -> None:
    """Aplica el toggle del botón 📋 antes de instanciar el checkbox del sidebar."""
    if _CLAVE_TOGGLE_TABLA_GMROI in st.session_state:
        st.session_state["inv_gmroi_mostrar_tabla"] = st.session_state.pop(_CLAVE_TOGGLE_TABLA_GMROI)


def _sidebar_gmroi_evai(df: pd.DataFrame, params: dict) -> None:
    """Controles GMROI/EVAI en sidebar: nivel, tabla opcional y acceso al análisis."""
    _inicializar_controles_gmroi()
    en_vista = st.session_state.get("inv_vista") == "GMROI y EVAI"
    with st.expander("GMROI y EVAI", expanded=en_vista):
        st.caption(
            "GMROI = margen bruto ÷ valor inv. promedio · "
            "% margen bruto e % ICC sobre ventas · "
            "EVAI = margen bruto − ICC asignado"
        )
        st.selectbox(
            "Asignar ICC por",
            options=["categoria", "subcategoria"],
            format_func=lambda x: "Categoría" if x == "categoria" else "Subcategoría",
            key="inv_gmroi_icc_por",
            help="Grupo del scorecard para repartir el costo de mantener inventario.",
        )
        st.slider(
            "Máx. registros (solo sin filtro)",
            min_value=5,
            max_value=100,
            key="inv_gmroi_top_n",
            help="Con nivel Código o filtros de categoría/subcategoría se muestran todos los registros.",
        )
        st.selectbox(
            "Análisis Pareto",
            options=scorecard.OPCIONES_PARETO_GMROI,
            key="inv_gmroi_pareto_set",
            help="Segmenta ítems en tramos (verde · amarillo · rojo) como en Perfilado.",
        )
        if "Desactivado" not in st.session_state.get("inv_gmroi_pareto_set", ""):
            st.checkbox(
                "Curva % acumulado",
                key="inv_gmroi_pareto_acumulado",
            )
        st.checkbox(
            "Mostrar tabla detallada",
            key="inv_gmroi_mostrar_tabla",
            help="También puede abrirla con el botón 📋 en la vista principal.",
        )
        try:
            tabla_sku = scorecard.tabla_gmroi_evai_por_sku(
                df, params, st.session_state["inv_gmroi_icc_por"]
            )
            resumen = scorecard.tabla_gmroi_evai_resumen(
                tabla_sku,
                scorecard.normalizar_nivel_gmroi(st.session_state.get("inv_gmroi_nivel", "codigo")),
            )
        except Exception as exc:
            st.warning(f"No se pudo calcular: {exc}")
            return
        c1, c2 = st.columns(2)
        c1.metric("Registros", f"{len(resumen):,}")
        gmroi_prom = resumen["GMROI"].replace(0, np.nan).mean()
        c2.metric("GMROI prom.", f"{gmroi_prom:.2f}" if pd.notna(gmroi_prom) else "—")
        st.metric("EVAI total", f"$ {resumen['EVAI'].sum():,.0f}")
        if not en_vista and st.button(
            "Abrir análisis completo",
            use_container_width=True,
            key="inv_ir_gmroi_evai",
        ):
            st.session_state["inv_vista"] = "GMROI y EVAI"
            st.rerun()


_CLAVE_TOGGLE_TABLA_GMROI = "_inv_gmroi_tabla_toggle_pendiente"
_OPCION_TODAS_CAT = "— Todas las categorías —"
_OPCION_TODAS_SUB = "— Todas las subcategorías —"
_OPCION_TODOS_COD = "— Todos los códigos —"


def _reset_filtros_gmroi_subcategoria() -> None:
    st.session_state["inv_gmroi_filtro_subcategoria"] = _OPCION_TODAS_SUB
    st.session_state["inv_gmroi_filtro_codigo"] = _OPCION_TODOS_COD


def _reset_filtros_gmroi_codigo() -> None:
    st.session_state["inv_gmroi_filtro_codigo"] = _OPCION_TODOS_COD


def _controles_filtro_gmroi(df: pd.DataFrame) -> tuple[str | None, str | None, str | None]:
    """Nivel de análisis + drill-down por categoría, subcategoría y código."""
    st.markdown("##### Presentar GMROI y EVAI por")
    nivel = st.radio(
        "Nivel de análisis",
        options=list(scorecard._NIVELES_GMROI),
        format_func=lambda x: scorecard._ETIQUETAS_NIVEL[x],
        horizontal=True,
        key="inv_gmroi_nivel",
        help="Categoría: totales por categoría · Subcategoría: por subcategoría · Código: GMROI/EVAI por artículo.",
    )

    st.markdown("##### Segmentar ventas (drill-down)")
    st.caption(
        "Elija **categoría** (p. ej. Alimentos, Abarrotes), luego **subcategoría** y, si lo necesita, "
        "un **código** concreto para ver GMROI y EVAI de ese artículo."
    )

    # Normalizar valores legacy del session_state
    for clave, default in (
        ("inv_gmroi_filtro_categoria", _OPCION_TODAS_CAT),
        ("inv_gmroi_filtro_subcategoria", _OPCION_TODAS_SUB),
        ("inv_gmroi_filtro_codigo", _OPCION_TODOS_COD),
    ):
        if st.session_state.get(clave) in ("— Todas —", None):
            st.session_state[clave] = default

    categorias = [_OPCION_TODAS_CAT, *sorted(df["categoria"].dropna().astype(str).unique())]
    c1, c2, c3 = st.columns(3)
    with c1:
        cat_sel = st.selectbox(
            "Categoría",
            categorias,
            key="inv_gmroi_filtro_categoria",
            on_change=_reset_filtros_gmroi_subcategoria,
        )
    cat_filtro = cat_sel if cat_sel != _OPCION_TODAS_CAT else None

    if cat_filtro:
        mask_sub = df["categoria"].astype(str) == cat_filtro
    else:
        mask_sub = pd.Series(True, index=df.index)
    sub_opts = sorted(df.loc[mask_sub, "subcategoria"].dropna().astype(str).unique())

    with c2:
        sub_sel = st.selectbox(
            "Subcategoría",
            [_OPCION_TODAS_SUB, *sub_opts],
            key="inv_gmroi_filtro_subcategoria",
            on_change=_reset_filtros_gmroi_codigo,
        )
    sub_filtro = sub_sel if sub_sel != _OPCION_TODAS_SUB else None

    mask_cod = mask_sub
    if sub_filtro:
        mask_cod = mask_cod & (df["subcategoria"].astype(str) == sub_filtro)
    cod_opts = sorted(df.loc[mask_cod, "codigo"].dropna().astype(str).unique())

    with c3:
        if nivel == "codigo":
            cod_sel = st.selectbox(
                "Código (producto)",
                [_OPCION_TODOS_COD, *cod_opts],
                key="inv_gmroi_filtro_codigo",
                help="Un artículo específico: GMROI y EVAI de ese SKU.",
            )
            cod_filtro = cod_sel if cod_sel != _OPCION_TODOS_COD else None
        else:
            st.caption("Use nivel **Código (SKU / producto)** para elegir un artículo.")
            cod_filtro = None

    return cat_filtro, sub_filtro, cod_filtro


def vista_gmroi_evai(df: pd.DataFrame, params: dict) -> None:
    """Gráficos GMROI/EVAI por código, categoría o subcategoría; tabla opcional."""
    _inicializar_controles_gmroi()
    cat_filtro, sub_filtro, cod_filtro = _controles_filtro_gmroi(df)
    nivel = scorecard.normalizar_nivel_gmroi(st.session_state["inv_gmroi_nivel"])
    icc_por = st.session_state["inv_gmroi_icc_por"]
    top_n = int(st.session_state["inv_gmroi_top_n"])
    mostrar_tabla = st.session_state["inv_gmroi_mostrar_tabla"]
    set_pareto = st.session_state["inv_gmroi_pareto_set"]
    pareto_acum = st.session_state.get("inv_gmroi_pareto_acumulado", False)
    etiqueta_nivel = scorecard._ETIQUETAS_NIVEL[nivel]
    etiqueta_icc = "categoría" if icc_por == "categoria" else "subcategoría"
    pareto_txt = set_pareto if "Desactivado" not in set_pareto else "Paleta azul → blanco"

    st.caption(
        "Más opciones (ICC, Pareto, registros en gráfico, tabla) en sidebar → **GMROI y EVAI**."
    )
    filtro_txt = ""
    if cat_filtro:
        filtro_txt += f" · **Categoría:** {cat_filtro}"
    if sub_filtro:
        filtro_txt += f" · **Subcategoría:** {sub_filtro}"
    if cod_filtro:
        filtro_txt += f" · **Código:** {cod_filtro}"
    st.caption(
        "Fórmulas: valor inventario promedio = inventario promedio bultos × costo unitario bulto · "
        "margen bruto = ventas totales − ventas costo · "
        "GMROI = margen bruto ÷ valor inventario promedio · "
        "% margen bruto = margen bruto ÷ ventas totales · "
        "% ICC = ICC asignado ÷ ventas totales · "
        "EVAI = margen bruto − ICC asignado"
    )

    try:
        tabla_sku = scorecard.tabla_gmroi_evai_por_sku(df, params, icc_por)
        tabla_sku = scorecard.filtrar_tabla_gmroi_sku(
            tabla_sku,
            categoria=cat_filtro,
            subcategoria=sub_filtro,
            codigo=cod_filtro,
        )
        if tabla_sku.empty:
            st.warning("No hay productos para los filtros seleccionados.")
            return
        tabla = scorecard.tabla_gmroi_evai_resumen(tabla_sku, nivel)
    except Exception as exc:
        st.error(f"No se pudo calcular GMROI/EVAI: {exc}")
        return

    mostrar_todos_graf = nivel == "codigo" or bool(cat_filtro or sub_filtro)
    limite_txt = (
        f"todos ({len(tabla):,})"
        if mostrar_todos_graf
        else f"top {top_n}"
    )
    st.caption(
        f"Nivel: {etiqueta_nivel}{filtro_txt} · ICC por: {etiqueta_icc} · "
        f"Gráfico: {limite_txt} · Color: {pareto_txt}"
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Registros", f"{len(tabla):,}")
    gmroi_prom = tabla["GMROI"].replace(0, np.nan).mean()
    m2.metric("GMROI promedio", f"{gmroi_prom:.2f}" if pd.notna(gmroi_prom) else "—")
    m3.metric("EVAI total", _fmt_moneda(float(tabla["EVAI"].sum())))
    m4.metric("Margen bruto", _fmt_moneda(float(tabla["margen bruto total"].sum())))

    st.caption("Gráficos verticales — mayor a menor (desplácese horizontalmente si hay muchos códigos)")
    g1, g2 = st.columns(2, gap="large")
    with g1:
        scorecard.grafico_gmroi_barras(
            tabla,
            nivel=nivel,
            top_n=top_n,
            metrica="GMROI",
            set_pareto=set_pareto,
            mostrar_acumulado=pareto_acum,
            mostrar_todos=mostrar_todos_graf,
        )
    with g2:
        scorecard.grafico_gmroi_barras(
            tabla,
            nivel=nivel,
            top_n=top_n,
            metrica="EVAI",
            set_pareto=set_pareto,
            mostrar_acumulado=pareto_acum,
            mostrar_todos=mostrar_todos_graf,
        )

    st.divider()
    btn_col, txt_col = st.columns([1, 4], vertical_alignment="center")
    with btn_col:
        etiqueta_btn = "📋 Ocultar tabla" if mostrar_tabla else "📋 Ver tabla de cálculos"
        if st.button(
            etiqueta_btn,
            key="inv_toggle_tabla_gmroi",
            use_container_width=True,
            help="Muestra u oculta la tabla con todos los cálculos (útil para imprimir o exportar).",
        ):
            st.session_state[_CLAVE_TOGGLE_TABLA_GMROI] = not mostrar_tabla
            st.rerun()
    with txt_col:
        if mostrar_tabla:
            st.caption("Tabla visible — desplácese vertical y horizontalmente; columnas fijas a la izquierda.")
        else:
            st.caption(
                "La tabla está colapsada. Use **📋 Ver tabla de cálculos** para revisar o imprimir el detalle."
            )

    if mostrar_tabla:
        anchos = ui_theme.controles_ancho_columnas_tabla()
        scorecard.render_tabla_gmroi_evai(tabla, anchos_manual=anchos)
        export = tabla.drop(columns=["_etiqueta"], errors="ignore")
        st.caption("Exportar tabla:")
        col_a, col_b = st.columns(2)
        base = f"gmroi_evai_{nivel}"
        col_a.download_button(
            "Descargar CSV",
            data=export.to_csv(index=False).encode("utf-8"),
            file_name=f"{base}.csv",
            use_container_width=True,
            key="gmroi_evai_dl_csv",
        )
        col_b.download_button(
            "Descargar Excel",
            data=_exportar_excel(export, "gmroi_evai"),
            file_name=f"{base}.xlsx",
            use_container_width=True,
            key="gmroi_evai_dl_xlsx",
        )


def vista_scorecard(df: pd.DataFrame, params: dict) -> None:
    """Tablero financiero / scorecard — solo resultados (drivers ya asignados)."""
    fs = _tabla_font_px()
    st.caption(
        "Tablero en tres niveles: **almacenaje**, **inventarios** y **resumen de métricas**. "
        "Los drivers se asignan en la vista *Drivers (tentativo)*."
    )
    dimension = st.radio(
        "Agrupar por:",
        options=["categoria", "subcategoria"],
        format_func=lambda x: "Categoría" if x == "categoria" else "Subcategoría",
        horizontal=True,
        key="scorecard_dimension",
    )

    tabla_valor = scorecard.tabla_pivote_valores(df, dimension)
    tabla_pct = scorecard.tabla_pivote_porcentajes(tabla_valor)
    pct_sin_total = tabla_pct.drop(columns=["Total"], errors="ignore")

    capital_pct = float(parametros.extraer_tag(params, "gen_financieros")[1][0])

    inv_alm_n, inv_alm_v = parametros.extraer_tag(params, "alm_inversiones")
    cost_alm_n, cost_alm_v = parametros.extraer_tag(params, "alm_costosgastos")
    cost_alm_vals = cost_alm_v[1:] + [capital_pct]

    inv_inv_n, inv_inv_v = parametros.extraer_tag(params, "inv_inversiones")
    inv_calc_n, inv_calc_v = parametros.extraer_tag(params, "inv_inversiones_calculado")
    inv_cost_n, inv_cost_v = parametros.extraer_tag(params, "inv_costosgastos")
    cost_inv_n = inv_calc_n[1:] + inv_cost_n
    cost_inv_v = inv_calc_v[1:] + inv_cost_v

    sc_alm_all = scorecard.scorecard_completo(
        pct_sin_total,
        scorecard.TABLA_DRIVERS_ALMACEN,
        inv_alm_n,
        inv_alm_v,
        capital_pct,
        cost_alm_n,
        cost_alm_vals,
    )
    sc_inv_all = scorecard.scorecard_completo(
        pct_sin_total,
        scorecard.TABLA_DRIVERS_INVENTARIO,
        inv_inv_n,
        inv_inv_v,
        capital_pct,
        cost_inv_n,
        cost_inv_v,
    )

    hdr_alm, _ = st.columns([5, 1], gap="small", vertical_alignment="center")
    with hdr_alm:
        ui_theme.titulo_seccion_scorecard(
            1,
            "Scorecard de almacenaje",
            subtitulo="Costos del almacén — inversiones y gastos de almacenaje por driver",
            font_px=fs,
        )
    alm_tabla = scorecard.mostrar_scorecard(
        pct_sin_total,
        scorecard.TABLA_DRIVERS_ALMACEN,
        inv_alm_n,
        cost_alm_n,
        sc_alm_all,
    )
    _, dl_alm = st.columns([5, 1], gap="small")
    with dl_alm:
        st.download_button(
            "Excel almacenaje",
            data=_exportar_excel(alm_tabla, "scorecard_almacen"),
            file_name=f"scorecard_almacen_{dimension}.xlsx",
            use_container_width=True,
            key="scorecard_dl_alm",
        )

    ui_theme.separador_scorecard()

    hdr_inv, _ = st.columns([5, 1], gap="small", vertical_alignment="center")
    with hdr_inv:
        ui_theme.titulo_seccion_scorecard(
            2,
            "Scorecard de inventarios",
            subtitulo="Costos del inventario — inversiones, oficina y control por driver",
            font_px=fs,
        )
    inv_tabla = scorecard.mostrar_scorecard(
        pct_sin_total,
        scorecard.TABLA_DRIVERS_INVENTARIO,
        inv_inv_n,
        cost_inv_n,
        sc_inv_all,
    )
    _, dl_inv = st.columns([5, 1], gap="small")
    with dl_inv:
        st.download_button(
            "Excel inventarios",
            data=_exportar_excel(inv_tabla, "scorecard_inventario"),
            file_name=f"scorecard_inventario_{dimension}.xlsx",
            use_container_width=True,
            key="scorecard_dl_inv",
        )

    total_df = scorecard.scorecard_total(alm_tabla, inv_tabla, tabla_valor)
    st.session_state["inv_scorecard_total"] = total_df

    ui_theme.separador_scorecard()

    hdr_kpi, _ = st.columns([5, 1], gap="small", vertical_alignment="center")
    with hdr_kpi:
        ui_theme.titulo_seccion_scorecard(
            3,
            "Resumen y métricas",
            subtitulo="ICC, ICR, rotación, GMROI, EVAI y ratios por categoría",
            font_px=fs,
        )
    scorecard.mostrar_kpis_totales(total_df)
    _, dl_kpi = st.columns([5, 1], gap="small")
    with dl_kpi:
        st.download_button(
            "Excel KPI's",
            data=_exportar_excel(total_df.reset_index(names=["KPI"])),
            file_name=f"scorecard_total_{dimension}.xlsx",
            use_container_width=True,
            key="scorecard_dl_total",
        )

    with st.expander("Gráficos ICC / ICR", expanded=False):
        scorecard._grafico_barras_horizontal(alm_tabla, inv_tabla)
        total_df = st.session_state.get("inv_scorecard_total")
        if total_df is not None:
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                scorecard._grafico_barras_valor_icc(total_df)
            with col_g2:
                scorecard._grafico_barras_icr(total_df)


def _parametros_calculados_setbox(
    params: dict,
    tag: str,
    titulo: str,
    *,
    layout: ui_theme.LayoutParametros | None = None,
    es_porcentaje: bool = False,
) -> None:
    """Parámetros del Excel: set box fijo (mismo formato que editables, solo lectura)."""
    fs = _tabla_font_px()
    tabla = parametros.tag_a_dataframe(params, tag)
    if layout is None:
        medidas = ui_theme.medidas_input_estandar(fs)
        layout = ui_theme.crear_layout_parametros(
            [str(x) for x in tabla["Parámetro"]],
            fs,
            grupo_id=tag,
            medidas_inp=medidas,
        )
    ui_theme.titulo_seccion_parametros(titulo, editable=False, font_px=fs, tag=tag)
    st.caption(
        "Valores **fijos** (rojo suave): calculados por el sistema al cargar el Excel. "
        "Mismo set box que los editables, sin cambios manuales."
    )
    ui_theme.editor_parametros_solo_lectura(
        tabla,
        tag,
        fs,
        layout=layout,
        es_porcentaje=es_porcentaje,
    )


def _editor_parametros(
    params: dict,
    tag: str,
    titulo: str,
    df: pd.DataFrame,
    formato: str | None = None,
    *,
    layout: ui_theme.LayoutParametros | None = None,
    medidas_inp: tuple[int, int, int, int] | None = None,
) -> dict:
    """Tabla editable de parámetros manuales; persiste en session_state."""
    fs = _tabla_font_px()
    base = parametros.tag_a_dataframe(params, tag)
    if layout is None:
        medidas = medidas_inp or ui_theme.medidas_input_estandar(fs)
        layout = ui_theme.crear_layout_parametros(
            [str(x) for x in base["Parámetro"]],
            fs,
            grupo_id=tag,
            medidas_inp=medidas,
        )
    ui_theme.titulo_seccion_parametros(titulo, editable=True, font_px=fs, tag=tag)
    editado = ui_theme.editor_parametros_compacto(
        base,
        tag,
        fs,
        es_porcentaje=formato is not None,
        layout=layout,
    )
    actualizado = parametros.dataframe_editable_a_tag(params, tag, editado, inplace=True)
    return actualizado


def vista_parametros_generales(df: pd.DataFrame, params: dict) -> None:
    """Ingreso manual: personal, costos de almacén, inversiones, capital %, etc."""
    if not st.session_state.get("inv_widgets_param_ok"):
        parametros.sincronizar_claves_widgets(params, force=True)
        st.session_state["inv_widgets_param_ok"] = True

    ui_theme.leyenda_origen_parametros()
    st.info(
        "**Inicio:** se cargan los valores **estándar** o los **últimos guardados** "
        "(botón abajo). Puede cambiar con **+ / −** o escribiendo el valor con el teclado. "
        "Los bloques **rojo suave** (set box fijo) son calculados por el sistema. Pulse **Guardar parámetros** para conservar "
        "los cambios en la próxima ejecución."
    )

    pestaña = st.radio(
        "Sección de parámetros",
        ["Parámetros Almacenaje", "Parámetros Inventario", "Parámetros Generales"],
        horizontal=True,
        key="inv_pestaña_parametros",
    )

    if pestaña == "Parámetros Almacenaje":
        params = _editor_parametros(params, "alm_datos", "Datos", df)
        ui_theme.separador_parametros()
        params = _editor_parametros(params, "alm_costosgastos", "Costos y gastos", df)
        ui_theme.separador_parametros()
        params = _editor_parametros(params, "alm_inversiones", "Inversiones", df)

    elif pestaña == "Parámetros Inventario":
        _parametros_calculados_setbox(params, "inv_datos_calculados", "Datos (desde Excel)")
        ui_theme.separador_parametros()
        params = _editor_parametros(params, "inv_datos", "Datos (manual)", df)
        ui_theme.separador_parametros()
        params = _editor_parametros(
            params, "inv_costosgastos", "Costos y gastos de inventario", df
        )
        ui_theme.separador_parametros()
        _parametros_calculados_setbox(
            params, "inv_inversiones_calculado", "Inversiones (desde Excel)"
        )
        ui_theme.separador_parametros()
        params = _editor_parametros(params, "inv_inversiones", "Inversiones (manual)", df)

    else:
        _parametros_calculados_setbox(params, "gen_financieros_calculados", "Financieros (desde Excel)")
        ui_theme.separador_parametros()
        params = _editor_parametros(
            params,
            "gen_financieros",
            "Financieros (manual)",
            df,
            formato="%d",
        )
        st.caption("El «Costo de capital de la empresa %» aplica sobre la inversión en inventario.")
        ui_theme.separador_parametros()
        params = _editor_parametros(params, "gen_operativos", "Operativos", df)

    parametros.actualizar_calculados_si_necesario(params, df)
    st.session_state["inv_parametros"] = params

    col_g1, col_g2 = st.columns([1, 2])
    with col_g1:
        if st.button("Guardar parámetros", type="primary", use_container_width=True):
            params_guardar = parametros.params_desde_widgets(params)
            parametros.guardar_parametros_editables(params_guardar)
            parametros.actualizar_calculados_si_necesario(params_guardar, df)
            st.session_state["inv_parametros"] = params_guardar
            st.success("Valores guardados para la próxima vez que abra la app.")
        if st.button(
            "Restaurar valores estándar",
            use_container_width=True,
            help=f"Excel `{data_loader.NOMBRE_ARCHIVO_DEFECTO}` + parámetros de plantilla.",
        ):
            _reiniciar_plantilla_completa()
    with col_g2:
        st.caption(
            f"Archivos: `{os.path.basename(parametros.ARCHIVO_GUARDADO)}` (local) y "
            f"`{os.path.basename(parametros.ARCHIVO_BACKUP)}` (respaldo en el módulo)."
        )

    st.success(
        "Parámetros listos para Scorecard y drivers. "
        "Los calculados (rojo suave) se actualizan al cargar el Excel."
    )


# Orden del flujo en sidebar.
OPCIONES_VISTA = [
    "Parámetros",
    "Base de datos",
    "Drivers (tentativo)",
    "Asignación de drivers",
    "Scorecard",
    "GMROI y EVAI",
]
VISTAS: dict[str, Callable[[pd.DataFrame, dict], None]] = {
    "Parámetros": vista_parametros_generales,
    "Base de datos": vista_base_datos,
    "Drivers (tentativo)": vista_drivers,
    "Asignación de drivers": vista_asignacion_drivers,
    "Scorecard": vista_scorecard,
    "GMROI y EVAI": vista_gmroi_evai,
}


def main() -> None:
    _inicializar_datos_en_sesion()
    _inicializar_controles_gmroi()
    _aplicar_toggle_tabla_gmroi_pendiente()

    with st.sidebar:
        ui_theme.render_branding_sidebar()
        st.markdown(
            '<p class="lri-inv-sidebar-titulo">Inventory Pro</p>',
            unsafe_allow_html=True,
        )
        _sidebar_cargar_datos()

        df_sidebar = st.session_state.get("inv_df_datos")
        err_sidebar = st.session_state.get("inv_error_carga")
        if df_sidebar is not None:
            _render_control_voz_sidebar(df_sidebar)
            _sidebar_gmroi_evai(df_sidebar, parametros.inicializar_parametros(df_sidebar))
        elif err_sidebar:
            st.warning(err_sidebar)

        st.divider()
        st.markdown("##### Navegación")
        if "inv_vista" not in st.session_state:
            st.session_state["inv_vista"] = OPCIONES_VISTA[0]
        elif st.session_state["inv_vista"] not in OPCIONES_VISTA:
            legacy = {
                "Parámetros generales": "Parámetros",
                "Drivers (DMD)": "Drivers (tentativo)",
                "Paso 4 — Scorecard (tablero financiero)": "Scorecard",
            }
            st.session_state["inv_vista"] = legacy.get(
                st.session_state["inv_vista"],
                OPCIONES_VISTA[0],
            )
        seleccion = st.radio(
            "Vista",
            OPCIONES_VISTA,
            key="inv_vista",
        )
        if seleccion == "Drivers (tentativo)":
            st.caption(
                "Vista provisional; más adelante será una función oculta del módulo."
            )

        st.divider()
        st.markdown("##### Ajustes de interfaz")
        st.session_state["inv_tabla_fontsize"] = st.slider(
            "Tamaño de letra (px)",
            min_value=ui_theme.TABLA_FONT_SIZE_MIN,
            max_value=ui_theme.TABLA_FONT_SIZE_MAX,
            value=int(
                st.session_state.get(
                    "inv_tabla_fontsize",
                    ui_theme.TABLA_FONT_SIZE_DEFAULT,
                )
            ),
            step=1,
            key="inv_tabla_fontsize_ui",
            help="Parámetros, tablas, scorecard y asignación de drivers.",
        )

    _inyectar_css_ui()
    ui_theme.cabecera_modulo_inventarios()

    seleccion = st.session_state.get("inv_vista", OPCIONES_VISTA[0])

    df = st.session_state.get("inv_df_datos")
    if df is None:
        st.error(
            st.session_state.get("inv_error_carga")
            or "Suba un Excel con la misma estructura de columnas que "
            f"`{data_loader.NOMBRE_ARCHIVO_DEFECTO}`."
        )
        if not data_loader.existe_archivo():
            st.info(
                f"Coloque `{data_loader.NOMBRE_ARCHIVO_DEFECTO}` en `data/sources/` "
                "o use el cargador del sidebar."
            )
        st.stop()

    inv_params = parametros.inicializar_parametros(df)
    VISTAS[seleccion](df, inv_params)


if __name__ == "__main__":
    main()
