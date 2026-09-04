"""Análisis ChatGPT para destrucción de valor (EVAI).

- Resumen HABLADO corto (global / categoría / subcategoría / SKU).
- Desglose IMPRESO abajo (listas largas; apto para catálogos grandes).
- Consulta puntual por código (texto, no voz).
Voz TTS fija: Fable.
"""
from __future__ import annotations

import json
import os
from typing import Any, Literal

import numpy as np
import pandas as pd
import streamlit as st

import destruccion_valor as dv

MODELO_TEXTO = "gpt-4o-mini"
MODELO_TTS = "gpt-4o-mini-tts"
VOZ_TTS = "fable"

NivelAnalisis = Literal["global", "categoria", "subcategoria", "sku"]

_SYSTEM_RESUMEN_VOZ = """\
Eres un analista senior de inventarios (LRI Inventory Pro). Redactas un RESUMEN ORAL
corto en español latinoamericano (45–90 segundos, ~90–180 palabras).
Usa SOLO el JSON. NO listes todos los SKUs. NO inventes números.

Enfoque: EVAI negativo = destrucción de valor.
Si hay Pareto 80/20 de categorías (o subcategorías), menciona las 3–4 que concentran
la mayor parte de la pérdida y el % acumulado.
Cierra con una invitación a profundizar en esas categorías en pantalla.
Sin markdown, sin viñetas, sin emojis: solo prosa hablada.
"""

_SYSTEM_CHAT_SKU = """\
Eres un consultor senior de inventarios (LRI Inventory Pro). Español latinoamericano.
NO inventes números: usa SOLO la ficha JSON.

Analiza: margen bruto vs grupo, ventas vs grupo, inventario/exceso vs grupo,
ICC vs grupo, rotación aproximada, GMROI y EVAI.
Indica distanciamiento del promedio y recomendaciones concretas.
"""


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
    ses = st.session_state.get("inv_openai_api_key")
    if isinstance(ses, str) and ses.strip():
        return ses.strip()
    return None


def _safe_float(v: Any) -> float | None:
    try:
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            return None
        if pd.isna(v):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _pct_vs(valor: float | None, promedio: float | None) -> float | None:
    if valor is None or promedio is None or promedio == 0:
        return None
    return round(100.0 * (valor - promedio) / abs(promedio), 1)


def pareto_grupos_destruccion(
    analisis: dv.AnalisisDestruccion,
    *,
    umbral: float = 0.80,
    max_grupos: int = 4,
) -> list[dict[str, Any]]:
    """Categorías/subcategorías que concentran ~80% de la pérdida (EVAI abs)."""
    if not analisis.grupos:
        return []
    orden = sorted(analisis.grupos, key=lambda g: abs(g.monto), reverse=True)
    total = sum(abs(g.monto) for g in orden) or 1.0
    acum = 0.0
    out: list[dict[str, Any]] = []
    for g in orden:
        parte = abs(g.monto) / total
        acum += parte
        out.append(
            {
                "nombre": g.nombre,
                "tipo": g.etiqueta_tipo,
                "n_productos": len(g.productos),
                "monto_usd": round(g.monto, 0),
                "pct_de_perdida_total": round(100.0 * parte, 1),
                "pct_acumulado": round(100.0 * acum, 1),
                "causa_mas_frecuente": g.causa_frecuente,
            }
        )
        if acum >= umbral or len(out) >= max_grupos:
            break
    return out


