import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from poe_truss.catalog import load_catalog
from poe_truss.engine import run_project
from poe_truss.migrate import migrate_v05

class MigrationTests(unittest.TestCase):
    def test_legacy_project_imports_without_silent_selfweight_double_count(self):
        cat=load_catalog(ROOT/'catalogo_perfis.csv')
        raw=json.loads((ROOT/'examples/modelo_legado_v05_para_teste.json').read_text())
        p=migrate_v05(raw,cat)
        self.assertEqual(p['geometry']['roof_shape'],'gable')
        self.assertEqual(p['sections']['superior']['count'],2)
        self.assertFalse(any(c['kind']=='self_weight' for c in p['load_cases']))
        self.assertAlmostEqual(next(c['value'] for c in p['load_cases'] if c['id']=='G_LEG'),40)
        r=run_project(p,cat)
        self.assertEqual(len(r['model']['members']),33)
        self.assertIn('ELS_LEG',r['analyses'])
    def test_bad_schema_rejected(self):
        with self.assertRaises(ValueError):migrate_v05({'schema':'unknown'}, {})
