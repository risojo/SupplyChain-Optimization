"""Parches parciales del perfil gráfico + undo/redo (Profile Pro / profile2).

ChatGPT solo interpreta intención; la validación y el cambio los hace Python
sobre el estado vigente en session_state (sin reconstruir el gráfico completo).
"""
from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from typing import Any

import streamlit as st

NINGUNA = "— Ninguna —"
_MAX_UNDO = 25

# Estado completo del gráfico que debe preservarse / restaurarse.
CLAVES_SNAPSHOT_PERFIL: tuple[str, ...] = (
    "lri_man_eje_x",
    "lri_man_eje_y",
    "lri_man_eje_y2",
    "lri_man_eje_y3",
    "lri_man_operacion",
    "lri_man_operacion_y",
    "lri_man_operacion_y2",
    "lri_man_operacion_y3",
    "lri_man_top_n",
    "lri_man_orden_ascendente",
    "drill_down_categoria",
    "drill_down_subcategoria",
    "lri_pareto_set",
    "prf2_vista_abc_articulos",
)

_SLOTS_Y = ("lri_man_eje_y", "lri_man_eje_y2", "lri_man_eje_y3")
_SLOTS_OP = {
    "lri_man_eje_y": "lri_man_operacion_y",
    "lri_man_eje_y2": "lri_man_operacion_y2",
    "lri_man_eje_y3": "lri_man_operacion_y3",
}

# Sinónimos → nombre canónico deseado (luego se valida contra columnas reales).
_SINONIMOS_METRICAS: dict[str, tuple[str, ...]] = {
    "ventas totales": (
        "ventas",
        "venta",
        "ventas totales",
        "venta total",
        "ventas brutas",
        "venta bruta",
        "ingresos",
        "ingreso",
        "sales",
    ),
    "margen bruto total": (
        "margen bruto total",
        "margen bruto",
        "utilidad bruta",
        "utilidad bruto",
        "margen",
        "utilidad",
        "gross margin",
        "gm",
    ),
    "margen utilidad ventas": (
        "margen utilidad ventas",
        "margen sobre ventas",
        "margen porcentaje",
        "margen %",
    ),
    "valor inventario promedio": (
        "valor inventario promedio",
        "inventario promedio",
        "inventario valor",
        "valor de inventario",
        "inventario promedio valor",
    ),
    "inventario promedio bultos": (
        "inventario promedio bultos",
        "inventario en bultos",
        "inventario bultos",
        "promedio bultos",
    ),
    "meses inventario": (
        "meses inventario",
        "meses de inventario",
        "mes inventario",
        "mes de inventario",
        "dias inventario",
        "dias de inventario",
        "día inventario",
        "días inventario",
        "cobertura en meses",
        "cobertura de inventario",
        "cobertura inventario",
        "doi",
    ),
    "rotacion": (
        "rotacion",
        "rotación",
        "giro",
        "giros",
        "turnover",
    ),
    "costo mantener inventario": (
        "costo mantener inventario",
        "costo de mantener",
        "costo mantener",
    ),
    "ventas costo": (
        "ventas costo",
        "costo de ventas",
        "costo ventas",
    ),
}

