"""LRI Forecast Pro — app Streamlit del módulo 1: Pronóstico (file-based).

Lee el Excel compartido ``data/sources/perfilado.xlsx`` (mismo archivo de
Inventarios, Compras y Profile Pro). Panel lateral (formato Profile Pro):
cargar datos → casilla «Mostrar archivo» → botón «Calcular pronóstico» y,
debajo, sus opciones: certificación, serie por SKU, estacionalidad,
distribución normal y Monte Carlo.

Ejecutar:
    streamlit run modules/pronostico/pronostico_app.py
"""
from __future__ import annotations

import io
import os
import re
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

_DIR_ACTUAL = os.path.dirname(os.path.abspath(__file__))
if _DIR_ACTUAL not in sys.path:
    sys.path.insert(0, _DIR_ACTUAL)

import pronostico_calculos as pc  # noqa: E402
import pronostico_excel as pexcel  # noqa: E402

st.set_page_config(page_title="LRI Forecast Pro", page_icon="📈", layout="wide")

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
_CLAVE_NIVEL_PRONOSTICO = "pron_nivel_pronostico"
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
    st.session_state[_CLAVE_MOSTRAR_ARCHIVO] = False


def _calcular_pronostico(df: pd.DataFrame, nivel: float | None, clave_fuente: tuple) -> None:
    _calcular(df, nivel, clave_fuente)
    st.session_state[_CLAVE_VISTA] = VISTA_PRONOSTICO


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
        args=(df, nivel, fuente.clave),
    )
    if resultado is None:
        zona_calculo.caption("Aún no se ha calculado el pronóstico.")
    else:
        zona_calculo.caption(f"✓ Calculado a las {resultado['hora']:%H:%M} · {len(resultado['calc']):,} SKUs")
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


def _tabla_pronostico_grupo(calc: pd.DataFrame, nivel: str) -> pd.DataFrame:
    return pc.consolidar_pronostico(calc, _NIVELES_CERTIFICACION[nivel]).rename(
        columns={
            "grupo": nivel,
            "skus": "SKUs",
            "promedio": _ETIQUETAS["pronostico calc"],
            "seguridad": _ETIQUETAS[pc.COL_SEGURIDAD_K],
            "pronostico": _ETIQUETAS[pc.COL_PRONOSTICO_LRI],
            "pct_total": "% del total",
        }
    )


