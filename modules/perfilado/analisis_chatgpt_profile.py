"""ChatGPT para Profile Pro (laboratorio / profile2) — audio + conversación por turnos.

- Mic de perfil: interpreta el cruce con ChatGPT.
- Narrar análisis: resumen oral del gráfico.
- Conversación por turnos: hablar / escribir / parar (respuesta en audio).
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Callable

import pandas as pd
import speech_recognition as sr
import streamlit as st

try:
    import perfil_patch
except ImportError:  # pragma: no cover
    from modules.perfilado import perfil_patch  # type: ignore

try:
    from audio_recorder_streamlit import audio_recorder
except ImportError:  # pragma: no cover
    audio_recorder = None  # type: ignore[misc, assignment]

MODELO_TEXTO = "gpt-4o-mini"
MODELO_TTS = "gpt-4o-mini-tts"
VOZ_TTS = "fable"
NINGUNA = "— Ninguna —"
_DIR_MODULO = os.path.dirname(os.path.abspath(__file__))
_LOG_DIR = os.path.join(_DIR_MODULO, "logs")
_LOG_EVENTOS = os.path.join(_LOG_DIR, "chatgpt_eventos.jsonl")
OPS_OK = ("Suma", "Promedio")
_CLAVES_PERFIL_UI = (
    "lri_man_eje_x",
    "lri_man_eje_y",
    "lri_man_eje_y2",
    "lri_man_eje_y3",
    "lri_man_operacion_y",
    "lri_man_operacion_y2",
    "lri_man_operacion_y3",
    "lri_man_top_n",
    "lri_man_orden_ascendente",
)

_SYSTEM_INTERPRETAR = """\
Eres el copiloto de Profile Pro (LRI). El usuario pide un cruce/perfilado por voz o texto.
Recibes una MATRIZ_PERFILADO con TODOS los atributos (eje X) y TODAS las métricas numéricas (eje Y)
del Excel cargado. SOLO puedes usar nombres exactos de esa matriz.

Devuelve SOLO un JSON válido (sin markdown):
{
  "eje_x": "<1 atributo exacto de atributos_eje_x>",
  "eje_y": "<métrica principal exacta de metricas_eje_y>",
  "eje_y2": "<2ª métrica exacta o null>",
  "eje_y3": "<3ª métrica exacta o null>",
  "operacion_y": "Suma" | "Promedio",
  "operacion_y2": "Suma" | "Promedio",
  "operacion_y3": "Suma" | "Promedio",
  "top_n": <entero 0..50000 o null; 0 = TODOS sin recorte>,
  "filtro_categoria": "<valor exacto de valores_filtro_categoria o null>",
  "filtro_subcategoria": "<valor exacto de valores_filtro_subcategoria o null>",
  "vista_especial": "abc_articulos" | null,
  "orden_y": "mayor_a_menor" | "menor_a_mayor" | null,
  "explicacion_corta": "<1 frase en español>"
}
Reglas:
- Máximo 3 métricas en Y (eje_y, eje_y2, eje_y3). Mínimo 1 (eje_y).
- ORDEN DE MÉTRICAS (OBLIGATORIO): respeta el orden en que el usuario las menciona
  al hablar. 1ª mención → eje_y, 2ª → eje_y2, 3ª → eje_y3. Si pide 4 o más, usa solo las 3 primeras.
  Ejemplo: «inventario promedio, días inventario y utilidad bruta por categoría» →
  eje_y=valor inventario promedio, eje_y2=meses inventario (días≈meses en la matriz),
  eje_y3=margen bruto total, eje_x=categoria.
- Exactamente 1 atributo en eje_x.
- Jerarquía del eje X (OBLIGATORIA; no confundir):
  1) Si dicen «subcategoría» / «subcategoria» como dimensión («por subcategoría») →
     eje_x = "subcategoria" (NUNCA descripcion ni categoria).
  2) Si dicen «por categoría» / «según categoría» (agregar TODAS) → eje_x = "categoria".
  3) SKU = artículo = ítem = producto = código → eje_x = "descripcion" (o "codigo"),
     cuando piden el detalle de ítems (con o sin filtro de un valor nombrado).
- Filtros (NO son el eje X): si nombran un valor concreto de la matriz:
  - Está en valores_filtro_subcategoria (p. ej. «Alimentos Secos») → filtro_subcategoria = ese valor
    y filtro_categoria = null. Aunque digan «categoría» por error: «Alimentos Secos» es subcategoría.
  - Está en valores_filtro_categoria (p. ej. «Alimentos», «Mascotas») → filtro_categoria = ese valor.
  Preferir el match más largo: «Alimentos Secos» gana sobre «Alimentos».
- «artículos/SKU de Alimentos Secos» → filtro_subcategoria=Alimentos Secos, eje_x=descripcion, top_n=0.
- «artículos/SKU de la categoría Alimentos» → filtro_categoria=Alimentos, eje_x=descripcion, top_n=0.
- «ventas por categoría» / «inventario por subcategoría» → agregación; eje_x = categoria o subcategoria;
  sin filtro (salvo que nombren un valor padre).
- Alias de métricas (usa el nombre EXACTO de la matriz):
  - Ventas → "ventas totales"
  - Utilidad/margen bruto → "margen bruto total"
  - Inventario valor / inventario promedio → "valor inventario promedio"
  - Inventario en bultos → "inventario promedio bultos"
  - Días inventario / días de inventario / DOI → "meses inventario" (si existe; si no, rotacion)
  - Meses inventario → "meses inventario"
  - Rotación → "rotacion"
- "mayores/top/ranking" → top_n 10–25 (default 15).
- "todos / todas / completo / cada uno / lista completa / sin límite" → top_n = 0 (mostrar TODOS los ítems).
- Clase ABC como atributo agregado («ventas por clase», «inventario por clase») → eje_x = "clase" y vista_especial = null.
- Listar / ver qué artículos son A, B, C (o «artículos ABC», «clasificación ABC de SKUs») →
  vista_especial = "abc_articulos", eje_x = "descripcion", top_n = 0,
  eje_y = una métrica numérica de la matriz (preferir "valor inventario promedio" o "ventas totales").
  La app mostrará scatter + tabla; no inventes columnas.
- Orden del gráfico: por defecto mayor→menor. Si piden «menor a mayor», «ascendente», «peores»,
  «más bajos», «menor utilidad/margen» → orden_y = "menor_a_mayor".
  Si piden «mayor a menor», «descendente», «mejores», «top» → orden_y = "mayor_a_menor" (o null).
- Cualquier cruce 1×{1..3} dentro de la matriz es válido; no inventes columnas fuera de la matriz.

Ejemplos few-shot (adapta nombres EXACTOS a la MATRIZ recibida; si falta una columna, elige la más cercana de la matriz):
1) Pedido: "muéstrame todos los artículos de menor a mayor utilidad bruta"
   → eje_x=descripcion, eje_y=margen bruto total, top_n=0, orden_y=menor_a_mayor, vista_especial=null
2) Pedido: "top 15 ventas por descripción"
   → eje_x=descripcion, eje_y=ventas totales, top_n=15, orden_y=mayor_a_menor, vista_especial=null
3) Pedido: "inventario promedio de cada sku"
   → eje_x=descripcion, eje_y=valor inventario promedio, top_n=0, operacion_y=Promedio, vista_especial=null
4) Pedido: "ventas y margen bruto por categoría"
   → eje_x=categoria, eje_y=ventas totales, eje_y2=margen bruto total, top_n=0, vista_especial=null
5) Pedido: "qué artículos son ABC" / "clasificación ABC de los skus"
   → vista_especial=abc_articulos, eje_x=descripcion, top_n=0, eje_y=valor inventario promedio (o ventas)
6) Pedido: "ventas por clase"
   → eje_x=clase, eje_y=ventas totales, vista_especial=null
7) Pedido: "en forma ascendente el valor de inventario de todos los productos"
   → eje_x=descripcion, eje_y=valor inventario promedio, top_n=0, orden_y=menor_a_mayor
8) Pedido: "descendente margen por subcategoría"
   → eje_x=subcategoria, eje_y=margen bruto total, orden_y=mayor_a_menor
9) Pedido: "muéstrame el inventario por subcategoría"
   → eje_x=subcategoria, eje_y=valor inventario promedio (NUNCA descripcion)
10) Pedido: "grafica ventas por categoría"
   → eje_x=categoria, eje_y=ventas totales (NUNCA subcategoria ni descripcion)
11) Pedido: "artículos de la categoría Alimentos" (si Alimentos está en valores_filtro_categoria)
   → filtro_categoria=Alimentos, eje_x=descripcion
12) Pedido: "ventas por SKU de la categoría Alimentos" / "ventas de cada artículo en Alimentos"
   → filtro_categoria=Alimentos, eje_x=descripcion, eje_y=ventas totales, top_n=0
   (NUNCA eje_x=categoria ni subcategoria)
13) Pedido: "ventas e inventario promedio por SKU de Alimentos"
   → filtro_categoria=Alimentos, eje_x=descripcion, eje_y=ventas totales,
     eje_y2=valor inventario promedio, top_n=0
14) Pedido: "subcategorías de Alimentos" / "ventas por subcategoría en Alimentos"
   → filtro_categoria=Alimentos, eje_x=subcategoria
15) Pedido: "ventas de cada SKU de Alimentos Secos" / "SKU de la categoría alimentos secos"
   → filtro_subcategoria=Alimentos Secos, filtro_categoria=null, eje_x=descripcion,
     eje_y=ventas totales, top_n=0
   (NUNCA eje_x=categoria; Alimentos Secos NO es categoría)
16) Pedido: "utilidad bruta y rotación por SKU en Alimentos Secos"
   → filtro_subcategoria=Alimentos Secos, eje_x=descripcion, eje_y=margen bruto total,
     eje_y2=<rotación de la matriz si existe>, top_n=0
17) Pedido: "ventas, utilidad bruta y días inventario por categoría"
   → eje_x=categoria, eje_y=ventas totales, eje_y2=margen bruto total,
     eje_y3=meses inventario (o rotacion si no hay meses), top_n=0
18) Pedido: "inventario promedio, días inventario y utilidad bruta por subcategoría"
   → eje_x=subcategoria, eje_y=valor inventario promedio, eje_y2=meses inventario,
     eje_y3=margen bruto total, top_n=0
19) Pedido: "ventas, margen y rotación de cada SKU en Alimentos"
   → filtro_categoria=Alimentos, eje_x=descripcion, eje_y=ventas totales,
     eje_y2=margen bruto total, eje_y3=rotacion, top_n=0
"""

_SYSTEM_NARRAR = """\
Eres consultor de inventarios (LRI). Resumen ORAL breve en español latinoamericano
(35–55 segundos, ~70–120 palabras). SOLO prosa hablada (sin markdown ni viñetas).
Usa ÚNICAMENTE el JSON de hechos. No inventes números.
Obligatorio:
- Di el cruce (dimensión × métrica) y el universo filtrado (n_universo / ambito_filtro).
  Si n_barras_en_pantalla < n_universo, aclara que el % es sobre el total del filtro.
- Di el total de la métrica principal del universo.
- Di concentración útil: pct_top_3, pct_top_5 y/o pct_top_10 de "concentracion"
  (ej. los 5 mayores concentran el 42% del total de la subcategoría). NUNCA digas
  que los N ítems generan el 100% solo porque N es todo lo visible.
- Nombra 2–3 líderes con su % individual si viene en top[].
- Cierra con 1 idea accionable (foco, cola, riesgo).
"""

_SYSTEM_CONVERSACION = """\
Eres un consultor senior de supply chain / inventarios (LRI Profile Pro).
Hablas en español latinoamericano, cercano y profesional.

PRIORIDAD: si el usuario pregunta por porcentajes, participación, concentración,
“cuánto representan los primeros N”, “qué % del total”, “análisis de los 3 primeros”,
responde con los hechos del JSON (perfil_en_pantalla.concentracion, n_universo,
ambito_filtro y top[].pct_acumulado / pct_del_total_principal).
NO cambies el gráfico ni propongas recortar a N barras: el % es siempre sobre el
universo filtrado completo (todos los SKUs de la categoría/subcategoría).

Reglas de datos:
- Usa SOLO hechos JSON + historial. NO inventes números.
- Si preguntan “los primeros 5 / top 5 / primeros diez”, usa concentracion.pct_top_5
  (o pct_top_3 / pct_top_10 / pct_top_20 / pct_top_2). Si falta ese N, usa el
  pct_acumulado del N-ésimo ítem en top[].
- Di el ámbito (ambito_filtro) y cuántos ítems tiene (n_universo).
- NUNCA digas que todos los ítems visibles “son el 100%” como insight: es trivial.
- Si piden lista completa: di n_universo y resume mayores; no leas 100 nombres en voz.
Respuestas ORALES cortas (15–40 s): sin markdown, sin viñetas, sin emojis.
"""

_SYSTEM_INTENTO = """\
Clasificas el mensaje del usuario en Profile Pro. Devuelve SOLO JSON válido (sin markdown):
{
  "accion": "cambiar_perfil" | "parche_perfil" | "deshacer" | "rehacer" | "narrar_analisis" | "consultar",
  "pedido_perfil": "<texto del cruce si accion=cambiar_perfil, si no null>",
  "motivo": "<frase corta>"
}
Reglas estrictas:
- accion=deshacer si pide volver al gráfico anterior / deshacer / regresar como estaba.
- accion=rehacer si pide rehacer el último cambio deshecho.
- accion=parche_perfil si pide SUSTITUIR/REEMPLAZAR/CAMBIAR una o varias métricas
  del gráfico YA en pantalla (ej. “sustituya ventas totales por meses inventario”),
  o solo cambiar el Top N, SIN pedir un cruce nuevo completo.
- accion=consultar si pregunta sobre el gráfico/ranking YA en pantalla:
  porcentajes, participación, “cuánto representan los primeros N”,
  “análisis de los 3 primeros”, concentración, explicar un número, sin pedir otro cruce.
  NUNCA uses cambiar_perfil para recortar el Top N cuando solo preguntan el %.
- accion=consultar también para saludos o charla.
- accion=narrar_analisis si pide narrar/resumir el gráfico actual sin otro cruce
  y SIN preguntar el % de los primeros N.
