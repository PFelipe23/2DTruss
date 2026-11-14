"""v0.4–0.6 — triagem de solicitações axiais, SEM dimensionamento normativo.

NÃO representa conformidade à NBR 14762:10 ou NBR 8800:24. Calcula:
(1) solicitação/força de escoamento bruto preliminar;
(2) carga crítica de Euler de eixo principal informado, apenas como alerta;
(3) utilização de resistências externas declaradas e rastreadas.
Instabilidade local, distorcional, flexo-torcional e ligações não implementadas.
"""
from __future__ import annotations
from math import isfinite, pi


def positive(value,label):
    x=float(value)
    if not isfinite(x) or x<=0:raise ValueError(f'{label} deve ser positivo e finito')
    return x


def axial_screen(project:dict, model:dict, envelope:dict, stability:dict, sections:dict)->dict:
    mat=project.get('material',{})
    fy=positive(mat.get('fy_MPa',250),'fy_MPa')
    E=positive(mat.get('E_MPa',200000),'E_MPa')
    # gamma é parâmetro fornecido pelo projetista, NÃO coeficiente normativo validado.
    gamma=positive(project.get('axial_options',{}).get('gamma_yield_screen',1.10),'gamma_yield_screen')
    capacities=project.get('external_resistances',{}) or {}
    if not isinstance(capacities,dict):raise ValueError('external_resistances deve ser objeto')
    entries=capacities.get('members',{}) or {}
    if not isinstance(entries,dict):raise ValueError('external_resistances.members deve ser objeto')
    member_ids={m['id'] for m in model['members']}
    if set(entries)-member_ids:raise ValueError(f'Resistências externas citam barras inexistentes: {sorted(set(entries)-member_ids)}')
    rows={}; stat={'total':len(member_ids),'external_declared':0,'external_missing':0,
                  'external_exceeds':0,'euler_warning':0,'no_global_geometry':0}
    for m in model['members']:
        mid=m['id'];env=envelope[mid];st=stability['members'][mid];sec=sections['members'][mid]
        nt=env['max_tension_n'];nc=abs(env['max_compression_n'])
        area=positive(m['area_mm2'],f'{mid}.area_mm2')
        Ny=area*fy/gamma
        cands=[]
        for axis,L_key,I_key in [('in_plane','effective_in_plane_mm','ix_mm4'),('out_of_plane','effective_out_of_plane_mm','iy_mm4')]:
            # Eixos da estabilidade devem coincidir com o eixo de seção declarado.
            associated=st.get('axis_in_plane' if axis=='in_plane' else 'axis_out_of_plane')
            relevant='x' if I_key=='ix_mm4' else 'y'
            inertia=sec.get('ix_mm4' if associated=='x' else 'iy_mm4')
            length=st.get(L_key)
            if length and associated in ('x','y') and inertia and sec.get('state')=='GEOMETRIA_ELASTICA_CALCULADA':
                ncr=pi*pi*E*inertia/(length*length)
                cands.append({'mode':axis,'reference_axis':associated,'length_mm':length,
                              'euler_critical_n':ncr})
        min_euler=min((x['euler_critical_n'] for x in cands),default=None)
        euler_warning=bool(min_euler is not None and nc>min_euler)
        if euler_warning:stat['euler_warning']+=1
        if len(cands)!=2:stat['no_global_geometry']+=1
        ext=entries.get(mid)
        external={'state':'NAO_INFORMADA','utilization':None,'tension_utilization':None,
                  'compression_utilization':None,'source':None}
        if ext is not None:
            if not isinstance(ext,dict):raise ValueError(f'{mid}: resistência externa inválida')
            source=str(ext.get('source','')).strip()
            profile=str(ext.get('profile','')).strip()
            if not source or not profile:
                raise ValueError(f'{mid}: informe source e profile na resistência externa')
            if profile!=m['profile']:
                raise ValueError(f'{mid}: resistência externa do perfil {profile} não corresponde ao modelo {m["profile"]}')
            tr=ext.get('tension_rd_n');cr=ext.get('compression_rd_n')
            if nt>0 and tr is None:raise ValueError(f'{mid}: resistência à tração externa ausente')
            if nc>0 and cr is None:raise ValueError(f'{mid}: resistência à compressão externa ausente')
            tr=positive(tr,f'{mid}.tension_rd_n') if tr is not None else None
            cr=positive(cr,f'{mid}.compression_rd_n') if cr is not None else None
            ut=nt/tr if tr else None;uc=nc/cr if cr else None
            utilization=max([v for v in (ut,uc) if v is not None],default=None)
            external={'state':'DECLARADA_PELO_PROJETISTA','utilization':utilization,
                      'tension_utilization':ut,'compression_utilization':uc,'source':source,
                      'tension_rd_n':tr,'compression_rd_n':cr,
                      'note':'A procedência foi declarada; o software NÃO certifica o cálculo externo.'}
            stat['external_declared']+=1
            if utilization is not None and utilization>1:stat['external_exceeds']+=1
        else:stat['external_missing']+=1
        rows[mid]={
           'member_id':mid,'profile':m['profile'],'group':m['group'],
           'tension_sd_n':nt,'compression_sd_n':nc,
           'gross_yield_screen_n':Ny,'gross_yield_ratio':nt/Ny if Ny else None,
           'gross_yield_screen_exceeded':nt>Ny,
           'euler_modes':cands,'euler_min_n':min_euler,'euler_critical_exceeded':euler_warning,
           'local_buckling':'NAO_VERIFICADA','distortional_buckling':'NAO_VERIFICADA',
           'flexural_torsional_buckling':'NAO_VERIFICADA',
           'net_section_fracture':'NAO_VERIFICADA','connections':'NAO_VERIFICADAS',
           'verification_status':'NAO_VERIFICADO_NORMATIVAMENTE',
           'external_capacity':external,
        }
    return {'schema':'poe-axial-screen/v1','members':rows,'summary':stat,
            'fy_mpa':fy,'gamma_yield_screen_user_defined':gamma,
            'warning':'Triagem informativa; não determina N_Rd da NBR 14762, não libera uso executivo ou aprovação ELU.'}
