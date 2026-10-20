"""EXPERIMENTAL — sync línea roja / demanda consultada (NO es la app de producción).

Copia independiente de ``pronostico_app.py``. Solo altera ``_vista_normal``:
la línea roja y un slider siguen el campo de bultos consultados.
No modifica Excel, cálculos oficiales ni la app principal.

Ejecutar (sin tocar producción en :8502):
    streamlit run modules/pronostico/_experimentos/pronostico_app_exp_linea_demanda.py --server.port 8503
"""
from __future__ import annotations

import io
import os
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from statistics import NormalDist

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from openpyxl.utils import get_column_letter

# Carpeta padre = módulo pronóstico (calculos / excel oficiales, solo lectura).
_DIR_EXP = os.path.dirname(os.path.abspath(__file__))
_DIR_MODULO = os.path.dirname(_DIR_EXP)
if _DIR_EXP not in sys.path:
    sys.path.insert(0, _DIR_EXP)
if _DIR_MODULO not in sys.path:
    sys.path.insert(0, _DIR_MODULO)

import pronostico_calculos as pc  # noqa: E402
import pronostico_excel as pexcel  # noqa: E402
from sync_linea_helpers import (  # noqa: E402
    bultos_desde_probabilidad,
    colores_barras_zonas,
    discretizar_normal_barras,
    probabilidad_desde_bultos,
    rango_eje_x_demanda,
    zonas_probabilidad_delimitadores,
)

st.set_page_config(
    page_title="LRI Forecast Pro · EXP línea demanda",
    page_icon="📈",
    layout="wide",
)

_CLAVE_CONTENEDOR_TABLA = "pron_tabla_archivo"

st.markdown(
    f"""
    <style>
    [data-testid="stHeader"] {{ height: 2.25rem; background: transparent; }}
    .block-container {{ padding-top: 2.25rem; padding-bottom: 0.5rem; }}
    .block-container h4 {{ padding: 0 0 0.25rem 0; }}
    .st-key-{_CLAVE_CONTENEDOR_TABLA} {{
        flex: 0 0 auto !important; height: calc(100vh - 9.5rem) !important; min-height: 320px;
    }}
    .st-key-{_CLAVE_CONTENEDOR_TABLA} > div {{ flex: 1 1 auto; height: 100%; }}
    </style>
    """,
    unsafe_allow_html=True,
)

COLOR_REAL = "#2196f3"
COLOR_PRONOSTICO = "#22c55e"
COLOR_AJUSTADO = "#ef4444"
COLOR_TENDENCIA = "#a855f7"
_ESTILO_PRONOSTICO = {"font-weight": "bold", "color": COLOR_PRONOSTICO}

_FORMATO_TABLA = {
    "fill rate deseado": "{:.1%}",
    "demanda total": "{:,.0f}",
    "pronostico calc": "{:,.1f}",
    "desviacion calc": "{:,.1f}",
    "nivel servicio": "{:.0%}",
    "z": "{:.3f}",
    "pronostico ajustado calc": "{:,.1f}",
    "stock seguridad mes": "{:,.1f}",
    "cv": "{:.1%}",
    pc.COL_K: "{:.2f}",
    pc.COL_SEGURIDAD_K: "{:,.1f}",
    pc.COL_PRONOSTICO_LRI: "{:,.1f}",
    "tendencia mensual": "{:+,.2f}",
    "tendencia % mes": "{:+.1%}",
}

_ETIQUETAS = {
    "fill rate deseado": "Fill rate deseado",
    "pronostico calc": "Promedio 12 meses",
    pc.COL_K: "K (factor de seguridad)",
    pc.COL_SEGURIDAD_K: "K × σ",
    pc.COL_PRONOSTICO_LRI: "Pronóstico",
    "desviacion calc": "Desviación estándar",
    "nivel servicio": "Nivel de servicio",
    "pronostico ajustado calc": "Pronóstico ajustado",
    "stock seguridad mes": "Stock de seguridad (mes)",
    "cv": "Coef. variación",
    "tendencia mensual": "Tendencia (bultos/mes)",
    "tendencia % mes": "Tendencia % mes",
    pc.COL_CERTIFICACION: "Certificación",
    pc.COL_MODELO_SUGERIDO: "Modelo sugerido",
    pc.COL_CUADRA_EXCEL: "Cuadra con Excel",
}

_COLUMNAS_PRONOSTICO = (
    "codigo",
    "descripcion",
    "categoria",
    "subcategoria",
    "proveedor",
    "clase",
    "fill rate deseado",
    pc.COL_K,
    "pronostico calc",
    "desviacion calc",
    "cv",
    pc.COL_SEGURIDAD_K,
    pc.COL_PRONOSTICO_LRI,
)

_COLUMNAS_CERTIFICACION = (
    "codigo",
    "descripcion",
    "categoria",
    "subcategoria",
    "proveedor",
    "clase",
    pc.COL_CERTIFICACION,
    "cv",
    "pronostico calc",
    "desviacion calc",
    "demanda total",
    pc.COL_MODELO_SUGERIDO,
)
_COLORES_CERTIFICACION = {
    pc.CERTIFICADO: "rgba(34,197,94,0.25)",
    pc.NO_CERTIFICADO: "rgba(239,68,68,0.30)",
    pc.SIN_DEMANDA: "rgba(148,163,184,0.25)",
}
_NIVELES_CERTIFICACION = {
    "SKU": None,
    "Categoría": "categoria",
    "Subcategoría": "subcategoria",
    "Proveedor": "proveedor",
}
_CLAVE_VER_POR_NO_CERT = "pron_ver_por_no_cert"
_CLAVE_VER_POR_CERT = "pron_ver_por_cert"
_MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_COLUMNAS_PORCENTAJE_EXCEL = {
    _ETIQUETAS["cv"],
    _ETIQUETAS["fill rate deseado"],
    "% no certificados",
    "% del total",
}
_COL_VER_GRAFICO = "📈 Ver gráfico"
_PREFIJO_VER_GRAFICO = "pron_ver_grafico_"
_COLOR_FUERA_SIGMA = "#f59e0b"
_COLORES_GRAFICO_CERTIFICACION = {
    pc.CERTIFICADO: "#22c55e",
    pc.NO_CERTIFICADO: "#ef4444",
    pc.SIN_DEMANDA: "#94a3b8",
}


VISTA_PRONOSTICO = "Pronóstico"
VISTAS = ("Certificación", "Serie por SKU", "Estacionalidad", "Distribución normal", "Monte Carlo")
_ICONOS_VISTA = {
    "Certificación": "✅",
    "Serie por SKU": "📉",
    "Estacionalidad": "📅",
    "Distribución normal": "🔔",
    "Monte Carlo": "🎲",
}
_AYUDA_VISTA = {
    "Certificación": "SKUs con CV entre 0% y 30% (aptos para modelo estadístico) y los que quedan fuera.",
    "Serie por SKU": "Demanda real, tendencia y comparación de métodos (móvil, exponencial, regresión).",
    "Estacionalidad": "Índice mensual por total, categoría, subcategoría o proveedor.",
    "Distribución normal": "Curva normal del SKU y zona cubierta por el nivel de servicio.",
    "Monte Carlo": "Demanda simulada, percentiles y cobertura real del pronóstico ajustado.",
}
_CLAVE_VISTA = "pron_vista"
_CLAVE_RESULTADO = "pron_resultado"
_CLAVE_MOSTRAR_ARCHIVO = "pron_mostrar_archivo"
_CLAVE_MOSTRAR_REPORTES = "pron_mostrar_reportes"
_CLAVE_ANCHO_BARRAS = "pron_ancho_barras"
_CLAVE_ESCRITURA_PRONOSTICO = "pron_escritura_pronostico"
_ARCHIVO_ESPEJO = "inventarios.xlsx"
_ANCHO_BARRAS_INICIAL = 25
_CLAVE_NIVEL_PRONOSTICO = "pron_nivel_pronostico"
_CLAVE_NIVEL_ANTERIOR = "pron_nivel_anterior"
_CLAVE_ABRIR_GRUPO = "pron_abrir_grupo"
_CLAVE_FILL_MTIME = "pron_fill_rate_mtime"
_CLAVE_FILL_RESULTADO = "pron_fill_rate_resultado"
_COLOR_COLUMNA_USADA = "rgba(34,197,94,0.18)"
_COLOR_COLUMNA_CALCULADA = "rgba(33,150,243,0.30)"
_MODULOS_COMPARTIDOS = "Inventarios, Compras y Profile Pro"


