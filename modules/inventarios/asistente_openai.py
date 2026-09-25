"""Integración OpenAI Responses API + function calling para el asistente LRI."""
from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

import pandas as pd

import asistente_catalogo as catalogo
import asistente_tools as tools

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None  # type: ignore

INSTRUCCIONES = """\
Eres el Asistente Inteligente de Inventarios LRI. Tu único rol es interpretar
lenguaje natural y proponer un plan estructurado (métricas, dimensiones, filtros,
group_by, agregaciones, derivadas, sort, limit, output/chart). El ejecutor local
aplica el plan de forma determinista sobre el DataFrame final de LRI Inventory Pro.

NUNCA inventes datos, ejecutes código libre, calcules sobre filas enviadas al modelo
ni generes imágenes/Base64. Nunca sustituyas silenciosamente una métrica por otra
con unidad distinta:
- ventas en unidades ≠ ventas en dólares
- inventario en bultos ≠ inventario en dólares
- «margen de utilidad» / «margen %» → metrica «margen utilidad ventas» (PORCENTAJE)
- «utilidad bruta» / «margen bruto» → metrica «margen bruto total» (DÓLARES)
Si dice solo «margen» o «utilidad» sin calificar, pregunta (%) o ($).
Nunca conviertas margen de utilidad en utilidad bruta.

Enrutamiento:
- Compra/reposición CON rotación objetivo explícita → consultar_plan_compras.
- Cualquier otra consulta (incl. «según el mínimo», filtros, multi-métrica, gráficos)
  → consultar_datos. «Artículos que hay/no hay que comprar según el mínimo» son
  FILTROS componibles (qty según mínimo > 0 o ≤ 0), no reportes cerrados; las
  métricas a mostrar son las que pida el usuario (si no pide ninguna, qty según mínimo).
- Conserva contexto SOLO en seguimientos claros («ahora…», «muéstrelo por…»).
- Gráficos: Plotly local en Streamlit. PROHIBIDO Base64 / data:image / PNG en texto.
"""

TIMEOUT_OPENAI_SEG = 45.0
MAX_TURNS_TOOLS = 4


def _resolver_consulta_local(
    pregunta: str,
    df: pd.DataFrame,
    *,
    dias_trabajo: int,
    contexto: dict[str, Any],
) -> dict[str, Any] | None:
    """Plan estructurado universal → ejecutor local (sin round-trip de tools)."""
    import asistente_query_plan as qp

    # Compra por rotación explícita → tools de compras (OpenAI / construir_plan_compras)
    if catalogo.es_consulta_compras(pregunta) and not catalogo.es_reposicion_por_minimo(
        pregunta
    ):
        return None
    if catalogo.menciona_rotacion_objetivo(pregunta) and any(
        k in catalogo._norm(pregunta)
        for k in ("comprar", "compra", "compras", "reposicion", "reponer")
    ):
        return None

    t = catalogo._norm(pregunta)
    if any(x in t for x in ("regrese", "grafico anterior", "gráfico anterior", "resultado anterior")):
        return {
            "ok": False,
            "tipo": "undo",
            "mensaje": "Use el botón «Regresar al resultado anterior» o diga de nuevo la consulta.",
            "necesita_aclaracion": False,
            "accion": "undo",
        }

    plan_ant = None
    # Solo heredar plan previo en seguimiento claro (no en consultas nuevas independientes)
    if contexto.get("ultimo_plan") and any(
        x in t
        for x in (
            "ahora",
            "cambie",
            "agregue",
            "quite",
            "ordene",
            "muestrelo",
            "muéstrelo",
            "solo",
            "solamente",
        )
    ):
        plan_ant = qp.QueryPlan.from_dict(contexto.get("ultimo_plan"))

    base = tools.enriquecer_dataframe_consulta(
        df,
        dias_trabajo=dias_trabajo,
        rotacion=int(contexto.get("rotacion") or 4),
    )
    plan = qp.construir_plan(pregunta, base, plan_anterior=plan_ant)
    if plan.es_compras:
        return None
    if plan.aclaracion:
        return {
            "ok": False,
            "tipo": "consulta_datos",
            "mensaje": plan.aclaracion,
            "necesita_aclaracion": True,
            "plan": plan.to_dict(),
        }
    if not plan.metrics:
        return None

    result = qp.ejecutar_plan(
        df,
        plan,
        dias_trabajo=dias_trabajo,
        rotacion=int(contexto.get("rotacion") or 4),
    )
    # Ampliar verificación con n_registros
    if result.get("ok") and result.get("verificacion") and result.get("resumen"):
        n = result["resumen"].get("n_filas")
        if n is not None and "Registros:" not in result["verificacion"]:
            result["verificacion"] = result["verificacion"] + f" | Registros: {n}"
            result["mensaje"] = result["verificacion"] + ". " + (
                result.get("mensaje", "").split(". ", 1)[-1]
                if result.get("mensaje")
                else ""
            )
    return result


