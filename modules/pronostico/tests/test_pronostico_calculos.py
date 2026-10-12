"""Pruebas de los cálculos del módulo Pronóstico."""
from __future__ import annotations

import os
import sys
import unittest

import numpy as np
import pandas as pd

_DIR = os.path.dirname(os.path.abspath(__file__))
_PRON = os.path.dirname(_DIR)
if _PRON not in sys.path:
    sys.path.insert(0, _PRON)

import pronostico_calculos as pc  # noqa: E402


class TestNormalizacion(unittest.TestCase):
    def test_encabezados_mal_escritos(self) -> None:
        df = pd.DataFrame(columns=["Demada mes 1", "demanda_mes2", "DEMANDA MES 10", "desviacion standart"])
        cols = list(pc.normalizar_columnas(df).columns)
        self.assertEqual(cols, ["demanda mes 1", "demanda mes 2", "demanda mes 10", pc.COL_DESVIACION])

    def test_meses_ordenados_numericamente(self) -> None:
        df = pd.DataFrame(columns=["demanda mes 10", "demanda mes 2", "demanda mes 1"])
        self.assertEqual(pc.columnas_meses(df), ["demanda mes 1", "demanda mes 2", "demanda mes 10"])


class TestFormulasOficiales(unittest.TestCase):
    def test_norminv_equivale_a_media_mas_z_sigma(self) -> None:
        self.assertAlmostEqual(pc.pronostico_ajustado(100, 10, 0.8), 100 + 0.8416212335729143 * 10, places=9)

    def test_sin_variabilidad_devuelve_media(self) -> None:
        self.assertEqual(pc.pronostico_ajustado(50, 0, 0.95), 50)

    def test_calculo_y_certificacion_sintetica(self) -> None:
        demanda = [10, 12, 14, 16]
        df = pd.DataFrame([{"codigo": "A", **{f"demanda mes {i + 1}": v for i, v in enumerate(demanda)}}])
        media, desv = np.mean(demanda), np.std(demanda, ddof=1)
        df[pc.COL_PRONOSTICO] = media
        df[pc.COL_DESVIACION] = desv
        df[pc.COL_NIVEL_SERVICIO] = 0.8
        df[pc.COL_PRONOSTICO_AJUSTADO] = pc.pronostico_ajustado(media, desv, 0.8)
        fila = pc.calcular_pronostico(df).iloc[0]
        self.assertEqual(fila[pc.COL_CUADRA_EXCEL], "Sí")
        self.assertAlmostEqual(fila["tendencia mensual"], 2.0)

    def test_cambiar_nivel_ya_no_cuadra_con_excel(self) -> None:
        df = pd.DataFrame([{"codigo": "A", "demanda mes 1": 10, "demanda mes 2": 20, "demanda mes 3": 30}])
        df[pc.COL_PRONOSTICO] = 20.0
        df[pc.COL_DESVIACION] = 10.0
        df[pc.COL_PRONOSTICO_AJUSTADO] = pc.pronostico_ajustado(20, 10, 0.8)
        self.assertEqual(pc.calcular_pronostico(df, nivel_servicio=0.95).iloc[0][pc.COL_CUADRA_EXCEL], "No")


