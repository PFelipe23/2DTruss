import {createNodalEditor} from './modules/nodal.js';
import {renderDiagram} from './modules/diagram.js';
import {renderResultsTable} from './modules/results.js';
'use strict';
/* 2DTruss v0.1 — UI/UX auditada — a interface somente edita os parâmetros e apresenta
 * resultados. Toda a solução FEM, distribuição das ações e envoltórias
 * ocorre no motor Python do servidor local. */
const $=id=>document.getElementById(id);
const REQ_HEADER={'Content-Type':'application/json','X-POE-Token':window.POE_TOKEN};
let project=null,catalog=[],result=null,preview=null,dirty=false,previewSeq=0,previewTimer=null,activePage='project',selectedLoad=null,selectedCombo=null,activeCase=null,selectedElement=null,units='m',eUnit='MPa',forceUnit='kgf';
const nodalEditor=createNodalEditor({
 root:()=> $('nodal-table'),
 getNodes:()=> (preview?.model||result?.model)?.nodes||[],
 getDefaultUnit:()=> $('case-unit').value||'kgf',
 onChange:()=>schedulePreview(),
});
const GROUP_LABELS={superior:'Banzo superior',inferior:'Banzo inferior',montante:'Montantes',diagonal:'Diagonais'};
const UNIT_MULT={m:1,cm:100,mm:1000},UNIT_DEC={m:5,cm:2,mm:0};
const n=(x,def=0)=>{const value=Number(String(x??'').trim().replace(/\s/g,'').replace(',','.'));return Number.isFinite(value)?value:def};
const forceShown=value=>value/({kgf:10,tf:10000,kN:1000}[forceUnit]);
const num=(v,d=2)=>Number(v||0).toLocaleString('pt-BR',{minimumFractionDigits:d,maximumFractionDigits:d});
function html(v){return String(v??'').replace(/[&<>"']/g,s=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[s]));}
function message(m,error=false){const e=$('flash');e.hidden=false;e.className='flash'+(error?' error':'');e.textContent=m;clearTimeout(message.timer);message.timer=setTimeout(()=>e.hidden=true,8500)}
async function api(url,payload){const r=await fetch(url,{method:'POST',headers:REQ_HEADER,body:JSON.stringify(payload)});const d=await r.json();if(!r.ok)throw Error(d.error||`HTTP ${r.status}`);return d}
function downloadText(filename,body,mime='text/plain;charset=utf-8'){const a=document.createElement('a'),url=URL.createObjectURL(new Blob([body],{type:mime}));a.href=url;a.download=filename;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1500)}
function formatLength(m){return Number(m*UNIT_MULT[units]).toFixed(UNIT_DEC[units]);}
const PAGE_TABS={project:['Geometria','Perfis','Apoios'],stability:['Parâmetros','Travamentos','Exceções','Quadro'],advanced:['Seções','DimPerfil','Contraflecha','Otimização','Relatórios']};
function initPanelTabs(){
 for(const [page,labels] of Object.entries(PAGE_TABS)){
  const section=$('page-'+page);if(!section)continue;
  const panels=Array.from(section.children).filter(x=>x.classList.contains('panel'));
  if(panels.length!==labels.length)continue;
  section.classList.add('tabbable');
  const nav=document.createElement('div');nav.className='subnav';nav.setAttribute('role','tablist');
  labels.forEach((label,i)=>{const b=document.createElement('button');b.type='button';b.textContent=label;b.dataset.subtab=String(i);b.setAttribute('role','tab');b.setAttribute('aria-selected',String(i===0));b.addEventListener('click',()=>activateSubtab(page,i));nav.appendChild(b)});
  section.insertBefore(nav,section.firstChild);activateSubtab(page,0);
 }
}
function activateSubtab(page,index){const section=$('page-'+page);if(!section)return;
 section.querySelectorAll(':scope > .panel').forEach((el,i)=>el.classList.toggle('subactive',i===index));
 section.querySelectorAll('.subnav button').forEach((el,i)=>{el.classList.toggle('active',i===index);el.setAttribute('aria-selected',String(i===index))});
}
function setPage(p){
 activePage=p;
 document.querySelectorAll('.page').forEach(e=>e.classList.toggle('active',e.id==='page-'+p));
 document.querySelectorAll('.navitem').forEach(e=>e.classList.toggle('active',e.dataset.page===p));
 if(p==='members'){renderMembers();drawModel();}if(p==='validation')renderValidation();if(p==='stability')renderStabilitySummary();if(p==='advanced')renderAdvancedSummary();
 if(p==='loads'){$('diagram-mode').value='loads';$('show-loads').checked=true;schedulePreview(false)}
 else if(p==='project'||p==='members'){$('diagram-mode').value='efforts';$('show-loads').checked=false;}
 else if(result&&!dirty){preview=null;drawModel();}
 else if(preview)drawModel();
}
function commitVisibleEditor(){
 if(activePage==='loads'&&selectedLoad)applyLoad({silent:true});
 if(activePage==='combinations'&&selectedCombo)saveCombo({silent:true});
 if(dirty){$('metrics').classList.add('stale');setModelState('stale','Dados alterados — recalcule');}
}
function initNavigation(){document.querySelectorAll('.navitem').forEach(b=>b.addEventListener('click',()=>{
 try{if(activePage!==b.dataset.page)commitVisibleEditor();setPage(b.dataset.page)}catch(e){message(e.message,true)}
}));}
function setGeometryFields(){const g=project.geometry; $('name').value=project.name||'';$('length-unit').value=units;
[['span','span_m'],['spacing','frame_spacing_m'],['height','height_m'],['rise','rise_m']].forEach(([id,k])=>$(id).value=formatLength(g[k]||0));
$('roof-shape').value=g.roof_shape;$('truss-type').value=g.truss_type;$('panels').value=g.panels;$('purlin-max').value=String(g.purlin_max_m??1.2);$('angle-min').value=g.angle_min_deg??45;$('angle-max').value=g.angle_max_deg??60;$('E').value=eUnit==='MPa'?project.material.E_MPa:project.material.E_MPa/1000;$('e-unit').value=eUnit;}
function requiredNumber(id,label,strictPositive=false){const raw=$(id).value.trim().replace(/\s/g,'').replace(',','.');
 if(raw===''||!Number.isFinite(Number(raw)))throw Error(`${label}: insira um número válido`);
 const v=Number(raw);if(strictPositive&&v<=0)throw Error(`${label}: valor deve ser maior que zero`);return v;
}
function readGeometryFields(){if(!project)return;
 const g=project.geometry,next={};
 [['span','span_m','Vão',true],['spacing','frame_spacing_m','Distância entre pórticos',true],['height','height_m','Altura',true],['rise','rise_m','Elevação',false]]
 .forEach(([id,k,label,required])=>next[k]=requiredNumber(id,label,required)/UNIT_MULT[units]);
 const panels=requiredNumber('panels','Número de painéis',true);
 if(!Number.isInteger(panels)||panels<2||panels>40)throw Error('Painéis devem ser inteiros entre 2 e 40');
 next.panels=panels;next.roof_shape=$('roof-shape').value;next.truss_type=$('truss-type').value;
 next.purlin_max_m=requiredNumber('purlin-max','Passo máximo de terças',true);
 next.angle_min_deg=requiredNumber('angle-min','Ângulo mínimo');next.angle_max_deg=requiredNumber('angle-max','Ângulo máximo');
 if(next.rise_m<0||next.angle_min_deg<0||next.angle_max_deg>90||next.angle_min_deg>next.angle_max_deg)throw Error('Verifique elevação e faixa angular');
 const E=requiredNumber('E','Módulo E',true)*(eUnit==='GPa'?1000:1);
 Object.assign(g,next);project.name=$('name').value.trim()||'Treliça sem nome';
 project.material.E_MPa=E;
 document.querySelectorAll('[data-profile-group]').forEach(el=>{project.sections[el.dataset.profileGroup].profile=el.value});
 document.querySelectorAll('[data-count-group]').forEach(el=>{project.sections[el.dataset.countGroup].count=Number(el.value)});
 $('project-title').textContent=project.name;
}
function setModelState(state,text){
 const status=$('model-status'),visual=$('diagram-state');
 status.className='model-status '+state;visual.className='diagram-state '+state;
 status.textContent=text;visual.textContent=state==='calculated'?'ANÁLISE CALCULADA':'PRÉVIA · SEM RESULTADOS ATUALIZADOS';
}
function buildPreviewDraft(){
 readGeometryFields();
 if(activePage!=='loads'||!selectedLoad)return project;
 const clone=structuredClone(project),load=clone.load_cases.find(c=>c.id===selectedLoad);
 if(!load)return clone;
 load.kind=$('case-kind').value;load.name=$('case-name').value.trim()||load.id;
 load.value=['surface','line'].includes(load.kind)?requiredNumber('case-value','Intensidade'):0;load.force_unit=$('case-unit').value;
 load.application=$('case-application').value;load.basis=$('case-basis').value;
 load.direction=$('case-direction').value;load.zone=$('case-zone').value;
 if(load.kind==='nodal'){load.loads=nodalEditor.read()}else delete load.loads;
 return clone;
}
function schedulePreview(markDirty=true){
 if(!project)return;
 if(markDirty){dirty=true;$('metrics').classList.add('stale');setModelState('stale','Parâmetros modificados — recalcule');}
 clearTimeout(previewTimer);const serial=++previewSeq;
 previewTimer=setTimeout(async()=>{
  try{
   const draft=buildPreviewDraft();
   const r=await api('/api/preview',{project:draft,load_case:activePage==='loads'?selectedLoad:null});
   if(serial!==previewSeq)return;
   preview=r;nodalEditor.updateNodes(r.model.nodes);drawModel();
  }catch(err){if(serial!==previewSeq)return;preview=null;setModelState('stale','Prévia inválida: '+err.message);}
 },190);
}
function renderSections(){const opts=catalog.map(p=>`<option value="${html(p.name)}">${html(p.name)} · ${num(p.mass_kg_m,2)} kg/m</option>`).join('');$('sections-edit').innerHTML=Object.entries(GROUP_LABELS).map(([g,name])=>`<div class="section-row"><label>${html(name)}</label><div><small>Seção transversal</small><select data-profile-group="${g}">${opts}</select></div><div><small>Perfis</small><select data-count-group="${g}"><option value="1">1×</option><option value="2">2×</option></select></div></div>`).join('');for(const g of Object.keys(GROUP_LABELS)){document.querySelector(`[data-profile-group="${g}"]`).value=project.sections[g].profile;document.querySelector(`[data-count-group="${g}"]`).value=project.sections[g].count||1}}
function selectedCaseItem(){return project.load_cases.find(c=>c.id===selectedLoad)}
function renderLoadList(){if(!selectedLoad && project.load_cases.length)selectedLoad=project.load_cases[0].id;
$('load-cases-list').innerHTML=project.load_cases.map(c=>`<button class="case-item ${c.id===selectedLoad?'active':''}" data-case="${html(c.id)}"><div><strong>${html(c.id)} · ${html(c.name)}</strong><span>${html(c.kind)}${c.kind==='surface'?' · '+num(c.value,2)+' '+html(c.force_unit||'kgf')+'/m²':''}</span></div><span>Editar ›</span></button>`).join('');document.querySelectorAll('[data-case]').forEach(b=>b.addEventListener('click',()=>{try{if(b.dataset.case!==selectedLoad)applyLoad({silent:true});selectedLoad=b.dataset.case;renderLoadList();schedulePreview(false);}catch(err){message('Não foi possível mudar o caso: '+err.message,true)}}));renderLoadEditor()}
function renderLoadEditor(){const c=selectedCaseItem();if(!c){$('case-id').value='';return}const values={
'case-id':c.id,'case-kind':c.kind,'case-name':c.name,'case-value':c.value??0,'case-unit':c.force_unit||'kgf',
'case-application':c.application||'top','case-basis':c.basis||'projected','case-direction':c.direction||'down','case-zone':c.zone||'all'};Object.entries(values).forEach(([id,val])=>$(id).value=val);nodalEditor.setRows(c.loads||[]);updateCaseFormVisibility()}
function updateCaseFormVisibility(){
 const kind=$('case-kind').value,self=kind==='self_weight',nodal=kind==='nodal';
 for(const id of ['case-value','case-unit','case-application','case-basis','case-direction','case-zone']){
  const el=$(id);el.disabled=self||(nodal&&id!=='case-unit');
  el.closest('.field')?.classList.toggle('field-disabled',el.disabled);
 }
 $('nodal-editor').hidden=!nodal;
 $('case-value').closest('.field').hidden=self||nodal;
 $('case-basis').closest('.field').hidden=self||nodal||kind==='line';
 $('case-application').closest('.field').hidden=self||nodal;
 $('case-direction').closest('.field').hidden=self||nodal;
 $('case-zone').closest('.field').hidden=self||nodal;
}
function applyLoad({silent=false}={}){
 const c=selectedCaseItem();if(!c)return;
 const old=c.id,before=JSON.stringify(c);
 const id=$('case-id').value.trim().replace(/\s/g,'_');
 if(!id)throw Error('ID da ação é obrigatório');
 if(id!==old&&project.load_cases.some(x=>x.id===id))throw Error('ID de ação duplicado');
 const kind=$('case-kind').value;
 const value=['surface','line'].includes(kind)?requiredNumber('case-value','Intensidade'):0;
 if(value<0)throw Error('Intensidade negativa: escolha a direção de aplicação');
 const next={...c,id,name:$('case-name').value.trim()||id,kind,value,force_unit:$('case-unit').value,
   application:$('case-application').value,basis:$('case-basis').value,
   direction:$('case-direction').value,zone:$('case-zone').value};
 if(kind==='nodal'){
  const loads=nodalEditor.read();
  if(!Array.isArray(loads)||!loads.length)throw Error('Informe ao menos uma carga nodal válida');
  next.loads=loads;
 }else delete next.loads;
 const changed=JSON.stringify(next)!==before;
 Object.keys(c).forEach(k=>{if(!(k in next))delete c[k]});Object.assign(c,next);
 if(old!==id)for(const comb of project.combinations){if(Object.hasOwn(comb.factors,old)){comb.factors[id]=comb.factors[old];delete comb.factors[old]}}
 selectedLoad=id;renderLoadList();
 if(!silent){schedulePreview();message('Caso atualizado. Recalcule para atualizar os esforços.');}
 else if(changed)dirty=true;
}
function newLoad(){if(activePage==='loads'&&selectedLoad)applyLoad({silent:true});let k=1;while(project.load_cases.some(x=>x.id==='NEW'+k))k++;const id='NEW'+k;project.load_cases.push({id,name:'Nova ação',kind:'surface',value:0,force_unit:'kgf',direction:'down',application:'top',basis:'projected',zone:'all'});selectedLoad=id;setPage('loads');renderLoadList();schedulePreview()}
function deleteLoad(){if(!selectedLoad)return;project.load_cases=project.load_cases.filter(x=>x.id!==selectedLoad);for(const comb of project.combinations)delete comb.factors[selectedLoad];selectedLoad=project.load_cases[0]?.id||null;renderLoadList();schedulePreview()}
function renderCombos(){if(!selectedCombo && project.combinations.length)selectedCombo=project.combinations[0].id;
$('combos-list').innerHTML=project.combinations.map(c=>`<button class="combo-item ${selectedCombo===c.id?'active':''}" data-combo="${html(c.id)}"><strong>${html(c.id)}</strong><span>${html(Object.entries(c.factors).filter(([,v])=>v).map(([k,v])=>`${num(v,2)}·${k}`).join(' + '))}</span></button>`).join('');document.querySelectorAll('[data-combo]').forEach(b=>b.addEventListener('click',()=>{try{if(selectedCombo!==b.dataset.combo)saveCombo({silent:true});selectedCombo=b.dataset.combo;renderCombos()}catch(err){message(err.message,true)}}));renderFactorGrid()}
function renderFactorGrid(){const c=project.combinations.find(x=>x.id===selectedCombo);$('combo-id').value=c?.id||'';
$('factors-grid').innerHTML=project.load_cases.map(load=>`<div class="factor-line"><label>${html(load.id)} · ${html(load.name)}</label><input type="text" inputmode="decimal" data-factor="${html(load.id)}" value="${html(c?.factors[load.id]??0)}"></div>`).join('')}
function saveCombo({silent=false}={}){const prev=project.combinations.find(x=>x.id===selectedCombo);if(!prev)throw Error('Nenhuma combinação selecionada');const before=JSON.stringify(prev);const id=$('combo-id').value.trim().replace(/\s/g,'_');if(!id)throw Error('ID de combinação vazio');if(id!==selectedCombo&&project.combinations.some(x=>x.id===id))throw Error('ID de combinação duplicado');let factors={};document.querySelectorAll('[data-factor]').forEach(el=>{const raw=el.value.trim().replace(',','.');if(raw===''||!Number.isFinite(Number(raw)))throw Error(`Fator inválido para ${el.dataset.factor}`);const v=Number(raw);if(v!==0)factors[el.dataset.factor]=v});if(Object.keys(factors).length===0)throw Error('Inclua pelo menos um fator diferente de zero');prev.id=id;prev.factors=factors;selectedCombo=id;if(silent){if(JSON.stringify(prev)!==before)dirty=true;}else{schedulePreview();message('Combinação salva. Recalcule a estrutura.')}renderCombos()}
function newCombo(){if(activePage==='combinations'&&selectedCombo)saveCombo({silent:true});let k=1;while(project.combinations.some(x=>x.id==='C'+k))k++;const c={id:'C'+k,name:'Combinação de usuário',factors:{[project.load_cases[0].id]:1}};project.combinations.push(c);selectedCombo=c.id;renderCombos();schedulePreview()}
function deleteCombo(){project.combinations=project.combinations.filter(c=>c.id!==selectedCombo);selectedCombo=project.combinations[0]?.id||null;renderCombos();schedulePreview()}
function renderSupports(){
 const model=preview?.model||result?.model;
 if(!model){$('supports-ui').innerHTML='<p class="tiny">Gere uma prévia para selecionar nós.</p>';return}
 const values={};(project.supports??model.supports).forEach(s=>{values[s.node]=(s.ux?'X':'')+(s.uy?'Y':'')});
 $('supports-ui').innerHTML=model.nodes.filter(v=>v.id.startsWith('B')||values[v.id]).map(nd=>`<div class="support-row"><span>${html(nd.id)} · X=${num(nd.x_mm/1000,2)} m</span><select data-support="${html(nd.id)}"><option value="">Livre</option><option value="X">Apoio X</option><option value="Y">Apoio Y</option><option value="XY">Apoio XY</option></select></div>`).join('');
 document.querySelectorAll('[data-support]').forEach(sel=>{sel.value=values[sel.dataset.support]||'';sel.addEventListener('change',()=>updateSupport(sel.dataset.support,sel.value))});
}
function updateSupport(node,type){
 const model=preview?.model||result?.model;
 if(!model||!model.nodes.some(n=>n.id===node))throw Error('Nó de apoio não encontrado na geometria atual');
 const lookup={};const supports=(project.supports??model.supports).map(x=>({...x}));
 for(const s of supports)lookup[s.node]=s;
 delete lookup[node];if(type)lookup[node]={node,ux:type.includes('X'),uy:type.includes('Y')};
 project.supports=Object.values(lookup);dirty=true;
 $('metrics').classList.add('stale');setModelState('stale','Apoios modificados — recalcule');
 renderSupports();schedulePreview(false);message(`Apoio ${node}: ${type||'livre'}. Recalcule.`);
}
function restoreSupports(){
 const model=preview?.model||result?.model;
 if(!model)throw Error('Gere primeiro o modelo geométrico');
 const bottoms=model.nodes.filter(n=>n.id.startsWith('B'));
 if(bottoms.length<2)throw Error('Não há dois nós inferiores para os apoios extremos');
 project.supports=[{node:bottoms[0].id,ux:true,uy:true},{node:bottoms.at(-1).id,ux:false,uy:true}];
 dirty=true;$('metrics').classList.add('stale');setModelState('stale','Apoios padrão — recalcule');
 renderSupports();schedulePreview(false);message('Apoios extremos adotados. Recalcule.');
}
function inspectPreviewNode(id){
 const model=preview?.model,nd=model?.nodes.find(n=>n.id===id);if(!nd)return;
 selectedElement={type:'node',id};
 const sup=(project.supports??model.supports).find(s=>s.node===id),current=sup?(sup.ux?'X':'')+(sup.uy?'Y':''):'';
 $('detail-state').textContent=`PRÉVIA DO NÓ ${id}`;
 $('detail-body').innerHTML=`<p class="hint">Nó ${html(id)}: X=${num(nd.x_mm/1000,3)} m, Y=${num(nd.y_mm/1000,3)} m. Não há deslocamentos calculados nesta prévia.</p><div class="field"><label>Vínculo do nó</label><select id="selected-support"><option value="">Livre</option><option value="X">Apoio X</option><option value="Y">Apoio Y</option><option value="XY">Apoio XY</option></select></div><button class="btn btn-light" id="btn-node-support">Aplicar vínculo</button>`;
 $('selected-support').value=current;
 $('btn-node-support').addEventListener('click',()=>{try{updateSupport(id,$('selected-support').value)}catch(e){message(e.message,true)}});
}
async function analyze(){$('btn-run').disabled=true;try{if(activePage==='loads'&&selectedLoad)applyLoad({silent:true});if(activePage==='combinations'&&selectedCombo)saveCombo({silent:true});clearTimeout(previewTimer);previewSeq++;readGeometryFields();readStabilityGroups();readBracing();readAdvanced();const r=await api('/api/analyze',project);result=r;preview=null;dirty=false;$('metrics').classList.remove('stale');setModelState('calculated','Análise atualizada');activeCase=(activePage==='loads'&&selectedLoad in r.analyses)?selectedLoad:(activeCase in r.analyses?activeCase:Object.keys(r.analyses).find(k=>k.startsWith('S_'))||Object.keys(r.analyses)[0]);renderResults();nodalEditor.updateNodes(r.model.nodes);renderAdvancedSummary();message(`Análise concluída: ${r.model.nodes.length} nós, ${r.model.members.length} barras e ${Object.keys(r.analyses).length} estados.`)}catch(e){message(e.message,true)}finally{$('btn-run').disabled=false}}
function renderResults(){if(!result)return;$('analysis-view').innerHTML=Object.keys(result.analyses).map(c=>`<option value="${html(c)}">${html(c)}</option>`).join('');$('analysis-view').value=activeCase;drawModel();renderMetrics();renderMembers();renderValidation();renderSupports();renderWarnings();renderStabilitySummary();renderStabilityMemberOptions();}
function drawModel(){
  return renderDiagram({$,result,preview,dirty,activePage,activeCase,selectedLoad,selectedElement,
    forceShown,num,forceUnit,inspectMember,inspectNode,
    inspectPreviewNode:(id,isPreview)=>{
      if(activePage==='loads' && $('case-kind').value==='nodal'){
        nodalEditor.assignNode(id);selectedElement={type:'node',id};
        $('detail-state').textContent='CARGA NODAL · '+id;
        $('detail-body').textContent='Nó '+id+' atribuído à linha selecionada. Informe Fx e Fy na tabela de cargas.';
        return;
      }
      if(isPreview)inspectPreviewNode(id);else inspectNode(id);
    },onMemberSelect:inspectMember});
}
function renderMetrics(){if(!result)return;const view=result.analyses[activeCase],axials=Object.values(view.axial_n);let tension=Math.max(0,...axials),comp=Math.min(0,...axials);
$('metrics').innerHTML=[['Massa das barras',num(result.model.mass_kg,1)+' kg'],['Desloc. vertical crítico',num(Math.abs(view.max_abs_roof_mm),2)+' mm '+(view.max_abs_roof_mm>0?'↑':'↓')],['Compressão',num(forceShown(comp),2)+' '+forceUnit],['Tração',num(forceShown(tension),2)+' '+forceUnit]].map(([l,v])=>`<div class="metric"><span>${l}</span><strong>${v}</strong></div>`).join('')}
function renderMembers(){
  renderResultsTable({$,result,dirty,activeCase,forceUnit,num,html,forceShown,
   selectedElement,onSelect:(id)=>{inspectMember(id);renderMembers();},onSummary:(text)=>{$('member-filter-summary').textContent=text}});
}
function renderWarnings(){if(!result)return;$('warnings').innerHTML='<div class="warning-list">'+result.warnings.map(x=>`<p>• ${html(x)}</p>`).join('')+'</div>'}
function inspectMember(id){if(!result)return;selectedElement={type:'member',id};const m=result.model.members.find(m=>m.id===id),e=result.envelope[id],N=result.analyses[activeCase].axial_n[id];$('detail-state').textContent=id;
$('detail-body').innerHTML=`<div class="info-grid"><div>Grupo<b>${html(m.group)}</b></div><div>Seção<b>${html(m.profile)}</b></div><div>Comprimento<b>${num(m.length_mm/1000,3)} m</b></div><div>Área<b>${num(m.area_mm2,1)} mm²</b></div><div>Normal (${html(activeCase)})<b class="${N<0?'neg':'pos'}">${num(forceShown(N),2)} ${forceUnit}</b></div><div>Massa unitária<b>${num(m.mass_kg_m,2)} kg/m</b></div><div>Maior tração<b>${num(forceShown(e.max_tension_n),2)} ${forceUnit} (${html(e.tension_case||'—')})</b></div><div>Maior compressão<b>${num(forceShown(e.max_compression_n),2)} ${forceUnit} (${html(e.compression_case||'—')})</b></div></div><p class="hint">Valores de análise, sem verificação resistente.</p>`;drawModel()}
function inspectNode(id){if(!result)return;selectedElement={type:'node',id};const v=result.analyses[activeCase].nodal_displacements[id],r=result.analyses[activeCase].reactions[id],nd=result.model.nodes.find(n=>n.id===id),sup=result.model.supports.find(s=>s.node===id);const current=sup?(sup.ux?'X':'')+(sup.uy?'Y':''):'';
$('detail-state').textContent=`NÓ ${id}`;$('detail-body').innerHTML=`<div class="info-grid"><div>X<b>${num(nd.x_mm/1000,3)} m</b></div><div>Y<b>${num(nd.y_mm/1000,3)} m</b></div><div>UX<b>${num(v.ux_mm,5)} mm</b></div><div>UY<b>${num(v.uy_mm,5)} mm</b></div><div>RX<b>${num(forceShown(r?.fx_n||0),2)} ${forceUnit}</b></div><div>RY<b>${num(forceShown(r?.fy_n||0),2)} ${forceUnit}</b></div></div><div class="field" style="margin-top:12px"><label>Vínculo no nó ${html(id)}</label><select id="selected-support"><option value="">Livre</option><option value="X">Apoio X</option><option value="Y">Apoio Y</option><option value="XY">Apoio XY</option></select></div><button class="btn btn-light" id="btn-node-support">Aplicar apoio no nó</button>`;
$('selected-support').value=current;$('btn-node-support').addEventListener('click',()=>updateSupport(id,$('selected-support').value));}
function renderValidation(){if(!result)return;const e=result.analyses[activeCase].equilibrium;
$('equilibrium-card').innerHTML=`<div class="info-grid"><div>Σ FX residual<b>${num(e.sum_fx_n,7)} N</b></div><div>Σ FY residual<b>${num(e.sum_fy_n,7)} N</b></div><div>Σ M residual<b>${num(e.sum_m_nmm,5)} N·mm</b></div><div>Máximo residual GDL livre<b>${num(e.max_free_residual_n,8)} N</b></div></div>`;}
async function exportKind(kind){readGeometryFields();readStabilityGroups();readBracing();readAdvanced();if(dirty)throw Error('Parâmetros alterados: recalcule antes de exportar');if(!result)throw Error('Execute uma análise antes de exportar');const response=await api('/api/export',{project,kind,analysis_id:activeCase});
if(kind==='ftool'){for(const [name,data] of Object.entries(response.data)){downloadText(`${response.filename_prefix}_${name}.csv`,data,'text/csv;charset=utf-8')}downloadText(`${response.filename_prefix}_apoios.json`,JSON.stringify(response.supports,null,2),'application/json');return}
downloadText(response.filename,response.data,kind==='memorial'?'text/html;charset=utf-8':'text/csv;charset=utf-8')}

async function suggestGeometry(){
 readGeometryFields();$('btn-suggest').disabled=true;$('suggest-results').innerHTML='<p class="hint">Calculando alternativas...</p>';
 try{const r=await api('/api/suggest',{project,options:{case:project.combinations.some(c=>c.id==='S_GRAV')?'S_GRAV':project.combinations[0]?.id||project.load_cases[0]?.id, flecha_rel:250}});
   $('suggest-results').innerHTML=`<p class="sug-note">3 melhores de ${r.evaluated} alternativas; critérios geométricos/ELS. Você pode manter qualquer valor manual. Sem ELU.</p>`+r.candidates.slice(0,3).map((a,i)=>`<div class="sug"><div><b>${a.panels} painéis · h=${num(a.height_m,2)} m</b><small>Terças ≤ ${num(a.max_purlin_m,2)} m · ∠ na faixa: ${num((a.angle_fraction||0)*100,0)}% · flecha ${num(a.max_abs_roof_mm,2)} mm</small></div><button data-adopt="${i}">Adotar</button></div>`).join('');
   document.querySelectorAll('[data-adopt]').forEach(btn=>btn.addEventListener('click',async()=>{const v=r.candidates[Number(btn.dataset.adopt)];if((project.supports||project.stability?.lateral_bracing?.length)&&!confirm('A mudança de topologia exigirá revisar apoios e travamentos. Deseja continuar?'))return;project.geometry.panels=v.panels;project.geometry.height_m=v.height_m;delete project.supports;if(project.stability){project.stability.members={};project.stability.lateral_bracing=[];}renderStabilityEditor();selectedElement=null;setGeometryFields();message('Geometria adotada. Apoios extremos restaurados para a nova topologia.');await analyze()}));
 }catch(e){$('suggest-results').innerHTML='';message(e.message,true)}finally{$('btn-suggest').disabled=false}
}


function ensureStability(){if(!project.stability||typeof project.stability!=='object')project.stability={};project.stability.groups??={};project.stability.members??={};project.stability.lateral_bracing??=[]}
const stabilityFields=[['unbraced_in_plane_mm','Lb no plano (m)'],['unbraced_out_of_plane_mm','Lb lateral (m)'],['torsion_unbraced_mm','Lt torsional (m)'],['k_in_plane','K no plano'],['k_out_of_plane','K fora plano'],['axis_in_plane','Eixo plano'],['axis_out_of_plane','Eixo fora plano'],['rotation_deg','Rotação (°)'],['restraint_note','Observação'],['restraint_reference','Justificativa']];
function renderStabilityEditor(){ensureStability();const groups=Object.entries(GROUP_LABELS);
$('stability-groups').innerHTML=groups.map(([group,title])=>{const d=project.stability.groups[group]||{};return `<div class="panel" style="padding:15px;margin:8px 0"><h3>${html(title)}</h3><div class="field-grid">`+stabilityFields.map(([field,label])=>{let v=d[field];if(field.startsWith('k_'))v??=1;if(field==='rotation_deg')v??=0;if(field==='axis_in_plane'||field==='axis_out_of_plane')return `<div class="field"><label>${label}</label><select data-stability-group="${group}" data-stability-field="${field}"><option value="">A definir</option><option value="x" ${v==='x'?'selected':''}>x (seção)</option><option value="y" ${v==='y'?'selected':''}>y (seção)</option></select></div>`;if(field.endsWith('_mm')&&v!=null)v=v/1000;return `<div class="field"><label>${label}</label><input type="text" data-stability-group="${group}" data-stability-field="${field}" value="${html(v??'')}" placeholder="Pendente"></div>`}).join('')+'</div></div>'}).join('');
$('stability-bracing').value=JSON.stringify(project.stability.lateral_bracing,null,2);renderStabilityMemberOptions();}
function readStabilityGroups(){if(!project)return;ensureStability();const grouped={};document.querySelectorAll('[data-stability-group]').forEach(el=>{const group=el.dataset.stabilityGroup,field=el.dataset.stabilityField;const raw=el.value.trim();grouped[group]??={};if(!raw)return;if(field==='restraint_reference'||field==='restraint_note'){grouped[group][field]=raw;return}if(field==='axis_in_plane'||field==='axis_out_of_plane'){grouped[group][field]=raw;return}let x=Number(raw.replace(',','.'));if(!Number.isFinite(x))throw Error(`Estabilidade ${group}: ${field} inválido`);grouped[group][field]=field.endsWith('_mm')?x*1000:x;});project.stability.groups=grouped;}
function readBracing(){ensureStability();const x=JSON.parse($('stability-bracing').value||'[]');if(!Array.isArray(x))throw Error('Travamentos devem ser uma lista JSON');project.stability.lateral_bracing=x;}
function renderStabilityMemberOptions(){if(!project||!$('stability-member'))return;const current=$('stability-member').value;const members=result?.model?.members||[];$('stability-member').innerHTML=members.map(m=>`<option value="${html(m.id)}">${html(m.id)} · ${html(m.group)}</option>`).join('');if(members.some(m=>m.id===current))$('stability-member').value=current;renderStabilityMemberEditor();}
function renderStabilityMemberEditor(){if(!project)return;ensureStability();const id=$('stability-member').value;const d=project.stability.members[id]||{};$('member-lout').value=d.unbraced_out_of_plane_mm==null?'':Number(d.unbraced_out_of_plane_mm)/1000;$('member-kout').value=d.k_out_of_plane??'';$('member-ref').value=d.restraint_reference??'';}
function saveStabilityMember(){ensureStability();const id=$('stability-member').value;if(!id)throw Error('Selecione uma barra');const d={};const L=$('member-lout').value.trim(),K=$('member-kout').value.trim(),ref=$('member-ref').value.trim();if(L)d.unbraced_out_of_plane_mm=Number(L.replace(',','.'))*1000;if(K)d.k_out_of_plane=Number(K.replace(',','.'));if(ref)d.restraint_reference=ref;project.stability.members[id]=d;}
function renderStabilitySummary(){if(!result||!$('stability-summary'))return;const st=result.stability;let rows=Object.values(st.members);$('stability-summary').innerHTML=`<p class="hint">${st.summary.complete_declared} barras com dados declarados; ${st.summary.pending} pendentes. Nenhuma resistência NBR 14762 foi calculada.</p><div class="table-wrap"><table><thead><tr><th>Barra</th><th>Perfil</th><th>L (m)</th><th>Lb plano</th><th>Lb lateral</th><th>Leff lateral</th><th>Status</th></tr></thead><tbody>${rows.map(d=>`<tr><td>${html(d.member_id)}</td><td>${html(d.profile)}</td><td>${num(d.length_mm/1000,3)}</td><td>${num(d.unbraced_in_plane_mm/1000,3)}</td><td>${d.unbraced_out_of_plane_mm==null?'—':num(d.unbraced_out_of_plane_mm/1000,3)}</td><td>${d.effective_out_of_plane_mm==null?'—':num(d.effective_out_of_plane_mm/1000,3)}</td><td>${html(d.state)}</td></tr>`).join('')}</tbody></table></div>`;}

function renderAdvancedEditor(){
 if(!project)return;
 $('advanced-arrangements').value=JSON.stringify(project.section_arrangements||{},null,2);
 $('advanced-resistances').value=JSON.stringify(project.external_resistances||{members:{}},null,2);
 $('advanced-fy').value=project.material.fy_MPa??250;
 $('advanced-gamma').value=project.axial_options?.gamma_yield_screen??1.1;
 $('advanced-camber-case').value=project.camber?.reference_case??'G1';
 $('advanced-camber-factor').value=project.camber?.compensation_fraction??1;
 $('advanced-opt-options').value=JSON.stringify({service_case:project.combinations?.[0]?.id||'S_GRAV',flecha_rel:250,
   profiles:{superior:[project.sections.superior.profile],inferior:[project.sections.inferior.profile],
   montante:[project.sections.montante.profile],diagonal:[project.sections.diagonal.profile]}},null,2);
}
function readAdvanced(){
 const arr=JSON.parse($('advanced-arrangements').value||'{}');
 const ext=JSON.parse($('advanced-resistances').value||'{"members":{}}');
 if(!arr||typeof arr!=='object'||Array.isArray(arr))throw Error('Arranjos devem ser objeto JSON');
 if(!ext||typeof ext!=='object'||Array.isArray(ext))throw Error('Resistências devem ser objeto JSON');
 project.section_arrangements=arr;project.external_resistances=ext;
 const fy=Number($('advanced-fy').value.replace(',','.'));
 const gamma=Number($('advanced-gamma').value.replace(',','.'));
 const factor=Number($('advanced-camber-factor').value.replace(',','.'));
 if(!Number.isFinite(fy)||fy<=0||!Number.isFinite(gamma)||gamma<=0||!Number.isFinite(factor))throw Error('Parâmetros materiais/contraflecha inválidos');
 project.material.fy_MPa=fy;project.axial_options={gamma_yield_screen:gamma};
 project.camber={reference_case:$('advanced-camber-case').value.trim(),compensation_fraction:factor};
}
function renderAdvancedSummary(){
 if(!result||!$('advanced-summary'))return;
 const a=result.axial_screen.summary,c=result.camber,s=result.section_properties;
 const withSource=Object.values(a).length;
 $('advanced-summary').innerHTML=`<p><strong>${a.total} barras analisadas.</strong> ${a.external_declared} resistências externas declaradas; ${a.external_missing} sem resistência externa; ${a.euler_warning} alertas de Euler. ${a.no_global_geometry} barras sem dados suficientes de estabilidade elástica nos dois planos.</p><p>Contraflecha: ${html(c.state)} · valor máximo ${num(c.max_abs_camber_mm||0,3)} mm (apenas indicativo).</p><p>Seções: ${Object.keys(s.members).length} barras; a resistência ELU permanece <strong>não verificada</strong>.</p>`;
}
async function optimizeAdvanced(){
 readGeometryFields();readStabilityGroups();readBracing();readAdvanced();
 const options=JSON.parse($('advanced-opt-options').value||'{}');
 const target=$('advanced-opt-results');target.textContent='Executando pesquisa de perfis...';
 const r=await api('/api/optimize-sections',{project,options});
 target.innerHTML=`<p>${r.evaluated} alternativas. Massa: ${num(r.mass_kg,2)} kg; flecha: ${num(r.flecha_mm,2)} mm (limite ${num(r.flecha_limit_mm,2)} mm). ELU pendente.</p>`+
   Object.entries(r.selected_sections).map(([k,v])=>`<p>${html(k)}: ${html(v.profile)}</p>`).join('')+
   '<button class="btn btn-light" id="btn-opt-adopt">Adotar perfis pesquisados</button>';
 $('btn-opt-adopt').addEventListener('click',async()=>{
   for(const [k,v] of Object.entries(r.selected_sections))project.sections[k].profile=v.profile;
   project.external_resistances={members:{}}; // dados externos associados ao perfil anterior INVALIDADOS
   renderSections();renderAdvancedEditor();await analyze();
   message('Perfis adotados. Capacidades externas anteriores invalidadas. Sem comprovação ELU.');
 });
}

async function init(){initNavigation();initPanelTabs();try{const [p,c]=await Promise.all([fetch('/api/default').then(r=>r.json()),fetch('/api/catalog').then(r=>r.json())]);project=p;catalog=c;selectedLoad=p.load_cases[0]?.id;selectedCombo=p.combinations[0]?.id;
setGeometryFields();renderSections();renderLoadList();renderCombos();renderSupports();renderStabilityEditor();renderAdvancedEditor();$('project-title').textContent=project.name;
$('length-unit').addEventListener('change',e=>{readGeometryFields();units=e.target.value;setGeometryFields();schedulePreview(false);});
$('e-unit').addEventListener('change',e=>{readGeometryFields();eUnit=e.target.value;setGeometryFields();schedulePreview(false);});
$('h-up').addEventListener('click',()=>{readGeometryFields();project.geometry.height_m=Math.round((project.geometry.height_m+.05)*1000)/1000;setGeometryFields();schedulePreview()});
$('h-down').addEventListener('click',()=>{readGeometryFields();project.geometry.height_m=Math.max(.05,Math.round((project.geometry.height_m-.05)*1000)/1000);setGeometryFields();schedulePreview()});
$('case-kind').addEventListener('change',()=>{updateCaseFormVisibility();if($('case-kind').value==='nodal' && !nodalEditor.hasRows())nodalEditor.addRow();});$('btn-run').addEventListener('click',analyze);$('btn-use-current').addEventListener('click',analyze);$('btn-suggest').addEventListener('click',suggestGeometry);
$('analysis-view').addEventListener('change',e=>{activeCase=e.target.value;if(!dirty)preview=null;drawModel();renderMetrics();renderMembers();renderValidation()});
$('force-view').addEventListener('change',e=>{forceUnit=e.target.value;document.querySelectorAll('.force-unit-label').forEach(el=>el.textContent=forceUnit);drawModel();renderMetrics();renderMembers();if(selectedElement?.type==='member')inspectMember(selectedElement.id);if(selectedElement?.type==='node')inspectNode(selectedElement.id)});
$('show-loads').addEventListener('change',drawModel);$('show-numbers').addEventListener('change',drawModel);$('diagram-mode').addEventListener('change',e=>{$('show-loads').checked=e.target.value==='loads';drawModel()});$('vertical-scale').addEventListener('input',drawModel);$('label-density').addEventListener('change',drawModel);window.addEventListener('resize',()=>{clearTimeout(drawModel.resize);drawModel.resize=setTimeout(drawModel,120)});
$('btn-nodal-add').addEventListener('click',()=>nodalEditor.addRow());
  for(const id of ['member-group-filter','member-status-filter','member-governor-filter','member-sort']) $(id).addEventListener('change',()=>{renderMembers();drawModel();});
  $('member-search').addEventListener('input',renderMembers);
  $('btn-new-case').addEventListener('click',()=>{try{newLoad()}catch(e){message(e.message,true)}});$('btn-delete-case').addEventListener('click',deleteLoad);$('btn-apply-case').addEventListener('click',()=>{try{applyLoad()}catch(e){message(e.message,true)}});
$('factors-grid').addEventListener('input',()=>schedulePreview());$('combo-id').addEventListener('input',()=>schedulePreview());$('btn-new-combo').addEventListener('click',()=>{try{newCombo()}catch(e){message(e.message,true)}});$('btn-delete-combo').addEventListener('click',deleteCombo);$('btn-apply-combo').addEventListener('click',()=>{try{saveCombo()}catch(e){message(e.message,true)}});
$('btn-support-default').addEventListener('click',()=>{try{restoreSupports()}catch(e){message(e.message,true)}});
$('btn-save').addEventListener('click',()=>{try{commitVisibleEditor();readGeometryFields();readStabilityGroups();readBracing();readAdvanced();downloadText('2DTruss_Projeto.json',JSON.stringify(project,null,2),'application/json')}catch(e){message(e.message,true)}});
$('btn-open').addEventListener('click',()=>$('open-file').click());$('open-file').addEventListener('change',async(e)=>{try{const file=e.target.files[0];if(!file)return;if(file.size>2_000_000)throw Error('Projeto JSON excede 2 MB');let p=JSON.parse(await file.text());if(p.schema==='poe-trelica-cff/v05'){p=await api('/api/migrate',p);message('Projeto v0.5 convertido. Revise G_LEG, combinações, vínculos e direção do vento antes de utilizar.',true)}if(p.schema!=='poe-truss-python/v1'||!p.geometry||!p.sections||!Array.isArray(p.load_cases))throw Error('JSON incompatível com poe-truss-python/v1');project=p;result=null;activeCase=null;selectedLoad=project.load_cases[0]?.id;selectedCombo=project.combinations?.[0]?.id;project.combinations??=[];setGeometryFields();renderSections();renderLoadList();renderCombos();renderSupports();renderStabilityEditor();renderAdvancedEditor();schedulePreview();message('Projeto importado. Revise a prévia e execute Calcular.')}catch(err){message(err.message,true)}e.target.value='' });
[['btn-load-audit','load_audit'],['btn-stability-export','stability'],['btn-ftool','ftool'],['btn-ftool-template','ftool_compare'],['btn-dimperfil','dimperfil'],['btn-memorial','memorial'],['btn-axial-export','axial_screen'],['btn-assembly-export','section_properties'],['btn-camber-export','camber'],['btn-advanced-memorial','memorial']].forEach(([id,kind])=>$(id).addEventListener('click',async()=>{try{await exportKind(kind);message('Exportação gerada.')}catch(e){message(e.message,true)}}));
$('btn-advanced-apply').addEventListener('click',async()=>{try{readAdvanced();await analyze()}catch(e){message(e.message,true)}});
$('btn-advanced-optimize').addEventListener('click',async()=>{try{await optimizeAdvanced()}catch(e){message(e.message,true)}});
$('btn-stability-apply').addEventListener('click',()=>{try{readStabilityGroups();message('Grupos de estabilidade atualizados. Recalcule.')}catch(e){message(e.message,true)}});
$('btn-bracing-apply').addEventListener('click',()=>{try{readBracing();message('Travamentos registrados. Recalcule.')}catch(e){message(e.message,true)}});
$('stability-member').addEventListener('change',renderStabilityMemberEditor);
$('btn-member-stability').addEventListener('click',()=>{try{saveStabilityMember();message('Exceção registrada. Recalcule.')}catch(e){message(e.message,true)}});
$('btn-remove-member-stability').addEventListener('click',()=>{delete project.stability?.members?.[$('stability-member').value];renderStabilityMemberEditor();message('Exceção removida. Recalcule.');});
$('btn-stop').addEventListener('click',async()=>{try{await api('/api/shutdown',{});message('Servidor encerrado. Pode fechar esta aba.')}catch(e){message(e.message,true)}});
// Modificações em parâmetros: prévia sem solver, preservando resultados calculados como desatualizados.
const liveIds=['name','span','spacing','height','rise','panels','roof-shape','truss-type','purlin-max','angle-min','angle-max','E'];
for(const id of liveIds)$(id).addEventListener('input',()=>schedulePreview());
$('sections-edit').addEventListener('change',()=>schedulePreview());
const caseIds=['case-value','case-unit','case-application','case-basis','case-direction','case-zone','case-kind'];
for(const id of caseIds)$(id).addEventListener('input',()=>{if(id==='case-kind')updateCaseFormVisibility();schedulePreview();});
await analyze();}catch(e){message('Falha ao inicializar: '+e.message,true);console.error(e)}}
init();
