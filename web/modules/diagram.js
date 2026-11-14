/* 2DTruss — módulo SVG. Modelo somente para leitura, sem cálculos FEM. */
const SVG='http://www.w3.org/2000/svg';
function svgNode(tag,attrs,text=''){const el=document.createElementNS(SVG,tag);Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,String(v)));if(text)el.textContent=text;return el}
export function renderDiagram(context){
 const {$,result,preview,dirty,activePage,activeCase,selectedLoad,selectedElement,forceShown,num,forceUnit,inspectMember,inspectNode,inspectPreviewNode,onMemberSelect} = context;

 const isPreview=Boolean(preview)&&(dirty||activePage==='loads'||!result);
 if(!result&&!isPreview)return;
 const svg=$('model-svg');while(svg.firstChild)svg.removeChild(svg.firstChild);
 const model=isPreview?preview.model:result.model;
 const view=isPreview?null:result.analyses[activeCase];
 if(!isPreview&&!view)return;
 const mode=$('diagram-mode').value;
 const loads=isPreview?preview.loads:(view?.loads||{});
 const coords=Object.fromEntries(model.nodes.map(v=>[v.id,v]));
 const xs=model.nodes.map(a=>a.x_mm),ys=model.nodes.map(a=>a.y_mm);
 const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
 const width=Math.max(620,svg.clientWidth||900),height=Math.max(240,svg.clientHeight||380);
 svg.setAttribute('viewBox',`0 0 ${width} ${height}`);
 const vscale=Math.min(3,Math.max(.5,Number($('vertical-scale').value)||1));
 const spanX=Math.max(maxX-minX,1),spanY=Math.max((maxY-minY)*vscale,1);
 const scale=Math.min((width-100)/spanX,(height-115)/spanY);
 const offsetX=(width-spanX*scale)/2-minX*scale;
 const offsetY=(height+spanY*scale)/2+minY*vscale*scale;
 const X=x=>offsetX+x*scale,Y=y=>offsetY-y*scale*vscale;
 const showEffort=!!view&&mode==='efforts';
 const showLoads=mode==='loads'||(mode==='efforts'&&$('show-loads').checked);
 const axial=view?.axial_n||{};
 const forceMax=Math.max(1,...Object.values(axial).map(Math.abs));
 const criticalThreshold=forceMax*.33;
 const activeLabel=$('label-density').value,labels=[];
 svg.appendChild(svgNode('text',{x:15,y:24,fill:'#51687a','font-size':12,'font-weight':700},
  isPreview?'PRÉVIA GEOMÉTRICA / AÇÕES — NÃO CALCULADA':`CASO / COMBINAÇÃO: ${activeCase}`));
 const baseline=Y(minY),axisY=Math.min(height-23,baseline+30);
 svg.appendChild(svgNode('line',{x1:X(minX),y1:axisY,x2:X(maxX),y2:axisY,stroke:'#c9d6df','stroke-width':1}));
 svg.appendChild(svgNode('text',{x:(X(minX)+X(maxX))/2,y:axisY+17,fill:'#6a8195','font-size':11,'text-anchor':'middle'},`L = ${num(spanX/1000,3)} m`));
 for(const m of model.members){
  const a=coords[m.i],b=coords[m.j],N=axial[m.id]||0;
  const color=!showEffort?'#49768e':N>1e-6?'#c33e4a':N < -1e-6?'#116cae':'#8294a2';
  const thickness=showEffort?1.7+3.0*Math.sqrt(Math.abs(N)/forceMax):2.2;
  const line=svgNode('line',{x1:X(a.x_mm),y1:Y(a.y_mm),x2:X(b.x_mm),y2:Y(b.y_mm),stroke:color,
    'stroke-width':thickness,'stroke-linecap':'round',class:'selected-element'+(selectedElement?.type==='member'&&selectedElement.id===m.id?' active':''),'data-id':m.id});
  if(!isPreview && activePage==='members' && $('member-group-filter')?.value!=='all' && $('member-group-filter')?.value!==m.group) line.setAttribute('opacity','.25');
  if(!isPreview){line.addEventListener('click',()=>onMemberSelect(m.id));}
  line.appendChild(svgNode('title',{},`${m.id} · ${m.group}${showEffort?' · N='+num(forceShown(N),2)+' '+forceUnit:''}`));svg.appendChild(line);
  if(showEffort&&$('show-numbers').checked&&activeLabel!=='none'&&(activeLabel==='all'||Math.abs(N)>=criticalThreshold)){
   const ax=X(a.x_mm),ay=Y(a.y_mm),bx=X(b.x_mm),by=Y(b.y_mm);
   const dx=bx-ax,dy=by-ay,len=Math.hypot(dx,dy)||1;
   let ang=Math.atan2(dy,dx)*180/Math.PI;
   if(ang>90)ang-=180;if(ang< -90)ang+=180;
   const sign=m.group==='inferior'?1:-1;
   const offset=(m.group==='montante'?13:12)*sign;
   const mx=(ax+bx)/2-(dy/len)*offset,my=(ay+by)/2+(dx/len)*offset;
   const val=num(forceShown(N),2);
   labels.push({mx,my,ang,val,color,force:Math.abs(N),group:m.group});
  }
 }
 // Distribuição de rótulos com prioridade às barras críticas. A visualização
 // automática não altera o cálculo nem oculta valores disponíveis no tooltip.
 const boxes=[];
 labels.sort((a,b)=>b.force-a.force);
 for(const l of labels){
  const rad=l.ang*Math.PI/180,cos=Math.abs(Math.cos(rad)),sin=Math.abs(Math.sin(rad));
  const len=l.val.length*7.25+8,thick=17;
  const W=len*cos+thick*sin+7,H=len*sin+thick*cos+5;
  const box={x:l.mx-W/2,y:l.my-H/2,w:W,h:H};
  const collision=boxes.some(b=>box.x<b.x+b.w&&box.x+box.w>b.x&&box.y<b.y+b.h&&box.y+box.h>b.y);
  if(activeLabel==='auto'&&collision)continue;
  boxes.push(box);
  svg.appendChild(svgNode('text',{x:l.mx,y:l.my,'text-anchor':'middle','dominant-baseline':'middle',
    'font-size':12,fill:l.color,class:'effort-label',transform:`rotate(${l.ang.toFixed(2)} ${l.mx.toFixed(2)} ${l.my.toFixed(2)})`},l.val));
 }
 for(const s of model.supports){const nd=coords[s.node];if(!nd)continue;const x=X(nd.x_mm),y=Y(nd.y_mm);
  svg.appendChild(svgNode('polygon',{points:`${x},${y+4} ${x-9},${y+17} ${x+9},${y+17}`,fill:'#dfeefa',stroke:'#17608e','stroke-width':1.4}));
  if(s.uy)svg.appendChild(svgNode('line',{x1:x-14,y1:y+19,x2:x+14,y2:y+19,stroke:'#17608e','stroke-width':2}));
 }
 for(const nd of model.nodes){const c=svgNode('circle',{cx:X(nd.x_mm),cy:Y(nd.y_mm),r:3.7,fill:'#fff',stroke:'#29485f','stroke-width':1.6,class:'node-hit','data-node':nd.id});
  c.appendChild(svgNode('title',{},`Nó ${nd.id}`));c.addEventListener('click',()=>inspectPreviewNode(nd.id, isPreview));svg.appendChild(c);
 }
 const summary=$('load-summary');summary.hidden=true;
 if(showLoads){
  const active=Object.entries(loads).filter(([id,f])=>coords[id]&&Math.hypot(f.fx_n,f.fy_n)>1e-7);
  const maxF=Math.max(1,...active.map(([,f])=>Math.hypot(f.fx_n,f.fy_n)));
  const defs=svgNode('defs',{}),marker=svgNode('marker',{id:'poe-load-arrow',markerWidth:8,markerHeight:8,refX:7,refY:3,orient:'auto'});
  marker.appendChild(svgNode('path',{d:'M0,0 L7,3 L0,6',stroke:'#bb7d15','stroke-width':1.4,fill:'none'}));defs.appendChild(marker);svg.appendChild(defs);
  const step=active.length>28?Math.ceil(active.length/28):1;
  for(const [i,[nid,f]] of active.entries()){
   const nd=coords[nid],mag=Math.hypot(f.fx_n,f.fy_n),ux=f.fx_n/mag,uy=-f.fy_n/mag,size=24+18*mag/maxF;
   const x2=X(nd.x_mm)-ux*5,y2=Y(nd.y_mm)-uy*5,x1=x2-ux*size,y1=y2-uy*size;
   const arrow=svgNode('line',{x1,y1,x2,y2,class:'load-arrow','marker-end':'url(#poe-load-arrow)'});
   arrow.appendChild(svgNode('title',{},`${nid}: Fx=${num(forceShown(f.fx_n),2)}, Fy=${num(forceShown(f.fy_n),2)} ${forceUnit}`));svg.appendChild(arrow);
   if(i%step===0){const tx=x1-ux*10,ty=y1-uy*10;
    svg.appendChild(svgNode('text',{x:tx,y:ty,fill:'#9a650f','font-size':11,'text-anchor':'middle',class:'force-label'},num(forceShown(mag),2)));
   }
  }
  const fx=active.reduce((v,[,f])=>v+f.fx_n,0),fy=active.reduce((v,[,f])=>v+f.fy_n,0);
  summary.hidden=false;summary.textContent=`${isPreview?selectedLoad||'Prévia':activeCase} · ${active.length} nós carregados · ΣFx=${num(forceShown(fx),2)} ${forceUnit} · ΣFy=${num(forceShown(fy),2)} ${forceUnit} · valores na seta = módulo`;
 }
 const badge=$('diagram-state');badge.className='diagram-state '+(isPreview?'stale':'calculated');
 badge.textContent=isPreview?'PRÉVIA — SEM ESFORÇOS ATUALIZADOS':'ANÁLISE CALCULADA';
}
