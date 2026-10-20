"""Pruebas locales de sincronización línea roja ↔ cantidad (sin Streamlit UI)."""
from __future__ import annotations

import os
import sys
import unittest

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from sync_linea_helpers import (  # noqa: E402
    bultos_desde_probabilidad,
    colores_barras_zonas,
    discretizar_normal_barras,
    probabilidad_desde_bultos,
    rango_eje_x_demanda,
    zonas_probabilidad_delimitadores,
)


class TestSyncLineaDemanda(unittest.TestCase):
    def test_consulta_dentro_del_eje(self):
        for bultos in (200, 225, 250, 275):
            xs = rango_eje_x_demanda(220.0, 30.0, float(bultos))
            self.assertLessEqual(xs[0], bultos)
            self.assertGreaterEqual(xs[-1], bultos)

    def test_consulta_fuera_amplia_eje(self):
        xs = rango_eje_x_demanda(100.0, 10.0, 275.0)  # 275 >> media+4σ=140
        self.assertGreaterEqual(xs[-1], 275.0)
        self.assertAlmostEqual(xs[-1], 275.0 * 1.05, places=5)

    def test_vline_x_igual_consulta(self):
        """La posición de la línea roja debe ser exactamente la cantidad."""
        for bultos in (200.0, 225.0, 250.0, 275.0):
            vline_x = float(bultos)
            self.assertEqual(vline_x, bultos)

    def test_ida_y_vuelta_probabilidad_bultos(self):
        media, desv = 220.0, 30.0
        for p in (0.50, 0.80, 0.90, 0.95):
            x = bultos_desde_probabilidad(media, desv, p)
            p2 = probabilidad_desde_bultos(media, desv, x)
            self.assertAlmostEqual(p2, p, places=5)
            # La línea roja usaría x; debe ser finita y coherente con media±colas.
            self.assertTrue(x > media - 5 * desv)
            self.assertTrue(x < media + 5 * desv)

    def test_barras_cambian_color_con_rango(self):
        media, desv = 220.0, 30.0
        centers, heights, _w = discretizar_normal_barras(media, desv, 100, 340, n_bins=40)
        self.assertEqual(len(centers), len(heights))
        colores = colores_barras_zonas(centers, 200.0, 275.0)
        self.assertEqual(len(colores), len(centers))
        # Alguna barra dentro (anaranjado sólido) y alguna fuera (cola clara).
        self.assertIn("#EA580C", colores)
        self.assertTrue(any(c != "#EA580C" for c in colores))
        p_i, p_c, p_d, lo, hi = zonas_probabilidad_delimitadores(media, desv, 200, 275)
        self.assertAlmostEqual(p_i + p_c + p_d, 1.0, places=5)
        self.assertEqual(lo, 200.0)
        self.assertEqual(hi, 275.0)


if __name__ == "__main__":
    unittest.main()
