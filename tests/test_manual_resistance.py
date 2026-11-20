from dataclasses import replace

import pytest

from desktop.bridge import Session
from desktop.manual_resistance import resistance_rows, update_manual_resistances
from poe_truss.model import Member, Model, Node


def test_reference_length_covers_shorter_matching_members_only():
    catalog = Session().catalog
    profile = catalog['Ue 150x60x20x3,00']
    members = [
        Member('L', 'A', 'B', 'diagonal', profile.name, profile.area_mm2, profile.mass_kg_m),
        Member('S', 'B', 'C', 'diagonal', profile.name, profile.area_mm2, profile.mass_kg_m),
    ]
    model = Model([Node('A', 0, 0), Node('B', 2500, 0), Node('C', 4750, 0)],
                  members, {}, 4750, 1000, 'explicit', '', 2)
    project = {'stability': {'groups': {'diagonal': {
        'axis_in_plane': 'x', 'axis_out_of_plane': 'y', 'unbraced_out_of_plane_mm': 2500,
        'torsion_unbraced_mm': 2500, 'restraint_reference': 'Detalhe T1',
    }}}}

    def compression(doc, structure):
        return [row for row in resistance_rows(doc, structure, catalog) if row['kind'] == 'compression']

    group, = compression(project, model)
    assert group['members'] == ['L', 'S']
    assert group['length_mm'] == 2500
    with pytest.raises(ValueError, match='comprimento-limite'):
        update_manual_resistances(project, [(group, 2250, 30_000)], 'Memorial T1')
    saved = update_manual_resistances(project, [(group, 2500, 30_000)], 'Memorial T1')
    reread, = compression(saved, model)
    assert reread['rule']['resistance_n'] == 30_000
    assert reread['members'] == ['L', 'S']
    stretched = replace(model, nodes=[*model.nodes[:2], Node('C', 5100, 0)])
    rows = compression(saved, stretched)
    assert [(row['members'], bool(row['rule'])) for row in rows] == [(['S'], False), (['L'], True)]
    saved['stability']['groups']['diagonal']['k_out_of_plane'] = 1.2
    changed, = compression(saved, model)
    assert changed['rule'] is None
    saved['stability']['groups']['diagonal'].pop('unbraced_out_of_plane_mm')
    assert [len(row['members']) for row in compression(saved, model)] == [1, 1]