def hechos_resumen_voz(
    analisis: dv.AnalisisDestruccion,
    *,
    nivel: NivelAnalisis,
    foco: str | None = None,
    gmroi_promedio: float | None = None,
) -> dict[str, Any]:
    """JSON corto para el guion hablado (sin listar todos los SKUs)."""
    pareto = pareto_grupos_destruccion(analisis)
    base: dict[str, Any] = {
        "nivel": nivel,
        "foco": foco,
        "dimension": analisis.dimension_icc,
        "n_skus_destruyen_valor": analisis.n_productos,
        "monto_total_destruccion_usd": round(analisis.monto_total, 0),
        "gmroi_promedio_filtro": (
            None if gmroi_promedio is None else round(float(gmroi_promedio), 3)
        ),
        "pareto_80_20_grupos": pareto,
        "n_grupos_totales": len(analisis.grupos),
    }
    if nivel == "global":
        base["instruccion"] = (
            "Resumen global: cuántos SKUs, pérdida total, y las 3–4 categorías "
            "(o grupos) del Pareto 80/20. No enumerar códigos."
        )
        return base

    if nivel in ("categoria", "subcategoria") and foco:
        g = next((x for x in analisis.grupos if x.nombre == foco), None)
        top = []
        if g:
            for p in g.productos[:5]:
                top.append(
                    {
                        "codigo": p.codigo,
                        "evai_usd": round(p.evai, 0),
                        "causa": p.razon,
                    }
                )
            base["grupo"] = {
                "nombre": g.nombre,
                "n_productos": len(g.productos),
                "monto_usd": round(g.monto, 0),
                "causa_mas_frecuente": g.causa_frecuente,
                "top_5_mayor_perdida": top,
            }
        base["instruccion"] = (
            f"Resumen solo de {nivel} «{foco}»: pérdida, n SKUs, causa frecuente "
            "y mencione como máximo los 3 peores códigos (no la lista completa)."
        )
        return base

    if nivel == "sku" and foco:
        item = next((f for f in analisis.filas if f.codigo == foco), None)
        base["sku"] = (
            {
                "codigo": item.codigo,
                "evai_usd": round(item.evai, 0),
                "causa": item.razon,
                "grupo": item.grupo,
            }
            if item
            else {"codigo": foco, "nota": "Sin EVAI negativo o no está en el filtro"}
        )
        base["instruccion"] = (
            "Resumen oral muy breve de este SKU (EVAI, causa, qué priorizar). "
            "Sin listar otros artículos."
        )
    return base


