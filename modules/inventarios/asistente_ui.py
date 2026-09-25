"""UI Streamlit: Asistente Inteligente de Inventarios LRI."""
from __future__ import annotations

import io
from typing import Any

import pandas as pd
import streamlit as st

import asistente_charts as charts
import asistente_columnas as cols
import asistente_openai as oa
import asistente_tools as tools
import skus_a_comprar as skus

VISTA_NOMBRE = "Asistente Inteligente de Inventarios LRI"
CLAVE_ESTADO = "lri_asistente_estado"


def _parece_basura_tecnica(texto: str) -> bool:
    t = (texto or "").strip().lower()
    if not t:
        return True
    if "data:image" in t or "base64," in t:
        return True
    if t.startswith("ivbor") or (len(t) > 4000 and " " not in t[:200]):
        return True
    return False


def _estado() -> dict[str, Any]:
    if CLAVE_ESTADO not in st.session_state:
        st.session_state[CLAVE_ESTADO] = {
            "messages": [],
            "filtros": {},
            "rotacion": int(
                st.session_state.get(
                    skus.CLAVE_ROTACION, skus._ROTACION_DESEADA_DEFAULT
                )
            ),
            "ultimo_resultado": None,
            "historial_resultados": [],
            "ultimo_grafico_spec": None,
            "historial_specs": [],
        }
    return st.session_state[CLAVE_ESTADO]


def _fmt_moneda(v: float) -> str:
    return f"$ {v:,.0f}"


def _tabla_mostrar(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    preferidas = [c for c in cols.COLUMNAS_TABLA_COMPRA if c in df.columns]
    if preferidas and cols.COL_QTY in df.columns:
        extras = [c for c in df.columns if c not in preferidas]
        return df.loc[:, preferidas + extras]
    return df


def _metricas(resumen: dict[str, Any] | None) -> None:
    if not resumen:
        return
    if resumen.get("intencion") == "reposicion_por_minimo":
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Criterio", "Según mínimo")
        c2.metric("Artículos", f"{int(resumen.get('n_skus') or 0):,}")
        c3.metric(
            "Total a comprar",
            f"{float(resumen.get('suma_unidades') or 0):,.1f}",
        )
        c4.metric("Rotación", "No aplicada")
        return
    if resumen.get("rotacion_objetivo") is not None and resumen.get("monto_total") is not None:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Rotación objetivo", f"{resumen.get('rotacion_objetivo', '—')}")
        c2.metric("SKUs", f"{int(resumen.get('n_skus') or 0):,}")
        c3.metric("Unidades", f"{float(resumen.get('suma_unidades') or 0):,.1f}")
        c4.metric("Monto total", _fmt_moneda(float(resumen.get("monto_total") or 0)))
        adv = resumen.get("advertencia_sin_costo")
        if adv:
            st.warning(adv)
        return
    fmt = resumen.get("formato")
    unidad = resumen.get("unidad")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Métrica",
        str(
            resumen.get("metrica_legible")
            or (
                ", ".join(resumen["metricas"])
                if resumen.get("metricas")
                else resumen.get("metrica")
            )
            or "—"
        ),
    )
    n_filas = resumen.get("n_filas_filtradas")
    if n_filas is None:
        n_filas = resumen.get("n_filas")
    c2.metric("Registros (filtrados)", f"{int(n_filas or 0):,}")

    def _fmt_val(v: float) -> str:
        if fmt == "moneda" or unidad == "dólares":
            return _fmt_moneda(v)
        if unidad == "bultos":
            return f"{v:,.1f} bultos"
        return f"{v:,.2f}"

    if resumen.get("promedio") is not None:
        label = "Promedio"
        if unidad == "dólares":
            label = "Promedio ($)"
        elif unidad == "bultos":
            label = "Promedio (bultos)"
        c3.metric(label, _fmt_val(float(resumen["promedio"])))
    else:
        c3.metric("Dimensión", str(resumen.get("dimension") or "—"))
    if resumen.get("suma") is not None:
        label = "Suma / total"
        if unidad == "dólares":
            label = "Total ($)"
        elif unidad == "bultos":
            label = "Total (bultos)"
        c4.metric(label, _fmt_val(float(resumen["suma"])))
    else:
        c4.metric("Orden", str(resumen.get("orden") or "—"))
    if resumen.get("sugerencia"):
        st.info(resumen["sugerencia"])


