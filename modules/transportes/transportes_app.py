"""LRI Transportes PRO — app Streamlit del módulo de transportes.

Sidebar al estilo Inventory Pro: una acción a la vez.
Acciones: Perfilado, Mapas (distrito / cantón / otros), Cluster (distrito o
cantón) y Rutas (distrito o cantón).

Ejecutar:
    streamlit run modules/transportes/transportes_app.py
"""
from __future__ import annotations

import os
import sys
import importlib
import math

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

_DIR_ACTUAL = os.path.dirname(os.path.abspath(__file__))
_RAIZ_PROYECTO = os.path.abspath(os.path.join(_DIR_ACTUAL, "..", ".."))
for _p in (_DIR_ACTUAL, _RAIZ_PROYECTO):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.auth import exigir_clave_web  # noqa: E402

import transportes_datos as datos  # noqa: E402

datos = importlib.reload(datos)

st.set_page_config(page_title="LRI Transportes PRO", page_icon="🚚", layout="wide")
exigir_clave_web(titulo="LRI Transportes PRO")

TITULO = "LRI Transportes PRO"

# Acciones del sidebar (mismo patrón que Decisiones en Inventory Pro).
ACCIONES: tuple[tuple[str, str, str], ...] = (
    (
        "base",
        "Base de datos",
        "Tabla completa de la hoja de clientes y rutas.",
    ),
    ("perfilado", "Perfilado", "Gráficos del perfil y mapa de los clientes de ese cruce."),
    (
        "mapas",
        "Mapas",
        "Se mantiene para el mapa de rutas.",
    ),
    (
        "cluster",
        "Cluster",
        "Agrupación de clientes cercanos, de 15 a 25 por segmento.",
    ),
    (
        "rutas",
        "Rutas",
        "Rutas existentes por distrito o cantón.",
    ),
)

CORTES: dict[str, tuple[str, ...]] = {
    "mapas": ("Distrito", "Cantón", "Otros"),
    "cluster": ("Distrito", "Cantón"),
    "rutas": ("Distrito", "Cantón"),
}

_PLOTLY_PAPER = "#051426"
_PLOTLY_TEXTO = "#FFFFFF"


def _cargar_tema() -> None:
    """Inyecta el tema azul. Solo apariencia."""
    ruta_css = os.path.join(_DIR_ACTUAL, "transportes_theme.css")
    try:
        with open(ruta_css, encoding="utf-8") as f:
            css = f.read()
    except OSError:
        return
    st.markdown(f"<style>\n{css}\n</style>", unsafe_allow_html=True)


def _logo_b64() -> str | None:
    import base64

    for ruta in (
        os.path.join(_RAIZ_PROYECTO, "assets", "LRI_logo.png"),
        os.path.join(_RAIZ_PROYECTO, "modules", "inventarios", "assets", "LRI_logo.png"),
    ):
        if os.path.isfile(ruta):
            with open(ruta, "rb") as f:
                return base64.b64encode(f.read()).decode("ascii")
    return None


def _render_marca_sidebar() -> None:
    logo = _logo_b64()
    if logo:
        st.markdown(
            '<div style="padding-top:8px;line-height:0;">'
            f'<img src="data:image/png;base64,{logo}" alt="LRI" '
            'style="height:96px;width:auto;max-width:100%;object-fit:contain;" />'
            "</div>",
            unsafe_allow_html=True,
        )
    st.markdown(
        '<p class="lri-tr-sidebar-titulo">LRI Transportes <span class="lri-app-pro">PRO</span></p>',
        unsafe_allow_html=True,
    )


def _cabecera(subtitulo: str) -> None:
    st.markdown(
        f"""<div class="lri-tr-titulo-main">
  <span class="lri-app-title">LRI Transportes <span class="lri-app-pro">PRO</span></span>
  <div class="lri-app-sub">{subtitulo}</div>
</div>""",
        unsafe_allow_html=True,
    )


def _inicializar_menu() -> None:
    st.session_state.setdefault("tr_accion", "perfilado")
    for accion, cortes in CORTES.items():
        st.session_state.setdefault(f"tr_corte_{accion}", cortes[0])
    st.session_state.setdefault("tr_otro", datos.COL_PROVINCIA)


def _render_menu() -> None:
    accion = st.session_state["tr_accion"]
    st.markdown("##### Acciones")
    for clave, etiqueta, ayuda in ACCIONES:
        if st.button(
            etiqueta,
            key=f"tr_nav_{clave}",
            width="stretch",
            type="primary" if accion == clave else "secondary",
            help=ayuda,
        ):
            st.session_state["tr_accion"] = clave
            st.rerun()

    cortes = CORTES.get(accion)
    if not cortes:
        return

    st.markdown("##### Corte")
    actual = st.session_state.get(f"tr_corte_{accion}", cortes[0])
    if actual not in cortes:
        actual = cortes[0]
        st.session_state[f"tr_corte_{accion}"] = actual
    for corte in cortes:
        if st.button(
            corte,
            key=f"tr_corte_{accion}_{corte}",
            width="stretch",
            type="primary" if actual == corte else "secondary",
            help=f"{etiqueta_accion(accion)} por {corte.lower()}.",
        ):
            st.session_state[f"tr_corte_{accion}"] = corte
            st.rerun()


def etiqueta_accion(clave: str) -> str:
    for c, etiqueta, _ayuda in ACCIONES:
        if c == clave:
            return etiqueta
    return clave


