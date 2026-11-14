"""Regressão cumulativa v0.2 (cargas) + v0.3 (estabilidade declarada).

Sem resultados fabricados do FTool: benchmarks de comparação externa continuam PENDENTES.
"""
import copy
import json
import math
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from poe_truss.catalog import load_catalog
from poe_truss.model import make_model
from poe_truss.loads import build_case_loads,loads_by_case,combination_audit,merge_forces
from poe_truss.stability import resolve_stability
from poe_truss.engine import run_project
from poe_truss.export import load_audit_rows,stability_rows,dimperfil_rows

CAT=load_catalog(ROOT/'catalogo_perfis.csv')
BASE=json.loads((ROOT/'examples/cobertura_duas_aguas.json').read_text(encoding='utf-8'))
TRI=json.loads((ROOT/'examples/FTool_A02_trelica_triangular.json').read_text(encoding='utf-8'))

def roof(): return copy.deepcopy(BASE)

class AuditingTests(unittest.TestCase):
    def test_olidio_tributary_panel(self):
        p=roof();p['geometry'].update({'span_m':3.35,'frame_spacing_m':7.5,
           'panels':2,'height_m':.75,'rise_m':0,'roof_shape':'parallel'})
        m=make_model(p,CAT)
        case={'id':'G2','kind':'surface','value':35,'force_unit':'kgf',
              'application':'top','basis':'projected','direction':'down'}
        nodal,a=build_case_loads(m,case)
        self.assertAlmostEqual(-nodal['T01'][1]/10,35*7.5*1.675,places=9)
        self.assertEqual(len(a['entries']),4)
        self.assertEqual(a['status'],'CONSISTENTE_ALGEBRICAMENTE')
        self.assertAlmostEqual(a['sum_fy_n'],-35*7.5*3.35*10,places=8)

    def test_weight_matches_mass_and_entries(self):
        m=make_model(BASE,CAT)
        loads,a=build_case_loads(m,{'id':'G1','kind':'self_weight'})
        self.assertEqual(len(a['entries']),2*len(m.members))
        self.assertAlmostEqual(-sum(v[1] for v in loads.values()),10*m.mass_kg(),places=8)
        self.assertAlmostEqual(a['sum_m_origin_nmm'],sum(item['moment_origin_nmm'] for item in a['entries']),places=4)

    def test_horizontal_normal_wind_and_moments(self):
        m=make_model(BASE,CAT)
        c={'id':'W','kind':'surface','value':300,'force_unit':'kgf','zone':'left',
           'basis':'roof_surface','direction':'outward_normal','application':'top'}
        f,a=build_case_loads(m,c)
        self.assertLess(a['sum_fx_n'],0)
        self.assertGreater(a['sum_fy_n'],0)
        self.assertAlmostEqual(a['sum_m_origin_nmm'],sum(m.node_map()[k].x*v[1]-m.node_map()[k].y*v[0] for k,v in f.items()),delta=1e-4)
        self.assertLess(abs(a['residual']['moment_nmm']),1e-4)

    def test_nodal_source_trace_and_units(self):
        m=make_model(TRI,CAT)
        f,a=build_case_loads(m,{'id':'A','kind':'nodal','loads':[
          {'node':'C','fx':1,'fy':-2,'force_unit':'tf'},
          {'node':'C','fx':-10,'fy':0,'force_unit':'kN'}]})
        self.assertEqual(f['C'],(0.,-20000.))
        self.assertEqual(a['entries'][0]['input_unit'],'tf')
        self.assertEqual(a['entries'][1]['source'],'load_2')

    def test_combination_signed_ledger(self):
        m=make_model(TRI,CAT)
        a,_=build_case_loads(m,{'id':'A','kind':'nodal','loads':[{'node':'C','fy':10,'force_unit':'kN'}]})
        b,_=build_case_loads(m,{'id':'B','kind':'nodal','loads':[{'node':'C','fy':3,'force_unit':'kN'}]})
        raw={'A':a,'B':b}
        comb=combination_audit('S',{'A':1.3,'B':-2.},raw)
        self.assertAlmostEqual(comb['sum_fy_n'],7000,places=9)
        self.assertAlmostEqual(merge_forces({'A':1.3,'B':-2.},raw)['C'][1],7000)

    def test_audit_does_not_change_solver_result(self):
        result=run_project(BASE,CAT)
        before=loads_by_case(make_model(BASE,CAT),BASE['load_cases'][0])
        self.assertEqual(result['analyses']['G1']['loads']['T00']['fy_n'],before['T00'][1])
        self.assertIn('load_audit',result)
        self.assertTrue(load_audit_rows(result,'G1'))
        self.assertTrue(load_audit_rows(result,'S_GRAV'))

    def test_invalid_direction_and_negative_intensity(self):
        m=make_model(BASE,CAT)
        case={'id':'ERR','kind':'surface','value':-1,'force_unit':'kgf'}
        with self.assertRaises(ValueError):build_case_loads(m,case)
        case['value']=10;case['direction']='sideways'
        with self.assertRaises(ValueError):build_case_loads(m,case)

    def test_explicit_triangle_analytic_unchanged(self):
        r=run_project(TRI,CAT)
        self.assertAlmostEqual(r['analyses']['F10']['axial_n']['AB']/1000,6.6666666667,places=7)
        self.assertAlmostEqual(r['analyses']['F10']['nodal_displacements']['C']['uy_mm'],-.2625,places=9)

