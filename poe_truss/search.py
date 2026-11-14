"""Busca preliminar de modulação e altura, SEM verificação de resistência.

Otimiza critérios geométricos e de deformação linear para o caso/combinação
selecionado. Apoios padrão nos extremos durante a busca; não atribui ELU.
"""
from __future__ import annotations
import copy
from math import ceil,floor,isfinite
from .engine import run_project


def suggest_geometry(project:dict,catalog:dict,options:dict|None=None):
    options=options or {}
    if project.get('model_override'):raise ValueError('A busca só aceita treliças paramétricas')
    g=project.get('geometry',{})
    L=float(g['span_m']); h=float(g['height_m']); max_step=float(g.get('purlin_max_m',0))
    if not isfinite(L) or not isfinite(h) or L<=0 or h<=0:raise ValueError('Vão e altura inválidos')
    if L>100 or h>10:raise ValueError('Modelo fora do domínio de pesquisa')
    assumed_step=max_step if max_step>0 else L/max(int(g['panels']),1)
    target_n=max(2,min(40,round(L/assumed_step)))
    panel_min=max(2,int(options.get('panel_min',target_n-3)))
    panel_max=min(40,int(options.get('panel_max',target_n+3)))
    if panel_max<panel_min:raise ValueError('Intervalo de painéis inválido')
    h_min=float(options.get('height_min_m',max(.4,h-.5)))
    h_max=float(options.get('height_max_m',h+.5))
    step=float(options.get('height_step_m',.05))
    ratio=float(options.get('flecha_rel',250))
    target_case=str(options.get('case','S_GRAV'))
    if not all(isfinite(v) for v in (h_min,h_max,step,ratio)) or h_min<=0 or h_max<h_min or step<.025 or step>.5 or ratio<=0:
        raise ValueError('Parâmetros de pesquisa inválidos')
    heights=min(31,1+int((h_max-h_min)/step+1e-7))
    if heights<1:raise ValueError('Não há alturas candidatas')
    if (panel_max-panel_min+1)*heights>320:
        raise ValueError('Busca excede 320 combinações; reduza altura/painéis')
    raw=[];invalid=0
    for panels in range(panel_min,panel_max+1):
        if g.get('roof_shape')=='gable' and panels%2:continue
        for k in range(heights):
            z=copy.deepcopy(project)
            z['geometry']['panels']=panels
            z['geometry']['height_m']=round(h_min+k*step,5)
            z.pop('supports',None) # apoios extremos-padrão, explícito nos metadados
            try:
                r=run_project(z,catalog)
                data=r['geometry_diagnostics']
                a=r['analyses'].get(target_case)
                if not a:raise ValueError(f'Caso/combinação {target_case} não encontrado')
                disp=abs(a['max_abs_roof_mm'])
                limit=z['geometry']['span_m']*1000/ratio
                max_dist=data['max_roof_step_m']
                excess=max(0.,max_dist/max_step-1) if max_step>0 else 0.
                angular=[]
                a_min=float(g.get('angle_min_deg',45))
                a_max=float(g.get('angle_max_deg',60))
                for d in data['diagonal_angles']:
                    angle=d['angle_deg']
                    angular.append(max(a_min-angle,0,angle-a_max))
                avg_dev=sum(angular)/max(len(angular),1)
                raw.append({'panels':panels,'height_m':z['geometry']['height_m'],
                  'mass_kg':round(r['model']['mass_kg'],3),'max_purlin_m':max_dist,
                  'max_abs_roof_mm':round(disp,4),'displacement_limit_mm':round(limit,4),
                  'angle_fraction':data['angle_preferred_fraction'],
                  'angle_avg_deviation_deg':round(avg_dev,3),
                  'purlin_ok':excess<=1e-9,'displacement_ok':disp<=limit+1e-7,
                  '_purlin_excess':excess,'_disp_excess':max(0,disp/max(limit,1e-8)-1)})
            except ValueError:
                invalid+=1
    if not raw:raise ValueError('Nenhuma geometria estável encontrada na faixa indicada')
    mass_ref=min(x['mass_kg'] for x in raw)
    for r in raw:
        r['score']=round(0.65*r['mass_kg']/mass_ref +
                         30*r['_disp_excess']+30*r['_purlin_excess']+
                         .7*r['angle_avg_deviation_deg'],4)
        r['meets_geometric_service_criteria']=r['purlin_ok'] and r['displacement_ok']
        del r['_disp_excess'];del r['_purlin_excess']
    # Viáveis são apresentados antes dos demais; faixa angular é preferência.
    raw.sort(key=lambda x:(not x['meets_geometric_service_criteria'],x['score']))
    return {'candidates':raw[:10],'evaluated':len(raw),'invalid':invalid,
            'target_case':target_case,'flecha_rel':ratio,
            'supports_for_search':'default_end_XY_Y',
            'scope':'Apenas rigidez linear, geometria e massa de barras; SEM verificação resistente ELU',
            'all_candidates_meet_criteria':all(x['meets_geometric_service_criteria'] for x in raw)}
