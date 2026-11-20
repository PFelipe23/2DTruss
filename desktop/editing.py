"""Edição de topologia 2D independente de Qt. Sem alterar o solver.

O primeiro comando avançado materializa o modelo paramétrico em model_override.
Nós soltos permanecem em cad_drafts até a primeira conexão válida.
Operações retornam um novo JSON; o chamador aplica Session.update_project
somente depois de passar pelas validações do núcleo.
"""
from __future__ import annotations
from copy import deepcopy
from math import hypot, isfinite
from typing import Iterable


def materialize(project:dict, model) -> dict:
    p=deepcopy(project)
    if 'model_override' not in p:
        p['model_override']={
            'nodes':[{'id':n.id,'x_mm':n.x,'y_mm':n.y} for n in model.nodes],
            'members':[{'id':m.id,'i':m.i,'j':m.j,'group':m.group,
                        'profile':m.profile,'area_mm2':m.area,'mass_kg_m':m.mass} for m in model.members],
            'supports':[{'node':nid,'ux':uv[0],'uy':uv[1]} for nid,uv in model.supports.items()]
        }
        p.pop('node_edits',None)
        p.pop('supports',None)
    return p


def _invalidate_derived(p:dict):
    """Derruba declarações de resistência e eficácia potencialmente obsoletas."""
    p.pop("external_resistances",None)
    for br in p.get("stability",{}).get("lateral_bracing",[]):
        br["assumed_effective"]=False
    review_nodal_restraints(p)
    p.setdefault("cad_editor_notices",[]).append(
        "Edição CAD: revisar travamentos, capacidades externas e comprimento de flambagem")

def review_nodal_restraints(project):
    for entry in (project.get('stability') or {}).get('nodal_restraints', {}).values():
        entry['confirmed'] = False


def _find(rows, key):
    return next((r for r in rows if r['id']==key),None)


def _id(prefix, items, p):
    ids={x['id'] for x in items}
    seq=p.setdefault('cad_sequences',{})
    existing=[int(x[len(prefix):]) for x in ids if x.startswith(prefix) and x[len(prefix):].isdigit()]
    k=max(seq.get(prefix,1), max(existing,default=0)+1)
    while f'{prefix}{k:03d}' in ids:k+=1
    seq[prefix]=k+1
    return f'{prefix}{k:03d}'


def _xy(x,y):
    x,y=float(x),float(y)
    if not isfinite(x) or not isfinite(y):raise ValueError('Coordenadas não finitas')
    return x,y


def add_draft(project:dict, model, x, y)->tuple[dict,str]:
    x,y=_xy(x,y)
    p=materialize(project,model)
    nodes=p['model_override']['nodes']
    drafts=p.setdefault('cad_drafts',[])
    if any(hypot(x-z['x_mm'],y-z['y_mm'])<.001 for z in nodes+drafts):
        raise ValueError('Já existe um nó nesta posição')
    nid=_id('N',nodes+drafts,p)
    drafts.append({'id':nid,'x_mm':x,'y_mm':y})
    return p,nid


def add_member(project:dict,model,nid_a:str,nid_b:str,*,group='diagonal')->tuple[dict,str]:
    if nid_a==nid_b:raise ValueError('A barra requer dois nós distintos')
    p=materialize(project,model); d=p['model_override'];drafts=p.get('cad_drafts',[])
    combined=d['nodes']+drafts
    a,b=_find(combined,nid_a),_find(combined,nid_b)
    if not a or not b:raise ValueError('Nó não encontrado')
    if hypot(a['x_mm']-b['x_mm'],a['y_mm']-b['y_mm'])<1e-6:
        raise ValueError('Comprimento da barra é nulo')
    if any({m['i'],m['j']}=={nid_a,nid_b} for m in d['members']):
        raise ValueError('Barra entre estes nós já existe')
    # Dois nós novos sem ligação com o modelo não constituem um modelo estrutural
    # válido. O usuário precisa anexá-los à malha existente.
    registered={x['id'] for x in d['nodes']}
    if not ({nid_a,nid_b}&registered):
        raise ValueError('Conecte primeiro pelo menos um nó à estrutura existente')
    if group not in p.get('sections',{}):
        raise ValueError('Grupo não tem seção cadastrada')
    from poe_truss.catalog import load_catalog
    from .bridge import CATALOG
    catalog=load_catalog(CATALOG)
    section=p['sections'][group]
    prof=catalog[section['profile']];cnt=int(section.get('count',1))
    if cnt not in (1,2):raise ValueError('Número inválido de componentes')
    for nid in (nid_a,nid_b):
        draft=_find(drafts,nid)
        if draft:
            d['nodes'].append(deepcopy(draft));drafts.remove(draft)
    mid=_id('M',d['members'],p)
    d['members'].append({'id':mid,'i':nid_a,'j':nid_b,'group':group,
                         'profile':section['profile'],'area_mm2':prof.area_mm2*cnt,
                         'mass_kg_m':prof.mass_kg_m*cnt})
    _invalidate_derived(p)
    return p,mid