@dataclass(frozen=True)
class Fuente:
    contenido: bytes | None
    nombre: str
    ruta: str | None
    mtime: float | None

    @property
    def clave(self) -> tuple:
        return (self.nombre, self.mtime, len(self.contenido) if self.contenido else None)


@st.cache_data(show_spinner=False)
def _cargar_demanda(contenido: bytes | None, mtime: float | None) -> tuple[pd.DataFrame | None, str | None]:
    return pc.cargar_demanda(contenido)


@st.cache_data(show_spinner=False)
def _cargar_hojas(contenido: bytes | None, mtime: float | None) -> tuple[dict[str, pd.DataFrame] | None, str | None]:
    return pc.leer_archivo_completo(contenido)


def _sincronizar_fill_rate() -> pexcel.ResultadoEscritura | None:
    """Actualiza «fill rate deseado» en el Excel compartido una vez por versión del archivo."""
    ruta = pc.ARCHIVO_EXCEL_PATH
    if not os.path.isfile(ruta):
        return None
    mtime = os.path.getmtime(ruta)
    if st.session_state.get(_CLAVE_FILL_MTIME) != mtime:
        resultado = pexcel.actualizar_fill_rate_excel(ruta)
        st.session_state[_CLAVE_FILL_RESULTADO] = resultado
        st.session_state[_CLAVE_FILL_MTIME] = os.path.getmtime(ruta)
    return st.session_state.get(_CLAVE_FILL_RESULTADO)


def _aviso_fill_rate(resultado: pexcel.ResultadoEscritura) -> None:
    columna = f"columna {resultado.columna}" if resultado.columna else "la última columna"
    if resultado.estado == "actualizado":
        st.sidebar.success(f"«{pc.COL_FILL_RATE}» actualizado en el archivo ({columna}).")
    elif resultado.estado == "sin cambios":
        st.sidebar.caption(f"✓ «{pc.COL_FILL_RATE}» al día en el archivo ({columna}).")
    else:
        st.sidebar.warning(
            f"No se pudo escribir «{pc.COL_FILL_RATE}» en el archivo: {resultado.mensaje} "
            "Se muestra calculado en pantalla."
        )


def _seccion_archivo() -> Fuente:
    st.sidebar.markdown("##### 📁 Cargar datos")
    nombre_defecto = os.path.basename(pc.ARCHIVO_EXCEL_PATH)
    subido = st.sidebar.file_uploader(
        "Archivo Excel",
        type=["xlsx"],
        key="pron_upload",
        help=(
            f"Si no sube archivo, se usa **{nombre_defecto}**, el archivo compartido con "
            f"{_MODULOS_COMPARTIDOS}. Otro Excel debe traer la misma hoja «data»."
        ),
    )
    if subido is not None:
        fuente = Fuente(subido.getvalue(), subido.name, None, None)
        st.sidebar.caption(f"Archivo: **{fuente.nombre}** (no es el compartido)")
    else:
        resultado_fill = _sincronizar_fill_rate()
        mtime = os.path.getmtime(pc.ARCHIVO_EXCEL_PATH) if os.path.isfile(pc.ARCHIVO_EXCEL_PATH) else None
        fuente = Fuente(None, nombre_defecto, pc.ARCHIVO_EXCEL_PATH, mtime)
        modificado = f" · modificado {datetime.fromtimestamp(mtime):%d/%m/%Y %H:%M}" if mtime else ""
        st.sidebar.caption(
            f"Por defecto: **{nombre_defecto}**{modificado}  \n"
            f"Compartido con {_MODULOS_COMPARTIDOS}."
        )
        if resultado_fill is not None:
            _aviso_fill_rate(resultado_fill)
    st.session_state.setdefault(_CLAVE_MOSTRAR_ARCHIVO, True)
    st.sidebar.checkbox("Mostrar archivo", key=_CLAVE_MOSTRAR_ARCHIVO)
    return fuente


def _calcular(df: pd.DataFrame, nivel: float | None, clave_fuente: tuple) -> None:
    st.session_state[_CLAVE_RESULTADO] = {
        "fuente": clave_fuente,
        "nivel": nivel,
        "calc": pc.calcular_pronostico(df, nivel),
        "hora": datetime.now(),
    }
    st.session_state.pop(_CLAVE_ESCRITURA_PRONOSTICO, None)
    st.session_state[_CLAVE_MOSTRAR_ARCHIVO] = False


def _calcular_pronostico(df: pd.DataFrame, nivel: float | None, fuente: Fuente) -> None:
    _calcular(df, nivel, fuente.clave)
    st.session_state[_CLAVE_VISTA] = VISTA_PRONOSTICO
    if fuente.ruta:
        _escribir_pronostico(fuente)


def _escribir_pronostico(fuente: Fuente) -> None:
    """Pone el pronóstico en la columna «pronostico» del Excel compartido y copia el espejo."""
    resultado = st.session_state[_CLAVE_RESULTADO]
    calc = resultado["calc"]
    escritura = pexcel.escribir_pronostico_excel(dict(zip(calc["codigo"], calc[pc.COL_PRONOSTICO_LRI])), fuente.ruta)
    st.session_state[_CLAVE_ESCRITURA_PRONOSTICO] = (escritura, None)
    if escritura.estado != "actualizado":
        return
    espejo = os.path.join(os.path.dirname(fuente.ruta), _ARCHIVO_ESPEJO)
    aviso_espejo = None
    if os.path.isfile(espejo):
        try:
            shutil.copy2(fuente.ruta, espejo)
        except OSError:
            aviso_espejo = f"No se pudo copiar a {_ARCHIVO_ESPEJO} (¿está abierto?)."
    st.session_state[_CLAVE_ESCRITURA_PRONOSTICO] = (escritura, aviso_espejo)
    mtime = os.path.getmtime(fuente.ruta)
    df, _ = _cargar_demanda(None, mtime)
    if df is not None:
        resultado["calc"] = pc.calcular_pronostico(df, resultado["nivel"])
    resultado["fuente"] = Fuente(None, fuente.nombre, fuente.ruta, mtime).clave


def _aviso_escritura_pronostico(zona) -> None:
    guardado = st.session_state.get(_CLAVE_ESCRITURA_PRONOSTICO)
    if guardado is None:
        return
    escritura, aviso_espejo = guardado
    columna = f"columna {escritura.columna}" if escritura.columna else "columna «pronostico»"
    if escritura.estado == "actualizado":
        zona.caption(f"✓ Pronóstico escrito en el Excel ({columna}, {escritura.celdas:,} SKUs).")
    elif escritura.estado == "sin cambios":
        zona.caption(f"✓ Pronóstico al día en el Excel ({columna}).")
    else:
        zona.warning(f"No se pudo escribir el pronóstico en el Excel: {escritura.mensaje}")
    if aviso_espejo:
        zona.warning(aviso_espejo)


def _elegir_alternativa(vista: str, df: pd.DataFrame, nivel: float | None, clave_fuente: tuple) -> None:
    st.session_state[_CLAVE_VISTA] = vista
    resultado = st.session_state.get(_CLAVE_RESULTADO)
    if resultado is None or resultado["fuente"] != clave_fuente:
        _calcular(df, nivel, clave_fuente)
    else:
        st.session_state[_CLAVE_MOSTRAR_ARCHIVO] = False


