"""LRI Forecast Pro — app Streamlit del módulo 1: Pronóstico (file-based).

Lee el Excel compartido ``data/sources/perfilado.xlsx`` (mismo archivo de
Inventarios, Compras y Profile Pro). Panel lateral (formato Profile Pro):
cargar datos → casilla opcional «Abrir archivo» → botón «Calcular pronóstico» y,
debajo, sus opciones: certificación, simulación Monte Carlo (@RISK), serie por SKU
y estacionalidad. Al iniciar no se muestra el Excel; el foco es el cálculo del
pronóstico.

Ejecutar:
    streamlit run modules/pronostico/pronostico_app.py
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

_DIR_ACTUAL = os.path.dirname(os.path.abspath(__file__))
_DIR_EXPERIMENTOS = os.path.join(_DIR_ACTUAL, "_experimentos")
for _p in (_DIR_ACTUAL, _DIR_EXPERIMENTOS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

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

st.set_page_config(page_title="LRI Forecast Pro", page_icon="📈", layout="wide")

_CLAVE_CONTENEDOR_TABLA = "pron_tabla_archivo"
_CLAVE_CONTENEDOR_PRON = "pron_tabla_pronostico"
# Altura en px del st.dataframe (no «stretch»): así el scroll es interno y la
# barra horizontal queda al pie del marco, visible en la primera pantalla.
# Cabecera + esta altura deben caber en la primera pantalla (barra horizontal a la vista).
_ALTURA_TABLA_ARCHIVO_PX = 460
_ALTURA_TABLA_PRONOSTICO_PX = 320

# Fondos Plotly (solo estética; no altera series ni marker_color).
_PLOTLY_PAPER = "#051426"
_PLOTLY_PLOT = "#051426"
_PLOTLY_TEXTO = "#FFFFFF"
_PLOTLY_EJE = "#C5D8E8"
_PLOTLY_REJILLA = "rgba(8, 118, 185, 0.22)"


def _cargar_tema_visual() -> None:
    """Inyecta forecast_theme.css (solo apariencia de Forecast Pro)."""
    ruta_css = os.path.join(_DIR_ACTUAL, "forecast_theme.css")
    try:
        with open(ruta_css, encoding="utf-8") as f:
            css = f.read()
    except OSError:
        return
    st.markdown(f"<style>\n{css}\n</style>", unsafe_allow_html=True)


def _estilo_fondo_plotly(fig: go.Figure) -> None:
    """Fondo, ejes y rejilla oscuros; no toca colores de barras ni datos."""
    fig.update_layout(
        paper_bgcolor=_PLOTLY_PAPER,
        plot_bgcolor=_PLOTLY_PLOT,
        font=dict(color=_PLOTLY_TEXTO),
        title_font=dict(color=_PLOTLY_TEXTO),
        legend=dict(font=dict(color=_PLOTLY_TEXTO)),
    )
    fig.update_xaxes(
        gridcolor=_PLOTLY_REJILLA,
        zerolinecolor=_PLOTLY_REJILLA,
        tickfont=dict(color=_PLOTLY_EJE),
        title_font=dict(color=_PLOTLY_EJE),
        linecolor=_PLOTLY_EJE,
    )
    fig.update_yaxes(
        gridcolor=_PLOTLY_REJILLA,
        zerolinecolor=_PLOTLY_REJILLA,
        tickfont=dict(color=_PLOTLY_EJE),
        title_font=dict(color=_PLOTLY_EJE),
        linecolor=_PLOTLY_EJE,
    )


_cargar_tema_visual()

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

# Excel imprimible / de entrega del cálculo (columnas principales).
_COLUMNAS_ARCHIVO_PRONOSTICO = (
    "codigo",
    "descripcion",
    "categoria",
    "subcategoria",
    "proveedor",
    "clase",
    "nivel servicio",
    "fill rate deseado",
    "inventario final bulto",
    "inventario promedio bultos",
    "cv",
    "desviacion calc",
    "pronostico calc",
    pc.COL_SEGURIDAD_K,
    pc.COL_PRONOSTICO_LRI,
    pc.COL_CERTIFICACION,
)
_ETIQUETAS_ARCHIVO_PRONOSTICO = {
    **_ETIQUETAS,
    "nivel servicio": "Nivel de servicio",
    "inventario final bulto": "Inventario final (bultos)",
    "inventario promedio bultos": "Inventario promedio (bultos)",
    "cv": "Variabilidad (CV)",
    "desviacion calc": "Desviación estándar",
    "pronostico calc": "Promedio 12 meses",
    pc.COL_PRONOSTICO_LRI: "Pronóstico LRI",
}

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
VISTAS = ("Certificación", "Simulación Monte Carlo", "Serie por SKU", "Estacionalidad")
_ICONOS_VISTA = {
    "Certificación": "✅",
    "Simulación Monte Carlo": "🎲",
    "Serie por SKU": "📉",
    "Estacionalidad": "📅",
}
_AYUDA_VISTA = {
    "Certificación": "SKUs con CV entre 0% y 30% (aptos para modelo estadístico) y los que quedan fuera.",
    "Simulación Monte Carlo": "Histograma estilo @RISK: delimitadores, probabilidad y riesgo por zonas (anaranjado).",
    "Serie por SKU": "Demanda real, tendencia y comparación de métodos (móvil, exponencial, regresión).",
    "Estacionalidad": "Índice mensual por total, categoría, subcategoría o proveedor.",
}
_VISTAS_LEGACY = {
    "Distribución normal": "Simulación Monte Carlo",
    "Monte Carlo": "Simulación Monte Carlo",
}
_CLAVE_VISTA = "pron_vista"
_CLAVE_RESULTADO = "pron_resultado"
_CLAVE_MOSTRAR_ARCHIVO = "pron_mostrar_archivo"
_CLAVE_MOSTRAR_REPORTES = "pron_mostrar_reportes"
_CLAVE_ANCHO_BARRAS = "pron_ancho_barras"
_CLAVE_ESCRITURA_PRONOSTICO = "pron_escritura_pronostico"
_CLAVE_ARCHIVO_TOKEN = "pron_archivo_token"  # fuerza remount de «Mostrar archivo» tras calcular
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
    st.session_state.setdefault(_CLAVE_MOSTRAR_ARCHIVO, False)
    st.sidebar.button(
        "📁 Abrir archivo",
        key="pron_btn_abrir_archivo",
        type="primary" if st.session_state[_CLAVE_MOSTRAR_ARCHIVO] else "secondary",
        width="stretch",
        help="Muestra solo el Excel en pantalla (oculta pronóstico y alternativas).",
        on_click=_activar_vista_archivo,
    )
    return fuente


def _activar_vista_archivo() -> None:
    """Vista exclusiva: solo el archivo Excel."""
    st.session_state[_CLAVE_MOSTRAR_ARCHIVO] = True


def _cerrar_vista_archivo() -> None:
    """Al ir a cálculo o una alternativa, se oculta el Excel."""
    st.session_state[_CLAVE_MOSTRAR_ARCHIVO] = False


def _misma_fuente_datos(clave_guardada: tuple, fuente: Fuente) -> bool:
    """True si el cálculo sigue valiendo: mismo archivo (el mtime puede cambiar al escribir)."""
    if not clave_guardada:
        return False
    nombre_ok = clave_guardada[0] == fuente.nombre
    # Subido: comparar tamaño del contenido; compartido en disco: solo el nombre.
    if fuente.contenido is not None:
        return nombre_ok and clave_guardada[2] == len(fuente.contenido)
    return nombre_ok and fuente.ruta is not None


def _calcular(df: pd.DataFrame, nivel: float | None, clave_fuente: tuple) -> None:
    st.session_state[_CLAVE_RESULTADO] = {
        "fuente": clave_fuente,
        "nivel": nivel,
        "calc": pc.calcular_pronostico(df, nivel),
        "hora": datetime.now(),
    }
    st.session_state.pop(_CLAVE_ESCRITURA_PRONOSTICO, None)
    st.session_state[_CLAVE_ARCHIVO_TOKEN] = int(st.session_state.get(_CLAVE_ARCHIVO_TOKEN, 0)) + 1
    _cerrar_vista_archivo()


def _calcular_pronostico(df: pd.DataFrame, nivel: float | None, fuente: Fuente) -> None:
    _calcular(df, nivel, fuente.clave)
    st.session_state[_CLAVE_VISTA] = VISTA_PRONOSTICO
    _cerrar_vista_archivo()
    if fuente.ruta:
        # Forzar escritura + limpiar caché para que «Mostrar archivo» relea el Excel.
        _escribir_pronostico(fuente, forzar=True)
    else:
        st.session_state[_CLAVE_ESCRITURA_PRONOSTICO] = (
            pexcel.ResultadoEscritura(
                "error",
                mensaje=(
                    "El archivo subido no se escribe en disco. "
                    "Use el Excel compartido (perfilado.xlsx) o pulse "
                    "«Actualizar pronóstico en Excel» con ese archivo."
                ),
            ),
            None,
        )


def _escribir_pronostico(fuente: Fuente, *, forzar: bool = False) -> None:
    """Pone el pronóstico en la columna «pronostico» del Excel compartido y copia el espejo."""
    resultado = st.session_state.get(_CLAVE_RESULTADO)
    if resultado is None or not fuente.ruta:
        return
    calc = resultado["calc"]
    escritura = pexcel.escribir_pronostico_excel(
        dict(zip(calc["codigo"], calc[pc.COL_PRONOSTICO_LRI])),
        fuente.ruta,
        forzar=forzar,
    )
    # Siempre refrescar caché: «Mostrar archivo» debe releer el Excel de disco.
    _cargar_demanda.clear()
    _cargar_hojas.clear()
    espejo = os.path.join(os.path.dirname(fuente.ruta), _ARCHIVO_ESPEJO)
    aviso_espejo = None
    if escritura.estado in ("actualizado", "sin cambios") and os.path.isfile(espejo):
        try:
            shutil.copy2(fuente.ruta, espejo)
        except OSError:
            aviso_espejo = (
                f"No se pudo copiar a {_ARCHIVO_ESPEJO} (¿está abierto?). "
                "perfilado.xlsx sí tiene el pronóstico LRI."
            )
    st.session_state[_CLAVE_ESCRITURA_PRONOSTICO] = (escritura, aviso_espejo)
    st.session_state[_CLAVE_ARCHIVO_TOKEN] = int(st.session_state.get(_CLAVE_ARCHIVO_TOKEN, 0)) + 1
    if escritura.estado not in ("actualizado", "sin cambios"):
        return
    mtime = os.path.getmtime(fuente.ruta)
    df, _ = _cargar_demanda(None, mtime)
    if df is not None:
        resultado["calc"] = pc.calcular_pronostico(df, resultado["nivel"])
    # Actualizar clave al mtime nuevo sin invalidar el cálculo (el archivo es el mismo).
    resultado["fuente"] = Fuente(None, fuente.nombre, fuente.ruta, mtime).clave


def _actualizar_pronostico_excel(fuente: Fuente) -> None:
    """Reescribe el último cálculo en perfilado.xlsx (forzado; cerrar Excel si está abierto)."""
    if st.session_state.get(_CLAVE_RESULTADO) is None:
        st.session_state[_CLAVE_ESCRITURA_PRONOSTICO] = (
            pexcel.ResultadoEscritura(
                "error",
                mensaje="Primero pulse «📈 Cálculo del pronóstico».",
            ),
            None,
        )
        return
    if not fuente.ruta:
        st.session_state[_CLAVE_ESCRITURA_PRONOSTICO] = (
            pexcel.ResultadoEscritura(
                "error",
                mensaje=(
                    "Solo se actualiza el Excel compartido en disco (perfilado.xlsx). "
                    "Quite el archivo subido o use el archivo por defecto."
                ),
            ),
            None,
        )
        return
    _escribir_pronostico(fuente, forzar=True)


def _aviso_escritura_pronostico(zona) -> None:
    """Solo avisa si falló la escritura o la copia al espejo (sin mensaje de éxito)."""
    guardado = st.session_state.get(_CLAVE_ESCRITURA_PRONOSTICO)
    if guardado is None:
        return
    escritura, aviso_espejo = guardado
    if escritura.estado not in ("actualizado", "sin cambios"):
        zona.warning(f"No se pudo escribir el pronóstico en el Excel: {escritura.mensaje}")
    if aviso_espejo:
        zona.warning(aviso_espejo)


def _elegir_alternativa(vista: str, df: pd.DataFrame, nivel: float | None, clave_fuente: tuple) -> None:
    st.session_state[_CLAVE_VISTA] = vista
    _cerrar_vista_archivo()
    resultado = st.session_state.get(_CLAVE_RESULTADO)
    if resultado is None or (resultado.get("fuente") or (None,))[0] != clave_fuente[0]:
        _calcular(df, nivel, clave_fuente)


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
    if resultado and not _misma_fuente_datos(resultado.get("fuente"), fuente):
        st.session_state.pop(_CLAVE_RESULTADO)
        resultado = None
    elif resultado is not None:
        # El mtime cambia al escribir fill rate / pronóstico; conservar el cálculo.
        resultado["fuente"] = fuente.clave

    st.session_state.setdefault(_CLAVE_VISTA, VISTA_PRONOSTICO)
    solo_archivo = bool(st.session_state.get(_CLAVE_MOSTRAR_ARCHIVO))
    activa = None if solo_archivo or resultado is None else st.session_state[_CLAVE_VISTA]
    zona_calculo.markdown("##### Cálculo")
    zona_calculo.button(
        "📈 Cálculo del pronóstico",
        key="pron_btn_calculo",
        type="primary" if activa == VISTA_PRONOSTICO else "secondary",
        width="stretch",
        help=(
            "Pronóstico = promedio 12 meses + K × σ (K según el fill rate deseado). "
            "Solo artículos certificados (CV ≤ 30%). "
            "Con el Excel compartido, también escribe la columna «pronostico» en perfilado.xlsx. "
            "Oculta la vista del archivo para mostrar solo el pronóstico."
        ),
        on_click=_calcular_pronostico,
        args=(df, nivel, fuente),
    )
    if resultado is None:
        zona_calculo.caption(
            "Aún no se ha calculado el pronóstico. "
            "Tras calcular, podrá crear el archivo Excel del pronóstico."
        )
    else:
        zona_calculo.caption(f"✓ Calculado a las {resultado['hora']:%H:%M} · {len(resultado['calc']):,} SKUs")
        _aviso_escritura_pronostico(zona_calculo)
        zona_calculo.download_button(
            "📥 Crear archivo Excel del pronóstico",
            data=_excel_archivo_pronostico(resultado["calc"], df),
            file_name=f"pronostico_lri_{resultado['hora']:%Y%m%d_%H%M}.xlsx",
            mime=_MIME_XLSX,
            key="pron_dl_archivo_pronostico",
            type="secondary",
            width="stretch",
            help=(
                "Descarga un Excel con código, descripción, categoría, subcategoría, proveedor, "
                "nivel de servicio, inventario, variabilidad (CV) y pronóstico LRI."
            ),
        )
        if resultado["nivel"] != nivel:
            zona_calculo.warning("Cambiaste el nivel de servicio: vuelve a calcular.")
        if not fuente.ruta:
            zona_calculo.caption(
                "Archivo subido: el cálculo es solo en pantalla. "
                "Este Excel de pronóstico es independiente del maestro perfilado.xlsx."
            )

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


def _columna_por_nombre_canonico(df: pd.DataFrame, nombre: str) -> str | None:
    for col in df.columns:
        if pc._nombre_canonico(str(col)) == nombre:
            return col
    return None


def _sincronizar_pronostico_en_vista(
    df_hoja: pd.DataFrame, calc: pd.DataFrame
) -> tuple[pd.DataFrame, int]:
    """
    En la tabla en pantalla, sustituye «pronostico» (y «pronostico ajustado»)
    con el LRI del último cálculo, alineado por código. Se «cae encima» de los
    valores anteriores del Excel para que «Mostrar archivo» muestre el cálculo actual.
    """
    out = df_hoja.copy()
    col_cod = _columna_por_nombre_canonico(out, "codigo")
    col_pron = _columna_por_nombre_canonico(out, pc.COL_PRONOSTICO)
    if col_cod is None or col_pron is None or calc is None or calc.empty:
        return out, 0
    mapa = {
        pexcel.normalizar_codigo(c): float(v)
        for c, v in zip(calc["codigo"], calc[pc.COL_PRONOSTICO_LRI])
        if np.isfinite(v)
    }
    if not mapa:
        return out, 0
    codigos = out[col_cod].map(pexcel.normalizar_codigo)
    nuevos = codigos.map(mapa)
    mask = nuevos.notna()
    n = int(mask.sum())
    if n == 0:
        return out, 0
    # Forzar dtype numérico: si la columna venía mixta, el assign a veces no se ve.
    out[col_pron] = pd.to_numeric(out[col_pron], errors="coerce")
    out.loc[mask, col_pron] = nuevos.loc[mask].to_numpy(dtype=float)
    col_aj = _columna_por_nombre_canonico(out, pc.COL_PRONOSTICO_AJUSTADO)
    if col_aj is not None:
        out[col_aj] = pd.to_numeric(out[col_aj], errors="coerce")
        out.loc[mask, col_aj] = nuevos.loc[mask].to_numpy(dtype=float)
    out = out.rename(columns={col_pron: f"{col_pron} · LRI actualizado"})
    return out, n


def _vista_archivo(
    hojas: dict[str, pd.DataFrame],
    fuente: Fuente,
    calc: pd.DataFrame | None = None,
) -> None:
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
    n_sync = 0
    if es_datos and calc is not None:
        crudo, n_sync = _sincronizar_pronostico_en_vista(crudo, calc)
    tabla = _para_mostrar(crudo, es_datos)
    n_usadas = sum(1 for c in tabla.columns if es_datos and pc.es_columna_pronostico(c))
    resumen = f"**{fuente.nombre}** · {len(tabla):,} filas · {tabla.shape[1]:,} columnas"
    if es_datos:
        resumen += f" · {n_usadas} columnas de demanda / atributo"
        if n_sync:
            resumen += f" · «pronostico» = LRI ({n_sync:,} SKUs)"
    col_info.caption(resumen)

    # height fijo en px + DataFrame sin Styler: el scroll es interno al marco
    # (barra horizontal al pie, visible sin bajar miles de filas).
    token = int(st.session_state.get(_CLAVE_ARCHIVO_TOKEN, 0))
    with st.container(key=f"{_CLAVE_CONTENEDOR_TABLA}_{token}"):
        st.dataframe(
            tabla,
            width="stretch",
            height=_ALTURA_TABLA_ARCHIVO_PX,
            hide_index=True,
            key=f"pron_df_archivo_{token}_{n_sync}",
        )


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


def _tabla_archivo_pronostico(calc: pd.DataFrame, df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Hoja de entrega: código, descripción, cat/subcat/proveedor, nivel, inventario, variabilidad, pronóstico."""
    out = calc.copy()
    if df is not None:
        for col in ("inventario final bulto", "inventario promedio bultos"):
            if col in df.columns:
                out[col] = df.reindex(out.index)[col]
    columnas = [c for c in _COLUMNAS_ARCHIVO_PRONOSTICO if c in out.columns]
    tabla = out[columnas].sort_values(pc.COL_PRONOSTICO_LRI, ascending=False, na_position="last")
    return tabla.rename(columns=_ETIQUETAS_ARCHIVO_PRONOSTICO)


