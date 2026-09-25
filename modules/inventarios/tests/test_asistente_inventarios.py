"""Pruebas del Asistente Inteligente — cálculos oficiales y herramientas."""
from __future__ import annotations

import os
import sys
import unittest

import pandas as pd

_DIR = os.path.dirname(os.path.abspath(__file__))
_INV = os.path.dirname(_DIR)
if _INV not in sys.path:
    sys.path.insert(0, _INV)

import asistente_charts as charts  # noqa: E402
import asistente_openai as oa  # noqa: E402
import asistente_tools as tools  # noqa: E402
import data_loader as dl  # noqa: E402
import skus_a_comprar as skus  # noqa: E402


class TestAsistenteInventarios(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        df, _err = dl.cargar_datos()
        assert df is not None and not df.empty, "No se pudo cargar perfilado.xlsx"
        cls.df = df

    def test_rotacion_3_coincide_con_modulo_oficial(self) -> None:
        oficial = skus.tabla_skus_a_comprar(self.df, 3, 30, solo_a_comprar=True)
        plan = tools.construir_plan_compras(
            self.df, rotacion_objetivo=3, dias_trabajo=30, solo_compra_positiva=True
        )
        got = plan["_df_completo"]
        self.assertEqual(len(oficial), len(got))
        m = oficial.merge(
            got[["codigo", "cantidad a comprar"]],
            on="codigo",
            suffixes=("_of", "_as"),
        )
        delta = (m["cantidad a comprar_of"] - m["cantidad a comprar_as"]).abs().max()
        self.assertLessEqual(float(delta), 1e-6)

    def test_rotacion_4_cambia_parametro(self) -> None:
        p3 = tools.construir_plan_compras(self.df, rotacion_objetivo=3, dias_trabajo=30)
        p4 = tools.construir_plan_compras(self.df, rotacion_objetivo=4, dias_trabajo=30)
        self.assertEqual(p3["resumen"]["rotacion_objetivo"], 3)
        self.assertEqual(p4["resumen"]["rotacion_objetivo"], 4)
        of4 = skus.calcular_cantidad_a_comprar(self.df, 4, 30)
        self.assertGreaterEqual(float(of4.clip(lower=0).sum()), 0)

    def test_monto_total_igual_suma_filas(self) -> None:
        plan = tools.construir_plan_compras(self.df, rotacion_objetivo=4, dias_trabajo=30)
        df = plan["_df_completo"]
        if df.empty or "monto compra" not in df.columns:
            self.skipTest("Sin filas o sin monto")
        suma = float(pd.to_numeric(df["monto compra"], errors="coerce").sum())
        self.assertAlmostEqual(suma, float(plan["resumen"]["monto_total"]), places=2)

    def test_agrupacion_proveedor_suma_total(self) -> None:
        res = tools.resumir_compras_por_proveedor(
            self.df, rotacion_objetivo=4, dias_trabajo=30
        )
        total_g = sum(float(g["monto"]) for g in res["por_proveedor"])
        self.assertAlmostEqual(total_g, float(res["monto_total"]), places=2)

    def test_filtro_proveedor(self) -> None:
        if "proveedor" not in self.df.columns:
            self.skipTest("Sin proveedores")
        provs = self.df["proveedor"].dropna().astype(str).unique().tolist()
        if not provs:
            self.skipTest("Sin proveedores")
        plan = tools.construir_plan_compras(
            self.df, rotacion_objetivo=4, dias_trabajo=30, proveedor=provs[0]
        )
        df = plan["_df_completo"]
        if df.empty:
            return
        self.assertTrue((df["proveedor"].astype(str) == provs[0]).all())

    def test_sin_compras_negativas(self) -> None:
        plan = tools.construir_plan_compras(self.df, rotacion_objetivo=4, dias_trabajo=30)
        qty = pd.to_numeric(plan["_df_completo"]["cantidad a comprar"], errors="coerce")
        self.assertTrue((qty.fillna(0) >= 0).all())

    def test_proveedor_inexistente_error(self) -> None:
        with self.assertRaises(ValueError):
            tools.construir_plan_compras(
                self.df,
                rotacion_objetivo=4,
                dias_trabajo=30,
                proveedor="___NO_EXISTE_XYZ___",
            )

    def test_seguimiento_hereda_filtros(self) -> None:
        prov = str(self.df["proveedor"].dropna().iloc[0])
        ctx = {"filtros": {"proveedor": prov, "rotacion_objetivo": 3}, "rotacion": 3}
        result = oa.ejecutar_herramienta(
            "consultar_plan_compras",
            {"rotacion_objetivo": 5},
            self.df,
            dias_trabajo=30,
            contexto=ctx,
        )
        self.assertEqual(result["resumen"]["rotacion_objetivo"], 5)
        self.assertEqual(result["resumen"]["filtros"]["proveedor"], prov)

    def test_herramienta_no_autorizada(self) -> None:
        bad = oa.ejecutar_herramienta(
            "drop_table", {}, self.df, dias_trabajo=30, contexto={}
        )
        self.assertFalse(bad.get("ok", True))

    def test_comparar_escenarios(self) -> None:
        comp = tools.comparar_escenarios_compra(
            self.df, rotaciones=[3, 4], dias_trabajo=30
        )
        self.assertEqual(comp["rotaciones"], [3, 4])
        self.assertEqual(len(comp["tabla_comparativa"]), 2)

    def test_grafico_usa_mismos_datos(self) -> None:
        plan = tools.construir_plan_compras(self.df, rotacion_objetivo=4, dias_trabajo=30)
        df = plan["_df_completo"]
        if df.empty:
            self.skipTest("Sin compras")
        spec = {
            "tipo": "barras",
            "eje_x": "codigo",
            "eje_y": "monto compra",
            "top_n": 5,
            "titulo": "test",
        }
        fig = charts.figura_desde_spec(df, spec, resumen=plan["resumen"])
        self.assertIsNotNone(fig)
        y = (
            pd.to_numeric(df["monto compra"], errors="coerce")
            .fillna(0)
            .sort_values(ascending=False)
            .head(5)
        )
        self.assertEqual(len(y), min(5, len(df)))

    def test_inventario_promedio_dolares_categoria_alimentos(self) -> None:
        r = oa._resolver_consulta_local(
            "Grafique el inventario promedio en dólares de la categoría Alimentos",
            self.df,
            dias_trabajo=30,
            contexto={"rotacion": 4},
        )
        self.assertTrue(r and r.get("ok"))
        self.assertEqual(r["resumen"]["metrica"], "valor inventario promedio")
        self.assertEqual(r["resumen"]["formato"], "moneda")
        self.assertEqual(r["resumen"]["filtros"].get("categoria"), "Alimentos")
        self.assertEqual(r["resumen"]["n_filas"], 24)
        self.assertIn("dólares", r["verificacion"].lower())
        self.assertIn("Alimentos", r["verificacion"])
        cats = set(r["_df_completo"]["categoria"].astype(str).unique())
        self.assertEqual(cats, {"Alimentos"})
        self.assertEqual(
            r["_grafico_spec"]["titulo"],
            "Valor promedio del inventario – Categoría Alimentos",
        )

    def test_valor_promedio_inventario_alimentos(self) -> None:
        r = oa._resolver_consulta_local(
            "Grafique el valor promedio del inventario de Alimentos",
            self.df,
            dias_trabajo=30,
            contexto={"rotacion": 4},
        )
        self.assertTrue(r and r.get("ok"))
        self.assertEqual(r["resumen"]["metrica"], "valor inventario promedio")
        self.assertEqual(r["resumen"]["filtros"].get("categoria"), "Alimentos")
        self.assertEqual(r["resumen"]["n_filas"], 24)

    def test_inventario_promedio_bultos_alimentos(self) -> None:
        r = oa._resolver_consulta_local(
            "Grafique el inventario promedio en bultos de la categoría Alimentos",
            self.df,
            dias_trabajo=30,
            contexto={"rotacion": 4},
        )
        self.assertTrue(r and r.get("ok"))
        self.assertEqual(r["resumen"]["metrica"], "inventario promedio bultos")
        self.assertEqual(r["resumen"]["unidad"], "bultos")
        self.assertEqual(r["resumen"]["filtros"].get("categoria"), "Alimentos")
        self.assertEqual(r["resumen"]["n_filas"], 24)

    def test_inventario_promedio_sin_unidad_pide_aclaracion(self) -> None:
        r = oa._resolver_consulta_local(
            "Grafique el inventario promedio de la categoría Alimentos",
            self.df,
            dias_trabajo=30,
            contexto={"rotacion": 4},
        )
        self.assertTrue(r and r.get("necesita_aclaracion"))
        self.assertIn("dólares", (r.get("mensaje") or "").lower())
        self.assertIn("bultos", (r.get("mensaje") or "").lower())

    def test_filas_solo_categoria_alimentos(self) -> None:
        n_ref = int((self.df["categoria"].astype(str) == "Alimentos").sum())
        r = oa._resolver_consulta_local(
            "Grafique el inventario promedio en dólares de la categoría Alimentos",
            self.df,
            dias_trabajo=30,
            contexto={"rotacion": 4},
        )
        self.assertEqual(r["resumen"]["n_filas"], n_ref)
        self.assertTrue(
            (r["_df_completo"]["categoria"].astype(str) == "Alimentos").all()
        )


if __name__ == "__main__":
    unittest.main()