def _seccion_calculo(df: pd.DataFrame, fuente: Fuente) -> dict | None:
    """Botón «Cálculo del pronóstico» y, debajo, las alternativas (formato de Inventarios)."""
    st.sidebar.divider()
    zona_calculo = st.sidebar.container()
    zona_alternativas = st.sidebar.container()

    nivel_excel = pc.nivel_servicio_excel(df)
    with st.sidebar.expander("⚙️ Nivel de servicio"):
        usar_excel = st.checkbox(f"Del Excel ({nivel_excel:.0%})", value=True, key="pron_nivel_excel")
        nivel = None
        if not usar_excel:
            nivel = st.slider("Nivel de servicio", 0.50, 0.995, float(nivel_excel), 0.005, format="%.3f")
    with st.sidebar.expander("🎨 Gráficos"):
        st.slider(
            "Ancho de barras",
            10,
            100,
            _ANCHO_BARRAS_INICIAL,
            5,
            format="%d%%",
            key=_CLAVE_ANCHO_BARRAS,
            help="Porcentaje del espacio de cada barra que ocupa la columna (100% = barras pegadas).",
        )

    resultado = st.session_state.get(_CLAVE_RESULTADO)
    if resultado and resultado["fuente"] != fuente.clave:
        st.session_state.pop(_CLAVE_RESULTADO)
        resultado = None

    st.session_state.setdefault(_CLAVE_VISTA, VISTA_PRONOSTICO)
    activa = st.session_state[_CLAVE_VISTA] if resultado else None
    zona_calculo.markdown("##### Cálculo")
    zona_calculo.button(
        "📈 Cálculo del pronóstico",
        key="pron_btn_calculo",
        type="primary" if activa == VISTA_PRONOSTICO else "secondary",
        width="stretch",
        help=(
            "Pronóstico = promedio 12 meses + K × σ (K según el fill rate deseado). "
            "Solo artículos certificados (CV ≤ 30%)."
        ),
        on_click=_calcular_pronostico,
        args=(df, nivel, fuente),
    )
    if resultado is None:
        zona_calculo.caption("Aún no se ha calculado el pronóstico.")
    else:
        zona_calculo.caption(f"✓ Calculado a las {resultado['hora']:%H:%M} · {len(resultado['calc']):,} SKUs")
        _aviso_escritura_pronostico(zona_calculo)
        if resultado["nivel"] != nivel:
            zona_calculo.warning("Cambiaste el nivel de servicio: vuelve a calcular.")

    zona_alternativas.markdown("##### Alternativas de cálculo")
    for vista in VISTAS:
        zona_alternativas.button(
            f"{_ICONOS_VISTA[vista]} {vista}",
            key=f"pron_btn_{vista}",
            type="primary" if vista == activa else "secondary",
            width="stretch",
            help=_AYUDA_VISTA[vista],
            on_click=_elegir_alternativa,
            args=(vista, df, nivel, fuente.clave),
        )
    st.session_state.setdefault(_CLAVE_MOSTRAR_REPORTES, False)
    zona_alternativas.checkbox(
        "📥 Mostrar reportes (Excel)",
        key=_CLAVE_MOSTRAR_REPORTES,
        help="Muestra los botones para descargar en Excel las tablas y el reporte de certificación.",
    )
    return resultado


def _filtros(calc: pd.DataFrame) -> pd.DataFrame:
    filtrado = calc
    for col, etiqueta in (("categoria", "Categoría"), ("subcategoria", "Subcategoría"), ("proveedor", "Proveedor")):
        if col not in filtrado.columns:
            continue
        opciones = sorted(filtrado[col].dropna().unique().tolist())
        elegidos = st.sidebar.multiselect(etiqueta, opciones, key=f"pron_filtro_{col}")
        if elegidos:
            filtrado = filtrado[filtrado[col].isin(elegidos)]
    return filtrado


def _para_mostrar(df: pd.DataFrame, es_datos: bool) -> pd.DataFrame:
    """Columnas con tipos mezclados (p. ej. ``codigo``) pasan a texto para la tabla."""
    out = df.copy()
    if not es_datos:
        out.columns = [get_column_letter(int(c) + 1) for c in out.columns]
    for c in out.columns:
        if out[c].dtype == object:
            out[c] = out[c].map(lambda v: "" if pd.isna(v) else str(v))
    return out


def _vista_archivo(hojas: dict[str, pd.DataFrame], fuente: Fuente) -> None:
    nombres = list(hojas)
    col_hoja, col_info = st.columns([1, 3], vertical_alignment="center")
    with col_hoja:
        hoja = (
            st.radio("Hoja", nombres, horizontal=True, label_visibility="collapsed")
            if len(nombres) > 1
            else nombres[0]
        )
    es_datos = str(hoja).strip().lower() == pc.HOJA_DATOS
    crudo = pc.agregar_fill_rate(hojas[hoja]) if es_datos else hojas[hoja]
    tabla = _para_mostrar(crudo, es_datos)

    usadas = [c for c in tabla.columns if es_datos and pc.es_columna_pronostico(c)]
    calculadas = [c for c in tabla.columns if es_datos and c == pc.COL_FILL_RATE]
    resumen = f"**{fuente.nombre}** · {len(tabla):,} filas · {tabla.shape[1]:,} columnas"
    if es_datos:
        resumen += (
            f" · 🟩 {len(usadas)} que usa el pronóstico"
            f" · 🟦 «{pc.COL_FILL_RATE}» (después de EVAI, se actualiza al cargar según la clase)"
        )
    col_info.caption(resumen)

    estilo = tabla.style.format(precision=2, thousands=",", na_rep="")
    if usadas:
        estilo = estilo.set_properties(subset=usadas, **{"background-color": _COLOR_COLUMNA_USADA})
    if calculadas:
        estilo = estilo.format("{:.1%}", subset=calculadas, na_rep="").set_properties(
            subset=calculadas, **{"background-color": _COLOR_COLUMNA_CALCULADA}
        )
    with st.container(key=_CLAVE_CONTENEDOR_TABLA):
        st.dataframe(estilo, width="stretch", height="stretch", hide_index=True)


def _etiqueta_sku(fila: pd.Series) -> str:
    desc = fila.get("descripcion")
    return f"{fila['codigo']} · {desc}" if pd.notna(desc) else str(fila["codigo"])


def _tabla(df: pd.DataFrame) -> None:
    formato = {_ETIQUETAS.get(k, k): v for k, v in _FORMATO_TABLA.items() if k in df.columns}
    st.dataframe(
        df.rename(columns=_ETIQUETAS).style.format(formato, na_rep="—"),
        width="stretch",
        hide_index=True,
    )


def _excel_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.rename(columns=_ETIQUETAS).to_excel(writer, sheet_name="pronostico", index=False)
    return buffer.getvalue()


def _clave_ver_grafico(tabla: pd.DataFrame) -> str:
    """La clave cambia con los SKUs listados, así una marca nunca apunta a otra fila tras filtrar."""
    return f"{_PREFIJO_VER_GRAFICO}{hash(tuple(tabla['codigo'].astype(str)))}"


def _skus_marcados(tabla: pd.DataFrame) -> list:
    """Índices de los SKUs con «Ver gráfico» marcado (estado del editor de la corrida anterior)."""
    cambios = st.session_state.get(_clave_ver_grafico(tabla), {}).get("edited_rows", {})
    return [
        tabla.index[int(fila)]
        for fila, valores in cambios.items()
        if valores.get(_COL_VER_GRAFICO) and int(fila) < len(tabla)
    ]


def _tabla_no_certificados(tabla: pd.DataFrame) -> None:
    columnas = [c for c in _COLUMNAS_CERTIFICACION if c in tabla.columns]
    editable = tabla[columnas].rename(columns=_ETIQUETAS)
    editable.insert(0, _COL_VER_GRAFICO, False)
    configuracion = {
        _COL_VER_GRAFICO: st.column_config.CheckboxColumn(
            _COL_VER_GRAFICO, help="Muestra arriba la demanda mensual del SKU y qué tan dispersa está."
        ),
        _ETIQUETAS["cv"]: st.column_config.NumberColumn(format="percent"),
    }
    for col in ("pronostico calc", "desviacion calc", "demanda total"):
        if _ETIQUETAS.get(col, col) in editable.columns:
            configuracion[_ETIQUETAS.get(col, col)] = st.column_config.NumberColumn(format="%.1f")
    st.data_editor(
        editable,
        key=_clave_ver_grafico(tabla),
        width="stretch",
        hide_index=True,
        disabled=[c for c in editable.columns if c != _COL_VER_GRAFICO],
        column_config=configuracion,
    )


def _barras_delgadas(fig: go.Figure, n_barras: int) -> None:
    """Ancho según el slider «Ancho de barras»; con más de 40 barras se ensancha para que se vean."""
    ancho = st.session_state.get(_CLAVE_ANCHO_BARRAS, _ANCHO_BARRAS_INICIAL) / 100
    if n_barras > 40:
        ancho = 0.5 + ancho / 2
    fig.update_layout(bargap=max(0.0, 1 - ancho))


