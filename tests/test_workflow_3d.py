"""Regras de negócio do desktop integrado + geometria 3D sem Qt."""
import math
import pytest
from copy import deepcopy
from desktop.bridge import Session
from desktop import workflow, editing
from desktop.preview3d import Camera,project,member_prism,prism_faces,color_key,palette_keys


def test_update_section_rebuilds_mass_and_invalidates_external():
    ses=Session();p=deepcopy(ses.project)
    p['external_resistances']={'members':{}}
    group='diagonal';profile=next(iter(ses.catalog))
    pp=workflow.update_section(p,ses.model,ses.catalog,group,profile,2)
    assert 'external_resistances' not in pp
    assert pp['sections'][group]=={'profile':profile,'count':2}
    ses.update_project(pp)
    assert all(abs(m.area-2*ses.catalog[profile].area_mm2)<1e-9 for m in ses.model.members if m.group==group)


def test_update_section_explicit_cad_consistent():
    ses=Session();p=editing.materialize(ses.project,ses.model)
    prof=next(iter(ses.catalog))
    nextp=workflow.update_section(p,ses.model,ses.catalog,'superior',prof,2)
    ses.update_project(nextp)
    for m in ses.model.members:
        if m.group=='superior':
            assert m.profile==prof
            assert m.mass==pytest.approx(2*ses.catalog[prof].mass_kg_m)


def test_surface_and_wind_parameters_preserve_direction():
    ses=Session()
    p=workflow.update_load_case(ses.project,'W_UP',name='Sucção esquerda',kind='surface',
        value=300,force_unit='kgf',application='top',basis='roof_surface',
        direction='outward_normal',zone='left')
    ses.update_project(p)
    r=ses.calculate()
    a=r['load_audit']['W_UP']
    assert a['n_entries']>0
    assert a['residual']['fx_n']==pytest.approx(0,abs=1e-8)
    assert a['residual']['fy_n']==pytest.approx(0,abs=1e-8)
    assert any(c['zone']=='left' for c in ses.project['load_cases'] if c['id']=='W_UP')


def test_combination_factors_negative_preserved():
    ses=Session()
    p=workflow.update_combination(ses.project,'S_SUCC',{'G1':1.3,'W_UP':-1.2})
    ses.update_project(p)
    assert ses.project['combinations'][1]['factors']['W_UP']==pytest.approx(-1.2)
    forces=ses.forces_for_case('S_SUCC')
    assert all(len(v)==2 for v in forces.values())
    assert ses.calculate()['analyses']['S_SUCC']['axial_n']


def test_empty_combination_rejected():
    ses=Session()
    with pytest.raises(ValueError):workflow.update_combination(ses.project,'S_GRAV',{'G1':0})


def test_case_used_in_combo_cannot_be_deleted():
    ses=Session()
    with pytest.raises(ValueError):workflow.delete_load_case(ses.project,'G1')


def test_update_stability_requires_valid_axes():
    ses=Session()
    with pytest.raises(ValueError):workflow.update_stability_group(ses.project,'superior',axis_in='z')
    p=workflow.update_stability_group(ses.project,'superior',lateral_mm=4000,
        inplane_mm=1000,torsion_mm=4000,kin=1,kout=1,reference='Premissa para estudo, a verificar')
    ses.update_project(p)
    r=ses.calculate()
    assert any(v['unbraced_out_of_plane_mm']==4000 for v in r['stability']['members'].values() if v['group']=='superior')
    assert all(v['resistance_verified'] is False for v in r['stability']['members'].values())


def test_diagnostics_do_not_issue_elu_approval():
    ses=Session();ses.calculate()
    issues=workflow.project_diagnostics(ses.project,ses.model,ses.result)
    assert any(x['level']=='pendência' and 'ELU' in x['message'] for x in issues)
    assert not any('APROVADO' in x['message'] for x in issues)


def test_3d_project_is_deterministic_and_finite():
    p=project((1000,200,60),Camera(30,22))
    assert len(p)==3 and all(math.isfinite(x) for x in p)
    assert p==project((1000,200,60),Camera(30,22))


def test_3d_prisms_have_six_faces_and_preserve_length():
    points=member_prism((0,0),(3000,4000),thickness=50,depth=120)
    assert len(points)==8
    faces=prism_faces(points)
    assert len(faces)==6 and all(len(x)==4 for x in faces)
    with pytest.raises(ValueError):member_prism((0,0),(0,0))


def test_3d_color_modes_group_family_force():
    ses=Session();m=ses.model.members[0]
    assert color_key(m,ses.catalog,'group')==m.group
    assert color_key(m,ses.catalog,'family')==ses.catalog[m.profile].family
    assert color_key(m,ses.catalog,'force',{m.id:-300})=='Compressão'
    assert color_key(m,ses.catalog,'force',{m.id:200})=='Tração'
    assert palette_keys(ses.model,ses.catalog,'family')


def test_3d_projection_rejects_non_finite():
    with pytest.raises(ValueError):project((float('nan'),1,0),Camera())


def test_roof_registration_updates_load_and_purlin_step():
    ses=Session()
    p=workflow.update_roof(ses.project,'Fabricante declarado','Telha sanduíche X',12.5,1.15)
    ses.update_project(p)
    assert ses.project['roofing']['mass_kg_m2']==12.5
    assert ses.project['geometry']['purlin_max_m']==1.15
    case=next(x for x in ses.project['load_cases'] if x['id']=='G2')
    assert case['value']==12.5 and case['force_unit']=='kgf'
    assert ses.calculate()['load_audit']['G2']['n_entries']>0
    with pytest.raises(ValueError):workflow.update_roof(ses.project,'','X',12,1.0)


def test_update_load_case_rejects_illegal_direction():
    ses=Session()
    with pytest.raises(ValueError):workflow.update_load_case(ses.project,'W_UP',name='W',kind='surface',direction='diagonal_global')
