"""CLI auditável: execução, geração de benchmarks e confronto posterior FTool."""
from __future__ import annotations
import argparse
import hashlib
import json
import csv
from pathlib import Path
from .catalog import load_catalog
from .engine import run_project
from .design import suggest_sections
from .export import ftool_rows,as_csv,comparison_rows,dimperfil_rows,report_html,ftool_comparison_full_rows,load_audit_rows,stability_rows,axial_screen_rows,section_properties_rows

ROOT=Path(__file__).resolve().parent.parent


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def export_ftool(project_path:Path,out:Path,case:str):
    project=load(project_path)
    result=run_project(project,load_catalog(ROOT/'catalogo_perfis.csv'))
    if case not in result['analyses']:
        raise ValueError(f'Estado {case} não encontrado em {project_path.name}')
    out.mkdir(parents=True,exist_ok=True)
    rows=ftool_rows(result,case)
    for name,data in rows.items():
        if name!='supports': (out/f'{name}.csv').write_text(as_csv(data),encoding='utf-8')
    (out/'supports.json').write_text(json.dumps(rows['supports'],indent=2,ensure_ascii=False),encoding='utf-8')
    (out/'ftool_comparacao_PREENCHER.csv').write_text(as_csv(comparison_rows(result,case)),encoding='utf-8')
    (out/'FTool_CONFRONTO_COMPLETO.csv').write_text(as_csv(ftool_comparison_full_rows(result,case)),encoding='utf-8')
    (out/'referencia_POE.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    canonical=json.dumps({'model':result['model'],'loads':result['analyses'][case]['loads'],
                          'case':case},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    manifest={'schema':'poe-ftool-manifest/v1','reference_case':case,
              'sha256_model_and_loads':hashlib.sha256(canonical).hexdigest(),
              'units':{'coordinates':'m','force':'kN','solver':'N-mm-MPa','kgf_nominal_n':10},
              'nodes':len(result['model']['nodes']),'members':len(result['model']['members']),
              'ftool_native_model_generated':False,
              'external_ftool_result_status':'PENDENTE',
              'notice':'CSV para construção manual do modelo; NÃO é arquivo .ftl nativo nem resultado FTool.'}
    (out/'manifesto_ftool.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'INSTRUCOES_FTOOL.txt').write_text(
        'FTool: reproduza coordenadas e barras dos CSV; configure E = '+str(project['material']['E_MPa'])+' MPa.\n'
        'Modele BARRAS ARTICULADAS e forças nodais fx/fy de nodes.csv.\n'
        'Apoios fixados em supports.json (UX/ UY). A tabela apresenta resultados POE, NÃO FTool.\n'
        'No FTool, compare forças N em kN (+ tração, - compressão; conferir convenção do FTool),\n'
        'reações e deslocamentos em mm. Preencha ftool_comparacao_PREENCHER.csv.\n'
        'Para esforços, deslocamentos e reações preencher FTool_CONFRONTO_COMPLETO.csv.\n'
        'A comparação numérica deve ser formalizada com `python -m poe_truss.cli compare ...`.\n',encoding='utf-8')
    return result


def compare_ftool(path:Path,relative_percent:float=.10,absolute_kn:float=.01):
    """Só aprova valores efetivamente preenchidos a partir do FTool."""
    with open(path,encoding='utf-8-sig',newline='') as fh:
        rows=list(csv.DictReader(fh,delimiter=';'))
    if not rows:raise ValueError('Tabela vazia')
    full='valor_POE' in rows[0]
    results=[]
    for r in rows:
        name=(r['tipo']+':'+r['identificador']+':'+r['componente']) if full else r['member']
        field='valor_FTOOL_PREENCHER' if full else 'N_kN_FTOOL_PREENCHER'
        value=str(r.get(field,'')).strip()
        if not value:raise ValueError(f'FTool não fornecido para {name}; comparação pendente')
        expected=float(str(r['valor_POE'] if full else r['N_kN_POE']).replace(',','.'))
        actual=float(value.replace(',','.'))
        error=abs(expected-actual)
        rel=float(r['tolerancia_rel_percent']) if full else relative_percent
        absolute=float(r['tolerancia_abs']) if full else absolute_kn
        tolerance=max(absolute,rel/100*max(abs(actual),abs(expected)))
        results.append({'identificador':name,'unidade':r['unidade'] if full else 'kN',
             'valor_poe':expected,'valor_ftool':actual,'erro_absoluto':error,
             'tolerancia_absoluta':tolerance,'aprovado':error<=tolerance})
    return results