def _grafico_cv_por_sku(calc: pd.DataFrame, limite: float) -> None:
    graf = calc.sort_values("cv", ascending=False).assign(
        sku=lambda d: d["codigo"].astype(str), cv_pct=lambda d: d["cv"] * 100
    )
    fig = px.bar(
        graf,
        x="sku",
        y="cv_pct",
        color=pc.COL_CERTIFICACION,
        color_discrete_map=_COLORES_GRAFICO_CERTIFICACION,
        hover_data={"descripcion": True, "clase": True, "cv_pct": ":.1f", "sku": False},
        labels={"cv_pct": "CV %", "sku": "SKU", pc.COL_CERTIFICACION: "Certificación"},
        title="Coeficiente de variación por SKU (mayor a menor)",
    )
    fig.add_hline(
        y=limite * 100,
        line_dash="dash",
        line_color="#f59e0b",
        annotation_text=f"Límite {limite:.0%}",
        annotation_position="top right",
    )
    fig.update_layout(
        height=300,
        margin=dict(t=40, b=0, l=0, r=0),
        xaxis=dict(type="category", categoryorder="array", categoryarray=graf["sku"], showticklabels=False),
        legend_title_text="",
    )
    _barras_delgadas(fig, len(graf))
    st.plotly_chart(fig, width="stretch")


def _grafico_dispersion_sku(fila: pd.Series, serie: np.ndarray, meses: list[str]) -> None:
    r = pc.resumen_dispersion(serie)
    etiquetas = [f"Mes {i}" for i in range(1, len(meses) + 1)]
    fuera = np.abs(serie - r.media) > r.desviacion
    fig = go.Figure()
    fig.add_hrect(
        y0=max(0.0, r.media - r.desviacion),
        y1=r.media + r.desviacion,
        fillcolor=COLOR_PRONOSTICO,
        opacity=0.12,
        line_width=0,
        layer="below",
        annotation_text="Promedio ± 1 desviación",
        annotation_position="top left",
    )
    fig.add_bar(
        x=etiquetas,
        y=serie,
        marker_color=[_COLOR_FUERA_SIGMA if f else COLOR_REAL for f in fuera],
        name="Demanda mensual",
        hovertemplate="%{x}: %{y:,.0f}<extra></extra>",
    )
    fig.add_hline(
        y=r.media,
        line_color=COLOR_PRONOSTICO,
        annotation_text=f"Pronóstico (promedio) {r.media:,.1f}",
        annotation_position="top right",
    )
    ajustado = fila.get("pronostico ajustado calc")
    if pd.notna(ajustado):
        fig.add_hline(
            y=float(ajustado),
            line_dash="dash",
            line_color=COLOR_AJUSTADO,
            annotation_text=f"Pronóstico ajustado {float(ajustado):,.1f}",
            annotation_position="bottom right",
        )
    desc = fila.get("descripcion")
    titulo = f"{fila['codigo']}" + (f" · {desc}" if pd.notna(desc) else "")
    fig.update_layout(
        title=f"{titulo} — CV {r.cv:.1%} · {fila[pc.COL_CERTIFICACION]}",
        height=300,
        margin=dict(t=40, b=0, l=0, r=0),
        showlegend=False,
        yaxis_title="Demanda (unidades)",
    )
    _barras_delgadas(fig, len(etiquetas))
    st.plotly_chart(fig, width="stretch")
    st.caption(
        f"Mínimo {r.minimo:,.0f} · Máximo {r.maximo:,.0f} · Desviación {r.desviacion:,.1f} · "
        f"{r.meses_fuera_1sigma} de {r.meses} meses (barras naranjas) fuera de promedio ± 1 desviación · "
        f"{r.meses_sin_demanda} meses sin demanda"
    )


def _tabla_certificacion(df: pd.DataFrame) -> None:
    columnas = [c for c in _COLUMNAS_CERTIFICACION if c in df.columns]
    tabla = df[columnas].sort_values("cv", ascending=False)
    formato = {_ETIQUETAS.get(k, k): v for k, v in _FORMATO_TABLA.items() if k in columnas}
    estilo = (
        tabla.rename(columns=_ETIQUETAS)
        .style.format(formato, na_rep="—")
        .map(
            lambda v: f"background-color: {_COLORES_CERTIFICACION.get(v, '')}",
            subset=[_ETIQUETAS[pc.COL_CERTIFICACION]],
        )
    )
    st.dataframe(estilo, width="stretch", hide_index=True)


def _quitar_ver_por(clave: str) -> None:
    st.session_state[clave] = None


def _texto_tipo(certificados: bool, cantidad: int = 2) -> str:
    base = "certificado" if certificados else "no certificado"
    return base if cantidad == 1 else f"{base}s"


@st.dialog("🔎 Ver por", width="large")
def _dialogo_ver_por(calc: pd.DataFrame, clave: str, certificados: bool) -> None:
    actual = st.session_state.get(clave)
    st.markdown(f"**Artículos {_texto_tipo(certificados)}**")
    niveles = [n for n, col in _NIVELES_CERTIFICACION.items() if col is None or col in calc.columns]
    nivel = st.segmented_control("Nivel", niveles, default=actual[0] if actual else niveles[0]) or niveles[0]
    columna = _NIVELES_CERTIFICACION[nivel]
    if columna is None:
        st.caption(f"Muestra todos los SKUs {_texto_tipo(certificados)}.")
        if st.button("Ver todos", type="primary", width="stretch"):
            _quitar_ver_por(clave)
            st.rerun()
        return

    campo = "certificados" if certificados else "no_certificados"
    resumen = pc.resumen_certificacion(calc, columna).sort_values([campo, "grupo"], ascending=[False, True])
    st.caption(f"Haz clic en un grupo para ver sus artículos {_texto_tipo(certificados)}.")
    with st.container(height=420):
        for i, fila in resumen.iterrows():
            cantidad = int(fila[campo])
            if st.button(
                f"{fila['grupo']} — {cantidad} {_texto_tipo(certificados, cantidad)} de {fila['skus']} SKUs",
                key=f"{clave}_{nivel}_{i}",
                type="primary" if actual == (nivel, fila["grupo"]) else "secondary",
                width="stretch",
                disabled=cantidad == 0,
            ):
                st.session_state[clave] = (nivel, fila["grupo"])
                st.rerun()


def _filtrar_ver_por(tabla: pd.DataFrame, clave: str) -> tuple[pd.DataFrame, tuple[str, str] | None]:
    ver_por = st.session_state.get(clave)
    if not ver_por:
        return tabla, None
    nivel, valor = ver_por
    columna = _NIVELES_CERTIFICACION.get(nivel)
    if columna not in tabla.columns:
        return tabla, None
    grupos = tabla[columna].fillna("(sin dato)").astype(str).str.strip()
    return tabla[grupos == valor], ver_por


def _nombre_archivo(texto: str) -> str:
    return re.sub(r"[^\w\-]+", "_", texto).strip("_").lower()


def _hoja_certificacion(tabla: pd.DataFrame) -> pd.DataFrame:
    columnas = [c for c in _COLUMNAS_CERTIFICACION if c in tabla.columns]
    return tabla[columnas].sort_values("cv", ascending=False).rename(columns=_ETIQUETAS)