def _leer_datos() -> pd.DataFrame | None:
    archivo = st.session_state.get("tr_archivo_subido")
    if archivo is not None:
        try:
            df = datos.preparar(pd.read_excel(archivo, sheet_name=datos.HOJA_CLIENTES))
        except Exception as exc:
            st.session_state["tr_error_carga"] = (
                f"No se pudo leer la hoja «{datos.HOJA_CLIENTES}»: {exc}"
            )
            return None
        st.session_state["tr_error_carga"] = None
        return df

    if not datos.existe_archivo():
        st.session_state["tr_error_carga"] = (
            f"No está el archivo `{datos.NOMBRE_ARCHIVO}` en `modules/transportes/data/`."
        )
        return None
    try:
        df = datos.cargar_clientes()
    except Exception as exc:
        st.session_state["tr_error_carga"] = str(exc)
        return None
    st.session_state["tr_error_carga"] = None
    return df


def _sidebar_datos() -> None:
    with st.expander("Cargar datos", expanded=False):
        subido = st.file_uploader(
            "Excel de transportes",
            type=["xlsx"],
            key="tr_uploader",
            help=f"Debe incluir la hoja «{datos.HOJA_CLIENTES}».",
        )
        st.session_state["tr_archivo_subido"] = subido
        st.caption(f"Por defecto: `{datos.NOMBRE_ARCHIVO}`")


def _valores(df: pd.DataFrame, columna: str) -> list[str]:
    if columna not in df.columns:
        return []
    serie = df[columna].dropna().astype(str).str.strip()
    serie = serie[serie != ""]
    return sorted(serie.unique().tolist())


def _filtro_grupo(df: pd.DataFrame, columna: str, etiqueta: str) -> pd.DataFrame:
    opciones = ["Todos"] + _valores(df, columna)
    if len(opciones) == 1:
        st.warning(f"La base no trae la columna «{columna}».")
        return df.iloc[0:0]
    elegido = st.selectbox(etiqueta, opciones, key=f"tr_grupo_{columna}")
    if elegido == "Todos":
        return df
    return df[df[columna].astype(str).str.strip() == elegido]


def _columnas_clientes(df: pd.DataFrame) -> list[str]:
    return [
        c
        for c in (
            datos.COL_CLIENTE,
            datos.COL_NOMBRE,
            datos.COL_PROVINCIA,
            datos.COL_CANTON,
            datos.COL_DISTRITO,
            datos.COL_NOMBRE_RUTA,
            datos.COL_RUTA,
            datos.COL_KM,
        )
        if c in df.columns
    ]


def _distritos_del_clic(evento: object, puntos: pd.DataFrame) -> list[str]:
    """Distrito de cada punto pulsado en el mapa (customdata[0] = distrito)."""
    seleccion = getattr(evento, "selection", None)
    if seleccion is None:
        return []
    elegidos = seleccion.get("points") if hasattr(seleccion, "get") else None
    if not elegidos:
        return []
    vistos: list[str] = []
    for punto in elegidos:
        distrito = ""
        custom = punto.get("customdata") if isinstance(punto, dict) else None
        if isinstance(custom, (list, tuple)) and custom:
            distrito = str(custom[0]).strip()
        if not distrito and datos.COL_LATITUD in puntos.columns:
            lat = punto.get("lat") if isinstance(punto, dict) else None
            lon = punto.get("lon") if isinstance(punto, dict) else None
            if lat is not None and lon is not None:
                delta = (puntos[datos.COL_LATITUD] - float(lat)).abs() + (
                    puntos[datos.COL_LONGITUD] - float(lon)
                ).abs()
                distrito = str(puntos.loc[delta.idxmin(), datos.COL_DISTRITO]).strip()
        if distrito and distrito not in vistos:
            vistos.append(distrito)
    return vistos


def _render_clientes_distrito(df: pd.DataFrame, distritos: list[str]) -> None:
    """Lista, sobre fondo azul, los clientes del distrito pulsado en el mapa."""
    if datos.COL_DISTRITO not in df.columns:
        st.error("La base no trae la columna Distrito.")
        return
    if not distritos:
        with st.container(border=True):
            st.caption(
                "Haga clic en un cliente del mapa para ver los clientes de su distrito."
            )
        return
    columnas = _columnas_clientes(df)
    distrito_txt = df[datos.COL_DISTRITO].astype(str).str.strip()
    for distrito in distritos:
        grupo = df[distrito_txt == distrito]
        with st.container(border=True):
            st.markdown(f"##### Distrito {distrito}")
            st.caption(f"{len(grupo):,} clientes en la base de datos")
            if grupo.empty:
                st.info("Ese distrito no tiene clientes en la base.")
            else:
                st.dataframe(
                    grupo[columnas] if columnas else grupo,
                    width="stretch",
                    height=min(420, 56 + 32 * len(grupo)),
                )


def _formato_variable(variable: str) -> str:
    if variable in (datos.VARIABLE_CLIENTES, "Unidades vendidas"):
        return ",.0f"
    if variable == "% Distribución":
        return ".1%"
    return ",.1f"


def _rango_eje(valores: pd.Series) -> list[float]:
    """Eje Y con aire arriba y, si hay negativos (TVA), también debajo de cero."""
    nums = pd.to_numeric(valores, errors="coerce").dropna()
    if nums.empty:
        return [0, 1]
    ymax = float(nums.max())
    ymin = float(nums.min())
    arriba = ymax * 1.22 if ymax > 0 else 0.0
    abajo = ymin * 1.22 if ymin < 0 else 0.0
    if arriba == 0 and abajo == 0:
        return [0, 1]
    if abajo < 0 and arriba == 0:
        arriba = abs(abajo) * 0.08
    return [abajo, arriba]