def _excel_archivo_pronostico(calc: pd.DataFrame, df: pd.DataFrame | None = None) -> bytes:
    """Bytes .xlsx del archivo de pronóstico (impresión / entrega)."""
    buffer = io.BytesIO()
    hoja = _tabla_archivo_pronostico(calc, df)
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        hoja.to_excel(writer, sheet_name="pronostico", index=False)
        # Hoja aparte solo certificados (los que tienen LRI).
        if pc.COL_PRONOSTICO_LRI in calc.columns:
            cert = hoja[hoja["Pronóstico LRI"].notna()] if "Pronóstico LRI" in hoja.columns else hoja
            cert.to_excel(writer, sheet_name="con pronostico LRI", index=False)
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
    _estilo_fondo_plotly(fig)
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
    _estilo_fondo_plotly(fig)
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


def _mostrar_pronostico_sku(pron: pd.DataFrame) -> None:
    """Tabla de pronóstico con altura fija: barra horizontal siempre en pantalla."""
    tabla = _tabla_pronostico_sku(pron)
    formato = {_ETIQUETAS.get(k, k): v for k, v in _FORMATO_TABLA.items() if _ETIQUETAS.get(k, k) in tabla.columns}
    estilo = tabla.style.format(formato, na_rep="—").set_properties(
        subset=[_ETIQUETAS[pc.COL_PRONOSTICO_LRI]], **_ESTILO_PRONOSTICO
    )
    with st.container(key=_CLAVE_CONTENEDOR_PRON):
        st.dataframe(
            estilo,
            width="stretch",
            height=_ALTURA_TABLA_PRONOSTICO_PX,
            hide_index=True,
            key="pron_df_pronostico_sku",
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
        height=520,
        title=dict(text=f"Pronóstico mensual por SKU · {titulo}", font=dict(size=13)),
        margin=dict(t=40, b=8, l=8, r=8),
        xaxis=dict(type="category", categoryorder="array", categoryarray=x, showticklabels=len(graf) <= 40, tickangle=-45),
        yaxis_title="Unidades / mes",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, traceorder="normal", font=dict(size=11)),
    )
    _barras_delgadas(fig, len(graf))
    _estilo_fondo_plotly(fig)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def _reporte_pedido(skus: pd.DataFrame, excluidos: pd.DataFrame) -> bytes:
    hojas = {"Pronóstico por SKU": _tabla_pronostico_sku(skus)}
    if not excluidos.empty:
        hojas["Excluidos (no certificados)"] = _hoja_certificacion(excluidos)
    return _escribir_hojas(hojas)


