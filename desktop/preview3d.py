"""Geometria 3D esquemática e projeção, sem dependências gráficas.

A estrutura permanece exclusivamente no plano XY. O volume exibido é
apenas ENVELOPE PRISMÁTICO ILUSTRATIVO, sem perfis CFF detalhados nem solver 3D.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import cos,sin,radians,hypot,isfinite

@dataclass(frozen=True)
class Camera:
    yaw_deg:float=30.0
    elevation_deg:float=22.0


def project(point, camera:Camera):
    x,y,z=(float(v) for v in point)
    if not all(isfinite(v) for v in (x,y,z)):
        raise ValueError('Projeção 3D requer valores finitos')
    return camera_projection(camera)((x, y, z))


def camera_projection(camera: Camera):
    """Precalcula a rotação para projeção em lote de vértices já validados."""
    a, b = radians(camera.yaw_deg), radians(camera.elevation_deg)
    if not isfinite(a) or not isfinite(b):
        raise ValueError('A câmera requer ângulos finitos')
    ca, sa, cb, sb = cos(a), sin(a), cos(b), sin(b)

    def transform(point):
        x, y, z = point
        zr = x * sa + z * ca
        return x * ca - z * sa, zr * sb - y * cb, y * sb + zr * cb

    return transform


def unproject(point, camera):
    """Inverte a projeção ortográfica de uma posição com profundidade conhecida."""
    x, y, z = point
    a, b = radians(camera.yaw_deg), radians(camera.elevation_deg)
    zr = y * sin(b) + z * cos(b)
    return (x * cos(a) + zr * sin(a), z * sin(b) - y * cos(b),
            zr * cos(a) - x * sin(a))


def member_prism(node_a,node_b, thickness=60., depth=160.):
    """8 pontos de volume ao redor do eixo real XY (somente visualização)."""
    x1,y1=node_a; x2,y2=node_b
    L=hypot(x2-x1,y2-y1)
    if not isfinite(L) or L<=0:raise ValueError('Barra 3D com comprimento inválido')
    if thickness<=0 or depth<=0:raise ValueError('Espessura visual inválida')
    px=-(y2-y1)/L*thickness/2
    py=(x2-x1)/L*thickness/2
    return [(x+sgn*px,y+sgn*py,z) for x,y in ((x1,y1),(x2,y2))
            for sgn in (-1,1) for z in (-depth/2,depth/2)]


def prism_faces(vertices):
    """Faces indexadas nos 8 vértices: extremidades, laterais e superiores."""
    faces=((0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3))
    return [tuple(vertices[i] for i in face) for face in faces]


def family_key(member,catalog):
    profile=catalog.get(member.profile)
    return profile.family if profile else member.profile


def palette_keys(model,catalog,mode='group',axial=None):
    if mode=='family':return sorted({family_key(m,catalog) for m in model.members})
    if mode=='force':return ['Tração','Compressão','Nulo / não calculado']
    return sorted({m.group for m in model.members})


def color_key(member,catalog,mode='group',axial=None):
    if mode=='family':return family_key(member,catalog)
    if mode=='force':
        n=(axial or {}).get(member.id)
        return 'Tração' if n is not None and n>1e-7 else 'Compressão' if n is not None and n< -1e-7 else 'Nulo / não calculado'
    return member.group