def _escribir_hojas(hojas: dict[str, pd.DataFrame]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for nombre, tabla in hojas.items():
            hoja = nombre[:31]
            tabla.to_excel(writer, sheet_name=hoja, index=False)
            ws = writer.sheets[hoja]
            ws.freeze_panes = "A2"
            for j, col in enumerate(tabla.columns, start=1):
                letra = get_column_letter(j)
                largo = int(tabla[col].astype(str).str.len().max()) if len(tabla) else 0
                ws.column_dimensions[letra].width = min(45, max(10, len(str(col)) + 2, largo + 2))
                if col in _COLUMNAS_PORCENTAJE_EXCEL:
                    for celda in ws[letra][1:]:
                        celda.number_format = "0.0%"
    return buffer.getvalue()


def _reporte_certificacion(calc: pd.DataFrame) -> bytes:
    certificado = calc[pc.COL_CERTIFICACION] == pc.CERTIFICADO
    hojas = {
        "No certificados": _hoja_certificacion(calc[~certificado]),
        "Certificados": _hoja_certificacion(calc[certificado]),
    }
    for nivel, columna in _NIVELES_CERTIFICACION.items():
        if columna and columna in calc.columns:
            hojas[f"Por {nivel.lower()}"] = pc.resumen_certificacion(calc, columna).rename(
                columns={
                    "grupo": nivel,
                    "skus": "SKUs",
                    "certificados": "Certificados",
                    "no_certificados": "No certificados",
                    "pct_no_certificados": "% no certificados",
                }
            )
    return _escribir_hojas(hojas)


def _encabezado_tabla(
    titulo: str, calc: pd.DataFrame, tabla: pd.DataFrame, clave: str, certificados: bool
) -> pd.DataFrame:
    """Título + «🔎 Ver por» (+ «📥 Excel» si se piden reportes); devuelve la tabla filtrada."""
    filtrada, ver_por = _filtrar_ver_por(tabla, clave)
    col_titulo, col_ver, col_quitar, col_excel = st.columns([5, 3, 0.7, 1.5], vertical_alignment="bottom")
    col_titulo.markdown(f"##### {titulo} ({len(filtrada):,})")
    if col_ver.button(
        f"🔎 {ver_por[0]}: {ver_por[1]}" if ver_por else "🔎 Ver por: todos",
        key=f"{clave}_abrir",
        type="primary" if ver_por else "secondary",
        width="stretch",
        help="Ver estos artículos por categoría, subcategoría o proveedor.",
    ):
        _dialogo_ver_por(calc, clave, certificados)
    if ver_por:
        col_quitar.button(
            "✕", key=f"{clave}_quitar", on_click=_quitar_ver_por, args=(clave,), help="Ver todos", width="stretch"
        )
    if not st.session_state.get(_CLAVE_MOSTRAR_REPORTES):
        return filtrada
    hoja = "Certificados" if certificados else "No certificados"
    nombre = hoja + (f" {ver_por[0]} {ver_por[1]}" if ver_por else "")
    col_excel.download_button(
        "📥 Excel",
        data=_escribir_hojas({hoja: _hoja_certificacion(filtrada)}),
        file_name=f"{_nombre_archivo(nombre)}.xlsx",
        mime=_MIME_XLSX,
        key=f"{clave}_excel",
        width="stretch",
        disabled=filtrada.empty,
        help="Descarga en Excel los artículos que muestra esta tabla.",
    )
    return filtrada


def _vista_certificacion(
    df: pd.DataFrame, calc: pd.DataFrame, meses: list[str], nivel_override: bool
) -> None:
    limite = pc.CV_MAX_CERTIFICADO
    st.subheader("Certificación por coeficiente de variación")
    st.caption(
        f"CV = desviación estándar ÷ pronóstico (promedio mensual). **Certificado**: CV entre 0% y "
        f"{limite:.0%} → demanda estable, apta para el modelo estadístico (distribución normal). "
        f"**No certificado**: CV mayor a {limite:.0%} → variabilidad alta; usar otro modelo "
        "o la demanda anual."
    )
    total = len(calc)
    estado = calc[pc.COL_CERTIFICACION]
    certificados = calc[estado == pc.CERTIFICADO]
    no_certificados = calc[estado != pc.CERTIFICADO]
    cuadran = int((calc[pc.COL_CUADRA_EXCEL] == "Sí").sum())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SKUs", f"{total:,}")
    c2.metric(
        "✅ Certificados",
        f"{len(certificados):,}",
        f"{len(certificados) / total:.0%} del total" if total else None,
        delta_arrow="off",
        help=f"CV entre 0% y {limite:.0%}: aptos para el modelo estadístico.",
    )
    c3.metric(
        "⚠️ No certificados",
        f"{len(no_certificados):,}",
        f"{len(no_certificados) / total:.0%} del total" if total else None,
        delta_color="inverse",
        delta_arrow="off",
        help=f"CV mayor a {limite:.0%}: otro modelo o demanda anual.",
    )
    c4.metric("Recálculo cuadra con Excel", f"{cuadran:,} de {total:,}")
    if nivel_override:
        st.info(
            "El nivel de servicio fue cambiado en el panel lateral: «Cuadra con Excel = No» "
            "indica diferencia contra el Excel por ese cambio, no un error de datos."
        )

    no_certificados = no_certificados.sort_values("cv", ascending=False)
    no_cert_visibles, _ = _filtrar_ver_por(no_certificados, _CLAVE_VER_POR_NO_CERT)
    marcados = _skus_marcados(no_cert_visibles) if not no_cert_visibles.empty else []
    if marcados:
        for idx in marcados:
            _grafico_dispersion_sku(calc.loc[idx], df.loc[idx, meses].to_numpy(dtype=float), meses)
    else:
        _grafico_cv_por_sku(calc, limite)

    no_cert_visibles = _encabezado_tabla(
        f"⚠️ No certificados · CV mayor a {limite:.0%}", calc, no_certificados, _CLAVE_VER_POR_NO_CERT, False
    )
    if no_certificados.empty:
        st.success("Todos los SKUs filtrados están dentro del rango para análisis estadístico.")
    elif no_cert_visibles.empty:
        st.info("Este grupo no tiene artículos no certificados.")
    else:
        st.caption(
            "Variabilidad alta: requieren otro modelo estadístico o usar la demanda anual. "
            f"Marca **{_COL_VER_GRAFICO}** para ver arriba la dispersión de su demanda; "
            "desmárcalo para volver al gráfico general."
        )
        _tabla_no_certificados(no_cert_visibles)

    cert_visibles = _encabezado_tabla(
        f"✅ Certificados · CV entre 0% y {limite:.0%}", calc, certificados, _CLAVE_VER_POR_CERT, True
    )
    if cert_visibles.empty:
        st.info("Este grupo no tiene artículos certificados.")
    else:
        _tabla_certificacion(cert_visibles)

    if not st.session_state.get(_CLAVE_MOSTRAR_REPORTES):
        return
    col_reporte, col_pronostico, _ = st.columns([2, 2, 3])
    col_reporte.download_button(
        "📥 Reporte de certificación (Excel)",
        data=_reporte_certificacion(calc),
        file_name="certificacion_pronostico_lri.xlsx",
        mime=_MIME_XLSX,
        width="stretch",
        help="No certificados, certificados y resumen por categoría, subcategoría y proveedor.",
    )
    col_pronostico.download_button(
        "Descargar pronóstico (Excel)",
        data=_excel_bytes(calc),
        file_name="pronostico_lri.xlsx",
        mime=_MIME_XLSX,
        width="stretch",
    )


def _tabla_pronostico_sku(pron: pd.DataFrame) -> pd.DataFrame:
    columnas = [c for c in _COLUMNAS_PRONOSTICO if c in pron.columns]
    return pron[columnas].sort_values(pc.COL_PRONOSTICO_LRI, ascending=False).rename(columns=_ETIQUETAS)


def _mostrar_pronostico_sku(pron: pd.DataFrame, altura: int | str = "auto") -> None:
    tabla = _tabla_pronostico_sku(pron)
    formato = {_ETIQUETAS.get(k, k): v for k, v in _FORMATO_TABLA.items() if _ETIQUETAS.get(k, k) in tabla.columns}
    st.dataframe(
        tabla.style.format(formato, na_rep="—").set_properties(
            subset=[_ETIQUETAS[pc.COL_PRONOSTICO_LRI]], **_ESTILO_PRONOSTICO
        ),
        width="stretch",
        height=altura,
        hide_index=True,
    )


def _clave_grupo(nivel: str) -> str:
    return f"pron_grupo_{_NIVELES_CERTIFICACION[nivel]}"


def _grupos(tabla: pd.DataFrame, nivel: str) -> pd.Series:
    return tabla[_NIVELES_CERTIFICACION[nivel]].fillna("(sin dato)").astype(str).str.strip()


def _articulo_nivel(nivel: str) -> str:
    return f"{'un' if nivel == 'Proveedor' else 'una'} {nivel.lower()}"


def _cambiar_nivel_pronostico() -> None:
    """Al pulsar categoría, subcategoría o proveedor (aunque ya esté activo) se abre el panel para escoger."""
    nivel = st.session_state.get(_CLAVE_NIVEL_PRONOSTICO) or st.session_state.get(_CLAVE_NIVEL_ANTERIOR, "SKU")
    st.session_state[_CLAVE_NIVEL_PRONOSTICO] = nivel
    st.session_state[_CLAVE_NIVEL_ANTERIOR] = nivel
    st.session_state[_CLAVE_ABRIR_GRUPO] = _NIVELES_CERTIFICACION.get(nivel) is not None


def _abrir_panel_grupo() -> None:
    st.session_state[_CLAVE_ABRIR_GRUPO] = True


@st.dialog("🔎 Elegir grupo", width="large")
def _dialogo_grupo_pronostico(pron: pd.DataFrame, nivel: str) -> None:
    clave = _clave_grupo(nivel)
    actual = st.session_state.get(clave)
    conteo = _grupos(pron, nivel).value_counts()
    st.markdown(f"**{nivel}** · haz clic para ver sus artículos con pronóstico.")
    with st.container(height=420):
        for i, grupo in enumerate(sorted(conteo.index)):
            if st.button(
                f"{grupo} — {conteo[grupo]} SKUs",
                key=f"{clave}_opcion_{i}",
                type="primary" if grupo == actual else "secondary",
                width="stretch",
            ):
                st.session_state[clave] = grupo
                st.rerun()


def _grafico_pronostico_skus(skus: pd.DataFrame, titulo: str) -> None:
    graf = skus.sort_values(pc.COL_PRONOSTICO_LRI, ascending=False)
    x = graf["codigo"].astype(str)
    descripcion = graf["descripcion"].fillna("") if "descripcion" in graf.columns else pd.Series("", index=graf.index)
    datos = np.column_stack([descripcion.astype(str), graf[pc.COL_PRONOSTICO_LRI].to_numpy(dtype=float)])
    plantilla = "<b>%{x}</b> · %{customdata[0]}<br>%{fullData.name}: %{y:,.1f}<br>Pronóstico: %{customdata[1]:,.1f}<extra></extra>"
    fig = go.Figure()
    fig.add_bar(x=x, y=graf["pronostico calc"], name="Promedio 12 meses", marker_color=COLOR_PRONOSTICO,
                customdata=datos, hovertemplate=plantilla)
    fig.add_bar(x=x, y=graf[pc.COL_SEGURIDAD_K], name="K × σ", marker_color=COLOR_AJUSTADO,
                customdata=datos, hovertemplate=plantilla)
    fig.update_layout(
        barmode="stack",
        height=300,
        title=f"Pronóstico mensual por SKU · {titulo} (mayor a menor)",
        title_font_size=14,
        margin=dict(t=36, b=0, l=0, r=0),
        xaxis=dict(type="category", categoryorder="array", categoryarray=x, showticklabels=len(graf) <= 40, tickangle=-45),
        yaxis_title="Unidades / mes",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1, traceorder="normal"),
    )
    _barras_delgadas(fig, len(graf))
    st.plotly_chart(fig, width="stretch")