def _texto_barra(valor: float, variable: str) -> str:
    if pd.isna(valor):
        return ""
    if variable == "% Distribución":
        return f"{valor:.1%}"
    if variable in (datos.VARIABLE_CLIENTES, "Unidades vendidas"):
        return f"{valor:,.0f}"
    return f"{valor:,.1f}"


_COLORES_VARIABLES = ("#008DFF", "#00B7FF", "#779d40")
_SIN_VARIABLE = "Ninguna"


def _grafico_barras_perfil(
    resumen: pd.DataFrame,
    nombre_x: str,
    variables: list[str],
) -> None:
    """Barras de mayor a menor, ocupando el eje X, con la cantidad arriba de cada una."""
    resumen = resumen.sort_values(variables[0], ascending=False, kind="mergesort")
    categorias = resumen[nombre_x].astype(str).tolist()
    n = len(resumen)
    n_var = len(variables)
    if n_var == 1:
        variable = variables[0]
        textos = [_texto_barra(v, variable) for v in resumen[variable]]
        fig = px.bar(resumen, x=nombre_x, y=variable, text=textos)
        fig.update_traces(
            marker_color="#008DFF",
            marker_line_width=0,
            textposition="outside",
            textfont=dict(color="#FFFFFF", size=13 if n <= 12 else 9),
            cliponaxis=False,
        )
        fig.update_yaxes(
            title=variable,
            tickformat=_formato_variable(variable),
            range=_rango_eje(resumen[variable]),
        )
    else:
        largo = resumen.melt(
            id_vars=nombre_x,
            value_vars=variables,
            var_name="Variable",
            value_name="Valor",
        )
        largo["Texto"] = [
            _texto_barra(valor, variable)
            for valor, variable in zip(largo["Valor"], largo["Variable"])
        ]
        fig = px.bar(
            largo,
            x=nombre_x,
            y="Valor",
            color="Variable",
            barmode="group",
            text="Texto",
            category_orders={nombre_x: categorias, "Variable": variables},
            color_discrete_sequence=list(_COLORES_VARIABLES[:n_var]),
        )
        fig.update_traces(
            textposition="outside",
            textfont=dict(color="#FFFFFF", size=11 if n <= 12 else 8),
            cliponaxis=False,
        )
        fig.update_layout(
            barmode="group",
            bargroupgap=0.02,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                font=dict(color="#FFFFFF"),
            ),
        )
        fig.update_yaxes(
            title=" · ".join(variables),
            range=_rango_eje(largo["Valor"]),
        )

    fig.update_layout(
        paper_bgcolor=_PLOTLY_PAPER,
        plot_bgcolor=_PLOTLY_PAPER,
        font=dict(color=_PLOTLY_TEXTO),
        bargap=0.08,
        margin=dict(l=56, r=12, t=48, b=120),
    )
    fig.update_xaxes(
        title=nombre_x,
        type="category",
        categoryorder="array",
        categoryarray=categorias,
        tickangle=-60 if n > 8 else 0,
        tickfont=dict(color="#C5D8E8"),
        title_font=dict(color="#C5D8E8"),
        gridcolor="rgba(8, 118, 185, 0.22)",
        automargin=True,
    )
    fig.update_yaxes(
        tickfont=dict(color="#C5D8E8"),
        title_font=dict(color="#C5D8E8"),
        gridcolor="rgba(8, 118, 185, 0.22)",
    )
    fig.update_layout(height=560, bargap=0.04 if n > 16 else 0.08)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    st.caption(
        f"{n} grupos de {nombre_x} en una sola vista, de mayor a menor. "
        "Un TVA negativo baja de cero."
    )


def _elegir_nombre(
    df: pd.DataFrame,
    etiqueta: str,
    filtros: dict[str, str],
    clave: str,
    rotulo: str,
) -> str:
    opciones = ["Todos"] + datos.valores_atributo(df, etiqueta, filtros or None)
    if st.session_state.get(clave) not in opciones:
        st.session_state[clave] = "Todos"
    return st.selectbox(rotulo, opciones, key=clave)


def _atributos_de_hoja(hoja: str, acotar: dict[str, str], nivel: str) -> list[str]:
    """El gráfico muestra el peldaño actual. Si el padre ya está elegido, la barra lleva solo ese nombre."""
    if hoja == "Nombre del cliente":
        return ["Nombre del cliente"]
    if hoja == "Cantón":
        return ["Cantón"] if "Provincia" in acotar else ["Provincia", "Cantón"]
    if "Cantón" in acotar or nivel == "Distrito":
        return ["Distrito"]
    if "Provincia" in acotar or nivel == "Cantón":
        return ["Cantón", "Distrito"]
    return ["Provincia", "Cantón", "Distrito"]


def _relato_cascada(hoja: str, acotar: dict[str, str]) -> str:
    titulo = {"Cantón": "Cantones", "Distrito": "Distritos"}.get(hoja, "Clientes")
    if not acotar:
        return f"{titulo} de todo el perfil"
    return f"{titulo} de " + " · ".join(acotar.values())


def _elegir_opcional(clave: str, opciones: list[str], vacio: str) -> None:
    if st.session_state.get(clave) not in opciones:
        st.session_state[clave] = vacio


