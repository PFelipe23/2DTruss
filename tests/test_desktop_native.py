"""Testes do contrato desktop sem iniciar UI ou servidor HTTP."""
from __future__ import annotations
from copy import deepcopy
import tempfile
import unittest
from pathlib import Path
from desktop.bridge import Session,write_project,load_project

class DesktopContractTests(unittest.TestCase):
    def setUp(self):self.s=Session()

    def test_node_edit_changes_coordinates_and_invalidates_analysis(self):
        previous=self.s.model.node_map()['T08']
        self.s.calculate()
        self.s.set_node('T08',previous.x,previous.y+100)
        self.assertIsNone(self.s.result)
        self.assertAlmostEqual(self.s.model.node_map()['T08'].y,previous.y+100)
        # As cargas de área continuam operacionais após editar um nó.
        case=self.s.forces_for_case('G2')
        self.assertTrue(any(abs(v[1])>0 for v in case.values()))
        result=self.s.calculate()
        self.assertIn('G2',result['analyses'])

    def test_edit_node_rejects_invalid_heights_and_unknown_ids(self):
        before=deepcopy(self.s.project)
        with self.assertRaises(ValueError):self.s.set_node('T08',8000,-50)
        self.assertEqual(self.s.project,before)
        with self.assertRaises(ValueError):self.s.set_node('N_999',0,100)
        self.assertEqual(self.s.project,before)

    def test_edit_node_x_order(self):
        with self.assertRaises(ValueError):self.s.set_node('T08',100,3000)

    def test_supports_per_node_without_new_solver(self):
        self.s.set_support('T08',False,True)
        self.assertIn('T08',self.s.model.supports)
        self.assertEqual(self.s.model.supports['T08'],(False,True))
        self.assertEqual(self.s.calculate()['schema'],'poe-truss-result/v1')
        self.s.set_support('T08',False,False)
        self.assertNotIn('T08',self.s.model.supports)

    def test_nodal_load_round_trip_preserves_units_and_sign(self):
        self.s.add_nodal_case('P_NOD')
        self.s.set_nodal_load('P_NOD','T08',50,-300,'kgf')
        self.assertEqual(self.s.forces_for_case('P_NOD')['T08'],(500.,-3000.))
        self.s.set_nodal_load('P_NOD','T08',5,-30,'kN',index=0)
        self.assertEqual(self.s.forces_for_case('P_NOD')['T08'],(5000.,-30000.))
        with tempfile.TemporaryDirectory() as path:
            file=Path(path)/'modelo.json'
            write_project(file,self.s.project)
            restored=Session(load_project(file))
            self.assertEqual(restored.project['load_cases'][-1]['loads'][0]['force_unit'],'kN')
            self.assertEqual(restored.forces_for_case('P_NOD')['T08'],(5000.,-30000.))
            self.assertIn('P_NOD',restored.calculate()['analyses'])

    def test_explicit_benchmark_nodal_edit_and_support(self):
        from desktop.bridge import ROOT,load_project
        explicit=Session(project=load_project(ROOT/'examples'/'FTool_A02_trelica_triangular.json'))
        nid=explicit.model.nodes[2].id
        old=explicit.model.node_map()[nid]
        explicit.set_node(nid,old.x,old.y+20)
        self.assertAlmostEqual(explicit.model.node_map()[nid].y,old.y+20)
        explicit.set_support(nid,False,True)
        self.assertEqual(explicit.model.supports[nid],(False,True))

    def test_schema_stays_identical_to_v09(self):
        self.assertEqual(self.s.project['schema'],'poe-truss-python/v1')
        self.assertEqual(self.s.calculate()['schema'],'poe-truss-result/v1')

    def test_invalid_input_cannot_corrupt_state(self):
        original=deepcopy(self.s.project)
        with self.assertRaises(ValueError):self.s.set_nodal_load('G1','T08',float('nan'),0)
        self.assertEqual(self.s.project,original)
        with self.assertRaises(ValueError):self.s.add_nodal_case('G1')
        self.assertEqual(self.s.project,original)

if __name__=='__main__':unittest.main()
