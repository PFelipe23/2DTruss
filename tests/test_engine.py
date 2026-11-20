"""Testes de regressão e benchmarks analíticos independentes do FTool.

Executar: python -m unittest discover -s tests -v
"""
from __future__ import annotations
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
from poe_truss.loads import loads_by_case,merge_forces
from poe_truss.solver import LinearTruss,StabilityError
from poe_truss.units import force_n,area_pressure_n_per_mm2,line_n_per_mm
from poe_truss.engine import run_project
from poe_truss.search import suggest_geometry

CATALOG=load_catalog(ROOT/'catalogo_perfis.csv')
TRIANGLE=json.loads((ROOT/'examples/FTool_A02_trelica_triangular.json').read_text())
ROOF=json.loads((ROOT/'examples/cobertura_duas_aguas.json').read_text())


class AnalyticTests(unittest.TestCase):
    def test_classified_envelopes_keep_manual_combinations_out(self):
        project = copy.deepcopy(TRIANGLE)
        project['combinations'] = [
            {'id': 'U', 'combination_class': 'uls_normal', 'factors': {'F10': 2}},
            {'id': 'S', 'combination_class': 'sls_rare', 'factors': {'F10': -1}},
            {'id': 'M', 'factors': {'F10': 10}},
        ]
        result = run_project(project, CATALOG)
        self.assertEqual(result['envelope_combinations'], {'elu': ['U'], 'els': ['S']})
        self.assertEqual(result['envelope']['AB']['tension_case'], 'M')
        self.assertEqual(result['classified_envelopes']['elu']['AB']['tension_case'], 'U')
        self.assertNotIn('els', result['classified_envelopes'])
        self.assertAlmostEqual(result['analyses']['S']['axial_n']['AB'], -20_000 / 3)
        self.assertAlmostEqual(result['analyses']['S']['nodal_displacements']['C']['uy_mm'], .2625)

    def test_static_case_and_combination_apply_pattern_factors(self):
        from desktop.bridge import Session
        from desktop.workflow import add_combination, update_combination, update_static_case

        project = copy.deepcopy(TRIANGLE)
        project['load_patterns'] = [{
            'id': 'Q4', 'kind': 'nodal', 'action_class': 'variable',
            'loads': [{'node': 'C', 'fy': -4, 'force_unit': 'kN'}],
        }]
        project = update_static_case(project, 'Q18', 'Cargas combinadas',
                                     {'F10': 1, 'Q4': 2}, create=True)
        project = add_combination(project, 'S9')
        project = update_combination(project, 'S9', {'Q18': .5}, 'sls_rare')
        session = Session(project, CATALOG)
        result = session.calculate()
        self.assertNotIn('Q4', result['analyses'])
        self.assertEqual(session.forces_for_case('Q4')['C'], (0., -4000.))
        self.assertEqual(session.forces_for_case('S9')['C'], (0., -9000.))
        case = result['analyses']['Q18']
        self.assertAlmostEqual(case['axial_n']['AC'], -15000.)
        self.assertAlmostEqual(case['reactions']['A']['fy_n'], 9000.)
        self.assertAlmostEqual(result['analyses']['S9']['axial_n']['AB'], 6000.)
        self.assertEqual({row['pattern_id'] for row in result['load_audit']['Q18']['entries']},
                         {'F10', 'Q4'})

    def test_A02_member_forces(self):
        r=run_project(TRIANGLE,CATALOG)['analyses']['F10']['axial_n']
        self.assertAlmostEqual(r['AB']/1000, 6.6666666667, places=8)
        self.assertAlmostEqual(r['AC']/1000,-8.3333333333,places=8)
        self.assertAlmostEqual(r['BC']/1000,-8.3333333333,places=8)

    def test_A02_reactions(self):
        r=run_project(TRIANGLE,CATALOG)['analyses']['F10']['reactions']
        self.assertAlmostEqual(r['A']['fy_n']/1000,5,places=9)
        self.assertAlmostEqual(r['B']['fy_n']/1000,5,places=9)
        self.assertAlmostEqual(r['A']['fx_n']/1000,0,places=9)

    def test_A02_C_vertical_deflection_analytic_virtual_work(self):
        # δ = [N_AB²*4000 + 2*N_AC²*2500] / (P*E*A) = 0,2625 mm
        r=run_project(TRIANGLE,CATALOG)['analyses']['F10']
        self.assertAlmostEqual(r['nodal_displacements']['C']['uy_mm'],-0.2625,places=10)
        # Apoio móvel em B permite deslocamento horizontal do nó C, mesmo com geometria simétrica.
        self.assertAlmostEqual(r['nodal_displacements']['C']['ux_mm'],1/15,places=10)

    def test_A02_elastic_scaling_E(self):
        a=run_project(TRIANGLE,CATALOG)['analyses']['F10']
        p=copy.deepcopy(TRIANGLE);p['material']['E_MPa']=400000
        b=run_project(p,CATALOG)['analyses']['F10']
        for m in ('AB','AC','BC'):
            self.assertAlmostEqual(a['axial_n'][m],b['axial_n'][m],places=7)
        self.assertAlmostEqual(a['nodal_displacements']['C']['uy_mm'],2*b['nodal_displacements']['C']['uy_mm'],places=10)

    def test_reverse_load_reverses_response(self):
        p=copy.deepcopy(TRIANGLE)
        p['load_cases'][0]['loads'][0]['fy']=10
        a=run_project(TRIANGLE,CATALOG)['analyses']['F10']
        b=run_project(p,CATALOG)['analyses']['F10']
        for member in a['axial_n']:self.assertAlmostEqual(a['axial_n'][member],-b['axial_n'][member],places=6)

    def test_A01_isolated_axial_bar(self):
        p=copy.deepcopy(TRIANGLE)
        p['model_override']={'nodes':[{'id':'A','x_mm':0,'y_mm':0},{'id':'B','x_mm':2000,'y_mm':0}],
          'members':[{'id':'AB','i':'A','j':'B','area_mm2':500}],
          'supports':[{'node':'A','ux':True,'uy':True},{'node':'B','ux':False,'uy':True}]}
        p['load_cases']=[{'id':'F','kind':'nodal','loads':[{'node':'B','fx':10,'fy':0,'force_unit':'kN'}]}]
        r=run_project(p,CATALOG)['analyses']['F']
        self.assertAlmostEqual(r['axial_n']['AB'],10000,places=9)
        self.assertAlmostEqual(r['nodal_displacements']['B']['ux_mm'],10000*2000/(200000*500),places=10)