def _vista_pronostico(calc: pd.DataFrame) -> None:
    limite = pc.CV_MAX_CERTIFICADO
    pron = calc[np.isfinite(calc[pc.COL_PRONOSTICO_LRI].to_numpy(dtype=float))]
    excluidos = calc.drop(index=pron.index)

    with st.container(key="pron_vista_pron"):
        col_titulo, col_nivel, col_buscar = st.columns([1.4, 2.2, 1.6], vertical_alignment="bottom")
        col_titulo.markdown("#### Pronóstico mensual")
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
        buscar = col_buscar.text_input(
            "Buscar código",
            key="pron_buscar_codigo",
            placeholder="Código",
            label_visibility="collapsed",
            help="Filtra gráfico y tabla por código.",
        )
        nivel = st.session_state.get(_CLAVE_NIVEL_PRONOSTICO) or niveles[0]
        if pron.empty:
            st.warning("Ningún SKU certificado con los filtros actuales.")
            return

        if _NIVELES_CERTIFICACION[nivel] is None:
            skus, excl, titulo = pron, excluidos, "Todos los SKUs"
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
            col_sel.caption(titulo)

        if buscar.strip():
            q = pexcel.normalizar_codigo(buscar.strip()).lower()
            mask = skus["codigo"].map(lambda c: q in pexcel.normalizar_codigo(c).lower())
            skus = skus[mask]
            excl = excl[excl["codigo"].map(lambda c: q in pexcel.normalizar_codigo(c).lower())]
            if skus.empty and excl.empty:
                st.warning(f"Ningún SKU coincide con «{buscar.strip()}».")
                return

        promedio = float(skus["pronostico calc"].sum()) if not skus.empty else 0.0
        total = float(skus[pc.COL_PRONOSTICO_LRI].sum()) if not skus.empty else 0.0
        st.caption(
            f"**{titulo}** · {len(skus):,} SKUs · "
            f"excl. {len(excl):,} · "
            f"promedio {promedio:,.0f} · "
            f"pronóstico {total:,.0f}"
            + (f" (+{total - promedio:,.0f} K×σ)" if total > promedio else "")
        )
        if len(skus) == 1:
            fila = skus.iloc[0]
            fr = fila.get(pc.COL_FILL_RATE)
            fr_txt = f"{float(fr):.1%}" if fr is not None and np.isfinite(fr) else "—"
            st.caption(
                f"{fila['codigo']} · LRI **{fila[pc.COL_PRONOSTICO_LRI]:,.1f}** · "
                f"clase {fila.get('clase', '—')} · fill {fr_txt}"
            )

        if skus.empty:
            st.info("Sin SKUs certificados en este filtro.")
            return

        _grafico_pronostico_skus(skus, titulo)
        _mostrar_pronostico_sku(skus)

        if not excl.empty:
            with st.expander(f"⚠️ Excluidos ({len(excl):,}) · pendientes de política"):
                st.caption(f"CV > {limite:.0%}: sin pronóstico hasta definir política.")
                _tabla_certificacion(excl)

        if st.session_state.get(_CLAVE_MOSTRAR_REPORTES):
            st.download_button(
                f"📥 Artículos a pedir · {titulo} (Excel)",
                data=_reporte_pedido(skus, excl),
                file_name=f"{_nombre_archivo(f'pronostico {titulo}')}.xlsx",
                mime=_MIME_XLSX,
                help="SKUs con descripción, clase, fill rate, K, promedio, σ, CV, K × σ y pronóstico.",
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
    _estilo_fondo_plotly(fig)
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
    _estilo_fondo_plotly(fig)
    st.plotly_chart(fig, width="stretch")
    st.dataframe(indices.style.format("{:.2f}"), width="stretch")
    st.caption("Con un solo año de historia el índice es indicativo; se confirma con más años.")


def _vista_normal(df: pd.DataFrame, calc: pd.DataFrame, meses: list[str]) -> None:
    """Simulación Monte Carlo (@RISK): gráfico → probabilidad → bultos | delimitadores."""
    del meses  # ya no se muestra el histograma de meses reales
    st.subheader("Simulación Monte Carlo")
    col_sku, _ = st.columns([2, 3])
    with col_sku:
        etiquetas = {_etiqueta_sku(f): i for i, f in calc.iterrows()}
        elegido = st.selectbox("SKU", list(etiquetas), key="sku_normal", label_visibility="collapsed")
    idx = etiquetas[elegido]
    fila = calc.loc[idx]
    media, desv, nivel = fila["pronostico calc"], fila["desviacion calc"], fila["nivel servicio"]
    if not (np.isfinite(desv) and desv > 0):
        st.warning("El SKU no tiene variabilidad suficiente para una distribución normal.")
        return
    corte = float(fila["pronostico ajustado calc"])

    clave_val = "pron_demanda_consulta_bultos"
    clave_izq = "pron_delimitador_izq"
    clave_sku = "pron_demanda_consulta_sku"
    if st.session_state.get(clave_sku) != elegido or clave_val not in st.session_state:
        st.session_state[clave_val] = float(round(corte))
        st.session_state[clave_izq] = 0.0
        st.session_state[clave_sku] = elegido

    def _aplicar_bultos(valor: float) -> None:
        st.session_state[clave_val] = max(0.0, float(valor))

    def _desde_slider_bultos() -> None:
        _aplicar_bultos(st.session_state["pron_sl_demanda_bultos"])

    def _desde_slider_prob() -> None:
        _aplicar_bultos(
            bultos_desde_probabilidad(media, desv, float(st.session_state["pron_sl_prob_objetivo"]))
        )

    def _desde_rango() -> None:
        lo, hi = st.session_state["pron_sl_rango_delimitadores"]
        st.session_state[clave_izq] = float(min(lo, hi))
        _aplicar_bultos(float(max(lo, hi)))

    tope_slider = float(max(media + 5.0 * desv, float(st.session_state[clave_val]), corte, 300.0))
    consulta = float(st.session_state[clave_val])
    p_sync = probabilidad_desde_bultos(media, desv, consulta)
    if not np.isfinite(p_sync):
        p_sync = float(nivel) if np.isfinite(nivel) else 0.8
    p_sync = float(min(max(p_sync, 0.001), 0.999))

    st.session_state["pron_sl_demanda_bultos"] = float(min(max(0.0, consulta), tope_slider))
    st.session_state["pron_sl_prob_objetivo"] = p_sync

    eje = rango_eje_x_demanda(media, desv, consulta)
    x_min_eje = min(float(eje[0]), 0.0)
    x_max_eje = max(float(eje[-1]), consulta, media + 4 * desv)
    st.session_state.setdefault(clave_izq, 0.0)
    x_izq = float(st.session_state[clave_izq])
    if x_izq > consulta:
        x_izq = max(0.0, min(x_izq, consulta))
        st.session_state[clave_izq] = x_izq
    st.session_state["pron_sl_rango_delimitadores"] = (
        float(min(max(x_min_eje, x_izq), x_max_eje)),
        float(min(max(x_min_eje, consulta), x_max_eje)),
    )

    p_izq, p_centro, p_der, x_lo, x_hi = zonas_probabilidad_delimitadores(
        media, desv, x_izq, consulta
    )

    st.markdown(
        f"""
        <div style="display:flex;width:100%;max-width:720px;border-radius:5px;overflow:hidden;
        font-weight:600;font-size:0.8rem;text-align:center;margin:0.15rem 0 0.4rem 0;">
          <div style="flex:{max(p_izq, 0.001):.4f};background:#FED7AA;color:#9A3412;padding:0.28rem 0.2rem;">
            {p_izq:.1%}
          </div>
          <div style="flex:{max(p_centro, 0.001):.4f};background:#EA580C;color:#fff;padding:0.28rem 0.2rem;">
            {p_centro:.1%}
          </div>
          <div style="flex:{max(p_der, 0.001):.4f};background:#FED7AA;color:#9A3412;padding:0.28rem 0.2rem;">
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
    fig.add_vline(x=x_lo, line=dict(color="#1E293B", width=2), annotation_text=f"{x_lo:,.0f}")
    fig.add_vline(x=x_hi, line=dict(color="#EA580C", width=2), annotation_text=f"{x_hi:,.0f}")
    fig.update_layout(
        xaxis_title="Demanda mensual (bultos)",
        yaxis_title="Densidad",
        margin=dict(t=28, b=36),
        showlegend=False,
        bargap=0.05,
        xaxis_range=[x_min_eje, x_max_eje],
        height=380,
    )
    _estilo_fondo_plotly(fig)
    st.plotly_chart(fig, width="stretch")

    st.caption(
        f"Cola izq. {p_izq:.1%} · Centro {p_centro:.1%} · Cola der. {p_der:.1%} · "
        f"ref. ajustado {corte:,.1f} · nivel Excel {nivel:.0%}"
    )

    with st.container(key="pron_risk_controles"):
        # 1) Probabilidad a todo el ancho, justo debajo del gráfico
        st.slider(
            "Probabilidad P(demanda ≤ x)",
            min_value=0.001,
            max_value=0.999,
            step=0.001,
            format="%.3f",
            key="pron_sl_prob_objetivo",
            on_change=_desde_slider_prob,
        )
        # 2) Bultos y delimitadores al mismo nivel
        col_bultos, col_delim = st.columns(2)
        with col_bultos:
            st.slider(
                "Bultos",
                min_value=0.0,
                max_value=tope_slider,
                step=1.0,
                key="pron_sl_demanda_bultos",
                on_change=_desde_slider_bultos,
            )
        with col_delim:
            st.slider(
                "Delimitadores",
                min_value=float(x_min_eje),
                max_value=float(x_max_eje),
                step=1.0,
                key="pron_sl_rango_delimitadores",
                on_change=_desde_rango,
            )


def main() -> None:
    st.markdown(
        '<div class="lri-fc-header">'
        "<h4>📈 LRI Forecast Pro "
        '<span class="lri-fc-sub">'
        "· Módulo 1 · Pronóstico de demanda sobre el archivo compartido de LRI</span></h4>"
        "</div>",
        unsafe_allow_html=True,
    )

    fuente = _seccion_archivo()
    # Si acabamos de escribir el Excel, releer con el mtime nuevo (no el de la fuente previa).
    mtime_lectura = fuente.mtime
    if fuente.ruta and os.path.isfile(fuente.ruta):
        mtime_lectura = os.path.getmtime(fuente.ruta)
    hojas, err_hojas = _cargar_hojas(fuente.contenido, mtime_lectura)
    df, err = _cargar_demanda(fuente.contenido, mtime_lectura)
    if err or df is None:
        st.error(err or err_hojas or "No se pudieron cargar los datos.")
        st.stop()

    resultado = _seccion_calculo(df, fuente)

    # Tras calcular/escribir: releer el Excel para que «Mostrar archivo» no use una copia vieja.
    if (
        fuente.ruta
        and os.path.isfile(fuente.ruta)
        and st.session_state.get(_CLAVE_ESCRITURA_PRONOSTICO) is not None
    ):
        mtime_lectura = os.path.getmtime(fuente.ruta)
        _cargar_hojas.clear()
        hojas, err_hojas = _cargar_hojas(None, mtime_lectura)

    vista = st.session_state.get(_CLAVE_VISTA, VISTA_PRONOSTICO)
    if vista in _VISTAS_LEGACY:
        vista = _VISTAS_LEGACY[vista]
        st.session_state[_CLAVE_VISTA] = vista

    # Una sola vista a la vez: archivo XOR pronóstico/alternativa.
    if st.session_state.get(_CLAVE_MOSTRAR_ARCHIVO):
        if hojas:
            calc_vista = resultado["calc"] if resultado is not None else None
            _vista_archivo(hojas, fuente, calc=calc_vista)
        else:
            st.error(err_hojas or "No se pudo leer el archivo completo.")
        return

    if resultado is None:
        st.info(
            "Pulse **📈 Cálculo del pronóstico** para ver el resultado, "
            "**📁 Abrir archivo** para ver solo el Excel, "
            "o una alternativa de cálculo en el panel lateral."
        )
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
    elif vista == "Simulación Monte Carlo":
        _vista_normal(df_f, calc, meses)
    elif vista == "Serie por SKU":
        _vista_serie(df_f, calc, meses)
    elif vista == "Estacionalidad":
        _vista_estacionalidad(df_f)


main()
