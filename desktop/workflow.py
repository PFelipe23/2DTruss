"""Contratos de edição do fluxo de trabalho, independentes de Qt.

Não realiza dimensionamento resistente. Todas as funções retornam NOVO JSON,
validado posteriormente por Session.update_project (modelo/solver existentes).
"""
from __future__ import annotations
from copy import deepcopy
from math import isfinite
from poe_truss.materials import STEEL_GRADES
from poe_truss.model import GROUPS

LOAD_KINDS = ('self_weight','surface','line','nodal')
DIRECTIONS = ('down','up','outward_normal','inward_normal','right','left')


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


def update_load_case(project, case_id, *, name, kind, value=0, force_unit='kgf',
                     application='top', basis='projected', direction='down', zone='all'):
    p=deepcopy(project)
    c=next((x for x in p.get('load_cases',[]) if x['id']==case_id),None)
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
    return p


def add_load_case(project,case_id,kind='surface'):
    case_id=str(case_id).strip()
    ids={r['id'] for r in project.get('load_cases',[])}|{r['id'] for r in project.get('combinations',[])}
    if (not 1<=len(case_id)<=32 or not case_id.replace('_','').isalnum()
        or case_id in ids):raise ValueError('ID vazio, duplicado ou inválido')
    p=deepcopy(project)
    p.setdefault('load_cases',[]).append({'id':case_id,'name':case_id,'kind':kind,
        **({'loads':[]} if kind=='nodal' else {}),
        **({'value':0.,'force_unit':'kgf','application':'top','basis':'projected',
            'direction':'down','zone':'all'} if kind in ('surface','line') else {})})
    return p


def delete_load_case(project,case_id):
    p=deepcopy(project)
    if not any(c['id']==case_id for c in p.get('load_cases',[])):raise ValueError('Caso inexistente')
    if any(case_id in c.get('factors',{}) for c in p.get('combinations',[])):
        raise ValueError('Caso usado em combinação: remova o fator antes de excluir o caso')
    p['load_cases']=[c for c in p['load_cases'] if c['id']!=case_id]
    return p


def update_combination(project,combo_id,factors):
    p=deepcopy(project)
    c=next((r for r in p.get('combinations',[]) if r['id']==combo_id),None)
    if c is None:raise ValueError('Combinação inexistente')
    valid={x['id'] for x in p.get('load_cases',[])}
    if set(factors)-valid:raise ValueError('Combinação referencia caso inexistente')
    numeric={k:float(v) for k,v in factors.items() if float(v)!=0}
    if not numeric or not all(isfinite(x) for x in numeric.values()):
        raise ValueError('Combinação requer ao menos um fator finito não nulo')
    c['factors']=numeric
    return p


def add_combination(project, combo_id):
    combo_id=str(combo_id).strip()
    ids={r['id'] for r in project.get('load_cases',[])}|{r['id'] for r in project.get('combinations',[])}
    if not 1<=len(combo_id)<=32 or not combo_id.replace('_','').isalnum() or combo_id in ids:
        raise ValueError('ID da combinação inválido ou repetido')
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
    for case in project.get('load_cases',[]):
        if case.get('kind')=='nodal' and not case.get('loads'):
            add('erro',f'Caso {case["id"]}: sem forças nodais')
        if model.shape=='explicit' and case.get('kind') in ('surface','line'):
            add('erro',f'Caso {case["id"]}: cargas distribuídas requerem associação ao CAD')
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
        p.setdefault('load_cases',[]).append({'id':'G2','name':'Telha: '+model,
            'kind':'surface','value':mass,'force_unit':'kgf','application':'top',
            'basis':'roof_surface','direction':'down','zone':'all'})
    elif target.get('kind')=='surface':
        target.update(name='Telha: '+model,value=mass,force_unit='kgf',
                      application='top',basis='roof_surface',direction='down')
    else:raise ValueError('G2 existente não é uma carga superficial; não será sobrescrito')
    return p
