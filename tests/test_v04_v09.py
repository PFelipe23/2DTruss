"""Regressões acumulativas v0.4--v0.1 (triagem != aprovação normativa)."""
from __future__ import annotations
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from poe_truss.catalog import load_catalog
from poe_truss.engine import run_project
from poe_truss.model import make_model
from poe_truss.sections import section_properties
from poe_truss.axial import axial_screen
from poe_truss.camber import suggested_camber
from poe_truss.design import suggest_sections
from poe_truss.export import axial_screen_rows, section_properties_rows,camber_rows,integrated_report_html,as_csv
from poe_truss.cli import export_ftool

ROOT=Path(__file__).resolve().parent.parent
CAT=load_catalog(ROOT/'catalogo_perfis.csv')
BASE=json.loads((ROOT/'examples/cobertura_duas_aguas.json').read_text(encoding='utf-8'))


class TestV09(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=run_project(BASE,CAT)

    def test_01_old_model_preserved(self):
        self.assertEqual(self.base['software_version'],'0.1')
        self.assertEqual(len(self.base['model']['members']),65)
        self.assertIn('stability',self.base)
        self.assertIn('load_audit',self.base)
        self.assertIn('axial_screen',self.base)
        self.assertIn('section_properties',self.base)
        self.assertIn('camber',self.base)
        self.assertIn('S_GRAV',self.base['analyses'])

    def test_02_assembly_inertia_parallel_axes(self):
        p=copy.deepcopy(BASE)
        p['section_arrangements']={'superior':{'centroid_dx_mm':60,'centroid_dy_mm':30,'rotation_deg':0}}
        m=make_model(p,CAT)
        a=section_properties(m,p,CAT)['members']
        upper=next(x for x in m.members if x.group=='superior')
        s=a[upper.id]
        original=CAT[upper.profile]
        self.assertAlmostEqual(s['area_mm2'],2*original.area_mm2)
        self.assertAlmostEqual(s['ix_mm4'],2*original.ix_mm4+original.area_mm2*30**2/2)
        self.assertAlmostEqual(s['iy_mm4'],2*original.iy_mm4+original.area_mm2*60**2/2)
        self.assertFalse(s['connected_as_unit_verified'])

    def test_03_perpendicular_rotation_and_geometry_reject(self):
        p=copy.deepcopy(BASE)
        p['section_arrangements']={'superior':{'rotation_deg':90}}
        a=section_properties(make_model(p,CAT),p,CAT)['members']
        member=next(x for x in a.values() if x['group']=='superior')
        self.assertGreater(member['ix_mm4'],0)
        p['section_arrangements']['superior']['rotation_deg']=30
        with self.assertRaisesRegex(ValueError,'rotações ortogonais'):run_project(p,CAT)

    def test_04_l_shape_requires_ixy(self):
        s=next(x for x in self.base['section_properties']['members'].values() if x['group']=='diagonal')
        self.assertEqual(s['state'],'PARCIAL_Ixy_DESCONHECIDO')
        self.assertIsNone(s['ixy_mm4'])

    def test_05_tension_gross_and_sign(self):
        m=self.base['model']['members'][0]; a=self.base['axial_screen']['members'][m['id']]
        self.assertAlmostEqual(a['gross_yield_screen_n'],m['area_mm2']*250/1.1)
        self.assertGreaterEqual(a['tension_sd_n'],0)
        self.assertGreaterEqual(a['compression_sd_n'],0)
        self.assertEqual(a['verification_status'],'NAO_VERIFICADO_NORMATIVAMENTE')
        self.assertEqual(a['local_buckling'],'NAO_VERIFICADA')

    def test_06_no_euler_without_axis_and_bracing(self):
        a=self.base['axial_screen']['members']
        self.assertTrue(any(v['euler_min_n'] is None for v in a.values()))
        self.assertEqual(self.base['axial_screen']['summary']['external_missing'],65)

    def test_07_euler_reference_formula(self):
        p=copy.deepcopy(BASE)
        p['sections']['inferior']['count']=1
        p['stability']={'groups':{'inferior':{'axis_in_plane':'x','axis_out_of_plane':'y',
          'unbraced_out_of_plane_mm':2000,'k_in_plane':1,'k_out_of_plane':1}}}
        r=run_project(p,CAT)
        item=next(x for x in r['axial_screen']['members'].values() if x['group']=='inferior')
        sec=r['section_properties']['members'][item['member_id']]
        expect=math.pi**2*200000*sec['iy_mm4']/2000**2
        mode=next(v for v in item['euler_modes'] if v['mode']=='out_of_plane')
        self.assertAlmostEqual(mode['euler_critical_n'],expect)
        self.assertNotEqual(item['verification_status'],'ATENDE')

    def test_08_external_resistance_must_match_profile(self):
        m=self.base['model']['members'][0]
        p=copy.deepcopy(BASE)
        p['external_resistances']={'members':{m['id']:{'profile':'OUTRO','source':'DimPerfil',
         'tension_rd_n':1e6,'compression_rd_n':1e6}}}
        with self.assertRaisesRegex(ValueError,'não corresponde'):run_project(p,CAT)

    def test_09_external_resistance_comparison_is_not_normative(self):
        m=self.base['model']['members'][0]
        p=copy.deepcopy(BASE)
        p['external_resistances']={'members':{m['id']:{'profile':m['profile'],'source':'DimPerfil manual',
          'tension_rd_n':100,'compression_rd_n':100}}}
        a=run_project(p,CAT)['axial_screen']['members'][m['id']]
        self.assertEqual(a['external_capacity']['state'],'DECLARADA_PELO_PROJETISTA')
        self.assertEqual(a['verification_status'],'NAO_VERIFICADO_NORMATIVAMENTE')

    def test_10_camber_stays_zero_at_ends(self):
        cam=self.base['camber']
        self.assertEqual(cam['state'],'GEOMETRIA_PRELIMINAR_NAO_CONSTRUTIVA')
        self.assertAlmostEqual(cam['nodes'][0]['camber_y_mm'],0)
        self.assertAlmostEqual(next(x['camber_y_mm'] for x in cam['nodes'] if x['node_id']=='T00'),0)
        self.assertAlmostEqual(next(x['camber_y_mm'] for x in cam['nodes'] if x['node_id']=='T16'),0)
        self.assertGreater(cam['max_abs_camber_mm'],0)

    def test_11_camber_fraction_and_missing_case(self):
        p=copy.deepcopy(BASE);p['camber']={'reference_case':'G1','compensation_fraction':0.5}
        half=run_project(p,CAT)['camber']['max_abs_camber_mm']
        self.assertAlmostEqual(half*2,self.base['camber']['max_abs_camber_mm'],places=7)
        p['camber']['reference_case']='INEXISTENTE'
        self.assertEqual(run_project(p,CAT)['camber']['state'],'PENDENTE_CASO_REFERENCIA')

    def test_12_optimizer_runs_without_ELU_claims(self):
        r=suggest_sections(BASE,CAT,{'service_case':'S_GRAV','flecha_rel':250,
                                    'profiles':{'montante':[BASE['sections']['montante']['profile']]}})
        self.assertGreaterEqual(r['evaluated'],4)
        self.assertEqual(r['resistant_design_status'],'PENDENTE_NBR_14762_E_LIGACOES')
        self.assertIn('superior',r['selected_sections'])

    def test_13_optimizer_rejects_bad_profiles(self):
        r=suggest_sections(BASE,CAT,{'profiles':{'montante':['PERFIL_DESCONHECIDO']}})
        self.assertTrue(any('não cadastrado' in msg for msg in r['invalid']))

    def test_14_exports(self):
        r=self.base
        self.assertEqual(len(axial_screen_rows(r)),65)
        self.assertEqual(len(section_properties_rows(r)),65)
        self.assertEqual(len(camber_rows(r)),34)
        self.assertIn('NAO_VERIFICADO_NORMATIVAMENTE',as_csv(axial_screen_rows(r)))
        html=integrated_report_html(r,BASE,'S_GRAV')
        self.assertIn('ANEXO TÉCNICO v0.1',html)
        self.assertIn('</html>',html)

    def test_15_manifest_ftool_does_not_fake_native(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)
            export_ftool(ROOT/'examples/cobertura_duas_aguas.json',out,'S_GRAV')
            x=json.loads((out/'manifesto_ftool.json').read_text())
            self.assertFalse(x['ftool_native_model_generated'])
            self.assertEqual(len(x['sha256_model_and_loads']),64)
            self.assertEqual(x['external_ftool_result_status'],'PENDENTE')

if __name__=='__main__':unittest.main()
