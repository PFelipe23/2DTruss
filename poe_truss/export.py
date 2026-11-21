"""Exportações rastreáveis para comparação com FTool e DimPerfil.

FTool deve ser modelado/comparado externamente; a exportação CSV é um
intercâmbio neutro, NÃO é um arquivo nativo FTool.
"""
from __future__ import annotations
import csv
import io
from html import escape


def as_csv(rows:list[dict]):
    if not rows:return ''
    buffer=io.StringIO(newline='')
    writer=csv.DictWriter(buffer,fieldnames=list(rows[0]),delimiter=';')
    writer.writeheader()
    # Evita execução de fórmulas por planilhas ao abrir CSVs com entradas
    # fornecidas pelo usuário (nome, observações, fonte externa etc.).
    def safe_cell(value):
        if not isinstance(value,str):return value
        stripped=value.lstrip(' \t\r\n')
        if stripped.startswith(('=','+','@')) or (stripped.startswith('-') and not stripped[1:].replace('.','',1).isdigit()):
            return "'"+value
        return value
    for row in rows:writer.writerow({k:safe_cell(v) for k,v in row.items()})
    return '\ufeff'+buffer.getvalue()


def axial_screen_rows(result:dict):
    rows=[]
    for mid,v in result['axial_screen']['members'].items():
        x=v['external_capacity']
        rows.append({'barra':mid,'perfil':v['profile'],'grupo':v['group'],
            'Nsd_tracao_kN':round(v['tension_sd_n']/1000,6),
            'Nsd_compressao_kN':round(v['compression_sd_n']/1000,6),
            'Ny_bruto_PRELIMINAR_kN':round(v['gross_yield_screen_n']/1000,6),
            'Ncr_Euler_REFERENCIAL_kN':round(v['euler_min_n']/1000,6) if v['euler_min_n'] else '',
            'alerta_Euler':v['euler_critical_exceeded'],
            'alerta_escoamento_bruto':v['gross_yield_screen_exceeded'],
            'indice_externo_DECLARADO':x.get('utilization') if x else '',
            'fonte_externa':x.get('source') or '',
            'status_ELU':'NAO_VERIFICADO_NORMATIVAMENTE'})
    return rows


def section_properties_rows(result:dict):
    return [{'barra':mid,'perfil':v.get('profile',''),'area_mm2':v.get('area_mm2'),
             'Ix_mm4':v.get('ix_mm4'),'Iy_mm4':v.get('iy_mm4'),'Ixy_mm4':v.get('ixy_mm4'),
             'rx_mm':v.get('rx_mm'),'ry_mm':v.get('ry_mm'),'status':v['state'],
             'ligacao_solidaria_verificada':False}
            for mid,v in result['section_properties']['members'].items()]

def camber_rows(result:dict):
    return result['camber'].get('nodes',[])