class ActionTests(unittest.TestCase):
    def test_nominal_units(self):
        self.assertEqual(force_n(1000,'kgf'),force_n(1,'tf'))
        self.assertEqual(force_n(1,'tf'),force_n(10,'kN'))
        self.assertAlmostEqual(area_pressure_n_per_mm2(100,'kgf'),.001)
        self.assertAlmostEqual(line_n_per_mm(100,'kgf'),1)

    def test_uniform_roof_projection_resultant(self):
        m=make_model(ROOF,CATALOG)
        f=loads_by_case(m,{'kind':'surface','value':10,'force_unit':'kgf',
                           'application':'top','basis':'projected','direction':'down','zone':'all'})
        self.assertAlmostEqual(sum(v[1] for v in f.values()),-10*10*m.span_mm/1000*m.frame_spacing_mm/1000,places=6)

    def test_self_weight_mass_consistency(self):
        m=make_model(ROOF,CATALOG)
        f=loads_by_case(m,{'kind':'self_weight'})
        self.assertAlmostEqual(sum(v[1] for v in f.values()),-10*m.mass_kg(),places=6)

    def test_wind_roof_normal_has_horizontal_on_each_slope(self):
        m=make_model(ROOF,CATALOG)
        f=loads_by_case(m,{'kind':'surface','value':10,'force_unit':'kgf',
                          'application':'top','basis':'roof_surface','direction':'outward_normal','zone':'left'})
        self.assertLess(sum(v[0] for v in f.values()),0)
        self.assertGreater(sum(v[1] for v in f.values()),0)

    def test_symmetric_suction_horizontal_cancel(self):
        m=make_model(ROOF,CATALOG)
        f=loads_by_case(m,{'kind':'surface','value':10,'force_unit':'kgf',
                          'application':'top','basis':'roof_surface','direction':'outward_normal','zone':'all'})
        self.assertAlmostEqual(sum(v[0] for v in f.values()),0,places=7)

    def test_nodal_force_conservation(self):
        m=make_model(TRIANGLE,CATALOG)
        f=loads_by_case(m,TRIANGLE['load_cases'][0]);self.assertEqual(f['C'],(0.,-10000.))

    def test_combination_superposition(self):
        r=run_project(ROOF,CATALOG)
        combo=r['analyses']['S_GRAV']
        for m in r['model']['members']:
            expected=sum(r['analyses'][k]['axial_n'][m['id']] for k in ('G1','G2','G3','G4','G5','Q1'))
            self.assertAlmostEqual(combo['axial_n'][m['id']],expected,delta=max(abs(expected)*1e-8,1e-5))

    def test_resultants_normal_vs_vertical_differ(self):
        m=make_model(ROOF,CATALOG)
        normal=loads_by_case(m,{'kind':'surface','value':10,'force_unit':'kgf',
          'application':'top','basis':'roof_surface','direction':'outward_normal'})
        up=loads_by_case(m,{'kind':'surface','value':10,'force_unit':'kgf',
          'application':'top','basis':'roof_surface','direction':'up'})
        self.assertNotAlmostEqual(sum(x[1] for x in normal.values()),sum(x[1] for x in up.values()),places=5)


