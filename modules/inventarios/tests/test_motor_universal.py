"""10 pruebas obligatorias del motor universal (QueryPlan + catálogo + charts)."""
from __future__ import annotations

import os
import sys
import unittest

import pandas as pd

_DIR = os.path.dirname(os.path.abspath(__file__))
_INV = os.path.dirname(_DIR)
if _INV not in sys.path:
    sys.path.insert(0, _INV)

import asistente_catalogo as cat  # noqa: E402
import asistente_charts as charts  # noqa: E402
import asistente_derivadas as der  # noqa: E402
import asistente_openai as oa  # noqa: E402
import asistente_query_plan as qp  # noqa: E402
import asistente_tools as tools  # noqa: E402
import data_loader as dl  # noqa: E402


class TestMotorUniversalObligatorias(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        df, err = dl.cargar_datos()
        assert df is not None and not df.empty, err
        cls.df = tools.enriquecer_dataframe_consulta(df, dias_trabajo=30, rotacion=4)
        cls.schema = der.enriquecer_catalogo_derivadas(cat.descubrir_schema(cls.df))
        cls.cat_val = str(cls.df["categoria"].dropna().iloc[0])
        cls.prov_val = str(cls.df["proveedor"].dropna().iloc[0])
        # Preferir «Alimentos» si existe
        cats = {str(c) for c in cls.df["categoria"].dropna().unique()}
        cls.alimentos = next((c for c in cats if cat._norm(c) == "alimentos"), cls.cat_val)

    def _run(self, pregunta: str, plan_ant: qp.QueryPlan | None = None):
        plan = qp.construir_plan(pregunta, self.df, plan_anterior=plan_ant)
        if plan.aclaracion:
            return plan, {
                "ok": False,
                "necesita_aclaracion": True,
                "mensaje": plan.aclaracion,
                "plan": plan.to_dict(),
            }
        if plan.es_compras:
            return plan, {"ok": False, "tipo": "compras"}
        return plan, qp.ejecutar_plan(self.df, plan, dias_trabajo=30, rotacion=4)

    def _fig(self, r: dict):
        return charts.figura_desde_spec(
            r["_df_completo"], r["_grafico_spec"], resumen=r.get("resumen")
        )

    def test_01_ventas_y_utilidad_por_subcategoria(self) -> None:
        q = "Grafique las ventas y la utilidad bruta por subcategoría"
        plan, r = self._run(q)
        self.assertIsNone(plan.aclaracion, plan.aclaracion)
        self.assertEqual(plan.metrics, ["ventas totales", "margen bruto total"])
        self.assertEqual(plan.group_by, ["subcategoria"])
        self.assertTrue(r.get("ok"), r.get("mensaje"))
        cols = r.get("columnas") or []
        self.assertIn("ventas totales", cols)
        self.assertIn("margen bruto total", cols)
        self.assertEqual(len(plan.metrics), 2)
        fig = self._fig(r)
        self.assertIsNotNone(fig)
        self.assertEqual(len(fig.data), 2)
        self.assertIn("Métricas:", r.get("verificacion") or "")

    def test_01b_margen_de_utilidad_es_porcentual(self) -> None:
        q = "Grafique el margen de utilidad por subcategoría"
        plan, r = self._run(q)
        self.assertIsNone(plan.aclaracion, plan.aclaracion)
        self.assertEqual(plan.metrics, ["margen utilidad ventas"])
        self.assertNotEqual(plan.metrics, ["margen bruto total"])
        self.assertEqual(plan.aggregations.get("margen utilidad ventas"), "mean")
        self.assertTrue(r.get("ok"), r.get("mensaje"))
        self.assertIn("margen utilidad ventas", r.get("columnas") or [])
        self.assertIn("%", (r.get("verificacion") or ""))

    def test_01c_utilidad_bruta_es_monetaria(self) -> None:
        q = "Grafique la utilidad bruta por categoría"
        plan, r = self._run(q)
        self.assertIsNone(plan.aclaracion, plan.aclaracion)
        self.assertEqual(plan.metrics, ["margen bruto total"])
        self.assertEqual(plan.aggregations.get("margen bruto total"), "sum")
        self.assertTrue(r.get("ok"), r.get("mensaje"))

    def test_01d_margen_ambiguo_pide_aclaracion(self) -> None:
        plan, r = self._run("Grafique el margen por categoría")
        self.assertTrue(plan.aclaracion or r.get("necesita_aclaracion"))
        msg = (plan.aclaracion or r.get("mensaje") or "").lower()
        self.assertTrue("%" in msg or "porcent" in msg)
        self.assertTrue("bruta" in msg or "dólar" in msg or "dolar" in msg or "$" in msg)

    def test_02_comprar_segun_minimo_default_metric(self) -> None:
        q = "Grafique los artículos que deben comprarse según el mínimo"
        plan, r = self._run(q)
        self.assertTrue(r.get("ok"), r.get("mensaje"))
        self.assertEqual(plan.metrics, [qp.COL_QTY_MINIMO])
        self.assertTrue(
            any(
                f.column == qp.COL_QTY_MINIMO and f.operator == "gt"
                for f in plan.filters
            )
        )
        cols = r.get("columnas") or []
        self.assertIn(qp.COL_QTY_MINIMO, cols)
        self.assertTrue(
            "codigo" in cols or "descripcion" in cols,
            cols,
        )
        qty = pd.to_numeric(r["_df_completo"][qp.COL_QTY_MINIMO], errors="coerce")
        self.assertTrue((qty > 0).all())
        spec = r.get("_grafico_spec") or {}
        self.assertEqual(spec.get("eje_y"), qp.COL_QTY_MINIMO)
        self.assertNotIn("rotacion", (r.get("verificacion") or "").lower())

    def test_03_filtro_compra_dos_metricas(self) -> None:
        q = (
            "Para los artículos que deben comprarse según el mínimo, "
            "grafique ventas en unidades e inventario promedio en dólares"
        )
        plan, r = self._run(q)
        self.assertIsNone(plan.aclaracion, plan.aclaracion)
        self.assertTrue(
            any(f.column == qp.COL_QTY_MINIMO and f.operator == "gt" for f in plan.filters)
        )
        self.assertEqual(
            plan.metrics,
            ["unidades vendidas", "valor inventario promedio"],
        )
        self.assertNotIn(qp.COL_QTY_MINIMO, plan.metrics)
        self.assertTrue(r.get("ok"), r.get("mensaje"))
        cols = r.get("columnas") or []
        self.assertIn("unidades vendidas", cols)
        self.assertIn("valor inventario promedio", cols)
        fig = self._fig(r)
        self.assertEqual(len(fig.data), 2)
        self.assertEqual((r.get("_grafico_spec") or {}).get("tipo"), "dual_axis")

    def test_04_no_comprar_utilidad_y_ventas(self) -> None:
        q = (
            "Para los artículos que no deben comprarse según el mínimo, "
            "grafique utilidad bruta y ventas por SKU"
        )
        plan, r = self._run(q)
        self.assertIsNone(plan.aclaracion, plan.aclaracion)
        self.assertTrue(
            any(
                f.column == qp.COL_QTY_MINIMO and f.operator == "lte"
                for f in plan.filters
            )
        )
        self.assertEqual(plan.metrics, ["margen bruto total", "ventas totales"])
        self.assertIn("codigo", plan.group_by)
        self.assertTrue(r.get("ok"), r.get("mensaje"))
        fig = self._fig(r)
        self.assertEqual(len(fig.data), 2)

    def test_05_rotacion_e_inventario_categoria(self) -> None:
        q = (
            f"Compare rotación e inventario promedio en dólares por SKU "
            f"de la categoría {self.alimentos}"
        )
        plan, r = self._run(q)
        self.assertIsNone(plan.aclaracion, plan.aclaracion)
        self.assertTrue(
            any(f.column == "categoria" and str(f.value) == self.alimentos for f in plan.filters)
        )
        self.assertEqual(
            plan.metrics,
            ["rotacion", "valor inventario promedio"],
        )
        self.assertIn("codigo", plan.group_by)
        self.assertTrue(r.get("ok"), r.get("mensaje"))
        fig = self._fig(r)
        self.assertEqual(len(fig.data), 2)

    def test_06_tres_metricas_proveedor(self) -> None:
        q = "Grafique ventas, utilidad bruta e inventario en dólares por proveedor"
        plan, r = self._run(q)
        self.assertIsNone(plan.aclaracion, plan.aclaracion)
        self.assertEqual(len(plan.metrics), 3, plan.metrics)
        self.assertEqual(
            plan.metrics,
            ["ventas totales", "margen bruto total", "valor inventario promedio"],
        )
        self.assertIn("proveedor", plan.group_by)
        self.assertTrue(r.get("ok"), r.get("mensaje"))
        fig = self._fig(r)
        self.assertEqual(len(fig.data), 3)

    def test_07_inventario_bultos_y_dolares(self) -> None:
        q = (
            "Grafique inventario promedio en bultos e inventario promedio "
            "en dólares por categoría"
        )
        plan, r = self._run(q)
        self.assertIsNone(plan.aclaracion, plan.aclaracion)
        self.assertEqual(
            plan.metrics,
            ["inventario promedio bultos", "valor inventario promedio"],
        )
        self.assertEqual(plan.chart_type, "dual_axis")
        self.assertTrue(r.get("ok"))
        fig = self._fig(r)
        self.assertEqual(len(fig.data), 2)
        unidades = (r.get("resumen") or {}).get("unidades") or {}
        self.assertIn("bultos", str(unidades.get("inventario promedio bultos") or "").lower())
        self.assertIn(
            "dólar",
            str(unidades.get("valor inventario promedio") or "").lower(),
        )

    def test_08_proveedor_rotacion_lt2_orden(self) -> None:
        q = (
            f"Muestre los SKU del proveedor {self.prov_val} "
            f"con rotación menor que 2 y ordénelos de menor a mayor"
        )
        plan, r = self._run(q)
        self.assertTrue(
            any(f.column == "proveedor" and str(f.value) == self.prov_val for f in plan.filters),
            plan.filters,
        )
        self.assertTrue(
            any(f.column == "rotacion" and f.operator == "lt" and float(f.value) == 2 for f in plan.filters)
        )
        self.assertEqual(plan.sort_order, "asc")
        self.assertIn("rotacion", plan.metrics)
        if r.get("ok") and r.get("resumen", {}).get("n_filas", 0) > 0:
            rot = pd.to_numeric(r["_df_completo"]["rotacion"], errors="coerce")
            self.assertTrue((rot < 2).all())
            self.assertTrue(rot.is_monotonic_increasing)

    def test_09_presupuesto_anual_ventas(self) -> None:
        q = (
            "Grafique el presupuesto anual de ventas por categoría "
            "utilizando el pronóstico ajustado mensual"
        )
        plan, r = self._run(q)
        self.assertIsNone(plan.aclaracion, plan.aclaracion)
        self.assertIn("presupuesto anual ventas", plan.metrics)
        self.assertIn("categoria", plan.group_by)
        self.assertTrue(r.get("ok"), r.get("mensaje"))
        formulas = plan.formulas_aplicadas or (r.get("plan") or {}).get("formulas_aplicadas") or []
        self.assertTrue(formulas, "Debe registrar la fórmula anual")
        self.assertTrue(
            any("precio unitario" in str(f.get("formula", "")).lower() for f in formulas)
            or any("12" in str(f.get("formula", "")) for f in formulas)
        )
        self.assertIn("Fórmula", r.get("mensaje") or "")

    def test_10_seguimiento_cambia_agrupacion(self) -> None:
        q1 = "Grafique las ventas y la utilidad bruta por subcategoría"
        plan1, r1 = self._run(q1)
        self.assertTrue(r1.get("ok"), r1.get("mensaje"))
        self.assertEqual(plan1.group_by, ["subcategoria"])
        q2 = "Ahora muéstrelo por proveedor"
        plan2, r2 = self._run(q2, plan_ant=plan1)
        self.assertEqual(plan2.metrics, plan1.metrics)
        self.assertEqual(plan2.filters, plan1.filters)
        self.assertEqual(plan2.group_by, ["proveedor"])
        self.assertTrue(r2.get("ok"), r2.get("mensaje"))
        self.assertIn("proveedor", r2.get("columnas") or [])

    def test_local_resolver_no_hereda_rotacion_en_minimo(self) -> None:
        frase = "Grafique los artículos que deben comprarse según el mínimo"
        ctx = {
            "rotacion": 4,
            "filtros": {"categoria": "Alimentos", "rotacion_objetivo": 4},
            "ultimo_plan": None,
        }
        r = oa._resolver_consulta_local(frase, self.df, dias_trabajo=30, contexto=ctx)
        self.assertTrue(r and r.get("ok"), r)
        plan = r.get("plan") or {}
        self.assertEqual(plan.get("metrics"), [qp.COL_QTY_MINIMO])
        self.assertNotIn("rotación 4", (r.get("mensaje") or "").lower())
        self.assertNotIn("Rotación objetivo", r.get("mensaje") or "")


if __name__ == "__main__":
    unittest.main()
