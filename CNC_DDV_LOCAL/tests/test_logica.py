from pathlib import Path
import sys
import unittest
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from logica import cartera_al_cierre,generar_casos

class TestCNC(unittest.TestCase):
    def setUp(self):
        self.clientes=pd.DataFrame({'cliente':['1','2','3'], 'fantasia':['A','B','C'],
            'alta':pd.to_datetime(['2025-01-01','2025-01-01','2026-01-01']),
            'anulado':['SI','NO','NO'],
            'fecha_baja':pd.to_datetime(['2025-08-15',None,None]),
            'promotor':['X','X','X'],'licencia_alcohol':['SI','SI','SI']})
    def test_baja_historica(self):
        # El cliente 1 se incluye en julio y deja de figurar al cierre de agosto.
        self.assertEqual(set(cartera_al_cierre(self.clientes,'2025-07').cliente),{'1','2'})
        self.assertEqual(set(cartera_al_cierre(self.clientes,'2025-08').cliente),{'2'})
        self.assertEqual(set(cartera_al_cierre(self.clientes,'2026-03').cliente),{'2','3'})
    def test_ventas_12_meses_y_baja(self):
        ventas=pd.DataFrame([{'mes':'2025-06','cliente':'1','unidad':'CERVEZAS CMQ','neto':100},
                              {'mes':'2026-01','cliente':'2','unidad':'CERVEZAS CMQ','neto':100}])
        cobertura={str(x) for x in pd.period_range('2025-05','2026-06',freq='M')}
        r,meta=generar_casos(self.clientes,ventas,'2026-06',cobertura)
        fila=r[(r.cliente=='2')&(r.negocio=='CZA')].iloc[0]
        self.assertTrue(fila.cnc_u3m)
        self.assertFalse(fila.cnc_u12m)
        self.assertFalse('1' in r.cliente.values)
    def test_sin_12_meses_no_confirma(self):
        ventas=pd.DataFrame([{'mes':'2025-07','cliente':'2','unidad':'CERVEZAS CMQ','neto':20}])
        r,meta=generar_casos(self.clientes,ventas,'2025-07',{'2025-05','2025-06','2025-07'})
        self.assertTrue(meta['u3_completo'])
        self.assertFalse(meta['u12_completo'])
        self.assertEqual(int(r.cnc_u12m.sum()),0)

if __name__=='__main__':unittest.main()

class TestContactos(unittest.TestCase):
    def test_frecuencia_y_censo_pendiente(self):
        from logica import control_contactos_u12m
        casos=pd.DataFrame({'cliente':['1','2','3'],'negocio':['CZA']*3,
            'cnc_u12m':[True,True,False],'oportunidad_censo':['Sí','Sin validar','No']})
        contactos=pd.DataFrame([
            {'cliente':'1','negocio':'CZA','fecha':'2026-10-04','tipo':'Visita promotor','resultado':'Motivo relevado'},
            {'cliente':'1','negocio':'CZA','fecha':'2026-10-20','tipo':'BEES Force','resultado':'Motivo relevado'},
            {'cliente':'1','negocio':'CZA','fecha':'2026-10-22','tipo':'Visita supervisor','resultado':'Cliente contactado'},
            {'cliente':'2','negocio':'CZA','fecha':'2026-10-01','tipo':'Visita promotor','resultado':'Sin contacto'},
        ])
        result=control_contactos_u12m(casos,contactos,'2026-10')
        self.assertEqual(result.contactos_requeridos.tolist(),[2,1,0])
        self.assertEqual(result.contactos_mes.tolist(),[2,0,0])
        self.assertEqual(result.contacto_pendiente.tolist(),[False,True,False])
        self.assertTrue(result.censo_pendiente.iloc[1])
