"""v0.8 — pesquisa discreta assistida de perfis, usando massa e ELS.

Não otimiza a segurança ELU. Soluções são candidatas para verificação externa,
jamais dimensionamento estrutural aprovado.
"""
from __future__ import annotations
import copy
from math import isfinite
from .engine import run_project
from .model import GROUPS


def suggest_sections(project:dict,catalog:dict,options:dict|None=None)->dict:
    if 'model_override' in project:raise ValueError('Otimização de perfis aceita apenas treliças paramétricas')
    opt=options or {}
    choices=opt.get('profiles',{})
    if not isinstance(choices,dict):raise ValueError('profiles deve ser objeto por grupo')
    if set(choices)-set(GROUPS):raise ValueError('Grupos desconhecidos na pesquisa')
    target=str(opt.get('service_case','S_GRAV'))
    flecha=float(opt.get('flecha_rel',250))
    if not isfinite(flecha) or flecha<=0:raise ValueError('flecha_rel inválida')
    max_candidates=int(opt.get('max_candidates',120))
    if max_candidates<1 or max_candidates>300:raise ValueError('max_candidates deve estar entre 1 e 300')
    base=copy.deepcopy(project)
    base.pop('external_resistances',None)  # nunca reusar capacidades de outros perfis
    # Refazer a busca a partir do modelo atual, alterando um grupo por rodada.
    current=run_project(base,catalog)
    if target not in current['analyses']:raise ValueError('Combinação de serviço não existente')
    limit=current['model']['span_mm']/flecha
    evaluated=0;invalid=[];history=[]
    for group in GROUPS:
        provided=choices.get(group,[base['sections'][group]['profile']])
        if not isinstance(provided,list) or not provided:raise ValueError(f'{group}: lista de perfis vazia')
        possibilities=list(dict.fromkeys(provided))
        if base['sections'][group]['profile'] not in possibilities:
            possibilities.append(base['sections'][group]['profile'])
        local=[]
        for profile in possibilities:
            if evaluated>=max_candidates:break
            evaluated+=1
            if profile not in catalog:
                invalid.append(f'{group}/{profile}: perfil não cadastrado');continue
            p=copy.deepcopy(base);p['sections'][group]['profile']=profile
            try:
                r=run_project(p,catalog)
                flecha_actual=abs(r['analyses'][target]['max_abs_roof_mm'])
                # Qualquer alteração de massa atualiza automaticamente o caso self_weight.
                local.append({'profile':profile,'mass_kg':r['model']['mass_kg'],
                              'flecha_mm':flecha_actual,'service_ok':flecha_actual<=limit+1e-8,
                              'gross_screen_exceed_count':sum(v['gross_yield_screen_exceeded'] or v['euler_critical_exceeded']
                                    for v in r['axial_screen']['members'].values()),
                              'project':p,'result':r})
            except (ValueError,OverflowError,ZeroDivisionError) as exc:
                invalid.append(f'{group}/{profile}: {exc}')
        # Preferir ELÁSTICAMENTE admissível e menor massa; triagem axial só alerta.
        local.sort(key=lambda v:(not v['service_ok'],v['mass_kg']))
        if local:
            winner=local[0]
            base=winner['project'];current=winner['result']
            history.append({'group':group,'candidates':len(local),'selected_profile':winner['profile'],
                            'mass_kg':round(winner['mass_kg'],4),'flecha_mm':round(winner['flecha_mm'],5),
                            'service_ok':winner['service_ok'],
                            'preliminary_axial_alerts':winner['gross_screen_exceed_count']})
        if evaluated>=max_candidates:break
    final_disp=abs(current['analyses'][target]['max_abs_roof_mm'])
    return {'schema':'poe-optimization/v1','method':'coordinate_greedy_E_L_mass',
            'evaluated':evaluated,'invalid':invalid[:30],'steps':history,
            'selected_sections':base['sections'], 'mass_kg':current['model']['mass_kg'],
            'service_case':target,'flecha_mm':final_disp,'flecha_limit_mm':limit,
            'service_limit_ok':final_disp<=limit+1e-8,
            'resistant_design_status':'PENDENTE_NBR_14762_E_LIGACOES',
            'warning':'Pesquisa local sequencial; não comprova ótimo global, resistência, combinações normativas ou dimensionamento ELU.'}