def integrated_report_html(result:dict,project:dict,analysis_id:str)->str:
    """Memorial HTML A3 com triagem e contraflecha, SEM aprovação normativa."""
    original=report_html(result,project,analysis_id)
    from html import escape as esc
    r=result['axial_screen']
    rows=axial_screen_rows(result)
    c=result['camber']
    status=f"{r['summary']['external_declared']} resistências externas declaradas; {r['summary']['external_missing']} pendentes"
    table=''.join('<tr>'+''.join(f'<td>{esc(str(v))}</td>' for v in list(row.values()))+'</tr>' for row in rows)
    th=''.join(f'<th>{esc(str(k))}</th>' for k in rows[0]) if rows else ''
    add=(f'<section class="poe-v09" style="page-break-before:always;padding:18px">'
         f'<h1>ANEXO TÉCNICO v0.1</h1><h2>Triagem axial — não é ELU normativo</h2>'
         f'<p><strong>{esc(status)}</strong>. Escoamento bruto e Euler são referências informativas.</p>'
         f'<p><strong>Compressão:</strong> instabilidades local, distorcional, flexo-torcional e ligações NÃO verificadas.</p>'
         f'<div style="overflow:auto"><table style="border-collapse:collapse;width:100%;font-size:8px"><thead><tr>{th}</tr></thead><tbody>{table}</tbody></table></div>'
         f'<h2>Contraflecha indicativa</h2><p>Caso: {esc(str(c.get("reference_case")))}. Estado: {esc(c["state"])}. '
         f'Máxima: {c.get("max_abs_camber_mm",0):.3f} mm.</p><p>{esc(c["warning"])}</p>'
         f'<p>FTool: validação cruzada externa pendente. NBR 14762 e NBR 8800: dimensionamento resistente não comprovado.</p></section>')
    local = result['analyses'][analysis_id].get('member_flexure', {})
    if local:
        rows = ''.join(
            f'<tr><td>{escape(member)}</td><td>{values["shear_i_n"] / 1000:+.3f}</td>'
            f'<td>{values["shear_j_n"] / 1000:+.3f}</td><td>{values["moment_mid_nmm"] / 1e6:+.3f}</td></tr>'
            for member, values in local.items()
        )
        add += ('<section><h2>Cortante e momento locais</h2>'
                '<p>Barras biapoiadas com carga uniforme, no eixo local i → j.</p>'
                '<table><thead><tr><th>Barra</th><th>V(i) kN</th><th>V(j) kN</th>'
                '<th>M no meio kN·m</th></tr></thead><tbody>' + rows + '</tbody></table></section>')
    if '</body>' in original:
        return original.replace('</body>',add+'</body>')
    return original.replace('</html>',add+'</html>') if '</html>' in original else original+add


def dimperfil_rows(result:dict):
    result_rows=[]
    env=result['envelope']
    for m in result['model']['members']:
        r=env[m['id']]
        stab=result.get('stability',{}).get('members',{}).get(m['id'],{})
        result_rows.append({
            'barra':m['id'],'no_i':m['i'],'no_j':m['j'],
            'grupo':m['group'],'perfil':m['profile'],'area_mm2':round(m['area_mm2'],5),
            'comprimento_mm':round(m['length_mm'],3),'massa_kg_m':round(m['mass_kg_m'],5),
            'N_tracao_max_kgf':round(r['max_tension_n']/10,3),
            'N_compressao_min_kgf':round(r['max_compression_n']/10,3),
            'combinacao_tracao':r['tension_case'] or '',
            'combinacao_compressao':r['compression_case'] or '',
            'comprimento_efetivo_plano_mm':stab.get('effective_in_plane_mm'),
            'comprimento_efetivo_fora_plano_mm':stab.get('effective_out_of_plane_mm'),
            'eixo_plano':stab.get('axis_in_plane'),
            'eixo_fora_plano':stab.get('axis_out_of_plane'),
            'travamento_status':stab.get('state'),
            'Nrd_tracao_kgf_INSERIR':'','Nrd_compressao_kgf_INSERIR':'',
            'utilizacao_INSERIR':'','observacao':'SEM VERIFICACAO RESISTENTE'})
    return result_rows


def ftool_rows(result:dict,analysis_id:str):
    model=result['model'];case=result['analyses'][analysis_id]
    nodes=[{
        'node':n['id'],'x_m':round(n['x_mm']/1000,7),'y_m':round(n['y_mm']/1000,7),
        'fx_kN':round(case['loads'][n['id']]['fx_n']/1000,7),
        'fy_kN':round(case['loads'][n['id']]['fy_n']/1000,7),
        'ux_mm_POE':round(case['nodal_displacements'][n['id']]['ux_mm'],8),
        'uy_mm_POE':round(case['nodal_displacements'][n['id']]['uy_mm'],8)} for n in model['nodes']]
    members=[{'member':m['id'],'node_i':m['i'],'node_j':m['j'],
              'area_cm2':round(m['area_mm2']/100,8),
              'length_m':round(m['length_mm']/1000,8),
              'N_kN_POE':round(case['axial_n'][m['id']]/1000,8)} for m in model['members']]
    reactions=[]
    for n,v in case['reactions'].items():
        reactions.append({'node':n,'rx_kN_POE':round(v['fx_n']/1000,8),'ry_kN_POE':round(v['fy_n']/1000,8)})
    return {'nodes':nodes,'members':members,'reactions':reactions,'supports':model['supports']}


