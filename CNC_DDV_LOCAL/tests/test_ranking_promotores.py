from pathlib import Path
import sys
import unittest
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from logica import resumen_cnc_por_promotor

class TestRankingPromotores(unittest.TestCase):
    def setUp(self):
        # El mismo cliente puede tener dos negocios sin compra: un cliente, dos casos.
        base = [
            ('1', 'A', 'CZA', '2026-06', 'NO', None),
            ('1', 'A', 'NABS', '2025-07', 'NO', None),
            ('2', 'A', 'CZA', '2026-10', 'NO', None),
            ('3', 'B', 'CZA', None, 'NO', None),
            ('6', 'B', 'NABS', '2026-06', 'NO', None),
            ('4', '',  'CZA', None, 'NO', None),
            ('5', 'A', 'CZA', None, 'SI', '2026-09-20'),
        ]
        self.casos = pd.DataFrame(base, columns=['cliente','promotor','negocio',
            'ultima_compra','anulado','fecha_baja'])
        self.casos['alta'] = pd.Timestamp('2025-01-01')
        self.casos['fecha_baja'] = pd.to_datetime(
            self.casos['fecha_baja'], errors='coerce')
        self.cobertura = {str(x) for x in pd.period_range(
            '2025-11', '2026-10', freq='M')}

    def test_tres_meses_unicos_y_casos(self):
        tabla, meta = resumen_cnc_por_promotor(
            self.casos, '2026-10', self.cobertura, 3)
        self.assertTrue(meta['verificable'])
        por = tabla.set_index('promotor')
        self.assertEqual(int(por.loc['A','clientes_cnc']), 1)
        self.assertEqual(int(por.loc['A','casos_cnc']), 2)
        self.assertEqual(int(por.loc['A','clientes_activos']), 2)
        self.assertEqual(int(por.loc['B','clientes_cnc']), 2)
        self.assertNotIn('', por.index)
        self.assertEqual(int(tabla['clientes_cnc'].sum()), 3)
        self.assertEqual(int(tabla['casos_cnc'].sum()), 4)

    def test_seis_y_doce_meses(self):
        tab6, meta6 = resumen_cnc_por_promotor(
            self.casos, '2026-10', self.cobertura, 6)
        tab12, meta12 = resumen_cnc_por_promotor(
            self.casos, '2026-10', self.cobertura, 12)
        self.assertEqual((meta6['inicio'],meta12['inicio']), ('2026-05','2025-11'))
        self.assertEqual(int(tab6['clientes_cnc'].sum()), 2)
        self.assertEqual(int(tab6['casos_cnc'].sum()), 2)
        self.assertEqual(int(tab12['clientes_cnc'].sum()), 2)
        self.assertEqual(int(tab12['casos_cnc'].sum()), 2)

    def test_cobertura_incompleta_no_muestra_ceros(self):
        tabla, meta = resumen_cnc_por_promotor(
            self.casos, '2025-07', {'2025-05','2025-06','2025-07'}, 6)
        self.assertFalse(meta['verificable'])
        self.assertEqual(meta['faltantes'], ['2025-02','2025-03','2025-04'])
        self.assertTrue(tabla.empty)

    def test_parametro_invalido(self):
        with self.assertRaises(ValueError):
            resumen_cnc_por_promotor(self.casos, '2026-10', self.cobertura, 9)

if __name__ == '__main__':
    unittest.main()
