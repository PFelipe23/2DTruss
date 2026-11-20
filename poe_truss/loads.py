"""Conversão auditável de ações em forças nodais equivalentes (N, mm).

Hipóteses: treliça ideal articulada. Distribuição de uma carga uniforme
por trecho em metades nodais preserva força e momento resultantes, mas NÃO
reproduz a flexão local da barra nem a rigidez da terça.
"""
from __future__ import annotations
from math import hypot, isfinite
from .model import Model
from .units import force_n, area_pressure_n_per_mm2, line_n_per_mm

VALID_DIRECTIONS=('down','up','outward_normal','inward_normal','right','left')
VALID_ZONES=('all','left','right')


def _direction(direction: str, dx: float, dy: float):
    if direction == 'down': return 0., -1.
    if direction == 'up': return 0., 1.
    if direction == 'right': return 1., 0.
    if direction == 'left': return -1., 0.
    length=hypot(dx,dy)
    if length <= 0: raise ValueError('Segmento com comprimento nulo')
    nx,ny=-dy/length,dx/length
    return (nx,ny) if direction == 'outward_normal' else (-nx,-ny)


def build_case_loads(model: Model, case: dict) -> tuple[dict[str,tuple[float,float]],dict]:
    """Produz cargas e relatório de parcelas independentemente da interface.

    ``entries`` contém cada parcela nodal, com seu nó, barra-origem e
    coordenadas. Os totais são recalculados dessas parcelas e confrontados
    com o vetor entregue ao solver. Não arredondar até a visualização.
    """
    nodes=model.node_map()
    totals={key:[0.,0.] for key in nodes}
    entries=[]
    kind=case.get('kind')
    cid=str(case.get('id','SEM_ID'))

    def add(node: str, fx: float, fy: float, origin: str, source: str,
            meta: dict | None=None):
        if node not in nodes: raise ValueError(f'Caso {cid}: nó inexistente {node}')
        if not isfinite(fx) or not isfinite(fy): raise ValueError(f'Caso {cid}: parcela não finita')
        totals[node][0]+=fx
        totals[node][1]+=fy
        n=nodes[node]
        entries.append({'case_id':cid,'origin':origin,'source':source,'node':node,
                        'x_mm':n.x,'y_mm':n.y,'fx_n':fx,'fy_n':fy,
                        'moment_origin_nmm':n.x*fy-n.y*fx,**(meta or {})})

    if kind=='self_weight':
        for m in model.members:
            length_mm=model.member_length(m)
            total_n=m.mass*length_mm/1000*10  # 1 kg nominal = 10 N
            for target in (m.i,m.j):
                add(target,0.,-total_n/2,'self_weight',m.id,
                    {'member_id':m.id,'reference_length_mm':length_mm,
                     'source_mass_kg_m':m.mass,'resultant_n':total_n})
    elif kind=='nodal':
        actions=case.get('loads',[])
        if not isinstance(actions,list) or not actions:
            raise ValueError(f'Caso {cid}: sem ações nodais')
        for index,action in enumerate(actions):
            unit=action.get('force_unit',case.get('force_unit','kgf'))
            fx=force_n(action.get('fx',0),unit)
            fy=force_n(action.get('fy',0),unit)
            add(str(action['node']),fx,fy,'nodal',f'load_{index+1}',
                {'input_fx':action.get('fx',0),'input_fy':action.get('fy',0),'input_unit':unit})
    elif kind in ('surface','line'):
        if model.shape=='explicit':
            raise ValueError('Modelo explícito: distribuídas exigem associação de segmentos; use cargas nodais')
        intensity=float(case.get('value',0))
        if not isfinite(intensity) or intensity<0:raise ValueError(f'Caso {cid}: intensidade inválida')
        unit=case.get('force_unit','kgf')
        q=area_pressure_n_per_mm2(intensity,unit) if kind=='surface' else line_n_per_mm(intensity,unit)
        direction=case.get('direction','down')
        zone=case.get('zone','all')
        application=case.get('application','top')
        basis=case.get('basis','projected')
        if direction not in VALID_DIRECTIONS:raise ValueError(f'Caso {cid}: direção inválida')
        if zone not in VALID_ZONES:raise ValueError(f'Caso {cid}: zona inválida')
        if application not in ('top','bottom'):raise ValueError(f'Caso {cid}: aplicação inválida')
        if basis not in ('projected','roof_surface'):raise ValueError(f'Caso {cid}: base de comprimento inválida')
        left=min(n.x for n in model.nodes)
        center=(left+max(n.x for n in model.nodes))/2
        for m in model.members:
            if m.group!=('superior' if application=='top' else 'inferior'):
                continue
            a,b=nodes[m.i],nodes[m.j]
            dx,dy=b.x-a.x,b.y-a.y
            midpoint=(a.x+b.x)/2
            if zone=='left' and midpoint>center+1e-8:continue
            if zone=='right' and midpoint<center-1e-8:continue
            actual=hypot(dx,dy)
            projected=abs(dx)
            reference_length=projected if basis=='projected' else actual
            tributary_width=model.frame_spacing_mm if kind=='surface' else 1.
            resultant=q*reference_length*tributary_width
            ux,uy=_direction(direction,dx,dy)
            meta={'member_id':m.id,'kind':kind,'input_value':intensity,
                  'input_force_unit':unit,'basis':basis,'direction':direction,'zone':zone,
                  'actual_length_mm':actual,'projected_length_mm':projected,
                  'reference_length_mm':reference_length,
                  'frame_spacing_mm':model.frame_spacing_mm if kind=='surface' else None,
                  'resultant_n':resultant}
            for target in (m.i,m.j):
                add(target,resultant*ux/2,resultant*uy/2,kind,m.id,meta)
    else:
        raise ValueError(f'Caso {cid}: tipo de ação inválido: {kind}')

    loads={key:tuple(v) for key,v in totals.items()}
    total_fx=sum(item['fx_n'] for item in entries)
    total_fy=sum(item['fy_n'] for item in entries)
    total_m=sum(item['moment_origin_nmm'] for item in entries)
    vfx=sum(v[0] for v in loads.values())
    vfy=sum(v[1] for v in loads.values())
    vm=sum(nodes[k].x*v[1]-nodes[k].y*v[0] for k,v in loads.items())
    residual={'fx_n':vfx-total_fx,'fy_n':vfy-total_fy,'moment_nmm':vm-total_m}
    scale=max(1.,abs(vfx),abs(vfy),abs(total_fx),abs(total_fy))
    arm=max(1.,max((abs(n.x)+abs(n.y) for n in nodes.values()),default=0.))
    if (abs(residual['fx_n'])>scale*1e-9 or abs(residual['fy_n'])>scale*1e-9
        or abs(residual['moment_nmm'])>scale*arm*1e-9):
        raise ArithmeticError(f'Caso {cid}: falha de conservação na distribuição nodal')
    audit={'case_id':cid,'kind':kind,'entries':entries,'n_entries':len(entries),
           'sum_fx_n':vfx,'sum_fy_n':vfy,'sum_m_origin_nmm':vm,
           'residual':residual,'status':'CONSISTENTE_ALGEBRICAMENTE',
           'scope':'Conservação da transformação nodal; não valida modelo físico nem coeficientes normativos'}
    return loads,audit


