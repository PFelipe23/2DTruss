"""Geração de estudos de cobertura e de planos isolados de travamento."""

from copy import deepcopy
from math import ceil, hypot, isclose, isfinite

from .engine import run_project
from .model import make_model
from .search import suggest_geometry


def roof_project(template, *, name, geometry, roofing, actions):
    """Cria um projeto novo com intensidades informadas e casos separados."""
    project = {
        'schema': 'poe-truss-python/v1',
        'name': name.strip() or 'Estudo de cobertura',
        'geometry': dict(geometry),
        'material': deepcopy(template['material']),
        'sections': deepcopy(template['sections']),
        'roofing': dict(roofing),
        'load_patterns': [],
        'load_cases': [],
        'combinations': [],
    }
    patterns = project['load_patterns']
    if actions['self_weight']:
        patterns.append({'id': 'G1', 'name': 'Peso próprio da treliça',
                         'kind': 'self_weight', 'action_class': 'permanent'})
    rows = [
        ('G2', 'Telha', roofing['mass_kg_m2'], 'kgf', 'permanent', 'roof_surface', 'down'),
        ('G3', 'Acessórios da cobertura', actions['additional'], 'kN', 'permanent', 'projected', 'down'),
        ('Q1', 'Sobrecarga de cobertura', actions['live'], 'kN', 'variable', 'projected', 'down'),
        ('W_PRESS', 'Vento normal de pressão', actions['pressure'], 'kN', 'wind', 'roof_surface', 'inward_normal'),
        ('W_SUCC', 'Vento normal de sucção', actions['suction'], 'kN', 'wind', 'roof_surface', 'outward_normal'),
    ]
    for key, label, intensity, unit, action_class, basis, direction in rows:
        if not isfinite(intensity) or intensity < 0:
            raise ValueError(f'{label}: informe uma intensidade finita e não negativa.')
        if intensity or key == 'G2':
            patterns.append({'id': key, 'name': label, 'kind': 'surface',
                             'value': intensity, 'force_unit': unit, 'action_class': action_class,
                             'application': 'top', 'basis': basis, 'direction': direction, 'zone': 'all'})
    gravity = {}
    for pattern in patterns:
        identifier = pattern['id']
        case_id = f'CASO_{identifier}'
        project['load_cases'].append({'id': case_id, 'kind': 'static',
                                      'name': pattern['name'], 'patterns': {identifier: 1}})
        if pattern['action_class'] != 'wind':
            gravity[case_id] = 1
    project['combinations'].append({
        'id': 'REF_GRAV',
        'name': 'Referência de busca · G + Q informados',
        'combination_class': 'manual',
        'factors': gravity,
    })
    return project


def roof_alternatives(project, catalog, *, height_min, height_max, ratio):
    """Posiciona a grade de busca perto do passo real de apoio exigido pela telha."""
    geometry = project['geometry']
    span, rise, step = (geometry[key] for key in ('span_m', 'rise_m', 'purlin_max_m'))
    if not all(isfinite(x) and x > 0 for x in (span, step)) or not isfinite(rise) or rise < 0:
        raise ValueError('Confira o vão, o desnível e o passo máximo das terças.')
    shape = geometry['roof_shape']
    if shape == 'gable':
        target = 2 * ceil(hypot(span / 2, rise) / step)
    elif shape == 'trapezoid':
        target = ceil(hypot(span, rise / .30) / step)
    else:
        target = ceil((hypot(span, rise) if shape == 'single' else span) / step)
    target = max(2, min(40, target))
    return suggest_geometry(project, catalog, {
        'case': 'REF_GRAV', 'flecha_rel': ratio,
        'panel_min': max(2, target - 2), 'panel_max': min(40, target + 4),
        'height_min_m': height_min, 'height_max_m': height_max, 'height_step_m': .1,
    })


