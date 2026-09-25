"""Catálogo dinámico del DataFrame procesado (Inventory Pro).

Descubre automáticamente columnas, roles, unidades, formatos, sinónimos
y valores categóricos. No inventa columnas ni valores.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

import pandas as pd

# Sinónimos opcionales (mejora UX). El descubrimiento no depende de esta lista:
# toda columna del DF entra al catálogo aunque no tenga sinónimos aquí.
_SINONIMOS_FIJOS: dict[str, list[str]] = {
    "codigo": [
        "sku",
        "skus",
        "codigo",
        "código",
        "item",
        "items",
        "articulo",
        "artículo",
        "producto",
        "productos",
    ],
    "descripcion": ["descripcion", "descripción", "nombre", "detalle"],
    "categoria": ["categoria", "categoría", "cat", "categorias", "categorías"],
    "clase": ["clase", "clases"],
    "subcategoria": [
        "subcategoria",
        "subcategoría",
        "subcat",
        "subcategorias",
        "subcategorías",
    ],
    "proveedor": ["proveedor", "proveedores", "vendor"],
    "pais": ["pais", "país", "paises", "países"],
    "marca": ["marca", "marcas"],
    "familia": ["familia", "familias"],
    "bodega": ["bodega", "bodegas", "almacen", "almacén", "ubicacion", "ubicación"],
    "ventas totales": [
        "ventas",
        "venta",
        "ventas totales",
        "sales",
        "ventas en dolares",
        "ventas en dolar",
        "ventas monetarias",
    ],
    "ventas costo": [
        "ventas costo",
        "costo de ventas",
        "costo ventas",
        "costo de la venta",
    ],
    "margen bruto total": [
        # Monetario ($). NO incluir «margen» ni «margen de utilidad» sueltos.
        "margen bruto",
        "margen bruto total",
        "gross margin",
        "gross margin dollars",
        "utilidad bruta",
        "utilidad bruta total",
        "ganancia bruta",
        "ganancia bruta total",
        "margen en dolares",
        "margen en dolar",
        "margen monetario",
    ],
    "margen utilidad ventas": [
        # Porcentual (%). «margen de utilidad» = % , NO $ .
        "margen utilidad ventas",
        "margen de utilidad",
        "margen utilidad",
        "margen porcentaje",
        "margen %",
        "margen porcentual",
        "% margen",
        "porcentaje de margen",
        "margen bruto porcentual",
        "porcentaje de utilidad",
        "utilidad porcentual",
        "% utilidad",
        "% de utilidad",
        "margen de utilidad porcentual",
        "margen porcentual de utilidad",
        "pct margen",
        "pct utilidad",
    ],
    "cubicaje inventario": [
        "cubicaje inventario",
        "cubicaje",
        "volumen inventario",
        "metros cubicos",
        "m3",
    ],
    "cubicaje tarima": [
        "cubicaje tarima",
        "cubicaje de tarima",
    ],
    "valor inventario promedio": [
        "valor inventario",
        "valor del inventario",
        "inventario valor",
        "valor promedio inventario",
        "valor promedio del inventario",
        "inventario promedio en dolares",
        "inventario promedio en dolar",
        "inventario promedio monetario",
        "inventario promedio valor",
        "valor inventario promedio",
        "inventario en dolares",
        "inventario en dolar",
    ],
    "inventario final bulto": [
        "stock disponible",
        "existencia",
        "inventario disponible",
        "inventario final",
        "bultos inventario",
        "stock",
        "stock actual",
    ],
    # NO incluir «inventario promedio» solo: ambigua ($ vs bultos).
    "inventario promedio bultos": [
        "inventario promedio bultos",
        "inventario promedio en bultos",
        "promedio bultos",
        "bultos promedio",
        "inventario fisico promedio",
        "inventario físico promedio",
    ],
    "rotacion": ["rotacion", "rotación", "turnover"],
    "meses inventario": [
        "meses inventario",
        "meses de inventario",
        "cover",
        "cobertura",
    ],
    "bultos despachados mes": [
        "bultos despachados",
        "despachos",
        "unidades despachadas",
    ],
    "unidades vendidas": [
        "unidades vendidas",
        "ventas en unidades",
        "venta en unidades",
        "unidades",
    ],
    "bultos vendidos": ["bultos vendidos", "ventas en bultos"],
    "costo unitario bulto": ["costo unitario", "costo uni"],
    "precio unitario bulto": ["precio unitario", "precio"],
    "EVAI": ["evai", "economic value"],
    "GMROI": ["gmroi", "gnroi", "gross margin return"],
    "stock de seguridad": [
        "stock de seguridad",
        "inventario de seguridad",
        "ss",
        "safety stock",
    ],
    "demanda en el tiempo de entrega": [
        "demanda tr",
        "demanda lead time",
        "demanda tiempo entrega",
        "demanda durante el tiempo de entrega",
    ],
    "cantidad minima de inventario": [
        "cantidad minima",
        "cantidad mínima",
        "inventario minimo",
        "inventario mínimo",
        "minimo inventario",
        "mínimo inventario",
    ],
    "inventario objetivo": [
        "cantidad maxima",
        "cantidad máxima",
        "inventario maximo",
        "inventario máximo",
        "inventario objetivo",
        "maximo inventario",
        "máximo inventario",
    ],
    "cantidad a comprar": [
        "cantidad a comprar",
        "cantidad recomendada",
        "compra recomendada",
        "reposicion",
        "reposición",
    ],
    "monto compra": [
        "monto compra",
        "monto de compra",
        "inversion compra",
        "inversión compra",
    ],
    "valor inventario transito": [
        "transito",
        "tránsito",
        "inventario transito",
        "inventario en transito",
    ],
    "pronostico": ["pronostico", "pronóstico", "forecast"],
    "pronostico ajustado": [
        "pronostico ajustado",
        "pronóstico ajustado",
        "forecast ajustado",
    ],
    "tiempo entrega": ["tiempo entrega", "lead time", "leadtime", "dias entrega"],
    "fill rate": ["fill rate", "fillrate", "nivel de servicio"],
    "LOVA": ["lova"],
}

_DIM_CANDIDATAS = {
    "categoria",
    "subcategoria",
    "clase",
    "proveedor",
    "codigo",
    "descripcion",
    "pais",
    "marca",
    "familia",
    "bodega",
    "ubicacion",
    "almacen",
}


def _norm(texto: str) -> str:
    s = unicodedata.normalize("NFKD", str(texto or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9\s%]", " ", s)
    return " ".join(s.split())


def _formato_columna(nombre: str, serie: pd.Series) -> str:
    n = _norm(nombre)
    if any(k in n for k in ("margen utilidad", "porcent", "fill rate")) or n.endswith(
        " %"
    ):
        return "porcentaje"
    if any(
        k in n
        for k in (
            "ventas totales",
            "margen bruto",
            "valor inventario",
            "costo unitario",
            "precio unitario",
            "monto",
            "evai",
            "icc",
            "transito",
            "ventas costo",
            "costo mantener",
        )
    ):
        return "moneda"
    # «costo» / «precio» sueltos
    if ("costo" in n or "precio" in n or "monto" in n) and "bulto" not in n.replace(
        "costo unitario bulto", "x"
    ):
        if "unitario" in n or "monto" in n or "ventas" in n:
            return "moneda"
    if "rotacion" in n or "gmroi" in n or "gnroi" in n or "lova" in n:
        return "decimal"
    if "meses" in n:
        return "meses"
    if pd.api.types.is_numeric_dtype(serie):
        return "numero"
    return "texto"


def _unidad_columna(nombre: str, formato: str) -> str | None:
    n = _norm(nombre)
    if formato == "moneda":
        return "moneda"
    if formato == "porcentaje":
        return "porcentaje"
    if formato == "meses" or "meses" in n:
        return "meses"
    if "tiempo entrega" in n or (n.startswith("dias") or " dias" in n):
        return "dias"
    if any(
        k in n
        for k in (
            "bulto",
            "bultos",
            "unidad",
            "unidades",
            "tarima",
            "caja",
            "cajas",
            "cantidad",
            "stock",
            "inventario final",
            "inventario promedio bultos",
            "demanda",
            "pronostico",
        )
    ):
        if "valor" in n or "monto" in n or "dolar" in n:
            return "moneda"
        return "bultos"
    if "rotacion" in n or "gmroi" in n or "gnroi" in n or "lova" in n:
        return "ratio"
    return None


def _rol_columna(nombre: str, serie: pd.Series, formato: str) -> str:
    n = _norm(nombre)
    if n in ("codigo", "sku") or n.endswith(" id"):
        return "identificador"
    if any(k in n for k in ("fecha", "periodo", "anio", "año", "mes ", " date")):
        if not pd.api.types.is_numeric_dtype(serie) or "demanda mes" in n:
            if "demanda mes" in n:
                return "metrica"
            return "fecha"
    if n in _DIM_CANDIDATAS or any(n == d or n.startswith(d) for d in _DIM_CANDIDATAS):
        if not pd.api.types.is_numeric_dtype(serie):
            return "dimension"
    if pd.api.types.is_numeric_dtype(serie):
        # baja cardinalidad numérica etiquetada como clase? raro → métrica
        return "metrica"
    # texto con pocos valores únicos → dimensión
    nunique = int(serie.nunique(dropna=True))
    if 0 < nunique <= max(200, int(len(serie) * 0.5)):
        return "dimension"
    return "dimension" if formato == "texto" else "metrica"


def _operaciones_validas(rol: str, unidad: str | None) -> list[str]:
    if rol != "metrica":
        return ["count"]
    if unidad in ("ratio", "porcentaje", "meses", "dias"):
        return ["mean", "median", "min", "max", "count"]
    return ["sum", "mean", "median", "min", "max", "count"]


def construir_catalogo(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Compat: nombre_real → meta básica. Preferir descubrir_schema."""
    return descubrir_schema(df)


