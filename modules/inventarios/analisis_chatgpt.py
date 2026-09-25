"""Análisis ChatGPT para destrucción de valor (EVAI).

- Resumen HABLADO corto (global / categoría / subcategoría / SKU).
- Desglose IMPRESO abajo (listas largas; apto para catálogos grandes).
- Consulta puntual por código (texto, no voz).
Voz TTS fija: Fable.
"""
from __future__ import annotations

import json
import os
import re
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


def _normalizar_api_key(raw: str | None) -> str | None:
    """Quita espacios/comillas que suelen pegarse al copiar la clave."""
    if not isinstance(raw, str):
        return None
    key = raw.strip()
    if (key.startswith('"') and key.endswith('"')) or (
        key.startswith("'") and key.endswith("'")
    ):
        key = key[1:-1].strip()
    # Evita restos de markdown / BOM al pegar.
    key = key.lstrip("\ufeff").strip()
    return key or None


def obtener_api_key() -> str | None:
    env = _normalizar_api_key(os.environ.get("OPENAI_API_KEY"))
    if env:
        return env
    try:
        secret = st.secrets.get("OPENAI_API_KEY", "")
        secret_n = _normalizar_api_key(secret if isinstance(secret, str) else None)
        if secret_n:
            return secret_n
    except Exception:
        pass
    ses = _normalizar_api_key(st.session_state.get("inv_openai_api_key"))
    if ses:
        return ses
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
        try:
            audio = client.audio.speech.create(
                model="tts-1-hd",
                voice="fable",
                input=texto,
                response_format="mp3",
            )
            return audio.content
        except Exception as exc:
            raise RuntimeError(
                f"No se pudo sintetizar audio ({type(exc).__name__}: {exc}). "
                "El texto del requerimiento sí puede generarse sin audio."
            ) from exc


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
        help="Pegue solo la clave (sk-…), sin comillas ni espacios.",
    )
    clave_n = _normalizar_api_key(clave)
    if clave_n:
        st.session_state["inv_openai_api_key"] = clave_n
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


# ---------------------------------------------------------------------------
# Requerimientos de compra (SKUs a comprar)
# ---------------------------------------------------------------------------
_SYSTEM_REQUERIMIENTO_COMPRA = """\
Eres un analista senior de reposición / compras (LRI Inventory Pro).
Redactas un REQUERIMIENTO DE COMPRA en español latinoamericano, claro y accionable.

REGLAS CRÍTICAS:
- Usa SOLO los datos del JSON de entrada. NO inventes SKUs ni cantidades.
- Responde ÚNICAMENTE en texto Markdown legible para humanos.
- PROHIBIDO devolver JSON, código, llaves { }, o estructuras tipo API.
- PROHIBIDO envolver la respuesta en ```json o ```.
- OBLIGATORIO: incluir la lista de ÍTEMS / SKUs individuales (código + descripción
  + cantidad + proveedor). NO te quedes solo en categoría, subcategoría o proveedor.

Estructura del texto (títulos Markdown, no claves JSON):
## Encabezado
Alcance (exactamente el de «vista» del JSON), rotación deseada y meses de inventario objetivo.

## Resumen ejecutivo
Cuántos SKUs, suma a comprar, 2–4 hallazgos clave en viñetas.

## Lista de ítems / SKUs a comprar
Una viñeta por CADA SKU del JSON (campo «skus»): código — descripción — cantidad sugerida — proveedor — categoría/subcategoría si vienen.
Orden mayor → menor cantidad. Si la nota indica truncado, detalla todos los del JSON y menciona cuántos faltan.

## Agrupaciones
Si el JSON trae por_proveedor / por_categoria / por_subcategoria, resume en viñetas DESPUÉS de la lista de SKUs.

## Cierre
2–3 recomendaciones operativas (pedido, lead time, riesgo de quiebre).
"""

