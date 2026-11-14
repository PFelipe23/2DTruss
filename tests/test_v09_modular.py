"""Regressões da UI modular consolidada como 2DTruss v0.1.

O navegador é testado em tests/browser_ui_v09_inmemory.py (Playwright opcional).
"""
from __future__ import annotations
import json
import sys
import unittest
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from poe_truss.catalog import load_catalog
from poe_truss.model import make_model
from poe_truss.loads import build_case_loads
from poe_truss.server import run_server

class ModularHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=run_server(ROOT,False)
        cls.thread=Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(2)

    def test_esm_sources_are_served_and_isolated(self):
        for module in ('nodal','diagram','results'):
            with self.subTest(module=module):
                with urlopen(self.url+'/modules/'+module+'.js') as response:
                    payload=response.read().decode('utf-8')
                    self.assertIn('application/javascript',response.headers['Content-Type'])
                    self.assertIn('export ',payload)
                    self.assertEqual(response.headers['X-Frame-Options'],'DENY')

    def test_unlisted_modules_not_served(self):
        for name in ('missing.js','private.js','../catalogo_perfis.csv'):
            with self.subTest(name=name):
                with self.assertRaises(HTTPError) as err:
                    urlopen(self.url+'/modules/'+name)
                self.assertEqual(err.exception.code,404)

    def test_version_is_pinned_to_v09(self):
        with urlopen(self.url) as response:html=response.read().decode('utf-8')
        self.assertIn('v0.1',html)
        self.assertNotIn('v0.1.0',html)
        self.assertIn('type="module" src="/app.js"',html)
        self.assertIn('id="nodal-table"',html)
        self.assertIn('id="member-group-filter"',html)

class NodalContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project=json.loads((ROOT/'examples/cobertura_duas_aguas.json').read_text(encoding='utf-8'))
        cls.model=make_model(cls.project,load_catalog(ROOT/'catalogo_perfis.csv'))

    def test_independent_nodal_units_and_signed_forces(self):
        case={'id':'TESTE_UI','kind':'nodal','loads':[
            {'node':'T00','fx':50,'fy':-125,'force_unit':'kgf'},
            {'node':'T02','fx':0.5,'fy':1.5,'force_unit':'kN'},
        ]}
        loads,audit=build_case_loads(self.model,case)
        self.assertEqual(loads['T00'],(500,-1250))
        self.assertEqual(loads['T02'],(500,1500))
        self.assertAlmostEqual(audit['sum_fx_n'],1000)
        self.assertAlmostEqual(audit['sum_fy_n'],250)
        self.assertEqual(audit['n_entries'],2)

    def test_nodal_nonexistent_node_rejected(self):
        with self.assertRaisesRegex(ValueError,'nó inexistente'):
            build_case_loads(self.model,{'id':'INV','kind':'nodal','loads':[
                {'node':'INVÁLIDO','fx':5,'fy':0,'force_unit':'kgf'}]})

if __name__=='__main__': unittest.main()
