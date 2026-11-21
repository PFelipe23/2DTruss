"""Geração de estudos de cobertura e de planos isolados de travamento."""

from copy import deepcopy
from math import ceil, hypot, isclose, isfinite, pi

from .engine import run_project
from .loads import merge_forces, resolve_case_loads
from .model import GROUPS, MEMBER_PREFIX, make_model
from .search import suggest_geometry
from .solver import LinearTruss

STUDY_LOADS = (
    ('G2', 'Peso Próprio de Telha', 6., 'roof_surface'),
    ('G3', 'Peso Próprio de Terças', 6., 'projected'),
    ('G4', 'Peso Próprio de Estabilizadores', 1., 'projected'),
    ('G5', 'Peso Próprio de Utilidades', 10., 'projected'),
    ('Q1', 'Sobrecarga', 25., 'projected'),
)


def preliminary_roof_project(template, *, name, geometry, intensities):
    """Monta ações provisórias, em kgf/m², para a pesquisa de candidatos."""
    project = roof_project(template, name=name, geometry=geometry, roofing={'mass_kg_m2': 0},
                           actions=dict(self_weight=True, additional=0, live=0, pressure=0, suction=0))
    project.pop('roofing')
    patterns = project['load_patterns'][:1]
    for identifier, caption, default, basis in STUDY_LOADS:
        value = intensities.get(identifier, default)
        if not isfinite(value) or value < 0:
            raise ValueError(f'{caption}: intensidade inválida.')
        patterns.append(dict(id=identifier, name=caption, kind='surface', value=value,
                             force_unit='kgf', application='top', direction='down', basis=basis,
                             action_class='variable' if identifier == 'Q1' else 'permanent'))
    project['load_patterns'] = patterns
    project['load_cases'] = [dict(id=f'CASO_{p["id"]}', kind='static', patterns={p['id']: 1}) for p in patterns]
    gravity = {c['id']: 1 for c in project['load_cases']}
    project['combinations'] = [
        dict(id='REF_GRAV', factors=gravity, combination_class='manual'),
        dict(id='REF_PONDERADA', factors={key: 1.50 if key == 'CASO_Q1' else 1.25 for key in gravity},
             combination_class='manual'),
    ]
    project['geometry']['member_ids'] = 'group'
    return project


def light_sections(project, catalog, limit_mm):
    """Explora os perfis simples disponíveis nas famílias de origem."""
    source = deepcopy(project)
    groups = source['sections']
    options = {}
    for group in GROUPS:
        family = catalog[groups[group]['profile']].family
        options[group] = sorted((p.name for p in catalog.values() if p.family == family),
                                key=lambda name: (catalog[name].mass_kg_m, -catalog[name].area_mm2))
    patterns = {p['id']: p for p in source['load_patterns']}
    service, weighted = (c['factors'] for c in source['combinations'])
    tested = {}

    def evaluate(names, include_weighted=False):
        if names in tested and not include_weighted:
            return tested[names]
        source['sections'] = {group: {'profile': name, 'count': 1} for group, name in zip(GROUPS, names)}
        model = make_model(source, catalog)
        solver = LinearTruss(model, source['material'].get('E_MPa', 200000))
        cache = {}
        forces = {case['id']: resolve_case_loads(model, case, patterns, cache=cache)[0]
                  for case in source['load_cases']}
        service_result = solver.analyze(merge_forces(service, forces))
        record = abs(service_result['max_abs_roof_mm']), model.mass_kg()
        tested[names] = record
        if include_weighted:
            axial = solver.analyze(merge_forces(weighted, forces))['axial_n']
            return record, max(map(abs, axial.values())) / 1000
        return record

    minimum = tuple(options[group][0] for group in GROUPS)
    if evaluate(minimum)[0] <= limit_mm:
        (displacement, mass), axial = evaluate(minimum, include_weighted=True)
        return source['sections'], displacement, mass, axial

    seeds = {tuple(options[g][min(i, len(options[g]) - 1)] for g in GROUPS)
             for i in range(max(map(len, options.values())))}
    seeds.add(tuple(groups[g]['profile'] for g in GROUPS))
    def rank(names):
        displacement, mass = evaluate(names)
        return (False, mass, displacement, names) if displacement <= limit_mm else (True, displacement, mass, names)

    best = min(seeds, key=rank)
    for _ in range(2):
        for index, group in enumerate(GROUPS):
            best = min((best[:index] + (name,) + best[index+1:] for name in options[group]), key=rank)
    (displacement, mass), axial = evaluate(best, include_weighted=True)
    return source['sections'], displacement, mass, axial


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