class TestCertificacionCV(unittest.TestCase):
    def test_limites_del_rango(self) -> None:
        self.assertEqual(pc.certificar_cv(0.0), pc.CERTIFICADO)
        self.assertEqual(pc.certificar_cv(0.30), pc.CERTIFICADO)
        self.assertEqual(pc.certificar_cv(0.3001), pc.NO_CERTIFICADO)
        self.assertEqual(pc.certificar_cv(0.70), pc.NO_CERTIFICADO)
        self.assertEqual(pc.certificar_cv(1.5), pc.NO_CERTIFICADO)
        self.assertEqual(pc.certificar_cv(float("nan")), pc.SIN_DEMANDA)

    def test_calculo_por_sku(self) -> None:
        estable = [100, 110, 90, 105, 95, 100]
        erratica = [10, 200, 0, 150, 5, 300]
        sin_demanda = [0] * 6
        filas = [
            {"codigo": c, **{f"demanda mes {i + 1}": v for i, v in enumerate(d)}}
            for c, d in (("E", estable), ("R", erratica), ("Z", sin_demanda))
        ]
        calc = pc.calcular_pronostico(pd.DataFrame(filas)).set_index("codigo")
        self.assertAlmostEqual(calc.loc["E", "cv"], np.std(estable, ddof=1) / np.mean(estable))
        self.assertEqual(calc.loc["E", pc.COL_CERTIFICACION], pc.CERTIFICADO)
        self.assertEqual(calc.loc["E", pc.COL_MODELO_SUGERIDO], pc.MODELO_ESTADISTICO)
        self.assertEqual(calc.loc["R", pc.COL_CERTIFICACION], pc.NO_CERTIFICADO)
        self.assertEqual(calc.loc["R", pc.COL_MODELO_SUGERIDO], pc.MODELO_ALTERNATIVO)
        self.assertEqual(calc.loc["Z", pc.COL_CERTIFICACION], pc.SIN_DEMANDA)

    def test_resumen_dispersion(self) -> None:
        serie = [10, 200, 0, 150, 5, 300, None]
        r = pc.resumen_dispersion(serie)
        validos = [10, 200, 0, 150, 5, 300]
        media, desv = np.mean(validos), np.std(validos, ddof=1)
        self.assertEqual(r.meses, 6)
        self.assertAlmostEqual(r.media, media)
        self.assertAlmostEqual(r.cv, desv / media)
        self.assertEqual((r.minimo, r.maximo), (0, 300))
        self.assertEqual(r.meses_sin_demanda, 1)
        self.assertEqual(r.meses_fuera_1sigma, sum(abs(v - media) > desv for v in validos))

    def test_resumen_por_grupo(self) -> None:
        calc = pd.DataFrame(
            {
                "proveedor": ["P1", "P1", "P2", "P2", "P2", None],
                pc.COL_CERTIFICACION: [
                    pc.CERTIFICADO,
                    pc.NO_CERTIFICADO,
                    pc.CERTIFICADO,
                    pc.CERTIFICADO,
                    pc.SIN_DEMANDA,
                    pc.CERTIFICADO,
                ],
            }
        )
        r = pc.resumen_certificacion(calc, "proveedor").set_index("grupo")
        self.assertEqual(r.loc["P1", "skus"], 2)
        self.assertEqual(r.loc["P1", "no_certificados"], 1)
        self.assertAlmostEqual(r.loc["P1", "pct_no_certificados"], 0.5)
        self.assertEqual(r.loc["P2", "certificados"], 2)
        self.assertEqual(r.loc["(sin dato)", "skus"], 1)
        self.assertEqual(r.index[0], "P1")
        self.assertEqual(int(r["skus"].sum()), len(calc))

    def test_resumen_dispersion_sin_datos(self) -> None:
        r = pc.resumen_dispersion([None, None])
        self.assertEqual(r.meses, 0)
        self.assertTrue(np.isnan(r.cv))