class StabilityDataTests(unittest.TestCase):
    def test_no_unverified_bracing_inferred(self):
        r=run_project(BASE,CAT)
        self.assertEqual(r['stability']['summary']['pending'],len(r['model']['members']))
        self.assertTrue(all(e['unbraced_out_of_plane_mm'] is None for e in r['stability']['members'].values()))
        self.assertTrue(all(not e['resistance_verified'] for e in r['stability']['members'].values()))

    def test_group_and_individual_override(self):
        p=roof();p['stability']={'groups':{'superior':{
            'unbraced_out_of_plane_mm':4000,'k_out_of_plane':1.1,
            'axis_in_plane':'x','axis_out_of_plane':'y','torsion_unbraced_mm':4000,
            'restraint_reference':'Hipótese externa sujeita a verificação'}},
            'members':{'M002':{'unbraced_out_of_plane_mm':2000,'k_out_of_plane':1.2}}}
        r=run_project(p,CAT)['stability']['members']
        self.assertAlmostEqual(r['M002']['effective_out_of_plane_mm'],2400)
        self.assertAlmostEqual(r['M004']['effective_out_of_plane_mm'],4400)
        self.assertEqual(r['M004']['state'],'PENDENTE') # Dupla seção transversal sem propriedades resistentes verificadas

    def test_braced_chord_span_instead_of_panel(self):
        p=roof();p['stability']={'lateral_bracing':[{ 
            'group':'superior','node_ids':['T00','T04','T08','T12','T16'],
            'assumed_effective':True,'reference':'Sistema de contraventamento declarado pelo projetista'}]}
        r=run_project(p,CAT)['stability']['members']
        self.assertGreater(r['M002']['unbraced_out_of_plane_mm'],4000)
        self.assertEqual(r['M002']['out_of_plane_source'],'bracing_assumed_effective')
        self.assertIsNone(r['M001']['unbraced_out_of_plane_mm'])

    def test_brace_not_verified_is_not_used(self):
        p=roof();p['stability']={'lateral_bracing':[{
            'group':'superior','node_ids':['T00','T16'],'assumed_effective':False}]}
        r=run_project(p,CAT)['stability']['members']
        self.assertIsNone(r['M002']['unbraced_out_of_plane_mm'])

    def test_brace_requires_justification(self):
        p=roof();p['stability']={'lateral_bracing':[{
            'group':'superior','node_ids':['T00','T16'],'assumed_effective':True}]}
        with self.assertRaisesRegex(ValueError,'referência'):run_project(p,CAT)

    def test_brace_unsupported_node_rejected(self):
        p=roof();p['stability']={'lateral_bracing':[{
            'group':'superior','node_ids':['T00','B16'],'assumed_effective':True,
            'reference':'Documento de projeto'}]}
        with self.assertRaisesRegex(ValueError,'não pertence'):run_project(p,CAT)

    def test_invalid_out_plane_length_rejected(self):
        p=roof();p['stability']={'groups':{'superior':{'unbraced_out_of_plane_mm':-5}}}
        with self.assertRaisesRegex(ValueError,'positivo'):run_project(p,CAT)

    def test_undefined_or_mismatched_member_rejected(self):
        p=roof();p['stability']={'members':{'M999':{'k_in_plane':1}}}
        with self.assertRaisesRegex(ValueError,'não existentes'):run_project(p,CAT)

    def test_explicit_case_is_supported_without_catalog_transverse_data(self):
        r=run_project(TRI,CAT)['stability']
        self.assertIn('AB',r['members'])
        self.assertFalse(r['members']['AB']['radii_reference_mm'])

    def test_export_stability_has_no_fake_resistance(self):
        r=run_project(BASE,CAT)
        rows=stability_rows(r)
        self.assertEqual(len(rows),len(r['model']['members']))
        self.assertTrue(all(x['resistance_verified'] is False for x in rows))
        dp=dimperfil_rows(r)
        self.assertIn('comprimento_efetivo_fora_plano_mm',dp[0])
        self.assertEqual(dp[0]['Nrd_compressao_kgf_INSERIR'],'')

    def test_stability_changes_do_not_modify_solver(self):
        p=roof();base=run_project(p,CAT)
        p['stability']={'groups':{'superior':{'k_in_plane':1.5,
           'unbraced_out_of_plane_mm':5000,'rotation_deg':90}}}
        changed=run_project(p,CAT)
        self.assertEqual(base['analyses']['S_GRAV']['axial_n'],changed['analyses']['S_GRAV']['axial_n'])

    def test_angle_rotation_keeps_reference_slenderness_pending(self):
        p=roof();p['sections']['montante']['count']=1
        p['stability']={'groups':{'montante':{
            'rotation_deg':90,'axis_in_plane':'x','axis_out_of_plane':'y',
            'unbraced_out_of_plane_mm':2000}}}
        r=run_project(p,CAT)['stability']['members']
        first=next(v for v in r.values() if v['group']=='montante')
        self.assertIsNone(first['lambda_in_plane_reference'])
        self.assertIn('propriedades_transversais_nao_validadas_para_arranjo_ou_rotacao',first['missing'])

if __name__=='__main__':unittest.main()
