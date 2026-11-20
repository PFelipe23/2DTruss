"""Resistências fornecidas pelo projetista e escopos de reaproveitamento."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from hashlib import sha256
import json
from math import isfinite

from poe_truss.stability import resolve_stability

KINDS = {'tension': 'Tração', 'compression': 'Compressão'}
TOLERANCE_MM = 1e-6


def _conditions(project, model, member, stability, kind, catalog_profile):
    profile = {'name': member.profile, 'area_mm2': member.area, 'mass_kg_m': member.mass,
               'catalog': catalog_profile.as_json() if catalog_profile else None}
    data = {
        'profile': profile, 'group': member.group, 'kind': kind,
        'material': project.get('material', {}) or {},
        'section': project.get('section_arrangements', {}).get(member.group, {}),
        'support_i': list(model.supports.get(member.i, (False, False))),
        'support_j': list(model.supports.get(member.j, (False, False))),
    }
    if catalog_profile is None:
        data['individual_member'] = member.id
    if kind == 'compression':
        fixed = (
            'axis_in_plane', 'axis_out_of_plane', 'k_in_plane', 'k_out_of_plane', 'rotation_deg',
            'unbraced_out_of_plane_mm', 'torsion_unbraced_mm', 'out_of_plane_source',
            'restraint_reference', 'restraint_note',
        )
        data.update((key, stability[key]) for key in fixed)
        length = stability['length_mm']
        in_plane = stability['unbraced_in_plane_mm']
        data['in_plane_length'] = ('member_length' if abs(in_plane - length) <= TOLERANCE_MM else in_plane)
        if (not data['unbraced_out_of_plane_mm'] or not data['torsion_unbraced_mm']
                or data['axis_in_plane'] is None or data['axis_out_of_plane'] is None
                or data['out_of_plane_source'] != 'declared' or not data['restraint_reference']):
            data['individual_member'] = member.id
    return data


def resistance_rows(project, model, catalog, result=None):
    limits = project.get('manual_resistances', [])
    by_scope = defaultdict(list)
    for rule in limits:
        by_scope[rule['scope']].append(rule)
    for rules in by_scope.values():
        rules.sort(key=lambda rule: rule['max_length_mm'])
    stability = resolve_stability(model, project, catalog)['members']
    elu = (result or {}).get('classified_envelopes', {}).get('elu', {})
    groups = {}
    for member in model.members:
        data = stability[member.id]
        length = data['length_mm']
        for kind in KINDS:
            conditions = _conditions(project, model, member, data, kind, catalog.get(member.profile))
            scope = sha256(json.dumps(conditions, sort_keys=True).encode()).hexdigest()
            saved = next((rule for rule in by_scope[scope]
                          if rule['max_length_mm'] + TOLERANCE_MM >= length), None)
            key = (scope, saved['max_length_mm'] if saved else None)
            row = groups.setdefault(key, {
                'scope': scope, 'conditions': conditions, 'profile': member.profile, 'group': member.group,
                'kind': kind, 'members': [], 'length_mm': 0., 'rule': saved,
                'demand_n': 0. if elu else None, 'governing': None,
            })
            row['members'].append(member.id)
            row['length_mm'] = max(row['length_mm'], length)
            if elu:
                extreme = elu[member.id]
                demand = abs(extreme[f'max_{kind}_n'])
                if demand > row['demand_n']:
                    row['demand_n'] = demand
                    row['governing'] = member.id, extreme[f'{kind}_case']
    return sorted(groups.values(), key=lambda row: (row['profile'], row['group'],
                                                    row['kind'], -row['length_mm']))


def update_manual_resistances(project, changes, reference):
    """Aplica somente as linhas editadas e mantém as referências das demais."""
    reference = reference.strip()
    rules = deepcopy(project.get('manual_resistances', []))
    for row, length, resistance in changes:
        if resistance is not None:
            if not reference:
                raise ValueError('Informe a origem da resistência e as condições de ligação e travamento.')
            if not (isfinite(length) and length + TOLERANCE_MM >= row['length_mm']):
                raise ValueError(f'{row["profile"]}: o comprimento-limite deve cobrir todas as barras da linha.')
            if not isfinite(resistance) or resistance <= 0:
                raise ValueError('A resistência deve ser positiva.')
        old = row['rule']
        if old:
            rules.remove(old)
        if resistance is not None:
            scope = row['scope']
            if any(rule['scope'] == scope and abs(rule['max_length_mm'] - length) <= TOLERANCE_MM
                   for rule in rules):
                raise ValueError(f'{row["profile"]}: já existe uma resistência para esse comprimento-limite.')
            rules.append({'scope': scope, 'conditions': row['conditions'], 'max_length_mm': length,
                          'resistance_n': resistance, 'reference': reference})
    updated = deepcopy(project)
    updated['manual_resistances'] = rules
    return updated