def bracing_stations(project, catalog):
    """Pares de nós alinhados verticalmente no modelo atual da treliça."""
    model = make_model(project, catalog)
    if model.shape == 'explicit':
        raise ValueError('Os planos do assistente usam estações de uma treliça paramétrica.')
    points = model.node_map()
    stations = {}
    for index in range(model.panels + 1):
        lower, upper = points[f'B{index:02d}'], points[f'T{index:02d}']
        if isclose(lower.x, upper.x, abs_tol=1e-6):
            stations[lower.id] = {'lower': lower.id, 'upper': upper.id,
                                  'x_mm': lower.x, 'height_mm': upper.y - lower.y}
    return stations


def bracing_plane(roof, station, specification):
    """Gera plano vertical em X com barras axiais bilaterais e apoios declarados."""
    bays = specification['bays']
    area = specification['area_mm2']
    force = specification['force_kn']
    spacing = roof['geometry']['frame_spacing_m']
    height = station['height_mm']
    if type(bays) is not int or not 1 <= bays <= 12:
        raise ValueError('Informe de 1 a 12 vãos entre treliças.')
    if not all(isfinite(x) and x > 0 for x in (area, spacing, height, force)):
        raise ValueError('Confira a área, a altura, o espaçamento e a força de travamento.')
    nodes, members = [], []
    for index in range(bays + 1):
        x = index * spacing * 1000
        for prefix, y in [('I', 0), ('S', height)]:
            nodes.append({'id': f'{prefix}{index:02d}', 'x_mm': x, 'y_mm': y})

    def bar(start, end, group):
        members.append({'id': f'M{len(members)+1:03d}', 'i': start, 'j': end,
                        'group': group, 'area_mm2': area, 'profile': 'Área declarada'})

    for index in range(bays + 1):
        i, j = f'{index:02d}', f'{index+1:02d}'
        bar('I' + i, 'S' + i, 'montante')
        if index < bays:
            bar('I' + i, 'I' + j, 'inferior')
            bar('S' + i, 'S' + j, 'superior')
            bar('I' + i, 'S' + j, 'diagonal')
            bar('I' + j, 'S' + i, 'diagonal')
    actions = []
    for direction, factor in [('POS', 1), ('NEG', -1)]:
        actions.append({
            'id': f'H_{direction}', 'kind': 'nodal',
            'name': f'Ação horizontal {direction} informada',
            'loads': [{'node': f'S{i:02d}', 'fx': force * factor, 'fy': 0, 'force_unit': 'kN'}
                      for i in range(bays + 1)],
        })
    return {
        'schema': 'poe-truss-python/v1',
        'name': f"Travamento transversal {station['lower']}–{station['upper']}",
        'material': deepcopy(roof['material']),
        'geometry': {'frame_spacing_m': spacing},
        'model_override': {
            'nodes': nodes, 'members': members,
            'supports': [{'node': 'I00', 'ux': True, 'uy': True},
                         {'node': f'I{bays:02d}', 'ux': False, 'uy': True}],
        },
        'load_cases': actions,
        'combinations': [],
        'bracing_origin': {'station': dict(station), 'reference': specification.get('reference', ''),
                           'scheme': 'Plano vertical isolado em X, barras bilaterais e apoios extremos XY/Y'},
    }


def analyze_bracing(roof, catalog, specification):
    stations = bracing_stations(roof, catalog)
    if roof['geometry']['panels'] != specification['panels']:
        raise ValueError('O número de painéis mudou. Revise as estações de travamento.')
    rows = []
    for station_id in specification['stations']:
        if station_id not in stations:
            raise ValueError(f'A estação {station_id} perdeu o alinhamento entre os banzos.')
        station = stations[station_id]
        project = bracing_plane(roof, station, specification)
        result = run_project(project, catalog)
        analyses = result['analyses'].values()
        rows.append({'station': station,
                     'max_axial_kn': max(abs(n) for a in analyses for n in a['axial_n'].values()) / 1000,
                     'max_ux_mm': max(abs(d['ux_mm']) for a in analyses
                                      for d in a['nodal_displacements'].values())})
    return rows
