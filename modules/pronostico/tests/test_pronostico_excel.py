"""Pruebas de la escritura de «fill rate deseado» en el Excel."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

import openpyxl
import pandas as pd

_DIR = os.path.dirname(os.path.abspath(__file__))
_PRON = os.path.dirname(_DIR)
if _PRON not in sys.path:
    sys.path.insert(0, _PRON)

import pronostico_calculos as pc  # noqa: E402
import pronostico_excel as pexcel  # noqa: E402


class _ConCarpetaTemporal(unittest.TestCase):
    def setUp(self) -> None:
        self.carpeta = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.carpeta, ignore_errors=True)


class TestLibroMinimo(_ConCarpetaTemporal):
    def _crear(self) -> str:
        ruta = os.path.join(self.carpeta, "mini.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "data"
        ws.append(["codigo", "clase", "EVAI"])
        for codigo, clase in (("1", "A+"), ("2", "A"), ("3", "B"), ("4", "C"), ("5", "C-"), ("6", "Z")):
            ws.append([codigo, clase, None])
        wb.create_sheet("parametros").append(["x", 1])
        wb.save(ruta)
        return ruta

    def test_agrega_columna_despues_de_la_ultima(self) -> None:
        ruta = self._crear()
        resultado = pexcel.actualizar_fill_rate_excel(ruta)
        self.assertEqual(resultado.estado, "actualizado")
        self.assertEqual(resultado.columna, "D")
        ws = openpyxl.load_workbook(ruta)["data"]
        self.assertEqual(ws["D1"].value, pc.COL_FILL_RATE)
        self.assertEqual([ws[f"D{i}"].value for i in range(2, 8)], [0.997, 0.97, 0.9, 0.6, 0.5, None])
        self.assertEqual(ws["D2"].number_format, "0.0%")

    def test_segunda_pasada_sin_cambios(self) -> None:
        ruta = self._crear()
        pexcel.actualizar_fill_rate_excel(ruta)
        self.assertEqual(pexcel.actualizar_fill_rate_excel(ruta).estado, "sin cambios")

    def test_si_cambia_la_clase_se_actualiza_el_valor(self) -> None:
        ruta = self._crear()
        pexcel.actualizar_fill_rate_excel(ruta)
        wb = openpyxl.load_workbook(ruta)
        wb["data"]["B4"] = "A+"
        wb.save(ruta)
        resultado = pexcel.actualizar_fill_rate_excel(ruta)
        self.assertEqual((resultado.estado, resultado.columna), ("actualizado", "D"))
        self.assertEqual(openpyxl.load_workbook(ruta)["data"]["D4"].value, 0.997)

    def test_archivo_inexistente(self) -> None:
        self.assertEqual(pexcel.actualizar_fill_rate_excel(os.path.join(self.carpeta, "no.xlsx")).estado, "error")


class TestExcelReal(_ConCarpetaTemporal):
    def setUp(self) -> None:
        super().setUp()
        if not os.path.isfile(pc.ARCHIVO_EXCEL_PATH):
            self.skipTest("No está el Excel compartido")
        self.ruta = os.path.join(self.carpeta, "perfilado.xlsx")
        shutil.copy2(pc.ARCHIVO_EXCEL_PATH, self.ruta)

    def test_conserva_formulas_y_resto_de_datos(self) -> None:
        antes = pd.read_excel(self.ruta, pc.HOJA_DATOS).drop(columns=[pc.COL_FILL_RATE], errors="ignore")
        resultado = pexcel.actualizar_fill_rate_excel(self.ruta)
        self.assertIn(resultado.estado, ("actualizado", "sin cambios"))

        despues = pd.read_excel(self.ruta, pc.HOJA_DATOS)
        self.assertEqual(despues.columns[-1], pc.COL_FILL_RATE)
        self.assertEqual(list(despues.columns[-2:]), ["EVAI", pc.COL_FILL_RATE])
        pd.testing.assert_frame_equal(antes, despues.drop(columns=[pc.COL_FILL_RATE]))

        con_clase = despues[despues["clase"].notna()]
        esperado = pc.fill_rate_deseado(con_clase["clase"])
        pd.testing.assert_series_equal(con_clase[pc.COL_FILL_RATE], esperado, check_names=False)

        ws = openpyxl.load_workbook(self.ruta)[pc.HOJA_DATOS]
        self.assertEqual(ws["W2"].value, "=AVERAGE(K2:V2)")
        self.assertEqual(ws["Z2"].value, "=NORMINV(Y2,W2,X2)")
        self.assertEqual(pd.read_excel(self.ruta, "parametros", header=None).shape,
                         pd.read_excel(pc.ARCHIVO_EXCEL_PATH, "parametros", header=None).shape)


if __name__ == "__main__":
    unittest.main()
