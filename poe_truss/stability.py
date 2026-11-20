"""v0.3 — dados declarados para estabilidade axial no plano e fora do plano.

NÃO é solver 3D nem verificador resistente NBR 14762. Travamentos laterais
são declarados pelo projetista e não são comprovados por esta ferramenta.
Comprimentos de flambagem são hipóteses, não resultado do solver plano.
"""
from __future__ import annotations
from math import isfinite,sqrt
from .model import Model, GROUPS

SPEC_KEYS={'k_in_plane','k_out_of_plane','unbraced_in_plane_mm','unbraced_out_of_plane_mm',
           'torsion_unbraced_mm','rotation_deg','axis_in_plane','axis_out_of_plane',
           'restraint_note','restraint_reference'}


def _optional_length(v,label):
    if v is None or v=='':return None
    n=float(v)
    if not isfinite(n) or n<=0:raise ValueError(f'{label} deve ser positivo e finito')
    return n


def _validate_spec(spec:dict,identifier:str):
    if not isinstance(spec,dict):raise ValueError(f'Estabilidade {identifier}: configuração inválida')
    unknown=set(spec)-SPEC_KEYS
    if unknown:raise ValueError(f'Estabilidade {identifier}: campos desconhecidos {sorted(unknown)}')
    for key in ('k_in_plane','k_out_of_plane'):
        if key in spec:
            x=float(spec[key])
            if not isfinite(x) or x<=0:raise ValueError(f'Estabilidade {identifier}: {key} inválido')
    for key in ('unbraced_in_plane_mm','unbraced_out_of_plane_mm','torsion_unbraced_mm'):
        if key in spec:_optional_length(spec[key],f'{identifier}.{key}')
    if 'rotation_deg' in spec:
        angle=float(spec['rotation_deg'])
        if not isfinite(angle) or not -180<=angle<=180:
            raise ValueError(f'Estabilidade {identifier}: rotação fora de [-180,180] graus')
    for key in ('axis_in_plane','axis_out_of_plane'):
        if key in spec and spec[key] not in (None,'x','y'):
            raise ValueError(f'Estabilidade {identifier}: eixo inválido em {key}')
    for key in ('restraint_note','restraint_reference'):
        if key in spec and not isinstance(spec[key],str):
            raise ValueError(f'Estabilidade {identifier}: {key} deve ser texto')


def _lengths_from_bracing(model:Model,bracing:list[dict]):
    """Intervalo entre nós de contraventamento efetivo, ao longo do banzo.

    Aplica-se apenas a grupos com caminho simples sem ramificações. A
    declaração de eficácia deve ser explícita e acompanhada de referência.
    Não calcula rigidez, força ou continuidade do contraventamento.
    """
    nd=model.node_map()
    computed={}
    summary=[]
    if not isinstance(bracing,list):raise ValueError('Estabilidade.lateral_bracing deve ser lista')
    seen=set()
    for br in bracing:
        if not isinstance(br,dict):raise ValueError('Travamento lateral inválido')
        group=br.get('group')
        if group not in ('superior','inferior'):
            raise ValueError('Travamento automático entre nós somente para banzos superior/inferior')
        if group in seen:raise ValueError(f'Travamento duplicado para o grupo {group}')
        seen.add(group)
        ids=br.get('node_ids',[])
        if not isinstance(ids,list) or len(set(ids))!=len(ids):
            raise ValueError(f'Travamento {group}: nós duplicados ou lista inválida')
        effective=br.get('assumed_effective',False)
        if type(effective) is not bool:raise ValueError('assumed_effective deve ser booleano')
        evidence=str(br.get('reference','')).strip()
        if effective and not evidence:
            raise ValueError(f'Travamento {group}: informar referência/justificativa de eficácia')
        members=[m for m in model.members if m.group==group]
        links={}
        for m in members:
            links.setdefault(m.i,[]).append((m.j,m.id,model.member_length(m)))
            links.setdefault(m.j,[]).append((m.i,m.id,model.member_length(m)))
        if any(node not in links for node in ids):
            raise ValueError(f'Travamento {group}: nó não pertence ao banzo')
        if any(len(v)>2 for v in links.values()):
            raise ValueError(f'Travamento {group}: grupo ramificado não suporta inferência automática')
        ends=[n for n,v in links.items() if len(v)==1]
        if len(ends)!=2 or not members:
            raise ValueError(f'Travamento {group}: banzo não forma caminho aberto contínuo')
        start=min(ends,key=lambda k:(nd[k].x,nd[k].y))
        arc={start:0.};midpoints={};previous=None;node=start
        while True:
            options=[c for c in links[node] if c[0]!=previous]
            if not options:break
            if len(options)!=1:raise ValueError(f'Travamento {group}: caminho ambíguo')
            next_node,mid,length=options[0]
            midpoints[mid]=arc[node]+length/2
            arc[next_node]=arc[node]+length
            previous,node=node,next_node
        if len(arc)!=len(links):
            raise ValueError(f'Travamento {group}: trecho desconectado')
        positions=sorted((arc[k], k) for k in ids)
        summary.append({'group':group,'node_ids':ids,'assumed_effective':effective,
                        'reference':evidence,'note':'Eficácia declarada, não verificada' if effective else 'Não utilizado no cálculo'})
        if not effective:continue
        for m in members:
            mid=midpoints[m.id]
            for (left, start_node), (right, end_node) in zip(positions,positions[1:]):
                if left-1e-8<=mid<=right+1e-8:
                    computed[m.id]=(right-left, (start_node, end_node), evidence)
                    break
    return computed,summary