def _restaurar_anterior(estado: dict[str, Any]) -> bool:
    hist = list(estado.get("historial_resultados") or [])
    if len(hist) < 2:
        return False
    hist.pop()
    prev = hist[-1]
    estado["historial_resultados"] = hist
    estado["ultimo_resultado"] = prev
    res = prev.get("resumen") or {}
    if res.get("rotacion_objetivo"):
        estado["rotacion"] = res["rotacion_objetivo"]
    specs = list(estado.get("historial_specs") or [])
    if len(specs) >= 2:
        specs.pop()
        estado["ultimo_grafico_spec"] = specs[-1]
        estado["historial_specs"] = specs
    return True


def render(df: pd.DataFrame, params: dict[str, Any]) -> None:
    del params
    st.markdown(f"### {VISTA_NOMBRE}")
    st.caption(
        "Consulte, analice y grafique cualquier información disponible en la base de datos "
        "de LRI Inventory Pro."
    )

    estado = _estado()
    api_key = oa.obtener_api_key()
    if not api_key:
        st.info(
            "Configure `OPENAI_API_KEY` en `.streamlit/secrets.toml` "
            "o en variable de entorno para usar el asistente."
        )
        pasted = st.text_input(
            "API key OpenAI (solo sesión)",
            type="password",
            key="lri_asistente_api_key_input",
        )
        if pasted:
            st.session_state["inv_openai_api_key"] = pasted.strip()
            st.rerun()
        return

    dias = int(st.session_state.get(skus.CLAVE_DIAS, skus._DIAS_TRABAJO_DEFAULT))

    for msg in estado["messages"]:
        contenido = tools.sanitizar_texto_respuesta(str(msg.get("content") or ""))
        if not contenido or _parece_basura_tecnica(contenido):
            continue
        with st.chat_message(msg["role"]):
            st.markdown(contenido)

    col_a, col_b = st.columns([1, 1])
    with col_a:
        if st.button("Regresar al análisis anterior", use_container_width=True):
            if _restaurar_anterior(estado):
                st.session_state[CLAVE_ESTADO] = estado
                st.success("Se restauró el resultado anterior.")
                st.rerun()
            else:
                st.warning("No hay un análisis anterior en el historial.")
    with col_b:
        if st.button("Limpiar conversación", use_container_width=True):
            st.session_state[CLAVE_ESTADO] = {
                "messages": [],
                "filtros": {},
                "rotacion": estado.get("rotacion", 4),
                "ultimo_resultado": None,
                "historial_resultados": [],
                "ultimo_grafico_spec": None,
                "historial_specs": [],
                "ultimo_plan": None,
            }
            st.rerun()

    # Micrófono: solo transcribe → mismo procesar_pregunta que el chat escrito
    pregunta_voz = None
    try:
        from audio_recorder_streamlit import audio_recorder
    except Exception:
        audio_recorder = None  # type: ignore
    if audio_recorder is not None:
        audio = audio_recorder(
            text="",
            recording_color="#e74c3c",
            neutral_color="#6b7280",
            icon_name="microphone",
            icon_size="2x",
            key="lri_asistente_mic",
        )
        audio_bytes = audio.get("bytes") if isinstance(audio, dict) else audio
        if audio_bytes:
            import hashlib

            h = hashlib.md5(audio_bytes, usedforsecurity=False).hexdigest()
            if h != st.session_state.get("lri_asistente_mic_hash"):
                st.session_state["lri_asistente_mic_hash"] = h
                try:
                    import io
                    import speech_recognition as sr

                    r = sr.Recognizer()
                    with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
                        data = r.record(source)
                    pregunta_voz = r.recognize_google(data, language="es-CR")
                    st.caption(f'Dictado: *"{pregunta_voz}"*')
                except Exception as exc:
                    st.warning(f"No se pudo transcribir el audio: {exc}")

    pregunta = st.chat_input(
        "Ejemplo: Grafique ventas y utilidad bruta por subcategoría; "
        "artículos a comprar según el mínimo; o compras para rotación 4."
    )
    if pregunta_voz and not pregunta:
        pregunta = pregunta_voz
    if pregunta:
        estado["messages"].append({"role": "user", "content": pregunta})
        with st.chat_message("user"):
            st.markdown(pregunta)

        with st.chat_message("assistant"):
            status = st.empty()
            try:
                low = pregunta.lower()
                if any(
                    x in low
                    for x in (
                        "regresa al analisis anterior",
                        "regresa al análisis anterior",
                        "regresar al grafico anterior",
                        "regresar al gráfico anterior",
                        "analisis anterior",
                        "análisis anterior",
                    )
                ):
                    if _restaurar_anterior(estado):
                        texto = "Restauré el análisis anterior (mismos datos oficiales)."
                    else:
                        texto = "No hay un análisis anterior para restaurar."
                    ctx = estado
                else:

                    def _on(msg: str) -> None:
                        status.caption(msg)

                    texto, ctx = oa.procesar_pregunta(
                        pregunta,
                        df,
                        api_key=api_key,
                        dias_trabajo=dias,
                        contexto=estado,
                        on_status=_on,
                    )
                    estado.update(ctx)
                status.empty()
                texto = tools.sanitizar_texto_respuesta(texto)
                if _parece_basura_tecnica(texto):
                    texto = (
                        "Resultado listo. Revise la tabla y el gráfico abajo."
                    )
                st.markdown(texto)
                estado["messages"].append({"role": "assistant", "content": texto})
                estado["messages"] = [
                    m
                    for m in estado["messages"]
                    if not _parece_basura_tecnica(str(m.get("content") or ""))
                ][-40:]
            except Exception as exc:
                status.empty()
                err = f"No se pudo completar la consulta: {exc}"
                st.error(err)
                estado["messages"].append({"role": "assistant", "content": err})

        st.session_state[CLAVE_ESTADO] = estado
        st.rerun()

    resultado = estado.get("ultimo_resultado")
    if not resultado:
        st.info(
            "Consulte, analice y grafique cualquier información disponible en la base de datos "
            "de LRI Inventory Pro. "
            "Ejemplo: Grafique la rotación de todos los SKU de mayor a menor; "
            "muestre las ventas por categoría; o calcule las compras necesarias para una rotación de 4."
        )
        return

    # Orden: verificación → métricas → tabla → gráfico Plotly
    st.divider()
    st.markdown("#### Resultado oficial")
    if resultado.get("verificacion"):
        st.info(tools.sanitizar_texto_respuesta(str(resultado["verificacion"])))
    resumen = resultado.get("resumen")
    if not resumen and resultado.get("por_rotacion"):
        st.markdown(resultado.get("mensaje") or "")
        df_comp = resultado.get("_df")
        if isinstance(df_comp, pd.DataFrame) and not df_comp.empty:
            st.dataframe(df_comp, use_container_width=True, hide_index=True)
        return

    _metricas(resumen)
    if resultado.get("mensaje"):
        st.caption(tools.sanitizar_texto_respuesta(str(resultado["mensaje"])))

    df_show = resultado.get("_df_completo")
    if df_show is None:
        df_show = resultado.get("_df")
    if isinstance(df_show, pd.DataFrame) and not df_show.empty:
        with st.expander(
            f"Tabla detallada ({len(df_show):,} filas)",
            expanded=len(df_show) <= 40,
        ):
            st.dataframe(
                _tabla_mostrar(df_show),
                use_container_width=True,
                hide_index=True,
            )
        # Export Excel cuando el resultado es una lista de compra
        col_qty = None
        for cand in (
            "cantidad a comprar",
            "cantidad a comprar segun minimo",
            cols.COL_QTY if hasattr(cols, "COL_QTY") else None,
        ):
            if cand and cand in df_show.columns:
                col_qty = cand
                break
        if col_qty:
            st.checkbox(
                "Generar Excel de artículos a comprar",
                key="lri_asistente_export_compra_check",
                help=(
                    "Descarga ítem, proveedor, categoría, subcategoría y cantidad a comprar."
                ),
            )
            if st.session_state.get("lri_asistente_export_compra_check"):
                export_cols = [
                    c
                    for c in (
                        "codigo",
                        "descripcion",
                        "proveedor",
                        "categoria",
                        "subcategoria",
                        col_qty,
                        "monto compra",
                    )
                    if c in df_show.columns
                ]
                export = df_show.loc[:, export_cols].copy()
                qty = pd.to_numeric(export[col_qty], errors="coerce").fillna(0)
                export = export.loc[qty > 0].copy()
                export = export.rename(
                    columns={
                        "codigo": "Ítem / SKU",
                        "descripcion": "Descripción",
                        "proveedor": "Proveedor",
                        "categoria": "Categoría",
                        "subcategoria": "Subcategoría",
                        col_qty: "Cantidad a comprar",
                        "monto compra": "Monto de compra ($)",
                    }
                )
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                    export.to_excel(writer, sheet_name="Articulos a comprar", index=False)
                buf.seek(0)
                st.caption(f"**{len(export):,}** artículo(s) con cantidad a comprar > 0.")
                st.download_button(
                    "Descargar Excel de compra",
                    data=buf.getvalue(),
                    file_name="articulos_a_comprar.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key="lri_asistente_dl_excel_compra",
                    type="primary",
                )
        if (
            cols.COL_MONTO in df_show.columns
            and resumen
            and resumen.get("monto_total") is not None
        ):
            suma = float(pd.to_numeric(df_show[cols.COL_MONTO], errors="coerce").sum())
            if abs(suma - float(resumen.get("monto_total") or 0)) > 0.05:
                st.warning(
                    f"Revisión: suma tabla {_fmt_moneda(suma)} vs indicador "
                    f"{_fmt_moneda(float(resumen.get('monto_total') or 0))}."
                )
    else:
        st.info("No hay filas para mostrar con los filtros actuales.")

    grupos = resultado.get("agrupacion") or resultado.get("por_proveedor")
    if grupos:
        with st.expander("Por proveedor", expanded=False):
            st.dataframe(pd.DataFrame(grupos), use_container_width=True, hide_index=True)

    spec = resultado.get("_grafico_spec") or estado.get("ultimo_grafico_spec")
    if not spec and isinstance(df_show, pd.DataFrame) and not df_show.empty and resumen:
        metrica = resumen.get("metrica")
        dim = resumen.get("dimension") or "codigo"
        if metrica and metrica in df_show.columns:
            spec = {
                "tipo": "barras",
                "eje_x": dim
                if dim in df_show.columns
                else ("codigo" if "codigo" in df_show.columns else df_show.columns[0]),
                "eje_y": metrica,
                "titulo": f"{metrica}" + (f" por {dim}" if dim else ""),
                "top_n": None if resumen.get("mostrar_todos") else 20,
                "mostrar_todos": bool(resumen.get("mostrar_todos")),
                "orden_desc": resumen.get("orden") != "asc",
                "formato": resumen.get("formato"),
            }
        elif cols.COL_MONTO in df_show.columns:
            spec = {
                "tipo": "barras",
                "eje_x": "codigo",
                "eje_y": cols.COL_MONTO,
                "titulo": f"Compras · rotación {resumen.get('rotacion_objetivo', '')}",
                "top_n": 20,
                "mostrar_todos": False,
                "orden_desc": True,
                "formato": "moneda",
            }

    if spec and isinstance(df_show, pd.DataFrame) and not df_show.empty:
        try:
            fig = charts.figura_desde_spec(df_show, spec, resumen=resumen)
        except Exception as exc:
            fig = None
            st.warning(f"No se pudo construir el gráfico: {exc}")
        if fig is not None:
            st.markdown("##### Gráfico")
            st.plotly_chart(
                fig, use_container_width=True, config={"displayModeBar": True}
            )
            specs = list(estado.get("historial_specs") or [])
            if not specs or specs[-1] != spec:
                specs.append(spec)
                estado["historial_specs"] = specs[-8:]
                estado["ultimo_grafico_spec"] = spec
                st.session_state[CLAVE_ESTADO] = estado
