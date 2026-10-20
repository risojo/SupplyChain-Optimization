"""Escritura en el Excel compartido: «fill rate deseado» y el pronóstico calculado.

Edita directamente el XML de la hoja ``data`` dentro del .xlsx:
- ``actualizar_fill_rate_excel``: agrega o actualiza la columna «fill rate deseado»
  (a la derecha de la última columna con encabezado, hoy después de ``EVAI``).
- ``escribir_pronostico_excel``: pone el pronóstico LRI como valor en «pronostico»
  (sustituye la fórmula AVERAGE) y deja «pronostico ajustado» = «pronostico».
El resto del archivo queda byte a byte igual.
No se usa openpyxl para guardar porque descarta los valores calculados de las
fórmulas (``pronostico``, ``desviacion standart``, ``pronostico ajustado``)
y Inventarios / Profile Pro los leerían vacíos.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from xml.sax.saxutils import escape, unescape

import numpy as np

import pronostico_calculos as pc

_NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_FORMATO_PORCENTAJE = "0.0%"
_ID_FORMATO_PROPIO = 164

_RE_FILA = re.compile(r"<row\b([^>]*?)(?:/>|>(.*?)</row>)", re.S)
_RE_CELDA = re.compile(r'<c r="([A-Z]+)(\d+)"(?:[^>]*/>|[^>]*>.*?</c>)', re.S)


@dataclass(frozen=True)
class ResultadoEscritura:
    estado: str  # "actualizado" | "sin cambios" | "bloqueado" | "error"
    columna: str | None = None
    celdas: int = 0
    mensaje: str = ""


def _indice_columna(letras: str) -> int:
    n = 0
    for ch in letras:
        n = n * 26 + (ord(ch) - 64)
    return n


def _letras_columna(indice: int) -> str:
    letras = ""
    while indice:
        indice, resto = divmod(indice - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def _ruta_hoja(z: zipfile.ZipFile, nombre: str) -> str:
    libro = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rid = next(
        s.get(f"{{{_NS_REL}}}id")
        for s in libro.iter(f"{{{_NS_MAIN}}}sheet")
        if s.get("name", "").strip().lower() == nombre
    )
    destino = next(r.get("Target") for r in rels if r.get("Id") == rid)
    return destino.lstrip("/") if destino.startswith("/") else f"xl/{destino}"


def _textos_compartidos(z: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    raiz = ET.fromstring(z.read("xl/sharedStrings.xml"))
    return [
        "".join(t.text or "" for t in si.iter(f"{{{_NS_MAIN}}}t"))
        for si in raiz.findall(f"{{{_NS_MAIN}}}si")
    ]


def _texto_celda(celda: str, compartidos: list[str]) -> str | None:
    if 't="s"' in celda:
        m = re.search(r"<v>(\d+)</v>", celda)
        return compartidos[int(m.group(1))] if m else None
    m = re.search(r"<t[^>]*>(.*?)</t>", celda, re.S) or re.search(r"<v>(.*?)</v>", celda, re.S)
    return m.group(1) if m else None


def _valor_numerico(celda: str) -> float | None:
    m = re.search(r"<v>(.*?)</v>", celda)
    try:
        return float(m.group(1)) if m and not re.match(r'<c\b[^>]*\st="', celda) else None
    except ValueError:
        return None


def _estilo_porcentaje(estilos: str) -> tuple[str, int]:
    """Índice de un estilo «0.0 %»; lo agrega a styles.xml si no existe."""
    formato = re.search(
        rf'<numFmt numFmtId="(\d+)" formatCode="{re.escape(_FORMATO_PORCENTAJE)}"\s*/>', estilos
    )
    bloque_xfs = re.search(r"<cellXfs[^>]*>(.*?)</cellXfs>", estilos, re.S)
    xfs = re.findall(r"<xf\b[^>]*?(?:/>|>.*?</xf>)", bloque_xfs.group(1), re.S)
    if formato:
        for i, xf in enumerate(xfs):
            if f'numFmtId="{formato.group(1)}"' in xf:
                return estilos, i
        id_formato = int(formato.group(1))
    else:
        ids = [int(x) for x in re.findall(r'<numFmt numFmtId="(\d+)"', estilos)]
        id_formato = max([_ID_FORMATO_PROPIO - 1, *ids]) + 1
        nuevo = f'<numFmt numFmtId="{id_formato}" formatCode="{_FORMATO_PORCENTAJE}"/>'
        if re.search(r"<numFmts\b[^>]*/>", estilos):
            estilos = re.sub(r"<numFmts\b[^>]*/>", f'<numFmts count="1">{nuevo}</numFmts>', estilos, count=1)
        elif "<numFmts" in estilos:
            estilos = re.sub(
                r'<numFmts count="(\d+)"\s*>',
                lambda m: f'<numFmts count="{int(m.group(1)) + 1}">',
                estilos,
                count=1,
            ).replace("</numFmts>", f"{nuevo}</numFmts>", 1)
        else:
            estilos = re.sub(r"(<styleSheet\b[^>]*>)", rf'\1<numFmts count="1">{nuevo}</numFmts>', estilos, count=1)

    xf = f'<xf numFmtId="{id_formato}" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    estilos = re.sub(
        r'<cellXfs count="(\d+)"\s*>',
        lambda m: f'<cellXfs count="{int(m.group(1)) + 1}">',
        estilos,
        count=1,
    ).replace("</cellXfs>", f"{xf}</cellXfs>", 1)
    return estilos, len(xfs)


def _reemplazar_celda(contenido: str, col: str, fila: int, nueva: str | None) -> tuple[str, bool]:
    """Pone ``nueva`` en la celda col+fila respetando el orden de columnas (None = borrar)."""
    destino = _indice_columna(col)
    celdas = list(_RE_CELDA.finditer(contenido))
    for m in celdas:
        if m.group(1) == col:
            if nueva == m.group(0):
                return contenido, False
            return contenido[: m.start()] + (nueva or "") + contenido[m.end():], True
    if nueva is None:
        return contenido, False
    posicion = len(contenido)
    for m in celdas:
        if _indice_columna(m.group(1)) > destino:
            posicion = m.start()
            break
    return contenido[:posicion] + nueva + contenido[posicion:], True


def _ampliar_spans(atributos: str, indice: int) -> str:
    def ajustar(m: re.Match) -> str:
        inicio, fin = int(m.group(1)), int(m.group(2))
        return f'spans="{min(inicio, indice)}:{max(fin, indice)}"'

    return re.sub(r'spans="(\d+):(\d+)"', ajustar, atributos)


def _ampliar_dimension(hoja: str, col: str) -> str:
    def ajustar(m: re.Match) -> str:
        inicio, col_fin, fila_fin = m.group(1), m.group(2), m.group(3)
        if _indice_columna(col) > _indice_columna(col_fin):
            col_fin = col
        return f'<dimension ref="{inicio}:{col_fin}{fila_fin}"/>'

    return re.sub(r'<dimension ref="([A-Z]+\d+):([A-Z]+)(\d+)"/>', ajustar, hoja, count=1)


def _celda_valor(col: str, fila: int, valor: float, estilo: int) -> str:
    return f'<c r="{col}{fila}" s="{estilo}"><v>{valor!r}</v></c>'


def _celda_encabezado(col: str, texto: str) -> str:
    return f'<c r="{col}1" t="inlineStr"><is><t>{escape(texto)}</t></is></c>'


def _guardar(ruta: str, reemplazos: dict[str, bytes], quitar: frozenset[str] = frozenset()) -> None:
    temporal = f"{ruta}.tmp"
    try:
        with zipfile.ZipFile(ruta) as origen, zipfile.ZipFile(temporal, "w") as destino:
            for info in origen.infolist():
                if info.filename not in quitar:
                    destino.writestr(info, reemplazos.get(info.filename, origen.read(info.filename)))
        os.replace(temporal, ruta)
    finally:
        if os.path.exists(temporal):
            os.remove(temporal)


def normalizar_codigo(valor: object) -> str:
    """Mismo texto para ``77001046``, ``77001046.0`` y ``"77001046"``."""
    texto = str(valor).strip()
    try:
        numero = float(texto)
    except ValueError:
        return texto
    return str(int(numero)) if numero.is_integer() else texto


def leer_pronosticos_excel(
    ruta: str | None = None,
    codigos: set[str] | None = None,
) -> dict[str, float]:
    """Lee la columna «pronostico» del Excel (valor en caché del XML) por código normalizado."""
    ruta = ruta or pc.ARCHIVO_EXCEL_PATH
    with zipfile.ZipFile(ruta) as z:
        hoja = z.read(_ruta_hoja(z, pc.HOJA_DATOS)).decode("utf-8")
        compartidos = _textos_compartidos(z)
    filas = list(_RE_FILA.finditer(hoja))
    encabezado = next((f for f in filas if re.search(r'\br="1"', f.group(1))), None)
    if encabezado is None:
        return {}
    columnas = {
        pc._nombre_canonico((_texto_celda(m.group(0), compartidos) or "").strip()): m.group(1)
        for m in _RE_CELDA.finditer(encabezado.group(2) or "")
    }
    col_codigo = columnas.get("codigo")
    col_pron = columnas.get(pc.COL_PRONOSTICO)
    if col_codigo is None or col_pron is None:
        return {}
    buscados = {normalizar_codigo(c) for c in codigos} if codigos is not None else None
    out: dict[str, float] = {}
    for f in filas:
        numero = int(re.search(r'\br="(\d+)"', f.group(1)).group(1))
        if numero < 2:
            continue
        celdas = {m.group(1): m.group(0) for m in _RE_CELDA.finditer(f.group(2) or "")}
        codigo = normalizar_codigo(_texto_celda(celdas.get(col_codigo, ""), compartidos) or "")
        if not codigo or (buscados is not None and codigo not in buscados):
            continue
        valor = _valor_numerico(celdas.get(col_pron, ""))
        if valor is None:
            continue
        out[codigo] = valor
        if buscados is not None and len(out) >= len(buscados):
            break
    return out


def _desplazar_filas(formula: str, delta: int) -> str:
    """Traslada las referencias relativas de una fórmula compartida ``delta`` filas."""

    def mover(m: re.Match) -> str:
        if m.group(3):
            return m.group(0)
        return f"{m.group(1)}{m.group(2)}{int(m.group(4)) + delta}"

    return re.sub(r"(?<![A-Za-z_.$])(\$?)([A-Z]{1,3})(\$?)(\d+)(?![\d(])", mover, formula)


def _fila_de_celda(celda: str) -> int:
    return int(re.match(r'<c r="[A-Z]+(\d+)"', celda).group(1))


def _sin_formula_compartida(celda: str, maestras: dict[str, tuple[int, str]]) -> str:
    """Convierte una celda de fórmula compartida en fórmula propia (misma fórmula, mismo valor)."""
    m = re.search(r'<f\b[^>/]*\bt="shared"[^>/]*(?:/>|>(.*?)</f>)', celda, re.S)
    if not m:
        return celda
    si = re.search(r'\bsi="(\d+)"', m.group(0)).group(1)
    fila_maestra, formula = maestras[si]
    propia = _desplazar_filas(formula, _fila_de_celda(celda) - fila_maestra)
    return celda[: m.start()] + f"<f>{escape(propia)}</f>" + celda[m.end():]


def _maestras_compartidas(hoja: str, col: str) -> dict[str, tuple[int, str]]:
    """Fórmulas compartidas que nacen en la columna ``col``: si → (fila, fórmula)."""
    maestras = {}
    for m in re.finditer(rf'<c r="{col}(\d+)"[^>]*>\s*<f\b[^>/]*\bt="shared"[^>/]*>(.*?)</f>', hoja, re.S):
        si = re.search(r'\bsi="(\d+)"', m.group(0)).group(1)
        maestras[si] = (int(m.group(1)), unescape(m.group(2)))
    return maestras


def _celda_numero(col: str, fila: int, valor: float, actual: str | None, formula: str | None = None) -> str:
    estilo = re.search(r'\bs="(\d+)"', actual or "")
    atributos = f' s="{estilo.group(1)}"' if estilo else ""
    return f'<c r="{col}{fila}"{atributos}>' + (f"<f>{formula}</f>" if formula else "") + f"<v>{valor!r}</v></c>"


def _quitar_calc_chain(z: zipfile.ZipFile) -> tuple[dict[str, bytes], frozenset[str]]:
    """Excel reconstruye la cadena de cálculo al abrir; se quita para no apuntar a fórmulas borradas."""
    if "xl/calcChain.xml" not in z.namelist():
        return {}, frozenset()
    tipos = re.sub(r'<Override[^>]*PartName="/xl/calcChain.xml"[^>]*/>', "", z.read("[Content_Types].xml").decode("utf-8"))
    rels = re.sub(r'<Relationship[^>]*Target="[^"]*calcChain.xml"[^>]*/>', "", z.read("xl/_rels/workbook.xml.rels").decode("utf-8"))
    return (
        {"[Content_Types].xml": tipos.encode("utf-8"), "xl/_rels/workbook.xml.rels": rels.encode("utf-8")},
        frozenset({"xl/calcChain.xml"}),
    )


def escribir_pronostico_excel(
    pronosticos: dict[str, float],
    ruta: str | None = None,
    *,
    forzar: bool = False,
) -> ResultadoEscritura:
    """Pone el pronóstico calculado como valor en la columna «pronostico» de la hoja ``data``.

    ``pronosticos`` va por código (``normalizar_codigo``); solo se escriben valores finitos.
    En esas filas «pronostico ajustado» pasa a ``=pronostico`` (el pronóstico LRI ya trae
    K × σ; NORMINV sumaría un segundo margen de seguridad). Las filas sin pronóstico
    (no certificados) conservan sus fórmulas.

    ``forzar=True`` reescribe aunque el XML coincida (actualiza fecha del archivo;
    útil si Excel o la app muestran datos en caché).
    """
    ruta = ruta or pc.ARCHIVO_EXCEL_PATH
    try:
        with zipfile.ZipFile(ruta) as z:
            ruta_hoja = _ruta_hoja(z, pc.HOJA_DATOS)
            hoja = z.read(ruta_hoja).decode("utf-8")
            compartidos = _textos_compartidos(z)
            extra, quitar = _quitar_calc_chain(z)
    except PermissionError:
        return ResultadoEscritura("bloqueado", mensaje=pc.MSG_ARCHIVO_ABIERTO)
    except (OSError, KeyError, StopIteration, zipfile.BadZipFile, ET.ParseError) as exc:
        return ResultadoEscritura("error", mensaje=f"No se pudo leer el Excel: {exc}")

    filas = list(_RE_FILA.finditer(hoja))
    encabezado = next((f for f in filas if re.search(r'\br="1"', f.group(1))), None)
    if encabezado is None:
        return ResultadoEscritura("error", mensaje="La hoja «data» no tiene fila de encabezados.")
    columnas = {
        pc._nombre_canonico((_texto_celda(m.group(0), compartidos) or "").strip()): m.group(1)
        for m in _RE_CELDA.finditer(encabezado.group(2) or "")
    }
    col_codigo = columnas.get("codigo")
    col_pron = columnas.get(pc.COL_PRONOSTICO)
    if col_codigo is None or col_pron is None:
        return ResultadoEscritura("error", mensaje="La hoja «data» no tiene las columnas «codigo» y «pronostico».")
    col_ajust = columnas.get(pc.COL_PRONOSTICO_AJUSTADO)
    pronosticos = {normalizar_codigo(k): float(v) for k, v in pronosticos.items() if np.isfinite(v)}
    maestras = {col: _maestras_compartidas(hoja, col) for col in (col_pron, col_ajust) if col}

    escritas = 0
    partes: list[str] = []
    ultimo = 0
    for f in filas:
        numero = int(re.search(r'\br="(\d+)"', f.group(1)).group(1))
        contenido = f.group(2) or ""
        if numero == 1 or not contenido:
            continue
        celdas = {m.group(1): m.group(0) for m in _RE_CELDA.finditer(contenido)}
        codigo = _texto_celda(celdas.get(col_codigo, ""), compartidos)
        valor = pronosticos.get(normalizar_codigo(codigo)) if codigo else None
        nuevas: dict[str, str] = {}
        if valor is None:
            for col, de_columna in maestras.items():
                actual = celdas.get(col)
                if actual and 't="shared"' in actual:
                    nuevas[col] = _sin_formula_compartida(actual, de_columna)
        else:
            nuevas[col_pron] = _celda_numero(col_pron, numero, valor, celdas.get(col_pron))
            if col_ajust:
                nuevas[col_ajust] = _celda_numero(
                    col_ajust, numero, valor, celdas.get(col_ajust), formula=f"{col_pron}{numero}"
                )
        if not forzar:
            nuevas = {col: nueva for col, nueva in nuevas.items() if nueva != celdas.get(col)}
        if not nuevas:
            continue
        if valor is not None:
            escritas += 1
        for col, nueva in nuevas.items():
            contenido, _ = _reemplazar_celda(contenido, col, numero, nueva)

        partes.append(hoja[ultimo: f.start()])
        partes.append(f"<row{f.group(1)}>{contenido}</row>")
        ultimo = f.end()

    if not partes:
        return ResultadoEscritura(
            "sin cambios",
            columna=col_pron,
            mensaje="El Excel ya tiene el mismo pronóstico LRI en disco (nada que cambiar).",
        )
    partes.append(hoja[ultimo:])
    try:
        _guardar(ruta, {ruta_hoja: "".join(partes).encode("utf-8"), **extra}, quitar)
    except PermissionError:
        return ResultadoEscritura("bloqueado", columna=col_pron, mensaje=pc.MSG_ARCHIVO_ABIERTO)
    except OSError as exc:
        return ResultadoEscritura("error", columna=col_pron, mensaje=f"No se pudo guardar el Excel: {exc}")

    # Comprobar en disco que lo escrito coincide con el LRI (evita falsos «actualizado»).
    leidos = leer_pronosticos_excel(ruta, set(pronosticos))
    desvios = [
        f"{c}: app {pronosticos[c]:,.1f} ≠ Excel {leidos.get(c, float('nan')):,.1f}"
        for c in list(pronosticos)[:20]
        if c in leidos and abs(leidos[c] - pronosticos[c]) > 1e-6
    ]
    if desvios:
        return ResultadoEscritura(
            "error",
            columna=col_pron,
            celdas=escritas,
            mensaje="Se guardó el archivo pero la lectura de control no coincide: " + "; ".join(desvios[:5]),
        )
    return ResultadoEscritura("actualizado", columna=col_pron, celdas=escritas)


def actualizar_fill_rate_excel(ruta: str | None = None) -> ResultadoEscritura:
    """Escribe/actualiza «fill rate deseado» en la hoja ``data`` según la clase de cada fila."""
    ruta = ruta or pc.ARCHIVO_EXCEL_PATH
    try:
        with zipfile.ZipFile(ruta) as z:
            ruta_hoja = _ruta_hoja(z, pc.HOJA_DATOS)
            hoja = z.read(ruta_hoja).decode("utf-8")
            estilos = z.read("xl/styles.xml").decode("utf-8")
            compartidos = _textos_compartidos(z)
    except PermissionError:
        return ResultadoEscritura("bloqueado", mensaje=pc.MSG_ARCHIVO_ABIERTO)
    except (OSError, KeyError, StopIteration, zipfile.BadZipFile, ET.ParseError) as exc:
        return ResultadoEscritura("error", mensaje=f"No se pudo leer el Excel: {exc}")

    filas = list(_RE_FILA.finditer(hoja))
    encabezado = next((f for f in filas if re.search(r'\br="1"', f.group(1))), None)
    if encabezado is None:
        return ResultadoEscritura("error", mensaje="La hoja «data» no tiene fila de encabezados.")
    titulos = {
        m.group(1): (_texto_celda(m.group(0), compartidos) or "").strip()
        for m in _RE_CELDA.finditer(encabezado.group(2) or "")
    }
    col_clase = next((c for c, t in titulos.items() if pc._nombre_canonico(t) == pc.COL_CLASE), None)
    if col_clase is None:
        return ResultadoEscritura("error", mensaje="La hoja «data» no tiene la columna «clase».")
    col_fill = next((c for c, t in titulos.items() if pc._nombre_canonico(t) == pc.COL_FILL_RATE), None)
    if col_fill is None:
        col_fill = _letras_columna(max(_indice_columna(c) for c in titulos) + 1)
    indice_fill = _indice_columna(col_fill)

    estilos_nuevos, estilo = _estilo_porcentaje(estilos)
    cambios = 0
    partes: list[str] = []
    ultimo = 0
    for f in filas:
        numero = int(re.search(r'\br="(\d+)"', f.group(1)).group(1))
        contenido = f.group(2) or ""
        if numero == 1:
            nueva = _celda_encabezado(col_fill, pc.COL_FILL_RATE)
            actual = next((m.group(0) for m in _RE_CELDA.finditer(contenido) if m.group(1) == col_fill), None)
            if actual is not None and (_texto_celda(actual, compartidos) or "").strip().lower() == pc.COL_FILL_RATE:
                nueva = actual
        else:
            clase = next(
                (_texto_celda(m.group(0), compartidos) for m in _RE_CELDA.finditer(contenido) if m.group(1) == col_clase),
                None,
            )
            valor = pc.FILL_RATE_POR_CLASE.get((clase or "").strip().upper())
            actual = next((m.group(0) for m in _RE_CELDA.finditer(contenido) if m.group(1) == col_fill), None)
            if valor is None:
                nueva = None
            elif actual is not None and _valor_numerico(actual) == valor:
                nueva = actual
            else:
                nueva = _celda_valor(col_fill, numero, valor, estilo)
        contenido_nuevo, cambio = _reemplazar_celda(contenido, col_fill, numero, nueva)
        if not cambio:
            continue
        cambios += 1
        atributos = _ampliar_spans(f.group(1), indice_fill) if nueva else f.group(1)
        partes.append(hoja[ultimo: f.start()])
        partes.append(f"<row{atributos}>{contenido_nuevo}</row>" if contenido_nuevo else f"<row{atributos}/>")
        ultimo = f.end()

    if not cambios:
        return ResultadoEscritura("sin cambios", columna=col_fill)

    partes.append(hoja[ultimo:])
    hoja_nueva = _ampliar_dimension("".join(partes), col_fill)
    usa_estilo_nuevo = f's="{estilo}"' in hoja_nueva and estilos_nuevos != estilos
    reemplazos = {ruta_hoja: hoja_nueva.encode("utf-8")}
    if usa_estilo_nuevo:
        reemplazos["xl/styles.xml"] = estilos_nuevos.encode("utf-8")

    try:
        _guardar(ruta, reemplazos)
    except PermissionError:
        return ResultadoEscritura("bloqueado", columna=col_fill, mensaje=pc.MSG_ARCHIVO_ABIERTO)
    except OSError as exc:
        return ResultadoEscritura("error", columna=col_fill, mensaje=f"No se pudo guardar el Excel: {exc}")
    return ResultadoEscritura("actualizado", columna=col_fill, celdas=cambios)
