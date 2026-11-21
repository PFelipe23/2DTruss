"""Representação estrutural independente da interface e do sistema de cargas."""
from __future__ import annotations
from dataclasses import dataclass
from math import atan2, degrees, hypot, isfinite
from typing import Any
from .catalog import Profile

GROUPS = ('superior', 'inferior', 'montante', 'diagonal')
MEMBER_PREFIX = dict(zip(GROUPS, ('BS', 'BI', 'MO', 'DI')))


@dataclass(frozen=True)
class Node:
    id: str
    x: float  # mm
    y: float  # mm


@dataclass(frozen=True)
class Member:
    id: str
    i: str
    j: str
    group: str
    profile: str
    area: float  # mm2
    mass: float  # kg/m
    tension_only: bool = False

    @property
    def label(self):
        prefix = MEMBER_PREFIX.get(self.group)
        if prefix:
            previous = next((code for code in ('M', *MEMBER_PREFIX.values())
                             if self.id.startswith(code) and self.id[len(code):].isdigit()), None)
            if previous:
                return prefix + self.id[len(previous):]
        return self.id


@dataclass
class Model:
    nodes: list[Node]
    members: list[Member]
    supports: dict[str, tuple[bool, bool]]
    span_mm: float
    frame_spacing_mm: float
    shape: str
    truss_type: str
    panels: int
    chord_loads: bool = False

    def node_map(self) -> dict[str, Node]:
        return {n.id: n for n in self.nodes}

    def member_length(self, m: Member) -> float:
        nd = self.node_map()
        a, b = nd[m.i], nd[m.j]
        return hypot(b.x-a.x, b.y-a.y)

    def mass_kg(self) -> float:
        return sum(m.mass*self.member_length(m)/1000 for m in self.members)

    def to_dict(self):
        return {
            'nodes': [{'id':n.id,'x_mm':n.x,'y_mm':n.y} for n in self.nodes],
            'members':[{'id':m.id,'i':m.i,'j':m.j,'group':m.group,
                        'profile':m.profile,'area_mm2':m.area,'mass_kg_m':m.mass, **({'tension_only': True} if m.tension_only else {}),
                        'length_mm':self.member_length(m)} for m in self.members],
            'supports':[{'node':k,'ux':v[0],'uy':v[1]} for k,v in self.supports.items()],
            'span_mm':self.span_mm,'frame_spacing_mm':self.frame_spacing_mm,
            'roof_shape':self.shape,'truss_type':self.truss_type,'panels':self.panels,
            'mass_kg':self.mass_kg(),
        }


def _finite_positive(value, name):
    v=float(value)
    if not isfinite(v) or v<=0:
        raise ValueError(f'{name} deve ser positivo e finito')
    return v


def _top_elevation(x: float, L: float, h: float, rise: float, shape: str) -> float:
    if shape == 'parallel': return h
    if shape == 'single': return h+rise*x/L
    if shape == 'gable': return h+rise*(1.0-abs(2*x/L-1))
    if shape == 'trapezoid': return h+rise*min(x/(L*.30),1.,(L-x)/(L*.30))
    raise ValueError(f'Forma de cobertura não reconhecida: {shape}')


def _profile_group(group: str, sections: dict, catalog: dict[str, Profile]):
    spec=sections.get(group)
    if not isinstance(spec,dict): raise ValueError(f'Seção ausente: {group}')
    name=spec.get('profile','')
    if name not in catalog: raise ValueError(f'Perfil não cadastrado ({group}): {name}')
    count=int(spec.get('count',1))
    if count not in (1,2): raise ValueError(f'Quantidade de perfis em {group} deve ser 1 ou 2')
    p=catalog[name]
    return name,p.area_mm2*count,p.mass_kg_m*count