def _declared_nodal_intervals(model, restraints, legacy_summary):
    if not isinstance(restraints, dict):
        raise ValueError('Estabilidade.nodal_restraints deve ser objeto')
    connected = {node for member in model.members for node in (member.i, member.j)}
    confirmed = {}
    for node, entry in restraints.items():
        if not isinstance(entry, dict) or type(entry.get('confirmed')) is not bool:
            raise ValueError(f'Travamento nodal {node}: confirmação inválida')
        reference = entry.get('reference')
        if not isinstance(reference, str) or not reference.strip():
            raise ValueError(f'Travamento nodal {node}: informe uma referência')
        if entry['confirmed']:
            if node not in connected:
                raise ValueError(f'Travamento nodal {node}: nó conectado inexistente')
            confirmed[node] = reference.strip()
    assigned = {row['group'] for row in legacy_summary if row['assumed_effective']}
    intervals, summaries = {}, []
    for group in ('superior', 'inferior'):
        nodes = {node for member in model.members if member.group == group for node in (member.i, member.j)}
        marked = sorted(nodes & confirmed.keys())
        if len(marked) < 2 or group in assigned:
            continue
        entry = {'group': group, 'node_ids': marked, 'assumed_effective': True,
                 'reference': ' · '.join(dict.fromkeys(confirmed[node] for node in marked))}
        try:
            lengths, rows = _lengths_from_bracing(model, [entry])
        except ValueError as error:
            summaries.append(dict(entry, assumed_effective=False, note=str(error), source='nodal_declared'))
        else:
            intervals.update(lengths)
            summaries.extend(dict(row, source='nodal_declared') for row in rows)
    return intervals, summaries