def loads_by_case(model:Model,case:dict):
    return build_case_loads(model,case)[0]


def merge_forces(factors:dict[str,float],loads:dict[str,dict[str,tuple[float,float]]]):
    if not loads:raise ValueError('Nenhum caso de carregamento')
    keys=next(iter(loads.values())).keys()
    combined={k:[0.,0.] for k in keys}
    for case,multiplier in factors.items():
        if case not in loads:raise ValueError(f'Combinação referencia caso inexistente: {case}')
        factor=float(multiplier)
        if not isfinite(factor):raise ValueError(f'Fator inválido em {case}')
        for node,xy in loads[case].items():
            combined[node][0]+=factor*xy[0]
            combined[node][1]+=factor*xy[1]
    return {k:tuple(v) for k,v in combined.items()}


def load_patterns(project):
    """Padrões explícitos e carregamentos legados que também são casos."""
    return [*project.get('load_patterns', []),
            *(case for case in project.get('load_cases', []) if case.get('kind') != 'static')]


def resolve_case_loads(model, case, patterns, *, preview=False, cache=None):
    """Aplica padrões ao caso estático linear antes da análise."""
    if case['kind'] != 'static':
        if preview and case['kind'] == 'nodal' and not case.get('loads'):
            return {node.id: (0., 0.) for node in model.nodes}, {}
        return build_case_loads(model, case)
    factors = case.get('patterns', {})
    if not factors:
        raise ValueError(f'Caso {case["id"]}: informe ao menos um padrão')
    cache = {} if cache is None else cache
    for key in factors:
        if key not in patterns or patterns[key].get('kind') == 'static':
            raise ValueError(f'Caso {case["id"]}: padrão inexistente {key}')
        if key not in cache:
            cache[key] = resolve_case_loads(model, patterns[key], patterns, preview=preview)
    raw = {key: cache[key][0] for key in factors}
    forces = merge_forces(factors, raw)
    entries = []
    for key, factor in factors.items():
        for parcel in cache[key][1].get('entries', []):
            entry = dict(parcel, case_id=case['id'], pattern_id=key, factor=float(factor))
            for field in ('fx_n', 'fy_n', 'moment_origin_nmm'):
                entry[field] *= float(factor)
            entries.append(entry)
    return forces, {
        'case_id': case['id'], 'kind': 'static', 'patterns': dict(factors),
        'entries': entries, 'n_entries': len(entries),
        'sum_fx_n': sum(fx for fx, _ in forces.values()),
        'sum_fy_n': sum(fy for _, fy in forces.values()),
        'sum_m_origin_nmm': sum(row['moment_origin_nmm'] for row in entries),
    }


def combination_audit(combo_id:str,factors:dict[str,float],raw:dict[str,dict[str,tuple[float,float]]]):
    merged=merge_forces(factors,raw)
    entries=[]
    for case,factor in factors.items():
        for node,(fx,fy) in raw[case].items():
            if fx or fy:
                entries.append({'combo_id':combo_id,'case_id':case,'factor':float(factor),
                                'node':node,'fx_n':fx*float(factor),'fy_n':fy*float(factor)})
    return {'case_id':combo_id,'kind':'combination','factors':dict(factors),
            'nodal_parcels':entries,'sum_fx_n':sum(v[0] for v in merged.values()),
            'sum_fy_n':sum(v[1] for v in merged.values()),
            'status':'CONSISTENTE_ALGEBRICAMENTE'}
