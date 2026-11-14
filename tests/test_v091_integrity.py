"""Testes de integridade da revisão de interface e da prévia não resistente."""
import copy
import csv
import io
import json
import re
import sys
import unittest
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from poe_truss.catalog import load_catalog
from poe_truss.engine import run_project
from poe_truss.export import as_csv
from poe_truss.server import run_server


class CSVSanitizationTests(unittest.TestCase):
    def test_formula_injection_is_neutralized(self):
        source = [
            {'name': '=HYPERLINK("https://evil.invalid")', 'obs': '  +cmd', 'val': -10.5},
            {'name': '@SUM(A1:A4)', 'obs': '-cmd | test', 'val': 0.0},
        ]
        raw = as_csv(source)
        loaded = list(csv.DictReader(io.StringIO(raw.lstrip('\ufeff')), delimiter=';'))
        self.assertTrue(loaded[0]['name'].startswith("'="))
        self.assertTrue(loaded[0]['obs'].startswith("'"))
        self.assertTrue(loaded[1]['name'].startswith("'@"))
        self.assertTrue(loaded[1]['obs'].startswith("'-"))
        self.assertEqual(loaded[0]['val'], '-10.5')

    def test_plain_text_and_negative_numeric_survive(self):
        raw=as_csv([{'name':'Perfil U','val':'-125.25'}])
        self.assertIn('Perfil U;-125.25',raw)


class PreviewHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = run_server(ROOT, False)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f'http://127.0.0.1:{cls.server.server_port}'
        with urlopen(Request(cls.origin+'/bootstrap.js',headers={'Referer':cls.origin+'/'})) as resp:
            cls.token=re.search(r'POE_TOKEN="([^"]+)"',resp.read().decode()).group(1)
        with urlopen(cls.origin+'/api/default') as resp:
            cls.project=json.load(resp)
        cls.catalog=load_catalog(ROOT/'catalogo_perfis.csv')
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(2)

    def post(self,path,body,token=None):
        headers={'X-POE-Token':token or self.token,'Content-Type':'application/json'}
        with urlopen(Request(self.origin+path,data=json.dumps(body).encode(),headers=headers,method='POST'),timeout=15) as response:
            return json.load(response)

    def test_preview_has_model_but_no_analysis(self):
        data=self.post('/api/preview',{'project':self.project})
        self.assertTrue(data['preview_only'])
        self.assertNotIn('analyses',data)
        self.assertEqual(len(data['model']['members']),65)
        self.assertIn('geometry_diagnostics',data)

    def test_preview_geometry_responds_to_user_height(self):
        a=self.post('/api/preview',{'project':self.project})
        modified=copy.deepcopy(self.project)
        modified['geometry']['height_m'] += 0.35
        b=self.post('/api/preview',{'project':modified})
        def y(result):
            return next(n['y_mm'] for n in result['model']['nodes'] if n['id']=='T00')
        self.assertAlmostEqual(y(b)-y(a),350.0, places=7)

    def test_preview_nodal_loads_agree_with_real_motor(self):
        preview=self.post('/api/preview',{'project':self.project,'load_case':'G2'})
        actual=run_project(self.project,self.catalog)
        for nid,components in preview['loads'].items():
            expected=actual['analyses']['G2']['loads'][nid]
            self.assertAlmostEqual(components['fx_n'],expected['fx_n'],places=7)
            self.assertAlmostEqual(components['fy_n'],expected['fy_n'],places=7)
        self.assertAlmostEqual(preview['load_audit']['residual']['moment_nmm'],0.0,places=6)

    def test_unknown_load_case_is_rejected(self):
        with self.assertRaises(HTTPError) as ex:
            self.post('/api/preview',{'project':self.project,'load_case':'INEXISTENTE'})
        self.assertEqual(ex.exception.code,422)

    def test_preview_cannot_be_called_without_token(self):
        with self.assertRaises(HTTPError) as ex:
            self.post('/api/preview',{'project':self.project},token='incorrect-token')
        self.assertEqual(ex.exception.code,403)

    def test_security_headers(self):
        with urlopen(self.origin) as response:
            self.assertEqual(response.headers.get('X-Frame-Options'),'DENY')
            self.assertEqual(response.headers.get('Cross-Origin-Resource-Policy'),'same-origin')
            self.assertIn("frame-ancestors 'none'",response.headers.get('Content-Security-Policy'))

    def test_invalid_geometry_is_rejected_without_old_result(self):
        bad=copy.deepcopy(self.project)
        bad['geometry']['span_m']=0
        with self.assertRaises(HTTPError) as ex:
            self.post('/api/preview',{'project':bad})
        self.assertEqual(ex.exception.code,422)

if __name__=='__main__':unittest.main()