def comparison_rows(result:dict,analysis_id:str):
    """Gera template CSV para preenchimento manual da resposta do FTool."""
    case=result['analyses'][analysis_id]
    return [{'member':m['id'],'N_kN_POE':round(case['axial_n'][m['id']]/1000,8),
             'N_kN_FTOOL_PREENCHER':'','erro_rel_percent_CALCULAR':''}
            for m in result['model']['members']]



def ftool_comparison_full_rows(result:dict,analysis_id:str):
    """Todos os esforços normais, deslocamentos UX/UY e reações de apoio.

    Valores do FTool intencionalmente vazios: devem ser preenchidos pelo usuário.
    """
    c=result['analyses'][analysis_id]
    rows=[]
    def add(kind,key,component,value,unit,relative,absolute):
        rows.append({'tipo':kind,'identificador':key,'componente':component,
          'valor_POE':round(value,9),'valor_FTOOL_PREENCHER':'',
          'unidade':unit,'tolerancia_rel_percent':relative,'tolerancia_abs':absolute})
    for m in result['model']['members']:
        add('barra',m['id'],'N',c['axial_n'][m['id']]/1000,'kN',.1,.01)
    for node,d in c['nodal_displacements'].items():
        add('deslocamento',node,'UX',d['ux_mm'],'mm',.5,.02)
        add('deslocamento',node,'UY',d['uy_mm'],'mm',.5,.02)
    for node,d in c['reactions'].items():
        add('reacao',node,'RX',d['fx_n']/1000,'kN',.1,.01)
        add('reacao',node,'RY',d['fy_n']/1000,'kN',.1,.01)
    return rows