_SYSTEM_ANALISIS_COMPRA_VOZ = """\
Eres un analista de compras (LRI Inventory Pro). Redactas un RESUMEN ORAL corto
en español latinoamericano (45–90 segundos, ~90–180 palabras).
Usa SOLO el JSON de entrada. NO inventes SKUs ni cantidades.
PROHIBIDO devolver JSON o markdown: solo prosa hablada (oraciones seguidas).

Di claramente:
1) El alcance pedido (categoría, subcategoría, proveedor o SKU) según «vista».
2) Cuántos SKUs hay que comprar y la suma de cantidad a comprar.
3) Lista oral de los artículos (ítems/SKUs): menciona código o descripción corta
   y cantidad de CADA uno si hay ≤12; si hay más, los 8 de mayor cantidad y di
   cuántos quedan. NO te limites a hablar solo de categorías o proveedores.
4) Una frase de cierre con el siguiente paso (revisar pedido / proveedor).
"""

_CLAVE_REQ_TEXTO = "inv_skus_chatgpt_req_texto"
_CLAVE_REQ_AUDIO = "inv_skus_chatgpt_req_audio"
_CLAVE_REQ_FP = "inv_skus_chatgpt_req_fp"
# Alias públicos (sidebar / otras vistas).
CLAVE_REQ_TEXTO = _CLAVE_REQ_TEXTO
CLAVE_REQ_AUDIO = _CLAVE_REQ_AUDIO
CLAVE_REQ_FP = _CLAVE_REQ_FP


def hechos_requerimiento_compra(
    tabla: pd.DataFrame,
    *,
    titulo_vista: str,
    rotacion: int,
    dias_trabajo: int,
    col_cantidad: str = "cantidad a comprar",
) -> dict[str, Any]:
    """JSON factual para el prompt de requerimiento de compra."""
    t = tabla.copy()
    if col_cantidad not in t.columns:
        raise ValueError(f"Falta columna «{col_cantidad}».")
    t[col_cantidad] = pd.to_numeric(t[col_cantidad], errors="coerce").fillna(0)
    t = t.loc[t[col_cantidad] > 0].sort_values(col_cantidad, ascending=False)

    def _fila(r: pd.Series) -> dict[str, Any]:
        out: dict[str, Any] = {
            "codigo": str(r.get("codigo", "")),
            "descripcion": str(r.get("descripcion", ""))[:80],
            "cantidad_a_comprar": round(float(r[col_cantidad]), 2),
        }
        for c in (
            "categoria",
            "subcategoria",
            "proveedor",
            "inventario final bulto",
            "cantidad minima de inventario",
            "inventario objetivo",
            "pronostico ajustado",
        ):
            if c not in r.index or pd.isna(r.get(c)):
                continue
            v = r.get(c)
            if isinstance(v, (int, float, np.floating, np.integer)):
                out[c.replace(" ", "_")] = round(float(v), 2)
            else:
                out[c.replace(" ", "_")] = str(v)
        return out

    skus = [_fila(r) for _, r in t.iterrows()]
    por_proveedor: list[dict[str, Any]] = []
    if "proveedor" in t.columns:
        g = (
            t.groupby(t["proveedor"].astype(str), dropna=False)[col_cantidad]
            .agg(["sum", "count"])
            .reset_index()
            .sort_values("sum", ascending=False)
        )
        por_proveedor = [
            {
                "proveedor": str(row["proveedor"]),
                "skus": int(row["count"]),
                "suma_cantidad": round(float(row["sum"]), 2),
            }
            for _, row in g.iterrows()
        ]
    por_categoria: list[dict[str, Any]] = []
    if "categoria" in t.columns:
        g = (
            t.groupby(t["categoria"].astype(str), dropna=False)[col_cantidad]
            .agg(["sum", "count"])
            .reset_index()
            .sort_values("sum", ascending=False)
        )
        por_categoria = [
            {
                "categoria": str(row["categoria"]),
                "skus": int(row["count"]),
                "suma_cantidad": round(float(row["sum"]), 2),
            }
            for _, row in g.iterrows()
        ]
    por_subcategoria: list[dict[str, Any]] = []
    if "subcategoria" in t.columns:
        g = (
            t.groupby(t["subcategoria"].astype(str), dropna=False)[col_cantidad]
            .agg(["sum", "count"])
            .reset_index()
            .sort_values("sum", ascending=False)
        )
        por_subcategoria = [
            {
                "subcategoria": str(row["subcategoria"]),
                "skus": int(row["count"]),
                "suma_cantidad": round(float(row["sum"]), 2),
            }
            for _, row in g.iterrows()
        ]

    rot = max(1, int(rotacion))
    lim_skus = 80
    return {
        "vista": titulo_vista,
        "rotacion_deseada": rot,
        "meses_inventario_objetivo": round(12.0 / rot, 2),
        "dias_trabajo_mes": int(dias_trabajo),
        "n_skus": int(len(skus)),
        "suma_cantidad_a_comprar": round(float(t[col_cantidad].sum()), 2),
        "por_proveedor": por_proveedor,
        "por_categoria": por_categoria,
        "por_subcategoria": por_subcategoria,
        # Lista de ÍTEMS (prioridad del análisis; no solo agregados).
        "skus": skus[:lim_skus],
        "instruccion": (
            "Debes listar TODOS los SKUs del arreglo «skus» en la respuesta. "
            "Las agrupaciones son complementarias, no sustituyen la lista de ítems."
        ),
        "nota": (
            f"Lista truncada a {lim_skus} de {len(skus)} SKUs (orden mayor→menor)."
            if len(skus) > lim_skus
            else None
        ),
    }