def _reporte_pedido(skus: pd.DataFrame, excluidos: pd.DataFrame) -> bytes:
    hojas = {"Pronóstico por SKU": _tabla_pronostico_sku(skus)}
    if not excluidos.empty:
        hojas["Excluidos (no certificados)"] = _hoja_certificacion(excluidos)
    return _escribir_hojas(hojas)


def _vista_pronostico(calc: pd.DataFrame) -> None:
    limite = pc.CV_MAX_CERTIFICADO
    pron = calc[np.isfinite(calc[pc.COL_PRONOSTICO_LRI].to_numpy(dtype=float))]
    excluidos = calc.drop(index=pron.index)

    col_titulo, col_nivel = st.columns([3, 2], vertical_alignment="bottom")
    col_titulo.subheader("Pronóstico mensual")
    niveles = [n for n, col in _NIVELES_CERTIFICACION.items() if col is None or col in calc.columns]
    if st.session_state.get(_CLAVE_NIVEL_PRONOSTICO) not in niveles:
        st.session_state[_CLAVE_NIVEL_PRONOSTICO] = niveles[0]
    col_nivel.segmented_control(
        "Ver por",
        niveles,
        key=_CLAVE_NIVEL_PRONOSTICO,
        label_visibility="collapsed",
        on_change=_cambiar_nivel_pronostico,
    )
    nivel = st.session_state.get(_CLAVE_NIVEL_PRONOSTICO) or niveles[0]
    claves_k = " · ".join(
        f"{clase} {fill:.1%} → K {pc.factor_k([fill])[0]:.2f}" for clase, fill in pc.FILL_RATE_POR_CLASE.items()
    )
    st.caption(
        "**Pronóstico = promedio de los 12 meses + K × σ** · σ = desviación estándar de los 12 meses · "
        f"K = factor de seguridad según el fill rate deseado de la clase ({claves_k}). "
        f"Solo artículos certificados (CV ≤ {limite:.0%})."
    )
    if pron.empty:
        st.warning("Ningún SKU certificado con los filtros actuales.")
        return

    if _NIVELES_CERTIFICACION[nivel] is None:
        skus, excl, titulo = pron, excluidos, "Todos los SKUs"
        st.markdown(f"##### {titulo}")
    else:
        clave = _clave_grupo(nivel)
        if st.session_state.get(clave) not in set(_grupos(pron, nivel)):
            st.session_state[clave] = None
        if st.session_state.pop(_CLAVE_ABRIR_GRUPO, False):
            _dialogo_grupo_pronostico(pron, nivel)
        grupo = st.session_state.get(clave)
        col_sel, col_boton = st.columns([3, 1], vertical_alignment="center")
        col_boton.button(
            f"🔎 Elegir {nivel.lower()}",
            key="pron_btn_elegir_grupo",
            on_click=_abrir_panel_grupo,
            width="stretch",
        )
        if grupo is None:
            col_sel.info(f"Elige {_articulo_nivel(nivel)} para ver sus artículos con pronóstico.")
            return
        skus = pron[_grupos(pron, nivel) == grupo]
        excl = excluidos[_grupos(excluidos, nivel) == grupo]
        titulo = f"{nivel}: {grupo}"
        col_sel.markdown(f"##### {titulo}")

    promedio = float(skus["pronostico calc"].sum())
    total = float(skus[pc.COL_PRONOSTICO_LRI].sum())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SKUs con pronóstico", f"{len(skus):,}")
    c2.metric(
        "⚠️ Excluidos",
        f"{len(excl):,}",
        "Sin política aún",
        delta_color="off",
        help="No certificados (CV mayor a 30%): sin pronóstico hasta definir su política.",
        delta_arrow="off",
    )
    c3.metric("Promedio 12 meses (mes)", f"{promedio:,.0f}")
    c4.metric(
        "Pronóstico (mes)",
        f"{total:,.0f}",
        f"+{total - promedio:,.0f} por K × σ",
        delta_color="off",
        delta_arrow="off",
    )

    _grafico_pronostico_skus(skus, titulo)
    _mostrar_pronostico_sku(skus, altura=420 if len(skus) > 12 else "auto")

    if not excl.empty:
        with st.expander(f"⚠️ Artículos excluidos del pronóstico ({len(excl):,}) · pendientes de política"):
            st.caption(
                f"CV mayor a {limite:.0%}: no se les calcula pronóstico hasta definir su política "
                "(por el usuario o por la AI)."
            )
            _tabla_certificacion(excl)

    if st.session_state.get(_CLAVE_MOSTRAR_REPORTES):
        st.download_button(
            f"📥 Artículos a pedir · {titulo} (Excel)",
            data=_reporte_pedido(skus, excl),
            file_name=f"{_nombre_archivo(f'pronostico {titulo}')}.xlsx",
            mime=_MIME_XLSX,
            help="SKUs con descripción, clase, fill rate, K, promedio, σ, CV, K × σ y pronóstico (mayor a menor).",
        )