def resolve_stability(model:Model,project:dict,catalog:dict) -> dict:
    config=project.get('stability',{})
    if config is None:config={}
    if not isinstance(config,dict):raise ValueError('Campo stability deve ser objeto')
    extra=set(config)-{'groups','members','lateral_bracing','nodal_restraints'}
    if extra:raise ValueError(f'Estabilidade: campos não reconhecidos {sorted(extra)}')
    group_specs=config.get('groups',{})
    member_specs=config.get('members',{})
    if not isinstance(group_specs,dict) or not isinstance(member_specs,dict):
        raise ValueError('stability.groups/members devem ser objetos')
    member_by_id={m.id:m for m in model.members}
    if set(member_specs)-set(member_by_id):
        raise ValueError('Estabilidade: barras não existentes no modelo (revisar geometria)')
    for key,s in group_specs.items():
        if key not in set(m.group for m in model.members):
            # Suporte para grupos de modelos explícitos, desde que presentes.
            raise ValueError(f'Estabilidade: grupo inexistente {key}')
        _validate_spec(s,f'grupo {key}')
    for key,s in member_specs.items():_validate_spec(s,f'barra {key}')
    auto_braces,bracing_summary=_lengths_from_bracing(model,config.get('lateral_bracing',[]))
    restraints = config.get('nodal_restraints', {})
    nodal_braces, nodal_summary = _declared_nodal_intervals(model, restraints, bracing_summary)
    resolved={};counts={'complete_declared':0,'pending':0}
    for m in model.members:
        d={**group_specs.get(m.group,{}),**member_specs.get(m.id,{})}
        L=model.member_length(m)
        inplane=_optional_length(d.get('unbraced_in_plane_mm'),f'{m.id}.inplane') or L
        outplane=_optional_length(d.get('unbraced_out_of_plane_mm'),f'{m.id}.outplane')
        src_out='declared' if outplane is not None else None
        interval = None
        reference = d.get('restraint_reference', '').strip()
        if outplane is None and m.id in auto_braces:
            outplane, _, _ = auto_braces[m.id]
            src_out='bracing_assumed_effective'
        if outplane is None and m.id in nodal_braces:
            outplane, interval, _ = nodal_braces[m.id]
            src_out = 'nodal_declared'
            reference = ' · '.join(dict.fromkeys(restraints[node]['reference'] for node in interval))
        torsion=_optional_length(d.get('torsion_unbraced_mm'),f'{m.id}.torsion')
        kin=float(d.get('k_in_plane',1.))
        kout=float(d.get('k_out_of_plane',1.))
        axis_in=d.get('axis_in_plane')
        axis_out=d.get('axis_out_of_plane')
        rotation=float(d.get('rotation_deg',0.))
        profile=catalog.get(m.profile)
        count=project.get('sections',{}).get(m.group,{}).get('count',1) if model.shape!='explicit' else None
        section_safe=(profile is not None and count==1 and rotation==0)
        # Ix/Iy sobre eixos informados pelo catálogo, SEM aproximação de Ixy.
        radii={}
        if section_safe:
            radii={'x':sqrt(profile.ix_mm4/profile.area_mm2),'y':sqrt(profile.iy_mm4/profile.area_mm2)}
        def slenderness(k,unbraced,axis):
            r=radii.get(axis)
            return k*unbraced/r if r and unbraced else None
        lambda_in=slenderness(kin,inplane,axis_in)
        lambda_out=slenderness(kout,outplane,axis_out)
        pending=[]
        if outplane is None: pending.append('comprimento_lateral_nao_definido')
        if axis_in not in ('x','y') or axis_out not in ('x','y'):
            pending.append('eixos_da_secao_nao_associados_ao_plano')
        if not section_safe:pending.append('propriedades_transversais_nao_validadas_para_arranjo_ou_rotacao')
        if profile and profile.family.startswith('L '):
            pending.append('cantoneira_sem_Ixy_ou_eixos_principais_cadastrados')
        if torsion is None:pending.append('comprimento_torcional_nao_definido')
        if not reference:pending.append('justificativa_dos_travamentos_pendente')
        state='DADOS_DECLARADOS' if not pending else 'PENDENTE'
        counts['complete_declared' if not pending else 'pending']+=1
        resolved[m.id]={'member_id':m.id,'group':m.group,'profile':m.profile,
            'length_mm':L,'rotation_deg':rotation,'axis_in_plane':axis_in,
            'axis_out_of_plane':axis_out,'unbraced_in_plane_mm':inplane,
            'unbraced_out_of_plane_mm':outplane,'torsion_unbraced_mm':torsion,
            'k_in_plane':kin,'k_out_of_plane':kout,
            'effective_in_plane_mm':kin*inplane,
            'effective_out_of_plane_mm':kout*outplane if outplane else None,
            'out_of_plane_source':src_out,'radii_reference_mm':radii,
            'out_of_plane_interval':list(interval) if interval else None,
            'lambda_in_plane_reference':lambda_in,'lambda_out_plane_reference':lambda_out,
            'restraint_note':d.get('restraint_note',''),
            'restraint_reference':reference,
            'state':state,'missing':pending,
            'resistance_verified':False}
    return {'schema':'poe-stability-data/v1','members':resolved,
            'lateral_bracing':bracing_summary + nodal_summary,'summary':counts,
            'disclaimer':'Somente dados e índices geométricos de referência; sem resistência NBR 14762, sem verificação de contraventamentos ou flambagem 3D.'}
