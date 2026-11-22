"""Interface local via biblioteca padrão. Não abre portas externas."""
from __future__ import annotations
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import json
import secrets
import time
import webbrowser
import sys
from .catalog import load_catalog
from .engine import run_project
from .model import make_model, geometry_diagnostics
from .loads import load_patterns, resolve_case_loads
from .search import suggest_geometry
from .design import suggest_sections
from .migrate import migrate_v05
from .export import as_csv,dimperfil_rows,ftool_rows,comparison_rows,report_html,ftool_comparison_full_rows,load_audit_rows,stability_rows,axial_screen_rows,section_properties_rows,camber_rows,integrated_report_html

MAX_POST=1_000_000


def run_server(base:Path, open_browser:bool=True)->ThreadingHTTPServer:
    token=secrets.token_urlsafe(32)
    catalog=load_catalog(base/'catalogo_perfis.csv')
    default=json.loads((base/'examples'/'cobertura_duas_aguas.json').read_text(encoding='utf-8'))
    root=base/'web'
    class Handler(BaseHTTPRequestHandler):
        server_version='POE-Trelica-Python'
        def log_message(self,fmt,*args):
            # Nenhum acesso remoto é permitido. Mantemos apenas erros HTTP no terminal.
            if self.path.startswith('/api/') and args and str(args[1])[:1] in ('4','5'):
                sys.stderr.write(f'[HTTP] {fmt%args}\n')
        def respond(self,payload,status=200,ctype='application/json; charset=utf-8'):
            data=payload if isinstance(payload,bytes) else json.dumps(payload,ensure_ascii=False,allow_nan=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type',ctype)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('X-Frame-Options','DENY')
            self.send_header('Referrer-Policy','same-origin')
            self.send_header('Cross-Origin-Resource-Policy','same-origin')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers();self.wfile.write(data)
        def do_GET(self):
            if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
                return self.respond({'error':'Host não autorizado'},403)
            paths={'/':('index.html','text/html; charset=utf-8'),
                   '/style.css':('style.css','text/css; charset=utf-8'),
                   '/app.js':('app.js','application/javascript; charset=utf-8')}
            for module_name in ('nodal','diagram','results'):
                paths[f'/modules/{module_name}.js']=(f'modules/{module_name}.js','application/javascript; charset=utf-8')
            if self.path in paths:
                fname,ctype=paths[self.path]
                return self.respond((root/fname).read_bytes(),ctype=ctype)
            if self.path=='/bootstrap.js':
                referer=self.headers.get('Referer','')
                if not referer.startswith(f'http://127.0.0.1:{self.server.server_port}/'):
                    return self.respond({'error':'Referer incompatível'},403)
                return self.respond(f'window.POE_TOKEN={json.dumps(token)};window.POE_VERSION="0.9";'.encode(),ctype='application/javascript')
            if self.path=='/api/catalog':
                return self.respond([p.as_json() for p in catalog.values()])
            if self.path=='/api/default':
                return self.respond(default)
            return self.respond({'error':'Rota inexistente'},404)
        def do_POST(self):
            host=f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host')!=host or (self.headers.get('Origin') and self.headers.get('Origin')!=f'http://{host}'):
                return self.respond({'error':'Origem não autorizada'},403)
            if self.headers.get('X-POE-Token')!=token:
                return self.respond({'error':'Token de sessão inválido'},403)
            length=self.headers.get('Content-Length','')
            if not length.isdigit() or int(length)>MAX_POST:
                return self.respond({'error':'Tamanho de requisição inválido'},413)
            if 'application/json' not in self.headers.get('Content-Type',''):
                return self.respond({'error':'Content-Type deve ser JSON'},415)
            try:
                body=json.loads(self.rfile.read(int(length)))
                if self.path=='/api/preview':
                    # Prévia independente do solver: jamais confundir com resultados calculados.
                    project=body.get('project',{})
                    if not isinstance(project,dict): raise ValueError('Projeto inválido')
                    model=make_model(project,catalog)
                    geo=project.get('geometry',{})
                    diagnostics=geometry_diagnostics(model,
                        angle_min=float(geo.get('angle_min_deg',45)),
                        angle_max=float(geo.get('angle_max_deg',60)),
                        purlin_max_m=float(geo.get('purlin_max_m',0)))
                    selected=body.get('load_case')
                    loads={}
                    audit=None
                    if selected is not None:
                        patterns = {pattern['id']: pattern for pattern in load_patterns(project)}
                        cases = {case['id']: case for case in project.get('load_cases', [])}
                        source = cases.get(selected) or patterns.get(selected)
                        if source is None:raise ValueError('Caso de prévia inexistente')
                        raw,audit=resolve_case_loads(model,source,patterns)
                        loads={nid:{'fx_n':v[0],'fy_n':v[1]} for nid,v in raw.items()}
                    return self.respond({'preview_only':True,'model':model.to_dict(),
                                         'loads':loads,'load_audit':audit,
                                         'geometry_diagnostics':diagnostics})
                if self.path=='/api/analyze':
                    return self.respond(run_project(body,catalog))
                if self.path=='/api/optimize-sections':
                    return self.respond(suggest_sections(body.get('project',{}),catalog,body.get('options',{})))
                if self.path=='/api/migrate':
                    return self.respond(migrate_v05(body,catalog))
                if self.path=='/api/suggest':
                    return self.respond(suggest_geometry(body.get('project',{}),catalog,body.get('options',{})))
                if self.path=='/api/export':
                    project=body['project'];kind=body['kind'];selected=body.get('analysis_id')
                    result=run_project(project,catalog)
                    if kind=='load_audit':
                        if selected not in result['analyses']:raise ValueError('Selecione caso ou combinação válido')
                        return self.respond({'data':as_csv(load_audit_rows(result,selected)), 'filename':f'POE_Auditoria_Cargas_{selected}.csv'})
                    if kind=='stability':
                        return self.respond({'data':as_csv(stability_rows(result)), 'filename':'POE_Estabilidade_Barras.csv'})
                    if kind=='axial_screen':
                        return self.respond({'data':as_csv(axial_screen_rows(result)),'filename':'POE_Triagem_Axial_v09.csv'})
                    if kind=='section_properties':
                        return self.respond({'data':as_csv(section_properties_rows(result)),'filename':'POE_Secoes_Compostas_v09.csv'})
                    if kind=='camber':
                        return self.respond({'data':as_csv(camber_rows(result)),'filename':'POE_Contraflecha_Preliminar_v09.csv'})
                    if kind=='dimperfil':
                        return self.respond({'data':as_csv(dimperfil_rows(result)),'filename':'POE_DimPerfil_Barras.csv'})
                    if kind=='ftool':
                        if selected not in result['analyses']:raise ValueError('Selecione caso ou combinação válido')
                        v=ftool_rows(result,selected)
                        return self.respond({'data':{k:as_csv(value) for k,value in v.items() if k!='supports'},
                                             'supports':v['supports'],'filename_prefix':f'FTool_{selected}'})
                    if kind=='ftool_compare':
                        if selected not in result['analyses']:raise ValueError('Selecione caso válido')
                        return self.respond({'data':as_csv(ftool_comparison_full_rows(result,selected)), 'filename':f'FTool_comparacao_{selected}.csv'})
                    if kind=='memorial':
                        if selected not in result['analyses']:raise ValueError('Selecione caso válido')
                        return self.respond({'data':integrated_report_html(result,project,selected),'filename':f'POE_Memorial_v09_{selected}.html'})
                    raise ValueError('Tipo de exportação inválido')
                if self.path=='/api/shutdown':
                    self.respond({'ok':True})
                    Thread(target=self.server.shutdown,daemon=True).start()
                    return
                return self.respond({'error':'Rota inexistente'},404)
            except (ValueError,KeyError,TypeError,OverflowError,ZeroDivisionError) as exc:
                return self.respond({'error':str(exc)},422)
            except Exception as exc:
                sys.stderr.write(f'[POE] Erro interno: {exc!r}\n')
                return self.respond({'error':'Falha interna no cálculo; consulte o terminal'},500)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    address=f'http://127.0.0.1:{server.server_port}/'
    print('2DTRUSS PYTHON v0.1')
    print('Servidor restrito a 127.0.0.1; não há conexão externa.')
    print('Acesse:',address)
    print('Pressione Ctrl+C para encerrar.')
    if open_browser:
        import threading
        threading.Timer(0.6,lambda:webbrowser.open(address)).start()
    return server


def main():
    root=Path(__file__).resolve().parent.parent
    server=run_server(root,True)
    try:server.serve_forever(poll_interval=0.15)
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()