def _vista_serie(df: pd.DataFrame, calc: pd.DataFrame, meses: list[str]) -> None:
    st.subheader("Serie y métodos por SKU")
    etiquetas = {_etiqueta_sku(f): i for i, f in calc.iterrows()}
    elegido = st.selectbox("SKU", list(etiquetas))
    idx = etiquetas[elegido]
    fila = calc.loc[idx]
    serie = df.loc[idx, meses].to_numpy(dtype=float)
    x = list(range(1, len(meses) + 1))

    c1, c2, c3 = st.columns(3)
    ventana = c1.slider("Ventana promedio móvil (meses)", 2, max(2, len(meses) - 1), 3)
    alpha = c2.slider("α suavizamiento exponencial", 0.05, 0.95, 0.30, 0.05)
    c3.metric(
        "Certificación",
        fila[pc.COL_CERTIFICACION],
        f"CV {fila['cv']:.1%}" if np.isfinite(fila["cv"]) else None,
        delta_color="off",
    )

    mask = np.isfinite(serie)
    b, a = np.polyfit(np.array(x)[mask], serie[mask], 1) if mask.sum() >= 2 else (0.0, np.nanmean(serie))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=serie, mode="lines+markers", name="Demanda real", line=dict(color=COLOR_REAL)))
    fig.add_trace(go.Scatter(x=x, y=[a + b * t for t in x], mode="lines", name="Tendencia", line=dict(color=COLOR_TENDENCIA, dash="dot")))
    fig.add_hline(y=fila["pronostico calc"], line=dict(color=COLOR_PRONOSTICO, dash="dash"), annotation_text="Pronóstico")
    fig.add_hline(y=fila["pronostico ajustado calc"], line=dict(color=COLOR_AJUSTADO, dash="dash"), annotation_text="Pronóstico ajustado")
    fig.update_layout(xaxis_title="Mes", yaxis_title="Demanda (bultos)", hovermode="x unified", margin=dict(t=30))
    st.plotly_chart(fig, width="stretch")

    resultados = pc.comparar_metodos(serie, ventana=ventana, alpha=alpha)
    tabla = pd.DataFrame(
        [
            {
                "Método": r.metodo,
                "Pronóstico mes siguiente": r.pronostico,
                "MAD": r.mad,
                "MAPE": r.mape,
                "Sesgo": r.sesgo,
            }
            for r in resultados
        ]
    )
    mejor = tabla.loc[tabla["MAD"].idxmin(), "Método"] if tabla["MAD"].notna().any() else None
    st.dataframe(
        tabla.style.format(
            {"Pronóstico mes siguiente": "{:,.1f}", "MAD": "{:,.1f}", "MAPE": "{:.1%}", "Sesgo": "{:+,.1f}"},
            na_rep="—",
        ),
        width="stretch",
        hide_index=True,
    )
    st.caption(
        "Backtest un paso adelante desde el mes 4. Sesgo positivo = el método se quedó corto. "
        + (f"Menor error (MAD): **{mejor}**." if mejor else "")
    )


def _vista_estacionalidad(df: pd.DataFrame) -> None:
    st.subheader("Estacionalidad")
    opciones = {"Total": None}
    for col, etiqueta in (("categoria", "Categoría"), ("subcategoria", "Subcategoría"), ("proveedor", "Proveedor")):
        if col in df.columns:
            opciones[etiqueta] = col
    agrupar = opciones[st.radio("Agrupar por", list(opciones), horizontal=True)]
    indices = pc.indices_estacionales(df, agrupar)
    largo = indices.reset_index(names="grupo").melt(id_vars="grupo", var_name="mes", value_name="indice")
    fig = px.line(largo, x="mes", y="indice", color="grupo", markers=True)
    fig.add_hline(y=1.0, line=dict(color="gray", dash="dot"))
    fig.update_layout(yaxis_title="Índice (1.0 = mes promedio)", xaxis_title="", margin=dict(t=30))
    st.plotly_chart(fig, width="stretch")
    st.dataframe(indices.style.format("{:.2f}"), width="stretch")
    st.caption("Con un solo año de historia el índice es indicativo; se confirma con más años.")