def ficha_articulo_vs_grupo(
    tabla_sku: pd.DataFrame,
    codigo: str,
    *,
    dimension_icc: str = "categoria",
) -> dict[str, Any] | None:
    if tabla_sku.empty or "codigo" not in tabla_sku.columns:
        return None
    dim = dimension_icc if dimension_icc in ("categoria", "subcategoria") else "categoria"
    mask = tabla_sku["codigo"].astype(str) == str(codigo)
    if not mask.any():
        return None
    row = tabla_sku.loc[mask].iloc[0]
    grupo_nombre = str(row.get(dim, "—"))
    peers = tabla_sku[tabla_sku[dim].astype(str) == grupo_nombre]

    ventas = _safe_float(row.get("ventas totales"))
    margen = _safe_float(row.get("margen bruto total"))
    inv = _safe_float(row.get("valor inventario promedio"))
    inv_bultos = _safe_float(row.get("inventario promedio bultos"))
    icc = _safe_float(row.get("ICC asignado"))
    gmroi = _safe_float(row.get("GMROI"))
    evai = _safe_float(row.get("EVAI"))
    pct_margen = _safe_float(row.get("% margen bruto"))
    if pct_margen is None and ventas and ventas > 0 and margen is not None:
        pct_margen = margen / ventas
    ratio_inv = (inv / ventas) if (inv is not None and ventas and ventas > 0) else None
    rotacion = (ventas / inv) if (inv and inv > 0 and ventas is not None) else None

    def _media(col: str) -> float | None:
        if col not in peers.columns or peers.empty:
            return None
        m = float(peers[col].astype(float).mean())
        return m if np.isfinite(m) else None

    avg_ventas = _media("ventas totales")
    avg_margen = _media("margen bruto total")
    avg_inv = _media("valor inventario promedio")
    avg_icc = _media("ICC asignado")
    avg_gmroi = _media("GMROI")
    avg_evai = _media("EVAI")
    avg_pct = _media("% margen bruto")
    if avg_pct is None and avg_ventas and avg_ventas > 0 and avg_margen is not None:
        avg_pct = avg_margen / avg_ventas

    peers_ratio: list[float] = []
    for _, r in peers.iterrows():
        v = _safe_float(r.get("ventas totales"))
        i = _safe_float(r.get("valor inventario promedio"))
        if v and v > 0 and i is not None:
            peers_ratio.append(i / v)
    avg_ratio = float(np.mean(peers_ratio)) if peers_ratio else None

    return {
        "codigo": str(row.get("codigo")),
        "descripcion": str(row.get("descripcion", "")),
        "categoria": str(row.get("categoria", "")),
        "subcategoria": str(row.get("subcategoria", "")),
        "grupo_comparacion": dim,
        "grupo_nombre": grupo_nombre,
        "n_articulos_en_grupo": int(len(peers)),
        "articulo": {
            "ventas_totales": ventas,
            "margen_bruto": margen,
            "pct_margen_bruto": round(pct_margen, 4) if pct_margen is not None else None,
            "inventario_promedio_bultos": inv_bultos,
            "valor_inventario_promedio": inv,
            "ratio_inventario_sobre_ventas": (
                round(ratio_inv, 3) if ratio_inv is not None else None
            ),
            "rotacion_aprox": round(rotacion, 3) if rotacion is not None else None,
            "icc_asignado": icc,
            "GMROI": round(gmroi, 3) if gmroi is not None else None,
            "EVAI": round(evai, 0) if evai is not None else None,
            "destruye_valor": bool(evai is not None and evai < 0),
        },
        "promedios_del_grupo": {
            "ventas_totales": avg_ventas,
            "margen_bruto": avg_margen,
            "pct_margen_bruto": round(avg_pct, 4) if avg_pct is not None else None,
            "valor_inventario_promedio": avg_inv,
            "ratio_inventario_sobre_ventas": (
                round(avg_ratio, 3) if avg_ratio is not None else None
            ),
            "icc_asignado": avg_icc,
            "GMROI": round(avg_gmroi, 3) if avg_gmroi is not None else None,
            "EVAI": round(avg_evai, 0) if avg_evai is not None else None,
        },
        "desviacion_pct_vs_promedio_grupo": {
            "ventas": _pct_vs(ventas, avg_ventas),
            "margen_bruto": _pct_vs(margen, avg_margen),
            "pct_margen_bruto": _pct_vs(pct_margen, avg_pct),
            "valor_inventario": _pct_vs(inv, avg_inv),
            "ratio_inventario_sobre_ventas": _pct_vs(ratio_inv, avg_ratio),
            "icc": _pct_vs(icc, avg_icc),
            "GMROI": _pct_vs(gmroi, avg_gmroi),
            "EVAI": _pct_vs(evai, avg_evai),
        },
        "lectura_rapida": {
            "margen_bajo_vs_grupo": bool(
                pct_margen is not None and avg_pct is not None and pct_margen < avg_pct
            ),
            "ventas_bajas_vs_grupo": bool(
                ventas is not None and avg_ventas is not None and ventas < avg_ventas
            ),
            "inventario_alto_vs_grupo": bool(
                inv is not None and avg_inv is not None and inv > avg_inv
            ),
            "icc_alto_vs_grupo": bool(
                icc is not None and avg_icc is not None and icc > avg_icc
            ),
            "posible_exceso_inventario": bool(
                ratio_inv is not None and avg_ratio is not None and ratio_inv > avg_ratio
            ),
        },
    }


def generar_resumen_hablado(
    hechos: dict[str, Any],
    *,
    api_key: str,
) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=MODELO_TEXTO,
        temperature=0.35,
        messages=[
            {"role": "system", "content": _SYSTEM_RESUMEN_VOZ},
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


def responder_pregunta_sku(
    pregunta: str,
    ficha: dict[str, Any],
    *,
    api_key: str,
) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=MODELO_TEXTO,
        temperature=0.35,
        messages=[
            {"role": "system", "content": _SYSTEM_CHAT_SKU},
            {
                "role": "user",
                "content": (
                    f"Ficha JSON:\n{json.dumps(ficha, ensure_ascii=False)}\n\n"
                    f"Pregunta:\n{pregunta.strip()}"
                ),
            },
        ],
    )
    texto = (resp.choices[0].message.content or "").strip()
    if not texto:
        raise RuntimeError("ChatGPT devolvió un texto vacío.")
    return texto


def sintetizar_voz_openai(texto: str, *, api_key: str) -> bytes:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
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


