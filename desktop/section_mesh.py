"""Malhas de inspeção 3D dos perfis U, UE e L.

Este módulo NÃO participa do solver. A geometria da seção é formada por paredes
planas (sem raios); em perfis laminados a espessura da mesa não está no catálogo
atual e usa-se, exclusivamente para VISUALIZAÇÃO, a espessura registrada da alma.
Unidades de armazenamento: mm. Sem dependências gráficas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from math import cos, sin, radians, hypot, isfinite
from typing import Sequence
import csv
import re


@dataclass(frozen=True)
class ProfileShape:
    name: str
    family: str
    height: float
    flange: float
    thickness: float
    lip: float = 0.0
    source: str = ''
    note: str = ''


@dataclass(frozen=True)
class Mesh:
    """Vértices XYZ, faces indexadas, material group e procedência visual."""
    vertices: tuple[tuple[float, float, float], ...]
    faces: tuple[tuple[int, ...], ...]
    member_id: str
    component: int
    group: str
    profile: str
    notes: tuple[str, ...] = ()


def _number(raw: str) -> float:
    v = float(str(raw).replace(',', '.'))
    if not isfinite(v):
        raise ValueError('Dimensão de perfil não finita')
    return v


def load_shape_catalog(path: str | Path) -> dict[str, ProfileShape]:
    result: dict[str, ProfileShape] = {}
    with open(path, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f, delimiter=';'):
            name, fam = row['perfil'], row['familia'].upper()
            if not (fam.startswith('U') or fam.startswith('L')):
                continue
            h, w, t = (_number(row[key]) for key in ('bw_mm', 'bf_mm', 't_mm'))
            lip = 0.
            note = 'Contornos retos, sem raios de dobramento ou concordância.'
            if fam.startswith('UE'):
                # Formato existente do catálogo: Ue 150x60x20x3,00.
                nums = re.findall(r'\d+(?:[,.]\d+)?', name)
                if len(nums) < 4:
                    raise ValueError(f'UE sem largura de enrijecedor identificável: {name}')
                lip = _number(nums[-2])
            if 'LAMINADO' in fam:
                note += ' Espessura de mesa aproximada pela espessura informada da alma; dimensões industriais não comprovadas.'
            if not (h > 2*t > 0 and w > t and (not lip or 0 < lip < h/2-2*t)):
                raise ValueError(f'Dimensões incompatíveis para renderização: {name}')
            result[name] = ProfileShape(name,fam,h,w,t,lip,row.get('origem',''),note)
    return result


def section_polygon(shape: ProfileShape) -> tuple[tuple[float,float], ...]:
    """Contorno fechado simples (sem repetir o ponto inicial) no plano local u/v."""
    h,w,t = shape.height,shape.flange,shape.thickness
    if shape.family.startswith('L'):
        outline = ((0,0),(w,0),(w,t),(t,t),(t,h),(0,h))
    elif shape.family.startswith('UE'):
        lip = shape.lip
        outline = ((0,0),(w,0),(w,t+lip),(w-t,t+lip),(w-t,t),
                   (t,t),(t,h-t),(w-t,h-t),(w-t,h-t-lip),
                   (w,h-t-lip),(w,h),(0,h))
    else:
        outline = ((0,0),(w,0),(w,t),(t,t),(t,h-t),(w,h-t),(w,h),(0,h))
    if polygon_area(outline)<=0:
        raise ValueError('Polígono da seção com orientação inválida')
    return outline


def polygon_area(points: Sequence[tuple[float,float]]) -> float:
    return sum(points[i][0]*points[(i+1)%len(points)][1]
               -points[(i+1)%len(points)][0]*points[i][1] for i in range(len(points)))/2


def polygon_centroid(points: Sequence[tuple[float,float]]) -> tuple[float,float]:
    a=polygon_area(points)
    if abs(a)<1e-9: raise ValueError('Polígono degenerado')
    cx=sum((points[i][0]+points[(i+1)%len(points)][0])*
           (points[i][0]*points[(i+1)%len(points)][1]-points[(i+1)%len(points)][0]*points[i][1])
           for i in range(len(points)))/(6*a)
    cy=sum((points[i][1]+points[(i+1)%len(points)][1])*
           (points[i][0]*points[(i+1)%len(points)][1]-points[(i+1)%len(points)][0]*points[i][1])
           for i in range(len(points)))/(6*a)
    return cx,cy


def centered_polygon(shape:ProfileShape, angle:float=0, mirror:bool=False):
    raw=section_polygon(shape);cx,cy=polygon_centroid(raw)
    c,s=cos(radians(angle)),sin(radians(angle))
    points=[]
    for u,v in raw:
        u-=cx;v-=cy
        if mirror:u=-u
        points.append((u*c-v*s,u*s+v*c))
    # Espelhamento inverte orientação, portanto restaurar anti-horária.
    if polygon_area(points)<0:points.reverse()
    return tuple(points)


def make_section_layout(shape:ProfileShape,count:int, config:dict|None=None):
    """Retorna (contornos[(u,v)], avisos) para uma ou duas seções.

    Separações explícitas são medidas de CENTROIDE a CENTROIDE. Sem essas
    medidas, utiliza-se posicionamento de CONTATO GRÁFICO, sempre sinalizado.
    """
    cfg=config or {}
    if count not in (1,2):raise ValueError('Renderização aceita 1 ou 2 perfis por barra')
    angle=float(cfg.get('rotation_deg',0))
    if not isfinite(angle):raise ValueError('Rotação inválida')
    first=centered_polygon(shape,angle)
    if count==1:return (first,),()
    kind=str(cfg.get('assembly_type','back_to_back'))
    # O U padrão abre para u positivo. Duas almas encostadas no centro
    # = costas a costas; duas aberturas voltadas ao centro = frente a frente.
    if kind in ('back_to_back','costas_a_costas'):
        first=centered_polygon(shape,angle,mirror=True)
        second=centered_polygon(shape,angle)
    elif kind in ('face_to_face','frente_a_frente'):
        first=centered_polygon(shape,angle)
        second=centered_polygon(shape,angle,mirror=True)
    else:
        second=centered_polygon(shape,angle)
    dx=float(cfg.get('centroid_dx_mm',0) or 0)
    dy=float(cfg.get('centroid_dy_mm',0) or 0)
    if not all(map(isfinite,(dx,dy))):raise ValueError('Espaçamento entre perfis inválido')
    warnings=[]
    if abs(dx)<1e-9 and abs(dy)<1e-9:
        u1=max(u for u,v in first);u2=min(u for u,v in second)
        # Contato gráfico com folga de 6 mm: NÃO é dado de projeto.
        dx=(u1-u2)+6.0
        warnings.append('Separação dupla não declarada: adotada folga GRÁFICA de 6 mm. Defina dx/dy no projeto.')
    out=[]
    for poly,su,sv in ((first,-dx/2,-dy/2),(second,dx/2,dy/2)):
        out.append(tuple((u+su,v+sv) for u,v in poly))
    # Uma distância de centroides muito pequena não pode passar por seção geométrica validada.
    if abs(dx)<shape.thickness and abs(dy)<shape.thickness:
        warnings.append('Componentes duplos podem estar sobrepostos; conferir dx, dy e orientação.')
    return tuple(out),tuple(warnings)


def extrude_member(node_a:tuple[float,float], node_b:tuple[float,float],
                   polygons:Sequence[Sequence[tuple[float,float]]],
                   member_id:str,group:str,profile:str,notes:Sequence[str]=()) -> tuple[Mesh,...]:
    x1,y1=map(float,node_a);x2,y2=map(float,node_b)
    L=hypot(x2-x1,y2-y1)
    if not all(map(isfinite,(x1,y1,x2,y2))) or L<=1e-8:
        raise ValueError('Barra inválida para malha 3D')
    # y2d da seção -> normal local no PLANO XY; x2d -> eixo Z.
    nx,ny=-(y2-y1)/L,(x2-x1)/L
    result=[]
    for component,poly in enumerate(polygons,1):
        n=len(poly)
        if n<3: raise ValueError('Contorno insuficiente')
        vertices=[]
        for cx,cy in ((x1,y1),(x2,y2)):
            for u,v in poly:
                vertices.append((cx+nx*v,cy+ny*v,u))
        # Capas poligonais concavas + faixas laterais. A renderização usa
        # preenchimento por regra even-odd nos contornos; sem buracos.
        faces=[tuple(reversed(tuple(range(n)))),tuple(range(n,2*n))]
        for k in range(n):
            j=(k+1)%n
            faces.append((k,j,j+n,k+n))
        result.append(Mesh(tuple(vertices),tuple(faces),member_id,component,group,profile,tuple(notes)))
    return tuple(result)


def make_model_meshes(model, project:dict, shape_catalog:dict[str,ProfileShape], catalog=None):
    by_id=model.node_map()
    configs=project.get('section_arrangements',{}) or {}
    sections=project.get('sections',{}) or {}
    meshes=[];warnings=[];meta={}
    for m in model.members:
        shape=shape_catalog.get(m.profile)
        if shape is None:
            warnings.append(f'{m.id}: sem definição de contorno para {m.profile}');continue
        spec=sections.get(m.group,{})
        count=int(spec.get('count',1))
        # Modelo CAD explícito guarda área por barra. Quando reconhecível,
        # ela governa a contagem, independentemente de presets por família.
        if model.shape=='explicit' and catalog and m.profile in catalog:
            ref_area=catalog[m.profile].area_mm2
            ratio=m.area/ref_area
            identified=next((n for n in (1,2) if abs(ratio-n)<1e-4),None)
            if identified is not None:
                if identified!=count:
                    warnings.append(f'{m.id}: quantidade no CAD ({identified}) difere do preset do grupo ({count}); exibida a quantidade física do CAD.')
                count=identified
            else:
                warnings.append(f'{m.id}: área no CAD não corresponde a 1 ou 2 perfis do catálogo; o volume é apenas referência visual.')
        if count not in (1,2):
            warnings.append(f'{m.id}: quantidade de componentes não suportada');continue
        cfg=configs.get(m.group,{})
        if not isinstance(cfg,dict):
            warnings.append(f'{m.id}: arranjo inválido');continue
        try:
            polygons,layout_warnings=make_section_layout(shape,count,cfg)
            notes=(shape.note,)+layout_warnings
            a,b=by_id[m.i],by_id[m.j]
            meshes.extend(extrude_member((a.x,a.y),(b.x,b.y),polygons,m.id,m.group,m.profile,notes))
            display_area=sum(polygon_area(p) for p in polygons)
            if m.area>0 and abs(display_area-m.area)/m.area>.08:
                message=f'{m.id}: área desenhada {display_area:.1f} mm² difere de A do solver {m.area:.1f} mm² (geometria idealizada).'
                warnings.append(message)
                notes=tuple(notes)+(message,)
            meta[m.id]={'components':count,'profile':shape.name,'notes':list(notes),
                        'family':shape.family,'area_visual_mm2':display_area,
                        'area_solver_mm2':m.area}
            for note in layout_warnings:warnings.append(f'{m.id}: {note}')
        except (TypeError,ValueError,OverflowError) as exc:
            warnings.append(f'{m.id}: {exc}')
    return meshes,warnings,meta


def triangulate_contour(poly: Sequence[tuple[float,float]]) -> tuple[tuple[int,int,int], ...]:
    """Triangulação ear-clipping para contornos simples côncavos CCW."""
    n=len(poly)
    if n<3 or polygon_area(poly)<=0:
        raise ValueError('Triangulação exige contorno simples anti-horário')
    remaining=list(range(n));faces=[]
    def cross(a,b,c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def inside(a,b,c,p):
        return cross(a,b,p)>=-1e-9 and cross(b,c,p)>=-1e-9 and cross(c,a,p)>=-1e-9
    while len(remaining)>3:
        found=False
        for k in range(len(remaining)):
            a,b,c=(remaining[(k-1)%len(remaining)], remaining[k], remaining[(k+1)%len(remaining)])
            if cross(poly[a],poly[b],poly[c])<=1e-9:continue
            if any(inside(poly[a],poly[b],poly[c],poly[j])
                   for j in remaining if j not in (a,b,c)):
                continue
            faces.append((a,b,c));remaining.pop(k);found=True;break
        if not found:raise ValueError('Contorno sobreposto ou degenerado (triangulação)')
    faces.append(tuple(remaining))
    return tuple(faces)


def export_obj(meshes:Sequence[Mesh],path:Path|str)->None:
    """Exporta seções extrudadas em OBJ (mm), COM CAPAS TRIANGULADAS.

    OBJ tem foco geométrico, não representa propriedades resistentes ou ligações.
    """
    lines=['# 2DTruss v0.1 - perfis extrudados idealizados - UNIDADE: mm',
           '# Sem raios, ligacoes e verificacao estrutural']
    offset=1
    for mesh in meshes:
        verts=mesh.vertices;n=len(verts)//2
        if n<3 or len(verts)!=2*n:raise ValueError('Malha inválida')
        dx=verts[n][0]-verts[0][0];dy=verts[n][1]-verts[0][1]
        length=hypot(dx,dy)
        if length<=0:raise ValueError('Malha sem comprimento')
        nx,ny=-dy/length,dx/length
        anchor=verts[0]
        contour=[(v[2],(v[0]-anchor[0])*nx+(v[1]-anchor[1])*ny) for v in verts[:n]]
        tris=triangulate_contour(contour)
        lines.append(f'o {mesh.member_id}_componente_{mesh.component}')
        lines.extend(f'v {x:.8f} {y:.8f} {z:.8f}' for x,y,z in verts)
        for a,b,c in tris:
            lines.append(f'f {offset+a} {offset+b} {offset+c}')
            lines.append(f'f {offset+n+c} {offset+n+b} {offset+n+a}')
        for k in range(n):
            j=(k+1)%n
            lines.append(f'f {offset+k} {offset+n+j} {offset+j}')
            lines.append(f'f {offset+k} {offset+n+k} {offset+n+j}')
        offset+=len(verts)
    Path(path).write_text('\n'.join(lines)+'\n',encoding='utf-8')


def display_scaled_vertices(mesh:Mesh,node_a:tuple[float,float],node_b:tuple[float,float],factor:float):
    """Multiplica SOMENTE o desenho da seção em torno do eixo analítico.

    A malha persistida e a exportação OBJ jamais sofrem esse exagero.
    """
    factor=float(factor)
    if not isfinite(factor) or not 1<=factor<=10:
        raise ValueError('Exagero visual deve estar entre 1 e 10')
    n=len(mesh.vertices)//2
    out=[]
    for idx,(x,y,z) in enumerate(mesh.vertices):
        base=node_a if idx<n else node_b
        out.append((base[0]+(x-base[0])*factor,
                    base[1]+(y-base[1])*factor,z*factor))
    return tuple(out)
