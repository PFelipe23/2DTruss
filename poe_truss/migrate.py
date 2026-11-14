"""Importador orientado à continuidade de projetos v0.5.0 (Go).

Converte cargas superficiais existentes SEM substituí-las por autopeso real:
a parcela 'g_trelica' anterior era estimativa por m², não barras explicitadas.
Assim evita dupla contagem silenciosa; o novo G1 automático pode ser adicionado
pelo usuário em substituição ao G_LEG, após conferência do modelo.
"""
from __future__ import annotations


def migrate_v05(raw:dict, catalogue:dict) -> dict:
    if raw.get('schema')!='poe-trelica-cff/v05' or not isinstance(raw.get('model'),dict):
        raise ValueError('Importação legada disponível somente para poe-trelica-cff/v05')
    old=raw['model']
    def number(k,default=0.):return float(old.get(k,default))
    def p(g,default):
        name=old.get(g,default)
        if name not in catalogue:raise ValueError(f'Perfil legado não encontrado: {name}')
        count=int(old.get('asm_'+g+'_count',1))
        if count not in (1,2):raise ValueError(f'Quantidade legada de perfis inválida: {g}')
        return {'profile':name,'count':count}
    origin={'flat':'parallel','pitched':'gable','mono':'single','trapezoid':'trapezoid','':'parallel'}
    shape=origin.get(old.get('top_shape','flat'))
    if not shape:raise ValueError('Formato legado desconhecido')
    groups={k:p(k, next(iter(catalogue))) for k in ('superior','inferior','montante','diagonal')}
    load=[]
    for cid,title,key in [
        ('G_TELHA','Telhas — carga original v0.5','g_telha'),
        ('G_TERCA','Terças — carga original v0.5','g_terca'),
        ('G_LEG','Estimativa anterior de peso da treliça — substituir por G1 automático após conferir','g_trelica'),
        ('Q_LEG','Sobrecarga — v0.5','q_surface')]:
        value=number(key)*1_000_000/10 # N/mm² -> kgf nominal/m²
        if value<0:raise ValueError(f'Carga legada negativa: {key}')
        load.append({'id':cid,'name':title,'kind':'surface','value':value,'force_unit':'kgf',
                     'application':'top','basis':'projected','direction':'down','zone':'all'})
    wind=number('wind_surface')*1_000_000/10
    mode=old.get('wind_mode','none')
    if wind>0:
        if mode in ('up','both'):
            load.append({'id':'W_LEG_UP','name':'Vento anterior vertical ascendente (NÃO normal)','kind':'surface',
                         'value':wind,'force_unit':'kgf','application':'top','basis':'projected','direction':'up','zone':'all'})
        if mode in ('down','both'):
            load.append({'id':'W_LEG_DOWN','name':'Vento anterior vertical descendente (NÃO normal)','kind':'surface',
                         'value':wind,'force_unit':'kgf','application':'top','basis':'projected','direction':'down','zone':'all'})
    G={c['id']:1 for c in load if c['id'].startswith('G_')}
    els={**G,'Q_LEG':1}
    elu={**{k:number('gamma_g',1.4) for k in G},'Q_LEG':number('gamma_q',1.5)}
    return {'schema':'poe-truss-python/v1','name':'IMPORTADO v0.5 — REVISAR AÇÕES!',
        'geometry':{'span_m':number('span_mm')/1000,'frame_spacing_m':number('spacing_mm')/1000,
           'panels':int(number('panels',8)),'height_m':number('height_mm',900)/1000,
           'rise_m':number('roof_rise_mm')/1000,'roof_shape':shape,
           'truss_type':old.get('geometry','Pratt'),'purlin_max_m':number('purlin_max_mm',1500)/1000,
           'angle_min_deg':number('angle_min_deg',45),'angle_max_deg':number('angle_max_deg',60)},
        'material':{'E_MPa':number('e_mpa',200000)},'sections':groups,'load_cases':load,
        'combinations':[{'id':'ELS_LEG','name':'G+Q conforme versão anterior','factors':els},
                        {'id':'ELU_LEG_ILUSTRATIVO','name':'Fatores ilustrativos anteriores — sem conformidade normativa','factors':elu}],
        'migration_notes':[ 'Cargas legadas conservadas como ações superficiais na projeção horizontal.',
           'G_LEG é peso da treliça estimado por área na v0.5; não acrescentar G1 automático sem remover G_LEG.',
           'Vento original é vertical, não normal à cobertura. Reexaminar carregamentos e combinações.',
           'Apoios atuais serão restaurados como XY à esquerda e Y à direita.',
           'Seções duplas conservam multiplicidade, sem verificar os arranjos ou ligações.' ]}