def _parece_json_respuesta(texto: str) -> bool:
    t = (texto or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.I)
        t = re.sub(r"\s*```$", "", t)
    t = t.strip()
    if not (t.startswith("{") and t.endswith("}")):
        return False
    claves = (
        "lista_priorizada_productos",
        "resumen_ejecutivo",
        "encabezado",
        "agrupaciones",
        '"skus"',
    )
    return any(k in t for k in claves)


def _parse_json_respuesta(texto: str) -> dict[str, Any] | None:
    t = (texto or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.I)
        t = re.sub(r"\s*```$", "", t)
    t = t.strip()
    try:
        obj = json.loads(t)
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _markdown_desde_respuesta_json(obj: dict[str, Any]) -> str:
    """Convierte la respuesta JSON errónea del modelo a Markdown legible."""
    lineas: list[str] = ["## Encabezado"]
    enc = obj.get("encabezado") or {}
    if isinstance(enc, dict):
        if enc.get("alcance"):
            lineas.append(f"- Alcance: **{enc['alcance']}**")
        if enc.get("rotacion_deseada") is not None:
            lineas.append(f"- Rotación deseada: **{enc['rotacion_deseada']}**× / año")
        if enc.get("meses_inventario_objetivo") is not None:
            lineas.append(
                f"- Meses inventario objetivo: **{enc['meses_inventario_objetivo']}**"
            )
    else:
        lineas.append(f"- {enc}")

    res = obj.get("resumen_ejecutivo") or {}
    lineas.extend(["", "## Resumen ejecutivo"])
    if isinstance(res, dict):
        if res.get("total_skus") is not None:
            lineas.append(f"- SKUs a comprar: **{res['total_skus']}**")
        if res.get("suma_a_comprar") is not None:
            lineas.append(f"- Suma cantidad a comprar: **{res['suma_a_comprar']:,.2f}**")
        for h in res.get("hallazgos_clave") or []:
            lineas.append(f"- {h}")
    else:
        lineas.append(f"- {res}")

    lista = obj.get("lista_priorizada_productos") or obj.get("skus") or []
    lineas.extend(["", "## Lista de ítems / SKUs a comprar"])
    for s in lista:
        if not isinstance(s, dict):
            continue
        cant = s.get("cantidad_sugerida", s.get("cantidad_a_comprar", ""))
        try:
            cant_txt = f"{float(cant):,.2f}"
        except Exception:
            cant_txt = str(cant)
        prov = s.get("proveedor") or ""
        lineas.append(
            f"- `{s.get('codigo', '')}` — {s.get('descripcion', '')} — **{cant_txt}**"
            + (f" — {prov}" if prov else "")
        )

    agrup = obj.get("agrupaciones") or {}
    if isinstance(agrup, dict):
        por_p = agrup.get("por_proveedor") or []
        if por_p:
            lineas.extend(["", "## Por proveedor"])
            for g in por_p:
                if not isinstance(g, dict):
                    continue
                lineas.append(
                    f"- **{g.get('proveedor')}**: {g.get('total_skus', g.get('skus'))} SKUs · "
                    f"suma {g.get('suma_cantidad', 0):,.2f}"
                )
        por_c = agrup.get("por_categoria") or []
        if por_c:
            lineas.extend(["", "## Por categoría"])
            for g in por_c:
                if not isinstance(g, dict):
                    continue
                lineas.append(
                    f"- **{g.get('categoria')}**: {g.get('total_skus', g.get('skus'))} SKUs · "
                    f"suma {g.get('suma_cantidad', 0):,.2f}"
                )

    cierre = obj.get("cierre") or {}
    lineas.extend(["", "## Cierre"])
    recs = []
    if isinstance(cierre, dict):
        recs = cierre.get("recomendaciones_operativas") or []
    if recs:
        for r in recs:
            lineas.append(f"- {r}")
    else:
        lineas.append("- Revisar y confirmar el pedido con el alcance indicado.")
    return "\n".join(lineas)


