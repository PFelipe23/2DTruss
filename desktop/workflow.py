"""Contratos de edição do fluxo de trabalho, independentes de Qt.

Não realiza dimensionamento resistente. Todas as funções retornam NOVO JSON,
validado posteriormente por Session.update_project (modelo/solver existentes).
"""
from __future__ import annotations
from copy import deepcopy
from math import isfinite
from poe_truss.materials import STEEL_GRADES
from poe_truss.loads import load_patterns
from poe_truss.model import GROUPS
from poe_truss.units import FORCE_TO_N

LOAD_KINDS = ('self_weight','surface','line','nodal')
DIRECTIONS = ('down','up','outward_normal','inward_normal','right','left')
ACTION_CLASSES = {
    'permanent': 'Permanente (G)',
    'variable': 'Variável (Q)',
    'wind': 'Vento (W)',
    'exceptional': 'Excepcional',
    'unspecified': 'A classificar',
}
COMBINATION_CLASSES = {
    'manual': 'Sem classificação',
    'uls_normal': 'ELU normal',
    'uls_special': 'ELU especial ou de construção',
    'uls_exceptional': 'ELU excepcional',
    'sls_rare': 'ELS rara',
    'sls_frequent': 'ELS frequente',
    'sls_quasi': 'ELS quase permanente',
}


def pattern_class(pattern):
    return pattern.get('action_class', 'permanent' if pattern['kind'] == 'self_weight'
                       else 'unspecified')


def _new_load_id(project, identifier):
    identifier = str(identifier).strip()
    ids = {row['id'] for key in ('load_patterns', 'load_cases', 'combinations')
           for row in project.get(key, [])}
    if not 1 <= len(identifier) <= 32 or not identifier.replace('_', '').isalnum() or identifier in ids:
        raise ValueError('ID vazio, duplicado ou inválido')
    return identifier


def _factors(factors, valid):
    if set(factors) - valid:
        raise ValueError('Um dos fatores referencia um identificador inexistente')
    numeric = {key: float(value) for key, value in factors.items()}
    numeric = {key: value for key, value in numeric.items() if value != 0}
    if not numeric or not all(isfinite(value) for value in numeric.values()):
        raise ValueError('Informe ao menos um fator finito não nulo')
    return numeric


def _nonnegative(value,name):
    try: x=float(value)
    except (TypeError,ValueError): raise ValueError(f'{name}: informe número') from None
    if not isfinite(x) or x<0: raise ValueError(f'{name}: deve ser não negativo e finito')
    return x


def update_section(project, model, catalog, group, profile, count):
    if group not in GROUPS or profile not in catalog or int(count) not in (1,2):
        raise ValueError('Família, perfil ou número de componentes inválido')
    p=deepcopy(project)
    p.setdefault('sections',{})[group]={'profile':profile,'count':int(count)}
    # Modelos CAD têm propriedades por barra, que devem ser sincronizadas.
    if 'model_override' in p:
        item=catalog[profile]
        for m in p['model_override']['members']:
            if m['group']==group:
                m.update(profile=profile,area_mm2=item.area_mm2*count,mass_kg_m=item.mass_kg_m*count)
    p.pop('external_resistances',None)
    p.setdefault('stability',{}).pop('members',None) # não reutilizar K/L da seção antiga
    return p


def update_steel(project, grade_id):
    grade = STEEL_GRADES[grade_id]
    updated = deepcopy(project)
    updated.setdefault('material', {}).update(
        grade_id=grade_id, standard=grade.standard, E_MPa=grade.E,
        fy_MPa=grade.fy, fu_MPa=grade.fu, source=grade.source,
    )
    updated.pop('external_resistances', None)
    return updated


def update_nodal_loads(project, model, case_id, node_ids, fx, fy, force_unit, index=None):
    """Insere uma parcela por nó ou substitui uma única linha existente."""
    targets = list(dict.fromkeys(node_ids))
    valid_nodes = model.node_map()
    if not targets or any(node not in valid_nodes for node in targets):
        raise ValueError('Selecione nós conectados ao modelo.')
    if force_unit not in FORCE_TO_N or not all(isfinite(value) for value in (fx, fy)):
        raise ValueError('Verifique a unidade e as componentes da força.')

    updated = deepcopy(project)
    case = next((entry for entry in load_patterns(updated) if entry['id'] == case_id), None)
    if case is None or case['kind'] != 'nodal':
        raise ValueError('Caso nodal não encontrado')
    rows = case.setdefault('loads', [])
    additions = [{'node': node, 'fx': fx, 'fy': fy, 'force_unit': force_unit} for node in targets]
    if index is None:
        rows.extend(additions)
    elif len(targets) == 1 and 0 <= index < len(rows):
        rows[index] = {**rows[index], **additions[0]}
    else:
        raise IndexError('Índice da força nodal inexistente')
    return updated


