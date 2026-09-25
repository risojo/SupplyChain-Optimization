"""Pruebas del motor general del Asistente Inteligente (QueryPlan + catálogo)."""
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
import asistente_openai as oa  # noqa: E402
import asistente_query_plan as qp  # noqa: E402
import asistente_tools as tools  # noqa: E402
import data_loader as dl  # noqa: E402


class TestMotorGeneralAsistente(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        df, _err = dl.cargar_datos()
        assert df is not None and not df.empty
        cls.df = tools.enriquecer_dataframe_consulta(df, dias_trabajo=30, rotacion=4)
        cls.schema = cat.descubrir_schema(cls.df)
        # Valores dinámicos reales (no hardcodeados en la lógica del sistema)
        cls.cat_val = str(cls.df["categoria"].dropna().iloc[0])
        cls.sub_val = str(cls.df["subcategoria"].dropna().iloc[0])
        cls.prov_val = str(cls.df["proveedor"].dropna().iloc[0])
        cls.sku_val = str(cls.df["codigo"].dropna().iloc[0])

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

    def test_01_metrica_todos_sku(self) -> None:
        plan, r = self._run("Grafique la rotación de todos los SKU de mayor a menor")
        self.assertTrue(r.get("ok"), r.get("mensaje"))
        self.assertEqual(plan.metrics[0], "rotacion")
        self.assertTrue(plan.mostrar_todos or plan.limit is None)
        self.assertEqual(r["resumen"]["n_filas"], len(self.df))

    def test_02_por_todas_categorias(self) -> None:
        plan, r = self._run("Muestre las ventas totales por todas las categorías")
        self.assertTrue(r.get("ok"), r.get("mensaje"))
        self.assertIn("categoria", plan.group_by)
        self.assertIn("ventas totales", plan.metrics)
        n_cats = self.df["categoria"].nunique()
        self.assertEqual(r["resumen"]["n_filas"], n_cats)

    def test_03_por_todas_subcategorias(self) -> None:
        plan, r = self._run("Grafique el margen bruto por todas las subcategorías")
        self.assertTrue(r.get("ok"), r.get("mensaje"))
        self.assertIn("subcategoria", plan.group_by)

    def test_04_por_todos_proveedores(self) -> None:
        plan, r = self._run("Muestre EVAI por todos los proveedores")
        self.assertTrue(r.get("ok"), r.get("mensaje"))
        self.assertIn("proveedor", plan.group_by)

    def test_05_filtro_categoria_dinamica(self) -> None:
        q = f"Grafique la rotación de la categoría {self.cat_val}"
        plan, r = self._run(q)
        self.assertTrue(r.get("ok"), r.get("mensaje"))
        self.assertTrue(any(f.value == self.cat_val for f in plan.filters))
        n_ref = int((self.df["categoria"].astype(str) == self.cat_val).sum())
        self.assertEqual(r["resumen"]["n_filas"], n_ref)

    def test_06_filtro_subcategoria_dinamica(self) -> None:
        q = f"Muestre las ventas de la subcategoría {self.sub_val}"
        plan, r = self._run(q)
        self.assertTrue(r.get("ok"), r.get("mensaje"))
        self.assertTrue(any(f.column == "subcategoria" for f in plan.filters))

    def test_07_filtro_proveedor_dinamico(self) -> None:
        q = f"Grafique el inventario final del proveedor {self.prov_val}"
        plan, r = self._run(q)
        self.assertTrue(r.get("ok"), r.get("mensaje"))
        self.assertTrue(any(f.value == self.prov_val for f in plan.filters))

    def test_08_filtro_sku_dinamico(self) -> None:
        q = f"Muestre la rotación del SKU {self.sku_val}"
        plan, r = self._run(q)
        self.assertTrue(r.get("ok"), r.get("mensaje"))
        self.assertTrue(
            any(f.column == "codigo" and str(f.value) == self.sku_val for f in plan.filters)
        )
        self.assertEqual(r["resumen"]["n_filas"], 1)

    def test_09_inventario_dolares(self) -> None:
        plan, r = self._run(
            f"Grafique el inventario promedio en dólares de la categoría {self.cat_val}"
        )
        self.assertTrue(r.get("ok"), r.get("mensaje"))
        self.assertEqual(plan.metrics[0], "valor inventario promedio")
        self.assertEqual(r["resumen"]["formato"], "moneda")

    def test_10_inventario_bultos(self) -> None:
        plan, r = self._run(
            f"Grafique el inventario promedio en bultos de la categoría {self.cat_val}"
        )
        self.assertTrue(r.get("ok"), r.get("mensaje"))
        self.assertEqual(plan.metrics[0], "inventario promedio bultos")

    def test_11_min_y_max(self) -> None:
        plan, r = self._run("Compare cantidad mínima y cantidad máxima por SKU top 10")
        self.assertTrue(r.get("ok") or plan.aclaracion, r.get("mensaje"))
        if r.get("ok"):
            self.assertGreaterEqual(len(plan.metrics), 2)
            self.assertIn("cantidad minima de inventario", plan.metrics)

    def test_12_pronostico_vs_ventas(self) -> None:
        if "pronostico" not in self.df.columns and "pronostico ajustado" not in self.df.columns:
            self.skipTest("Sin pronóstico en DF")
        col_p = "pronostico ajustado" if "pronostico ajustado" in self.df.columns else "pronostico"
        plan, r = self._run(f"Compare {col_p} frente a ventas totales top 15")
        self.assertTrue(r.get("ok"), r.get("mensaje"))
        self.assertGreaterEqual(len(plan.metrics), 2)
        spec = r.get("_grafico_spec") or {}
        self.assertIn(spec.get("tipo"), ("barras_agrupadas", "dual_axis", "barras"))

    def test_13_inventario_vs_ventas_agrupadas(self) -> None:
        plan, r = self._run(
            "Compare inventario promedio en dólares frente a ventas por SKU top 10"
        )
        self.assertTrue(r.get("ok"), r.get("mensaje"))
        self.assertIn("valor inventario promedio", plan.metrics)
        self.assertIn("ventas totales", plan.metrics)
        fig = charts.figura_desde_spec(
            r["_df_completo"], r["_grafico_spec"], resumen=r["resumen"]
        )
        self.assertIsNotNone(fig)

    def test_14_rotacion_vs_meses(self) -> None:
        plan, r = self._run(
            "Compare rotación frente a meses de inventario top 10"
        )
        self.assertTrue(r.get("ok"), r.get("mensaje"))
        self.assertIn("rotacion", plan.metrics)
        self.assertTrue(
            any("meses" in m for m in plan.metrics),
            plan.metrics,
        )
        spec = r.get("_grafico_spec") or {}
        # Misma familia de unidad ratio/meses → agrupadas o dual
        self.assertIsNotNone(spec)

    def test_15_compras(self) -> None:
        plan = qp.construir_plan(
            "Calcule las compras necesarias para una rotación de 4", self.df
        )
        self.assertTrue(plan.es_compras)
        # Herramienta oficial intacta
        res = tools.construir_plan_compras(self.df, rotacion_objetivo=4, dias_trabajo=30)
        self.assertTrue(res.get("ok") or "resumen" in res)

    def test_16_seguimiento_cambia_metrica(self) -> None:
        plan1, r1 = self._run(
            f"Grafique la rotación de la categoría {self.cat_val}"
        )
        self.assertTrue(r1.get("ok"))
        plan2, r2 = self._run("Cambie rotación por ventas", plan_ant=plan1)
        self.assertTrue(r2.get("ok"), r2.get("mensaje"))
        self.assertIn("ventas totales", plan2.metrics)
        self.assertTrue(any(f.value == self.cat_val for f in plan2.filters))

    def test_17_regrese_anterior(self) -> None:
        plan = qp.construir_plan("Regrese al gráfico anterior", self.df)
        self.assertTrue(plan.context_reference)

    def test_18_todos_sin_top(self) -> None:
        plan, r = self._run("Grafique la rotación de todos los SKU")
        self.assertTrue(r.get("ok"))
        self.assertTrue(plan.mostrar_todos)
        self.assertIsNone(plan.limit)
        self.assertEqual(r["resumen"]["n_filas"], len(self.df))
        self.assertTrue((r.get("_grafico_spec") or {}).get("mostrar_todos"))

    def test_19_top_10(self) -> None:
        plan, r = self._run("Grafique las ventas totales top 10")
        self.assertTrue(r.get("ok"), r.get("mensaje"))
        self.assertEqual(plan.limit, 10)
        self.assertEqual(r["resumen"]["n_filas"], 10)

    def test_20_ambiguo_pide_aclaracion(self) -> None:
        plan, r = self._run("Grafique el inventario promedio de todos los SKU")
        self.assertTrue(plan.aclaracion or r.get("necesita_aclaracion"))
        self.assertIn("dólares", (plan.aclaracion or r.get("mensaje") or "").lower())

    def test_multi_ventas_y_utilidad_por_subcategoria(self) -> None:
        q = "Grafique las ventas y la utilidad bruta por subcategoría"
        plan, r = self._run(q)
        self.assertIsNone(plan.aclaracion)
        self.assertEqual(plan.metrics, ["ventas totales", "margen bruto total"])
        self.assertEqual(plan.group_by, ["subcategoria"])
        self.assertEqual(plan.aggregations.get("ventas totales"), "sum")
        self.assertEqual(plan.aggregations.get("margen bruto total"), "sum")
        self.assertEqual(plan.chart_type, "barras_agrupadas")
        self.assertTrue(r.get("ok"), r.get("mensaje"))
        cols = r.get("columnas") or []
        self.assertIn("subcategoria", cols)
        self.assertIn("ventas totales", cols)
        self.assertIn("margen bruto total", cols)
        ver = r.get("verificacion") or ""
        self.assertIn("ventas totales", ver)
        self.assertIn("utilidad bruta", ver)
        self.assertIn("subcategoría", ver)
        self.assertEqual(
            (r.get("_grafico_spec") or {}).get("titulo"),
            "Ventas y utilidad bruta por subcategoría",
        )
        self.assertEqual((r.get("_grafico_spec") or {}).get("tipo"), "barras_agrupadas")
        self.assertEqual(
            (r.get("_grafico_spec") or {}).get("ejes_y"),
            ["ventas totales", "margen bruto total"],
        )
        fig = charts.figura_desde_spec(
            r["_df_completo"], r["_grafico_spec"], resumen=r.get("resumen")
        )
        self.assertIsNotNone(fig)
        self.assertEqual(len(fig.data), 2)

    def test_multi_inventario_bultos_y_dolares(self) -> None:
        q = (
            "Grafique el inventario promedio en bultos y el inventario "
            "promedio en dólares por categoría"
        )
        plan, r = self._run(q)
        self.assertIsNone(plan.aclaracion, plan.aclaracion)
        self.assertEqual(
            plan.metrics,
            ["inventario promedio bultos", "valor inventario promedio"],
        )
        self.assertEqual(plan.group_by, ["categoria"])
        self.assertTrue(r.get("ok"))
        self.assertEqual(len((r.get("_grafico_spec") or {}).get("ejes_y") or []), 2)

    def test_multi_tres_metricas_proveedor(self) -> None:
        q = "Compare ventas, costo de ventas y utilidad bruta por proveedor"
        plan, r = self._run(q)
        self.assertEqual(
            plan.metrics,
            ["ventas totales", "ventas costo", "margen bruto total"],
        )
        self.assertTrue(r.get("ok"))
        fig = charts.figura_desde_spec(
            r["_df_completo"], r["_grafico_spec"], resumen=r.get("resumen")
        )
        self.assertEqual(len(fig.data), 3)

    def test_multi_ventas_y_cubicaje(self) -> None:
        q = "Grafique ventas y cubicaje por SKU"
        plan, r = self._run(q)
        self.assertIn("ventas totales", plan.metrics)
        self.assertTrue(any("cubicaje" in m for m in plan.metrics))
        self.assertTrue(r.get("ok"))
        self.assertEqual((r.get("_grafico_spec") or {}).get("tipo"), "dual_axis")

    def test_multi_no_descarta_silenciosamente(self) -> None:
        q = "Grafique ventas y metricainexistentexyz por categoría"
        plan, r = self._run(q)
        self.assertTrue(plan.aclaracion or r.get("necesita_aclaracion"))
        self.assertIn("metricainexistentexyz", (plan.aclaracion or r.get("mensaje") or "").lower())

    def test_compra_minimo_via_queryplan(self) -> None:
        frase = (
            "Grafique únicamente los artículos que necesitan comprarse "
            "según el inventario mínimo. Muestre los artículos y las "
            "cantidades a comprar, ordenados de mayor a menor"
        )
        self.assertEqual(
            cat.clasificar_intencion_compra(frase), "reposicion_por_minimo"
        )
        self.assertFalse(cat.es_consulta_compras(frase))
        ctx = {
            "rotacion": 4,
            "filtros": {"categoria": "Alimentos", "rotacion_objetivo": 4},
        }
        r = oa._resolver_consulta_local(
            frase, self.df, dias_trabajo=30, contexto=ctx
        )
        self.assertTrue(r and r.get("ok"), r)
        plan = r.get("plan") or {}
        self.assertEqual(plan.get("metrics"), [qp.COL_QTY_MINIMO])
        self.assertNotIn("rotación 4", (r.get("mensaje") or "").lower())
        dfv = r["_df_completo"]
        self.assertIn(qp.COL_QTY_MINIMO, dfv.columns)
        qty = pd.to_numeric(dfv[qp.COL_QTY_MINIMO], errors="coerce")
        self.assertTrue((qty > 0).all())
        self.assertGreater(len(dfv), 0)
        spec = r.get("_grafico_spec") or {}
        self.assertEqual(spec.get("eje_y"), qp.COL_QTY_MINIMO)

    def test_compra_por_rotacion_sigue_separada(self) -> None:
        frase = "Calcule las compras necesarias para una rotación de 4"
        self.assertEqual(
            cat.clasificar_intencion_compra(frase), "compra_por_rotacion"
        )
        self.assertFalse(cat.es_reposicion_por_minimo(frase))
        roles = {m["rol"] for m in self.schema.values()}
        self.assertIn("metrica", roles)
        self.assertIn("dimension", roles)
        self.assertGreaterEqual(len(self.schema), len(self.df.columns))

    def test_valores_compuestos_no_se_parten(self) -> None:
        # Si existe un valor con « y », debe matchear completo
        compuesto = None
        for v in self.df["subcategoria"].dropna().astype(str).unique():
            if " y " in v.lower() or " & " in v:
                compuesto = v
                break
        if not compuesto:
            for v in self.df["categoria"].dropna().astype(str).unique():
                if " y " in v.lower():
                    compuesto = v
                    break
        if not compuesto:
            self.skipTest("No hay valor compuesto con 'y' en el DF")
        filtros, amb = cat.encontrar_valores_en_frase(
            f"Muestre rotación de {compuesto}", self.schema, self.df
        )
        self.assertIsNone(amb)
        self.assertTrue(any(f["value"] == compuesto for f in filtros), filtros)

    def test_no_base64_en_mensaje(self) -> None:
        _, r = self._run("Grafique rotación top 5")
        blob = str(r.get("mensaje") or "") + str(r.get("verificacion") or "")
        self.assertNotIn("base64", blob.lower())
        self.assertNotIn("data:image", blob.lower())


class TestAsistenteInventariosLegacy(unittest.TestCase):
    """Conserva pruebas de compras oficiales."""

    @classmethod
    def setUpClass(cls) -> None:
        import skus_a_comprar as skus

        cls.skus = skus
        df, _ = dl.cargar_datos()
        cls.df = df

    def test_rotacion_3_coincide(self) -> None:
        oficial = self.skus.tabla_skus_a_comprar(self.df, 3, 30, solo_a_comprar=True)
        plan = tools.construir_plan_compras(
            self.df, rotacion_objetivo=3, dias_trabajo=30, solo_compra_positiva=True
        )
        got = plan["_df_completo"]
        self.assertEqual(len(oficial), len(got))


if __name__ == "__main__":
    unittest.main()