def report_html(result:dict, project:dict, analysis_id:str):
    """Memorial auto-contido com impressão em A3 horizontal (HTML -> PDF navegador)."""
    model=result['model'];case=result['analyses'][analysis_id]
    nodes={n['id']:n for n in model['nodes']}
    xs=[n['x_mm'] for n in nodes.values()];ys=[n['y_mm'] for n in nodes.values()]
    xl=min(xs);xr=max(xs);yb=min(ys);yt=max(ys)
    scale=min(1380/max(1.,xr-xl),400/max(1.,yt-yb))
    fx=lambda x:75+(x-xl)*scale
    fy=lambda y:520-(y-yb)*scale
    segments=[]
    for m in model['members']:
        a,b=nodes[m['i']],nodes[m['j']]
        N=case['axial_n'][m['id']]/10
        color='#a52331' if N>1e-7 else '#15629c' if N < -1e-7 else '#657383'
        mx=(fx(a['x_mm'])+fx(b['x_mm']))/2
        my=(fy(a['y_mm'])+fy(b['y_mm']))/2
        segments.append(f'<line x1="{fx(a["x_mm"]):.1f}" y1="{fy(a["y_mm"]):.1f}" x2="{fx(b["x_mm"]):.1f}" y2="{fy(b["y_mm"]):.1f}" stroke="{color}" stroke-width="3"/>')
        segments.append(f'<text x="{mx:.1f}" y="{my-5:.1f}" fill="{color}" font-size="10" text-anchor="middle">{N:.1f}</text>')
    for n in model['nodes']:
        segments.append(f'<circle cx="{fx(n["x_mm"]):.1f}" cy="{fy(n["y_mm"]):.1f}" r="2.6" fill="#1e293b"/>')
    svg=f'<svg viewBox="0 0 1550 620" xmlns="http://www.w3.org/2000/svg">{"".join(segments)}</svg>'
    rows=[]
    for m in model['members']:
        e=result['envelope'][m['id']]
        rows.append('<tr>'+''.join('<td>'+escape(str(t))+'</td>' for t in [m['id'],m['group'],m['profile'],
            f"{m['length_mm']/1000:.3f}",f"{e['max_compression_n']/10:.1f}", f"{e['max_tension_n']/10:.1f}",
            e['compression_case'] or '—',e['tension_case'] or '—'])+'</tr>')
    warning='; '.join(result['warnings'])
    audit=result.get('load_audit',{}).get(analysis_id,{})
    stable=result.get('stability',{}).get('members',{})
    stability_html=''.join('<tr>'+''.join('<td>'+escape(str(v if v is not None else '—'))+'</td>' for v in [
        m['id'],stable.get(m['id'],{}).get('effective_in_plane_mm'),
        stable.get(m['id'],{}).get('effective_out_of_plane_mm'),
        stable.get(m['id'],{}).get('state','N/D')])+'</tr>' for m in model['members'])
    return f'''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Memorial — {escape(project.get('name','Treliça'))}</title>
<style>@page{{size:A3 landscape;margin:11mm}}body{{font:12px Arial,sans-serif;color:#172337;margin:0}}h1{{font-size:21px}}h2{{font-size:14px;margin:12px 0}}.muted{{color:#526577}}svg{{width:100%;height:310px;border:1px solid #d8dfe8}}table{{border-collapse:collapse;width:100%;font-size:10px}}th,td{{border:1px solid #b5beca;padding:4px 6px;text-align:left}}th{{background:#e7eef5}}.bad{{font-size:10px;color:#7c3f28}}header{{border-bottom:3px solid #0b72b9;padding-bottom:9px}}.tag{{float:right}}@media print{{.noprint{{display:none}}}}</style>
<header><span class="tag">2DTRUSS · MOTOR PYTHON v0.1</span><h1>{escape(project.get('name','Treliça'))}</h1><div class="muted">Análise: {escape(analysis_id)} · Valores nas barras em kgf nominais (10 N/kgf) · Tração (+) / Compressão (−)</div></header>
<h2>Diagrama de esforços normais — referência de apresentação: Olídio, figuras 198–199</h2>{svg}
<h2>Envoltória por barra — solicitações obtidas das combinações informadas</h2><table><thead><tr><th>Barra</th><th>Grupo</th><th>Seção</th><th>Compr. (m)</th><th>N mín. (kgf)</th><th>N máx. (kgf)</th><th>Comp.</th><th>Tração</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<h2>Auditoria de cargas</h2><p>Estado: {escape(audit.get('status','N/D'))} · ΣFx: {audit.get('sum_fx_n',0)/1000:.3f} kN · ΣFy: {audit.get('sum_fy_n',0)/1000:.3f} kN. Conferência algébrica apenas; consulte o CSV de parcelas.</p>
<h2>Comprimentos efetivos declarados — sem verificação de resistência</h2><table><thead><tr><th>Barra</th><th>Leff no plano (mm)</th><th>Leff fora plano (mm)</th><th>Estado</th></tr></thead><tbody>{stability_html}</tbody></table>
<h2>Observações e limitações</h2><p class="bad">{escape(warning)}</p>
<p class="muted">Documento de análise e pré-dimensionamento. Sem verificação resistente normativa. FTool: validação comparativa externa pendente.</p>
<button class="noprint" onclick="print()">Imprimir / salvar PDF</button></html>'''


def load_audit_rows(result:dict,analysis_id:str):
    """CSV por parcela; combos expandidas por caso e nó."""
    a=result['load_audit'][analysis_id]
    keys=('combo_id','case_id','factor','origin','source','node','fx_n','fy_n','moment_origin_nmm',
          'member_id','kind','input_value','input_force_unit','basis','direction',
          'reference_length_mm','frame_spacing_mm')
    rows=a.get('entries',a.get('nodal_parcels',[]))
    return [{key:row.get(key,'') for key in keys} for row in rows]


def stability_rows(result:dict):
    output=[]
    for m in result['model']['members']:
        item=result['stability']['members'][m['id']]
        output.append({key:(('|'.join(v)) if isinstance(v,list) else v)
            for key,v in item.items() if key!='radii_reference_mm'})
    return output