_SINONIMOS_DIMENSIONES: dict[str, tuple[str, ...]] = {
    "categoria": ("categoria", "categoría", "categorias", "categorías"),
    "subcategoria": (
        "subcategoria",
        "subcategoría",
        "subcategorias",
        "subcategorías",
        "subcateg",
    ),
    "descripcion": (
        "descripcion",
        "descripción",
        "sku",
        "skus",
        "articulo",
        "artículo",
        "articulos",
        "artículos",
        "producto",
        "productos",
        "item",
        "ítem",
        "items",
    ),
    "codigo": ("codigo", "código", "codigos", "códigos"),
    "clase": ("clase", "abc", "clase abc"),
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _texto_suave(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.lower()).strip()


def _es_vacia_metrica(v: Any) -> bool:
    if v is None:
        return True
    s = str(v).strip()
    return (not s) or s == NINGUNA


def metricas_activas_estado(estado: dict[str, Any] | None = None) -> list[str]:
    """Lista ordenada de métricas Y actuales (sin vacíos)."""
    src = estado if estado is not None else dict(st.session_state)
    out: list[str] = []
    for k in _SLOTS_Y:
        v = src.get(k)
        if not _es_vacia_metrica(v):
            out.append(str(v))
    return out


def snapshot_perfil_completo() -> dict[str, Any]:
    """Copia completa del estado vigente del gráfico."""
    snap: dict[str, Any] = {}
    for k in CLAVES_SNAPSHOT_PERFIL:
        if k in st.session_state:
            snap[k] = deepcopy(st.session_state.get(k))
    return snap


def _undo_stack() -> list[dict[str, Any]]:
    stck = st.session_state.get("prf2_perfil_undo_stack")
    if not isinstance(stck, list):
        stck = []
        st.session_state["prf2_perfil_undo_stack"] = stck
    return stck


def _redo_stack() -> list[dict[str, Any]]:
    stck = st.session_state.get("prf2_perfil_redo_stack")
    if not isinstance(stck, list):
        stck = []
        st.session_state["prf2_perfil_redo_stack"] = stck
    return stck


def push_undo_antes_de_cambiar() -> None:
    """Guarda el gráfico actual antes de una modificación válida."""
    snap = snapshot_perfil_completo()
    if not snap.get("lri_man_eje_x") and not snap.get("lri_man_eje_y"):
        return
    stack = _undo_stack()
    if stack and stack[-1] == snap:
        return
    stack.append(snap)
    del stack[:-_MAX_UNDO]
    st.session_state["prf2_perfil_redo_stack"] = []


def restaurar_snapshot(snap: dict[str, Any], *, aplicar_config: Any) -> dict[str, Any]:
    """Restaura un snapshot completo vía el apply existente."""
    cfg = deepcopy(snap)
    # Asegurar claves de métricas adicionales.
    for k in ("lri_man_eje_y2", "lri_man_eje_y3"):
        if k not in cfg or cfg.get(k) is None:
            cfg[k] = NINGUNA
    aplicar_config(cfg)
    return cfg


def deshacer_ultimo_cambio(*, aplicar_config: Any) -> dict[str, Any] | None:
    stack = _undo_stack()
    if not stack:
        return None
    actual = snapshot_perfil_completo()
    prev = stack.pop()
    _redo_stack().append(actual)
    return restaurar_snapshot(prev, aplicar_config=aplicar_config)


def rehacer_ultimo_cambio(*, aplicar_config: Any) -> dict[str, Any] | None:
    stack = _redo_stack()
    if not stack:
        return None
    actual = snapshot_perfil_completo()
    nxt = stack.pop()
    _undo_stack().append(actual)
    return restaurar_snapshot(nxt, aplicar_config=aplicar_config)


def parece_deshacer(mensaje: str) -> bool:
    p = _norm(mensaje)
    return any(
        k in p
        for k in (
            "deshacer",
            "undo",
            "volveralanterior",
            "volveralgraficoanterior",
            "regresarcomoestaba",
            "regresaalanterior",
            "comolodejeantes",
            "graficoanterior",
            "estadoanterior",
            "revertir",
            "echaatras",
            "echaparaatras",
        )
    )


def parece_rehacer(mensaje: str) -> bool:
    p = _norm(mensaje)
    return any(
        k in p
        for k in (
            "rehacer",
            "redo",
            "adelanteotravez",
            "reaplica",
            "reaplicar",
            "deshazeldeshacer",
        )
    )


def parece_parche_parcial(mensaje: str) -> bool:
    """Sustituir/cambiar una o varias variables sin pedir un cruce nuevo completo."""
    p = _norm(mensaje)
    if not p:
        return False
    # Reconstrucción completa explícita → no es parche.
    if any(
        k in p
        for k in (
            "muestrame",
            "mostrarme",
            "graficame",
            "grafica",
            "armame",
            "nuevografico",
            "otrocruce",
            "perfilnuevo",
        )
    ) and "sustitu" not in p and "reemplaz" not in p:
        # "cambia el gráfico a ventas por categoría" es reconstrucción
        if "porcategoria" in p or "porsubcategoria" in p or "porsku" in p:
            return False
    keys = (
        "sustitu",
        "reemplaz",
        "cambie",
        "cambia",
        "cambiar",
        "enlugarde",
        "ponmeenvez",
        "envezde",
        "envez",
        "intercamb",
        "reemplaza",
        "sustituya",
        "sustituye",
        "reemplaze",
    )
    if any(k in p for k in keys):
        # "cambia el top N" no es sustitución de métrica.
        if re.search(r"cambi(?:a|e|ar).{0,12}top", p) and not any(
            k in p for k in ("sustitu", "reemplaz", "enlugar", "envez")
        ):
            return False
        return True
    return False


def parece_solo_top_n(mensaje: str) -> bool:
    p = _norm(mensaje)
    if not p:
        return False
    if not any(k in p for k in ("top", "primeros", "mayores", "mostrartop", "dejame")):
        return False
    # Si nombra un cruce nuevo completo, no.
    if "porcategoria" in p or "porsubcategoria" in p:
        return False
    if parece_parche_parcial(mensaje) and any(
        k in p for k in ("sustitu", "reemplaz", "enlugar", "envez")
    ):
        return False
    return bool(re.search(r"top\d{1,5}", p) or re.search(r"(?:top|primeros|mayores)(\d{1,5})", p))


def extraer_top_n(mensaje: str) -> int | None:
    p = _norm(mensaje)
    m = re.search(r"top(\d{1,5})", p)
    if m:
        return int(m.group(1))
    m = re.search(r"(?:primeros|mayores|mostrar)(\d{1,5})", p)
    if m:
        return int(m.group(1))
    if "todos" in p or "todas" in p or "sinlimite" in p:
        return 0
    return None


def _columnas_dim_met(df: Any) -> tuple[list[str], list[str]]:
    """Dimensiones / métricas reales del DataFrame (sin inventar nombres)."""
    dims: list[str] = []
    mets: list[str] = []
    if df is None or not hasattr(df, "columns"):
        return dims, mets
    for col in df.columns:
        nombre = str(col).strip()
        if not nombre or nombre.lower().startswith("unnamed"):
            continue
        try:
            import pandas as pd

            if pd.api.types.is_numeric_dtype(df[col]):
                mets.append(nombre)
            else:
                dims.append(nombre)
        except Exception:
            dims.append(nombre)
    return dims, mets


def construir_catalogo_variables(df: Any) -> dict[str, Any]:
    """Catálogo real (columnas del DF) + sinónimos aplicables."""
    dims, mets = _columnas_dim_met(df)
    # Preferir catálogo ChatGPT si está disponible (misma fuente que la UI).
    try:
        from analisis_chatgpt_profile import catalogo_columnas

        cat = catalogo_columnas(df)
        dims = list(cat.get("dimensiones") or dims)
        mets = list(cat.get("metricas") or mets)
    except Exception:
        pass
    sinonimos_m: dict[str, str] = {}
    for canon, alts in _SINONIMOS_METRICAS.items():
        real = _resolver_en_lista(canon, mets)
        if not real:
            continue
        for a in alts:
            sinonimos_m[_norm(a)] = real
        sinonimos_m[_norm(canon)] = real
        sinonimos_m[_norm(real)] = real
    for m in mets:
        sinonimos_m[_norm(m)] = m

    sinonimos_d: dict[str, str] = {}
    for canon, alts in _SINONIMOS_DIMENSIONES.items():
        real = _resolver_en_lista(canon, dims)
        if not real:
            continue
        for a in alts:
            sinonimos_d[_norm(a)] = real
        sinonimos_d[_norm(canon)] = real
        sinonimos_d[_norm(real)] = real
    for d in dims:
        sinonimos_d[_norm(d)] = d

    return {
        "dimensiones": dims,
        "metricas": mets,
        "sinonimos_metricas": sinonimos_m,
        "sinonimos_dimensiones": sinonimos_d,
    }


def _resolver_en_lista(nombre: str, candidatas: list[str]) -> str | None:
    if not nombre or not candidatas:
        return None
    nn = _norm(nombre)
    for c in candidatas:
        if _norm(c) == nn:
            return c
    for c in candidatas:
        cn = _norm(c)
        if nn and (nn in cn or cn in nn) and abs(len(cn) - len(nn)) <= 8:
            return c
    return None


def resolver_variable(
    frase: str,
    df: Any,
    *,
    tipo: str = "metrica",
    candidatas_preferidas: list[str] | None = None,
) -> dict[str, Any]:
    """Resuelve una frase a columna real. Nunca inventa.

    Returns:
      ok, valor, candidatos, motivo
    """
    catalogo = construir_catalogo_variables(df)
    frase_n = _norm(frase)
    if not frase_n:
        return {"ok": False, "valor": None, "candidatos": [], "motivo": "vacio"}

    if tipo == "dimension":
        syn = catalogo["sinonimos_dimensiones"]
        pool = catalogo["dimensiones"]
    else:
        syn = catalogo["sinonimos_metricas"]
        pool = catalogo["metricas"]

    # 1) Match exacto por sinónimo / nombre
    if frase_n in syn:
        return {"ok": True, "valor": syn[frase_n], "candidatos": [syn[frase_n]], "motivo": "exacto"}

    # 2) Contención: sinónimos más largos primero
    hits: list[str] = []
    for key_n, real in sorted(syn.items(), key=lambda kv: len(kv[0]), reverse=True):
        if len(key_n) < 3:
            continue
        if key_n in frase_n or frase_n in key_n:
            if real not in hits:
                hits.append(real)

    # 3) Preferir métricas ya en el gráfico si hay ambigüedad
    if candidatas_preferidas:
        pref = [h for h in hits if h in candidatas_preferidas]
        if len(pref) == 1:
            return {"ok": True, "valor": pref[0], "candidatos": pref, "motivo": "preferida"}
        if len(pref) > 1:
            hits = pref

    hits = [h for h in hits if h in pool]
    # Únicos
    uniq: list[str] = []
    for h in hits:
        if h not in uniq:
            uniq.append(h)

    if len(uniq) == 1:
        return {"ok": True, "valor": uniq[0], "candidatos": uniq, "motivo": "unico"}
    if len(uniq) > 1:
        return {
            "ok": False,
            "valor": None,
            "candidatos": uniq[:8],
            "motivo": "ambiguo",
        }
    return {"ok": False, "valor": None, "candidatos": [], "motivo": "no_encontrado"}


def _extraer_pares_sustitucion(mensaje: str) -> list[tuple[str, str]]:
    """Extrae pares (desde, hacia) de frases tipo 'sustituya A por B' / 'A por B y C por D'."""
    t = _texto_suave(mensaje)
    pares: list[tuple[str, str]] = []

    # "pon X en lugar de Y" → desde=Y, hacia=X
    for m in re.finditer(
        r"(?:pon(?:ga|me)?|usa|use|usar)\s+(.+?)\s+(?:en\s+lugar\s+de|en\s+vez\s+de)\s+(.+?)(?=\s+y\s+|$|,|\.)",
        t,
        flags=re.I,
    ):
        hacia = m.group(1).strip(" .,;:")
        desde = m.group(2).strip(" .,;:")
        if desde and hacia:
            pares.append((desde, hacia))

    # Quitar verbos iniciales y partir en cláusulas "... por ..."
    cuerpo = re.sub(
        r"^(?:por\s+favor\s+)?(?:sustitu(?:ya|ye|ir)?|reemplaz(?:a|e|ar)?|cambia|cambie|cambiar)\s+",
        "",
        t,
        flags=re.I,
    )
    cuerpo = re.sub(
        r"^(?:en\s+lugar\s+de|en\s+vez\s+de)\s+",
        "",
        cuerpo,
        flags=re.I,
    )
    # "A por B y C por D" → dos cláusulas
    clausulas = re.split(r"\s+y\s+(?=.+\s+por\s+.)", cuerpo)
    for cl in clausulas:
        cl = cl.strip(" .,;:")
        m = re.search(r"^(.+?)\s+por\s+(.+)$", cl, flags=re.I)
        if not m:
            continue
        a = m.group(1).strip(" .,;:")
        b = m.group(2).strip(" .,;:")
        # Evitar verbos sueltos
        if _norm(a) in ("sustituya", "sustituye", "reemplaza", "cambia", "cambie"):
            continue
        if a and b and (a, b) not in pares:
            pares.append((a, b))
    return pares


def interpretar_parche_local(mensaje: str, df: Any) -> dict[str, Any]:
    """Intento local (sin GPT) de armar un parche validado."""
    if parece_deshacer(mensaje):
        return {"accion": "deshacer", "ok": True, "motivo": "local_deshacer"}
    if parece_rehacer(mensaje):
        return {"accion": "rehacer", "ok": True, "motivo": "local_rehacer"}

    estado = snapshot_perfil_completo()
    activas = metricas_activas_estado(estado)

    if parece_solo_top_n(mensaje) or (
        "top" in _norm(mensaje)
        and not _extraer_pares_sustitucion(mensaje)
        and not any(k in _norm(mensaje) for k in ("sustitu", "reemplaz", "enlugar", "envez"))
    ):
        top = extraer_top_n(mensaje)
        if top is not None:
            return {
                "accion": "parche_perfil",
                "ok": True,
                "top_n": top,
                "reemplazos": [],
                "motivo": "local_top_n",
            }

    if not parece_parche_parcial(mensaje) and not _extraer_pares_sustitucion(mensaje):
        return {"accion": None, "ok": False, "motivo": "no_parche"}

    pares_txt = _extraer_pares_sustitucion(mensaje)
    if not pares_txt:
        return {
            "accion": "parche_perfil",
            "ok": False,
            "motivo": "sin_pares",
            "pregunta": (
                "¿Qué métrica quiere sustituir y por cuál? "
                "Ejemplo: sustituya ventas totales por meses inventario."
            ),
        }

    reemplazos: list[dict[str, str]] = []
    preguntas: list[str] = []
    for desde_txt, hacia_txt in pares_txt:
        r_desde = resolver_variable(
            desde_txt, df, tipo="metrica", candidatas_preferidas=activas
        )
        r_hacia = resolver_variable(hacia_txt, df, tipo="metrica")
        if not r_desde["ok"]:
            if r_desde["motivo"] == "ambiguo":
                preguntas.append(
                    f"«{desde_txt}» puede ser: {', '.join(r_desde['candidatos'])}. ¿Cuál?"
                )
            else:
                preguntas.append(
                    f"No encuentro la métrica «{desde_txt}» en el gráfico ni en los datos."
                )
            continue
        if not r_hacia["ok"]:
            if r_hacia["motivo"] == "ambiguo":
                preguntas.append(
                    f"«{hacia_txt}» puede ser: {', '.join(r_hacia['candidatos'])}. ¿Cuál?"
                )
            else:
                preguntas.append(
                    f"No existe la métrica «{hacia_txt}» en las columnas del archivo."
                )
            continue
        if r_desde["valor"] not in activas:
            preguntas.append(
                f"«{r_desde['valor']}» no está en el gráfico actual "
                f"(ahora: {', '.join(activas) or 'ninguna'})."
            )
            continue
        if r_hacia["valor"] in activas and r_hacia["valor"] != r_desde["valor"]:
            preguntas.append(
                f"«{r_hacia['valor']}» ya está en el gráfico; elija otra métrica."
            )
            continue
        reemplazos.append({"desde": r_desde["valor"], "hacia": r_hacia["valor"]})

    if preguntas and not reemplazos:
        return {
            "accion": "parche_perfil",
            "ok": False,
            "motivo": "validacion",
            "pregunta": " ".join(preguntas),
            "reemplazos": [],
        }
    if not reemplazos:
        return {
            "accion": "parche_perfil",
            "ok": False,
            "motivo": "sin_reemplazos",
            "pregunta": "No pude identificar qué variable sustituir.",
        }
    out: dict[str, Any] = {
        "accion": "parche_perfil",
        "ok": True,
        "reemplazos": reemplazos,
        "motivo": "local_sustitucion",
    }
    if preguntas:
        out["advertencias"] = preguntas
    return out


def aplicar_reemplazos_metricas(
    estado: dict[str, Any],
    reemplazos: list[dict[str, str]],
) -> dict[str, Any]:
    """Devuelve un config-parche: solo slots Y tocados (+ ops espejo)."""
    cfg = deepcopy(estado)
    for rep in reemplazos:
        desde = rep.get("desde")
        hacia = rep.get("hacia")
        if not desde or not hacia:
            continue
        for slot in _SLOTS_Y:
            actual = cfg.get(slot)
            if _es_vacia_metrica(actual):
                continue
            if _norm(str(actual)) == _norm(str(desde)):
                cfg[slot] = hacia
                # Si era Y principal, el criterio de orden pasa a ser la nueva (mismo flag asc/desc).
                break
    # Config mínimo a aplicar (solo claves de snapshot presentes)
    patch = {k: cfg.get(k) for k in CLAVES_SNAPSHOT_PERFIL if k in cfg}
    # Asegurar ops legacy
    if patch.get("lri_man_operacion_y") and not patch.get("lri_man_operacion"):
        patch["lri_man_operacion"] = patch["lri_man_operacion_y"]
    return patch


def aplicar_parche_validado(
    intent: dict[str, Any],
    *,
    aplicar_config: Any,
) -> dict[str, Any]:
    """Aplica deshacer/rehacer/top_n/reemplazos sobre el estado actual."""
    accion = intent.get("accion")
    if accion == "deshacer":
        cfg = deshacer_ultimo_cambio(aplicar_config=aplicar_config)
        if cfg is None:
            return {"ok": False, "mensaje": "No hay un gráfico anterior para restaurar."}
        return {"ok": True, "mensaje": "Listo. Volví al gráfico anterior.", "config": cfg}
    if accion == "rehacer":
        cfg = rehacer_ultimo_cambio(aplicar_config=aplicar_config)
        if cfg is None:
            return {"ok": False, "mensaje": "No hay un cambio para rehacer."}
        return {"ok": True, "mensaje": "Listo. Rehíce el último cambio.", "config": cfg}

    if accion != "parche_perfil" or not intent.get("ok"):
        return {
            "ok": False,
            "mensaje": intent.get("pregunta")
            or "No pude aplicar el cambio parcial.",
        }

    estado = snapshot_perfil_completo()
    push_undo_antes_de_cambiar()

    patch = deepcopy(estado)
    msg_partes: list[str] = []

    reemplazos = intent.get("reemplazos") or []
    if reemplazos:
        patch = aplicar_reemplazos_metricas(patch, reemplazos)
        for r in reemplazos:
            msg_partes.append(f"sustituí {r['desde']} por {r['hacia']}")

    if intent.get("top_n") is not None:
        try:
            patch["lri_man_top_n"] = int(intent["top_n"])
            msg_partes.append(f"Top N = {patch['lri_man_top_n']}")
        except (TypeError, ValueError):
            pass

    if intent.get("eje_x"):
        patch["lri_man_eje_x"] = intent["eje_x"]
        msg_partes.append(f"eje X = {intent['eje_x']}")

    # Normalizar vacíos Y2/Y3
    for k in ("lri_man_eje_y2", "lri_man_eje_y3"):
        if k not in patch or patch.get(k) is None:
            patch[k] = NINGUNA

    aplicar_config(patch)
    # Actualizar bloqueo ChatGPT al nuevo estado (si existe el helper en sesión).
    st.session_state["prf2_perfil_bloqueado"] = {
        k: patch.get(k) for k in CLAVES_SNAPSHOT_PERFIL if k in patch
    }
    st.session_state["prf2_origen_perfil"] = "chatgpt_parche"

    mensaje = "Listo. " + ("; ".join(msg_partes) if msg_partes else "Actualicé el gráfico.") + "."
    activas = metricas_activas_estado(patch)
    if activas:
        mensaje += " Variables actuales: " + ", ".join(activas) + "."
    return {"ok": True, "mensaje": mensaje, "config": patch}