class StabilityTests(unittest.TestCase):
    def test_missing_horizontal_support_is_mechanism(self):
        p=copy.deepcopy(TRIANGLE)
        p['model_override']['supports']=[{'node':'A','ux':False,'uy':True},{'node':'B','ux':False,'uy':True}]
        with self.assertRaises(StabilityError):run_project(p,CATALOG)

    def test_duplicate_bar_rejected(self):
        p=copy.deepcopy(TRIANGLE)
        p['model_override']['members'].append(copy.deepcopy(p['model_override']['members'][0]))
        p['model_override']['members'][-1]['id']='AB2'
        with self.assertRaisesRegex(ValueError,'duplicada'):run_project(p,CATALOG)

    def test_zero_area_rejected(self):
        p=copy.deepcopy(TRIANGLE);p['model_override']['members'][0]['area_mm2']=0
        with self.assertRaises(ValueError):run_project(p,CATALOG)

    def test_support_relocated_keeps_symmetric_result(self):
        p=copy.deepcopy(TRIANGLE)
        p['model_override']['supports']=[{'node':'A','ux':False,'uy':True},{'node':'B','ux':True,'uy':True}]
        a=run_project(TRIANGLE,CATALOG)['analyses']['F10']
        b=run_project(p,CATALOG)['analyses']['F10']
        for m in a['axial_n']:
            self.assertAlmostEqual(a['axial_n'][m],b['axial_n'][m],places=6)

    def test_equilibrium_force_and_moment(self):
        r=run_project(ROOF,CATALOG)
        for case in r['analyses'].values():
            eq=case['equilibrium']
            self.assertLess(abs(eq['sum_fx_n']),1e-5)
            self.assertLess(abs(eq['sum_fy_n']),1e-5)
            self.assertLess(abs(eq['sum_m_nmm']),1e-1)
            self.assertLess(abs(eq['max_free_residual_n']),1e-5)

    def test_geometry_diagnostics(self):
        r=run_project(ROOF,CATALOG)
        self.assertEqual(len(r['geometry_diagnostics']['purlin_spans']),ROOF['geometry']['panels'])
        self.assertTrue(r['geometry_diagnostics']['all_roof_steps_within_max'])

    def test_envelopes_sources_are_existing(self):
        r=run_project(ROOF,CATALOG)
        for v in r['envelope'].values():
            if v['tension_case']:self.assertIn(v['tension_case'],r['analyses'])
            if v['compression_case']:self.assertIn(v['compression_case'],r['analyses'])

    def test_case_does_not_contaminate_other(self):
        p=copy.deepcopy(ROOF)
        base=run_project(p,CATALOG)['analyses']['G1']['axial_n']
        p['load_cases'][-1]['value']=900
        changed=run_project(p,CATALOG)['analyses']['G1']['axial_n']
        for k in base:self.assertAlmostEqual(base[k],changed[k],places=6)



class GeometrySearchTests(unittest.TestCase):
    def test_geometry_search_ordered_candidates(self):
        result=suggest_geometry(ROOF,CATALOG)
        self.assertGreater(result['evaluated'],10)
        self.assertLessEqual(len(result['candidates']),10)
        self.assertTrue(result['candidates'][0]['purlin_ok'])
        self.assertTrue(result['candidates'][0]['displacement_ok'])

    def test_search_does_not_modify_project(self):
        original=copy.deepcopy(ROOF)
        suggest_geometry(ROOF,CATALOG)
        self.assertEqual(ROOF,original)

    def test_search_restricts_invalid_limits(self):
        with self.assertRaisesRegex(ValueError,'Parâmetros de pesquisa'):
            suggest_geometry(ROOF,CATALOG,{'height_step_m':0.001})

if __name__=='__main__': unittest.main()