def _sanear_texto_requerimiento(
    texto: str, hechos: dict[str, Any] | None = None
) -> str:
    """Si el modelo (o la sesión) guardó JSON, lo convierte a Markdown."""
    if not _parece_json_respuesta(texto):
        return texto
    if hechos:
        return _requerimiento_markdown_desde_hechos(hechos)
    obj = _parse_json_respuesta(texto)
    if obj:
        return _markdown_desde_respuesta_json(obj)
    return texto


def _requerimiento_markdown_desde_hechos(hechos: dict[str, Any]) -> str:
    """Fallback local: arma el requerimiento en Markdown sin depender del modelo."""
    lineas: list[str] = [
        "## Encabezado",
        f"- Alcance: **{hechos.get('vista', 'SKUs a comprar')}**",
        f"- Rotación deseada: **{hechos.get('rotacion_deseada')}**× / año",
        f"- Meses inventario objetivo: **{hechos.get('meses_inventario_objetivo')}**",
        "",
        "## Resumen ejecutivo",
        f"- SKUs a comprar: **{hechos.get('n_skus', 0)}**",
        f"- Suma cantidad a comprar: **{hechos.get('suma_cantidad_a_comprar', 0):,.2f}**",
        "",
        "## Lista de ítems / SKUs a comprar",
    ]
    for s in hechos.get("skus") or []:
        lineas.append(
            f"- `{s.get('codigo', '')}` — {s.get('descripcion', '')} — "
            f"**{s.get('cantidad_a_comprar', 0):,.2f}**"
            + (f" — {s['proveedor']}" if s.get("proveedor") else "")
            + (
                f" · {s.get('categoria', '')}/{s.get('subcategoria', '')}"
                if s.get("categoria") or s.get("subcategoria")
                else ""
            )
        )
    if hechos.get("nota"):
        lineas.append(f"\n_{hechos['nota']}_")
    por_p = hechos.get("por_proveedor") or []
    if por_p:
        lineas.extend(["", "## Por proveedor"])
        for g in por_p:
            lineas.append(
                f"- **{g.get('proveedor')}**: {g.get('skus')} SKUs · "
                f"suma {g.get('suma_cantidad', 0):,.2f}"
            )
    por_c = hechos.get("por_categoria") or []
    if por_c:
        lineas.extend(["", "## Por categoría"])
        for g in por_c:
            lineas.append(
                f"- **{g.get('categoria')}**: {g.get('skus')} SKUs · "
                f"suma {g.get('suma_cantidad', 0):,.2f}"
            )
    lineas.extend(
        [
            "",
            "## Cierre",
            "- Revisar y confirmar el pedido con el alcance indicado.",
            "- Considerar lead time del proveedor antes de emitir OC.",
            "- Priorizar SKUs con mayor cantidad a comprar para evitar quiebres.",
        ]
    )
    return "\n".join(lineas)


