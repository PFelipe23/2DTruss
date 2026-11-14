"""Importação CAD controlada: DXF via ezdxf; DWG via ODA File Converter local.

Importa eixos de barras, não contornos. Não cria apoios, não determina
automaticamente que cruzamentos representem nós ou que desenhos equivalham
à modelagem estrutural validada. O usuário deve conferir e aprovar a prévia.
"""
from __future__ import annotations
from dataclasses import dataclass,field
from pathlib import Path
from copy import deepcopy
import hashlib
import math

MAX_CAD_BYTES=40*1024*1024
MAX_ENTITIES=10000
UNIT_FACTORS_MM={1:25.4,2:304.8,4:1.,5:10.,6:1000.,14:100.}


@dataclass
class CadPreview:
    nodes:list[dict]=field(default_factory=list)
    members:list[dict]=field(default_factory=list)
    source:str=''
    units_source:str=''
    scale_mm:float=1
    warnings:list[str]=field(default_factory=list)
    ignored:dict[str,int]=field(default_factory=dict)
    sha256:str=''
    layers:dict[str,int]=field(default_factory=dict)


def _group(layer:str)->str:
    name=layer.lower().replace('-','_')
    if any(s in name for s in ('banzo_sup','superior','bs_','top_chord')):return 'superior'
    if any(s in name for s in ('banzo_inf','inferior','bi_','bottom_chord')):return 'inferior'
    if any(s in name for s in ('montante','vertical','post_')):return 'montante'
    return 'diagonal'  # provisório: verificar na interface