def _render_perfilado(df: pd.DataFrame) -> None:
    _cabecera("Perfilado")
    opciones_x = datos.etiquetas_atributos(df)
    opciones_y = datos.etiquetas_variables(df)
    if not opciones_x or not opciones_y:
        st.error("La base no trae atributos o variables para el perfilado.")
        return

    if st.session_state.get("tr_perfil_y") not in opciones_y:
        st.session_state["tr_perfil_y"] = datos.VARIABLE_CLIENTES
    if st.session_state.get("tr_perfil_op") not in datos.OPS_CALCULO:
        st.session_state["tr_perfil_op"] = "Suma"
    _elegir_opcional("tr_perfil_y2", [_SIN_VARIABLE, *opciones_y], _SIN_VARIABLE)
    _elegir_opcional("tr_perfil_y3", [_SIN_VARIABLE, *opciones_y], _SIN_VARIABLE)

    niveles = [n for n in ("Provincia", "Cantón", "Distrito") if n in opciones_x]
    if not niveles:
        st.error("La base no trae provincia, cantón o distrito.")
        return
    if st.session_state.get("tr_perfil_nivel") not in niveles:
        st.session_state["tr_perfil_nivel"] = "Provincia" if "Provincia" in niveles else niveles[0]

    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            nivel = st.selectbox("Empezar por", niveles, key="tr_perfil_nivel")
        rotulos = {
            "Provincia": "Nombre de la provincia",
            "Cantón": "Nombre del cantón",
            "Distrito": "Nombre del distrito",
        }
        with c2:
            nombre = _elegir_nombre(df, nivel, {}, "tr_perfil_nombre", rotulos[nivel])
        acotar: dict[str, str] = {}
        if nombre != "Todos":
            acotar[nivel] = nombre
        ver = "Distrito"
        if nivel == "Provincia":
            with c3:
                ver = st.selectbox(
                    "Mostrar",
                    ["Cantón", "Distrito"],
                    key="tr_perfil_ver",
                    help="Dentro de la provincia: sus cantones o sus distritos.",
                )
        else:
            with c3:
                st.caption(
                    "El siguiente paso es el distrito."
                    if nivel == "Cantón"
                    else "Dentro del distrito se ve el nombre del cliente."
                )

        if nivel == "Provincia":
            d1, d2 = st.columns(2)
            with d1:
                nombre_canton = _elegir_nombre(
                    df, "Cantón", acotar, "tr_perfil_nom_canton", "Nombre del cantón"
                )
            if nombre_canton != "Todos":
                acotar["Cantón"] = nombre_canton
            pedir_distrito = ver == "Distrito" or nombre_canton != "Todos"
            if pedir_distrito:
                with d2:
                    nombre_distrito = _elegir_nombre(
                        df, "Distrito", acotar, "tr_perfil_nom_distrito", "Nombre del distrito"
                    )
                if nombre_distrito != "Todos":
                    acotar["Distrito"] = nombre_distrito
        elif nivel == "Cantón":
            nombre_distrito = _elegir_nombre(
                df, "Distrito", acotar, "tr_perfil_nom_distrito", "Nombre del distrito"
            )
            if nombre_distrito != "Todos":
                acotar["Distrito"] = nombre_distrito

        if "Distrito" in acotar or nivel == "Distrito":
            hoja = "Nombre del cliente"
        elif nivel == "Cantón" or ver == "Distrito" or "Cantón" in acotar:
            hoja = "Distrito"
        else:
            hoja = "Cantón"
        atributos = _atributos_de_hoja(hoja, acotar, nivel)
        atributos_mapa = ["Distrito"] if hoja == "Nombre del cliente" else atributos
        st.caption(_relato_cascada(hoja, acotar))

        v1, v2, v3, v4 = st.columns(4)
        with v1:
            variable = st.selectbox("Variable 1", opciones_y, key="tr_perfil_y")
        if st.session_state.get("tr_perfil_y2") == variable:
            st.session_state["tr_perfil_y2"] = _SIN_VARIABLE
        with v2:
            variable_2 = st.selectbox(
                "Variable 2",
                [_SIN_VARIABLE, *[v for v in opciones_y if v != variable]],
                key="tr_perfil_y2",
            )
        if st.session_state.get("tr_perfil_y3") in (variable, st.session_state.get("tr_perfil_y2")):
            st.session_state["tr_perfil_y3"] = _SIN_VARIABLE
        with v3:
            ya = {variable, variable_2}
            variable_3 = st.selectbox(
                "Variable 3",
                [_SIN_VARIABLE, *[v for v in opciones_y if v not in ya]],
                key="tr_perfil_y3",
            )
        variables = [
            v
            for v in (variable, variable_2, variable_3)
            if v not in (_SIN_VARIABLE, None)
        ]
        with v4:
            if any(v != datos.VARIABLE_CLIENTES for v in variables):
                operacion = st.radio(
                    "Cálculo",
                    datos.OPS_CALCULO,
                    horizontal=True,
                    key="tr_perfil_op",
                    help="Clientes siempre cuenta códigos. El cálculo aplica a las demás variables.",
                )
            else:
                operacion = "Suma"
                st.caption("Clientes cuenta códigos.")

        resumen = datos.agregar_perfil(
            df,
            atributos,
            variables,
            operacion,
            acotar=acotar,
        )
        if resumen.empty:
            st.info("No hay datos para ese cruce.")
        else:
            _grafico_barras_perfil(resumen, " · ".join(atributos), variables)

    _mapa_perfil(df, atributos_mapa, acotar)


_COLORES_ZONA = (
    "#008DFF",
    "#22c55e",
    "#f59e0b",
    "#ef4444",
    "#a855f7",
    "#00B7FF",
    "#84cc16",
    "#fb7185",
    "#14b8a6",
    "#eab308",
    "#6366f1",
    "#f97316",
    "#2dd4bf",
    "#e879f9",
    "#38bdf8",
    "#779d40",
)