def split_members(project:dict,model,member_ids:Iterable[str],t:float=.5)->tuple[dict,list[str]]:
    t=float(t)
    if not .01<t<.99:raise ValueError('Posição de subdivisão precisa estar entre 1% e 99%')
    p=materialize(project,model);d=p['model_override'];created=[]
    for mid in dict.fromkeys(member_ids):
        member=_find(d['members'],mid)
        if member is None:raise ValueError(f'Barra inexistente: {mid}')
        a,b=_find(d['nodes'],member['i']),_find(d['nodes'],member['j'])
        x=a['x_mm']*(1-t)+b['x_mm']*t;y=a['y_mm']*(1-t)+b['y_mm']*t
        if any(hypot(x-n['x_mm'],y-n['y_mm'])<.001 for n in d['nodes']):
            raise ValueError('A subdivisão geraria nó coincidente')
        nid=_id('N',d['nodes']+p.get('cad_drafts',[]),p)
        d['nodes'].append({'id':nid,'x_mm':x,'y_mm':y})
        original=deepcopy(member)
        _ids_before=[m['id'] for m in d['members']]
        mseq=p.setdefault('cad_sequences',{})
        mseq['M']=max(mseq.get('M',1),max((int(x[1:]) for x in _ids_before if x.startswith('M') and x[1:].isdigit()),default=0)+1)
        d['members'].remove(member)
        for a_id,b_id in ((original['i'],nid),(nid,original['j'])):
            m=deepcopy(original);m['id']=_id('M',d['members'],p);m['i']=a_id;m['j']=b_id
            d['members'].append(m)
        specs=p.get('stability',{}).get('members',{})
        # Invalida hipótese específica de flambagem; NÃO a transfere automaticamente.
        specs.pop(mid,None)
        created.append(nid)
    _invalidate_derived(p)
    return p,created


def move_nodes(project:dict,model,updates:dict[str,tuple[float,float]])->dict:
    p=materialize(project,model);d=p['model_override'];drafts=p.get('cad_drafts',[])
    for nid,coords in updates.items():
        target=_find(d['nodes'],nid) or _find(drafts,nid)
        if target is None:raise ValueError(f'Nó inexistente {nid}')
        x,y=_xy(*coords);target['x_mm']=x;target['y_mm']=y
    _invalidate_derived(p)
    return p


def delete_elements(project:dict,model,node_ids=(),member_ids=())->dict:
    p=materialize(project,model);d=p['model_override']
    remove_nodes=set(node_ids);remove_members=set(member_ids)
    all_n={r['id'] for r in d['nodes']+p.get('cad_drafts',[])}
    all_m={r['id'] for r in d['members']}
    if remove_nodes-all_n or remove_members-all_m:raise ValueError('Seleção contém identificador inexistente')
    if remove_nodes:
        remove_members|={m['id'] for m in d['members'] if m['i'] in remove_nodes or m['j'] in remove_nodes}
    d['members']=[m for m in d['members'] if m['id'] not in remove_members]
    d['nodes']=[n for n in d['nodes'] if n['id'] not in remove_nodes]
    p['cad_drafts']=[n for n in p.get('cad_drafts',[]) if n['id'] not in remove_nodes]
    d['supports']=[s for s in d['supports'] if s['node'] not in remove_nodes]
    for c in [*p.get('load_cases', []), *p.get('load_patterns', [])]:
        if c.get('kind')=='nodal':c['loads']=[r for r in c.get('loads',[]) if r['node'] not in remove_nodes]
    stability=p.get('stability',{})
    for nid in remove_nodes:
        stability.get('nodal_restraints', {}).pop(nid, None)
    for mid in remove_members:stability.get('members',{}).pop(mid,None)
    for brace in stability.get('lateral_bracing',[]):
        brace['node_ids']=[x for x in brace.get('node_ids',[]) if x not in remove_nodes]
        # Travamento automático precisa ser reconfirmado após topologia alterada.
        brace['assumed_effective']=False
    _invalidate_derived(p)
    return p


def update_member_group(project:dict,model,ids,group:str)->dict:
    p=materialize(project,model);d=p['model_override']
    if group not in p['sections']:raise ValueError('Grupo não cadastrado')
    from poe_truss.catalog import load_catalog
    from .bridge import CATALOG
    profname=p['sections'][group]['profile'];prof=load_catalog(CATALOG)[profname]
    cnt=int(p['sections'][group].get('count',1))
    for mid in ids:
        m=_find(d['members'],mid)
        if m is None:raise ValueError(f'Barra não existe: {mid}')
        m.update(group=group,profile=profname,area_mm2=prof.area_mm2*cnt,mass_kg_m=prof.mass_kg_m*cnt)
        p.get('stability',{}).get('members',{}).pop(mid,None)
    _invalidate_derived(p)
    return p