def load_cad(path:str|Path,*,unitless_unit='mm',merge_tolerance_mm=1.)->CadPreview:
    """Carrega LINE/LWPOLYLINE/POLYLINE 2D. Sem inferir nós em interseções.

    DWG só é aceito se o ODA File Converter estiver instalado. ezdxf nunca
    é utilizado como se decodificasse DWG nativamente.
    """
    import ezdxf
    p=Path(path)
    if not p.is_file():raise FileNotFoundError(str(p))
    if p.stat().st_size>MAX_CAD_BYTES:raise ValueError('Arquivo CAD maior que 40 MB')
    suffix=p.suffix.lower()
    if suffix=='.dxf':
        try:doc=ezdxf.readfile(str(p))
        except Exception as ex:raise ValueError(f'DXF inválido ou ilegível: {ex}') from ex
    elif suffix=='.dwg':
        try:
            from ezdxf.addons import odafc
        except ImportError as ex:raise RuntimeError('Importação DWG requer ezdxf e ODA File Converter') from ex
        if not odafc.is_installed():
            raise RuntimeError('DWG requer ODA File Converter instalado localmente. Converta para DXF e importe novamente.')
        try:doc=odafc.readfile(str(p),audit=True)
        except Exception as ex:raise ValueError(f'Falha de conversão DWG pela ODA: {ex}') from ex
    else:raise ValueError('Formatos aceitos: .dxf ou .dwg (via ODA)')
    audit=doc.audit()
    if audit.has_errors:raise ValueError('CAD possui erros de integridade detectados pelo auditor DXF')
    insunits=int(doc.header.get('$INSUNITS',0))
    if insunits==0:
        manual={'mm':1.,'cm':10.,'m':1000.,'in':25.4}.get(unitless_unit)
        if manual is None:raise ValueError('Unidade para DXF sem unidade inválida')
        factor=manual
        unit_label=f'{unitless_unit} (atribuído ao CAD sem unidade)'
    else:
        factor=UNIT_FACTORS_MM.get(insunits)
        if factor is None:raise ValueError(f'Unidade INSUNITS={insunits} ainda não suportada; converta o DXF para mm')
        unit_label=f'INSUNITS={insunits}'
    tol=float(merge_tolerance_mm)
    if not math.isfinite(tol) or not .001<=tol<=100:raise ValueError('Tolerância deve estar entre 0,001 e 100 mm')
    preview=CadPreview(source=p.name,scale_mm=factor,units_source=unit_label,
                       sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    if not insunits:preview.warnings.append('DXF sem unidade: unidade definida manualmente; conferir escala')
    if suffix=='.dwg':preview.warnings.append('DWG convertido por ferramenta ODA externa; revisar geometria e escala')
    preview.warnings.append('Cruzamentos sem vértices CAD NÃO são automaticamente subdivididos')
    preview.warnings.append('Camadas inferidas provisoriamente; verificar grupos de todas as barras')
    segs=[]
    def record(a,b,layer):
        xyz1=tuple(float(v) for v in a);xyz2=tuple(float(v) for v in b)
        if len(xyz1)<2 or len(xyz2)<2:return
        if any(not math.isfinite(v) for v in xyz1+xyz2):raise ValueError('CAD contém coordenada não finita')
        if (len(xyz1)>2 and abs(xyz1[2]*factor)>tol) or (len(xyz2)>2 and abs(xyz2[2]*factor)>tol):
            preview.ignored['NAO_PLANAR']=preview.ignored.get('NAO_PLANAR',0)+1;return
        a2=(xyz1[0]*factor,xyz1[1]*factor)
        b2=(xyz2[0]*factor,xyz2[1]*factor)
        if math.dist(a2,b2)<tol:
            preview.ignored['CURTO']=preview.ignored.get('CURTO',0)+1;return
        segs.append((a2,b2,layer))
    def handle(ent,level=0):
        if len(segs)>MAX_ENTITIES:raise ValueError('Muitas entidades (>10.000)')
        kind=ent.dxftype();layer=str(ent.dxf.get('layer','0'))
        if kind=='LINE':record(ent.dxf.start,ent.dxf.end,layer)
        elif kind=='LWPOLYLINE':
            pts=list(ent.get_points('xyb'))
            if any(abs(float(b))>1e-10 for _,_,b in pts):
                preview.ignored['LWPOLYLINE_COM_ARCO']=preview.ignored.get('LWPOLYLINE_COM_ARCO',0)+1;return
            z=float(ent.dxf.get('elevation',0))
            if abs(z*factor)>tol:
                preview.ignored['NAO_PLANAR']=preview.ignored.get('NAO_PLANAR',0)+1;return
            xyz=[(x,y,z) for x,y,_ in pts]
            for a,b in zip(xyz,xyz[1:]):record(a,b,layer)
            if ent.closed and len(xyz)>2:record(xyz[-1],xyz[0],layer)
        elif kind=='POLYLINE':
            verts=list(ent.vertices)
            xyz=[tuple(v.dxf.location) for v in verts]
            if getattr(ent,'is_3d_polyline',False) and any(abs(v[2]*factor)>tol for v in xyz):
                preview.ignored['NAO_PLANAR']=preview.ignored.get('NAO_PLANAR',0)+1;return
            for a,b in zip(xyz,xyz[1:]):record(a,b,layer)
            if ent.is_closed and len(xyz)>2:record(xyz[-1],xyz[0],layer)
        elif kind=='INSERT' and level<3:
            try:
                for sub in ent.virtual_entities():handle(sub,level+1)
            except Exception:
                preview.ignored['INSERT_INVALIDO']=preview.ignored.get('INSERT_INVALIDO',0)+1
        else:preview.ignored[kind]=preview.ignored.get(kind,0)+1
    for idx,entity in enumerate(doc.modelspace()):
        if idx>=MAX_ENTITIES:raise ValueError('Limite de 10.000 entidades CAD ultrapassado')
        handle(entity)
    if not segs:raise ValueError('Arquivo sem eixos LINE / POLYLINE 2D utilizáveis')
    # Tolerância espacial com grade e busca nas células vizinhas.
    # Usa coordenadas originais para evitar mover os pontos importados.
    node_xy=[];cells={}
    def nid(xy):
        gx=math.floor(xy[0]/tol);gy=math.floor(xy[1]/tol)
        for i in (gx-1,gx,gx+1):
            for j in (gy-1,gy,gy+1):
                for index in cells.get((i,j),[]):
                    if math.dist(xy,node_xy[index])<=tol:return index
        k=len(node_xy);node_xy.append(xy);cells.setdefault((gx,gy),[]).append(k)
        return k
    edges=set()
    provisional=[]
    for a,b,layer in segs:
        i,j=nid(a),nid(b)
        if i==j:
            preview.ignored['COLAPSADA']=preview.ignored.get('COLAPSADA',0)+1;continue
        key=tuple(sorted((i,j)))
        if key in edges:
            preview.ignored['DUPLICADA']=preview.ignored.get('DUPLICADA',0)+1;continue
        edges.add(key);provisional.append((i,j,layer))
        preview.layers[layer]=preview.layers.get(layer,0)+1
    if not provisional:raise ValueError('Nenhuma barra válida após fusão de nós')
    minx=min(x for x,y in node_xy);miny=min(y for x,y in node_xy)
    preview.warnings.append('Coordenadas deslocadas para origem local mínima (Xmin, Ymin)')
    preview.nodes=[{'id':f'N{k+1:03d}','x_mm':x-minx,'y_mm':y-miny} for k,(x,y) in enumerate(node_xy)]
    preview.members=[{'id':f'M{k+1:03d}','i':f'N{i+1:03d}','j':f'N{j+1:03d}',
                      'group':_group(layer),'layer':layer} for k,(i,j,layer) in enumerate(provisional)]
    return preview


def make_import_project(project:dict,preview:CadPreview,catalog:dict,layer_groups:dict[str,str]|None=None)->dict:
    """Substitui topologia após confirmação humana; descarta cargas incompatíveis.

    Não inventa apoios. Com apoios vazios, cálculo é bloqueado até edição.
    """
    layer_groups=layer_groups or {}
    p=deepcopy(project)
    groups=p.get('sections',{})
    if not groups:raise ValueError('Catálogo de seções ausente')
    members=[]
    for raw in preview.members:
        group=layer_groups.get(raw['layer'],raw['group'])
        if group not in groups:raise ValueError(f'Grupo inválido para camada {raw["layer"]}')
        spec=groups[group];prof=catalog[spec['profile']];count=int(spec.get('count',1))
        if count not in (1,2):raise ValueError('Seção dupla/simples inválida')
        members.append({'id':raw['id'],'i':raw['i'],'j':raw['j'],
                        'group':group,'profile':spec['profile'],
                        'area_mm2':prof.area_mm2*count,'mass_kg_m':prof.mass_kg_m*count})
    p['model_override']={'nodes':deepcopy(preview.nodes),'members':members,'supports':[]}
    p.pop('node_edits',None);p.pop('supports',None);p.pop('cad_drafts',None)
    p['load_cases']=[c for c in p.get('load_cases',[]) if c.get('kind')=='self_weight']
    if not p['load_cases']:p['load_cases']=[{'id':'G1','name':'Peso próprio das barras','kind':'self_weight'}]
    p['combinations']=[]
    p['stability']={}
    p.pop('external_resistances',None)
    p.pop('camber',None)
    p['cad_import']={'filename':preview.source,'sha256':preview.sha256,
                     'units':preview.units_source,'scale_to_mm':preview.scale_mm,
                     'origin_shift_applied':True,
                     'notice':'Modelo CAD requer apoios e carregamentos definidos pelo projetista'}
    return p
