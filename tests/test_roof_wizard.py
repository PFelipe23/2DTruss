"""Conferência analítica dos carregamentos e planos gerados pelo assistente."""

from math import ceil, hypot
from pathlib import Path

import pytest

from desktop.bridge import Session, load_project
from poe_truss.roof_wizard import (
    analyze_bracing, bracing_plane, bracing_stations, roof_alternatives, roof_project,
    chord_bracing_planes, chord_bracing_project, preliminary_roof_project,
)


ROOT = Path(__file__).resolve().parents[1]


def test_study_uses_distinct_service_and_factored_loads_and_sizes_candidate():
    template = load_project(ROOT / 'examples' / 'cobertura_duas_aguas.json')
    study = preliminary_roof_project(template, name='Estudo', geometry=template['geometry'], intensities={})
    assert [p.get('value') for p in study['load_patterns']] == [None, 6, 6, 1, 10, 25]
    assert set(study['combinations'][0]['factors'].values()) == {1}
    assert study['combinations'][1]['factors']['CASO_Q1'] == 1.50
    assert study['combinations'][1]['factors']['CASO_G1'] == 1.25
    session = Session(study)
    candidate = roof_alternatives(study, session.catalog, height_min=1.1, height_max=1.1,
                                  ratio=250, size_profiles=True)['candidates'][0]
    assert all(section['count'] == 1 for section in candidate['sections'].values())
    assert candidate['meets_geometric_service_criteria']
    assert {member.id[:2] for member in session.model.members} == {'BS', 'BI', 'MO', 'DI'}


@pytest.mark.parametrize('modules', [2, 3])
def test_symmetric_chord_planes_use_round_tension_only_diagonals(modules):
    roof = sample_roof()
    catalog = Session(roof).catalog
    widths = chord_bracing_planes(roof, catalog)
    assert widths['BS-E'] == pytest.approx(widths['BS-D'])
    assert widths['BI-E'] == pytest.approx(widths['BI-D'])
    for key, width in widths.items():
        project = chord_bracing_project(roof, key, width, dict(
            bays=modules, area_mm2=1000, diameter_mm=12.5, force_kn=2,
        ))
        session = Session(project, catalog)
        results = session.calculate()['analyses']
        for case in results.values():
            axial = case['axial_n']
            assert min(axial[m.id] for m in session.model.members if m.group != 'montante') >= 0
            assert any(axial[m.id] > 0 for m in session.model.members if m.group == 'diagonal')
            assert any(axial[m.id] == 0 for m in session.model.members if m.group == 'diagonal')
            assert abs(case['equilibrium']['sum_fx_n']) < 1e-7


def sample_roof():
    template = load_project(ROOT / 'examples' / 'cobertura_duas_aguas.json')
    return roof_project(
        template,
        name='Cobertura de referência',
        geometry=template['geometry'],
        roofing={'model': 'Telha de ensaio', 'mass_kg_m2': 8},
        actions={'self_weight': False, 'additional': .1, 'live': .25, 'pressure': .3, 'suction': .4},
    )


def test_roof_wizard_preserves_basis_units_and_load_directions():
    session = Session(sample_roof())
    result = session.calculate()
    analyses = result['analyses']
    roof_area = 2 * hypot(8., 1.2) * 5
    horizontal_area = 16 * 5

    def total_vertical(case):
        return sum(load['fy_n'] for load in analyses[case]['loads'].values())

    assert total_vertical('CASO_G2') == pytest.approx(-80 * roof_area)
    assert total_vertical('CASO_G3') == pytest.approx(-100 * horizontal_area)
    assert total_vertical('CASO_Q1') == pytest.approx(-250 * horizontal_area)
    assert total_vertical('CASO_W_PRESS') == pytest.approx(-300 * horizontal_area)
    assert total_vertical('CASO_W_SUCC') == pytest.approx(400 * horizontal_area)
    assert total_vertical('REF_GRAV') == pytest.approx(-80 * roof_area - 350 * horizontal_area)
    assert analyses['CASO_W_SUCC']['loads']['T00']['fx_n'] < 0


def test_roof_search_uses_inclined_purlin_step():
    project = sample_roof()
    session = Session(project)
    target = 2 * ceil(hypot(8., 1.2) / 1.2)
    outcome = roof_alternatives(project, session.catalog, height_min=1.1, height_max=1.2, ratio=250)
    choice = outcome['candidates'][0]
    assert outcome['evaluated'] > 1
    assert choice['panels'] >= target
    assert choice['max_purlin_m'] <= 1.2
    assert choice['meets_geometric_service_criteria']


def test_isolated_bracing_plane_matches_horizontal_and_moment_equilibrium():
    roof = sample_roof()
    parent = Session(roof)
    spec = {'bays': 1, 'area_mm2': 1000, 'force_kn': 2, 'panels': 16,
            'stations': ['B08'], 'reference': 'Caso analítico de teste'}
    station = bracing_stations(roof, parent.catalog)['B08']
    assert station['height_mm'] == pytest.approx(2300)
    plane = bracing_plane(roof, station, spec)
    assert len(plane['model_override']['members']) == 6
    session = Session(plane)
    result = session.calculate()
    positive = result['analyses']['H_POS']
    negative = result['analyses']['H_NEG']
    assert positive['reactions']['I00']['fx_n'] == pytest.approx(-4000)
    assert positive['reactions']['I00']['fy_n'] == pytest.approx(-4000 * 2.3 / 5)
    assert positive['reactions']['I01']['fy_n'] == pytest.approx(4000 * 2.3 / 5)
    assert negative['axial_n'] == pytest.approx({member: -force for member, force in positive['axial_n'].items()})
    rows = analyze_bracing(roof, parent.catalog, spec)
    assert rows[0]['max_axial_kn'] > 0
    assert rows[0]['max_ux_mm'] > 0
    assert 'stability' not in roof
    with pytest.raises(ValueError, match='painéis mudou'):
        analyze_bracing(roof, parent.catalog, dict(spec, panels=14))
