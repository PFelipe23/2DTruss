"""v0.7 — propriedades elásticas de conjuntos de perfis, auditáveis.

O catálogo só fornece Ix/Iy; Ixy e propriedades torsionais não são conhecidos.
Não inferir solidarização à compressão/flambagem de seções duplas. O solver
plano usa apenas a soma das áreas e, portanto, permanece inalterado.
"""
from __future__ import annotations
from math import isfinite, sqrt


def _number(v, name):
    x=float(v)
    if not isfinite(x):
        raise ValueError(f'{name}: valor não finito')
    return x


def section_properties(model, project:dict, catalog:dict)->dict:
    """Propriedades geométricas calculadas sem presumir Ixy nem ligação solidária.

    centroid_dx_mm/dy_mm são distâncias entre os *centroides* dos dois
    componentes; não são a distância entre faces nem dimensão de espaçador.
    Para usar Ix/Iy de catálogo, rotações de 0/90/180/-90 graus são suportadas.
    """
    configs=project.get('section_arrangements',{}) or {}
    if not isinstance(configs,dict):raise ValueError('section_arrangements deve ser objeto')
    result={}
    warnings=[]
    for m in model.members:
        spec=(project.get('sections',{}) or {}).get(m.group,{}) if model.shape!='explicit' else {}
        count=int(spec.get('count',1))
        profile=catalog.get(m.profile)
        if model.shape=='explicit' and profile is not None:
            ratio=m.area/profile.area_mm2 if profile.area_mm2>0 else 0
            if any(abs(ratio-x)<1e-5 for x in (1,2)):
                count=round(ratio)
            else:
                # Área arbitrária do CAD/modelo explícito não representa um
                # perfil catalogado com número conhecido de componentes.
                count=0
        config=configs.get(m.group,{})
        if not isinstance(config,dict):raise ValueError(f'Arranjo {m.group}: configuração inválida')
        allowed={'centroid_dx_mm','centroid_dy_mm','rotation_deg','connection_reference','assembly_type'}
        if set(config)-allowed:raise ValueError(f'Arranjo {m.group}: campos não reconhecidos: {sorted(set(config)-allowed)}')
        theta=_number(config.get('rotation_deg',0),'rotation_deg')
        if theta not in (0,90,-90,180):
            raise ValueError('Arranjo: apenas rotações ortogonais são suportadas com catálogo Ix/Iy simplificado')
        dx=_number(config.get('centroid_dx_mm',0),'centroid_dx_mm')
        dy=_number(config.get('centroid_dy_mm',0),'centroid_dy_mm')
        if (dx or dy) and count!=2:
            raise ValueError(f'Arranjo {m.group}: deslocamento entre centroides requer 2 perfis')
        if count==2 and dx==0 and dy==0:
            warnings.append(f'{m.group}: dois perfis sem distanciamento de centroides declarado; inércias de seção composta incompletas')
        if profile is None or count==0:
            result[m.id]={'member_id':m.id,'state':'DADOS_GEOMETRICOS_NAO_DISPONIVEIS','area_mm2':m.area}
            continue
        ix=profile.ix_mm4;iy=profile.iy_mm4
        if abs(theta)==90:ix,iy=iy,ix
        A=profile.area_mm2
        # Ixx = sum(Ixx componente + A*d_y^2); centroides +/- d_y/2
        ix_total=count*ix + (A*dy*dy/2 if count==2 else 0.)
        iy_total=count*iy + (A*dx*dx/2 if count==2 else 0.)
        ixy_off=(A*dx*dy/2 if count==2 else 0.)
        unreliable=profile.family.strip().upper().startswith('L')
        if unreliable:
            ixy=None
            state='PARCIAL_Ixy_DESCONHECIDO'
        else:
            ixy=ixy_off
            state='GEOMETRIA_ELASTICA_CALCULADA'
        # Para L, nem mesmo os eixos principais podem ser obtidos sem Ixy.
        assembled_area=count*A
        result[m.id]={
            'member_id':m.id,'group':m.group,'profile':m.profile,'component_count':count,
            'centroid_dx_mm':dx,'centroid_dy_mm':dy,'rotation_deg':theta,
            'assembly_type':str(config.get('assembly_type','single' if count==1 else 'declared_pair')),
            'connection_reference':str(config.get('connection_reference','')),
            'area_mm2':assembled_area,'ix_mm4':ix_total,'iy_mm4':iy_total,
            'ixy_mm4':ixy,'rx_mm':sqrt(ix_total/assembled_area),'ry_mm':sqrt(iy_total/assembled_area),
            'state':state,'connected_as_unit_verified':False,
            'warning':'Ixy original do perfil L não está no catálogo' if unreliable else
                ('Solidarização e estabilidade do conjunto ainda não verificadas' if count==2 else ''),
            'torsional_properties_verified':False,
        }
    return {'schema':'poe-sections/v1','members':result,'warnings':list(dict.fromkeys(warnings)),
            'scope':'Somente propriedades geométricas elásticas; não comprova ação composta, flambagem, torção nem ligações.'}