# Tonalidades separadas a propósito: negro con rojo, morado, azul oscuro, celeste.
# No van juntos un rojo y un rosado.
_COLORES_PUNTOS = (
    "#111111",
    "#E10600",
    "#5B21B6",
    "#0B3A82",
    "#38BDF8",
    "#F5C400",
    "#0E7C3A",
    "#FF6A00",
    "#7C2D12",
    "#064E3B",
    "#BE185D",
    "#1D4ED8",
)

# Un color distinto por clúster marcado: negro, rojo, verde, azul oscuro, y siguen
# tonalidades que no se parecen entre sí.
_COLORES_CLUSTER = (
    "#111111",
    "#E10600",
    "#0E7C3A",
    "#0B3A82",
    "#5B21B6",
    "#FF6A00",
    "#F5C400",
    "#38BDF8",
    "#7C2D12",
    "#BE185D",
    "#064E3B",
    "#1D4ED8",
)


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _colores_separados(puntos: pd.DataFrame, zonas: list[str]) -> dict[str, str]:
    """Asigna un color lejano al de las zonas vecinas en el mapa."""
    centro: dict[str, tuple[float, float]] = {}
    for zona in zonas:
        grupo = puntos[puntos["Zona"].astype(str) == zona]
        centro[zona] = (
            float(grupo[datos.COL_LATITUD].mean()),
            float(grupo[datos.COL_LONGITUD].mean()),
        )
    orden = sorted(zonas, key=lambda zona: (round(centro[zona][0], 2), centro[zona][1]))
    asignado: dict[str, str] = {}
    for zona in orden:
        lat, lon = centro[zona]
        vecinos = sorted(
            asignado,
            key=lambda otra: (centro[otra][0] - lat) ** 2 + (centro[otra][1] - lon) ** 2,
        )[:4]
        usados = [_rgb(asignado[otra]) for otra in vecinos]
        libres = [color for color in _COLORES_PUNTOS if color not in asignado.values()]
        candidatos = libres or list(_COLORES_PUNTOS)

        def lejos(color: str) -> float:
            if not usados:
                return 0.0
            r, g, b = _rgb(color)
            return min((r - ur) ** 2 + (g - ug) ** 2 + (b - ub) ** 2 for ur, ug, ub in usados)

        asignado[zona] = max(candidatos, key=lejos)
    return asignado


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _circulo(lat: float, lon: float, radio: float = 0.008, pasos: int = 18) -> list[tuple[float, float]]:
    coseno = max(0.25, math.cos(math.radians(lat)))
    anillo = []
    for i in range(pasos + 1):
        angulo = 2 * math.pi * i / pasos
        anillo.append((lat + radio * math.sin(angulo), lon + (radio * math.cos(angulo) / coseno)))
    return anillo