def make_model(project: dict[str,Any], catalog: dict[str,Profile]) -> Model:
    """Gera treliça articulada ou usa modelo explícito para benchmark FTool.

    Os nós têm IDs estáveis B00..Bn e T00..Tn. Se o número de painéis
    mudar, apoios anteriormente personalizados devem ser confirmados.
    """
    if 'model_override' in project:
        return _explicit_model(project)
    g=project.get('geometry',{})
    L=_finite_positive(g.get('span_m',0),'Vão')*1000
    spacing=_finite_positive(g.get('frame_spacing_m',0),'Distância entre pórticos')*1000
    h=_finite_positive(g.get('height_m',0),'Altura')*1000
    rise=float(g.get('rise_m',0))*1000
    if not isfinite(rise) or rise<0: raise ValueError('Elevação da cobertura inválida')
    panels=int(g.get('panels',0))
    if not 2<=panels<=40: raise ValueError('Número de painéis deve estar entre 2 e 40')
    shape=g.get('roof_shape','parallel')
    kind=g.get('truss_type','Pratt')
    if kind not in ('Pratt','Howe','Warren'):raise ValueError('Triangulação deve ser Pratt, Howe ou Warren')
    if shape=='gable' and panels%2:raise ValueError('Duas águas exige número par de painéis nesta versão')
    if shape not in ('parallel','single','gable','trapezoid'):raise ValueError('Forma não suportada')
    if h+rise<50:raise ValueError('Altura incompatível')
    sections=project.get('sections',{})
    section_map={k:_profile_group(k, sections, catalog) for k in GROUPS}
    width=max(2,len(str(panels)))
    bottom=[Node(f'B{i:0{width}d}', L*i/panels,0.) for i in range(panels+1)]
    top=[Node(f'T{i:0{width}d}',L*i/panels,_top_elevation(L*i/panels,L,h,rise,shape)) for i in range(panels+1)]
    # Edição paramétrica de nós sem perder cargas superficiais ou os IDs das barras.
    # Coordenadas fornecidas em mm. O mesmo modelo continua sendo processado pelo
    # gerador de cargas e pela análise matricial 2D.
    node_edits=project.get('node_edits', {})
    if not isinstance(node_edits, dict):
        raise ValueError('node_edits deve ser um objeto de ID de nó para coordenadas')
    known_ids={n.id for n in bottom+top}
    if set(node_edits)-known_ids:
        raise ValueError(f'Nó editado não existe na geometria atual: {sorted(set(node_edits)-known_ids)[0]}')
    def edited(n):
        item=node_edits.get(n.id)
        if item is None: return n
        if not isinstance(item,dict): raise ValueError(f'Coordenadas de {n.id} devem ser um objeto')
        x=float(item.get('x_mm',n.x));y=float(item.get('y_mm',n.y))
        if not isfinite(x) or not isfinite(y): raise ValueError(f'Coordenadas de {n.id} inválidas')
        return Node(n.id,x,y)
    bottom=[edited(n) for n in bottom]
    top=[edited(n) for n in top]
    for side, ns in [('inferior',bottom),('superior',top)]:
        if any(ns[i+1].x-ns[i].x<1 for i in range(len(ns)-1)):
            raise ValueError(f'Os nós do banzo {side} devem manter X crescente, com separação mínima de 1 mm')
    if any(top[i].y-bottom[i].y < 50 for i in range(len(top))):
        raise ValueError('Altura entre os banzos deve permanecer >= 50 mm')
    members=[]
    def add(i,j,group):
        name,area,mass=section_map[group]
        prefix = MEMBER_PREFIX[group] if g.get('member_ids') == 'group' else 'M'
        members.append(Member(f'{prefix}{len(members)+1:03d}',i,j,group,name,area,mass))
    for i in range(panels):
        add(bottom[i].id,bottom[i+1].id,'inferior')
        add(top[i].id,top[i+1].id,'superior')
    for i in range(panels+1): add(bottom[i].id,top[i].id,'montante')
    for i in range(panels):
        if kind=='Pratt':
            if i<panels/2: add(bottom[i+1].id,top[i].id,'diagonal')
            else: add(bottom[i].id,top[i+1].id,'diagonal')
        elif kind=='Howe':
            if i<panels/2: add(bottom[i].id,top[i+1].id,'diagonal')
            else: add(bottom[i+1].id,top[i].id,'diagonal')
        else:
            if i%2==0: add(bottom[i].id,top[i+1].id,'diagonal')
            else: add(bottom[i+1].id,top[i].id,'diagonal')
    supports_spec=project.get('supports')
    if supports_spec is None:
        supports_spec=[{'node':bottom[0].id,'ux':True,'uy':True},
                       {'node':bottom[-1].id,'ux':False,'uy':True}]
    supports=_parse_supports(supports_spec,{n.id for n in bottom+top})
    model=Model(bottom+top,members,supports,L,spacing,shape,kind,panels)
    validate_model(model)
    return model