def roof_alternatives(project, catalog, *, height_min, height_max, ratio, size_profiles=False):
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
    outcome = suggest_geometry(project, catalog, {
        'case': 'REF_GRAV', 'flecha_rel': ratio,
        'panel_min': max(2, target - 2), 'panel_max': min(40, target + 4),
        'height_min_m': height_min, 'height_max_m': height_max, 'height_step_m': .1,
    })
    if size_profiles:
        for row in outcome['candidates']:
            candidate = deepcopy(project)
            candidate['geometry'].update(panels=row['panels'], height_m=row['height_m'])
            sections, displacement, mass, axial = light_sections(candidate, catalog, row['displacement_limit_mm'])
            row.update(sections=sections, max_abs_roof_mm=displacement, mass_kg=mass, max_design_axial_kn=axial,
                       displacement_ok=displacement <= row['displacement_limit_mm'],
                       meets_geometric_service_criteria=row['purlin_ok'] and displacement <= row['displacement_limit_mm'])
        outcome['candidates'].sort(key=lambda row: (
            not row['meets_geometric_service_criteria'], not row['purlin_ok'], row['mass_kg'], row['max_abs_roof_mm']))
    return outcome



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


def chord_bracing_planes(roof, catalog):
    model = make_model(roof, catalog)
    half_span = model.span_mm / 2
    points = model.node_map()
    spans = {}
    for group, prefix in [('superior', 'BS'), ('inferior', 'BI')]:
        sides = {'E': 0., 'D': 0.} if model.shape == 'gable' else {'': 0.}
        for member in model.members:
            if member.group != group:
                continue
            x = (points[member.i].x + points[member.j].x) / 2
            side = ('E' if x <= half_span else 'D') if model.shape == 'gable' else ''
            sides[side] += model.member_length(member)
        for side, width in sides.items():
            spans[f'{prefix}-{side}' if side else prefix] = width
    return spans


def chord_bracing_project(roof, key, width, specification):
    """Gera uma faixa do banzo com dois cordões longitudinais e diagonais cruzadas."""
    bays = specification['bays']
    area, diameter, force = (specification[k] for k in ('area_mm2', 'diameter_mm', 'force_kn'))
    spacing = roof['geometry']['frame_spacing_m']
    if bays not in (2, 3) or not all(isfinite(x) and x > 0 for x in (area, diameter, force, spacing, width)):
        raise ValueError('Informe 2 ou 3 módulos e valores positivos de força, área e bitola.')
    nodes, members = [], []
    for index in range(bays + 1):
        for prefix, y in (('I', 0.), ('S', width)):
            nodes.append(dict(id=f'{prefix}{index:02d}', x_mm=index * spacing * 1000, y_mm=y))

    def add(a, b, group, index, *, diagonal=False):
        members.append(dict(id=f'{MEMBER_PREFIX[group]}{index:03d}', i=a, j=b, group=group,
                            area_mm2=pi * diameter ** 2 / 4 if diagonal else area,
                            profile=f'Barra redonda Ø{diameter:g} mm' if diagonal else 'Área declarada',
                            tension_only=group != 'montante'))

    # Índices crescentes nas bordas. O cruzamento das diagonais não cria nó.
    for index in range(bays + 1):
        i, j = f'{index:02d}', f'{index+1:02d}'
        add('I' + i, 'S' + i, 'montante', index + 1)
        if index < bays:
            add('I' + i, 'I' + j, 'inferior', index + 1)
            add('S' + i, 'S' + j, 'superior', index + 1)
            add('I' + i, 'S' + j, 'diagonal', 2 * index + 1, diagonal=True)
            add('S' + i, 'I' + j, 'diagonal', 2 * index + 2, diagonal=True)
    return {
        'schema': 'poe-truss-python/v1', 'name': f'Travamento no plano {key}',
        'material': deepcopy(roof['material']), 'geometry': {'frame_spacing_m': spacing},
        'model_override': {'nodes': nodes, 'members': members, 'supports': [
            dict(node=f'{prefix}{i:02d}', ux=True, uy=True)
            for i in (0, bays) for prefix in ('I', 'S')
        ]},
        'load_cases': [
            dict(id=case, kind='nodal', name=f'Ação horizontal {case}', loads=[
                dict(node=f'S{i:02d}', fx=force * sign, fy=0, force_unit='kN') for i in range(1, bays)
            ]) for case, sign in (('H_POS', 1), ('H_NEG', -1))
        ],
        'combinations': [],
        'bracing_origin': {'station': {'lower': key, 'height_mm': width},
                           'reference': specification.get('reference', ''),
                           'scheme': 'Faixa no plano do banzo, quatro apoios de canto, cordões e diagonais somente à tração'},
    }