def _render_clave_api() -> str | None:
    api_key = obtener_api_key()
    if api_key:
        return api_key
    st.warning(
        "Falta `OPENAI_API_KEY` en `.streamlit/secrets.toml` o péguela abajo."
    )
    clave = st.text_input(
        "OPENAI_API_KEY (sesión)",
        type="password",
        key="inv_openai_api_key_input",
    )
    if clave.strip():
        st.session_state["inv_openai_api_key"] = clave.strip()
        st.rerun()
    return None


def _df_impreso_destruccion(analisis: dv.AnalisisDestruccion) -> pd.DataFrame:
    filas = []
    for item in analisis.filas:
        filas.append(
            {
                "Código": item.codigo,
                "Grupo": item.grupo,
                "EVAI $": round(item.evai, 0),
                "Causa": item.razon,
            }
        )
    return pd.DataFrame(filas)


def _analisis_filtrado(
    analisis: dv.AnalisisDestruccion,
    *,
    nivel: NivelAnalisis,
    foco: str | None,
) -> dv.AnalisisDestruccion:
    if nivel == "global" or not foco:
        return analisis
    if nivel == "sku":
        filas = [f for f in analisis.filas if f.codigo == foco]
        grupos: list[dv.GrupoDestruccion] = []
        if filas:
            grupos = [
                dv.GrupoDestruccion(
                    nombre=filas[0].grupo,
                    etiqueta_tipo=(
                        "Categoría"
                        if analisis.dimension_icc == "categoria"
                        else "Subcategoría"
                    ),
                    productos=filas,
                )
            ]
        return dv.AnalisisDestruccion(
            filas=filas,
            grupos=grupos,
            dimension_icc=analisis.dimension_icc,
        )
    # categoria / subcategoria: los grupos del analisis ya están por dimension_icc;
    # si el usuario pide otra dimensión, filtramos por nombre de grupo coincidente.
    grupos = [g for g in analisis.grupos if g.nombre == foco]
    filas = [p for g in grupos for p in g.productos]
    return dv.AnalisisDestruccion(
        filas=filas,
        grupos=grupos,
        dimension_icc=analisis.dimension_icc,
    )