def generar_requerimiento_compra(
    hechos: dict[str, Any],
    *,
    api_key: str,
) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    try:
        resp = client.chat.completions.create(
            model=MODELO_TEXTO,
            temperature=0.25,
            messages=[
                {"role": "system", "content": _SYSTEM_REQUERIMIENTO_COMPRA},
                {
                    "role": "user",
                    "content": (
                        "Redacta el requerimiento en Markdown (NO en JSON). "
                        "Datos de entrada:\n"
                        f"{json.dumps(hechos, ensure_ascii=False)}"
                    ),
                },
            ],
        )
    except Exception as exc:
        msg = str(exc)
        low = msg.lower()
        if "401" in msg or "invalid_api_key" in low or "incorrect api key" in low:
            raise RuntimeError(
                "OpenAI rechazó la clave (401). Revise OPENAI_API_KEY en "
                ".streamlit/secrets.toml (sin comillas)."
            ) from exc
        if "429" in msg or "insufficient_quota" in low:
            raise RuntimeError(
                "Sin crédito/cuota en OpenAI (429). Revise billing en platform.openai.com."
            ) from exc
        raise RuntimeError(f"Error OpenAI: {exc}") from exc
    texto = (resp.choices[0].message.content or "").strip()
    if not texto:
        raise RuntimeError("ChatGPT devolvió un texto vacío.")
    return _sanear_texto_requerimiento(texto, hechos)


