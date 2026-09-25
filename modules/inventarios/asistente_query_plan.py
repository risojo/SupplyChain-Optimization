"""Plan estructurado de consulta + ejecutor determinístico (Asistente LRI).

Flujo: pregunta → QueryPlan → validar vs catálogo → ejecutar sobre DataFrame.
OpenAI no ejecuta código; solo puede ayudar a narrar o proponer planes.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, replace
from typing import Any

import numpy as np
import pandas as pd

import asistente_catalogo as cat

# ---------------------------------------------------------------------------
# Modelo del plan
# ---------------------------------------------------------------------------


@dataclass
class FilterSpec:
    column: str
    operator: str = "eq"  # eq | ne | contains | gt | gte | lt | lte
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {"column": self.column, "operator": self.operator, "value": self.value}


@dataclass
class QueryPlan:
    metrics: list[str] = field(default_factory=list)
    dimensions: list[str] = field(default_factory=list)
    filters: list[FilterSpec] = field(default_factory=list)
    group_by: list[str] = field(default_factory=list)
    aggregations: dict[str, str] = field(default_factory=dict)
    derived_metrics: list[str] = field(default_factory=list)
    sort_by: str | None = None
    sort_order: str = "desc"
    limit: int | None = None
    mostrar_todos: bool = False
    output: str = "combinacion"
    chart_type: str = "barras"
    comparison: list[str] = field(default_factory=list)
    primary_axis_metrics: list[str] = field(default_factory=list)
    secondary_axis_metrics: list[str] = field(default_factory=list)
    titulo: str | None = None
    aclaracion: str | None = None
    es_compras: bool = False  # solo compra_por_rotación con rotación explícita
    context_reference: bool = False
    raw_question: str = ""
    formulas_aplicadas: list[dict[str, str]] = field(default_factory=list)
    consulta_nueva: bool = True  # True = no heredar filtros previos

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["filters"] = [f.to_dict() if isinstance(f, FilterSpec) else f for f in self.filters]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> QueryPlan:
        if not data:
            return cls()
        filters = []
        for f in data.get("filters") or []:
            if isinstance(f, FilterSpec):
                filters.append(f)
            elif isinstance(f, dict):
                filters.append(
                    FilterSpec(
                        column=str(f.get("column") or ""),
                        operator=str(f.get("operator") or "eq"),
                        value=f.get("value"),
                    )
                )
        return cls(
            metrics=list(data.get("metrics") or []),
            dimensions=list(data.get("dimensions") or []),
            filters=filters,
            group_by=list(data.get("group_by") or []),
            aggregations=dict(data.get("aggregations") or {}),
            derived_metrics=list(data.get("derived_metrics") or []),
            sort_by=data.get("sort_by"),
            sort_order=str(data.get("sort_order") or "desc"),
            limit=data.get("limit"),
            mostrar_todos=bool(data.get("mostrar_todos", False)),
            output=str(data.get("output") or "combinacion"),
            chart_type=str(data.get("chart_type") or "barras"),
            comparison=list(data.get("comparison") or []),
            primary_axis_metrics=list(data.get("primary_axis_metrics") or []),
            secondary_axis_metrics=list(data.get("secondary_axis_metrics") or []),
            titulo=data.get("titulo"),
            aclaracion=data.get("aclaracion"),
            es_compras=bool(data.get("es_compras", False)),
            context_reference=bool(data.get("context_reference", False)),
            raw_question=str(data.get("raw_question") or ""),
            formulas_aplicadas=list(data.get("formulas_aplicadas") or []),
            consulta_nueva=bool(data.get("consulta_nueva", True)),
        )


# ---------------------------------------------------------------------------
# Construcción del plan desde lenguaje natural
# ---------------------------------------------------------------------------

_DIM_KEYWORDS = {
    "categoria": ("categoria", "categoría", "categorias", "categorías"),
    "subcategoria": ("subcategoria", "subcategoría", "subcategorias", "subcategorías"),
    "proveedor": ("proveedor", "proveedores", "vendor"),
    "clase": ("clase", "clases"),
    "codigo": ("sku", "skus", "codigo", "código", "producto", "productos", "articulo", "artículo"),
    "descripcion": ("descripcion", "descripción"),
    "pais": ("pais", "país", "paises", "países"),
    "marca": ("marca", "marcas"),
    "familia": ("familia", "familias"),
    "bodega": ("bodega", "bodegas", "almacen", "almacén"),
}


def _detectar_group_by(t: str, schema: dict[str, dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for col, kws in _DIM_KEYWORDS.items():
        if col not in schema:
            continue
        for kw in kws:
            # «por categoría» / «por todas las categorías»
            if re.search(
                rf"\bpor\s+(todas\s+las\s+|todos\s+los\s+|cada\s+)?{re.escape(kw)}\b",
                t,
            ):
                out.append(col)
                break
            # «todas las categorías» / «todos los proveedores» ⇒ agrupar
            # NO aplicar a SKU/código/descripcion: «todos los SKU» = detalle completo
            if col in ("codigo", "descripcion"):
                continue
            if re.search(rf"\btodas\s+las\s+{re.escape(kw)}\b", t) or re.search(
                rf"\btodos\s+los\s+{re.escape(kw)}\b", t
            ):
                out.append(col)
                break
    return list(dict.fromkeys(out))

def _detectar_orden(t: str) -> str:
    if any(
        x in t
        for x in (
            "menor a mayor",
            "ascendente",
            "de menor",
            "los de menor",
            "bottom",
            "asc",
        )
    ):
        return "asc"
    return "desc"


def _detectar_limite(t: str) -> tuple[int | None, bool]:
    mostrar_todos = any(
        x in t
        for x in (
            "todos los sku",
            "todas las sku",
            "todos los skus",
            "todos los productos",
            "todas las categorias",
            "todas las categorías",
            "todas las subcategorias",
            "todas las subcategorías",
            "todos los proveedores",
            "toda la base",
            "sin top",
            "sin limite",
            "sin límite",
        )
    )
    # «todos» genérico junto a grafique/muestre
    if re.search(r"\btodos\b", t) or re.search(r"\btodas\b", t):
        mostrar_todos = True
    m_top = re.search(r"\btop\s+(\d+)\b", t)
    m_n = re.search(r"\b(?:primeros|primeras|ultimos|últimos)\s+(\d+)\b", t)
    m_exact = re.search(r"\b(\d+)\s+(?:articulos|artículos|sku|skus|productos|filas)\b", t)
    limite = None
    if m_top:
        limite = int(m_top.group(1))
        mostrar_todos = False
    elif m_n:
        limite = int(m_n.group(1))
        mostrar_todos = False
    elif m_exact and not mostrar_todos:
        limite = int(m_exact.group(1))
    return limite, mostrar_todos


def _detectar_output(t: str) -> tuple[str, str]:
    quiere_graf = any(
        x in t
        for x in ("grafique", "grafica", "gráfica", "graficar", "chart", "plot", "diagrama")
    )
    quiere_tabla = any(x in t for x in ("tabla", "liste", "muestre", "mostra", "detalle"))
    if quiere_graf and quiere_tabla:
        out = "combinacion"
    elif quiere_graf:
        out = "grafico"
    elif quiere_tabla:
        out = "tabla"
    else:
        out = "combinacion"
    chart = "barras"
    if "horizontal" in t:
        chart = "horizontal"
    elif "linea" in t or "línea" in t:
        chart = "lineas"
    elif "pareto" in t:
        chart = "pareto"
    return out, chart


def _es_seguimiento(t: str) -> bool:
    return any(
        x in t
        for x in (
            "ahora",
            "cambie",
            "cambiar",
            "agregue",
            "agregar",
            "añada",
            "anada",
            "quite",
            "quitar",
            "solo",
            "solamente",
            "unicamente",
            "únicamente",
            "ordene",
            "ordenar",
            "muestreme unicamente",
            "muéstreme únicamente",
            "muestrelo",
            "muéstrelo",
            "mostrarlo",
            "regrese",
            "volver",
            "anterior",
            "en su lugar",
            "en vez",
        )
    )


def _norm_con_separadores(texto: str) -> str:
    """Como _norm pero conserva comas para partir listas de métricas."""
    import unicodedata

    s = unicodedata.normalize("NFKD", str(texto or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9\s%,]", " ", s)
    return " ".join(s.split())


_METRIC_HINTS = (
    "venta",
    "utilidad",
    "margen",
    "inventario",
    "rotacion",
    "costo",
    "cubicaje",
    "evai",
    "gmroi",
    "pronostico",
    "presupuesto",
    "unidades",
    "bultos",
    "despach",
    "monto",
    "fill rate",
    "stock",
    "demanda",
    "cantidad",
    "cobertura",
)


def _hay_multi_metricas(t: str, pregunta_raw: str = "") -> bool:
    """True si la frase une varias métricas (y / con / vs / compare / comas)."""
    raw = pregunta_raw or t
    if "," in str(raw):
        return True
    if re.search(
        r"\b(frente\s+a|vs\.?|versus|contra|compar(e|ar|ado|ada)|lado\s+a\s+lado)\b",
        t,
    ):
        return True
    if re.search(r"\s+y\s+|\s+e\s+|\s+con\s+", t):
        parts = re.split(r"\s+y\s+|\s+e\s+|\s+con\s+", t)
        hints = sum(1 for p in parts if any(h in p for h in _METRIC_HINTS))
        if hints >= 2:
            return True
        if any(
            x in t
            for x in ("grafique", "muestre", "mostra", "compare", "comparar", "por ")
        ):
            return True
    return False


def _hay_comparacion(t: str) -> bool:
    return _hay_multi_metricas(t)


def _segmento_metricas_texto(t: str) -> str:
    """Recorta prefijos/sufijos dejando la zona donde viven las métricas."""
    s = t
    s = re.sub(
        r"^(grafique|grafica|graficar|muestre|mostra|liste|compare|comparar|calcule)\s+",
        "",
        s,
    )
    s = re.sub(r"^(las|los|la|el|una|un)\s+", "", s)
    # Quitar cola de orden («y ordénelos…») — no es métrica
    s = re.sub(
        r"\s+y\s+orden\w*\b.*$",
        "",
        s,
    )
    s = re.sub(
        r"\b(de\s+mayor\s+a\s+menor|de\s+menor\s+a\s+mayor|ordenad[oa]s?)\b.*$",
        "",
        s,
    )
    m = re.search(
        r"\bpor\s+(todas\s+las\s+|todos\s+los\s+|cada\s+)?"
        r"(categor[ií]a|subcategor[ií]a|proveedor|clase|sku|codigo|productos?)\b",
        s,
    )
    if m:
        s = s[: m.start()]
    # Quitar filtros de dimensión embebidos para no partir «proveedor X y …»
    s = re.sub(
        r"\b(?:del\s+)?proveedor\s+\S+(?:\s+\S+){0,3}(?=\s+con\s+|\s*$)",
        "",
        s,
    )
    s = re.sub(
        r"\b(?:de\s+la\s+)?(?<!sub)categor[ií]a\s+\S+(?:\s+\S+){0,3}(?=\s+con\s+|\s*$)",
        "",
        s,
    )
    s = re.sub(r"\blos\s+sku\b|\btodos\s+los\s+sku\b|\bskus\b", "", s)
    s = re.sub(r"\s+con\s+", " ", s)
    return " ".join(s.split()).strip()


def _partir_fragmentos_metricas(pregunta: str) -> list[str]:
    """Divide «ventas y utilidad» / «ventas, costo de ventas y margen» en fragmentos."""
    t = _norm_con_separadores(pregunta)
    head = _segmento_metricas_texto(t)
    if not head:
        return []
    parts = re.split(
        r"\s*,\s*|\s+y\s+|\s+e\s+|\s+con\s+|\s+frente\s+a\s+|\s+vs\.?\s+|\s+versus\s+|\s+contra\s+",
        head,
    )
    out = []
    for p in parts:
        p = re.sub(r"^(las|los|la|el|una|un)\s+", "", p.strip(" ,"))
        p = re.sub(r"\b(tambien|también|ademas|además)\b", "", p).strip()
        if len(p) >= 3:
            out.append(p)
    return out


def _resolver_metricas_en_frase(
    pregunta: str, schema: dict[str, dict[str, Any]], df: pd.DataFrame
) -> tuple[list[str], str | None]:
    """Devuelve métricas resueltas (lista ordenada) + aclaración opcional.

    Nunca descarta silenciosamente una métrica pedida: si un fragmento no
    resuelve, informa cuál faltó.
    """
    t = cat._norm(pregunta)

    quiere_min = "cantidad minima" in t or (
        ("minima" in t or "minimo" in t) and "cantidad" in t
    )
    quiere_max = (
        "cantidad maxima" in t
        or "inventario objetivo" in t
        or (("maxima" in t or "maximo" in t) and "cantidad" in t)
    )
    if quiere_min and quiere_max and not _hay_multi_metricas(t, pregunta):
        cols = []
        if "cantidad minima de inventario" in df.columns:
            cols.append("cantidad minima de inventario")
        if "inventario objetivo" in df.columns:
            cols.append("inventario objetivo")
        if len(cols) >= 2:
            return cols, None

    if _hay_multi_metricas(t, pregunta):
        frags = _partir_fragmentos_metricas(pregunta)
        if len(frags) >= 2:
            metrics: list[str] = []
            no_reconocidas: list[str] = []
            for frag in frags:
                ms, err = _metricas_de_fragmento(frag, schema, df)
                if err and not ms:
                    return [], err
                if not ms:
                    no_reconocidas.append(frag)
                else:
                    for m in ms:
                        if m not in metrics:
                            metrics.append(m)
            if no_reconocidas:
                return [], (
                    "No se reconoció la métrica «"
                    + "», «".join(no_reconocidas)
                    + "». Indique el nombre exacto o un sinónimo válido "
                    "(use listar_columnas)."
                )
            if len(metrics) < 2:
                return [], (
                    "La consulta menciona varias variables, pero solo se identificó "
                    f"una métrica válida: {metrics[0] if metrics else 'ninguna'}. "
                    "¿Puede reformular las métricas?"
                )
            return metrics, None

    if cat.es_consulta_inventario_promedio(pregunta):
        col, err = cat.resolver_inventario_promedio(pregunta, df)
        if err and not col:
            return [], err
        return ([col] if col else []), None

    if cat.es_consulta_margen_o_utilidad(pregunta) and not _hay_multi_metricas(t, pregunta):
        col, err = cat.resolver_margen_utilidad(pregunta, df)
        if err and not col:
            return [], err
        if col:
            return [col], None

    metrics = _extraer_metricas_por_sinonimo(t, schema)
    if not metrics:
        return [], None

    for m in metrics:
        err = cat.validar_metrica_unidad(m, pregunta)
        if err:
            return [], err + " ¿Puede aclarar la unidad?"
    return metrics, None


def _metricas_de_fragmento(
    frag: str, schema: dict[str, dict[str, Any]], df: pd.DataFrame
) -> tuple[list[str], str | None]:
    """Resuelve un fragmento (p. ej. «utilidad bruta» o «inventario promedio en bultos»)."""
    f = cat._norm(frag)
    if not f:
        return [], None

    if cat.es_consulta_inventario_promedio(frag) or (
        "inventario" in f and "promedio" in f
    ):
        col, err = cat.resolver_inventario_promedio(frag, df)
        if err and not col:
            return [], err
        return ([col] if col else []), None

    if cat.es_consulta_margen_o_utilidad(frag):
        col, err = cat.resolver_margen_utilidad(frag, df)
        if err and not col:
            return [], err
        if col:
            return [col], None

    # Coincidencia exacta de sinónimo / nombre completo del fragmento
    for col, meta in schema.items():
        if meta.get("rol") != "metrica":
            continue
        if meta["normalizado"] == f:
            return [col], None
        if f in {cat._norm(s) for s in meta.get("sinonimos", [])}:
            return [col], None

    ms = _extraer_metricas_por_sinonimo(f, schema, multi=True)
    if ms:
        # Preferir el sinónimo más largo que cubra casi todo el fragmento
        best = ms[0]
        best_score = 0
        for col in ms:
            meta = schema[col]
            for s in [meta["normalizado"], *meta.get("sinonimos", [])]:
                sn = cat._norm(s)
                if sn and sn in f and len(sn) > best_score:
                    best_score = len(sn)
                    best = col
        return [best], None

    col, err = cat.resolver_columna(frag, df, catalogo=schema, contexto_frase=frag)
    if col and schema.get(col, {}).get("rol") == "metrica":
        return [col], None
    return [], None


def _extraer_metricas_por_sinonimo(
    t: str,
    schema: dict[str, dict[str, Any]],
    *,
    excluir: set[str] | None = None,
    multi: bool = False,
) -> list[str]:
    excluir = excluir or set()
    candidatos: list[tuple[int, int, str]] = []  # score, -posicion, col
    for col, meta in schema.items():
        if meta.get("rol") != "metrica":
            continue
        if col in excluir:
            continue
        sinonimos = [meta["normalizado"], *meta.get("sinonimos", [])]
        best = 0
        best_pos = 10**9
        for s in sinonimos:
            sn = cat._norm(s)
            if len(sn) < 3:
                continue
            pos = t.find(sn)
            if pos >= 0:
                if len(sn) > best or (len(sn) == best and pos < best_pos):
                    best = len(sn)
                    best_pos = pos
        if best:
            candidatos.append((best, best_pos, col))
    # Orden: aparición en la frase, luego score
    candidatos.sort(key=lambda x: (x[1], -x[0]))

    elegidas: list[str] = []
    spans_usados: list[tuple[int, int]] = []

    def _solapa(a: int, b: int) -> bool:
        for x, y in spans_usados:
            if not (b <= x or a >= y):
                return True
        return False

    for score, pos, col in candidatos:
        if col in elegidas:
            continue
        # Evitar que «margen» robe a «margen bruto total» ya elegido y viceversa
        sn = cat._norm(col)
        end = pos + score
        # ubicar span real del mejor sinónimo
        meta = schema[col]
        span = None
        for s in [meta["normalizado"], *meta.get("sinonimos", [])]:
            sn2 = cat._norm(s)
            if len(sn2) < 3:
                continue
            p2 = t.find(sn2)
            if p2 >= 0 and len(sn2) == score:
                span = (p2, p2 + len(sn2))
                break
        if span and _solapa(*span):
            continue
        # Si solo dijo «ventas», no añadir también «ventas costo»
        if elegidas and not multi and not _hay_multi_metricas(t):
            if any(
                cat._norm(col).startswith(cat._norm(e).split()[0])
                and cat._norm(e).startswith(cat._norm(col).split()[0])
                and col != e
                for e in elegidas
            ):
                continue
        elegidas.append(col)
        if span:
            spans_usados.append(span)
        if not multi and not _hay_multi_metricas(t) and len(elegidas) >= 1:
            break
        if len(elegidas) >= 5:
            break
    return elegidas

def _titulo_plan(plan: QueryPlan, schema: dict[str, dict[str, Any]]) -> str:
    mets = plan.metrics
    if (
        len(mets) == 2
        and "ventas totales" in mets
        and "margen bruto total" in mets
        and plan.group_by == ["subcategoria"]
    ):
        return "Ventas y utilidad bruta por subcategoría"
    if len(mets) == 1 and mets[0] == "valor inventario promedio":
        cat_f = next((f.value for f in plan.filters if f.column == "categoria"), None)
        if cat_f:
            return f"Valor promedio del inventario – Categoría {cat_f}"
        return "Valor promedio del inventario ($)"
    if len(mets) == 1 and mets[0] == "inventario promedio bultos":
        cat_f = next((f.value for f in plan.filters if f.column == "categoria"), None)
        if cat_f:
            return f"Inventario promedio (bultos) – Categoría {cat_f}"
        return "Inventario promedio (bultos)"

    labels = []
    for m in mets:
        if m == "margen bruto total":
            labels.append("utilidad bruta ($)")
        elif m == "margen utilidad ventas":
            labels.append("margen de utilidad (%)")
        elif m == "ventas totales":
            labels.append("ventas")
        else:
            labels.append(cat.etiqueta_metrica_legible(m))
    if len(labels) >= 2:
        base = " y ".join(labels[:3]) if len(labels) == 2 else ", ".join(labels[:-1]) + " y " + labels[-1]
    elif labels:
        base = labels[0]
    else:
        base = "Consulta"
    if plan.group_by:
        gb = plan.group_by[0]
        gb_lbl = {
            "subcategoria": "subcategoría",
            "categoria": "categoría",
            "proveedor": "proveedor",
            "codigo": "SKU",
        }.get(gb, gb)
        base += f" por {gb_lbl}"
    return base.capitalize() if base and base[0].islower() else base


def linea_verificacion(plan: QueryPlan) -> str:
    # Filtros legibles
    if plan.filters:
        bits = []
        for f in plan.filters:
            if f.column == COL_QTY_MINIMO and f.operator == "gt":
                bits.append("cantidad a comprar según mínimo > 0")
            elif f.column == COL_QTY_MINIMO and f.operator in ("lte", "eq") and f.value == 0:
                bits.append("cantidad a comprar según mínimo ≤ 0")
            elif f.operator == "eq":
                bits.append(f"{f.column} = {f.value}")
            elif f.operator == "lt":
                bits.append(f"{f.column} < {f.value}")
            elif f.operator == "gt":
                bits.append(f"{f.column} > {f.value}")
            elif f.operator == "lte":
                bits.append(f"{f.column} ≤ {f.value}")
            elif f.operator == "gte":
                bits.append(f"{f.column} ≥ {f.value}")
            else:
                bits.append(f"{f.column} {f.operator} {f.value}")
        filt = "; ".join(bits)
    else:
        filt = "ninguno"

    if plan.metrics:
        labels = []
        for m in plan.metrics:
            if m == "margen bruto total":
                labels.append("utilidad bruta ($)")
            elif m == "margen utilidad ventas":
                labels.append("margen de utilidad (%)")
            elif m == "ventas totales":
                labels.append("ventas totales")
            elif m == "ventas costo":
                labels.append("costo de ventas")
            elif m == COL_QTY_MINIMO:
                labels.append("cantidad a comprar según mínimo")
            elif m == "unidades vendidas":
                labels.append("ventas en unidades")
            elif m == "valor inventario promedio":
                labels.append("inventario promedio en dólares")
            elif m == "inventario promedio bultos":
                labels.append("inventario promedio en bultos")
            else:
                labels.append(cat.etiqueta_metrica_legible(m))
        if len(labels) == 1:
            met_txt = labels[0]
        elif len(labels) == 2:
            met_txt = f"{labels[0]} y {labels[1]}"
        else:
            met_txt = ", ".join(labels[:-1]) + " y " + labels[-1]
    else:
        met_txt = "—"

    agrup = ", ".join(plan.group_by) if plan.group_by else "ninguna"
    if plan.group_by == ["subcategoria"]:
        agrup = "subcategoría"
    elif plan.group_by == ["categoria"]:
        agrup = "categoría"
    elif plan.group_by == ["codigo"]:
        agrup = "SKU"

    if len(plan.metrics) >= 2:
        chart = "barras agrupadas" if plan.chart_type == "barras_agrupadas" else (
            "eje secundario / dos métricas" if plan.chart_type == "dual_axis" else plan.chart_type
        )
        if plan.chart_type == "dual_axis":
            chart = f"{len(plan.metrics)} métricas (ejes por unidad)"
        elif plan.chart_type == "barras_agrupadas":
            chart = f"{len(plan.metrics)} métricas (barras agrupadas)"
        return (
            f"Filtro: {filt} | Métricas: {met_txt} | Agrupación: {agrup} | "
            f"Gráfico: {chart}"
        )

    orden = "menor a mayor" if plan.sort_order == "asc" else "mayor a menor"
    return (
        f"Filtro: {filt} | Métricas: {met_txt} | Agrupación: {agrup} | Orden: {orden}"
    )


COL_QTY_MINIMO = "cantidad a comprar segun minimo"


def _metricas_negocio_explicitas(
    frase: str, schema: dict[str, dict[str, Any]], df: pd.DataFrame
) -> list[str]:
    """Métricas de negocio claras (ignora ruido «artículos» / «cantidades a comprar»)."""
    t = cat._norm(frase)
    ruido = (
        "articulo",
        "sku",
        "producto",
        "item",
        "cantidad a comprar",
        "cantidades a comprar",
        "compras",
    )
    frags = _partir_fragmentos_metricas(frase) if _hay_multi_metricas(t, frase) else [t]
    out: list[str] = []
    for frag in frags:
        fn = cat._norm(frag)
        if not fn or any(r in fn and len(fn) < len(r) + 8 for r in ruido):
            if fn in ("cantidad a comprar", "cantidades a comprar", "compra", "compras"):
                continue
            if any(fn == r or fn.startswith(r + " ") for r in ("articulo", "sku", "producto")):
                continue
        ms, _err = _metricas_de_fragmento(frag, schema, df)
        for m in ms:
            if m == "cantidad a comprar":
                continue
            if m not in out:
                out.append(m)
    # Sin multi: intentar sinónimos directos excluyendo qty compra genérica
    if not out:
        ms = _extraer_metricas_por_sinonimo(t, schema)
        out = [m for m in ms if m != "cantidad a comprar"]
    return out


def _extraer_filtro_compra_minimo(pregunta: str) -> FilterSpec | None:
    """Convierte frases de compra/no-compra según mínimo en filtro componible."""
    if not cat.es_reposicion_por_minimo(pregunta):
        return None
    t = cat._norm(pregunta)
    negativo = any(
        x in t
        for x in (
            "no deben",
            "no hay que",
            "no necesitan",
            "no comprarse",
            "no comprar",
            "que no deben",
            "que no hay",
            "sin necesidad de comprar",
            "no a comprar",
        )
    )
    if negativo:
        return FilterSpec(column=COL_QTY_MINIMO, operator="lte", value=0)
    return FilterSpec(column=COL_QTY_MINIMO, operator="gt", value=0)


def _extraer_filtros_numericos(
    pregunta: str, schema: dict[str, dict[str, Any]]
) -> list[FilterSpec]:
    t = cat._norm(pregunta)
    out: list[FilterSpec] = []
    patrones = [
        (r"rotacion\s+(?:menor\s+que|menor\s+a|under|below|<)\s*(\d+(?:\.\d+)?)", "rotacion", "lt"),
        (r"rotacion\s+(?:mayor\s+que|mayor\s+a|over|above|>)\s*(\d+(?:\.\d+)?)", "rotacion", "gt"),
        (r"rotacion\s+(?:menor\s+o\s+igual\s+(?:que|a)|<=)\s*(\d+(?:\.\d+)?)", "rotacion", "lte"),
        (r"rotacion\s+(?:mayor\s+o\s+igual\s+(?:que|a)|>=)\s*(\d+(?:\.\d+)?)", "rotacion", "gte"),
    ]
    for pat, col, op in patrones:
        if col not in schema and col not in ("rotacion",):
            continue
        m = re.search(pat, t)
        if m:
            out.append(FilterSpec(column=col, operator=op, value=float(m.group(1))))
    return out


def construir_plan(
    pregunta: str,
    df: pd.DataFrame,
    *,
    plan_anterior: QueryPlan | None = None,
    schema: dict[str, dict[str, Any]] | None = None,
) -> QueryPlan:
    """Convierte lenguaje natural → QueryPlan validable (motor universal)."""
    import asistente_derivadas as der

    schema = schema or cat.descubrir_schema(df)
    schema = der.enriquecer_catalogo_derivadas(schema)
    t = cat._norm(pregunta)
    plan = QueryPlan(raw_question=pregunta, consulta_nueva=True)

    # Solo compra_por_rotación con rotación explícita → herramientas de compras
    if cat.menciona_rotacion_objetivo(pregunta) and cat.es_consulta_compras(pregunta):
        plan.es_compras = True
        return plan
    if cat.es_consulta_compras(pregunta) and not cat.es_reposicion_por_minimo(pregunta):
        plan.es_compras = True
        return plan

    # Frases de deshacer / anterior las maneja la UI; aquí solo marcamos referencia
    if any(x in t for x in ("regrese", "grafico anterior", "gráfico anterior", "resultado anterior")):
        plan.context_reference = True
        plan.aclaracion = None
        plan.output = "grafico"
        return plan

    seguimiento = _es_seguimiento(t) and plan_anterior is not None and bool(
        plan_anterior.metrics or plan_anterior.filters
    )

    if seguimiento:
        plan = _aplicar_seguimiento(pregunta, plan_anterior, schema, df)
        plan.raw_question = pregunta
        plan.consulta_nueva = False
        if plan.aclaracion:
            return plan
    else:
        # Separar contexto de filtro («Para los artículos que…») de métricas a mostrar
        contexto_txt, metricas_txt = pregunta, pregunta
        t_full = cat._norm(pregunta)
        m_para = re.search(
            r"^para\s+(?:los\s+|las\s+)?(?:articulos|sku|skus|productos|items)\s+que\s+(.+?)"
            r"(?:,|;|:|\.)\s*(?:grafique|muestre|mostra|compare|comparar)\s+(.+)$",
            t_full,
        )
        if not m_para:
            m_para = re.search(
                r"^para\s+(?:los\s+|las\s+)?(?:articulos|sku|skus|productos|items)\s+que\s+(.+?)\s+"
                r"(?:grafique|muestre|mostra|compare)\s+(.+)$",
                t_full,
            )
        if m_para:
            contexto_txt = m_para.group(1)
            metricas_txt = m_para.group(2)

        f_min = _extraer_filtro_compra_minimo(pregunta)

        # --- métricas (desde la parte de visualización) ---
        metrics, err = _resolver_metricas_en_frase(metricas_txt, schema, df)
        # Si hay filtro de compra-mínimo y la frase no pide otras métricas claras,
        # no abortar por fragmentos tipo «artículos» / «cantidades a comprar».
        if err and f_min:
            otras = _metricas_negocio_explicitas(metricas_txt, schema, df)
            if otras:
                metrics, err = otras, None
            else:
                metrics, err = [], None
        if err:
            plan.aclaracion = err
            return plan

        # Derivadas (presupuesto anual, etc.)
        regla = der.resolver_derivada(pregunta)
        if regla:
            # Si la frase pide la derivada explícitamente
            syn_hit = any(cat._norm(s) in t for s in regla.sinonimos)
            if syn_hit and (
                not metrics
                or regla.columna_resultado in metrics
                or any(cat._norm(s) in cat._norm(metricas_txt) for s in regla.sinonimos)
            ):
                if regla.columna_resultado not in metrics:
                    # Reemplazar métricas genéricas confusas o añadir
                    if not metrics or all(
                        m in ("ventas totales", "pronostico ajustado", "pronostico")
                        for m in metrics
                    ):
                        metrics = [regla.columna_resultado]
                    elif regla.columna_resultado not in metrics:
                        metrics.append(regla.columna_resultado)
                plan.derived_metrics = [regla.columna_resultado]

        # Filtro compra según mínimo (componible — NO reemplaza métricas)
        if f_min and not metrics:
            # Solo filtro → métrica predeterminada = cantidad a comprar según mínimo
            metrics = [COL_QTY_MINIMO]
            plan.derived_metrics = list(
                dict.fromkeys([*(plan.derived_metrics or []), COL_QTY_MINIMO])
            )
        # Si resolvió «cantidad a comprar» o «cantidad minima…» pero la intención es según mínimo
        if f_min and metrics:
            solo_min_cols = {
                "cantidad a comprar",
                "cantidad minima de inventario",
                COL_QTY_MINIMO,
            }
            if set(metrics) <= solo_min_cols:
                metrics = [COL_QTY_MINIMO]
                plan.derived_metrics = list(
                    dict.fromkeys([*(plan.derived_metrics or []), COL_QTY_MINIMO])
                )

        plan.metrics = metrics

        # --- filtros por valor dinámico ---
        filtros, amb = cat.encontrar_valores_en_frase(pregunta, schema, df)
        if amb:
            plan.aclaracion = amb
            return plan
        plan.filters = [FilterSpec(**f) if isinstance(f, dict) else f for f in filtros]
        plan.filters = _fusionar_filtros_explicitos(pregunta, plan.filters, schema, df)
        plan.filters.extend(_extraer_filtros_numericos(pregunta, schema))
        if f_min:
            plan.filters = [f for f in plan.filters if f.column != COL_QTY_MINIMO]
            plan.filters.append(f_min)
            if COL_QTY_MINIMO not in plan.derived_metrics:
                plan.derived_metrics.append(COL_QTY_MINIMO)

        # --- group by ---
        gb = _detectar_group_by(t, schema)
        plan.group_by = gb
        if plan.group_by:
            plan.dimensions = list(plan.group_by)
        else:
            plan.dimensions = ["codigo"] if "codigo" in schema else []

        # agregación
        if plan.group_by:
            for m in plan.metrics:
                meta = schema.get(m, {})
                if (
                    meta.get("unidad") in ("ratio", "porcentaje", "meses", "dias")
                    or "promedio" in cat._norm(m)
                    or "rotacion" in cat._norm(m)
                ):
                    plan.aggregations[m] = "mean"
                else:
                    plan.aggregations[m] = "sum"
        else:
            for m in plan.metrics:
                plan.aggregations[m] = "none"

        plan.sort_order = _detectar_orden(t)
        plan.limit, plan.mostrar_todos = _detectar_limite(t)
        if plan.filters and plan.limit is None:
            plan.mostrar_todos = True
        plan.output, plan.chart_type = _detectar_output(t)
        if len(plan.metrics) >= 2:
            plan.comparison = list(plan.metrics)
            unidades = {
                (schema.get(m, {}).get("unidad") or schema.get(m, {}).get("formato"))
                for m in plan.metrics
            }
            if len(unidades) <= 1:
                plan.chart_type = "barras_agrupadas"
                plan.primary_axis_metrics = list(plan.metrics)
                plan.secondary_axis_metrics = []
            else:
                plan.chart_type = "dual_axis"
                # Primer grupo de unidad → primary; resto → secondary
                u0 = schema.get(plan.metrics[0], {}).get("unidad") or schema.get(
                    plan.metrics[0], {}
                ).get("formato")
                plan.primary_axis_metrics = [
                    m
                    for m in plan.metrics
                    if (schema.get(m, {}).get("unidad") or schema.get(m, {}).get("formato"))
                    == u0
                ]
                plan.secondary_axis_metrics = [
                    m for m in plan.metrics if m not in plan.primary_axis_metrics
                ]

    if not plan.metrics and not plan.aclaracion:
        return plan

    plan.sort_by = plan.sort_by or (plan.metrics[0] if plan.metrics else None)
    plan.titulo = plan.titulo or _titulo_plan(plan, schema)

    # Reafirmar chart multi-métrica tras sort/titulo
    if len(plan.metrics) >= 2 and plan.chart_type not in ("barras_agrupadas", "dual_axis"):
        unidades = {
            (schema.get(m, {}).get("unidad") or schema.get(m, {}).get("formato"))
            for m in plan.metrics
        }
        plan.chart_type = "barras_agrupadas" if len(unidades) <= 1 else "dual_axis"
        plan.comparison = list(plan.metrics)

    # Validación final de unidades (solo mono-métrica; multi ya validó por fragmento)
    if len(plan.metrics) == 1:
        err = cat.validar_metrica_unidad(plan.metrics[0], pregunta)
        if err:
            plan.aclaracion = err
            return plan

    return plan


def _fusionar_filtros_explicitos(
    pregunta: str,
    filtros: list[FilterSpec],
    schema: dict[str, dict[str, Any]],
    df: pd.DataFrame,
) -> list[FilterSpec]:
    t = cat._norm(pregunta)
    existentes = {f.column for f in filtros}
    patrones = [
        (
            "categoria",
            r"(?<!sub)categor[ií]a\s+(.+?)(?=\s+con\s+|\s+de\s+mayor|\s+de\s+menor|\s+orden|\s+y\s+|\s+por\s+|\s*$|,|\.|$)",
        ),
        (
            "subcategoria",
            r"subcategor[ií]a\s+(.+?)(?=\s+con\s+|\s+de\s+mayor|\s+de\s+menor|\s+por\s+|\s*$|,|\.|$)",
        ),
        (
            "proveedor",
            r"(?:del\s+)?proveedor\s+(.+?)(?=\s+con\s+|\s+de\s+mayor|\s+de\s+menor|\s+por\s+|\s*$|,|\.|$)",
        ),
        (
            "clase",
            r"(?<![a-z])clase\s+(.+?)(?=\s+con\s+|\s+de\s+mayor|\s+de\s+menor|\s+por\s+|\s*$|,|\.|$)",
        ),
    ]
    out = list(filtros)
    for col, pat in patrones:
        if col in existentes or col not in df.columns:
            continue
        m = re.search(pat, t)
        if not m:
            continue
        opts = sorted({str(v) for v in df[col].dropna().unique()})
        hit = cat.match_valor(m.group(1), opts)
        if hit:
            out.append(FilterSpec(column=col, operator="eq", value=hit))
    return out


def _aplicar_seguimiento(
    pregunta: str,
    prev: QueryPlan,
    schema: dict[str, dict[str, Any]],
    df: pd.DataFrame,
) -> QueryPlan:
    plan = QueryPlan.from_dict(prev.to_dict())
    plan.context_reference = True
    t = cat._norm(pregunta)

    # Cambiar métrica: «cambie rotacion por ventas» / «en vez de X use Y»
    m_cambio = re.search(
        r"(?:cambie|cambiar|reemplace|reemplazar|en\s+vez\s+de|en\s+lugar\s+de)\s+(.+?)\s+por\s+(.+)$",
        t,
    )
    if m_cambio:
        old_s, new_s = m_cambio.group(1), m_cambio.group(2)
        old_c, _ = cat.resolver_columna(old_s, df, catalogo=None, contexto_frase=old_s)
        new_c, err = cat.resolver_columna(new_s, df, catalogo=None, contexto_frase=new_s)
        if err and not new_c:
            # intentar inventario
            if cat.es_consulta_inventario_promedio(new_s):
                new_c, err = cat.resolver_inventario_promedio(new_s, df)
        if new_c:
            plan.metrics = [new_c if m == old_c else m for m in plan.metrics] or [new_c]
            if old_c and old_c not in plan.metrics and new_c not in plan.metrics:
                plan.metrics = [new_c]
            plan.metrics = list(dict.fromkeys([new_c if (old_c and m == old_c) else m for m in (plan.metrics or [new_c])]))
            if new_c not in plan.metrics:
                plan.metrics = [new_c]
            plan.aggregations = {m: plan.aggregations.get(m, "none") for m in plan.metrics}
            plan.sort_by = plan.metrics[0]
            plan.comparison = plan.metrics if len(plan.metrics) > 1 else []
            plan.titulo = None
        elif err:
            plan.aclaracion = err
            return plan

    # Agregar métrica
    if any(x in t for x in ("agregue", "agregar", "añada", "anada", "incluya")):
        ms, err = _resolver_metricas_en_frase(pregunta, schema, df)
        if err:
            plan.aclaracion = err
            return plan
        for m in ms:
            if m not in plan.metrics:
                plan.metrics.append(m)
        if len(plan.metrics) >= 2:
            plan.comparison = list(plan.metrics)
            plan.chart_type = "barras_agrupadas"
        plan.titulo = None

    # Solo filtro / ahora solamente Valor
    if any(x in t for x in ("ahora", "solo", "solamente", "unicamente", "únicamente", "filtre", "filtrar")):
        filtros, amb = cat.encontrar_valores_en_frase(pregunta, schema, df)
        if amb:
            plan.aclaracion = amb
            return plan
        if filtros:
            # Reemplaza filtros de esas columnas
            cols_new = {f["column"] for f in filtros}
            plan.filters = [f for f in plan.filters if f.column not in cols_new]
            plan.filters.extend(FilterSpec(**f) for f in filtros)
            plan.mostrar_todos = True
            plan.limit = None
            plan.titulo = None

    # Quitar filtro
    if any(x in t for x in ("quite", "quitar", "elimine", "eliminar", "saque")):
        for col in schema:
            if schema[col].get("rol") != "dimension":
                continue
            if cat._norm(col) in t or any(cat._norm(s) in t for s in schema[col].get("sinonimos", [])):
                plan.filters = [f for f in plan.filters if f.column != col]

    # Cambiar solo agrupación: «Ahora muéstrelo por proveedor» / «muéstrelo por…»
    if re.search(r"\bpor\s+", t) and (
        re.search(r"\b(ahora|solo|solamente)\b", t)
        or re.search(r"\b(muestrelo|mostrarlo|mostrame|muéstrame)\b", t)
        or re.search(r"\bcambie\s+(la\s+)?agrup", t)
    ):
        gb = _detectar_group_by(t, schema)
        if gb:
            plan.group_by = gb
            plan.dimensions = list(gb)
            if plan.group_by:
                for m in plan.metrics:
                    meta = schema.get(m, {})
                    if meta.get("unidad") in ("ratio", "porcentaje", "meses", "dias") or "promedio" in cat._norm(
                        m
                    ) or "rotacion" in cat._norm(m):
                        plan.aggregations[m] = "mean"
                    else:
                        plan.aggregations[m] = "sum"
            plan.titulo = None
            plan.consulta_nueva = False

    # Orden
    if any(x in t for x in ("ordene", "ordenar", "orden")):
        plan.sort_order = _detectar_orden(t)

    # Límite
    lim, todos = _detectar_limite(t)
    if lim is not None or "top" in t or "primeros" in t:
        plan.limit = lim
        plan.mostrar_todos = False if lim else todos
    if todos and lim is None:
        plan.mostrar_todos = True
        plan.limit = None

    plan.titulo = plan.titulo or _titulo_plan(plan, schema)
    return plan


# ---------------------------------------------------------------------------
# Ejecutor
# ---------------------------------------------------------------------------


def ejecutar_plan(
    df: pd.DataFrame,
    plan: QueryPlan,
    *,
    dias_trabajo: int = 30,
    rotacion: int = 4,
) -> dict[str, Any]:
    """Ejecuta un plan validado. Solo lectura sobre copia enriquecida."""
    import asistente_tools as tools

    if plan.aclaracion:
        return {
            "ok": False,
            "tipo": "consulta_datos",
            "mensaje": plan.aclaracion,
            "necesita_aclaracion": True,
            "plan": plan.to_dict(),
        }
    if plan.es_compras:
        return {"ok": False, "mensaje": "Usar herramientas de compras.", "tipo": "compras"}
    if not plan.metrics:
        return {
            "ok": False,
            "mensaje": "No se identificó una métrica. Indique qué desea consultar.",
            "tipo": "consulta_datos",
            "necesita_aclaracion": True,
            "plan": plan.to_dict(),
        }

    base = tools.enriquecer_dataframe_consulta(
        df, dias_trabajo=dias_trabajo, rotacion=rotacion
    )
    # Materializar derivadas pedidas (qty según mínimo, presupuesto anual, etc.)
    cols_der = list(
        dict.fromkeys([*(plan.derived_metrics or []), *plan.metrics, *[f.column for f in plan.filters]])
    )
    try:
        import asistente_derivadas as der

        base, formulas = der.aplicar_derivadas_necesarias(base, cols_der)
        plan.formulas_aplicadas = formulas
    except ValueError as exc:
        return {
            "ok": False,
            "tipo": "consulta_datos",
            "mensaje": str(exc),
            "necesita_aclaracion": True,
            "plan": plan.to_dict(),
        }

    schema = cat.descubrir_schema(base)
    try:
        import asistente_derivadas as der

        schema = der.enriquecer_catalogo_derivadas(schema)
    except Exception:
        pass

    # Validar columnas
    for m in plan.metrics:
        if m not in base.columns:
            rel = cat.metricas_relacionadas(m, schema)
            msg = f"La métrica «{m}» no existe en la base."
            if rel:
                msg += " Relacionadas: " + ", ".join(f"`{r}`" for r in rel[:8])
            return {"ok": False, "mensaje": msg, "tipo": "consulta_datos", "plan": plan.to_dict()}

    out = base.copy()
    filtros_aplicados: dict[str, Any] = {}

    # 1) Filtros primero
    for f in plan.filters:
        col = f.column
        if col not in out.columns:
            return {
                "ok": False,
                "mensaje": f"No existe la columna de filtro «{col}».",
                "tipo": "consulta_datos",
                "plan": plan.to_dict(),
            }
        if f.operator == "eq":
            opts = sorted({str(v) for v in out[col].dropna().unique()})
            hit = cat.match_valor(str(f.value), opts)
            if hit is None:
                cercanos = cat.valores_cercanos(str(f.value), opts, n=8)
                msg = f"Valor «{f.value}» no encontrado en {col}."
                if cercanos:
                    msg += " Alternativas: " + ", ".join(cercanos)
                return {"ok": False, "mensaje": msg, "tipo": "consulta_datos", "plan": plan.to_dict()}
            out = out.loc[out[col].astype(str) == hit].copy()
            filtros_aplicados[col] = hit
        elif f.operator == "contains":
            mask = out[col].astype(str).map(cat._norm).str.contains(
                cat._norm(str(f.value)), na=False
            )
            out = out.loc[mask].copy()
            filtros_aplicados[col] = f"*{f.value}*"
        else:
            num = pd.to_numeric(out[col], errors="coerce")
            val = float(f.value)
            ops = {
                "gt": num > val,
                "gte": num >= val,
                "lt": num < val,
                "lte": num <= val,
                "ne": num != val,
            }
            mask = ops.get(f.operator)
            if mask is None:
                return {
                    "ok": False,
                    "mensaje": f"Operador de filtro no soportado: {f.operator}",
                    "tipo": "consulta_datos",
                }
            out = out.loc[mask].copy()
            filtros_aplicados[col] = f"{f.operator} {f.value}"

    n_filtradas = len(out)
    metrics = plan.metrics
    primary = metrics[0]
    asc = plan.sort_order == "asc"

    # 2) Agrupar o detalle
    if plan.group_by:
        gcols = [c for c in plan.group_by if c in out.columns]
        if not gcols:
            return {
                "ok": False,
                "mensaje": f"Dimensión de agrupación no disponible: {plan.group_by}",
                "tipo": "consulta_datos",
            }
        agg_map = {}
        for m in metrics:
            op = plan.aggregations.get(m, "sum")
            if op in (None, "none", ""):
                op = "sum"
            agg_map[m] = op
        # groupby
        tmp = out.copy()
        for m in metrics:
            tmp[m] = pd.to_numeric(tmp[m], errors="coerce")
        grouped = tmp.groupby([tmp[c].astype(str) for c in gcols], dropna=False)
        # pandas groupby with list of series is awkward — use column names
        grouped = tmp.groupby(gcols, dropna=True)
        frames = []
        for m, op in agg_map.items():
            if op == "mean":
                s = grouped[m].mean()
            elif op == "median":
                s = grouped[m].median()
            elif op == "min":
                s = grouped[m].min()
            elif op == "max":
                s = grouped[m].max()
            elif op == "count":
                s = grouped[m].count()
            else:
                s = grouped[m].sum()
            frames.append(s.rename(m))
        resultado = pd.concat(frames, axis=1).reset_index()
        if "codigo" in tmp.columns:
            cnt = tmp.groupby(gcols)["codigo"].count().rename("n_skus")
            resultado = resultado.merge(cnt.reset_index(), on=gcols, how="left")
        # Orden de columnas: dimensión(es) + métricas (en orden del plan) + n_skus
        ordered = [c for c in gcols if c in resultado.columns]
        ordered += [m for m in metrics if m in resultado.columns]
        if "n_skus" in resultado.columns:
            ordered.append("n_skus")
        resultado = resultado.loc[:, ordered]
        dim_x = gcols[0]
    else:
        cols_keep: list[str] = []
        for c in (
            *(plan.dimensions or []),
            "codigo",
            "descripcion",
            "proveedor",
            "categoria",
            "subcategoria",
            "clase",
            *metrics,
        ):
            if c and c in out.columns and c not in cols_keep:
                cols_keep.append(c)
        resultado = out.loc[:, cols_keep].copy()
        for m in metrics:
            resultado[m] = pd.to_numeric(resultado[m], errors="coerce")
        dim_x = (
            plan.dimensions[0]
            if plan.dimensions and plan.dimensions[0] in resultado.columns
            else ("codigo" if "codigo" in resultado.columns else resultado.columns[0])
        )

    if resultado.empty:
        ver = linea_verificacion(plan)
        return {
            "ok": True,
            "tipo": "consulta_datos",
            "mensaje": "No se encontraron registros con los filtros indicados.",
            "verificacion": ver,
            "plan": plan.to_dict(),
            "resumen": {
                "metrica": primary,
                "metricas": metrics,
                "dimension": dim_x,
                "n_filas": 0,
                "n_filas_filtradas": n_filtradas,
                "filtros": filtros_aplicados,
            },
            "filas_preview": [],
            "_df": resultado,
            "_df_completo": resultado,
        }

    sort_col = plan.sort_by if plan.sort_by in resultado.columns else primary
    resultado = resultado.sort_values(sort_col, ascending=asc, na_position="last")

    n_total = len(resultado)
    if plan.mostrar_todos or (plan.limit is None and n_total <= 500):
        vista = resultado
        usado_limite = None
        mostrar_todos = True
    elif plan.limit is not None:
        vista = resultado.head(int(plan.limit))
        usado_limite = int(plan.limit)
        mostrar_todos = False
    else:
        vista = resultado
        usado_limite = None
        mostrar_todos = True

    formatos = {m: schema.get(m, {}).get("formato", "numero") for m in metrics}
    unidades = {m: schema.get(m, {}).get("unidad") for m in metrics}

    yvals = pd.to_numeric(vista[primary], errors="coerce")
    resumen = {
        "metrica": primary,
        "metricas": metrics,
        "metrica_legible": cat.etiqueta_metrica_legible(primary),
        "dimension": dim_x,
        "agregacion": plan.aggregations.get(primary, "none"),
        "orden": "asc" if asc else "desc",
        "n_filas": int(len(vista)),
        "n_filas_totales": int(n_total),
        "n_filas_filtradas": int(n_filtradas),
        "limite_aplicado": usado_limite,
        "mostrar_todos": bool(mostrar_todos),
        "suma": round(float(yvals.sum()), 4) if yvals.notna().any() else None,
        "promedio": round(float(yvals.mean()), 4) if yvals.notna().any() else None,
        "min": round(float(yvals.min()), 4) if yvals.notna().any() else None,
        "max": round(float(yvals.max()), 4) if yvals.notna().any() else None,
        "filtros": filtros_aplicados,
        "formato": formatos.get(primary, "numero"),
        "formatos": formatos,
        "unidad": _unidad_legible(unidades.get(primary), formatos.get(primary)),
        "unidades": {m: _unidad_legible(unidades.get(m), formatos.get(m)) for m in metrics},
        "group_by": plan.group_by,
        "comparison": plan.comparison or (metrics if len(metrics) > 1 else []),
    }

    preview = []
    for _, row in vista.head(40).iterrows():
        item = {}
        for c in vista.columns:
            v = row[c]
            if pd.isna(v):
                item[c] = None
            elif isinstance(v, (np.floating, float)):
                item[c] = round(float(v), 4)
            else:
                item[c] = str(v) if not isinstance(v, (int, np.integer)) else int(v)
        preview.append(item)

    tit = plan.titulo or _titulo_plan(plan, schema)
    generar = plan.output in ("grafico", "combinacion", "respuesta")

    # Nunca ejecutar multi-métrica con una sola columna de métrica
    if len(metrics) >= 2:
        faltan = [m for m in metrics if m not in vista.columns]
        if faltan:
            return {
                "ok": False,
                "tipo": "consulta_datos",
                "mensaje": (
                    "La consulta pidió varias métricas, pero faltan en el resultado: "
                    + ", ".join(f"«{m}»" for m in faltan)
                ),
                "necesita_aclaracion": True,
                "plan": plan.to_dict(),
            }

    spec = None
    if generar:
        def _u_key(m: str) -> str:
            u = unidades.get(m) or formatos.get(m)
            if u in ("moneda", "dólares", "dolares"):
                return "moneda"
            if u in ("bultos", "numero") and "bulto" in cat._norm(m):
                return "bultos"
            return str(u or "numero")

        mismas_unidades = len({_u_key(m) for m in metrics}) <= 1
        tipo = plan.chart_type
        if len(metrics) >= 2:
            tipo = "barras_agrupadas" if mismas_unidades else "dual_axis"
            plan.chart_type = tipo
        mostrar_all = bool(mostrar_todos and (usado_limite is None))
        top_graf = None if mostrar_all or usado_limite is None else usado_limite
        if mostrar_all and n_total > 80 and usado_limite is None:
            top_graf = None
        spec = {
            "tipo": tipo,
            "eje_x": dim_x,
            "eje_y": primary,
            "ejes_y": list(metrics),
            "titulo": tit,
            "agrupar_por": None,
            "top_n": top_graf,
            "mostrar_todos": True if (mostrar_todos or top_graf is None) else False,
            "orden_desc": not asc,
            "formato": formatos.get(primary),
            "formatos": formatos,
            "unidades": resumen["unidades"],
        }

    ver = linea_verificacion(plan)
    if "Registros:" not in ver:
        ver = f"{ver} | Registros: {len(vista)}"
    msg = f"{ver}."
    if plan.formulas_aplicadas:
        bits = [f"{f['columna']}: {f['formula']}" for f in plan.formulas_aplicadas]
        msg += " Fórmula(s): " + "; ".join(bits) + "."
    return {
        "ok": True,
        "tipo": "consulta_datos",
        "mensaje": msg,
        "verificacion": ver,
        "plan": plan.to_dict(),
        "resumen": resumen,
        "filas_preview": preview,
        "columnas": list(vista.columns),
        "_df": vista.head(500),
        "_df_completo": vista,
        "_grafico_spec": spec,
    }


def _unidad_legible(unidad: str | None, formato: str | None) -> str | None:
    if unidad == "moneda" or formato == "moneda":
        return "dólares"
    if unidad == "bultos":
        return "bultos"
    if unidad == "porcentaje" or formato == "porcentaje":
        return "%"
    if unidad == "meses" or formato == "meses":
        return "meses"
    if unidad == "dias":
        return "días"
    return unidad