def _reporte_pronostico(calc: pd.DataFrame, pron: pd.DataFrame, excluidos: pd.DataFrame) -> bytes:
    hojas = {"Por SKU": _tabla_pronostico_sku(pron)}
    for nivel, columna in _NIVELES_CERTIFICACION.items():
        if columna and columna in calc.columns:
            hojas[f"Por {nivel.lower()}"] = _tabla_pronostico_grupo(calc, nivel)
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
    nivel = (
        col_nivel.segmented_control(
            "Ver por", niveles, default=niveles[0], key=_CLAVE_NIVEL_PRONOSTICO, label_visibility="collapsed"
        )
        or niveles[0]
    )
    claves_k = " · ".join(
        f"{clase} {fill:.1%} → K {pc.factor_k([fill])[0]:.2f}" for clase, fill in pc.FILL_RATE_POR_CLASE.items()
    )
    st.caption(
        "**Pronóstico = promedio de los 12 meses + K × σ** · σ = desviación estándar de los 12 meses · "
        f"K = factor de seguridad según el fill rate deseado de la clase ({claves_k}). "
        f"Solo artículos certificados (CV ≤ {limite:.0%})."
    )

    promedio = float(pron["pronostico calc"].sum())
    total = float(pron[pc.COL_PRONOSTICO_LRI].sum())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SKUs pronosticados", f"{len(pron):,}")
    c2.metric(
        "⚠️ Excluidos",
        f"{len(excluidos):,}",
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
    if pron.empty:
        st.warning("Ningún SKU certificado con los filtros actuales.")
        return

    formato = {k: v for k, v in _FORMATO_TABLA.items()}
    if _NIVELES_CERTIFICACION[nivel] is None:
        tabla = _tabla_pronostico_sku(pron)
        formato_sku = {_ETIQUETAS.get(k, k): v for k, v in formato.items() if _ETIQUETAS.get(k, k) in tabla.columns}
        st.dataframe(
            tabla.style.format(formato_sku, na_rep="—").set_properties(
                subset=[_ETIQUETAS[pc.COL_PRONOSTICO_LRI]], **{"font-weight": "bold"}
            ),
            width="stretch",
            height=460,
            hide_index=True,
        )
    else:
        tabla = _tabla_pronostico_grupo(calc, nivel)
        graf = tabla.melt(
            id_vars=[nivel],
            value_vars=[_ETIQUETAS["pronostico calc"], _ETIQUETAS[pc.COL_SEGURIDAD_K]],
            var_name="Componente",
            value_name="Unidades",
        )
        fig = px.bar(
            graf,
            x=nivel,
            y="Unidades",
            color="Componente",
            color_discrete_sequence=[COLOR_PRONOSTICO, COLOR_AJUSTADO],
            title=f"Pronóstico mensual por {nivel.lower()} (promedio + K × σ)",
        )
        fig.update_layout(
            height=320,
            margin=dict(t=40, b=0, l=0, r=0),
            xaxis=dict(type="category", categoryorder="array", categoryarray=tabla[nivel]),
            legend_title_text="",
        )
        st.plotly_chart(fig, width="stretch")
        numeros = {c: "{:,.1f}" for c in tabla.columns[2:5]}
        st.dataframe(
            tabla.style.format({**numeros, "% del total": "{:.1%}"}),
            width="stretch",
            hide_index=True,
        )

    if not excluidos.empty:
        with st.expander(f"⚠️ Artículos excluidos del pronóstico ({len(excluidos):,}) · pendientes de política"):
            st.caption(
                f"CV mayor a {limite:.0%}: no se les calcula pronóstico hasta definir su política "
                "(por el usuario o por la AI)."
            )
            _tabla_certificacion(excluidos)

    if st.session_state.get(_CLAVE_MOSTRAR_REPORTES):
        st.download_button(
            "📥 Pronóstico (Excel)",
            data=_reporte_pronostico(calc, pron, excluidos),
            file_name="pronostico_mensual_lri.xlsx",
            mime=_MIME_XLSX,
            help="Hojas: por SKU, por categoría, por subcategoría, por proveedor y excluidos.",
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
    st.subheader("Distribución normal de la demanda")
    etiquetas = {_etiqueta_sku(f): i for i, f in calc.iterrows()}
    elegido = st.selectbox("SKU", list(etiquetas), key="sku_normal")
    idx = etiquetas[elegido]
    fila = calc.loc[idx]
    media, desv, nivel = fila["pronostico calc"], fila["desviacion calc"], fila["nivel servicio"]
    if not (np.isfinite(desv) and desv > 0):
        st.warning("El SKU no tiene variabilidad suficiente para una distribución normal.")
        return
    dist = NormalDist(media, desv)
    xs = np.linspace(max(0.0, media - 4 * desv), media + 4 * desv, 300)
    ys = [dist.pdf(v) for v in xs]
    corte = fila["pronostico ajustado calc"]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name="Normal", line=dict(color=COLOR_REAL)))
    zona = xs <= corte
    fig.add_trace(go.Scatter(x=xs[zona], y=np.array(ys)[zona], fill="tozeroy", mode="none", name=f"Cubierto {nivel:.0%}", fillcolor="rgba(34,197,94,0.3)"))
    fig.add_trace(go.Histogram(x=df.loc[idx, meses].astype(float), histnorm="probability density", name="Meses reales", opacity=0.35, marker_color="#64748b"))
    fig.add_vline(x=corte, line=dict(color=COLOR_AJUSTADO, dash="dash"), annotation_text="Pronóstico ajustado")
    fig.update_layout(xaxis_title="Demanda mensual (bultos)", yaxis_title="Densidad", margin=dict(t=30), barmode="overlay")
    st.plotly_chart(fig, width="stretch")

    consulta = st.number_input("¿Probabilidad de que la demanda no supere…? (bultos)", min_value=0.0, value=float(round(corte)))
    st.metric("Probabilidad", f"{dist.cdf(consulta):.1%}")


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
        "#### 📈 LRI Forecast Pro "
        "<span style='font-size:0.8rem;font-weight:400;opacity:0.7'>"
        "· Módulo 1 · Pronóstico de demanda sobre el archivo compartido de LRI</span>",
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