def render_panel_chatgpt(
    analisis: dv.AnalisisDestruccion,
    *,
    tabla_sku: pd.DataFrame | None = None,
    icc_por: str = "categoria",
    gmroi_promedio: float | None = None,
) -> None:
    """Resumen hablado + desglose impreso + consulta por SKU."""
    st.markdown("##### Análisis con ChatGPT")
    st.caption(
        "La **voz (Fable)** solo narra un **resumen** (global o del foco elegido). "
        "El detalle de SKUs queda **impreso** abajo — útil con catálogos grandes "
        "(p. ej. miles de artículos). Luego puede preguntar por un código concreto."
    )

    api_key = _render_clave_api()
    if not api_key:
        return

    st.markdown("###### ¿Qué desea analizar?")
    nivel_lbl = st.radio(
        "Alcance",
        options=[
            "Global (resumen + Pareto 80/20)",
            "Por categoría",
            "Por subcategoría",
            "Por SKU",
        ],
        horizontal=True,
        key="inv_chatgpt_nivel_lbl",
    )
    nivel_map = {
        "Global (resumen + Pareto 80/20)": "global",
        "Por categoría": "categoria",
        "Por subcategoría": "subcategoria",
        "Por SKU": "sku",
    }
    nivel: NivelAnalisis = nivel_map[nivel_lbl]  # type: ignore[assignment]

    foco: str | None = None
    if tabla_sku is not None and not tabla_sku.empty:
        cats = sorted(tabla_sku["categoria"].dropna().astype(str).unique().tolist())
        if nivel == "categoria":
            foco = st.selectbox("Categoría", cats, key="inv_chatgpt_foco_cat")
        elif nivel == "subcategoria":
            cat_ref = st.selectbox(
                "Categoría (para filtrar subcategorías)",
                ["— Todas —", *cats],
                key="inv_chatgpt_foco_cat_para_sub",
            )
            mask = (
                tabla_sku["categoria"].astype(str) == cat_ref
                if cat_ref != "— Todas —"
                else pd.Series(True, index=tabla_sku.index)
            )
            subs = sorted(
                tabla_sku.loc[mask, "subcategoria"].dropna().astype(str).unique().tolist()
            )
            if subs:
                foco = st.selectbox("Subcategoría", subs, key="inv_chatgpt_foco_sub")
            else:
                st.warning("No hay subcategorías en el filtro.")
        elif nivel == "sku":
            # Priorizar SKUs con EVAI negativo (mayor pérdida primero)
            neg = (
                tabla_sku[tabla_sku["EVAI"].astype(float) < 0]
                .sort_values("EVAI", ascending=True)
                if "EVAI" in tabla_sku.columns
                else tabla_sku
            )
            codigos_neg = neg["codigo"].astype(str).tolist()
            codigos_resto = [
                c
                for c in sorted(tabla_sku["codigo"].dropna().astype(str).unique())
                if c not in set(codigos_neg)
            ]
            opciones = codigos_neg + codigos_resto
            if opciones:
                foco = st.selectbox(
                    "Código (primero los de mayor destrucción de valor)",
                    opciones,
                    key="inv_chatgpt_foco_sku",
                )

    # Si el análisis está por categoría ICC pero usuario pide subcategoría,
    # reanalizar tabla a esa dimensión para el desglose impreso coherente.
    analisis_vista = analisis
    if (
        tabla_sku is not None
        and not tabla_sku.empty
        and nivel in ("categoria", "subcategoria")
        and foco
    ):
        dim_vista = "subcategoria" if nivel == "subcategoria" else "categoria"
        if dim_vista != analisis.dimension_icc:
            analisis_vista = dv.analizar_destruccion_valor(
                tabla_sku, dimension_icc=dim_vista
            )
        analisis_vista = _analisis_filtrado(
            analisis_vista, nivel=nivel, foco=foco
        )
    elif nivel == "sku" and foco:
        analisis_vista = _analisis_filtrado(analisis, nivel="sku", foco=foco)

    generar = st.button(
        "Generar resumen hablado (ChatGPT + Fable)",
        type="primary",
        use_container_width=True,
        key="inv_openai_generar_resumen",
    )

    hechos = hechos_resumen_voz(
        analisis if nivel == "global" else analisis_vista,
        nivel=nivel,
        foco=foco,
        gmroi_promedio=gmroi_promedio,
    )
    # Para global siempre usar el análisis completo (Pareto de todo el filtro)
    if nivel == "global":
        hechos = hechos_resumen_voz(
            analisis, nivel="global", foco=None, gmroi_promedio=gmroi_promedio
        )

    fingerprint = json.dumps(hechos, sort_keys=True, ensure_ascii=False)

    if generar:
        with st.spinner("ChatGPT prepara el resumen oral (sin leer todos los SKUs)…"):
            try:
                guion = generar_resumen_hablado(hechos, api_key=api_key)
                audio = sintetizar_voz_openai(guion, api_key=api_key)
                st.session_state["inv_openai_guion"] = guion
                st.session_state["inv_openai_audio"] = audio
                st.session_state["inv_openai_fp"] = fingerprint
            except Exception as exc:
                st.error(f"No se pudo generar el resumen: {exc}")
                return

    guion = st.session_state.get("inv_openai_guion")
    audio = st.session_state.get("inv_openai_audio")
    if guion and audio and st.session_state.get("inv_openai_fp") == fingerprint:
        with st.expander("Ver texto del resumen hablado", expanded=False):
            st.write(guion)
        st.audio(audio, format="audio/mp3")
        st.caption("Voz fija **Fable** · solo resumen (no enumera el catálogo completo).")
    else:
        st.caption(
            "Pulse **Generar resumen hablado** para oír el resumen del alcance elegido."
        )

    # —— Desglose IMPRESO ——
    st.divider()
    st.markdown("##### Desglose impreso (sin voz)")
    if nivel == "global":
        pareto = pareto_grupos_destruccion(analisis)
        st.markdown(
            f"**Resumen:** {analisis.n_productos:,} SKU(s) con EVAI negativo · "
            f"pérdida total **−${abs(analisis.monto_total):,.0f}**"
        )
        if pareto:
            st.markdown("**Categorías / grupos que concentran ~80% de la pérdida:**")
            st.dataframe(pd.DataFrame(pareto), use_container_width=True, hide_index=True)
        st.markdown("**Todos los SKUs con destrucción de valor** (mayor pérdida primero):")
        df_imp = _df_impreso_destruccion(analisis)
        if df_imp.empty:
            st.info("No hay SKUs con EVAI negativo en el filtro.")
        else:
            st.dataframe(df_imp, use_container_width=True, hide_index=True, height=320)
    else:
        st.markdown(
            f"**Alcance:** {nivel_lbl}"
            + (f" · **{foco}**" if foco else "")
            + f" · {analisis_vista.n_productos:,} SKU(s) · "
            f"pérdida **−${abs(analisis_vista.monto_total):,.0f}**"
        )
        df_imp = _df_impreso_destruccion(analisis_vista)
        if df_imp.empty:
            st.info("No hay destrucción de valor en este alcance.")
        else:
            st.dataframe(df_imp, use_container_width=True, hide_index=True, height=320)

    # —— Consulta por SKU (texto) ——
    st.divider()
    st.markdown("##### Preguntar por un SKU (texto, no hablado)")
    st.caption(
        "Ideal para los de **mayor pérdida EVAI**. Ejemplo: "
        "«¿Qué habría que hacer con este código?»"
    )
    if tabla_sku is None or tabla_sku.empty:
        return

    neg = (
        tabla_sku[tabla_sku["EVAI"].astype(float) < 0].sort_values("EVAI", ascending=True)
        if "EVAI" in tabla_sku.columns
        else tabla_sku
    )
    codigos_chat = neg["codigo"].astype(str).tolist()
    if not codigos_chat:
        codigos_chat = sorted(tabla_sku["codigo"].dropna().astype(str).unique().tolist())
    if not codigos_chat:
        return

    # Si hay foco SKU o desglose, preseleccionar el peor
    default_idx = 0
    if nivel == "sku" and foco and foco in codigos_chat:
        default_idx = codigos_chat.index(foco)

    c1, c2 = st.columns([1, 2])
    with c1:
        codigo_q = st.selectbox(
            "Código",
            codigos_chat,
            index=min(default_idx, len(codigos_chat) - 1),
            key="inv_chatgpt_ask_sku",
        )
    with c2:
        pregunta = st.text_input(
            "Pregunta",
            value=(
                f"¿Qué habría que hacer con el código {codigo_q}? "
                "Compara margen, ventas, inventario e ICC vs el promedio del grupo."
            ),
            key="inv_chatgpt_ask_q",
        )

    if "inv_chatgpt_historial" not in st.session_state:
        st.session_state["inv_chatgpt_historial"] = []

    b1, b2 = st.columns(2)
    with b1:
        enviar = st.button(
            "Preguntar a ChatGPT",
            type="primary",
            use_container_width=True,
            key="inv_chatgpt_ask_send",
        )
    with b2:
        if st.button("Limpiar respuestas", use_container_width=True, key="inv_chatgpt_ask_clear"):
            st.session_state["inv_chatgpt_historial"] = []
            st.rerun()

    if enviar:
        ficha = ficha_articulo_vs_grupo(tabla_sku, codigo_q, dimension_icc=icc_por)
        if not ficha:
            st.error(f"No se encontró {codigo_q}.")
        elif not (pregunta or "").strip():
            st.warning("Escriba una pregunta.")
        else:
            with st.spinner(f"Analizando {codigo_q}…"):
                try:
                    resp = responder_pregunta_sku(pregunta, ficha, api_key=api_key)
                    st.session_state["inv_chatgpt_historial"].append(
                        {
                            "codigo": codigo_q,
                            "pregunta": pregunta.strip(),
                            "respuesta": resp,
                            "ficha": ficha,
                        }
                    )
                except Exception as exc:
                    st.error(f"Error ChatGPT: {exc}")

    for i, item in enumerate(reversed(st.session_state.get("inv_chatgpt_historial") or []), 1):
        with st.expander(
            f"{item['codigo']} — {item['pregunta'][:80]}",
            expanded=(i == 1),
        ):
            st.write(item["respuesta"])
            with st.expander("Ficha numérica", expanded=False):
                st.json(item.get("ficha") or {})