def _parse_supports(spec,ids):
    if not isinstance(spec,list):raise ValueError('Lista de apoios inválida')
    out={}
    for s in spec:
        node=s['node']
        if node not in ids:raise ValueError(f'Apoio associado a nó inexistente: {node}')
        if node in out:raise ValueError(f'Apoio repetido: {node}')
        if type(s.get('ux',False)) is not bool or type(s.get('uy',False)) is not bool:
            raise ValueError('Restrições devem ser booleanas')
        out[node]=(s.get('ux',False),s.get('uy',False))
    return out


def _explicit_model(project:dict) -> Model:
    d=project['model_override']
    nodes=[Node(str(n['id']),float(n['x_mm']),float(n['y_mm'])) for n in d['nodes']]
    members=[Member(str(m['id']),str(m['i']),str(m['j']),str(m.get('group','benchmark')),
                    str(m.get('profile','AREA_EXPLICITA')),_finite_positive(m['area_mm2'],'Área da barra'),
                    float(m.get('mass_kg_m',0)), m.get('tension_only') is True) for m in d['members']]
    ids={n.id for n in nodes}
    supports=_parse_supports(d.get('supports',[]),ids)
    xs=[n.x for n in nodes]
    L=max(xs)-min(xs) if xs else 0.
    spacing=float(project.get('geometry',{}).get('frame_spacing_m',1))*1000
    model=Model(nodes,members,supports,L,spacing,'explicit','explicit',0,
                chord_loads=d.get('chord_loads') is True)
    if nodes or members:
        validate_model(model)
    return model


def validate_model(model:Model):
    if any(not isfinite(n.x) or not isfinite(n.y) for n in model.nodes):
        raise ValueError('Coordenadas nodais devem ser finitas')
    if len({n.id for n in model.nodes})!=len(model.nodes): raise ValueError('IDs de nós duplicados')
    if len({m.id for m in model.members})!=len(model.members): raise ValueError('IDs de barras duplicados')
    if len({(n.x,n.y) for n in model.nodes})!=len(model.nodes):raise ValueError('Nós com coordenadas coincidentes')
    nodes=model.node_map()
    edges=set()
    for m in model.members:
        if not isfinite(m.mass) or m.mass<0:raise ValueError(f'Massa da barra {m.id} inválida')
        if m.i not in nodes or m.j not in nodes: raise ValueError(f'Barra {m.id}: nó inexistente')
        if m.i==m.j or model.member_length(m)<1e-8:raise ValueError(f'Barra {m.id}: comprimento nulo')
        key=tuple(sorted((m.i,m.j)))
        if key in edges:raise ValueError(f'Barra duplicada: {m.id}')
        edges.add(key)
        if not isfinite(m.area) or m.area<=0:raise ValueError(f'Área da barra {m.id} inválida')
    connected={s for m in model.members for s in (m.i,m.j)}
    if len(connected)!=len(nodes):raise ValueError('Existem nós desconectados')
    if len(model.nodes)<2:raise ValueError('Modelo sem barras suficientes')


def geometry_diagnostics(model:Model, angle_min:float=45,angle_max:float=60,purlin_max_m:float=0):
    nd=model.node_map()
    diag=[]
    for m in model.members:
        if m.group=='diagonal':
            a,b=nd[m.i],nd[m.j]
            theta=degrees(atan2(abs(b.y-a.y),abs(b.x-a.x)))
            diag.append({'member':m.id,'angle_deg':round(theta,3),
                         'within_preferred':angle_min<=theta<=angle_max})
    roof=[m for m in model.members if m.group=='superior']
    purlins=[{'member':m.id,'spacing_slope_m':round(model.member_length(m)/1000,5),
              'max_ok':not purlin_max_m or model.member_length(m)/1000<=purlin_max_m+1e-9}
             for m in roof]
    return {'diagonal_angles':diag,'purlin_spans':purlins,
            'angle_preferred_fraction':sum(d['within_preferred'] for d in diag)/len(diag) if diag else None,
            'max_roof_step_m':max([p['spacing_slope_m'] for p in purlins],default=0.),
            'all_roof_steps_within_max':all(p['max_ok'] for p in purlins)}
