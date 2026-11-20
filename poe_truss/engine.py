"""Orquestra geração do modelo, casos, combinações, análise e envoltórias."""
from __future__ import annotations
from math import isfinite
from .model import make_model,geometry_diagnostics
from .loads import load_patterns,resolve_case_loads,merge_forces,combination_audit
from .stability import resolve_stability
from .sections import section_properties
from .axial import axial_screen
from .camber import suggested_camber
from .solver import LinearTruss
from .version import VERSION

COMBINATION_SCOPES = {
    'elu': ('uls_normal', 'uls_special', 'uls_exceptional'),
    'els': ('sls_rare', 'sls_frequent', 'sls_quasi'),
}


def axial_envelope(members, analyses, candidates):
    if not candidates:
        return {}
    envelope = {}
    for member in members:
        values = [(analyses[case]['axial_n'][member.id], case) for case in candidates]
        tension, tension_case = max(values, key=lambda entry: entry[0])
        compression, compression_case = min(values, key=lambda entry: entry[0])
        envelope[member.id] = {
            'max_tension_n': max(0., tension), 'max_compression_n': min(0., compression),
            'tension_case': tension_case if tension > 0 else None,
            'compression_case': compression_case if compression < 0 else None,
        }
    return envelope


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
    definitions = load_patterns(project)
    patterns = {pattern['id']: pattern for pattern in definitions}
    if len(patterns) != len(definitions):
        raise ValueError('ID de padrão de carga duplicado')
    ids.update(pattern['id'] for pattern in project.get('load_patterns', []))
    pattern_cache = {}
    for case in sources:
        cid=str(case.get('id','')).strip()
        if not cid or cid in ids:raise ValueError(f'ID de carregamento vazio ou duplicado: {cid}')
        ids.add(cid)
        if cid in pattern_cache:
            raw[cid],load_audit[cid] = pattern_cache[cid]
        else:
            raw[cid],load_audit[cid] = resolve_case_loads(model, case, patterns, cache=pattern_cache)
            if case['kind'] != 'static':
                pattern_cache[cid] = raw[cid], load_audit[cid]
        meta = {'id': cid, 'name': case.get('name', cid), 'kind': case.get('kind')}
        if case['kind'] == 'static':
            meta['patterns'] = dict(case['patterns'])
        if 'action_class' in case:
            meta['action_class'] = case['action_class']
        case_meta.append(meta)
    combos=project.get('combinations',[])
    identifiers=set(ids)
    combinations={}
    combination_meta = []
    for entry in combos:
        cid=str(entry.get('id','')).strip()
        if not cid or cid in identifiers:raise ValueError('ID de combinação inválido ou duplicado')
        identifiers.add(cid)
        factors=entry.get('factors',{})
        if not factors:raise ValueError(f'Combinação {cid} sem fatores')
        combinations[cid]=factors
        meta = {'id': cid, 'factors': factors}
        if 'combination_class' in entry:
            meta['combination_class'] = entry['combination_class']
        combination_meta.append(meta)
    analyses={}
    for cid,force in raw.items():analyses[cid]=solver.analyze(force)
    for cid,factors in combinations.items():
        analyses[cid]=solver.analyze(merge_forces(factors,raw))
        load_audit[cid]=combination_audit(cid,factors,raw)
    candidates=list(combinations.keys()) if combinations else list(raw.keys())
    envelope = axial_envelope(model.members, analyses, candidates)
    classified = {
        scope: [entry['id'] for entry in combination_meta
                if entry.get('combination_class') in classes]
        for scope, classes in COMBINATION_SCOPES.items()
    }
    envelopes = {scope: axial_envelope(model.members, analyses, ids)
                 for scope, ids in classified.items()}
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
            'load_cases':case_meta,'combinations':combination_meta,
            'analyses':analyses,'envelope':envelope,'classified_envelopes':envelopes,
            'envelope_combinations':classified,'geometry_diagnostics':diagnostics,
            'warnings':notices,'load_audit':load_audit,'stability':stability,
            'section_properties':section_data,'axial_screen':axial_data,'camber':camber,
            'software_version':VERSION,'envelope_source':'combinations' if combinations else 'individual_load_cases'}