def update_load_case(project, case_id, *, name, kind, value=0, force_unit='kgf',
                     application='top', basis='projected', direction='down', zone='all',
                     action_class=None):
    p=deepcopy(project)
    c=next((x for x in load_patterns(p) if x['id']==case_id),None)
    if c is None:raise ValueError('Caso inexistente')
    if kind not in LOAD_KINDS:raise ValueError('Tipo de ação inválido')
    if force_unit not in ('kgf','kN','tf','N'):raise ValueError('Unidade de força inválida')
    if direction not in DIRECTIONS:raise ValueError('Direção inválida')
    if application not in ('top','bottom') or basis not in ('projected','roof_surface'):
        raise ValueError('Aplicação/base inválida')
    if zone not in ('all','left','right'):raise ValueError('Zona inválida')
    c['name']=str(name).strip() or case_id
    if c.get('kind')!=kind:
        if c.get('kind')=='nodal' and c.get('loads'):
            raise ValueError('Apague as cargas nodais antes de trocar o tipo de caso')
        c.clear();c.update(id=case_id,name=str(name).strip() or case_id,kind=kind)
    if kind in ('surface','line'):
        c.update(value=_nonnegative(value,'Intensidade'),force_unit=force_unit,
                 application=application,basis=basis,direction=direction,zone=zone)
    if kind=='nodal':c.setdefault('loads',[])
    if action_class is not None:
        if action_class not in ACTION_CLASSES or (kind == 'self_weight' and action_class != 'permanent'):
            raise ValueError('Classificação de ação incompatível')
        c['action_class'] = action_class
    return p


def add_load_case(project, case_id, kind='surface', *, pattern_only=False):
    case_id = _new_load_id(project, case_id)
    if kind not in LOAD_KINDS:
        raise ValueError('Tipo de ação inválido')
    p=deepcopy(project)
    key = 'load_patterns' if pattern_only else 'load_cases'
    p.setdefault(key,[]).append({'id':case_id,'name':case_id,'kind':kind,
        **({'loads':[]} if kind=='nodal' else {}),
        **({'value':0.,'force_unit':'kgf','application':'top','basis':'projected',
            'direction':'down','zone':'all'} if kind in ('surface','line') else {})})
    return p


def delete_load_case(project,case_id):
    p=deepcopy(project)
    if any(case_id in c.get('patterns', {}) for c in p.get('load_cases', [])):
        raise ValueError('Padrão usado em caso estático. Remova o fator antes de excluir.')
    if any(case_id in c.get('factors',{}) for c in p.get('combinations',[])):
        raise ValueError('Caso usado em combinação: remova o fator antes de excluir o caso')
    if any(c['id'] == case_id for c in p.get('load_patterns', [])):
        p['load_patterns'] = [c for c in p['load_patterns'] if c['id'] != case_id]
        return p
    if not any(c['id']==case_id for c in p.get('load_cases',[])):raise ValueError('Caso inexistente')
    p['load_cases']=[c for c in p['load_cases'] if c['id']!=case_id]
    return p


def update_static_case(project, case_id, name, factors, *, create=False):
    p = deepcopy(project)
    numeric = _factors(factors, {row['id'] for row in load_patterns(p)})
    if create:
        case_id = _new_load_id(p, case_id)
        case = {'id': case_id, 'kind': 'static'}
        p.setdefault('load_cases', []).append(case)
    else:
        case = next((row for row in p.get('load_cases', [])
                     if row['id'] == case_id and row['kind'] == 'static'), None)
        if case is None:
            raise ValueError('Caso estático inexistente')
    case.update(name=str(name).strip() or case_id, patterns=numeric)
    return p


def update_combination(project,combo_id,factors,combination_class=None):
    p=deepcopy(project)
    c=next((r for r in p.get('combinations',[]) if r['id']==combo_id),None)
    if c is None:raise ValueError('Combinação inexistente')
    valid={x['id'] for x in p.get('load_cases',[])}
    c['factors'] = _factors(factors, valid)
    if combination_class is not None:
        if combination_class not in COMBINATION_CLASSES:
            raise ValueError('Classificação de combinação inválida')
        c['combination_class'] = combination_class
    return p


def add_combination(project, combo_id):
    combo_id = _new_load_id(project, combo_id)
    cases=project.get('load_cases',[])
    if not cases:raise ValueError('Cadastre um caso de carregamento primeiro')
    p=deepcopy(project)
    p.setdefault('combinations',[]).append({'id':combo_id,'name':combo_id,
                                             'factors':{cases[0]['id']:1.0}})
    return p


def update_stability_group(project,group,*,kin=1,kout=1,lateral_mm=None,
                            inplane_mm=None,torsion_mm=None,axis_in='x',axis_out='y',
                            rotation=0,reference=''):
    if group not in GROUPS:raise ValueError('Grupo inválido')
    kin=float(kin);kout=float(kout);rotation=float(rotation)
    if not all(isfinite(v) for v in (kin,kout,rotation)) or kin<=0 or kout<=0 or abs(rotation)>180:
        raise ValueError('K ou orientação inválidos')
    if axis_in not in ('x','y') or axis_out not in ('x','y'):
        raise ValueError('Eixo deve ser x ou y')
    p=deepcopy(project)
    spec={'k_in_plane':kin,'k_out_of_plane':kout,'axis_in_plane':axis_in,
          'axis_out_of_plane':axis_out,'rotation_deg':rotation,
          'restraint_reference':str(reference).strip()}
    for key,val in [('unbraced_out_of_plane_mm',lateral_mm),
                    ('unbraced_in_plane_mm',inplane_mm),('torsion_unbraced_mm',torsion_mm)]:
        if val not in (None,'',0):
            f=float(val)
            if not isfinite(f) or f<=0:raise ValueError(f'{key} inválido')
            spec[key]=f
    p.setdefault('stability',{}).setdefault('groups',{})[group]=spec
    return p