def descubrir_schema(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Descubre todas las columnas del DF con rol, unidad, formato y valores."""
    catalogo: dict[str, dict[str, Any]] = {}
    for col in df.columns:
        serie = df[col]
        formato = _formato_columna(col, serie)
        unidad = _unidad_columna(col, formato)
        rol = _rol_columna(col, serie, formato)
        sinonimos = list(_SINONIMOS_FIJOS.get(col, []))
        if _norm(col) not in {_norm(s) for s in sinonimos}:
            sinonimos.append(_norm(col))
        valores: list[str] | None = None
        if rol in ("dimension", "identificador"):
            # Limitar para no inflar memoria en descripciones muy largas
            if col == "descripcion":
                valores = None  # match por contención puntual, no índice completo
            else:
                vals = sorted({str(v) for v in serie.dropna().unique()}, key=lambda x: (-len(str(x)), str(x)))
                valores = vals[:5000]
        entry = {
            "nombre": col,
            "nombre_visible": col,
            "normalizado": _norm(col),
            "dtype": str(serie.dtype),
            "formato": formato,
            "unidad": unidad,
            "rol": rol,
            "sinonimos": sinonimos,
            "operaciones": _operaciones_validas(rol, unidad),
            "valores_unicos": valores,
            "n_nulos": int(serie.isna().sum()),
            "n_valores": int(serie.notna().sum()),
            "n_unicos": int(serie.nunique(dropna=True)),
            "funcion_empresarial": None,
            "derivada": False,
        }
        catalogo[col] = entry
    # Incorporar métricas derivadas registradas (auditables)
    try:
        import asistente_derivadas as der

        catalogo = der.enriquecer_catalogo_derivadas(catalogo)
    except Exception:
        pass
    return catalogo


def match_valor(consulta: str, opciones: list[str]) -> str | None:
    """Match exacto / contención (valor más largo) / difuso ligero."""
    q = _norm(consulta)
    if not q or not opciones:
        return None
    norms = {op: _norm(op) for op in opciones}
    for op, n in norms.items():
        if n == q:
            return op
    hits = [op for op, n in norms.items() if n and (q == n or q in n or n in q)]
    if hits:
        return sorted(hits, key=lambda o: len(norms[o]), reverse=True)[0]
    mejores: list[tuple[float, str]] = []
    for op, n in norms.items():
        if not n:
            continue
        ratio = SequenceMatcher(None, q, n).ratio()
        if ratio >= 0.85:
            mejores.append((ratio, op))
    if not mejores:
        return None
    mejores.sort(key=lambda x: x[0], reverse=True)
    return mejores[0][1]


def valores_cercanos(consulta: str, opciones: list[str], n: int = 8) -> list[str]:
    q = _norm(consulta)
    scored = []
    for op in opciones:
        on = _norm(op)
        ratio = SequenceMatcher(None, q, on).ratio()
        if q and on and (q in on or on in q):
            ratio = max(ratio, 0.8)
        scored.append((ratio, op))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [op for r, op in scored[:n] if r >= 0.45]


def metricas_relacionadas(consulta: str, schema: dict[str, dict[str, Any]]) -> list[str]:
    q = _norm(consulta)
    toks = [t for t in q.split() if len(t) > 2]
    rel = []
    for col, meta in schema.items():
        if meta.get("rol") != "metrica":
            continue
        blob = meta["normalizado"] + " " + " ".join(meta.get("sinonimos") or [])
        if any(t in blob for t in toks):
            rel.append(col)
    return list(dict.fromkeys(rel))[:10]


def _indice_valores(
    schema: dict[str, dict[str, Any]],
) -> list[tuple[str, str, str]]:
    """Lista (norm_valor, columna, valor_original) ordenada por longitud desc."""
    items: list[tuple[str, str, str]] = []
    for col, meta in schema.items():
        if meta.get("rol") not in ("dimension", "identificador"):
            continue
        if col == "descripcion":
            continue
        for v in meta.get("valores_unicos") or []:
            nv = _norm(v)
            if len(nv) < 2:
                continue
            items.append((nv, col, v))
    items.sort(key=lambda x: len(x[0]), reverse=True)
    return items


def encontrar_valores_en_frase(
    texto: str,
    schema: dict[str, dict[str, Any]],
    df: pd.DataFrame | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Detecta valores de dimensiones en la frase (match del valor completo más largo).

    Retorna (filtros[{column, operator, value}], mensaje_ambiguedad|None).
    No divide compuestos como «Harinas y Pastas» por la conjunción «y».
    """
    t = _norm(texto)
    if not t:
        return [], None

    indice = _indice_valores(schema)
    filtros: list[dict[str, Any]] = []
    usados_spans: list[tuple[int, int]] = []
    ambiguedades: list[str] = []

    def _ocupado(start: int, end: int) -> bool:
        for a, b in usados_spans:
            if not (end <= a or start >= b):
                return True
        return False

    for nv, col, original in indice:
        if len(nv) < 3 and col != "codigo":
            continue
        # Buscar como token/frase completa
        pattern = rf"(?<![a-z0-9]){re.escape(nv)}(?![a-z0-9])"
        m = re.search(pattern, t)
        if not m:
            continue
        start, end = m.start(), m.end()
        if _ocupado(start, end):
            continue
        # ¿El mismo valor en otra dimensión?
        otras = [
            (c, o)
            for n2, c, o in indice
            if n2 == nv and c != col
        ]
        # Preferir si la frase menciona el nombre de la dimensión
        meta = schema.get(col, {})
        menciones_col = any(
            _norm(s) in t for s in [col, *meta.get("sinonimos", [])] if len(_norm(s)) >= 3
        )
        if otras and not menciones_col:
            # Si solo una aparición y columnas distintas → aclarar
            cols_amb = sorted({col, *[c for c, _ in otras]})
            # Excepción: codigo vs descripcion no aplica aquí
            if len(cols_amb) > 1:
                # Si el valor es claramente de una sola columna por cardinalidad en frase
                # con prefijo «de la categoría» etc. ya se resuelve en fusionar_explicitos
                # Aquí solo ambigüedad real
                preferidas = [c for c in cols_amb if any(_norm(s) in t for s in schema[c].get("sinonimos", []) + [c])]
                if len(preferidas) == 1:
                    col = preferidas[0]
                    original = next(o for n2, c, o in indice if n2 == nv and c == col)
                else:
                    ambiguedades.append(
                        f"«{original}» aparece en {', '.join(cols_amb)}. "
                        f"¿A cuál se refiere?"
                    )
                    usados_spans.append((start, end))
                    continue
        usados_spans.append((start, end))
        filtros.append({"column": col, "operator": "eq", "value": original})

    if ambiguedades:
        return filtros, ambiguedades[0]
    return filtros, None


def detectar_unidad_inventario(texto: str) -> str | None:
    """Devuelve 'moneda', 'bultos' o None si la unidad no está clara."""
    t = _norm(texto)
    crudo = str(texto or "").lower()
    contexto_inv = es_consulta_inventario_promedio(texto) or (
        "inventario" in t and ("promedio" in t or "valor" in t)
    )
    if not contexto_inv:
        return None

    pistas_moneda = (
        "$" in crudo
        or any(
            k in t
            for k in (
                "dolar",
                "dolares",
                "dinero",
                "monetario",
                "monetaria",
                "monto",
                "costo",
            )
        )
        or "valor" in t
    )
    pistas_bultos = any(
        k in t
        for k in (
            "bulto",
            "bultos",
            "unidad",
            "unidades",
            "cantidad fisica",
            "cantidad física",
            "volumen",
            "fisico",
            "físico",
            "caja",
            "cajas",
            "tarima",
            "tarimas",
        )
    )
    if "valor promedio" in t and "inventario" in t:
        pistas_moneda = True
        pistas_bultos = False
    if "valor inventario" in t or "inventario en dolar" in t:
        pistas_moneda = True
        pistas_bultos = False

    if pistas_moneda and not pistas_bultos:
        return "moneda"
    if pistas_bultos and not pistas_moneda:
        return "bultos"
    if pistas_moneda and pistas_bultos:
        if re.search(
            r"inventario\s+promedio\s+(en\s+)?(dolar|dolares|dinero|valor|monetario)",
            t,
        ) or "$" in crudo:
            return "moneda"
        if re.search(
            r"inventario\s+promedio\s+(en\s+)?(bulto|bultos|unidad|unidades)",
            t,
        ):
            return "bultos"
        if "valor" in t:
            return "moneda"
        return "bultos"
    return None


def es_consulta_inventario_promedio(texto: str) -> bool:
    t = _norm(texto)
    return (
        "inventario promedio" in t
        or "promedio del inventario" in t
        or "valor promedio del inventario" in t
        or "valor inventario promedio" in t
        or ("valor promedio" in t and "inventario" in t)
        or ("inventario en dolar" in t)
        or ("inventario en bulto" in t)
    )


def resolver_inventario_promedio(
    texto: str, df: pd.DataFrame
) -> tuple[str | None, str | None]:
    col_moneda = "valor inventario promedio"
    col_bultos = "inventario promedio bultos"
    if col_moneda not in df.columns and col_bultos not in df.columns:
        return None, "No hay columnas de inventario promedio en el DataFrame."

    unidad = detectar_unidad_inventario(texto)
    if unidad == "moneda":
        if col_moneda not in df.columns:
            return None, "No existe la columna monetaria «valor inventario promedio»."
        return col_moneda, None
    if unidad == "bultos":
        if col_bultos not in df.columns:
            return None, "No existe la columna «inventario promedio bultos»."
        return col_bultos, None
    return None, (
        "¿Desea el inventario promedio en **dólares** "
        "(valor inventario promedio) o en **bultos** "
        "(inventario promedio bultos)?"
    )


def extraer_filtros_frase(texto: str, df: pd.DataFrame) -> dict[str, str]:
    """Compat: dict columna→valor. Preferir encontrar_valores_en_frase."""
    schema = descubrir_schema(df)
    filtros, _amb = encontrar_valores_en_frase(texto, schema, df)
    out: dict[str, str] = {}
    for f in filtros:
        out[f["column"]] = str(f["value"])
    # explícitos
    t = _norm(texto)
    for col, pat in (
        (
            "categoria",
            r"(?<!sub)categor[ií]a\s+([a-z0-9\s&]+?)(?=\s+de\s+mayor|\s+de\s+menor|\s+orden|\s+y\s+|\s*$|,|\.)",
        ),
        (
            "subcategoria",
            r"subcategor[ií]a\s+([a-z0-9\s&]+?)(?=\s+de\s+mayor|\s+de\s+menor|\s*$|,|\.)",
        ),
        (
            "proveedor",
            r"(?:del\s+)?proveedor\s+([a-z0-9\s&]+?)(?=\s+de\s+mayor|\s+de\s+menor|\s*$|,|\.)",
        ),
    ):
        if col in out or col not in df.columns:
            continue
        m = re.search(pat, t)
        if not m:
            continue
        opts = sorted({str(v) for v in df[col].dropna().unique()})
        hit = match_valor(m.group(1), opts)
        if hit:
            out[col] = hit
    return out


def etiqueta_metrica_legible(columna: str) -> str:
    mapa = {
        "valor inventario promedio": "valor promedio del inventario ($)",
        "inventario promedio bultos": "inventario promedio (bultos)",
        "inventario final bulto": "inventario final (bultos)",
        "rotacion": "rotación",
        "ventas totales": "ventas totales ($)",
        "margen bruto total": "utilidad bruta / margen bruto ($)",
        "margen utilidad ventas": "margen de utilidad (%)",
        "meses inventario": "meses de inventario",
        "cantidad minima de inventario": "cantidad mínima",
        "inventario objetivo": "cantidad máxima / inventario objetivo",
        "EVAI": "EVAI ($)",
        "GMROI": "GMROI",
        "pronostico": "pronóstico",
        "pronostico ajustado": "pronóstico ajustado",
    }
    return mapa.get(columna, columna)


def es_consulta_margen_o_utilidad(texto: str) -> bool:
    """True si la frase habla de margen / utilidad (monetario o %)."""
    t = _norm(texto)
    return any(
        k in t
        for k in (
            "margen",
            "utilidad",
            "ganancia bruta",
            "gross margin",
        )
    )


def detectar_tipo_margen(texto: str) -> str | None:
    """'porcentaje' | 'moneda' | None (ambiguo)."""
    t = _norm(texto)
    # Señales de porcentaje (prioridad)
    if any(
        k in t
        for k in (
            "margen de utilidad",
            "margen utilidad",
            "margen porcentual",
            "margen porcentaje",
            "porcentaje de margen",
            "porcentaje de utilidad",
            "utilidad porcentual",
            "margen bruto porcentual",
            "% margen",
            "% utilidad",
            "% de utilidad",
            "pct margen",
            "pct utilidad",
        )
    ):
        return "porcentaje"
    if ("%" in str(texto) or " por ciento" in t or "porcent" in t) and (
        "margen" in t or "utilidad" in t
    ):
        return "porcentaje"
    # Señales monetarias
    if any(
        k in t
        for k in (
            "utilidad bruta",
            "ganancia bruta",
            "margen bruto",
            "margen bruto total",
            "margen monetario",
            "margen en dolar",
            "gross margin",
        )
    ):
        return "moneda"
    if any(k in t for k in ("dolar", "monetari", "en $", " en pesos")) and (
        "margen" in t or "utilidad" in t
    ):
        return "moneda"
    return None


def resolver_margen_utilidad(
    texto: str, df: pd.DataFrame
) -> tuple[str | None, str | None]:
    """Separa margen de utilidad (%) vs utilidad bruta / margen bruto ($)."""
    col_pct = "margen utilidad ventas"
    col_mon = "margen bruto total"
    tipo = detectar_tipo_margen(texto)
    if tipo == "porcentaje":
        if col_pct not in df.columns:
            return None, "No existe la columna porcentual «margen utilidad ventas»."
        return col_pct, None
    if tipo == "moneda":
        if col_mon not in df.columns:
            return None, "No existe la columna monetaria «margen bruto total»."
        return col_mon, None
    # Ambiguo: «margen» / «utilidad» sin calificar
    if es_consulta_margen_o_utilidad(texto):
        return None, (
            "¿Desea el **margen de utilidad (%)** (porcentual) o la "
            "**utilidad bruta / margen bruto ($)** (monto monetario)?"
        )
    return None, None


def validar_metrica_unidad(columna: str, texto: str) -> str | None:
    unidad = detectar_unidad_inventario(texto)
    if unidad == "moneda" and columna == "inventario promedio bultos":
        return (
            "La consulta pide dólares, pero se seleccionó inventario en bultos. "
            "Use valor inventario promedio."
        )
    if unidad == "bultos" and columna == "valor inventario promedio":
        return (
            "La consulta pide bultos, pero se seleccionó valor en dólares. "
            "Use inventario promedio bultos."
        )
    t = _norm(texto)
    tipo_margen = detectar_tipo_margen(texto)
    if tipo_margen == "porcentaje" and columna == "margen bruto total":
        return (
            "La consulta pide **margen de utilidad (%)**, pero se seleccionó "
            "utilidad bruta en dólares. Use «margen utilidad ventas»."
        )
    if tipo_margen == "moneda" and columna == "margen utilidad ventas":
        return (
            "La consulta pide **utilidad bruta ($)**, pero se seleccionó "
            "margen porcentual. Use «margen bruto total»."
        )
    if unidad == "moneda" and "bulto" in _norm(columna) and "valor" not in _norm(columna):
        return f"Incompatibilidad: pidió dólares y la columna «{columna}» es física."
    # mínimo vs máximo
    if "minima" in t or "mínima" in texto.lower() or "minimo" in t:
        if columna == "inventario objetivo" and "max" not in t:
            return "Pidió cantidad mínima; la columna seleccionada es de máximo/objetivo."
    if "maxima" in t or "máxima" in texto.lower() or "maximo" in t:
        if columna == "cantidad minima de inventario":
            return "Pidió cantidad máxima; la columna seleccionada es de mínimo."
    return None


def resolver_columna(
    consulta: str,
    df: pd.DataFrame,
    *,
    catalogo: dict[str, dict[str, Any]] | None = None,
    contexto_frase: str | None = None,
) -> tuple[str | None, str | None]:
    """Resuelve sinónimo → columna real. Devuelve (columna, error_o_aclaracion)."""
    frase = contexto_frase or consulta
    if es_consulta_inventario_promedio(consulta):
        return resolver_inventario_promedio(frase, df)
    if es_consulta_margen_o_utilidad(consulta):
        col_m, err_m = resolver_margen_utilidad(frase, df)
        if col_m or err_m:
            return col_m, err_m

    cat = catalogo or descubrir_schema(df)
    q = _norm(consulta)
    if not q:
        return None, "Indique la métrica o columna a consultar."

    for col, meta in cat.items():
        if meta["normalizado"] == q:
            return col, None

    for col, meta in cat.items():
        if q in {_norm(s) for s in meta["sinonimos"]}:
            return col, None

    hits: list[tuple[int, str]] = []
    for col, meta in cat.items():
        score = 0
        if q == meta["normalizado"]:
            score = 1000
        elif q in meta["normalizado"] or meta["normalizado"] in q:
            score = len(meta["normalizado"])
        for s in meta["sinonimos"]:
            sn = _norm(s)
            if q == sn:
                score = max(score, 900 + len(sn))
            elif q in sn or sn in q:
                score = max(score, len(sn))
        if score:
            hits.append((score, col))
    hits.sort(key=lambda x: x[0], reverse=True)
    cols_hit = list(dict.fromkeys([c for _, c in hits]))

    if len(cols_hit) == 1:
        err = validar_metrica_unidad(cols_hit[0], frase)
        if err:
            return None, err
        return cols_hit[0], None
    if len(cols_hit) > 1:
        inv_cols = [
            c
            for c in cols_hit
            if c
            in (
                "valor inventario promedio",
                "inventario promedio bultos",
                "inventario final bulto",
            )
        ]
        if len(inv_cols) >= 2 or any("inventario" in _norm(c) for c in cols_hit):
            unidad = detectar_unidad_inventario(frase)
            if unidad == "moneda" and "valor inventario promedio" in df.columns:
                return "valor inventario promedio", None
            if unidad == "bultos" and "inventario promedio bultos" in df.columns:
                return "inventario promedio bultos", None
            if "inventario promedio" in q or "inventario" in q:
                return None, (
                    "¿Desea el inventario promedio en **dólares** o en **bultos**?"
                )
        # margen % vs utilidad bruta $
        if "margen utilidad ventas" in cols_hit and "margen bruto total" in cols_hit:
            col_m, err_m = resolver_margen_utilidad(frase, df)
            if col_m or err_m:
                return col_m, err_m
        # min vs max
        if "cantidad minima de inventario" in cols_hit and "inventario objetivo" in cols_hit:
            if "max" in q:
                return "inventario objetivo", None
            if "min" in q:
                return "cantidad minima de inventario", None
            return None, (
                "¿Desea la **cantidad mínima** o la **cantidad máxima** "
                "(inventario objetivo)?"
            )
        return None, (
            f"«{consulta}» es ambiguo. Columnas relacionadas: "
            + ", ".join(f"`{h}`" for h in cols_hit[:8])
        )

    rel = metricas_relacionadas(consulta, cat)
    msg = f"No existe la columna «{consulta}»."
    if rel:
        msg += " Relacionadas disponibles: " + ", ".join(f"`{r}`" for r in rel)
    else:
        msg += " Use listar_columnas para ver el catálogo."
    return None, msg


def listar_columnas_payload(df: pd.DataFrame) -> dict[str, Any]:
    cat = descubrir_schema(df)
    items = [
        {
            "columna": meta["nombre"],
            "rol": meta.get("rol"),
            "formato": meta["formato"],
            "unidad": meta.get("unidad"),
            "sinonimos": meta["sinonimos"][:8],
            "n_unicos": meta.get("n_unicos"),
        }
        for meta in cat.values()
    ]
    return {
        "ok": True,
        "n_columnas": len(items),
        "columnas": items,
        "mensaje": f"Catálogo dinámico con {len(items)} columnas del DataFrame procesado.",
    }


def es_reposicion_por_minimo(texto: str) -> bool:
    """True si la frase menciona reposición/compra según mínimo (como filtro o tema).

    Ya NO implica un reporte cerrado: el planificador lo convierte en filtro
    componible sobre «cantidad a comprar segun minimo».
    """
    t = _norm(texto)
    claves = (
        "segun el minimo",
        "segun inventario minimo",
        "segun el inventario minimo",
        "inventario minimo",
        "debajo del minimo",
        "bajo el minimo",
        "bajo minimo",
        "por debajo del minimo",
        "reposicion por minimo",
        "reposicion segun el minimo",
        "reponer segun el minimo",
        "comprarse segun el minimo",
        "comprar segun el minimo",
        "necesitan comprarse segun",
        "necesitan comprar segun",
        "deben comprarse segun",
        "deben comprar segun",
        "hay que comprar segun",
        "no deben comprarse",
        "no hay que comprar",
        "no necesitan comprarse",
        "articulos que necesitan comprarse",
        "articulos que deben comprarse",
        "articulos que no deben",
        "cantidad a comprar segun el minimo",
    )
    if any(k in t for k in claves):
        return True
    if (
        any(k in t for k in ("comprar", "compra", "compras", "reponer", "reposicion", "necesitan", "deben"))
        and ("minimo" in t or "minima" in t)
        and "rotacion" not in t
    ):
        return True
    return False


def menciona_rotacion_objetivo(texto: str) -> bool:
    """True solo si el usuario pide explícitamente rotación objetivo/deseada."""
    t = _norm(texto)
    if "rotacion objetivo" in t or "rotacion deseada" in t:
        return True
    if "alcanzar" in t and "rotacion" in t:
        return True
    # «para una rotación de 4» / «con rotación objetivo» — NO «con rotación menor que 2»
    if re.search(
        r"\b(para|con)\s+(una\s+)?rotacion\s+(objetivo|deseada|de\s+\d+|=\s*\d+)",
        t,
    ):
        return True
    if re.search(r"\brotacion\s+(de\s+)?\d+\b", t) and any(
        k in t for k in ("comprar", "compra", "compras", "reposicion", "reponer", "plan")
    ):
        return True
    return False


def es_consulta_compras(texto: str) -> bool:
    """Compra_por_rotación: solo con rotación objetivo explícita o plan de compra."""
    if es_reposicion_por_minimo(texto) and not menciona_rotacion_objetivo(texto):
        return False
    t = _norm(texto)
    if menciona_rotacion_objetivo(texto):
        return True
    if any(
        k in t
        for k in (
            "plan de compra",
            "plan de compras",
            "orden de compra",
            "sku a comprar",
            "skus a comprar",
        )
    ):
        return True
    # «comprar» genérico SIN mínimo ni rotación → aún compras (OpenAI pedirá rotación)
    if any(k in t for k in ("comprar", "compra", "compras", "reponer", "reposicion")):
        if "minimo" in t or "minima" in t:
            return False
        return True
    return False


def clasificar_intencion_compra(texto: str) -> str | None:
    if es_reposicion_por_minimo(texto) and not menciona_rotacion_objetivo(texto):
        return "reposicion_por_minimo"  # filtro componible, no reporte cerrado
    if es_consulta_compras(texto):
        return "compra_por_rotacion"
    return None