def _explicacion_breve(
    *,
    api_key: str,
    pregunta: str,
    resultado: dict[str, Any],
) -> str:
    """Una sola llamada corta a OpenAI solo para narrar el resumen compacto."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key, timeout=TIMEOUT_OPENAI_SEG)
    compact = tools.resumen_compacto_para_modelo(resultado)
    resp = client.responses.create(
        model=obtener_modelo(),
        instructions=(
            "Eres el Asistente LRI. Explica en español, máximo 4 frases, el resultado. "
            "PROHIBIDO: Base64, data:image, JSON, listar todos los SKUs, inventar números."
        ),
        input=(
            f"Pregunta del usuario: {pregunta}\n"
            f"Resumen factual:\n{json.dumps(compact, ensure_ascii=False)}"
        ),
        temperature=0.2,
        max_output_tokens=350,
    )
    texto = (getattr(resp, "output_text", None) or "").strip()
    return tools.sanitizar_texto_respuesta(texto) or (
        resultado.get("mensaje") or "Resultado listo. Revise tabla y gráfico abajo."
    )

TOOL_DEFS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "consultar_datos",
        "description": (
            "Consulta GENERAL del DataFrame procesado (rotación, ventas, margen, "
            "inventario, EVAI, GMROI, etc.). NO usar para planes de compra/reposición."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "metrica": {
                    "type": "string",
                    "description": "Columna o sinónimo: rotacion, ventas totales, margen bruto total, etc.",
                },
                "metricas": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Varias métricas para comparar (frente a / vs).",
                },
                "dimension": {
                    "type": "string",
                    "description": "Eje X / agrupación: codigo, proveedor, categoria, subcategoria, clase.",
                },
                "agregacion": {
                    "type": "string",
                    "description": "none|sum|mean|median|min|max|count. Use sum/mean al agrupar.",
                },
                "orden": {"type": "string", "description": "desc o asc"},
                "limite": {
                    "type": "integer",
                    "description": "Top/Bottom N. Omitir si el usuario pide todos.",
                },
                "mostrar_todos": {
                    "type": "boolean",
                    "description": "true si el usuario dice todos los SKU / todos los registros.",
                },
                "proveedor": {"type": "string"},
                "categoria": {"type": "string"},
                "subcategoria": {"type": "string"},
                "clase": {"type": "string"},
                "sku": {"type": "string"},
                "generar_grafico": {"type": "boolean"},
                "titulo": {"type": "string"},
            },
            "required": ["metrica"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "listar_columnas",
        "description": "Lista columnas reales del DataFrame procesado con formato y sinónimos.",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "consultar_reposicion_por_minimo",
        "description": (
            "Compatibilidad: filtro componible cantidad-a-comprar-según-mínimo > 0. "
            "Preferir consultar_datos con la frase completa del usuario. "
            "SIN rotación objetivo."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "proveedor": {"type": "string"},
                "categoria": {"type": "string"},
                "subcategoria": {"type": "string"},
                "limite": {"type": "integer"},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "consultar_plan_compras",
        "description": (
            "SOLO compra_por_rotación: plan oficial CON rotación objetivo explícita "
            "(cantidad a comprar y monto). "
            "NO usar si el usuario habla de inventario mínimo / según el mínimo."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "rotacion_objetivo": {"type": "number"},
                "proveedor": {"type": "string"},
                "sku": {"type": "string"},
                "categoria": {"type": "string"},
                "incluir_transito": {"type": "boolean"},
                "solo_compra_positiva": {"type": "boolean"},
                "ordenar_por": {"type": "string"},
                "limite": {"type": "integer"},
                "agrupacion": {"type": "string"},
            },
            "required": ["rotacion_objetivo"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "comparar_escenarios_compra",
        "description": "Compara planes de compra para dos o más rotaciones objetivo.",
        "parameters": {
            "type": "object",
            "properties": {
                "rotaciones": {"type": "array", "items": {"type": "number"}},
                "proveedor": {"type": "string"},
                "categoria": {"type": "string"},
                "incluir_transito": {"type": "boolean"},
            },
            "required": ["rotaciones"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "resumir_compras_por_proveedor",
        "description": "Agrupa monto y unidades a comprar por proveedor.",
        "parameters": {
            "type": "object",
            "properties": {
                "rotacion_objetivo": {"type": "number"},
                "categoria": {"type": "string"},
                "incluir_transito": {"type": "boolean"},
            },
            "required": ["rotacion_objetivo"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "consultar_detalle_sku",
        "description": "Detalle de uno o varios SKUs (variables de cálculo / compra).",
        "parameters": {
            "type": "object",
            "properties": {
                "sku": {"type": "string"},
                "rotacion_objetivo": {"type": "number"},
            },
            "required": ["sku"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "preparar_visualizacion",
        "description": (
            "Ajusta el gráfico del último resultado. Preferir tipo=barras (verticales). "
            "mostrar_todos=true si el usuario pide todos los SKU."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tipo": {"type": "string"},
                "eje_x": {"type": "string"},
                "eje_y": {"type": "string"},
                "titulo": {"type": "string"},
                "agrupar_por": {"type": "string"},
                "top_n": {"type": "integer"},
                "mostrar_todos": {"type": "boolean"},
                "orden_desc": {"type": "boolean"},
                "formato": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
]


def obtener_api_key() -> str | None:
    env = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if env:
        return env
    if st is not None:
        try:
            sec = st.secrets.get("OPENAI_API_KEY", "")  # type: ignore[attr-defined]
            if sec:
                return str(sec).strip()
        except Exception:
            pass
        key = st.session_state.get("inv_openai_api_key")
        if key:
            return str(key).strip()
    return None


def obtener_modelo() -> str:
    env = (os.environ.get("OPENAI_MODEL") or "").strip()
    if env:
        return env
    if st is not None:
        try:
            sec = st.secrets.get("OPENAI_MODEL", "")  # type: ignore[attr-defined]
            if sec:
                return str(sec).strip()
        except Exception:
            pass
    return "gpt-4o-mini"


def _parse_sku_arg(sku: Any) -> str | list[str] | None:
    if sku is None:
        return None
    if isinstance(sku, list):
        return [str(s) for s in sku]
    s = str(sku).strip()
    if "," in s:
        return [p.strip() for p in s.split(",") if p.strip()]
    return s


def ejecutar_herramienta(
    nombre: str,
    argumentos: dict[str, Any],
    df: pd.DataFrame,
    *,
    dias_trabajo: int,
    contexto: dict[str, Any],
) -> dict[str, Any]:
    """Ejecuta herramienta autorizada; fusiona filtros previos del contexto."""
    args = dict(argumentos or {})
    filtros_prev = contexto.get("filtros") or {}

    def _heredar(clave: str, default: Any = None) -> Any:
        if clave in args and args[clave] is not None:
            return args[clave]
        return filtros_prev.get(clave, default)

    if nombre == "listar_columnas":
        base = tools.enriquecer_dataframe_consulta(
            df,
            dias_trabajo=dias_trabajo,
            rotacion=int(contexto.get("rotacion") or 4),
        )
        return catalogo.listar_columnas_payload(base)

    if nombre == "consultar_datos":
        import asistente_query_plan as qp

        frase = str(contexto.get("ultima_pregunta") or args.get("metrica") or "")
        # Preferir plan estructurado desde la frase del usuario
        plan_ant = (
            qp.QueryPlan.from_dict(contexto.get("ultimo_plan"))
            if contexto.get("ultimo_plan")
            else None
        )
        base = tools.enriquecer_dataframe_consulta(
            df,
            dias_trabajo=dias_trabajo,
            rotacion=int(contexto.get("rotacion") or 4),
        )
        plan = qp.construir_plan(frase or str(args.get("metrica") or ""), base, plan_anterior=plan_ant)
        # Sobrescribir con args explícitos del modelo si vienen
        if args.get("metrica"):
            col, err = catalogo.resolver_columna(
                str(args["metrica"]), base, contexto_frase=frase
            )
            if err and not col:
                return {
                    "ok": False,
                    "mensaje": err,
                    "tipo": "consulta_datos",
                    "necesita_aclaracion": True,
                }
            if col:
                plan.metrics = [col]
        if args.get("metricas"):
            resolved = []
            for raw in list(args["metricas"]):
                c, e = catalogo.resolver_columna(str(raw), base, contexto_frase=frase)
                if c:
                    resolved.append(c)
            if resolved:
                plan.metrics = resolved
                plan.comparison = resolved if len(resolved) > 1 else []
        if args.get("dimension"):
            plan.dimensions = [str(args["dimension"])]
            if args.get("agregacion") and args["agregacion"] not in ("none", None, ""):
                plan.group_by = [str(args["dimension"])]
        if args.get("orden"):
            plan.sort_order = (
                "asc"
                if catalogo._norm(str(args["orden"]))
                in ("asc", "ascendente", "menor", "menor a mayor")
                else "desc"
            )
        if args.get("limite") is not None:
            plan.limit = int(args["limite"])
            plan.mostrar_todos = False
        if args.get("mostrar_todos"):
            plan.mostrar_todos = True
            plan.limit = None
        # Filtros del modelo + auto
        auto = catalogo.extraer_filtros_frase(frase, base) if frase else {}
        for clave in ("categoria", "proveedor", "subcategoria", "clase"):
            val = _heredar(clave) or auto.get(clave)
            if val:
                plan.filters = [f for f in plan.filters if f.column != clave]
                plan.filters.append(qp.FilterSpec(column=clave, operator="eq", value=val))
        if args.get("titulo"):
            plan.titulo = str(args["titulo"])
        if not plan.metrics:
            return {
                "ok": False,
                "mensaje": "Indique al menos una métrica válida.",
                "tipo": "consulta_datos",
            }
        return qp.ejecutar_plan(
            df,
            plan,
            dias_trabajo=dias_trabajo,
            rotacion=int(contexto.get("rotacion") or 4),
        )

    if nombre == "consultar_reposicion_por_minimo":
        # Compatibilidad: traduce a QueryPlan (filtro qty según mínimo > 0)
        import asistente_query_plan as qp

        frase = str(contexto.get("ultima_pregunta") or "") or (
            "Grafique los artículos que deben comprarse según el mínimo"
        )
        base = tools.enriquecer_dataframe_consulta(
            df, dias_trabajo=dias_trabajo, rotacion=4
        )
        plan = qp.construir_plan(frase, base)
        # Aplicar filtros explícitos del tool si vienen
        for col, key in (
            ("proveedor", "proveedor"),
            ("categoria", "categoria"),
            ("subcategoria", "subcategoria"),
        ):
            val = args.get(key)
            if val:
                plan.filters = [f for f in plan.filters if f.column != col]
                plan.filters.append(qp.FilterSpec(column=col, operator="eq", value=val))
        if args.get("limite"):
            plan.limit = int(args["limite"])
            plan.mostrar_todos = False
        if not plan.metrics:
            plan.metrics = [qp.COL_QTY_MINIMO]
            plan.derived_metrics = [qp.COL_QTY_MINIMO]
        return qp.ejecutar_plan(
            df, plan, dias_trabajo=dias_trabajo, rotacion=4
        )

    if nombre == "consultar_plan_compras":
        rot = args.get("rotacion_objetivo")
        if rot is None:
            rot = contexto.get("rotacion") or filtros_prev.get("rotacion_objetivo")
        return tools.construir_plan_compras(
            df,
            rotacion_objetivo=rot,
            dias_trabajo=dias_trabajo,
            proveedor=_heredar("proveedor"),
            sku=_parse_sku_arg(_heredar("sku")),
            categoria=_heredar("categoria"),
            incluir_transito=bool(_heredar("incluir_transito", True)),
            solo_compra_positiva=bool(_heredar("solo_compra_positiva", True)),
            ordenar_por=_heredar("ordenar_por", "monto compra"),
            limite=args.get("limite"),
            agrupacion=args.get("agrupacion") or _heredar("agrupacion"),
        )

    if nombre == "comparar_escenarios_compra":
        return tools.comparar_escenarios_compra(
            df,
            rotaciones=list(args.get("rotaciones") or []),
            dias_trabajo=dias_trabajo,
            proveedor=_heredar("proveedor"),
            categoria=_heredar("categoria"),
            incluir_transito=bool(_heredar("incluir_transito", True)),
        )

    if nombre == "resumir_compras_por_proveedor":
        rot = args.get("rotacion_objetivo")
        if rot is None:
            rot = contexto.get("rotacion") or 4
        return tools.resumir_compras_por_proveedor(
            df,
            rotacion_objetivo=rot,
            dias_trabajo=dias_trabajo,
            categoria=_heredar("categoria"),
            incluir_transito=bool(_heredar("incluir_transito", True)),
        )

    if nombre == "consultar_detalle_sku":
        return tools.consultar_detalle_sku(
            df,
            sku=_parse_sku_arg(args.get("sku")) or "",
            rotacion_objetivo=args.get("rotacion_objetivo") or contexto.get("rotacion"),
            dias_trabajo=dias_trabajo,
        )

    if nombre == "preparar_visualizacion":
        return tools.preparar_visualizacion(
            tipo=str(args.get("tipo") or "barras"),
            eje_x=str(args.get("eje_x") or "codigo"),
            eje_y=str(args.get("eje_y") or "rotacion"),
            titulo=args.get("titulo"),
            agrupar_por=args.get("agrupar_por"),
            top_n=args.get("top_n"),
            mostrar_todos=bool(args.get("mostrar_todos", False)),
            orden_desc=bool(args.get("orden_desc", True)),
            formato=args.get("formato"),
        )

    return {"ok": False, "mensaje": f"Herramienta no autorizada: {nombre}"}


def _actualizar_contexto(
    ctx: dict[str, Any], nombre: str, result: dict[str, Any], args: dict
) -> None:
    if nombre in (
        "consultar_plan_compras",
        "resumir_compras_por_proveedor",
        "consultar_detalle_sku",
        "consultar_datos",
        "consultar_reposicion_por_minimo",
        "comparar_escenarios_compra",
    ):
        res = result.get("resumen") or {}
        if res.get("rotacion_objetivo"):
            ctx["rotacion"] = res["rotacion_objetivo"]
        if nombre == "consultar_reposicion_por_minimo":
            # Limpiar herencia de rotación / filtros de compra_por_rotación
            ctx["filtros"] = {
                k: v
                for k, v in (res.get("filtros") or {}).items()
                if v is not None
            }
            ctx.pop("rotacion", None)
        else:
            filtros = dict(ctx.get("filtros") or {})
            for k in (
                "proveedor",
                "categoria",
                "subcategoria",
                "clase",
                "sku",
                "dimension",
                "metrica",
                "incluir_transito",
                "solo_compra_positiva",
                "ordenar_por",
                "agrupacion",
            ):
                if k in args and args[k] is not None:
                    filtros[k] = args[k]
                if k in res and res[k] is not None and k not in ("filtros",):
                    if k in ("metrica", "dimension"):
                        filtros[k] = res[k]
            if "rotacion_objetivo" in args and args["rotacion_objetivo"] is not None:
                filtros["rotacion_objetivo"] = args["rotacion_objetivo"]
            if isinstance(res.get("filtros"), dict):
                filtros.update(res["filtros"])
            ctx["filtros"] = filtros
        if result.get("plan"):
            ctx["ultimo_plan"] = result["plan"]
        if "_df" in result or "_df_completo" in result:
            ctx["ultimo_resultado"] = result
            hist = list(ctx.get("historial_resultados") or [])
            hist.append(result)
            ctx["historial_resultados"] = hist[-8:]
        if result.get("_grafico_spec"):
            ctx["ultimo_grafico_spec"] = result["_grafico_spec"]
            specs = list(ctx.get("historial_specs") or [])
            specs.append(result["_grafico_spec"])
            ctx["historial_specs"] = specs[-8:]
    if nombre == "preparar_visualizacion":
        ctx["ultimo_grafico_spec"] = result.get("spec") or {}
        specs = list(ctx.get("historial_specs") or [])
        specs.append(ctx["ultimo_grafico_spec"])
        ctx["historial_specs"] = specs[-8:]


def procesar_pregunta(
    pregunta: str,
    df: pd.DataFrame,
    *,
    api_key: str,
    dias_trabajo: int = 30,
    contexto: dict[str, Any] | None = None,
    on_status: Callable[[str], None] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Bucle Responses API + tools. Devuelve (texto_asistente, contexto_actualizado)."""
    from openai import OpenAI

    ctx = dict(contexto or {})
    ctx["ultima_pregunta"] = pregunta

    def _status(msg: str) -> None:
        if on_status:
            on_status(msg)

    # --- Vía rápida local: métricas generales (rotación, ventas, etc.) ---
    try:
        _status("Calculando localmente…")
        local = _resolver_consulta_local(
            pregunta, df, dias_trabajo=dias_trabajo, contexto=ctx
        )
    except Exception:
        local = None

    if local and local.get("accion") == "undo":
        return tools.sanitizar_texto_respuesta(
            "Para regresar al gráfico anterior use el botón "
            "«Regresar al resultado anterior» en el panel del asistente."
        ), ctx

    if local and local.get("necesita_aclaracion"):
        return tools.sanitizar_texto_respuesta(
            str(local.get("mensaje") or "¿Puede aclarar la unidad o el filtro?")
        ), ctx

    if local and local.get("ok"):
        nombre_ctx = (
            "consultar_reposicion_por_minimo"
            if local.get("tipo") == "reposicion_por_minimo"
            else "consultar_datos"
        )
        _actualizar_contexto(ctx, nombre_ctx, local, {})
        if local.get("plan"):
            ctx["ultimo_plan"] = local["plan"]
        if local.get("_grafico_spec"):
            ctx["ultimo_grafico_spec"] = local["_grafico_spec"]
        try:
            _status("Redactando explicación breve…")
            texto = _explicacion_breve(
                api_key=api_key, pregunta=pregunta, resultado=local
            )
        except Exception as exc:
            texto = tools.sanitizar_texto_respuesta(
                local.get("mensaje")
                or f"Resultado listo (explicación no disponible: {exc}). "
                "Revise la tabla y el gráfico abajo."
            )
        return tools.sanitizar_texto_respuesta(texto), ctx

    # --- Vía completa: function calling (compras u otras) ---
    client = OpenAI(api_key=api_key, timeout=TIMEOUT_OPENAI_SEG)
    model = obtener_modelo()

    pista = ""
    if ctx.get("rotacion") or ctx.get("filtros"):
        pista = (
            "\n[Contexto previo] "
            f"rotación={ctx.get('rotacion')}, "
            f"filtros={json.dumps(ctx.get('filtros') or {}, ensure_ascii=False)}"
        )
    if catalogo.es_consulta_compras(pregunta):
        pista += "\n[Enrutador] Consulta de COMPRAS → herramientas de compra."
    else:
        pista += (
            "\n[Enrutador] Consulta GENERAL → consultar_datos. "
            "No uses compras. No devuelvas Base64 ni listados largos."
        )

    input_items: list[Any] = [{"role": "user", "content": pregunta + pista}]

    _status("Consultando al asistente…")
    try:
        response = client.responses.create(
            model=model,
            instructions=INSTRUCCIONES,
            input=input_items,
            tools=TOOL_DEFS,
            temperature=0.2,
            max_output_tokens=600,
        )
    except Exception as exc:
        return (
            tools.sanitizar_texto_respuesta(
                f"No se pudo completar la consulta a tiempo o hubo un error: {exc}"
            ),
            ctx,
        )

    for _ in range(MAX_TURNS_TOOLS):
        calls = [
            item
            for item in (response.output or [])
            if getattr(item, "type", "") == "function_call"
        ]
        if not calls:
            break
        outputs: list[dict[str, Any]] = []
        for call in calls:
            nombre = getattr(call, "name", "") or ""
            raw_args = getattr(call, "arguments", "") or "{}"
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                args = {}
            _status(f"Ejecutando {nombre}…")
            try:
                result = ejecutar_herramienta(
                    nombre, args, df, dias_trabajo=dias_trabajo, contexto=ctx
                )
                _actualizar_contexto(ctx, nombre, result, args)
                outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": tools.serializar_para_modelo(result),
                    }
                )
            except Exception as exc:
                outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(
                            {"ok": False, "mensaje": str(exc)}, ensure_ascii=False
                        ),
                    }
                )
        try:
            response = client.responses.create(
                model=model,
                instructions=INSTRUCCIONES,
                previous_response_id=response.id,
                input=outputs,
                tools=TOOL_DEFS,
                temperature=0.2,
                max_output_tokens=600,
            )
        except Exception as exc:
            return (
                tools.sanitizar_texto_respuesta(
                    f"La consulta excedió el tiempo de espera: {exc}. "
                    "Revise si hay un resultado parcial en el panel."
                ),
                ctx,
            )

    texto = (getattr(response, "output_text", None) or "").strip()
    texto = tools.sanitizar_texto_respuesta(texto)
    if not texto:
        texto = "Listo. Revise la tabla y el gráfico con los datos oficiales."
    ctx["previous_response_id"] = getattr(response, "id", None)
    return texto, ctx