class TestPronosticoLRI(unittest.TestCase):
    def test_factor_k_por_fill_rate(self) -> None:
        k = pc.factor_k([0.997, 0.97, 0.90, 0.60, 0.50, None, 1.0])
        self.assertAlmostEqual(k[0], 2.7477813854, places=6)
        self.assertAlmostEqual(k[1], 1.8807936082, places=6)
        self.assertAlmostEqual(k[2], 1.2815515655, places=6)
        self.assertAlmostEqual(k[3], 0.2533471031, places=6)
        self.assertAlmostEqual(k[4], 0.0, places=9)
        self.assertTrue(np.isnan(k[5]) and np.isnan(k[6]))

    def test_promedio_mas_k_sigma_solo_certificados(self) -> None:
        estable = [100, 110, 90, 105, 95, 100]
        erratica = [10, 200, 0, 150, 5, 300]
        filas = [
            {"codigo": c, "clase": clase, **{f"demanda mes {i + 1}": v for i, v in enumerate(d)}}
            for c, clase, d in (("E", "A", estable), ("R", "A", erratica), ("M", "C-", estable))
        ]
        calc = pc.calcular_pronostico(pd.DataFrame(filas)).set_index("codigo")
        media, sigma = np.mean(estable), np.std(estable, ddof=1)
        k_a = pc.factor_k([0.97])[0]
        self.assertAlmostEqual(calc.loc["E", pc.COL_K], k_a)
        self.assertAlmostEqual(calc.loc["E", pc.COL_SEGURIDAD_K], k_a * sigma)
        self.assertAlmostEqual(calc.loc["E", pc.COL_PRONOSTICO_LRI], media + k_a * sigma)
        self.assertAlmostEqual(calc.loc["M", pc.COL_PRONOSTICO_LRI], media)
        self.assertTrue(np.isnan(calc.loc["R", pc.COL_PRONOSTICO_LRI]))

    def test_consolidado_suma_los_skus(self) -> None:
        calc = pd.DataFrame(
            {
                "proveedor": ["P1", "P1", "P2", "P2"],
                "pronostico calc": [10.0, 20.0, 5.0, 7.0],
                pc.COL_SEGURIDAD_K: [1.0, 2.0, 0.5, np.nan],
                pc.COL_PRONOSTICO_LRI: [11.0, 22.0, 5.5, np.nan],
            }
        )
        r = pc.consolidar_pronostico(calc, "proveedor").set_index("grupo")
        self.assertEqual(r.loc["P1", "skus"], 2)
        self.assertAlmostEqual(r.loc["P1", "pronostico"], 33.0)
        self.assertAlmostEqual(r.loc["P1", "seguridad"], 3.0)
        self.assertEqual(r.loc["P2", "skus"], 1)
        self.assertAlmostEqual(r["pct_total"].sum(), 1.0)


class TestFillRate(unittest.TestCase):
    def test_mapeo_por_clase(self) -> None:
        clases = pd.Series(["A+", "A", "B", "C", "C-", " a+ ", "X", None])
        esperado = [0.997, 0.97, 0.90, 0.60, 0.50, 0.997]
        resultado = pc.fill_rate_deseado(clases)
        self.assertEqual(resultado.iloc[:6].tolist(), esperado)
        self.assertTrue(resultado.iloc[6:].isna().all())

    def test_columna_nueva_va_al_final(self) -> None:
        df = pd.DataFrame({"codigo": ["1"], "clase": ["B"], "EVAI": [None]})
        out = pc.agregar_fill_rate(df)
        self.assertEqual(list(out.columns), ["codigo", "clase", "EVAI", pc.COL_FILL_RATE])
        self.assertEqual(out[pc.COL_FILL_RATE].iloc[0], 0.90)
        self.assertNotIn(pc.COL_FILL_RATE, df.columns)

    def test_columna_existente_se_recalcula_en_su_lugar(self) -> None:
        df = pd.DataFrame({"clase": ["A+"], "Fill Rate Deseado": [0.1], "EVAI": [None]})
        out = pc.agregar_fill_rate(df)
        self.assertEqual(list(out.columns), ["clase", "Fill Rate Deseado", "EVAI"])
        self.assertEqual(out["Fill Rate Deseado"].iloc[0], 0.997)