def generar_analisis_compra_hablado(
    hechos: dict[str, Any],
    *,
    api_key: str,
) -> str:
    """Resumen oral corto de los SKUs a comprar del filtro pedido."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    try:
        resp = client.chat.completions.create(
            model=MODELO_TEXTO,
            temperature=0.35,
            messages=[
                {"role": "system", "content": _SYSTEM_ANALISIS_COMPRA_VOZ},
                {
                    "role": "user",
                    "content": (
                        "Narra en prosa hablada (nunca JSON) el análisis de compra "
                        f"con estos datos:\n{json.dumps(hechos, ensure_ascii=False)}"
                    ),
                },
            ],
        )
    except Exception as exc:
        msg = str(exc)
        low = msg.lower()
        if "401" in msg or "invalid_api_key" in low or "incorrect api key" in low:
            raise RuntimeError(
                "OpenAI rechazó la clave (401). Revise OPENAI_API_KEY."
            ) from exc
        if "429" in msg or "insufficient_quota" in low:
            raise RuntimeError(
                "Sin crédito/cuota en OpenAI (429)."
            ) from exc
        raise RuntimeError(f"Error OpenAI: {exc}") from exc
    texto = (resp.choices[0].message.content or "").strip()
    if not texto:
        raise RuntimeError("ChatGPT devolvió un texto vacío.")
    if _parece_json_respuesta(texto):
        # Narración mínima desde hechos si el modelo devolvió JSON.
        skus = hechos.get("skus") or []
        top = skus[:5]
        partes = [
            f"Para {hechos.get('vista', 'la compra')}: hay {hechos.get('n_skus', 0)} "
            f"SKUs a comprar, con una suma de "
            f"{hechos.get('suma_cantidad_a_comprar', 0):,.1f} unidades.",
        ]
        if top:
            detallados = "; ".join(
                f"{s.get('descripcion', s.get('codigo'))} "
                f"({s.get('cantidad_a_comprar', 0):,.1f})"
                for s in top
            )
            partes.append(f"Los principales son: {detallados}.")
        partes.append("Revise el pedido con el proveedor o categoría indicados.")
        return " ".join(partes)
    return texto


def render_panel_requerimiento_compra(
    tabla: pd.DataFrame,
    *,
    titulo_vista: str,
    rotacion: int,
    dias_trabajo: int,
    col_cantidad: str = "cantidad a comprar",
) -> None:
    """Panel ChatGPT: requerimiento de compra según la vista filtrada."""
    st.markdown("##### ChatGPT · requerimiento de compra")
    st.caption(
        "Genera la **lista / requerimiento de productos a comprar** según la vista "
        "actual (SKU, categoría, subcategoría o proveedor). Usa la misma clave OpenAI "
        "que GMROI (secrets o sesión)."
    )

    api_key = _render_clave_api()
    if not api_key:
        return

    if tabla is None or tabla.empty or col_cantidad not in tabla.columns:
        st.info("No hay SKUs a comprar en esta selección para generar el requerimiento.")
        return

    hechos = hechos_requerimiento_compra(
        tabla,
        titulo_vista=titulo_vista,
        rotacion=rotacion,
        dias_trabajo=dias_trabajo,
        col_cantidad=col_cantidad,
    )
    fingerprint = json.dumps(hechos, ensure_ascii=False, sort_keys=True)

    c1, c2 = st.columns(2)
    with c1:
        gen = st.button(
            "Generar requerimiento con ChatGPT",
            type="primary",
            use_container_width=True,
            key="inv_skus_chatgpt_generar",
        )
    with c2:
        con_voz = st.checkbox(
            "También generar audio (Fable)",
            value=False,
            key="inv_skus_chatgpt_voz",
            help="Narración corta del requerimiento (opcional).",
        )

    if gen:
        with st.spinner("ChatGPT redactando el requerimiento de compra…"):
            try:
                texto = generar_requerimiento_compra(hechos, api_key=api_key)
                st.session_state[_CLAVE_REQ_TEXTO] = texto
                st.session_state[_CLAVE_REQ_FP] = fingerprint
                st.session_state[_CLAVE_REQ_AUDIO] = None
                if con_voz:
                    try:
                        resumen_voz = texto if len(texto) <= 2200 else texto[:2200] + "…"
                        st.session_state[_CLAVE_REQ_AUDIO] = sintetizar_voz_openai(
                            resumen_voz, api_key=api_key
                        )
                    except Exception as exc_voz:
                        st.warning(f"Texto OK; audio no disponible: {exc_voz}")
                st.success("Requerimiento generado.")
            except Exception as exc:
                st.error(f"Error ChatGPT: {exc}")

    texto = st.session_state.get(_CLAVE_REQ_TEXTO)
    audio = st.session_state.get(_CLAVE_REQ_AUDIO)
    if texto and _parece_json_respuesta(str(texto)):
        # Sesión antigua con JSON crudo: convertir y reescribir.
        texto = _sanear_texto_requerimiento(str(texto), hechos)
        st.session_state[_CLAVE_REQ_TEXTO] = texto
    if texto and st.session_state.get(_CLAVE_REQ_FP) == fingerprint:
        st.markdown("###### Requerimiento")
        st.markdown(texto)
        st.download_button(
            "Descargar requerimiento (.txt)",
            data=texto.encode("utf-8"),
            file_name="requerimiento_compra_skus.txt",
            mime="text/plain",
            use_container_width=True,
            key="inv_skus_chatgpt_dl",
        )
        if audio:
            st.audio(audio, format="audio/mp3")
        with st.expander("Datos enviados a ChatGPT (JSON)", expanded=False):
            st.json(hechos)
    elif texto:
        if _parece_json_respuesta(str(texto)):
            texto = _sanear_texto_requerimiento(str(texto), None)
            st.session_state[_CLAVE_REQ_TEXTO] = texto
        st.caption(
            "Hay un requerimiento anterior de otra vista/filtro. "
            "Genere de nuevo para actualizarlo."
        )
        with st.expander("Ver requerimiento anterior", expanded=False):
            st.markdown(texto)