def project_diagnostics(project, model, result=None):
    """Diagnóstico descritivo; NÃO certifica rigidez fora do plano ou ELU."""
    out=[]
    def add(level,message,ref=None):out.append({'level':level,'message':message,'ref':ref})
    supports={n:sum(bool(x) for x in xy) for n,xy in model.supports.items()}
    if sum(supports.values())<3:add('erro','Menos de três restrições translacionais: verificar estabilidade global')
    if not any(ux for ux,uy in model.supports.values()):add('erro','Não há restrição horizontal UX')
    if not any(uy for ux,uy in model.supports.values()):add('erro','Não há restrição vertical UY')
    if project.get('cad_drafts'):add('aviso',f'{len(project["cad_drafts"])} nós provisórios não conectados')
    if not project.get('load_cases'):add('erro','Não existe caso de carregamento')
    cases = project.get('load_cases', [])
    active_patterns = {case['id'] for case in cases}
    defined_patterns = {pattern['id']: pattern for pattern in load_patterns(project)}
    for case in cases:
        if case.get('kind') == 'static':
            factors = case.get('patterns', {})
            if not factors or set(factors) - defined_patterns.keys():
                add('erro', f'Caso {case["id"]}: confira os padrões aplicados')
            active_patterns.update(factors)
    for pattern in defined_patterns.values():
        level = 'erro' if pattern['id'] in active_patterns else 'aviso'
        if pattern.get('kind') == 'nodal' and not pattern.get('loads'):
            add(level, f'Padrão {pattern["id"]}: sem forças nodais')
        if model.shape == 'explicit' and pattern.get('kind') in ('surface', 'line'):
            add(level, f'Padrão {pattern["id"]}: cargas distribuídas requerem associação ao CAD')
    if not project.get('combinations'):add('aviso','Sem combinações para análise de envoltórias')
    if project.get('stability',{}).get('groups') is None:
        add('aviso','Dados de estabilidade não cadastrados')
    if result:
        d=result.get('geometry_diagnostics',{})
        for row in d.get('diagonal_angles',[]):
            if not row['within_preferred']:
                add('aviso',f'{row["member"]}: diagonal fora da faixa preferencial',('member',row['member']))
        if not d.get('all_roof_steps_within_max',True):
            add('aviso','Passo de terça superior ao máximo informado')
        stability=result.get('stability',{})
        pending=stability.get('summary',{}).get('pending',0)
        if pending:add('pendência',f'{pending} barras com condições de estabilidade incompletas')
        for w in result.get('warnings',[]):
            if 'Euler:' in w:add('aviso',w)
    add('pendência','ELU por NBR 14762 e estabilidade global fora do plano NÃO verificados')
    return out


def update_roof(project,manufacturer,model,mass_kg_m2,purlin_max_m):
    """Cadastro manual sem inventar vãos admissíveis de fabricante.

    A massa em kg/m² corresponde à carga nominal em kgf/m² sob g=10.
    É adicionada ao caso G2, separado do peso próprio das barras G1.
    """
    manufacturer=str(manufacturer).strip();model=str(model).strip()
    if not manufacturer or not model:raise ValueError('Informe fabricante e modelo da telha')
    mass=_nonnegative(mass_kg_m2,'Massa da telha')
    span=_nonnegative(purlin_max_m,'Espaçamento máximo entre terças')
    if span<=0:raise ValueError('Espaçamento deve ser positivo')
    p=deepcopy(project)
    p['roofing']={'manufacturer':manufacturer,'model':model,'mass_kg_m2':mass,
                  'source':'DECLARADO_PELO_PROJETISTA; CAPACIDADE_DA_TELHA_NAO_VERIFICADA'}
    p.setdefault('geometry',{})['purlin_max_m']=span
    target=next((c for c in p.get('load_cases',[]) if c.get('id')=='G2'),None)
    if target is None:
        _new_load_id(p, 'G2')
        p.setdefault('load_cases',[]).append({'id':'G2','name':'Telha: '+model,
            'kind':'surface','value':mass,'force_unit':'kgf','application':'top',
            'basis':'roof_surface','direction':'down','zone':'all'})
    elif target.get('kind')=='surface':
        target.update(name='Telha: '+model,value=mass,force_unit='kgf',
                      application='top',basis='roof_surface',direction='down')
    else:raise ValueError('G2 existente não é uma carga superficial; não será sobrescrito')
    return p