class TestExcelMaestro(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        df, err = pc.cargar_demanda()
        if df is None:
            raise unittest.SkipTest(err)
        cls.df = df

    def test_doce_meses_y_sin_filas_vacias(self) -> None:
        self.assertEqual(len(pc.columnas_meses(self.df)), 12)
        self.assertTrue(self.df["codigo"].notna().all())

    def test_archivo_completo_conserva_todas_las_hojas_y_columnas(self) -> None:
        hojas, err = pc.leer_archivo_completo()
        self.assertIsNone(err)
        self.assertIn(pc.HOJA_DATOS, hojas)
        self.assertIn("parametros", hojas)
        datos = hojas[pc.HOJA_DATOS]
        self.assertIn("EVAI", datos.columns)
        self.assertGreaterEqual(len(datos), len(self.df))

    def test_columnas_que_usa_el_pronostico(self) -> None:
        hojas, _ = pc.leer_archivo_completo()
        usadas = [c for c in hojas[pc.HOJA_DATOS].columns if pc.es_columna_pronostico(c)]
        self.assertIn("demada mes 1", usadas)
        self.assertIn("demanda mes 12", usadas)
        self.assertIn("proveedor", usadas)
        self.assertNotIn("ventas totales", usadas)

    def test_toda_clase_del_excel_tiene_fill_rate(self) -> None:
        calc = pc.calcular_pronostico(self.df)
        sin_fill = calc[calc[pc.COL_FILL_RATE].isna()]
        self.assertTrue(sin_fill.empty, f"Clases sin fill rate: {sin_fill['clase'].unique().tolist()}")

    def test_recalculo_cuadra_con_excel(self) -> None:
        calc = pc.calcular_pronostico(self.df)
        distintos = calc[calc[pc.COL_CUADRA_EXCEL] != "Sí"]
        self.assertTrue(distintos.empty, f"SKUs que no cuadran: {distintos['codigo'].tolist()[:10]}")

    def test_pronostico_lri_en_todos_los_certificados(self) -> None:
        calc = pc.calcular_pronostico(self.df)
        cert = calc[pc.COL_CERTIFICACION] == pc.CERTIFICADO
        self.assertTrue(np.isfinite(calc.loc[cert, pc.COL_PRONOSTICO_LRI]).all())
        self.assertTrue(calc.loc[~cert, pc.COL_PRONOSTICO_LRI].isna().all())
        self.assertTrue((calc.loc[cert, pc.COL_PRONOSTICO_LRI] >= calc.loc[cert, "pronostico calc"] - 1e-9).all())

    def test_todo_sku_queda_certificado_o_no(self) -> None:
        calc = pc.calcular_pronostico(self.df)
        self.assertTrue(calc[pc.COL_CERTIFICACION].isin([pc.CERTIFICADO, pc.NO_CERTIFICADO, pc.SIN_DEMANDA]).all())
        fuera = calc["cv"] > pc.CV_MAX_CERTIFICADO
        self.assertTrue((calc.loc[fuera, pc.COL_CERTIFICACION] == pc.NO_CERTIFICADO).all())


class TestAnalisisApoyo(unittest.TestCase):
    def test_metodos_en_serie_constante(self) -> None:
        for r in pc.comparar_metodos([100.0] * 12):
            self.assertAlmostEqual(r.pronostico, 100.0)
            self.assertAlmostEqual(r.mad, 0.0)

    def test_regresion_sigue_tendencia(self) -> None:
        serie = [10.0 * (i + 1) for i in range(12)]
        reg = next(r for r in pc.comparar_metodos(serie) if r.metodo == "Regresión lineal")
        self.assertAlmostEqual(reg.pronostico, 130.0)

    def test_indices_estacionales_promedian_uno(self) -> None:
        df = pd.DataFrame({"categoria": ["X", "X"], "demanda mes 1": [10, 20], "demanda mes 2": [30, 40]})
        idx = pc.indices_estacionales(df, "categoria")
        self.assertAlmostEqual(float(idx.loc["X"].mean()), 1.0)

    def test_montecarlo_no_negativo_y_cobertura(self) -> None:
        sim = pc.simular_montecarlo(100, 20, 50_000, semilla=1)
        self.assertGreaterEqual(sim.min(), 0)
        cobertura = (sim <= pc.pronostico_ajustado(100, 20, 0.8)).mean()
        self.assertAlmostEqual(cobertura, 0.8, delta=0.01)


if __name__ == "__main__":
    unittest.main()