def main():
    parser=argparse.ArgumentParser(description='2DTruss — motor Python / FTool')
    sub=parser.add_subparsers(dest='command',required=True)
    a=sub.add_parser('run',help='executa JSON e grava saída auditável');a.add_argument('project');a.add_argument('--out','-o',default='saida_POE.json')
    b=sub.add_parser('ftool',help='exporta tabelas de modelo para benchmark FTool');b.add_argument('project');b.add_argument('--case',required=True);b.add_argument('--out','-o',default='benchmark_ftool')
    c=sub.add_parser('compare',help='compara valores introduzidos do FTool');c.add_argument('csv');c.add_argument('--out','-o',default='comparacao_ftool.json')
    e=sub.add_parser('audit',help='exporta rastreio de cargas nodais por parcela');e.add_argument('project');e.add_argument('--case',required=True);e.add_argument('--out','-o',default='auditoria_cargas.csv')
    f=sub.add_parser('stability',help='exporta dados de estabilidade declarados');f.add_argument('project');f.add_argument('--out','-o',default='estabilidade_barras.csv')
    g=sub.add_parser('axial',help='triagem axial — NÃO equivalente ao ELU normativo');g.add_argument('project');g.add_argument('--out','-o',default='triagem_axial.csv')
    h=sub.add_parser('sections',help='propriedades geométricas de perfis simples e duplos');h.add_argument('project');h.add_argument('--out','-o',default='secoes.csv')
    i=sub.add_parser('optimize',help='pesquisa ELS/massa sem dimensionamento ELU');i.add_argument('project');i.add_argument('--options');i.add_argument('--out','-o',default='otimizacao.json')
    d=sub.add_parser('dimperfil',help='exporta relação de solicitações');d.add_argument('project');d.add_argument('--out','-o',default='dimperfil.csv')
    args=parser.parse_args()
    if args.command=='compare':
        rows=compare_ftool(Path(args.csv))
        Path(args.out).write_text(json.dumps(rows,indent=2,ensure_ascii=False),encoding='utf-8')
        passed=sum(r['aprovado'] for r in rows)
        print(f'FTool comparados: {passed}/{len(rows)} aprovados. Arquivo: {args.out}')
        raise SystemExit(0 if passed==len(rows) else 2)
    if args.command=='ftool':
        result=export_ftool(Path(args.project),Path(args.out),args.case)
        print(f'FTool: pacote de dados exportado para {args.out}; execução EXTERNA pendente.')
        return
    data=load(args.project)
    if args.command=='optimize':
        options=load(args.options) if args.options else {}
        outcome=suggest_sections(data,load_catalog(ROOT/'catalogo_perfis.csv'),options)
        Path(args.out).write_text(json.dumps(outcome,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f"Pesquisa: {outcome['evaluated']} alternativas, sem aprovação ELU -> {args.out}")
        return
    r=run_project(data,load_catalog(ROOT/'catalogo_perfis.csv'))
    if args.command=='audit':
        if args.case not in r['load_audit']:raise ValueError('Caso de auditoria inexistente')
        Path(args.out).write_text(as_csv(load_audit_rows(r,args.case)),encoding='utf-8')
        print(f'Auditoria {args.case}: {args.out}')
        return
    if args.command=='stability':
        Path(args.out).write_text(as_csv(stability_rows(r)),encoding='utf-8')
        print(f'Estabilidade declarada: {args.out}')
        return
    if args.command=='axial':
        Path(args.out).write_text(as_csv(axial_screen_rows(r)),encoding='utf-8')
        print(f'Triagem axial: {args.out} (SEM ELU normativo)')
        return
    if args.command=='sections':
        Path(args.out).write_text(as_csv(section_properties_rows(r)),encoding='utf-8')
        print(f'Propriedades: {args.out} (geometria elástica)')
        return
    if args.command=='run':
        Path(args.out).write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f"{len(r['model']['members'])} barras, {len(r['analyses'])} estados calculados → {args.out}")
    else:
        Path(args.out).write_text(as_csv(dimperfil_rows(r)),encoding='utf-8')
        print(f'DimPerfil: {len(r["model"]["members"])} barras → {args.out}')

if __name__=='__main__':main()
