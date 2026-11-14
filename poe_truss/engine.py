"""Orquestra geração do modelo, casos, combinações, análise e envoltórias."""
from __future__ import annotations
from math import isfinite
from .model import make_model,geometry_diagnostics
from .loads import build_case_loads,merge_forces,combination_audit
from .stability import resolve_stability
from .sections import section_properties
from .axial import axial_screen
from .camber import suggested_camber
from .solver import LinearTruss
from .version import VERSION


def run_project(project:dict, catalog:dict) -> dict:
    if project.get('schema') not in ('poe-truss-python/v1',None):
        raise ValueError('Schema de projeto incompatível')
    model=make_model(project,catalog)
    E=float(project.get('material',{}).get('E_MPa',200000))
    solver=LinearTruss(model,E)
    sources=project.get('load_cases',[])
    if not sources:raise ValueError('Pelo menos um caso de carregamento é obrigatório')
    ids=set()
    raw={}
    load_audit={}
    case_meta=[]
    for case in sources:
        cid=str(case.get('id','')).strip()
        if not cid or cid in ids:raise ValueError(f'ID de carregamento vazio ou duplicado: {cid}')
        ids.add(cid)
        raw[cid],load_audit[cid]=build_case_loads(model,case)
        case_meta.append({'id':cid,'name':case.get('name',cid),'kind':case.get('kind')})
    combos=project.get('combinations',[])
    identifiers=set(ids)
    combinations={}
    for entry in combos:
        cid=str(entry.get('id','')).strip()
        if not cid or cid in identifiers:raise ValueError('ID de combinação inválido ou duplicado')
        identifiers.add(cid)
        factors=entry.get('factors',{})
        if not factors:raise ValueError(f'Combinação {cid} sem fatores')
        combinations[cid]=factors
    analyses={}
    for cid,force in raw.items():analyses[cid]=solver.analyze(force)
    for cid,factors in combinations.items():
        analyses[cid]=solver.analyze(merge_forces(factors,raw))
        load_audit[cid]=combination_audit(cid,factors,raw)
    candidates=list(combinations.keys()) if combinations else list(raw.keys())
    envelope={}
    for m in model.members:
        values=[(analyses[cid]['axial_n'][m.id],cid) for cid in candidates]
        tensile=max(values,key=lambda v:v[0])
        compressed=min(values,key=lambda v:v[0])
        envelope[m.id]={
            'max_tension_n':max(0.,tensile[0]),
            'max_compression_n':min(0.,compressed[0]),
            'tension_case':tensile[1] if tensile[0]>0 else None,
            'compression_case':compressed[1] if compressed[0]<0 else None,
        }
    criteria=project.get('geometry',{})
    diagnostics=geometry_diagnostics(model,
        angle_min=float(criteria.get('angle_min_deg',45)),angle_max=float(criteria.get('angle_max_deg',60)),
        purlin_max_m=float(criteria.get('purlin_max_m',0)))
    stability=resolve_stability(model,project,catalog)
    section_data=section_properties(model,project,catalog)
    axial_data=axial_screen(project,model.to_dict(),envelope,stability,section_data)
    camber=suggested_camber(project,model.to_dict(),analyses)
    notices=[
        'Análise linear elástica 2D, barras articuladas. Sem ELU resistente, ligações, flambagem ou estabilidade fora do plano.',
        'Cargas transversais entre nós representadas somente por resultantes nodais; flexão local do banzo não avaliada.',
        'Combinações fornecidas pelo usuário. Nenhuma conformidade automática à NBR 8681, NBR 14762 ou NBR 8800.',
        'Massa automática da treliça exclui ligações, chapas, soldas, acabamentos e acessórios.',
        'Convenção de unidades do projeto: 1 kgf = 10 N.',
        'Estabilidade: travamentos declarados não constituem comprovação da estabilidade global ou resistência axial.',
        'v0.1: triagem axial por escoamento bruto e Euler é INFORMATIVA; modos local, distorcional, flexo-torcional e ligações não verificados.',
        'Capacidades externas do DimPerfil são fornecidas pelo usuário; não auditadas internamente.'
    ]
    if not diagnostics['all_roof_steps_within_max']:
        notices.append('Passo entre terças excede o máximo geométrico informado.')
    if diagnostics['angle_preferred_fraction'] is not None and diagnostics['angle_preferred_fraction']<1:
        notices.append('Há diagonais fora do intervalo angular preferencial.')
    if stability['summary']['pending']:
        notices.append(f"Dados de estabilidade pendentes para {stability['summary']['pending']} de {len(model.members)} barras; NÃO equivale a aprovação resistente.")
    if axial_data['summary']['euler_warning']:
        notices.append(f"Triagem Euler: {axial_data['summary']['euler_warning']} barras ultrapassam a carga crítica elástica idealizada.")
    if solver.pivot_ratio>1e9:
        notices.append('Sistema potencialmente mal condicionado: verificar deformações e geometria.')
    return {'schema':'poe-truss-result/v1','engine':'Python stdlib','model':model.to_dict(),
            'load_cases':case_meta,'combinations':[{'id':k,'factors':v} for k,v in combinations.items()],
            'analyses':analyses,'envelope':envelope,'geometry_diagnostics':diagnostics,
            'warnings':notices,'load_audit':load_audit,'stability':stability,
            'section_properties':section_data,'axial_screen':axial_data,'camber':camber,
            'software_version':VERSION,'envelope_source':'combinations' if combinations else 'individual_load_cases'}