def _vista_normal(df: pd.DataFrame, calc: pd.DataFrame, meses: list[str]) -> None:
    """EXP: bultos ↔ slider ↔ línea roja ↔ probabilidad objetivo (inv_cdf)."""
    st.subheader("Distribución normal de la demanda")
    st.caption(
        "EXPERIMENTAL · línea roja = bultos consultados; también puede fijarse por probabilidad."
    )
    etiquetas = {_etiqueta_sku(f): i for i, f in calc.iterrows()}
    elegido = st.selectbox("SKU", list(etiquetas), key="sku_normal_exp")
    idx = etiquetas[elegido]
    fila = calc.loc[idx]
    media, desv, nivel = fila["pronostico calc"], fila["desviacion calc"], fila["nivel servicio"]
    if not (np.isfinite(desv) and desv > 0):
        st.warning("El SKU no tiene variabilidad suficiente para una distribución normal.")
        return
    dist = NormalDist(media, desv)
    corte = float(fila["pronostico ajustado calc"])

    clave_val = "exp_demanda_consulta_bultos"
    clave_izq = "exp_delimitador_izq"
    clave_sku = "exp_demanda_consulta_sku"
    if st.session_state.get(clave_sku) != elegido or clave_val not in st.session_state:
        st.session_state[clave_val] = float(round(corte))
        st.session_state[clave_izq] = 0.0
        st.session_state[clave_sku] = elegido

    def _aplicar_bultos(valor: float) -> None:
        st.session_state[clave_val] = max(0.0, float(valor))

    def _desde_numero() -> None:
        _aplicar_bultos(st.session_state["exp_ni_demanda_bultos"])

    def _desde_slider() -> None:
        _aplicar_bultos(st.session_state["exp_sl_demanda_bultos"])

    def _desde_probabilidad() -> None:
        # Camino inverso: probabilidad → bultos (NormalDist.inv_cdf).
        p = float(st.session_state["exp_ni_prob_objetivo"])
        _aplicar_bultos(bultos_desde_probabilidad(media, desv, p))

    def _desde_slider_prob() -> None:
        p = float(st.session_state["exp_sl_prob_objetivo"])
        _aplicar_bultos(bultos_desde_probabilidad(media, desv, p))

    tope_slider = float(
        max(
            media + 5.0 * desv,
            float(st.session_state[clave_val]),
            corte,
            300.0,
        )
    )
    consulta_prev = float(st.session_state[clave_val])
    p_sync = probabilidad_desde_bultos(media, desv, consulta_prev)
    if not np.isfinite(p_sync):
        p_sync = float(nivel) if np.isfinite(nivel) else 0.8
    p_sync = float(min(max(p_sync, 0.001), 0.999))

    st.session_state["exp_ni_demanda_bultos"] = consulta_prev
    st.session_state["exp_sl_demanda_bultos"] = float(
        min(max(0.0, consulta_prev), tope_slider)
    )
    st.session_state["exp_ni_prob_objetivo"] = p_sync
    st.session_state["exp_sl_prob_objetivo"] = p_sync

    c_in, c_sl = st.columns([1, 2])
    with c_in:
        st.number_input(
            "¿Probabilidad de que la demanda no supere…? (bultos)",
            min_value=0.0,
            step=1.0,
            key="exp_ni_demanda_bultos",
            on_change=_desde_numero,
        )
    with c_sl:
        st.slider(
            "Demanda consultada (bultos)",
            min_value=0.0,
            max_value=tope_slider,
            step=1.0,
            key="exp_sl_demanda_bultos",
            on_change=_desde_slider,
        )

    c_p1, c_p2 = st.columns([1, 2])
    with c_p1:
        st.number_input(
            "Probabilidad objetivo P(demanda ≤ x)",
            min_value=0.001,
            max_value=0.999,
            step=0.001,
            format="%.3f",
            key="exp_ni_prob_objetivo",
            on_change=_desde_probabilidad,
            help="Camino inverso: fija la probabilidad y mueve bultos, slider y línea roja.",
        )
    with c_p2:
        st.slider(
            "Probabilidad objetivo",
            min_value=0.001,
            max_value=0.999,
            step=0.001,
            format="%.3f",
            key="exp_sl_prob_objetivo",
            on_change=_desde_slider_prob,
        )

    consulta = float(st.session_state[clave_val])

    # --- Histograma interactivo estilo @RISK (barras que cambian de color) ---
    st.markdown("##### Distribución con delimitadores (estilo @RISK)")
    eje = rango_eje_x_demanda(media, desv, consulta)
    x_min_eje, x_max_eje = float(eje[0]), float(eje[-1])
    # Ampliar un poco para que quepan ambos mangos del rango.
    x_min_eje = min(x_min_eje, 0.0)
    x_max_eje = max(x_max_eje, consulta, media + 4 * desv)

    st.session_state.setdefault(clave_izq, 0.0)

    def _desde_rango() -> None:
        lo, hi = st.session_state["exp_sl_rango_delimitadores"]
        st.session_state[clave_izq] = float(min(lo, hi))
        _aplicar_bultos(float(max(lo, hi)))

    x_izq_prev = float(st.session_state[clave_izq])
    # Mantener izq. ≤ der. (consulta).
    if x_izq_prev > consulta:
        x_izq_prev = max(0.0, min(x_izq_prev, consulta))
        st.session_state[clave_izq] = x_izq_prev

    st.session_state["exp_sl_rango_delimitadores"] = (
        float(min(max(x_min_eje, x_izq_prev), x_max_eje)),
        float(min(max(x_min_eje, consulta), x_max_eje)),
    )
    st.slider(
        "Delimitadores (bultos) — mueva los mangos: las barras cambian de color",
        min_value=float(x_min_eje),
        max_value=float(x_max_eje),
        step=1.0,
        key="exp_sl_rango_delimitadores",
        on_change=_desde_rango,
    )

    consulta = float(st.session_state[clave_val])
    x_izq = float(st.session_state[clave_izq])
    p_izq, p_centro, p_der, x_lo, x_hi = zonas_probabilidad_delimitadores(
        media, desv, x_izq, consulta
    )

    # Franja superior de porcentajes (como @RISK).
    st.markdown(
        f"""
        <div style="display:flex;width:100%;border-radius:6px;overflow:hidden;
        font-weight:700;font-size:0.95rem;text-align:center;margin:0.25rem 0 0.75rem 0;">
          <div style="flex:{max(p_izq, 0.001):.4f};background:#FECACA;color:#7F1D1D;padding:0.45rem 0.25rem;">
            {p_izq:.1%}
          </div>
          <div style="flex:{max(p_centro, 0.001):.4f};background:#DC2626;color:#fff;padding:0.45rem 0.25rem;">
            {p_centro:.1%}
          </div>
          <div style="flex:{max(p_der, 0.001):.4f};background:#FECACA;color:#7F1D1D;padding:0.45rem 0.25rem;">
            {p_der:.1%}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    centers, heights, width = discretizar_normal_barras(
        media, desv, x_min_eje, x_max_eje, n_bins=52
    )
    colores = colores_barras_zonas(centers, x_lo, x_hi)

    fig = go.Figure(
        go.Bar(
            x=centers,
            y=heights,
            width=width * 0.92,
            marker=dict(color=colores, line=dict(width=0)),
            name="Densidad normal",
            hovertemplate="Demanda %{x:.0f} bultos<br>Densidad %{y:.5f}<extra></extra>",
        )
    )
    fig.add_vline(
        x=x_lo,
        line=dict(color="#1E293B", width=2),
        annotation_text=f"{x_lo:,.0f}",
    )
    fig.add_vline(
        x=x_hi,
        line=dict(color=COLOR_AJUSTADO, width=2),
        annotation_text=f"{x_hi:,.0f}",
    )
    fig.update_layout(
        xaxis_title="Demanda mensual (bultos)",
        yaxis_title="Densidad",
        margin=dict(t=36, b=40),
        showlegend=False,
        bargap=0.05,
        xaxis_range=[x_min_eje, x_max_eje],
    )
    st.plotly_chart(fig, width="stretch")

    z1, z2, z3 = st.columns(3)
    z1.metric(f"Cola izq. (≤ {x_lo:,.0f})", f"{p_izq:.1%}")
    z2.metric(f"Centro ({x_lo:,.0f} → {x_hi:,.0f})", f"{p_centro:.1%}")
    z3.metric(f"Cola der. (> {x_hi:,.0f})", f"{p_der:.1%}")

    with st.expander("Meses reales del SKU (referencia)", expanded=False):
        fig_h = go.Figure(
            go.Histogram(
                x=df.loc[idx, meses].astype(float),
                histnorm="probability density",
                name="Meses reales",
                marker_color="#64748b",
                opacity=0.7,
            )
        )
        fig_h.update_layout(
            xaxis_title="Bultos",
            yaxis_title="Densidad",
            margin=dict(t=20),
            height=260,
        )
        st.plotly_chart(fig_h, width="stretch")

    st.caption(
        f"EXPERIMENTAL · barras sólidas = zona entre delimitadores · "
        f"pronóstico ajustado ref. {corte:,.1f} · nivel Excel {nivel:.0%}. "
        f"No altera el motor oficial ni la app de producción."
    )


def _vista_montecarlo(calc: pd.DataFrame) -> None:
    st.subheader("Simulación Monte Carlo")
    etiquetas = {_etiqueta_sku(f): i for i, f in calc.iterrows()}
    elegido = st.selectbox("SKU", list(etiquetas), key="sku_mc")
    fila = calc.loc[etiquetas[elegido]]
    c1, c2 = st.columns(2)
    n = c1.select_slider("Simulaciones", options=[1_000, 5_000, 10_000, 50_000], value=10_000)
    semilla = c2.number_input("Semilla", min_value=0, value=42, step=1)
    sim = pc.simular_montecarlo(fila["pronostico calc"], fila["desviacion calc"], n, int(semilla))
    corte = fila["pronostico ajustado calc"]

    p50, p90, p95 = np.percentile(sim, [50, 90, 95])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Media simulada", f"{sim.mean():,.1f}")
    c2.metric("P50 / P90", f"{p50:,.0f} / {p90:,.0f}")
    c3.metric("P95", f"{p95:,.0f}")
    c4.metric("Cobertura del pronóstico ajustado", f"{(sim <= corte).mean():.1%}", f"objetivo {fila['nivel servicio']:.0%}")

    fig = px.histogram(x=sim, nbins=60, labels={"x": "Demanda mensual simulada (bultos)"})
    fig.update_traces(marker_color=COLOR_REAL, opacity=0.8)
    fig.add_vline(x=corte, line=dict(color=COLOR_AJUSTADO, dash="dash"), annotation_text="Pronóstico ajustado")
    fig.update_layout(yaxis_title="Frecuencia", margin=dict(t=30))
    st.plotly_chart(fig, width="stretch")


def main() -> None:
    st.markdown(
        "#### 📈 LRI Forecast Pro · EXP "
        "<span style='font-size:0.8rem;font-weight:400;opacity:0.7'>"
        "· línea roja = demanda consultada (copia experimental; producción intacta)</span>",
        unsafe_allow_html=True,
    )

    fuente = _seccion_archivo()
    hojas, err_hojas = _cargar_hojas(fuente.contenido, fuente.mtime)
    df, err = _cargar_demanda(fuente.contenido, fuente.mtime)
    if err or df is None:
        st.error(err or err_hojas or "No se pudieron cargar los datos.")
        st.stop()

    resultado = _seccion_calculo(df, fuente)

    vista = st.session_state[_CLAVE_VISTA]

    if st.session_state[_CLAVE_MOSTRAR_ARCHIVO]:
        if hojas:
            _vista_archivo(hojas, fuente)
        else:
            st.error(err_hojas or "No se pudo leer el archivo completo.")
        if resultado is not None:
            st.divider()

    if resultado is None:
        return

    st.sidebar.subheader("Filtros")
    calc = _filtros(resultado["calc"])
    if calc.empty:
        st.warning("Ningún SKU cumple los filtros.")
        return
    df_f = df.loc[calc.index]
    meses = pc.columnas_meses(df_f)

    if vista == VISTA_PRONOSTICO:
        _vista_pronostico(calc)
    elif vista == "Certificación":
        _vista_certificacion(df_f, calc, meses, nivel_override=resultado["nivel"] is not None)
    elif vista == "Serie por SKU":
        _vista_serie(df_f, calc, meses)
    elif vista == "Estacionalidad":
        _vista_estacionalidad(df_f)
    elif vista == "Distribución normal":
        _vista_normal(df_f, calc, meses)
    elif vista == "Monte Carlo":
        _vista_montecarlo(calc)


main()
