"""Testes funcionais Chromium sem rede: módulos ES importados por data: URLs.
Executar: python tests/browser_ui_v09_inmemory.py
"""
from pathlib import Path
import sys, json, base64
from playwright.sync_api import sync_playwright
base=Path(__file__).resolve().parents[1];sys.path.insert(0,str(base))
from poe_truss.catalog import load_catalog
from poe_truss.engine import run_project
from poe_truss.model import make_model,geometry_diagnostics
from poe_truss.loads import build_case_loads
from poe_truss.search import suggest_geometry
from poe_truss.design import suggest_sections
cat=load_catalog(base/'catalogo_perfis.csv')
default=json.loads((base/'examples/cobertura_duas_aguas.json').read_text())
def handler(url,body):
 if url=='/api/default':return default
 if url=='/api/catalog':return [c.as_json() for c in cat.values()]
 if url=='/api/preview':
  p=body['project'];model=make_model(p,cat);g=p['geometry'];cid=body.get('load_case');loads={};audit=None
  if cid:
   case=next(c for c in p['load_cases'] if c['id']==cid)
   vec,audit=build_case_loads(model,case);loads={k:{'fx_n':v[0],'fy_n':v[1]} for k,v in vec.items()}
  return {'preview_only':True,'model':model.to_dict(),'loads':loads,'load_audit':audit,
    'geometry_diagnostics':geometry_diagnostics(model,angle_min=g['angle_min_deg'],angle_max=g['angle_max_deg'],purlin_max_m=g['purlin_max_m'])}
 if url=='/api/analyze':return run_project(body,cat)
 if url=='/api/suggest':return suggest_geometry(body['project'],cat,body.get('options',{}))
 if url=='/api/optimize-sections':return suggest_sections(body.get('project',{}),cat,body.get('options',{}))
 return {'data':'id;A\nB;1','filename':'teste.csv'}

# Imports ficam desacoplados, mas Chromium não tem acesso à rede local neste ambiente.
app=(base/'web/app.js').read_text(encoding='utf-8')
for module in ['nodal','diagram','results']:
 content=(base/f'web/modules/{module}.js').read_text(encoding='utf-8')
 uri='data:text/javascript;base64,'+base64.b64encode(content.encode()).decode()
 app=app.replace(f"'./modules/{module}.js'", "'"+uri+"'")
html=(base/'web/index.html').read_text(encoding='utf-8')
html=html.replace('<link rel="stylesheet" href="/style.css"/>', '<style>'+(base/'web/style.css').read_text(encoding='utf-8')+'</style>')
html=html.replace('<script src="/bootstrap.js"></script><script type="module" src="/app.js"></script>','')
shots=base/'verification/ui_v09_modular';shots.mkdir(parents=True,exist_ok=True)
with sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
 page=browser.new_page(viewport={'width':1600,'height':900},accept_downloads=True)
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.expose_function('dataBridge',handler)
 page.set_content(html,wait_until='domcontentloaded')
 page.evaluate('''()=>{window.POE_TOKEN='test';window.fetch=async(url,options={})=>({ok:true,status:200,json:()=>window.dataBridge(url,options.body?JSON.parse(options.body):null)})}''')
 page.add_script_tag(type='module',content=app)
 page.locator('#model-status.calculated').wait_for(timeout=20000)
 print('Inicialização OK',page.locator('#model-status').inner_text())
 page.locator('.navitem[data-page="members"]').click();page.wait_for_timeout(300)
 count=page.locator('#member-rows tr[data-member-id]').count()
 print('10 críticas?',count);assert count==10
 page.locator('#member-group-filter').select_option('diagonal')
 page.locator('#member-status-filter').select_option('all')
 count=page.locator('#member-rows tr[data-member-id]').count()
 print('diagonais',count);assert count>1
 page.locator('#member-search').fill('M05')
 assert page.locator('#member-rows tr[data-member-id]').count()>=1
 page.locator('#member-rows tr[data-member-id]').first.click()
 print('barra',page.locator('#detail-state').inner_text())
 page.screenshot(path=str(shots/'UI_v0.1_resultados.png'),full_page=True)
 page.locator('.navitem[data-page="loads"]').click()
 page.locator('#btn-new-case').click();page.locator('#case-kind').select_option('nodal')
 page.wait_for_timeout(300)
 print('nodal visible',page.locator('#nodal-editor').is_visible())
 assert page.locator('#nodal-editor').is_visible()
 if page.locator('[data-nodal-row]').count()==0:page.locator('#btn-nodal-add').click()
 page.locator('[data-field="fy"]').first.fill('-125')
 page.locator('#model-svg [data-node="T00"]').click(force=True)
 page.wait_for_timeout(380)
 print('assigned node',page.locator('[data-field="node"]').first.input_value())
 assert page.locator('[data-field="node"]').first.input_value()=='T00'
 page.locator('#btn-apply-case').click()
 page.locator('#btn-run').click()
 page.locator('#model-status.calculated').wait_for(timeout=20000)
 assert page.locator('#analysis-view').input_value()=='NEW1', 'Um novo caso nodal deve ser visualizado após cálculo'
 print('node load applied',page.locator('#model-status').inner_text())
 page.screenshot(path=str(shots/'UI_v0.1_cargas.png'),full_page=True)
 page.locator('#btn-nodal-add').click();page.locator('[data-nodal-row]').last.locator('[data-field="node"]').select_option('T02')
 page.locator('[data-nodal-row]').last.locator('[data-field="fx"]').fill('55')
 page.locator('[data-nodal-row]').last.locator('[data-field="fy"]').fill('0')
 page.locator('#btn-apply-case').click()
 page.locator('#btn-run').click()
 page.locator('#model-status.calculated').wait_for(timeout=20000)
 assert page.locator('[data-nodal-row]').count()==2
 assert page.locator('#analysis-view').input_value()=='NEW1'
 with page.expect_download() as event:page.locator('#btn-save').click()
 download=event.value
 import json as _json
 saved=_json.loads(Path(download.path()).read_text(encoding='utf-8'))
 nodal=next(c for c in saved['load_cases'] if c['id']=='NEW1')
 assert nodal['loads'][0]['node']=='T00' and nodal['loads'][0]['fy']==-125
 assert nodal['loads'][1]['node']=='T02' and nodal['loads'][1]['fx']==55
 print('2 cargas salvas em JSON OK')
 # sem scroll global no viewport desktop
 dims=page.evaluate('''()=>({body:document.body.scrollHeight,win:window.innerHeight,documentWidth:document.documentElement.scrollWidth,innerWidth:window.innerWidth})''')
 print('dimensões',dims);assert dims['body']==dims['win'] and dims['documentWidth']<=dims['innerWidth']
 print('errors',errors);assert not errors,errors
 browser.close()