def _casco_convexo(puntos: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Anillo cerrado. Un punto o dos se dibujan como un borde alrededor."""
    unicos = sorted({(round(lat, 5), round(lon, 5)) for lat, lon in puntos})
    if not unicos:
        return []
    if len(unicos) == 1:
        return _circulo(unicos[0][0], unicos[0][1])
    if len(unicos) == 2:
        muestras = _circulo(unicos[0][0], unicos[0][1], 0.004) + _circulo(
            unicos[1][0], unicos[1][1], 0.004
        )
        unicos = sorted({(round(lat, 5), round(lon, 5)) for lat, lon in muestras})

    def cruz(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    inferior: list[tuple[float, float]] = []
    for p in unicos:
        while len(inferior) >= 2 and cruz(inferior[-2], inferior[-1], p) <= 0:
            inferior.pop()
        inferior.append(p)
    superior: list[tuple[float, float]] = []
    for p in reversed(unicos):
        while len(superior) >= 2 and cruz(superior[-2], superior[-1], p) <= 0:
            superior.pop()
        superior.append(p)
    anillo = inferior[:-1] + superior[:-1]
    if anillo[0] != anillo[-1]:
        anillo.append(anillo[0])
    return _engrosar(anillo)


def _engrosar(anillo: list[tuple[float, float]], minimo: float = 0.004) -> list[tuple[float, float]]:
    """Separa un poco el borde del centro para que un distrito estrecho se vea."""
    cuerpo = anillo[:-1] if anillo and anillo[0] == anillo[-1] else anillo
    if len(cuerpo) < 3:
        return anillo
    lat_c = sum(p[0] for p in cuerpo) / len(cuerpo)
    lon_c = sum(p[1] for p in cuerpo) / len(cuerpo)
    nuevo: list[tuple[float, float]] = []
    for lat, lon in cuerpo:
        dlat, dlon = lat - lat_c, lon - lon_c
        dist = math.hypot(dlat, dlon) or 1e-9
        extra = max(dist * 0.08, minimo)
        nuevo.append((lat_c + dlat / dist * (dist + extra), lon_c + dlon / dist * (dist + extra)))
    nuevo.append(nuevo[0])
    return nuevo


def _mapa_perfil(
    df: pd.DataFrame,
    atributos: list[str],
    acotar: str | dict[str, str] | None,
) -> None:
    """Mapa de los clientes del cruce, con un borde de color por zona."""
    st.markdown("##### Mapa del perfil")
    if datos.COL_LATITUD not in df.columns or datos.COL_LONGITUD not in df.columns:
        st.error("La base no trae Latitud y Longitud.")
        return
    vista = datos.recorte_perfil(df, atributos, acotar)
    puntos = vista.dropna(subset=[datos.COL_LATITUD, datos.COL_LONGITUD])
    if puntos.empty or "Zona" not in puntos.columns:
        st.info("No hay clientes con coordenada para este perfil.")
        return

    zonas = sorted(puntos["Zona"].astype(str).unique().tolist())
    modo = st.radio(
        "Ver el mapa",
        ["Zonas de color", "Puntos de color"],
        horizontal=True,
        key="tr_mapa_estilo",
        help="Zonas de color es el mapa actual. Puntos de color deja solo el punto, con tonalidades bien separadas.",
    )
    fig = go.Figure()
    if modo == "Puntos de color":
        color_de = _colores_separados(puntos, zonas)
        for zona in zonas:
            grupo = puntos[puntos["Zona"].astype(str) == zona]
            color = color_de[zona]
            fig.add_trace(
                go.Scattermap(
                    lat=grupo[datos.COL_LATITUD],
                    lon=grupo[datos.COL_LONGITUD],
                    mode="markers",
                    marker=dict(size=12, color=color),
                    name=zona,
                    text=grupo[datos.COL_NOMBRE] if datos.COL_NOMBRE in grupo.columns else zona,
                    hovertemplate="%{text}<br>" + zona + "<extra></extra>",
                )
            )
    else:
        color_de = {zona: _COLORES_ZONA[i % len(_COLORES_ZONA)] for i, zona in enumerate(zonas)}
        for zona in zonas:
            grupo = puntos[puntos["Zona"].astype(str) == zona]
            anillo = _casco_convexo(
                list(zip(grupo[datos.COL_LATITUD], grupo[datos.COL_LONGITUD], strict=False))
            )
            if len(anillo) < 3:
                continue
            color = color_de[zona]
            fig.add_trace(
                go.Scattermap(
                    lat=[p[0] for p in anillo],
                    lon=[p[1] for p in anillo],
                    mode="lines",
                    fill="toself",
                    fillcolor=_rgba(color, 0.28),
                    line=dict(color=color, width=2),
                    name=zona,
                    hoverinfo="name",
                    legendgroup=zona,
                )
            )
            fig.add_trace(
                go.Scattermap(
                    lat=grupo[datos.COL_LATITUD],
                    lon=grupo[datos.COL_LONGITUD],
                    mode="markers",
                    marker=dict(size=8, color=color),
                    name=zona,
                    text=grupo[datos.COL_NOMBRE] if datos.COL_NOMBRE in grupo.columns else zona,
                    hovertemplate="%{text}<br>" + zona + "<extra></extra>",
                    legendgroup=zona,
                    showlegend=False,
                )
            )

    span = max(
        float(puntos[datos.COL_LATITUD].max() - puntos[datos.COL_LATITUD].min()),
        float(puntos[datos.COL_LONGITUD].max() - puntos[datos.COL_LONGITUD].min()),
    )
    zoom = 8 if span > 0.8 else 10 if span > 0.25 else 13 if len(zonas) == 1 else 12
    fig.update_layout(
        map_style="open-street-map",
        map_center=dict(
            lat=float(puntos[datos.COL_LATITUD].mean()),
            lon=float(puntos[datos.COL_LONGITUD].mean()),
        ),
        map_zoom=zoom,
        height=560,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor=_PLOTLY_PAPER,
        legend=dict(
            font=dict(color="#FFFFFF"),
            bgcolor="rgba(4,14,26,0.82)",
        ),
        showlegend=len(zonas) <= 14 or modo == "Puntos de color",
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    if modo == "Puntos de color":
        st.caption(
            f"{len(puntos):,} clientes · {len(zonas)} zonas. "
            "Solo puntos. Las zonas vecinas llevan tonalidades bien separadas."
        )
    else:
        st.caption(
            f"{len(puntos):,} clientes · {len(zonas)} zonas. "
            "El borde de color agrupa los clientes de cada distrito, cantón o provincia del perfil."
        )


def _render_base(df: pd.DataFrame) -> None:
    _cabecera("Base de datos")
    st.caption(
        f"Hoja «{datos.HOJA_CLIENTES}» · {len(df):,} filas · {len(df.columns)} columnas."
    )
    with st.container(border=True):
        st.dataframe(df, width="stretch", height=640, hide_index=True)


def _render_mapas(df: pd.DataFrame, corte: str) -> None:
    otro = st.session_state.get("tr_otro", datos.COL_PROVINCIA)
    if corte == "Otros":
        if st.session_state.get("tr_otro_radio") not in datos.CORTES_OTROS:
            st.session_state["tr_otro_radio"] = (
                otro if otro in datos.CORTES_OTROS else datos.COL_PROVINCIA
            )
        otro = st.radio(
            "Otro corte",
            datos.CORTES_OTROS,
            horizontal=True,
            key="tr_otro_radio",
        )
        st.session_state["tr_otro"] = otro
    columna = datos.columna_corte("mapas", corte, otro)
    titulo = "Mapas por otros" if corte == "Otros" else f"Mapas por {corte.lower()}"
    _cabecera(titulo)

    if datos.COL_LATITUD not in df.columns or datos.COL_LONGITUD not in df.columns:
        st.error("La base no trae Latitud y Longitud.")
        return

    with st.container(border=True):
        vista = _filtro_grupo(df, columna, corte if corte != "Otros" else columna)
        puntos = vista.dropna(subset=[datos.COL_LATITUD, datos.COL_LONGITUD]).reset_index(
            drop=True
        )
        st.caption(f"{len(puntos):,} clientes con coordenada · corte «{columna}».")
    if puntos.empty:
        st.info("No hay puntos para ese corte.")
        return

    centro_lat = float(puntos[datos.COL_LATITUD].mean())
    centro_lon = float(puntos[datos.COL_LONGITUD].mean())
    color = datos.COL_PROVINCIA if datos.COL_PROVINCIA in puntos.columns else None
    hover = [c for c in (datos.COL_NOMBRE_RUTA, columna) if c in puntos.columns and c != datos.COL_DISTRITO]
    fig = px.scatter_map(
        puntos,
        lat=datos.COL_LATITUD,
        lon=datos.COL_LONGITUD,
        hover_name=datos.COL_NOMBRE if datos.COL_NOMBRE in puntos.columns else None,
        hover_data=hover or None,
        custom_data=[datos.COL_DISTRITO] if datos.COL_DISTRITO in puntos.columns else None,
        color=color,
        center={"lat": centro_lat, "lon": centro_lon},
        zoom=10,
        height=520,
    )
    fig.update_traces(marker=dict(size=10))
    fig.update_layout(
        map_style="open-street-map",
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor=_PLOTLY_PAPER,
        font=dict(color=_PLOTLY_TEXTO),
        legend=dict(font=dict(color=_PLOTLY_TEXTO)),
        clickmode="event+select",
    )
    evento = st.plotly_chart(
        fig,
        width="stretch",
        key=f"tr_mapa_{corte}",
        on_select="rerun",
        selection_mode="points",
    )
    _render_clientes_distrito(df, _distritos_del_clic(evento, puntos))


def _color_visible(hex_color: str) -> str:
    """Un blanco casi puro desaparece sobre el mapa; se cambia por negro."""
    rojo, verde, azul = _rgb(hex_color)
    if 0.299 * rojo + 0.587 * verde + 0.114 * azul > 210:
        return "#111111"
    return hex_color


def _flechas_ruta(coords: list[tuple[float, float]]) -> tuple[list[float | None], list[float | None]]:
    """Flecha negra de cada cliente al siguiente más cercano, hasta unirlos a todos."""
    orden = datos.orden_por_cercania(
        [p[0] for p in coords],
        [p[1] for p in coords],
    )
    lats: list[float | None] = []
    lons: list[float | None] = []
    for inicio, fin in zip(orden, orden[1:], strict=False):
        a, b = coords[inicio], coords[fin]
        lats.extend([a[0], b[0], None])
        lons.extend([a[1], b[1], None])
        dlat = (b[0] - a[0]) * 111.0
        coseno = max(0.2, math.cos(math.radians((a[0] + b[0]) / 2)))
        dlon = (b[1] - a[1]) * 111.0 * coseno
        dist = math.hypot(dlat, dlon) or 1e-6
        norte, este = dlat / dist, dlon / dist
        largo = min(0.28, dist * 0.32)
        ala = largo * 0.45
        base_lat = b[0] - (norte * largo) / 111.0
        base_lon = b[1] - (este * largo) / (111.0 * coseno)
        lats.extend(
            [
                base_lat + (este * ala) / 111.0,
                b[0],
                None,
                base_lat - (este * ala) / 111.0,
                b[0],
                None,
            ]
        )
        lons.extend(
            [
                base_lon - (norte * ala) / (111.0 * coseno),
                b[1],
                None,
                base_lon + (norte * ala) / (111.0 * coseno),
                b[1],
                None,
            ]
        )
    return lats, lons


def _render_cluster(df: pd.DataFrame, corte: str) -> None:
    columna = datos.columna_corte("cluster", corte)
    _cabecera(f"Cluster por {corte.lower()}")
    st.caption(
        "Segmentos de 15 a 25 clientes, lo más juntos posible por latitud y longitud. "
        f"Un {corte.lower()} que ya cae en ese rango se queda. "
        "Si tiene de más, se parte. Si tiene de menos, se pega al vecino más cercano."
    )
    if columna not in df.columns:
        st.error(f"La base no trae «{columna}».")
        return
    if datos.COL_LATITUD not in df.columns or datos.COL_LONGITUD not in df.columns:
        st.error("La base no trae Latitud y Longitud.")
        return
    objetivo = st.slider(
        "Clientes por segmento",
        min_value=datos.MIN_SEGMENTO,
        max_value=datos.MAX_SEGMENTO,
        value=20,
        key="tr_cluster_objetivo",
        help="Tamaño al que se apunta. El segmento queda entre 15 y 25 clientes.",
    )
    puntos, resumen = datos.segmentar_por_cercania(df, columna, int(objetivo))
    if resumen.empty:
        st.info("No hay clientes con coordenada para armar segmentos.")
        return
    en_rango = int(((resumen["Clientes"] >= datos.MIN_SEGMENTO) & (resumen["Clientes"] <= datos.MAX_SEGMENTO)).sum())
    debajo = int((resumen["Clientes"] < datos.MIN_SEGMENTO).sum())
    st.caption(
        f"{len(resumen)} segmentos · {en_rango} entre 15 y 25 · "
        f"{int((resumen['Forma'] == 'Partido por cercanía').sum())} salen de partir un {corte.lower()} · "
        f"{int((resumen['Forma'] == 'Unido al vecino').sum())} unen vecinos."
        + (f" {debajo} quedaron por debajo de 15 porque el vecino ya no tenía cupo." if debajo else "")
    )
    mapa = puntos.rename(columns={"Segmento": "Zona"})
    zonas = resumen.sort_values("Segmento")["Segmento"].astype(str).tolist()
    lugares = {
        str(fila["Segmento"]): str(fila["Lugares"])
        for _, fila in resumen.iterrows()
    }
    clientes_de = {
        str(fila["Segmento"]): int(fila["Clientes"])
        for _, fila in resumen.iterrows()
    }
    st.markdown("**Ver en el mapa**")
    st.caption("Marque un segmento para ver solo sus clientes. Sin marcas se ven todos.")
    columnas_check = st.columns(4)
    elegidos: list[str] = []
    for i, zona in enumerate(zonas):
        lugar = lugares.get(zona, zona).split(" · ")[0]
        with columnas_check[i % 4]:
            if st.checkbox(
                f"{zona} · {clientes_de.get(zona, 0)} · {lugar}",
                key=f"tr_cluster_ver_{corte}_{int(objetivo)}_{zona}",
            ):
                elegidos.append(zona)
    visibles = elegidos or zonas
    detalle = bool(elegidos)
    if detalle:
        color_de = {
            zona: _COLORES_CLUSTER[i % len(_COLORES_CLUSTER)]
            for i, zona in enumerate(visibles)
        }
    else:
        color_de = {
            zona: _color_visible(color)
            for zona, color in _colores_separados(mapa, zonas).items()
        }
    fig = go.Figure()
    for zona in visibles:
        grupo = mapa[mapa["Zona"] == zona]
        lat = grupo[datos.COL_LATITUD].astype(float).tolist()
        lon = grupo[datos.COL_LONGITUD].astype(float).tolist()
        if not lat:
            continue
        nombres = (
            grupo[datos.COL_NOMBRE].astype(str).tolist()
            if datos.COL_NOMBRE in grupo.columns
            else [zona] * len(lat)
        )
        if detalle:
            fl_lat, fl_lon = _flechas_ruta(list(zip(lat, lon, strict=False)))
            fig.add_trace(
                go.Scattermap(
                    lat=fl_lat,
                    lon=fl_lon,
                    mode="lines",
                    line=dict(color="#111111", width=2),
                    name=zona,
                    hoverinfo="skip",
                    showlegend=False,
                )
            )
        fig.add_trace(
            go.Scattermap(
                lat=lat,
                lon=lon,
                mode="markers",
                marker=dict(size=18 if detalle else 11, color=color_de[zona]),
                name=zona,
                text=nombres,
                hovertemplate="%{text}<br>" + zona + "<extra></extra>",
            )
        )
        if detalle:
            fig.add_trace(
                go.Scattermap(
                    lat=lat,
                    lon=lon,
                    mode="markers",
                    marker=dict(size=7, color="#FFFFFF"),
                    name=zona,
                    text=nombres,
                    hovertemplate="%{text}<br>" + zona + "<extra></extra>",
                    showlegend=False,
                )
            )
    vistos = mapa[mapa["Zona"].isin(visibles)]
    span = max(
        float(vistos[datos.COL_LATITUD].max() - vistos[datos.COL_LATITUD].min()),
        float(vistos[datos.COL_LONGITUD].max() - vistos[datos.COL_LONGITUD].min()),
    )
    if span > 0.8:
        zoom = 8
    elif span > 0.25:
        zoom = 10
    elif span > 0.08:
        zoom = 12
    elif span > 0.03:
        zoom = 13
    else:
        zoom = 14
    fig.update_layout(
        map_style="open-street-map",
        map_center=dict(
            lat=float(vistos[datos.COL_LATITUD].mean()),
            lon=float(vistos[datos.COL_LONGITUD].mean()),
        ),
        map_zoom=zoom,
        height=560,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor=_PLOTLY_PAPER,
        legend=dict(font=dict(color="#FFFFFF"), bgcolor="rgba(4,14,26,0.82)"),
        showlegend=len(visibles) <= 16,
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    if elegidos:
        st.caption(
            "Solo "
            + ", ".join(f"{zona} ({clientes_de.get(zona, 0)} clientes)" for zona in elegidos)
            + ". La flecha negra une cada cliente con el más cercano. "
            "Más adelante se ajusta a las carreteras."
        )
    with st.container(border=True):
        st.dataframe(resumen, width="stretch", height=420, hide_index=True)


def _render_rutas(df: pd.DataFrame, corte: str) -> None:
    columna = datos.columna_corte("rutas", corte)
    _cabecera(f"Rutas por {corte.lower()}")
    st.caption("Rutas ya cargadas en la base, vistas por el corte elegido.")
    if columna not in df.columns:
        st.error(f"La base no trae «{columna}».")
        return
    with st.container(border=True):
        vista = _filtro_grupo(df, columna, corte)
        columnas = [
            c
            for c in (
                columna,
                datos.COL_RUTA,
                datos.COL_NOMBRE_RUTA,
                datos.COL_NOMBRE,
                datos.COL_KM,
                datos.COL_DESPACHO,
            )
            if c in vista.columns
        ]
        st.dataframe(vista[columnas], width="stretch", height=480)


def main() -> None:
    _cargar_tema()
    _inicializar_menu()

    with st.sidebar:
        _render_marca_sidebar()
        _sidebar_datos()
        st.divider()
        _render_menu()

    df = _leer_datos()
    if df is None:
        _cabecera(TITULO)
        st.error(st.session_state.get("tr_error_carga") or "No hay datos de transportes.")
        st.stop()

    accion = st.session_state["tr_accion"]
    if accion == "base":
        _render_base(df)
        return
    if accion == "perfilado":
        _render_perfilado(df)
        return

    corte = st.session_state.get(f"tr_corte_{accion}", "Distrito")
    if accion == "mapas":
        _render_mapas(df, corte)
    elif accion == "cluster":
        _render_cluster(df, corte)
    else:
        _render_rutas(df, corte)


if __name__ == "__main__":
    main()
