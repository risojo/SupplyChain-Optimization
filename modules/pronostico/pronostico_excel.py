"""Escritura de la columna «fill rate deseado» en el Excel compartido.

Edita directamente el XML de la hoja ``data`` dentro del .xlsx: agrega o
actualiza solo esa columna (a la derecha de la última columna con encabezado,
hoy después de ``EVAI``) y deja el resto del archivo byte a byte igual.
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
from xml.sax.saxutils import escape

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
        return float(m.group(1)) if m and 't="' not in celda else None
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

    temporal = f"{ruta}.tmp"
    try:
        with zipfile.ZipFile(ruta) as origen, zipfile.ZipFile(temporal, "w") as destino:
            for info in origen.infolist():
                destino.writestr(info, reemplazos.get(info.filename, origen.read(info.filename)))
        os.replace(temporal, ruta)
    except PermissionError:
        return ResultadoEscritura("bloqueado", columna=col_fill, mensaje=pc.MSG_ARCHIVO_ABIERTO)
    except OSError as exc:
        return ResultadoEscritura("error", columna=col_fill, mensaje=f"No se pudo guardar el Excel: {exc}")
    finally:
        if os.path.exists(temporal):
            os.remove(temporal)
    return ResultadoEscritura("actualizado", columna=col_fill, celdas=cambios)