- accion=cambiar_perfil SOLO si pide explícitamente VER/MOSTRAR/GRAFICAR/ARMAR
  un cruce NUEVO completo (otra dimensión o un set nuevo de métricas desde cero).
NUNCA uses cambiar_perfil ante un saludo.
NUNCA uses cambiar_perfil solo porque mencionen “ventas” o “artículos” en una
pregunta de porcentaje del ranking actual.
NUNCA uses cambiar_perfil para “sustituya X por Y”: eso es parche_perfil.
"""

_MAX_TURNOS_HISTORIAL = 12
_VOICE_PAUSA_CHAT = 3.0
_NARRAR_KEYS = (
    "analiz",
    "narr",
    "resumen",
    "explic",
    "pareto",
    "cuentame",
    "quetalves",
    "queves",
    "interpret",
)
_CONSULTA_ANALITICA_KEYS = (
    "porcentaje",
    "porcient",
    "participacion",
    "concentr",
    "acumulad",
    "representa",
    "representan",
    "aportan",
    "aporta",
    "generan",
    "deltotal",
    "sobreetotal",
    "cuantorepresent",
    "querepresent",
    "cuantogener",
    "cuantosuman",
    "primeros",
    "primeras",
    "losprimeros",
    "lasprimeras",
    "cabeza",
    "cola",
    "cuantoes",
    "quedice",
    "explicameese",
    "eseporcentaje",
)
_CAMBIAR_KEYS = (
    "muestr",
    "graf",
    "cambi",
    "pasame",
    "quierover",
    "present",
    "ponme",
    "armame",
)
_SALUDO_KEYS = (
    "hola",
    "buenas",
    "buenosdias",
    "buenastardes",
    "buenasnoches",
    "comoestas",
    "comoesta",
    "comoteva",
    "comova",
    "quetal",
    "estasbien",
    "quehaces",
    "meescuchas",
    "escuchas",
    "puedesoír",
    "hey",
)


def obtener_api_key() -> str | None:
    env = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if env:
        return env
    try:
        secret = st.secrets.get("OPENAI_API_KEY", "")
        if isinstance(secret, str) and secret.strip():
            return secret.strip()
    except Exception:
        pass
    ses = st.session_state.get("prf2_openai_api_key")
    if isinstance(ses, str) and ses.strip():
        return ses.strip()
    return None


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _columna_descartable(nombre: str) -> bool:
    s = str(nombre).strip()
    return (not s) or s.lower().startswith("unnamed")


def _clasificar_metrica(nombre: str) -> str:
    n = _norm(nombre)
    if any(k in n for k in ("venta", "margen", "util", "precio", "costo", "evai", "gmroi")):
        return "financiera_comercial"
    if any(k in n for k in ("invent", "rotacion", "mesesinvent", "cubicaje", "tarima", "bulto")):
        return "inventario_logistica"
    if "demanda" in n or "demada" in n:
        return "demanda"
    if any(k in n for k in ("orden", "pedido", "entrega", "despach", "escazes", "escasez")):
        return "servicio_operacion"
    return "numerica_otras"


def _clasificar_atributo(nombre: str) -> str:
    n = _norm(nombre)
    if any(k in n for k in ("sku", "codigo", "descripcion", "producto", "articulo", "item")):
        return "producto_sku"
    if "subcateg" in n:
        return "subcategoria"
    if "categ" in n or n == "clase":
        return "categoria_clase"
    if "proveedor" in n:
        return "proveedor"
    if "pais" in n or "region" in n:
        return "geografia"
    return "atributo_otros"


def construir_matriz_perfilado(df: pd.DataFrame) -> dict[str, Any]:
    """Matriz canónica: todo atributo (X) × toda métrica numérica (Y), máx. 3 en Y.

    Se deriva del DataFrame cargado (Excel). Cualquier cruce 1×{1..3} de esta
    matriz es graficalbe por Profile; ChatGPT solo elige dentro de ella.
    """
    attrs = [
        c
        for c in df.select_dtypes(include=["object", "category"]).columns.tolist()
        if not _columna_descartable(c)
    ]
    # Pandas 2.x/3: columnas string
    try:
        for c in df.select_dtypes(include=["string"]).columns.tolist():
            if not _columna_descartable(c) and c not in attrs:
                attrs.append(c)
    except (TypeError, ValueError):
        pass
    # Incluir códigos numéricos que actúan como atributo (p. ej. codigo si viniera numérico)
    for c in df.columns:
        if _columna_descartable(c) or c in attrs:
            continue
        n = _norm(c)
        if n in ("codigo", "sku", "clave") and c not in attrs:
            attrs.append(c)

    mets = [
        c
        for c in df.select_dtypes(include=["number"]).columns.tolist()
        if not _columna_descartable(c)
    ]

    grupos_attr: dict[str, list[str]] = {}
    for a in attrs:
        grupos_attr.setdefault(_clasificar_atributo(a), []).append(a)

    grupos_met: dict[str, list[str]] = {}
    for m in mets:
        grupos_met.setdefault(_clasificar_metrica(m), []).append(m)

    n_a, n_m = len(attrs), len(mets)
    # Combinaciones de 1, 2 o 3 métricas en Y
    from math import comb

    n_comb_y = comb(n_m, 1) + (comb(n_m, 2) if n_m >= 2 else 0) + (comb(n_m, 3) if n_m >= 3 else 0)
    n_cruces = n_a * n_comb_y

    cats = _valores_categoria(df)
    subs = _valores_subcategoria(df)

    return {
        "version": 1,
        "reglas": {
            "eje_x": "exactamente 1 atributo de atributos_eje_x",
            "eje_y": "1 a 3 métricas de metricas_eje_y (orden: principal, adicional 2, adicional 3)",
            "filtro_opcional": (
                "drill-down por valor de categoria o subcategoria "
                "(preferir match más largo; p. ej. Alimentos Secos > Alimentos)"
            ),
            "fuente": "solo columnas presentes en el Excel/DataFrame cargado",
        },
        "atributos_eje_x": attrs,
        "metricas_eje_y": mets,
        "grupos_atributos": grupos_attr,
        "grupos_metricas": grupos_met,
        "valores_filtro_categoria": cats,
        "valores_filtro_subcategoria": subs,
        "cobertura": {
            "n_atributos": n_a,
            "n_metricas": n_m,
            "n_combinaciones_metricas_y_hasta_3": n_comb_y,
            "n_cruces_perfil_posibles": n_cruces,
            "assertividad": (
                "ChatGPT solo puede elegir nombres exactos de esta matriz; "
                "todo cruce 1 atributo × 1–3 métricas es válido para graficar."
            ),
        },
    }


def catalogo_columnas(df: pd.DataFrame) -> dict[str, list[str]]:
    matriz = construir_matriz_perfilado(df)
    return {
        "dimensiones": list(matriz["atributos_eje_x"]),
        "metricas": list(matriz["metricas_eje_y"]),
        "todas": list(df.columns),
        "matriz": matriz,
    }


def guardar_matriz_perfilado(
    df: pd.DataFrame,
    ruta: str | None = None,
) -> str:
    """Persiste la matriz para auditoría / clientes (lab)."""
    ruta = ruta or os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "matriz_perfilado_actual.json",
    )
    matriz = construir_matriz_perfilado(df)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(matriz, f, ensure_ascii=False, indent=2)
    return ruta


def _resolver_columna(nombre: str | None, candidatas: list[str]) -> str | None:
    if not nombre or not isinstance(nombre, str):
        return None
    nombre = nombre.strip()
    if not nombre or nombre.lower() in {"null", "none", "ninguna", "-"}:
        return None
    if nombre in candidatas:
        return nombre
    n = _norm(nombre)
    for c in candidatas:
        if _norm(c) == n:
            return c
    for c in candidatas:
        cn = _norm(c)
        if n and (n in cn or cn in n):
            return c
    return None


def _valores_columna_texto(df: pd.DataFrame, col: str) -> list[str]:
    if col not in df.columns:
        return []
    return sorted(
        {str(v).strip() for v in df[col].dropna().tolist() if str(v).strip() and str(v).strip().lower() != "nan"}
    )


def _valores_categoria(df: pd.DataFrame) -> list[str]:
    return _valores_columna_texto(df, "categoria")


def _valores_subcategoria(df: pd.DataFrame) -> list[str]:
    return _valores_columna_texto(df, "subcategoria")


def _resolver_filtros_segmento(
    pedido: str,
    df: pd.DataFrame,
    *,
    hint_categoria: str | None = None,
    hint_subcategoria: str | None = None,
) -> tuple[str | None, str | None]:
    """Detecta filtro por categoría o subcategoría.

    Prefiere el match más largo (p. ej. «Alimentos Secos» gana sobre «Alimentos»).
    «Alimentos Secos» es subcategoría (Mascotas), no categoría.
    """
    pedido_n = _norm(pedido)
    candidatos: list[tuple[int, str, str]] = []

    def _push(tipo: str, valor: str) -> None:
        vn = _norm(valor)
        if vn and vn in pedido_n:
            candidatos.append((len(vn), tipo, valor))

    def _push_hint(tipo: str, hint: str | None, valores: list[str]) -> None:
        if not hint:
            return
        hit = _resolver_columna(hint, valores)
        if hit:
            candidatos.append((len(_norm(hit)), tipo, hit))
            return
        hn = _norm(hint)
        for v in valores:
            vn = _norm(v)
            if hn and (hn == vn or hn in vn or vn in hn):
                candidatos.append((len(vn), tipo, v))

    cats = _valores_categoria(df)
    subs = _valores_subcategoria(df)
    for c in cats:
        _push("categoria", c)
    for s in subs:
        _push("subcategoria", s)
    _push_hint("categoria", hint_categoria, cats)
    _push_hint("subcategoria", hint_subcategoria, subs)

    if not candidatos:
        return None, None
    candidatos.sort(key=lambda x: (-x[0], 0 if x[1] == "subcategoria" else 1))
    _len, tipo, valor = candidatos[0]
    if tipo == "subcategoria":
        return None, valor
    return valor, None


def _resolver_filtro_categoria(pedido: str, df: pd.DataFrame, hint: str | None) -> str | None:
    """Compat: solo categoría (sin subcategoría). Preferir _resolver_filtros_segmento."""
    cat, _sub = _resolver_filtros_segmento(pedido, df, hint_categoria=hint)
    return cat


def _pide_todos_los_items(pedido: str) -> bool:
    """True si el usuario quiere ver el listado completo (sin Top N)."""
    p = _norm(pedido)
    # _norm quita espacios: las claves van pegadas.
    claves = (
        "todoslossaku",
        "todoslossku",
        "todaslossku",
        "todoslosarticulo",
        "todaslosarticulo",
        "todoslosproducto",
        "todaslosproducto",
        "todosloscodigo",
        "listacompleta",
        "listadocompleto",
        "completodesku",
        "sintop",
        "sinlimite",
        "sinrecorte",
        "cadasku",
        "cadaarticulo",
        "cadaproducto",
        "cadauno",
        "cadaunode",
        "decadauno",
        "porcadauno",
        "inventariodecada",
        "inventariopromediodecada",
    )
    if any(k in p for k in claves):
        return True
    # “todos” / “todas” junto a sku/artículo/inventario
    if ("todos" in p or "todas" in p or "completo" in p or "completa" in p) and any(
        k in p for k in ("sku", "articulo", "producto", "codigo", "descripcion", "invent", "item")
    ):
        return True
    return False


def pide_vista_abc_articulos(pedido: str) -> bool:
    """True: listar/ver artículos por clase ABC (scatter/tabla), no agregación «por clase»."""
    p = _norm(pedido)
    if not p:
        return False
    # Agregado estándar: ventas/inventario *por* clase → barras normales.
    # (_norm compacta espacios: "por clase" → "porclase")
    agregado_sin_listado = (
        ("porclase" in p or "segunclase" in p)
        and not any(
            k in p
            for k in (
                "articulo",
                "sku",
                "producto",
                "codigo",
                "cada",
                "cuales",
                "lista",
            )
        )
    )
    if agregado_sin_listado:
        return False
    tiene_abc = (
        "abc" in p
        or "clasificacionabc" in p
        or "claseabc" in p
        or "aby c" in p  # residual improbable
        or "clasea" in p
        or "claseb" in p
        or "clasec" in p
        or "clase" in p
    )
    if not tiene_abc:
        return False
    pide_listado = any(
        k in p
        for k in (
            "articulo",
            "sku",
            "producto",
            "codigo",
            "cuales",
            "lista",
            "listado",
            "muestra",
            "mostrar",
            "queson",
            "sona",
            "sonb",
            "sonc",
            "cada",
            "punto",
            "scatter",
            "plotter",
            "punteo",
        )
    )
    # «muéstrame el ABC» / «clasificación ABC» sin métrica agregada explícita
    if "abc" in p or "clasificacion" in p:
        return True
    return pide_listado


def pide_orden_ascendente(pedido: str) -> bool | None:
    """True=menor→mayor, False=mayor→menor, None=dejar automático de la métrica."""
    p = _norm(pedido)
    if not p:
        return None
    pide_asc = any(
        k in p
        for k in (
            "menoramayor",
            "demenoramayor",
            "demenor",
            "ascendente",
            "peores",
            "peor",
            "masbajos",
            "masbajo",
            "menores",
            "menorutilidad",
            "menormargen",
            "bajautilidad",
            "bajomargen",
            "bottom",
            "ascending",
        )
    )
    pide_desc = any(
        k in p
        for k in (
            "mayoramenor",
            "demayoramenor",
            "demayor",
            "descendente",
            "mejores",
            "mejor",
            "masaltos",
            "masalto",
            "ranking",
            "descending",
        )
    )
    # "top" / "mayores" suelen ser ranking alto; si también dijeron menor→mayor, gana asc.
    if pide_asc:
        return True
    if pide_desc or "top" in p or "mayores" in p:
        return False
    return None


def _pedido_sin_subcategoria(p: str) -> str:
    """Quita 'subcategoria' para poder detectar 'categoria' sin falso positivo."""
    return (
        p.replace("subcategoria", "")
        .replace("subcategorias", "")
        .replace("subcateg", "")
        .replace("porsubcategoria", "")
        .replace("subfamilia", "")
        .replace("subgrupo", "")
    )


def _pide_dimension_subcategoria(pedido_n: str) -> bool:
    return any(
        k in pedido_n
        for k in (
            "subcategoria",
            "subcategorias",
            "subcateg",
            "porsubcategoria",
            "porsub",
            "subfamilia",
            "subgrupo",
            "sublinea",
        )
    )


def _pide_dimension_categoria(pedido_n: str) -> bool:
    """True si piden categoría como EJE X (agregación), no como filtro de un valor.

    «por categoría» / «según categoría» → eje = categoria.
    «de la categoría Alimentos» + SKU → NO es eje categoría (es filtro); eso se resuelve aparte.
    """
    if _pide_dimension_subcategoria(pedido_n):
        return False
    p = _pedido_sin_subcategoria(pedido_n)
    return any(
        k in p
        for k in (
            "porcategoria",
            "porcategorias",
            "seguncategoria",
            "lascategorias",
            "agruparporcategoria",
            "desgloseporcategoria",
        )
    )


def _pide_dimension_sku(pedido_n: str) -> bool:
    """SKU = artículo = ítem = producto = código = descripción."""
    return any(
        k in pedido_n
        for k in (
            "sku",
            "articulo",
            "articulos",
            "producto",
            "productos",
            "item",
            "items",
            "codigo",
            "codigos",
            "descripcion",
            "descripciones",
            "cadauno",
            "decada",
        )
    )


def _texto_busqueda_metricas(pedido: str) -> str:
    """Minúsculas sin acentos, conservando espacios para posiciones de mención."""
    s = unicodedata.normalize("NFKD", str(pedido))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def _extraer_metricas_en_orden(pedido: str, mets: list[str]) -> list[str]:
    """Hasta 3 métricas en el orden en que el usuario las menciona al hablar."""
    if not mets:
        return []
    texto = _texto_busqueda_metricas(pedido)
    # (start, end, candidatos de columna)
    patrones: list[tuple[str, list[str]]] = [
        (r"dias?\s*(?:de\s*)?inventario|doi\b", ["meses inventario", "rotacion"]),
        (r"meses?\s*(?:de\s*)?inventario", ["meses inventario"]),
        (
            r"inventario\s+promedio\s+bultos|inventario\s+en\s+bultos|promedio\s+bultos",
            ["inventario promedio bultos"],
        ),
        (
            r"valor\s+inventario\s+promedio|inventario\s+promedio|inventario\s+valor|"
            r"inventario\s+promedio\s+valor",
            ["valor inventario promedio"],
        ),
        (
            r"margen\s+bruto(?:\s+total)?|utilidad\s+bruta|utilidad\s+bruto|"
            r"margen\s+de\s+utilidad|\bmargen\b|utilidad(?!\s*ventas)",
            ["margen bruto total", "margen utilidad ventas"],
        ),
        (r"margen\s+utilidad\s+ventas|margen\s+sobre\s+ventas", ["margen utilidad ventas"]),
        (r"ventas?\s+totales|\bventas\b|\bventa\b", ["ventas totales"]),
        (r"rotaci[oó]n|\brotacion\b", ["rotacion"]),
        (r"costo\s+mantener(?:\s+inventario)?", ["costo mantener inventario"]),
        (r"cubicaje(?:\s+inventario)?", ["cubicaje inventario"]),
        (r"ventas?\s+costo|costo\s+de\s+ventas", ["ventas costo"]),
    ]
    hits: list[tuple[int, int, list[str]]] = []
    for rx, cands in patrones:
        for m in re.finditer(rx, texto, flags=re.I):
            hits.append((m.start(), m.end(), cands))
    # Nombres exactos de la matriz (más largos primero) si aparecen literales.
    for col in sorted(mets, key=lambda x: len(_norm(x)), reverse=True):
        cn = _texto_busqueda_metricas(col)
        if len(cn) < 4:
            continue
        for m in re.finditer(re.escape(cn), texto):
            hits.append((m.start(), m.end(), [col]))

    hits.sort(key=lambda t: (t[0], -(t[1] - t[0])))
    elegidas: list[str] = []
    ocupado_hasta = -1
    for start, end, cands in hits:
        if start < ocupado_hasta:
            continue
        col_res = None
        for cand in cands:
            col_res = _resolver_columna(cand, mets)
            if col_res:
                break
        if not col_res or col_res in elegidas:
            continue
        elegidas.append(col_res)
        ocupado_hasta = end
        if len(elegidas) >= 3:
            break
    return elegidas


def _aplicar_heuristicas_perfil(
    pedido: str,
    df: pd.DataFrame,
    *,
    eje_x: str | None,
    eje_y: str | None,
    eje_y2: str | None,
    eje_y3: str | None,
    top_n: int | None,
    filtro_categoria: str | None,
    filtro_subcategoria: str | None = None,
) -> tuple[
    str | None,
    str | None,
    str | None,
    str | None,
    int | None,
    str | None,
    str | None,
    bool,
    bool | None,
]:
    """Corrige sesgos típicos (dimensión X, filtros cat/sub, métricas, ABC, orden)."""
    dims = catalogo_columnas(df)["dimensiones"]
    mets = catalogo_columnas(df)["metricas"]
    pedido_n = _norm(pedido)
    vista_abc = pide_vista_abc_articulos(pedido) and (
        _resolver_columna("clase", dims) is not None or "clase" in df.columns
    )
    orden_asc = pide_orden_ascendente(pedido)

    pide_sub = _pide_dimension_subcategoria(pedido_n)
    pide_cat = _pide_dimension_categoria(pedido_n)
    pide_sku = _pide_dimension_sku(pedido_n)
    pide_todos = _pide_todos_los_items(pedido)

    # Resolver filtros ANTES del eje: valores nombrados ≠ dimensión del gráfico.
    # «Alimentos Secos» (sub) gana sobre «Alimentos» (cat).
    filtro_categoria, filtro_subcategoria = _resolver_filtros_segmento(
        pedido,
        df,
        hint_categoria=filtro_categoria,
        hint_subcategoria=filtro_subcategoria,
    )
    hay_filtro_valor = bool(filtro_categoria or filtro_subcategoria)

    # Prioridad:
    # 1) Vista ABC
    # 2) Valor nombrado (cat/sub) + SKU → descripcion filtrada
    # 3) «por subcategoría» → eje subcategoria
    # 4) «por categoría» → eje categoria (sin filtro residual)
    # 5) SKU suelto / valor nombrado sin eje de agregación
    if vista_abc:
        eje_x = _resolver_columna("descripcion", dims) or _resolver_columna("codigo", dims) or eje_x
        top_n = 0
        pide_todos = True
    elif hay_filtro_valor and (pide_sku or not (pide_cat or pide_sub)):
        # Valor concreto: detalle por SKU (aunque digan «categoría» por error).
        eje_x = _resolver_columna("descripcion", dims) or _resolver_columna("codigo", dims) or eje_x
    elif pide_sub and not hay_filtro_valor:
        eje_x = _resolver_columna("subcategoria", dims) or eje_x
    elif pide_sub and filtro_categoria and not filtro_subcategoria:
        # «subcategorías de Alimentos»
        eje_x = _resolver_columna("subcategoria", dims) or eje_x
    elif pide_cat and not pide_sku:
        eje_x = _resolver_columna("categoria", dims) or eje_x
        filtro_categoria = None
        filtro_subcategoria = None
    elif pide_cat and pide_sku and not hay_filtro_valor:
        eje_x = _resolver_columna("categoria", dims) or eje_x
    elif pide_sku:
        eje_x = _resolver_columna("descripcion", dims) or _resolver_columna("codigo", dims) or eje_x

    # Hasta 3 métricas en el ORDEN hablado (prioridad sobre el JSON del modelo).
    ordenadas = _extraer_metricas_en_orden(pedido, mets)
    col_ventas = _resolver_columna("ventas totales", mets)
    col_util = _resolver_columna("margen bruto total", mets) or _resolver_columna(
        "margen utilidad ventas", mets
    )
    col_inv_val = _resolver_columna("valor inventario promedio", mets)
    col_inv_bultos = _resolver_columna("inventario promedio bultos", mets)
    col_rot = _resolver_columna("rotacion", mets) or _resolver_columna("rotación", mets)
    col_meses = _resolver_columna("meses inventario", mets)

    if ordenadas:
        eje_y = ordenadas[0]
        eje_y2 = ordenadas[1] if len(ordenadas) > 1 else None
        eje_y3 = ordenadas[2] if len(ordenadas) > 2 else None
    else:
        # Respaldo: señales sueltas (sin orden claro de 2–3 frases).
        pide_ventas = bool(re.search(r"venta(?!rio)", pedido_n))
        pide_util = any(k in pedido_n for k in ("utilidad", "margen", "brut"))
        pide_invent = "invent" in pedido_n
        pide_bultos = "bulto" in pedido_n
        pide_rot = "rotac" in pedido_n
        pide_dias = "diasinvent" in pedido_n or "doi" in pedido_n
        if pide_ventas and pide_util and col_ventas and col_util:
            eje_y, eje_y2 = col_ventas, col_util
            tercero = col_meses if pide_dias and col_meses else (col_rot if pide_rot else None)
            if tercero and tercero not in (eje_y, eje_y2):
                eje_y3 = tercero
        else:
            if (
                not pide_ventas
                and col_ventas
                and eje_y
                and _norm(eje_y) == _norm(col_ventas)
                and (pide_util or pide_invent or pide_rot or pide_dias)
            ):
                eje_y = None
            if pide_ventas and not eje_y and col_ventas:
                eje_y = col_ventas
            if pide_util and col_util:
                if not eje_y:
                    eje_y = col_util
                elif eje_y2 is None and col_util != eje_y:
                    eje_y2 = col_util
            if pide_invent:
                col_inv = col_inv_bultos if pide_bultos and col_inv_bultos else col_inv_val
                if col_inv:
                    if not eje_y:
                        eje_y = col_inv
                    elif eje_y2 is None and col_inv != eje_y:
                        eje_y2 = col_inv
            if pide_dias and col_meses:
                if not eje_y:
                    eje_y = col_meses
                elif eje_y2 is None and col_meses != eje_y:
                    eje_y2 = col_meses
                elif eje_y3 is None and col_meses not in (eje_y, eje_y2):
                    eje_y3 = col_meses
            if pide_rot and col_rot:
                if not eje_y:
                    eje_y = col_rot
                elif eje_y2 is None and col_rot != eje_y:
                    eje_y2 = col_rot
                elif eje_y3 is None and col_rot not in (eje_y, eje_y2):
                    eje_y3 = col_rot

    if vista_abc and not eje_y:
        eje_y = col_inv_val or col_ventas or (mets[0] if mets else None)

    # "de mayor a menor" / "de menor a mayor" no es pedido de Top N.
    pide_top_explicito = any(
        k in pedido_n
        for k in ("mayores", "top", "ranking", "principales", "primeros", "primeras")
    ) and not any(
        k in pedido_n
        for k in ("menormayor", "mayoramenor", "ascendente", "descendente")
    )
    # 0 = Todos (como el control «Filtrar Top N» de la app)
    if pide_todos or vista_abc:
        top_n = 0
    elif hay_filtro_valor and (pide_sku or eje_x in ("descripcion", "codigo")):
        if top_n is None and not pide_top_explicito:
            top_n = 0
    elif pide_top_explicito:
        if top_n is None:
            n_pedido, _ = _extraer_consulta_ranking(pedido)
            top_n = int(n_pedido) if n_pedido else 15
    elif (
        orden_asc is True
        and pide_sku
        and not pide_cat
        and not pide_sub
        and not hay_filtro_valor
        and top_n is None
    ):
        # Ordenar todos los ítems (p. ej. utilidad de menor a mayor).
        top_n = 0
    elif pide_sku and not pide_cat and not pide_sub and not hay_filtro_valor and top_n is None:
        top_n = 20
    elif (pide_cat or pide_sub) and top_n is None:
        top_n = 0

    # Pregunta de concentración («qué % representan los 3 primeros») → no recortar.
    if _parece_consulta_analitica(pedido):
        top_n = None

    return (
        eje_x,
        eje_y,
        eje_y2,
        eje_y3,
        top_n,
        filtro_categoria,
        filtro_subcategoria,
        vista_abc,
        orden_asc,
    )


def interpretar_pedido_perfil(
    pedido: str,
    df: pd.DataFrame,
    *,
    api_key: str,
) -> dict[str, Any]:
    from openai import OpenAI

    cat = catalogo_columnas(df)
    matriz = cat["matriz"]
    # Actualiza la matriz de referencia (auditoría / clientes) en cada interpretación.
    try:
        guardar_matriz_perfilado(df)
    except OSError:
        pass
    payload = {
        "pedido_usuario": pedido.strip(),
        "MATRIZ_PERFILADO": matriz,
    }
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=MODELO_TEXTO,
        temperature=0.1,
        max_tokens=350,
        messages=[
            {"role": "system", "content": _SYSTEM_INTERPRETAR},
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False),
            },
        ],
    )
    raw = (resp.choices[0].message.content or "").strip()
    if not raw:
        raise RuntimeError("ChatGPT no devolvió configuración.")
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.M).strip()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError("Respuesta ChatGPT inválida (no es objeto JSON).")

    dims = cat["dimensiones"]
    mets = cat["metricas"]
    todas = cat["todas"]

    eje_x = _resolver_columna(data.get("eje_x"), dims) or _resolver_columna(
        data.get("eje_x"), todas
    )
    eje_y = _resolver_columna(data.get("eje_y"), mets) or _resolver_columna(
        data.get("eje_y"), todas
    )
    eje_y2 = _resolver_columna(data.get("eje_y2"), mets) or _resolver_columna(
        data.get("eje_y2"), todas
    )
    eje_y3 = _resolver_columna(data.get("eje_y3"), mets) or _resolver_columna(
        data.get("eje_y3"), todas
    )

    def _op(key: str, default: str = "Suma") -> str:
        v = data.get(key) or default
        return v if v in OPS_OK else default

    top_n = data.get("top_n")
    try:
        top_n_i = int(top_n) if top_n is not None else None
        if top_n_i is not None:
            # 0 = Todos (sin recorte). Valores >0 se limitan a un tope práctico.
            if top_n_i < 0:
                top_n_i = 0
            elif top_n_i > 0:
                top_n_i = min(50000, top_n_i)
    except (TypeError, ValueError):
        top_n_i = None

    filtro_cat = data.get("filtro_categoria")
    if isinstance(filtro_cat, str):
        filtro_cat = filtro_cat.strip() or None
    else:
        filtro_cat = None
    filtro_sub = data.get("filtro_subcategoria")
    if isinstance(filtro_sub, str):
        filtro_sub = filtro_sub.strip() or None
    else:
        filtro_sub = None

    (
        eje_x,
        eje_y,
        eje_y2,
        eje_y3,
        top_n_i,
        filtro_cat,
        filtro_sub,
        vista_abc,
        orden_asc,
    ) = _aplicar_heuristicas_perfil(
        pedido,
        df,
        eje_x=eje_x,
        eje_y=eje_y,
        eje_y2=eje_y2,
        eje_y3=eje_y3,
        top_n=top_n_i,
        filtro_categoria=filtro_cat,
        filtro_subcategoria=filtro_sub,
    )
    vista_esp = str(data.get("vista_especial") or "").strip().lower()
    if vista_esp in ("abc_articulos", "abc", "scatter_abc") and "clase" in df.columns:
        vista_abc = True

    orden_raw = str(data.get("orden_y") or "").strip().lower()
    if orden_raw in ("menor_a_mayor", "ascendente", "asc", "ascending"):
        orden_asc = True
    elif orden_raw in ("mayor_a_menor", "descendente", "desc", "descending"):
        orden_asc = False

    config: dict[str, Any] = {
        "comando_voz_detectado": f"ChatGPT voz: {pedido.strip()}",
        "prf2_chatgpt_explicacion": str(data.get("explicacion_corta") or "").strip(),
        "drill_down_categoria": filtro_cat,
        "drill_down_subcategoria": filtro_sub,
        "prf2_vista_abc_articulos": bool(vista_abc),
    }
    if orden_asc is not None:
        config["lri_man_orden_ascendente"] = bool(orden_asc)
    else:
        config["lri_man_orden_ascendente"] = False
    if eje_x:
        config["lri_man_eje_x"] = eje_x
    if eje_y:
        config["lri_man_eje_y"] = eje_y
        config["lri_man_operacion_y"] = _op("operacion_y")
        config["lri_man_operacion"] = config["lri_man_operacion_y"]
    if eje_y2 and eje_y2 != eje_y:
        config["lri_man_eje_y2"] = eje_y2
        config["lri_man_operacion_y2"] = _op("operacion_y2")
    else:
        config["lri_man_eje_y2"] = NINGUNA
    if eje_y3 and eje_y3 not in {eje_y, eje_y2}:
        config["lri_man_eje_y3"] = eje_y3
        config["lri_man_operacion_y3"] = _op("operacion_y3")
    else:
        config["lri_man_eje_y3"] = NINGUNA
    # Incluir 0 (= Todos); no omitir la clave o queda el Top N anterior en sesión.
    if top_n_i is not None:
        config["lri_man_top_n"] = int(top_n_i)

    if not eje_x and not eje_y:
        raise RuntimeError(
            "No se pudo mapear el pedido a columnas del Excel."
        )
    return config


def hechos_perfil_resumen(
    df_resumen: pd.DataFrame,
    *,
    eje_x: str,
    eje_y: str,
    operacion_y: str,
    eje_y2: str | None = None,
    eje_y3: str | None = None,
    n_top: int | None = None,
    ambito_filtro: str | None = None,
    n_en_pantalla: int | None = None,
) -> dict[str, Any]:
    if df_resumen is None or df_resumen.empty or eje_x not in df_resumen.columns:
        return {"ok": False, "motivo": "Sin resumen de perfil"}
    if eje_y not in df_resumen.columns:
        return {"ok": False, "motivo": f"Falta métrica {eje_y}"}

    ys = pd.to_numeric(df_resumen[eje_y], errors="coerce").fillna(0.0)
    total = float(ys.sum())
    orden = df_resumen.assign(_y=ys).sort_values("_y", ascending=False).reset_index(drop=True)
    n_universo = int(len(df_resumen))
    n_barras = int(n_en_pantalla) if n_en_pantalla is not None else n_universo
    # Lista para conversación: completa si cabe; si no, top amplio.
    if n_top is None:
        n_top = n_universo if n_universo <= 120 else 40
    n_top = max(1, min(int(n_top), n_universo))

    top = []
    acum = 0.0
    for _, row in orden.head(n_top).iterrows():
        val = float(row["_y"])
        acum += val
        item: dict[str, Any] = {
            "item": str(row[eje_x]),
            "valor_principal": round(val, 2),
            "pct_del_total_principal": round(100.0 * val / total, 2) if total else None,
            "pct_acumulado": round(100.0 * acum / total, 2) if total else None,
        }
        for extra in (eje_y2, eje_y3):
            if extra and extra in df_resumen.columns and extra != NINGUNA:
                item[extra] = round(float(pd.to_numeric(row[extra], errors="coerce") or 0.0), 2)
        top.append(item)

    def _pct_top(k: int) -> float | None:
        if not total or n_universo <= 0:
            return None
        kk = max(1, min(int(k), n_universo))
        return round(100.0 * float(orden["_y"].head(kk).sum()) / total, 2)

    concentracion = {
        "pct_top_3": _pct_top(3),
        "pct_top_5": _pct_top(5),
        "pct_top_10": _pct_top(10),
        "pct_top_20": _pct_top(20),
        "base": "universo_filtrado_completo",
        "nota": (
            "Porcentaje = suma de los K mayores / total del universo filtrado × 100 "
            "(categoría o subcategoría completa). "
            "No usar solo las barras visibles si hay Top N en pantalla."
        ),
    }
    # También el acumulado del top enviado en la lista
    concentracion[f"pct_acumulado_top_{min(n_top, n_universo)}"] = _pct_top(n_top)
    for k_extra in (2, 4, 6, 7, 8, 15):
        concentracion[f"pct_top_{k_extra}"] = _pct_top(k_extra)

    ambito = ambito_filtro or "el ranking actual"
    out: dict[str, Any] = {
        "ok": True,
        "cruce": {
            "dimension": eje_x,
            "metrica_principal": eje_y,
            "operacion": operacion_y,
            "metrica_adicional_2": eje_y2 if eje_y2 and eje_y2 != NINGUNA else None,
            "metrica_adicional_3": eje_y3 if eje_y3 and eje_y3 != NINGUNA else None,
        },
        "ambito_filtro": ambito,
        "n_universo": n_universo,
        "n_barras": n_barras,
        "n_barras_en_pantalla": n_barras,
        "listado_completo_en_pantalla": n_barras >= n_universo,
        "total_metrica_principal": round(total, 2),
        "concentracion": concentracion,
        "concentracion_pareto_aprox": concentracion,  # alias retrocompatible
        "top": top,
    }
    if n_top >= n_universo:
        out["items_completos"] = top
    return out


def _extraer_n_primeros(pedido: str) -> int | None:
    """Compat: N en 'primeros/últimos 5', 'top 10', etc."""
    n, _cola = _extraer_consulta_ranking(pedido)
    return n


def _extraer_consulta_ranking(pedido: str) -> tuple[int | None, bool]:
    """Devuelve (N, es_cola). es_cola=True → últimos / peores / cola."""
    p = _norm(pedido)
    es_cola = any(
        k in p
        for k in (
            "ultimo",
            "ultimos",
            "ultima",
            "ultimas",
            "peor",
            "peores",
            "menores",
            "cola",
            "masbajos",
            "masbajo",
        )
    )
    m = re.search(
        r"(?:primer[oa]s|ultim[oa]s|top|mayores|menores|principales|peores)(\d{1,3})",
        p,
    )
    if m:
        return max(1, min(100, int(m.group(1)))), es_cola
    m = re.search(
        r"(\d{1,3})(?:primer|ultim|mayores|menores|principales|top|peor)",
        p,
    )
    if m:
        return max(1, min(100, int(m.group(1)))), es_cola
    palabras = {
        "dos": 2,
        "tres": 3,
        "cuatro": 4,
        "cinco": 5,
        "seis": 6,
        "siete": 7,
        "ocho": 8,
        "nueve": 9,
        "diez": 10,
        "quince": 15,
        "veinte": 20,
    }
    anclas = (
        "primer",
        "ultim",
        "top",
        "mayor",
        "menor",
        "principal",
        "peor",
        "articulo",
        "sku",
        "producto",
    )
    for pal, n in palabras.items():
        if any(
            f"{a}{pal}" in p or f"{pal}{a}" in p
            for a in ("primer", "primeros", "ultim", "ultimos", "top", "peor", "peores")
        ):
            return n, es_cola
        if pal in p and any(k in p for k in anclas):
            return n, es_cola
    return None, es_cola


def _parece_consulta_analitica(mensaje: str) -> bool:
    """Preguntas sobre el ranking actual (%, concentración) — no cambiar el gráfico."""
    p = _norm(mensaje)
    if not p:
        return False
    # "de menor a mayor" / "de mayor a menor" es orden del gráfico, no "los menores".
    pide_orden_asc_desc = any(
        k in p
        for k in (
            "menormayor",
            "mayoramenor",
            "ascendente",
            "descendente",
            "ordenasc",
            "ordendesc",
            "formaascendente",
            "formadescendente",
            "ordenadademenor",
            "ordenadademayor",
            "ordenadosdemenor",
            "ordenadosdemayor",
        )
    )
    pide_otro_grafico = any(
        k in p
        for k in (
            "muestrame",
            "mostrarme",
            "grafica",
            "graficar",
            "cambiame",
            "cambiael",
            "pasame",
            "quierover",
            "ponme",
            "armame",
            "filtrame",
            "dejamever",
            "recort",
        )
    )
    # Cruce básico: métrica por ítem/SKU/categoría (+ orden) → cambiar perfil, no consulta.
    pide_cruce_basico = (
        "por" in p
        and any(
            k in p
            for k in (
                "item",
                "items",
                "sku",
                "skus",
                "producto",
                "productos",
                "articulo",
                "articulos",
                "descripcion",
                "categoria",
                "categorias",
                "subcategoria",
                "cadauno",
                "cadaunode",
            )
        )
        and any(
            k in p
            for k in (
                "utilidad",
                "margen",
                "venta",
                "invent",
                "costo",
                "rotacion",
                "mes",
            )
        )
    )
    ancla_actual = any(
        k in p
        for k in (
            "estos",
            "estas",
            "actual",
            "pantalla",
            "grafico",
            "ranking",
            "delosprimeros",
            "delprimer",
            "delosultimos",
            "enpantalla",
        )
    )
    habla_concentracion = any(
        k in p
        for k in (
            "porcentaje",
            "porcient",
            "particip",
            "represent",
            "concentr",
            "acumulad",
            "aportan",
            "aporta",
            "deltotal",
            "sobreetotal",
            "cuantorepresent",
            "querepresent",
            "cuantosuman",
            "cuantogener",
        )
    )
    if pide_otro_grafico and not ancla_actual:
        if habla_concentracion and (
            "primer" in p or "top" in p or "ultim" in p or "peor" in p
        ):
            return True
        return False
    tiene_cabeza_cola = (
        "primer" in p or "top" in p or "ultim" in p or "peor" in p
    )
    # Cruce "utilidad por ítem" / orden asc-desc sin lenguaje de % → cambiar gráfico
    # (incluye "top 10 de utilidad por SKU", que no es pregunta de concentración).
    if (
        (pide_orden_asc_desc or pide_cruce_basico)
        and not habla_concentracion
        and "cuanto" not in p
        and "analiz" not in p
    ):
        return False
    tiene_ranking = tiene_cabeza_cola or (
        "menor" in p and not pide_orden_asc_desc
    )
    if tiene_ranking and (
        habla_concentracion
        or "analiz" in p
        or "total" in p
        or "venta" in p
        or "invent" in p
        or "margen" in p
        or "utilidad" in p
        or "cuanto" in p
    ):
        return True
    if any(k in p for k in _CONSULTA_ANALITICA_KEYS) and not pide_otro_grafico:
        if (
            pide_orden_asc_desc or pide_cruce_basico
        ) and not habla_concentracion and "cuanto" not in p:
            return False
        if any(
            k in p
            for k in (
                "primeros",
                "primeras",
                "losprimeros",
                "lasprimeras",
                "ultimos",
                "ultimas",
                "losultimos",
            )
        ) and not (
            habla_concentracion
            or "analiz" in p
            or "total" in p
            or "porcent" in p
            or "cola" in p
            or "cabeza" in p
            or "cuanto" in p
        ):
            return False
        return True
    return False


def _columna_metrica_consulta(df: pd.DataFrame, mensaje: str) -> str | None:
    """Métrica para %: la del pedido, la del gráfico actual, o ventas totales."""
    mets = catalogo_columnas(df)["metricas"]
    pedido_n = _norm(mensaje)
    if re.search(r"venta(?!rio)", pedido_n):
        hit = _resolver_columna("ventas totales", mets)
        if hit:
            return hit
    if any(k in pedido_n for k in ("utilidad", "margen", "brut")):
        hit = _resolver_columna("margen bruto total", mets) or _resolver_columna(
            "margen utilidad ventas", mets
        )
        if hit:
            return hit
    if "invent" in pedido_n:
        hit = _resolver_columna("valor inventario promedio", mets)
        if hit:
            return hit
    actual = st.session_state.get("lri_man_eje_y")
    if actual and actual in df.columns and pd.api.types.is_numeric_dtype(df[actual]):
        return str(actual)
    return _resolver_columna("ventas totales", mets) or (mets[0] if mets else None)


def _resolver_ambito_concentracion(
    mensaje: str,
    df: pd.DataFrame,
) -> tuple[str | None, str | None, str]:
    """Decide categoría/subcategoría del denominador del %.

    Prioridad:
    1) Valor nombrado en la pregunta (match más largo).
    2) Si dicen «subcategoría …» y hay drill de subcategoría en pantalla cuya
       etiqueta contiene el nombre dicho (p. ej. «alimentos» → «Alimentos Secos»),
       usar la subcategoría de pantalla.
    3) Drill actual de sesión (subcategoría o categoría).
    """
    msg_cat, msg_sub = _resolver_filtros_segmento(mensaje, df)
    ses_cat = st.session_state.get("drill_down_categoria")
    ses_sub = st.session_state.get("drill_down_subcategoria")
    if isinstance(ses_cat, str):
        ses_cat = ses_cat.strip() or None
    else:
        ses_cat = None
    if isinstance(ses_sub, str):
        ses_sub = ses_sub.strip() or None
    else:
        ses_sub = None

    pedido_n = _norm(mensaje)
    habla_sub = "subcateg" in pedido_n or "estasub" in pedido_n or "lasubcateg" in pedido_n

    if msg_sub:
        return None, msg_sub, f"la subcategoría {msg_sub}"
    if msg_cat and ses_sub and habla_sub:
        # «subcategoría de alimentos» con filtro activo Alimentos Secos → quedarse en Secos
        if _norm(msg_cat) in _norm(ses_sub):
            return None, ses_sub, f"la subcategoría {ses_sub}"
    if msg_cat:
        return msg_cat, None, f"la categoría {msg_cat}"
    if ses_sub:
        return None, ses_sub, f"la subcategoría {ses_sub}"
    if ses_cat:
        return ses_cat, None, f"la categoría {ses_cat}"
    return None, None, "el universo completo de artículos"


def _agregar_ranking_articulos(
    df: pd.DataFrame,
    *,
    eje_y: str,
    filtro_categoria: str | None = None,
    filtro_subcategoria: str | None = None,
) -> pd.DataFrame:
    """Ranking por descripción (SKU) dentro del filtro; total = suma del segmento."""
    out = df.copy()
    if filtro_categoria and "categoria" in out.columns:
        out = out[out["categoria"].astype(str).str.strip() == str(filtro_categoria).strip()]
    if filtro_subcategoria and "subcategoria" in out.columns:
        out = out[
            out["subcategoria"].astype(str).str.strip() == str(filtro_subcategoria).strip()
        ]
    if out.empty or eje_y not in out.columns:
        return pd.DataFrame()
    eje_x = "descripcion" if "descripcion" in out.columns else (
        "codigo" if "codigo" in out.columns else None
    )
    if not eje_x:
        return pd.DataFrame()
    t = out[[eje_x, eje_y]].copy()
    t[eje_y] = pd.to_numeric(t[eje_y], errors="coerce").fillna(0.0)
    return t.groupby(eje_x, as_index=False)[eje_y].sum()


def _hechos_concentracion_para_pregunta(
    mensaje: str,
    df: pd.DataFrame,
) -> dict[str, Any]:
    """Recalcula hechos del % sobre el segmento pedido (no el universo global)."""
    eje_y = _columna_metrica_consulta(df, mensaje)
    if not eje_y:
        return {"ok": False, "motivo": "Sin métrica"}
    cat, sub, ambito = _resolver_ambito_concentracion(mensaje, df)
    ranking = _agregar_ranking_articulos(
        df,
        eje_y=eje_y,
        filtro_categoria=cat,
        filtro_subcategoria=sub,
    )
    if ranking.empty:
        return {"ok": False, "motivo": f"Sin datos en {ambito}"}
    eje_x = "descripcion" if "descripcion" in ranking.columns else ranking.columns[0]
    n_pantalla = None
    hechos_prev = st.session_state.get("prf2_chatgpt_hechos")
    if isinstance(hechos_prev, dict) and hechos_prev.get("ok"):
        n_pantalla = hechos_prev.get("n_barras_en_pantalla") or hechos_prev.get("n_barras")
    return hechos_perfil_resumen(
        ranking,
        eje_x=eje_x,
        eje_y=eje_y,
        operacion_y="Suma",
        ambito_filtro=ambito,
        n_en_pantalla=n_pantalla,
        n_top=max(1, len(ranking)),
    )


def _items_ranking_hechos(hechos: dict[str, Any]) -> list[dict[str, Any]]:
    """Lista completa (o amplia) ordenada de mayor a menor."""
    items = hechos.get("items_completos") or hechos.get("top") or []
    return [it for it in items if isinstance(it, dict)]


def _seleccion_ranking(
    items: list[dict[str, Any]], n: int, *, cola: bool
) -> list[dict[str, Any]]:
    if not items or n <= 0:
        return []
    n_eff = min(n, len(items))
    if cola:
        return list(reversed(items[-n_eff:]))
    return items[:n_eff]


def _respuesta_concentracion_local(mensaje: str, hechos: dict[str, Any]) -> str | None:
    """% y detalle de los N primeros/últimos sobre el segmento (nombra todos)."""
    if not hechos or not hechos.get("ok"):
        return None
    n, es_cola = _extraer_consulta_ranking(mensaje)
    if n is None:
        if not _parece_consulta_analitica(mensaje):
            return None
        p = _norm(mensaje)
        if "porcent" in p or "represent" in p or "particip" in p or "cuanto" in p:
            n = 5
            es_cola = any(k in p for k in ("ultim", "peor", "cola", "menor"))
        else:
            return None

    items = _items_ranking_hechos(hechos)
    if not items:
        return None
    total = hechos.get("total_metrica_principal")
    metrica = (hechos.get("cruce") or {}).get("metrica_principal") or "la métrica"
    dim = (hechos.get("cruce") or {}).get("dimension") or "ítems"
    dim_lbl = "artículos" if _norm(str(dim)) in ("descripcion", "codigo") else str(dim)
    n_universo = int(hechos.get("n_universo") or len(items) or 0)
    seleccion = _seleccion_ranking(items, n, cola=es_cola)
    n_eff = len(seleccion)
    if n_eff <= 0:
        return None

    suma_val = 0.0
    suma_pct = 0.0
    filas_tabla: list[dict[str, Any]] = []
    detalle_oral: list[str] = []
    for i, it in enumerate(seleccion, start=1):
        nombre = str(it.get("item") or "").strip() or f"Ítem {i}"
        val = it.get("valor_principal")
        try:
            val_f = float(val) if val is not None else 0.0
        except (TypeError, ValueError):
            val_f = 0.0
        pi = it.get("pct_del_total_principal")
        if pi is None and isinstance(total, (int, float)) and total:
            pi = round(100.0 * val_f / float(total), 2)
        try:
            pi_f = float(pi) if pi is not None else 0.0
        except (TypeError, ValueError):
            pi_f = 0.0
        suma_val += val_f
        suma_pct += pi_f
        filas_tabla.append(
            {
                "#": i,
                "Artículo": nombre,
                "Valor": round(val_f, 2),
                "% del segmento": round(pi_f, 2),
            }
        )
        detalle_oral.append(
            f"{i}) {nombre}: {pi_f:.2f}%"
            + (f" ({val_f:,.0f})" if val_f else "")
        )

    pct = round(suma_pct, 2)
    ambito = hechos.get("ambito_filtro") or "el ranking actual"
    etiqueta = "últimos" if es_cola else "primeros"

    st.session_state["prf2_consulta_detalle"] = {
        "titulo": f"{etiqueta.capitalize()} {n_eff} · {ambito}",
        "filas": filas_tabla,
        "resumen": {
            "n": n_eff,
            "pct": pct,
            "suma_valor": round(suma_val, 2),
            "total_segmento": total,
            "metrica": metrica,
            "ambito": ambito,
            "cola": es_cola,
            "n_universo": n_universo,
        },
    }

    cuerpo = (
        f"Sobre {ambito} ({n_universo} {dim_lbl} en total), los {etiqueta} {n_eff} "
        f"concentran el {pct}% de {metrica}"
    )
    if isinstance(total, (int, float)):
        cuerpo += f" (segmento {total:,.0f}; suma de estos {n_eff}: {suma_val:,.0f})"
    cuerpo += ". Detalle: " + "; ".join(detalle_oral) + "."
    return cuerpo


def generar_resumen_hablado(hechos: dict[str, Any], *, api_key: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=MODELO_TEXTO,
        temperature=0.3,
        max_tokens=220,
        messages=[
            {"role": "system", "content": _SYSTEM_NARRAR},
            {
                "role": "user",
                "content": f"Redacta el resumen oral con este JSON:\n{json.dumps(hechos, ensure_ascii=False)}",
            },
        ],
    )
    texto = (resp.choices[0].message.content or "").strip()
    if not texto:
        raise RuntimeError("ChatGPT devolvió un texto vacío.")
    return texto


def sintetizar_voz_openai(texto: str, *, api_key: str, rapido: bool = False) -> bytes:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    if rapido:
        audio = client.audio.speech.create(
            model="tts-1",
            voice="fable",
            input=texto,
            response_format="mp3",
        )
        return audio.content
    try:
        with client.audio.speech.with_streaming_response.create(
            model=MODELO_TTS,
            voice=VOZ_TTS,
            input=texto,
            response_format="mp3",
            instructions=(
                "Habla en español latinoamericano con voz masculina Fable: "
                "tono calmado y profesional. Resume; no apresures."
            ),
        ) as response:
            return response.read()
    except Exception:
        audio = client.audio.speech.create(
            model="tts-1-hd",
            voice="fable",
            input=texto,
            response_format="mp3",
        )
        return audio.content


def mics_bloqueados() -> bool:
    """True mientras solo se debe narrar (no reinterpretar voz ni cambiar ejes)."""
    return bool(
        st.session_state.get("prf2_ignorar_mics")
        or st.session_state.get("prf2_chatgpt_forzar_narracion")
    )


def activar_solo_narracion() -> None:
    """Congela el gráfico actual y pide narración en el próximo render."""
    st.session_state["prf2_chatgpt_forzar_narracion"] = True
    st.session_state["prf2_ignorar_mics"] = True
    st.session_state.pop("prf2_post_narrar_refresh_done", None)
    # Evita que el mic reenvíe el último audio y reinterprete columnas.
    st.session_state["lri_last_audio_hash"] = st.session_state.get("lri_last_audio_hash") or "narrar"
    st.session_state["prf2_chat_last_audio_hash"] = (
        st.session_state.get("prf2_chat_last_audio_hash") or "narrar"
    )


def _parece_pedido_narrar(mensaje: str) -> bool:
    msg_n = _norm(mensaje)
    if not any(k in msg_n for k in _NARRAR_KEYS):
        return False
    # Concentración de los N primeros → consulta (no narrar ni recortar el gráfico).
    if _parece_consulta_analitica(mensaje):
        return False
    # Si también pide un cruce de datos o mostrar gráfico, priorizar perfilar.
    if _parece_cruce_de_datos(mensaje) or any(k in msg_n for k in _CAMBIAR_KEYS):
        return False
    return True


def _parece_cruce_de_datos(mensaje: str) -> bool:
    """Detecta pedidos del tipo ventas/inventario por SKU, categoría, etc."""
    if _parece_consulta_analitica(mensaje):
        return False
    msg_n = _norm(mensaje)
    dims = (
        "sku",
        "articulo",
        "producto",
        "item",
        "codigo",
        "descripcion",
        "subcateg",
        "categ",
        "proveedor",
        "clase",
    )
    mets = (
        "ventas",
        "venta",
        "invent",
        "utilidad",
        "margen",
        "demanda",
        "rotacion",
        "gmroi",
        "evai",
    )
    if any(d in msg_n for d in dims) and any(m in msg_n for m in mets):
        if "invent" in msg_n or re.search(r"venta(?!rio)", msg_n) or any(
            m in msg_n for m in ("utilidad", "margen", "demanda", "rotacion", "gmroi", "evai")
        ):
            return True
    if "por" in msg_n and (
        "invent" in msg_n
        or re.search(r"venta(?!rio)", msg_n)
        or any(m in msg_n for m in ("utilidad", "margen", "demanda", "rotacion", "gmroi", "evai"))
    ):
        return True
    return False


def _parece_saludo_o_charla(mensaje: str) -> bool:
    """Saludos / ‘cómo estás’ / ‘me escuchas’: nunca deben cambiar el gráfico."""
    msg_n = _norm(mensaje)
    if not msg_n:
        return False
    if _parece_consulta_analitica(mensaje):
        return False
    if any(k in msg_n for k in _CAMBIAR_KEYS):
        return False
    if any(
        k in msg_n
        for k in (
            "venta",
            "invent",
            "util",
            "margen",
            "categ",
            "subcateg",
            "sku",
            "demanda",
            "perfil",
            "pareto",
            "porcent",
        )
    ):
        return False
    if any(k in msg_n for k in _SALUDO_KEYS):
        return True
    if len(msg_n) <= 24 and not any(k in msg_n for k in _NARRAR_KEYS):
        return True
    return False


def clasificar_intento_usuario(mensaje: str, *, api_key: str) -> dict[str, Any]:
    # Saludo / charla → solo respuesta oral, jamás cambiar ejes.
    if _parece_saludo_o_charla(mensaje):
        return {
            "accion": "consultar",
            "pedido_perfil": None,
            "motivo": "local_saludo",
        }
    # Undo / redo del gráfico (antes que cualquier otra cosa).
    if perfil_patch.parece_deshacer(mensaje):
        return {"accion": "deshacer", "pedido_perfil": None, "motivo": "local_deshacer"}
    if perfil_patch.parece_rehacer(mensaje):
        return {"accion": "rehacer", "pedido_perfil": None, "motivo": "local_rehacer"}
    # Sustitución parcial / Top N sobre el gráfico actual.
    if perfil_patch.parece_parche_parcial(mensaje) or perfil_patch.parece_solo_top_n(mensaje):
        return {
            "accion": "parche_perfil",
            "pedido_perfil": mensaje.strip(),
            "motivo": "local_parche",
        }
    # % / concentración del ranking actual → consultar (antes que cruce).
    if _parece_consulta_analitica(mensaje):
        return {
            "accion": "consultar",
            "pedido_perfil": None,
            "motivo": "local_consulta_analitica",
        }
    # Cruce explícito (ventas por SKU, etc.) → cambiar perfil aunque digan “analiza”.
    if _parece_cruce_de_datos(mensaje) or any(
        k in _norm(mensaje) for k in _CAMBIAR_KEYS
    ):
        # “cambia X por Y” ya se capturó como parche; aquí es reconstrucción.
        if perfil_patch.parece_parche_parcial(mensaje):
            return {
                "accion": "parche_perfil",
                "pedido_perfil": mensaje.strip(),
                "motivo": "local_parche_vs_cruce",
            }
        return {
            "accion": "cambiar_perfil",
            "pedido_perfil": mensaje.strip(),
            "motivo": "local_cruce",
        }
    # Rápido y seguro: análisis del gráfico actual → no tocar ejes.
    if _parece_pedido_narrar(mensaje):
        return {
            "accion": "narrar_analisis",
            "pedido_perfil": None,
            "motivo": "local_narrar",
        }

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=MODELO_TEXTO,
        temperature=0.0,
        max_tokens=120,
        messages=[
            {"role": "system", "content": _SYSTEM_INTENTO},
            {"role": "user", "content": mensaje.strip()},
        ],
    )
    raw = (resp.choices[0].message.content or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.M).strip()
    validas = (
        "cambiar_perfil",
        "parche_perfil",
        "deshacer",
        "rehacer",
        "consultar",
        "narrar_analisis",
    )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"accion": "consultar", "pedido_perfil": None, "motivo": "fallback"}
    if not isinstance(data, dict):
        return {"accion": "consultar", "pedido_perfil": None, "motivo": "fallback"}
    accion = data.get("accion") if data.get("accion") in validas else "consultar"
    if accion == "cambiar_perfil" and _parece_saludo_o_charla(mensaje):
        accion = "consultar"
    if accion == "cambiar_perfil" and _parece_consulta_analitica(mensaje):
        accion = "consultar"
    if accion == "cambiar_perfil" and perfil_patch.parece_parche_parcial(mensaje):
        accion = "parche_perfil"
    if accion == "narrar_analisis" and _parece_cruce_de_datos(mensaje):
        accion = "cambiar_perfil"
    return {
        "accion": accion,
        "pedido_perfil": data.get("pedido_perfil") or mensaje.strip(),
        "motivo": str(data.get("motivo") or ""),
    }


def _responder_y_reproducir(
    texto: str,
    *,
    api_key: str | None,
    pedido: str | None = None,
) -> None:
    hist = _historial_conversacion()
    if pedido:
        hist.append({"role": "user", "content": pedido.strip()})
    hist.append({"role": "assistant", "content": texto})
    st.session_state["prf2_chat_historial"] = hist[-_MAX_TURNOS_HISTORIAL * 2 :]
    st.session_state["prf2_chat_activa"] = True
    if api_key:
        try:
            st.session_state["prf2_chat_reply_audio"] = sintetizar_voz_openai(
                texto, api_key=api_key, rapido=True
            )
        except Exception:
            pass


def _manejar_parche_perfil(
    mensaje: str,
    df: pd.DataFrame,
    *,
    api_key: str | None,
    aplicar_config: Callable[[dict], None],
) -> None:
    """Valida y aplica un parche parcial (o pregunta si hay ambigüedad)."""
    intent = perfil_patch.interpretar_parche_local(mensaje, df)
    if intent.get("accion") in ("deshacer", "rehacer"):
        resultado = perfil_patch.aplicar_parche_validado(
            intent, aplicar_config=aplicar_config
        )
        _responder_y_reproducir(
            str(resultado.get("mensaje") or "Listo."),
            api_key=api_key,
            pedido=mensaje,
        )
        registrar_evento_chatgpt(
            "parche" if resultado.get("ok") else "parche_fallido",
            pedido=mensaje.strip(),
            intent=intent,
            resultado=resultado,
        )
        return

    if not intent.get("ok"):
        pregunta = str(
            intent.get("pregunta")
            or "¿Qué variable quiere sustituir y por cuál? No modifiqué el gráfico."
        )
        _responder_y_reproducir(pregunta, api_key=api_key, pedido=mensaje)
        registrar_evento_chatgpt(
            "parche_ambiguo",
            pedido=mensaje.strip(),
            intent=intent,
        )
        return

    resultado = perfil_patch.aplicar_parche_validado(
        intent, aplicar_config=aplicar_config
    )
    _responder_y_reproducir(
        str(resultado.get("mensaje") or "Listo."),
        api_key=api_key,
        pedido=mensaje,
    )
    registrar_evento_chatgpt(
        "parche_aplicado" if resultado.get("ok") else "parche_fallido",
        pedido=mensaje.strip(),
        intent=intent,
        config=resultado.get("config"),
    )


def _historial_conversacion() -> list[dict[str, str]]:
    hist = st.session_state.get("prf2_chat_historial")
    if not isinstance(hist, list):
        hist = []
        st.session_state["prf2_chat_historial"] = hist
    return hist


def _guardar_hechos_perfil(hechos: dict[str, Any]) -> None:
    if hechos.get("ok"):
        st.session_state["prf2_chatgpt_hechos"] = hechos


def _contexto_datos_para_ia(df: pd.DataFrame) -> dict[str, Any]:
    """Permiso de lectura: matriz completa + perfil en pantalla."""
    cat = catalogo_columnas(df)
    return {
        "fuente": "Excel cargado en sesión (hoja data)",
        "n_filas": int(len(df)),
        "n_columnas": int(len(df.columns)),
        "MATRIZ_PERFILADO": cat["matriz"],
        "perfil_en_pantalla": st.session_state.get("prf2_chatgpt_hechos") or {"ok": False},
        "ejes_actuales": {
            "eje_x": st.session_state.get("lri_man_eje_x"),
            "eje_y": st.session_state.get("lri_man_eje_y"),
            "eje_y2": st.session_state.get("lri_man_eje_y2"),
            "eje_y3": st.session_state.get("lri_man_eje_y3"),
            "filtro_categoria": st.session_state.get("drill_down_categoria"),
            "filtro_subcategoria": st.session_state.get("drill_down_subcategoria"),
        },
    }


def responder_turno_conversacion(
    mensaje_usuario: str,
    df: pd.DataFrame,
    *,
    api_key: str,
) -> str:
    from openai import OpenAI

    # Recalcular % sobre el segmento nombrado / drill actual (nunca el universo global
    # si la pregunta ancla categoría o subcategoría).
    hechos_consulta = _hechos_concentracion_para_pregunta(mensaje_usuario, df)
    if hechos_consulta.get("ok"):
        local = _respuesta_concentracion_local(mensaje_usuario, hechos_consulta)
        if local:
            hist = _historial_conversacion()
            hist.append({"role": "user", "content": mensaje_usuario.strip()})
            hist.append({"role": "assistant", "content": local})
            st.session_state["prf2_chat_historial"] = hist[-_MAX_TURNOS_HISTORIAL * 2 :]
            st.session_state["prf2_chatgpt_hechos_consulta"] = hechos_consulta
            return local

    hechos = st.session_state.get("prf2_chatgpt_hechos") or {}
    local = _respuesta_concentracion_local(
        mensaje_usuario, hechos if isinstance(hechos, dict) else {}
    )
    if local:
        hist = _historial_conversacion()
        hist.append({"role": "user", "content": mensaje_usuario.strip()})
        hist.append({"role": "assistant", "content": local})
        st.session_state["prf2_chat_historial"] = hist[-_MAX_TURNOS_HISTORIAL * 2 :]
        return local

    ctx = _contexto_datos_para_ia(df)
    if hechos_consulta.get("ok"):
        ctx["concentracion_segmento_pregunta"] = hechos_consulta
        ctx["nota_concentracion"] = (
            "Si preguntan % de los primeros N de una categoría/subcategoría, "
            "usa concentracion_segmento_pregunta (n_universo y total de ESE segmento). "
            "No uses el total de todo el Excel."
        )
    hist = _historial_conversacion()
    messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM_CONVERSACION},
        {
            "role": "system",
            "content": (
                "Contexto de datos autorizados (JSON):\n"
                + json.dumps(ctx, ensure_ascii=False)
            ),
        },
    ]
    for turn in hist[-_MAX_TURNOS_HISTORIAL:]:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": mensaje_usuario.strip()})

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=MODELO_TEXTO,
        temperature=0.35,
        messages=messages,
    )
    texto = (resp.choices[0].message.content or "").strip()
    if not texto:
        raise RuntimeError("ChatGPT no respondió.")
    hist.append({"role": "user", "content": mensaje_usuario.strip()})
    hist.append({"role": "assistant", "content": texto})
    st.session_state["prf2_chat_historial"] = hist[-_MAX_TURNOS_HISTORIAL * 2 :]
    return texto


def _transcribir_audio(audio_bytes: bytes) -> str:
    r = sr.Recognizer()
    with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
        r.adjust_for_ambient_noise(source, duration=0.2)
        audio_data = r.record(source)
    return r.recognize_google(audio_data, language="es-CR")


def _reproducir_audio_sidebar(audio: bytes, *, autoplay: bool = True) -> None:
    try:
        if autoplay:
            st.sidebar.audio(audio, format="audio/mp3", autoplay=True)
        else:
            st.sidebar.audio(audio, format="audio/mp3")
    except TypeError:
        st.sidebar.audio(audio, format="audio/mp3")


def _limpiar_pendientes_ejes_perfil() -> None:
    """Evita que un cruce ChatGPT viejo pise un cambio manual en el próximo render."""
    for k in (
        "_lri_pending_man_eje_x",
        "_lri_pending_man_eje_y",
        "_lri_pending_man_eje_y2",
        "_lri_pending_man_eje_y3",
    ):
        st.session_state.pop(k, None)


def liberar_perfil_bloqueado() -> None:
    """Quita el congelamiento de ChatGPT para que los selectores manuales manden."""
    st.session_state.pop("prf2_perfil_bloqueado", None)
    st.session_state.pop("prf2_origen_perfil", None)
    # No resetear orden/ABC/ejes: el usuario acaba de elegirlos a mano.
    _limpiar_pendientes_ejes_perfil()


def _snapshot_perfil_ui() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in _CLAVES_PERFIL_UI:
        if k in st.session_state:
            out[k] = st.session_state.get(k)
    out["drill_down_categoria"] = st.session_state.get("drill_down_categoria")
    out["drill_down_subcategoria"] = st.session_state.get("drill_down_subcategoria")
    out["prf2_vista_abc_articulos"] = bool(st.session_state.get("prf2_vista_abc_articulos"))
    return out


def registrar_evento_chatgpt(evento: str, **payload: Any) -> None:
    """Telemetría local (JSONL) para mejorar heurísticas: confirmaciones y correcciones."""
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        fila = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "evento": evento,
            **{k: v for k, v in payload.items() if v is not None},
        }
        with open(_LOG_EVENTOS, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(fila, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


def _diff_perfiles(antes: dict[str, Any], despues: dict[str, Any]) -> dict[str, Any]:
    claves = set(antes) | set(despues)
    diff: dict[str, Any] = {}
    for k in sorted(claves):
        a, b = antes.get(k), despues.get(k)
        if a != b:
            diff[k] = {"chatgpt": a, "manual": b}
    return diff


def _confirmar_antes_de_aplicar() -> bool:
    return bool(st.session_state.get("prf2_chatgpt_confirmar_antes", True))


def texto_orden_perfil(orden_ascendente: Any) -> str:
    """Misma semántica que el gráfico: True=menor→mayor, False=mayor→menor."""
    return "de menor a mayor" if bool(orden_ascendente) else "de mayor a menor"


def resumen_legible_perfil(config: dict[str, Any]) -> str:
    """Texto corto para la tarjeta de confirmación."""
    ex = config.get("lri_man_eje_x") or "?"
    ey = config.get("lri_man_eje_y") or "?"
    op = config.get("lri_man_operacion_y") or config.get("lri_man_operacion") or "Suma"
    top = config.get("lri_man_top_n")
    if top is None:
        top_txt = "Top N actual"
    elif int(top) == 0:
        top_txt = "todos"
    else:
        top_txt = f"Top {int(top)}"
    orden = texto_orden_perfil(config.get("lri_man_orden_ascendente"))
    partes = [f"**{ey}** ({op}) por **{ex}**", top_txt, orden]
    ey2 = config.get("lri_man_eje_y2")
    if ey2 and ey2 != NINGUNA:
        partes.insert(1, f"+ {ey2}")
    ey3 = config.get("lri_man_eje_y3")
    if ey3 and ey3 != NINGUNA:
        partes.insert(2, f"+ {ey3}")
    if config.get("prf2_vista_abc_articulos"):
        partes.append("vista ABC (scatter + tabla)")
    drill = config.get("drill_down_categoria")
    if drill:
        partes.append(f"filtro cat: {drill}")
    drill_sub = config.get("drill_down_subcategoria")
    if drill_sub:
        partes.append(f"filtro sub: {drill_sub}")
    return " · ".join(partes)


def frase_propuesta_perfil(config: dict[str, Any]) -> str:
    """Audio/texto pidiendo confirmación (no afirma que ya se aplicó)."""
    ex = config.get("lri_man_eje_x")
    ey = config.get("lri_man_eje_y")
    ey2 = config.get("lri_man_eje_y2")
    top = config.get("lri_man_top_n")
    orden = texto_orden_perfil(config.get("lri_man_orden_ascendente"))
    if top == 0:
        alcance = "todos los ítems"
    elif isinstance(top, int) and top > 0:
        alcance = f"top {top}"
    else:
        alcance = "el recorte actual"
    filtro = config.get("drill_down_subcategoria") or config.get("drill_down_categoria")
    en_filtro = f" en {filtro}" if filtro else ""
    if config.get("prf2_vista_abc_articulos"):
        return (
            f"Propongo la vista ABC de artículos con {ey or 'la métrica'}, {alcance}{en_filtro}. "
            "¿Lo aplico?"
        )
    ey3 = config.get("lri_man_eje_y3")
    partes_y = [ey] if ey else []
    if ey2 and ey2 != NINGUNA:
        partes_y.append(str(ey2))
    if ey3 and ey3 != NINGUNA:
        partes_y.append(str(ey3))
    if ex and partes_y:
        if len(partes_y) == 1:
            y_txt = partes_y[0]
        else:
            y_txt = ", ".join(partes_y[:-1]) + f" y {partes_y[-1]}"
        return f"Propongo {y_txt} por {ex}{en_filtro}, {alcance}, {orden}. ¿Lo aplico?"
    return "Propongo un nuevo perfil con tus datos. ¿Lo aplico?"


def _proponer_o_aplicar_perfil(
    pedido: str,
    config: dict[str, Any],
    *,
    api_key: str | None,
    aplicar_config: Callable[[dict], None],
    origen: str = "chatgpt",
) -> None:
    """Si hay confirmación activa, deja pendiente; si no, aplica de inmediato."""
    config = completar_config_reemplazo_perfil(config)
    st.session_state["prf2_chatgpt_ultimo_pedido"] = pedido.strip()

    if _confirmar_antes_de_aplicar():
        frase = frase_propuesta_perfil(config)
        audio = None
        if api_key:
            try:
                audio = sintetizar_voz_openai(frase, api_key=api_key, rapido=True)
            except Exception:
                audio = None
        st.session_state["prf2_chatgpt_pendiente"] = {
            "pedido": pedido.strip(),
            "config": config,
            "frase": frase,
            "origen": origen,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        registrar_evento_chatgpt(
            "propuesto",
            pedido=pedido.strip(),
            config=config,
            origen=origen,
        )
        hist = _historial_conversacion()
        hist.append({"role": "user", "content": pedido.strip()})
        hist.append({"role": "assistant", "content": frase})
        st.session_state["prf2_chat_historial"] = hist[-_MAX_TURNOS_HISTORIAL * 2 :]
        if audio:
            st.session_state["prf2_chat_reply_audio"] = audio
        st.session_state["prf2_chat_activa"] = True
        return

    _aplicar_perfil_confirmado(config, pedido=pedido, aplicar_config=aplicar_config, origen=origen)
    if api_key:
        try:
            st.session_state["prf2_chatgpt_confirm_audio"] = sintetizar_voz_openai(
                frase_confirmacion_perfil(config), api_key=api_key, rapido=True
            )
        except Exception:
            pass


def _aplicar_perfil_confirmado(
    config: dict[str, Any],
    *,
    pedido: str,
    aplicar_config: Callable[[dict], None],
    origen: str = "chatgpt",
    omitir_turno_usuario_en_hist: bool = False,
) -> None:
    # Historial: guardar gráfico vigente antes de una reconstrucción completa.
    try:
        perfil_patch.push_undo_antes_de_cambiar()
    except Exception:
        pass
    config = completar_config_reemplazo_perfil(config)
    # Voz/ChatGPT pisa el manual: limpia pendientes viejos y bloquea el nuevo cruce.
    _limpiar_pendientes_ejes_perfil()
    _bloquear_perfil_desde_config(config)
    frase = frase_confirmacion_perfil(config)
    hist = _historial_conversacion()
    if not omitir_turno_usuario_en_hist:
        hist.append({"role": "user", "content": pedido.strip()})
    hist.append({"role": "assistant", "content": frase})
    st.session_state["prf2_chat_historial"] = hist[-_MAX_TURNOS_HISTORIAL * 2 :]
    st.session_state["prf2_chat_activa"] = True
    st.session_state["prf2_chatgpt_ultimo_pedido"] = pedido.strip()
    st.session_state["prf2_chatgpt_config_aplicada"] = {
        k: config.get(k) for k in list(_CLAVES_PERFIL_UI) + [
            "drill_down_categoria",
            "drill_down_subcategoria",
            "prf2_vista_abc_articulos",
        ]
    }
    aplicar_config(config)
    registrar_evento_chatgpt(
        "aplicado",
        pedido=pedido.strip(),
        config=config,
        origen=origen,
    )


def render_confirmacion_perfil_pendiente(
    *,
    aplicar_config: Callable[[dict], None],
) -> None:
    """Tarjeta Sí/No en sidebar cuando ChatGPT propuso un cruce."""
    pend = st.session_state.get("prf2_chatgpt_pendiente")
    if not isinstance(pend, dict) or not pend.get("config"):
        return

    config = pend["config"]
    pedido = str(pend.get("pedido") or "")
    st.sidebar.markdown("---")
    st.sidebar.markdown("##### ✅ Confirmar perfil ChatGPT")
    expl = str(config.get("prf2_chatgpt_explicacion") or "").strip()
    if expl:
        st.sidebar.caption(expl)
    st.sidebar.markdown(resumen_legible_perfil(config))
    if pedido:
        st.sidebar.caption(f'Pedido: *"{pedido}"*')

    c1, c2 = st.sidebar.columns(2)
    with c1:
        if st.button("✅ Aplicar", type="primary", use_container_width=True, key="prf2_chatgpt_ok"):
            st.session_state.pop("prf2_chatgpt_pendiente", None)
            registrar_evento_chatgpt("confirmado", pedido=pedido, config=config)
            _aplicar_perfil_confirmado(
                config,
                pedido=pedido,
                aplicar_config=aplicar_config,
                origen="confirmacion",
                omitir_turno_usuario_en_hist=True,
            )
            api_key = obtener_api_key()
            if api_key:
                try:
                    audio = sintetizar_voz_openai(
                        frase_confirmacion_perfil(config), api_key=api_key, rapido=True
                    )
                    st.session_state["prf2_chatgpt_confirm_audio"] = audio
                except Exception:
                    pass
            st.rerun()
    with c2:
        if st.button("❌ Descartar", use_container_width=True, key="prf2_chatgpt_no"):
            registrar_evento_chatgpt("descartado", pedido=pedido, config=config)
            st.session_state.pop("prf2_chatgpt_pendiente", None)
            st.rerun()


def _usuario_cambio_selectores_vs_bloqueo(bloqueado: dict[str, Any]) -> bool:
    """True si la UI ya trae valores distintos al último cruce de ChatGPT (cambio manual)."""
    for k in _CLAVES_PERFIL_UI:
        if k not in bloqueado:
            continue
        if k not in st.session_state:
            continue
        actual = st.session_state.get(k)
        ref = bloqueado.get(k)
        if actual is None and ref is None:
            continue
        if actual != ref:
            return True
    # Drill-down manual (categoría o subcategoría)
    if "drill_down_categoria" in bloqueado:
        if st.session_state.get("drill_down_categoria") != bloqueado.get("drill_down_categoria"):
            if "prev_drill_down_categoria" in st.session_state:
                return True
    if "drill_down_subcategoria" in bloqueado:
        if st.session_state.get("drill_down_subcategoria") != bloqueado.get(
            "drill_down_subcategoria"
        ):
            return True
    return False


def completar_config_reemplazo_perfil(config: dict[str, Any]) -> dict[str, Any]:
    """Completa un reemplazo FULL de perfil (voz/ChatGPT) sin leftovers del manual.

    Si el dict es un parche parcial (sin ambos ejes), no inventa Y2/Top N/filtros.
    """
    out = dict(config)
    es_reemplazo_completo = bool(out.get("lri_man_eje_x")) and bool(out.get("lri_man_eje_y"))
    if not es_reemplazo_completo:
        return out

    out["lri_man_eje_y2"] = out.get("lri_man_eje_y2") or NINGUNA
    out["lri_man_eje_y3"] = out.get("lri_man_eje_y3") or NINGUNA
    if "lri_man_operacion_y" in out and "lri_man_operacion" not in out:
        out["lri_man_operacion"] = out["lri_man_operacion_y"]
    # Siempre definir drills (None = quitar filtro manual previo).
    if "drill_down_categoria" not in out:
        out["drill_down_categoria"] = None
    if "drill_down_subcategoria" not in out:
        out["drill_down_subcategoria"] = None
    if "prf2_vista_abc_articulos" not in out:
        out["prf2_vista_abc_articulos"] = False
    if "lri_man_orden_ascendente" not in out:
        out["lri_man_orden_ascendente"] = False
    # Evita Top N pegajoso (p. ej. Top 2 → solo 2 de 4 categorías).
    if "lri_man_top_n" not in out or out.get("lri_man_top_n") is None:
        out["lri_man_top_n"] = 0
    return out


def _bloquear_perfil_desde_config(config: dict[str, Any]) -> None:
    """Recuerda el cruce de ChatGPT/voz (se respeta hasta que el usuario toque un selector)."""
    config = completar_config_reemplazo_perfil(config)
    st.session_state["prf2_origen_perfil"] = "chatgpt"
    bloqueo: dict[str, Any] = {}
    for k in _CLAVES_PERFIL_UI:
        if k in config:
            bloqueo[k] = config[k]
    bloqueo["drill_down_categoria"] = config.get("drill_down_categoria")
    bloqueo["drill_down_subcategoria"] = config.get("drill_down_subcategoria")
    bloqueo["prf2_vista_abc_articulos"] = bool(config.get("prf2_vista_abc_articulos"))
    for k in ("lri_man_eje_x", "lri_man_eje_y", "lri_man_eje_y2", "lri_man_eje_y3"):
        if k in config and config[k] is not None:
            bloqueo[k] = config[k]
    if "lri_man_operacion" in config:
        bloqueo["lri_man_operacion"] = config["lri_man_operacion"]
    if "lri_man_orden_ascendente" in config:
        bloqueo["lri_man_orden_ascendente"] = bool(config["lri_man_orden_ascendente"])
    st.session_state["prf2_perfil_bloqueado"] = bloqueo


def restaurar_perfil_bloqueado_si_aplica() -> None:
    """Mantiene el gráfico de ChatGPT solo si el usuario no movió selectores a mano."""
    bloqueado = st.session_state.get("prf2_perfil_bloqueado")
    if not isinstance(bloqueado, dict):
        return
    # Cambio manual en selectores → liberar y dejar que la UI mande.
    if _usuario_cambio_selectores_vs_bloqueo(bloqueado):
        manual = _snapshot_perfil_ui()
        diff = _diff_perfiles(bloqueado, manual)
        if diff:
            registrar_evento_chatgpt(
                "correccion_manual",
                pedido=st.session_state.get("prf2_chatgpt_ultimo_pedido"),
                config_chatgpt=bloqueado,
                config_manual=manual,
                diff=diff,
            )
        liberar_perfil_bloqueado()
        st.session_state["prf2_origen_perfil"] = "manual"
        # Importante: no reaplicar pendientes ChatGPT encima del manual.
        _limpiar_pendientes_ejes_perfil()
        return
    for k, v in bloqueado.items():
        if k in ("drill_down_categoria", "drill_down_subcategoria"):
            st.session_state[k] = v
            continue
        if k == "prf2_vista_abc_articulos":
            st.session_state[k] = bool(v)
            continue
        if k == "lri_man_orden_ascendente":
            st.session_state[k] = bool(v)
            continue
        if v is None:
            continue
        st.session_state[k] = v
        if k == "lri_man_eje_x":
            st.session_state["_lri_pending_man_eje_x"] = v
        elif k == "lri_man_eje_y":
            st.session_state["_lri_pending_man_eje_y"] = v
        elif k == "lri_man_eje_y2":
            st.session_state["_lri_pending_man_eje_y2"] = v
        elif k == "lri_man_eje_y3":
            st.session_state["_lri_pending_man_eje_y3"] = v


def _procesar_mensaje_conversacion(
    mensaje: str,
    df: pd.DataFrame,
    *,
    api_key: str,
    aplicar_config: Callable[[dict], None],
) -> None:
    """Consulta oral, narración del perfil actual, o cambio de gráfico desde datos."""
    with st.sidebar.spinner("ChatGPT trabaja con tus datos…"):
        intento = clasificar_intento_usuario(mensaje, api_key=api_key)
        accion = intento.get("accion")

        if accion in ("parche_perfil", "deshacer", "rehacer"):
            if mics_bloqueados() and accion == "parche_perfil":
                return
            _manejar_parche_perfil(
                mensaje,
                df,
                api_key=api_key,
                aplicar_config=aplicar_config,
            )
            st.rerun()
            return

        if accion == "narrar_analisis":
            activar_solo_narracion()
            hist = _historial_conversacion()
            hist.append({"role": "user", "content": mensaje.strip()})
            hist.append(
                {
                    "role": "assistant",
                    "content": "Voy a narrar el análisis del gráfico que está en pantalla.",
                }
            )
            st.session_state["prf2_chat_historial"] = hist[-_MAX_TURNOS_HISTORIAL * 2 :]
            st.session_state["prf2_chat_activa"] = True
            st.rerun()
            return

        if accion == "cambiar_perfil":
            if mics_bloqueados():
                return
            pedido = str(intento.get("pedido_perfil") or mensaje).strip()
            config = interpretar_pedido_perfil(pedido, df, api_key=api_key)
            _proponer_o_aplicar_perfil(
                pedido,
                config,
                api_key=api_key,
                aplicar_config=aplicar_config,
                origen="conversacion",
            )
            st.rerun()
            return

        respuesta = responder_turno_conversacion(mensaje, df, api_key=api_key)
        audio = sintetizar_voz_openai(respuesta, api_key=api_key, rapido=True)
    st.session_state["prf2_chat_reply_audio"] = audio
    st.session_state["prf2_chat_activa"] = True
    st.rerun()


def _parar_conversacion() -> None:
    st.session_state["prf2_chat_historial"] = []
    st.session_state["prf2_chat_activa"] = False
    st.session_state.pop("prf2_chat_reply_audio", None)
    st.session_state["prf2_chat_escribir"] = False
    st.session_state.pop("prf2_chat_last_audio_hash", None)
    st.session_state.pop("prf2_chatgpt_pendiente", None)


def frase_confirmacion_perfil(config: dict[str, Any]) -> str:
    ex = config.get("lri_man_eje_x")
    ey = config.get("lri_man_eje_y")
    ey2 = config.get("lri_man_eje_y2")
    orden = texto_orden_perfil(config.get("lri_man_orden_ascendente"))
    filtro = config.get("drill_down_subcategoria") or config.get("drill_down_categoria")
    en_filtro = f" en {filtro}" if filtro else ""
    if config.get("prf2_vista_abc_articulos"):
        return f"Listo. Vista ABC de artículos con {ey or 'la métrica'}{en_filtro}."
    ey3 = config.get("lri_man_eje_y3")
    partes_y = [ey] if ey else []
    if ey2 and ey2 != NINGUNA:
        partes_y.append(str(ey2))
    if ey3 and ey3 != NINGUNA:
        partes_y.append(str(ey3))
    if ex and partes_y:
        if len(partes_y) == 1:
            y_txt = partes_y[0]
        else:
            y_txt = ", ".join(partes_y[:-1]) + f" y {partes_y[-1]}"
        return f"Listo. Reemplacé el gráfico: ahora {y_txt} por {ex}{en_filtro}, {orden}."
    return "Perfil aplicado con los datos del archivo."


def aplicar_pedido_por_voz(
    pedido: str,
    df: pd.DataFrame,
    *,
    aplicar_config: Callable[[dict], None],
) -> None:
    """Transcripción → ChatGPT → propuesta o aplicación del perfil."""
    if mics_bloqueados():
        return
    api_key = obtener_api_key()
    if not api_key:
        st.sidebar.error("Falta OPENAI_API_KEY para ChatGPT por voz.")
        return
    # Saludo / “cómo estás”: responder en audio, no tocar el gráfico.
    if _parece_saludo_o_charla(pedido):
        with st.sidebar.spinner("ChatGPT responde…"):
            respuesta = responder_turno_conversacion(pedido, df, api_key=api_key)
            audio = sintetizar_voz_openai(respuesta, api_key=api_key, rapido=True)
        st.session_state["prf2_chat_reply_audio"] = audio
        st.rerun()
        return
    # Deshacer / rehacer / sustitución parcial (sin reconstruir el perfil).
    if (
        perfil_patch.parece_deshacer(pedido)
        or perfil_patch.parece_rehacer(pedido)
        or perfil_patch.parece_parche_parcial(pedido)
        or perfil_patch.parece_solo_top_n(pedido)
    ):
        with st.sidebar.spinner("Aplicando cambio parcial…"):
            _manejar_parche_perfil(
                pedido,
                df,
                api_key=api_key,
                aplicar_config=aplicar_config,
            )
        st.rerun()
        return
    # % de los N primeros / concentración → responder sin recortar el Top N del gráfico.
    if _parece_consulta_analitica(pedido):
        with st.sidebar.spinner("ChatGPT calcula sobre el total filtrado…"):
            respuesta = responder_turno_conversacion(pedido, df, api_key=api_key)
            audio = sintetizar_voz_openai(respuesta, api_key=api_key, rapido=True)
        st.session_state["prf2_chat_reply_audio"] = audio
        st.session_state["prf2_chat_activa"] = True
        st.rerun()
        return
    # Si el usuario pidió análisis general (no otro gráfico), no reinterpretar columnas.
    if _parece_pedido_narrar(pedido):
        activar_solo_narracion()
        st.rerun()
        return
    with st.sidebar.spinner("ChatGPT escucha el perfil…"):
        config = interpretar_pedido_perfil(pedido, df, api_key=api_key)
        _proponer_o_aplicar_perfil(
            pedido,
            config,
            api_key=api_key,
            aplicar_config=aplicar_config,
            origen="voz_perfil",
        )
    st.rerun()


def _render_clave_api() -> str | None:
    api_key = obtener_api_key()
    if api_key:
        return api_key
    st.sidebar.warning("Falta OPENAI_API_KEY (secrets o pegue abajo).")
    clave = st.sidebar.text_input(
        "OPENAI_API_KEY (sesión)",
        type="password",
        key="prf2_openai_api_key_input",
    )
    if clave.strip():
        st.session_state["prf2_openai_api_key"] = clave.strip()
        st.rerun()
    return None


def render_prefijos_chatgpt_sidebar() -> None:
    """API key, confirmaciones y captions (sin el botón Narrar)."""
    api_key = _render_clave_api()
    conf = st.session_state.pop("prf2_chatgpt_confirm_audio", None)
    if conf:
        _reproducir_audio_sidebar(conf, autoplay=True)

    # Migración: volver a aplicar de inmediato (la confirmación molestaba en uso normal).
    if not st.session_state.get("prf2_chatgpt_confirmar_migrado_v2"):
        st.session_state["prf2_chatgpt_confirmar_antes"] = False
        st.session_state["prf2_chatgpt_confirmar_migrado_v2"] = True
        st.session_state.pop("prf2_chatgpt_pendiente", None)

    if "prf2_chatgpt_confirmar_antes" not in st.session_state:
        st.session_state["prf2_chatgpt_confirmar_antes"] = False
    st.sidebar.checkbox(
        "Confirmar antes de aplicar el perfil",
        key="prf2_chatgpt_confirmar_antes",
        help=(
            "Desmarcado (recomendado): aplica el gráfico al instante. "
            "Marcado: ChatGPT propone el cruce y usted confirma con un clic."
        ),
    )

    if not api_key:
        st.sidebar.caption("Configure OPENAI_API_KEY para voz y narración.")

    df_act = st.session_state.get("lri_df_datos")
    if isinstance(df_act, pd.DataFrame) and not df_act.empty:
        cov = construir_matriz_perfilado(df_act).get("cobertura") or {}
        st.sidebar.caption(
            f"Matriz perfilado: {cov.get('n_atributos', 0)} atributos × "
            f"{cov.get('n_metricas', 0)} métricas → "
            f"{cov.get('n_cruces_perfil_posibles', 0):,} cruces válidos (máx. 3 en Y)."
        )
    if os.path.isfile(_LOG_EVENTOS):
        try:
            with open(_LOG_EVENTOS, encoding="utf-8") as fh:
                n_ev = sum(1 for _ in fh)
            st.sidebar.caption(f"Log ChatGPT: {n_ev} eventos (lab).")
        except OSError:
            pass


def render_boton_narrar_sidebar() -> None:
    """Botón para narrar el gráfico actual (usar debajo del mic de perfilado ChatGPT)."""
    if st.sidebar.button(
        "🔊 Narrar análisis",
        type="primary",
        use_container_width=True,
        key="prf2_chatgpt_narrar_ahora",
        help="Analiza en audio el gráfico actual sin cambiar ejes.",
    ):
        activar_solo_narracion()
        st.rerun()


def render_boton_narrar_sidebar_completo() -> None:
    """Compat: prefijos + botón Narrar (preferir orden: prefijos → mic → narrar)."""
    render_prefijos_chatgpt_sidebar()
    render_boton_narrar_sidebar()


def render_panel_chatgpt_sidebar(
    df: pd.DataFrame,
    *,
    aplicar_config: Callable[[dict], None],
) -> None:
    """Conversación por turnos (preguntas / otro cruce). Narrar va aparte, bajo el mic de perfil."""
    api_key = obtener_api_key()

    render_confirmacion_perfil_pendiente(aplicar_config=aplicar_config)

    st.sidebar.divider()
    st.sidebar.markdown(
        '<div style="color:#fff;font-size:1.02rem;font-weight:700;">💬 Conversación por turnos</div>'
        '<div style="color:#e2e8f0;font-size:0.78rem;margin:2px 0 8px 0;">'
        "Pida otro gráfico, sustituya una variable, o pregunte; "
        "«Narrar análisis» resume el actual</div>",
        unsafe_allow_html=True,
    )
    u1, u2 = st.sidebar.columns(2)
    with u1:
        if st.button(
            "↩ Deshacer",
            use_container_width=True,
            key="prf2_btn_undo_perfil",
            help="Volver al gráfico anterior",
        ):
            _manejar_parche_perfil(
                "deshacer el último cambio",
                df,
                api_key=api_key,
                aplicar_config=aplicar_config,
            )
            st.rerun()
    with u2:
        if st.button(
            "↪ Rehacer",
            use_container_width=True,
            key="prf2_btn_redo_perfil",
            help="Reaplicar el cambio deshecho",
        ):
            _manejar_parche_perfil(
                "rehacer el último cambio",
                df,
                api_key=api_key,
                aplicar_config=aplicar_config,
            )
            st.rerun()

    if not api_key:
        return

    reply = st.session_state.pop("prf2_chat_reply_audio", None)
    if reply:
        _reproducir_audio_sidebar(reply, autoplay=True)

    detalle = st.session_state.get("prf2_consulta_detalle")
    if isinstance(detalle, dict) and detalle.get("filas"):
        st.sidebar.markdown(f"**{detalle.get('titulo') or 'Detalle de consulta'}**")
        res = detalle.get("resumen") or {}
        if res:
            st.sidebar.caption(
                f"{res.get('n')} ítems · {res.get('pct')}% de {res.get('metrica')} · "
                f"suma {res.get('suma_valor'):,.0f} / total segmento {res.get('total_segmento'):,.0f}"
                if isinstance(res.get("suma_valor"), (int, float))
                and isinstance(res.get("total_segmento"), (int, float))
                else f"{res.get('n')} ítems · {res.get('pct')}% · {res.get('ambito')}"
            )
        try:
            st.sidebar.dataframe(
                pd.DataFrame(detalle["filas"]),
                use_container_width=True,
                hide_index=True,
            )
        except Exception:
            for fila in detalle["filas"]:
                st.sidebar.write(
                    f"{fila.get('#')}. {fila.get('Artículo')} — "
                    f"{fila.get('% del segmento')}% ({fila.get('Valor'):,.0f})"
                )

    if audio_recorder is None:
        st.sidebar.caption("Instale audio_recorder_streamlit para hablar en la conversación.")
    else:
        audio = audio_recorder(
            text="",
            pause_threshold=_VOICE_PAUSA_CHAT,
            energy_threshold=0.01,
            sample_rate=44100,
            neutral_color="#FFFFFF",
            recording_color="#38bdf8",
            icon_name="microphone",
            icon_size="3x",
            key="prf2_chat_mic",
        )
        audio_bytes = audio.get("bytes") if isinstance(audio, dict) else audio
        if audio_bytes:
            audio_hash = hashlib.md5(audio_bytes, usedforsecurity=False).hexdigest()
            if mics_bloqueados():
                # Mantener el botón visible; no reinterpretar durante la narración.
                st.session_state["prf2_chat_last_audio_hash"] = audio_hash
            elif audio_hash != st.session_state.get("prf2_chat_last_audio_hash"):
                st.session_state["prf2_chat_last_audio_hash"] = audio_hash
                try:
                    texto = _transcribir_audio(audio_bytes)
                    _procesar_mensaje_conversacion(
                        texto,
                        df,
                        api_key=api_key,
                        aplicar_config=aplicar_config,
                    )
                except sr.UnknownValueError:
                    st.sidebar.error("No se entendió el mensaje de voz.")
                except Exception as exc:
                    st.sidebar.error(f"Conversación: {exc}")

    if mics_bloqueados():
        st.sidebar.caption("Narrando… los micrófonos siguen visibles; el audio se ignora un momento.")

    c1, c2 = st.sidebar.columns(2)
    with c1:
        if st.button(
            "✍️ Escribir",
            use_container_width=True,
            key="prf2_chat_btn_escribir",
        ):
            st.session_state["prf2_chat_escribir"] = not bool(
                st.session_state.get("prf2_chat_escribir")
            )
            st.rerun()
    with c2:
        if st.button(
            "⏹ Parar",
            use_container_width=True,
            key="prf2_chat_btn_parar",
        ):
            _parar_conversacion()
            st.rerun()

    if st.session_state.get("prf2_chat_escribir"):
        pregunta = st.sidebar.text_input(
            "Pregunta",
            key="prf2_chat_texto",
            label_visibility="collapsed",
            placeholder="Ej: muestra inventario por subcategoría",
        )
        if st.sidebar.button(
            "Enviar pregunta",
            use_container_width=True,
            key="prf2_chat_enviar_texto",
        ):
            if (pregunta or "").strip():
                try:
                    _procesar_mensaje_conversacion(
                        pregunta.strip(),
                        df,
                        api_key=api_key,
                        aplicar_config=aplicar_config,
                    )
                except Exception as exc:
                    st.sidebar.error(f"Conversación: {exc}")


def talvez_narrar_tras_perfil(
    df_resumen: pd.DataFrame,
    *,
    eje_x: str,
    eje_y: str,
    operacion_y: str,
    eje_y2: str | None = None,
    eje_y3: str | None = None,
    df_universo: pd.DataFrame | None = None,
    n_en_pantalla: int | None = None,
) -> None:
    """Guarda hechos del perfil; narra solo si se pidió narración (botón o voz).

    ``df_universo`` debe ser el ranking completo del filtro actual (Top N = 0).
    Así la concentración de los primeros K es sobre el total de la categoría/subcategoría,
    no sobre el recorte visual.
    """
    forzar = bool(st.session_state.get("prf2_chatgpt_forzar_narracion", False))
    base = df_universo if isinstance(df_universo, pd.DataFrame) and not df_universo.empty else df_resumen
    cat = st.session_state.get("drill_down_categoria")
    sub = st.session_state.get("drill_down_subcategoria")
    if sub:
        ambito = f"la subcategoría {sub}"
    elif cat:
        ambito = f"la categoría {cat}"
    else:
        ambito = "el ranking actual"
    hechos = hechos_perfil_resumen(
        base,
        eje_x=eje_x,
        eje_y=eje_y,
        operacion_y=operacion_y,
        eje_y2=eje_y2,
        eje_y3=eje_y3,
        ambito_filtro=ambito,
        n_en_pantalla=n_en_pantalla
        if n_en_pantalla is not None
        else (len(df_resumen) if isinstance(df_resumen, pd.DataFrame) else None),
    )
    _guardar_hechos_perfil(hechos)
    if not hechos.get("ok"):
        st.session_state["prf2_chatgpt_forzar_narracion"] = False
        st.session_state["prf2_ignorar_mics"] = False
        return

    fp = json.dumps(hechos, sort_keys=True, ensure_ascii=False)
    audio_prev = st.session_state.get("prf2_chatgpt_audio")

    if not forzar:
        if audio_prev and st.session_state.get("prf2_chatgpt_audio_fp") == fp:
            try:
                st.audio(audio_prev, format="audio/mp3")
            except TypeError:
                st.audio(audio_prev, format="audio/mp3")
        return

    # Consumir flags solo al narrar de verdad (después de restaurar el perfil bloqueado).
    st.session_state["prf2_chatgpt_forzar_narracion"] = False
    api_key = obtener_api_key()
    if not api_key:
        st.session_state["prf2_ignorar_mics"] = False
        return

    try:
        with st.spinner("Narrando el gráfico actual…"):
            guion = generar_resumen_hablado(hechos, api_key=api_key)
            audio = sintetizar_voz_openai(guion, api_key=api_key, rapido=True)
        st.session_state["prf2_chatgpt_guion"] = guion
        st.session_state["prf2_chatgpt_audio"] = audio
        st.session_state["prf2_chatgpt_audio_fp"] = fp
    except Exception:
        st.session_state["prf2_ignorar_mics"] = False
        return

    st.session_state["prf2_ignorar_mics"] = False
    try:
        st.audio(audio, format="audio/mp3", autoplay=True)
    except TypeError:
        st.audio(audio, format="audio/mp3")
