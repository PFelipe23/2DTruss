/* 2DTruss v0.1 — edição estruturada de cargas nodais.
 * Não altera o motor de cargas: apenas edita o contrato `case.loads`.
 */
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const units=new Set(['kgf','tf','kN']);
function parseFinite(raw,field){
 const txt=String(raw??'').trim().replace(/\s/g,'').replace(',','.');
 if(!txt.length||!Number.isFinite(Number(txt)))throw Error(`${field}: valor numérico inválido`);
 return Number(txt);
}
export function createNodalEditor({root,getNodes,getDefaultUnit,onChange}){
 let selected=0, cachedNodeIDs='';
 const host=()=>root();
 const rows=()=>Array.from(host()?.querySelectorAll('[data-nodal-row]')||[]);
 const currentNodes=()=>getNodes().map(x=>x.id);
 function selectRow(index){selected=Math.max(0,Math.min(index,Math.max(rows().length-1,0)));
  rows().forEach((row,i)=>{row.classList.toggle('selected',i===selected);row.setAttribute('aria-selected',String(i===selected))});
 }
 function collect({strict=false}={}){
  const result=[]; const known=currentNodes();
  for(const [i,row] of rows().entries()){
   const node=row.querySelector('[data-field=node]').value;
   const fxText=row.querySelector('[data-field=fx]').value,fyText=row.querySelector('[data-field=fy]').value;
   const force_unit=row.querySelector('[data-field=force_unit]').value;
   const fx=strict?parseFinite(fxText,`Linha ${i+1}, Fx`):Number(String(fxText).replace(',','.'))||0;
   const fy=strict?parseFinite(fyText,`Linha ${i+1}, Fy`):Number(String(fyText).replace(',','.'))||0;
   if(strict && (!node || (known.length && !known.includes(node))))throw Error(`Linha ${i+1}: selecione um nó válido na geometria atual`);
   if(strict && !units.has(force_unit))throw Error(`Linha ${i+1}: unidade desconhecida`);
   if(strict && fx===0 && fy===0)throw Error(`Linha ${i+1}: Fx e Fy não podem ser ambos zero`);
   result.push({node,fx,fy,force_unit});
  }
  if(strict && !result.length)throw Error('Adicione pelo menos uma carga nodal');
  return result;
 }
 function setRows(data){
  const items=Array.isArray(data)?data:[];
  host().replaceChildren();
  items.forEach((row)=>appendRow(row,false));
  selectRow(0);
 }
 function appendRow(data={},signal=true){
  const index=rows().length;
  const nodeIDs=currentNodes();
  const node=String(data.node??nodeIDs[0]??'');
  const unit=units.has(data.force_unit)?data.force_unit:(getDefaultUnit()||'kgf');
  const tr=document.createElement('tr');tr.dataset.nodalRow=String(index);tr.setAttribute('aria-selected','false');
  tr.innerHTML=`<td class="nodal-idx">${index+1}</td><td><select data-field="node" aria-label="Nó da carga ${index+1}">${Array.from(new Set([...nodeIDs,node])).filter(Boolean).map(id=>`<option value="${esc(id)}">${esc(id)}</option>`).join('')}</select></td><td><input data-field="fx" type="text" inputmode="decimal" value="${esc(data.fx??0)}" aria-label="Fx da carga ${index+1}"></td><td><input data-field="fy" type="text" inputmode="decimal" value="${esc(data.fy??0)}" aria-label="Fy da carga ${index+1}"></td><td><select data-field="force_unit" aria-label="Unidade da carga ${index+1}"><option value="kgf">kgf</option><option value="tf">tf</option><option value="kN">kN</option></select></td><td><button type="button" class="nodal-delete" title="Remover carga ${index+1}" aria-label="Remover carga ${index+1}">×</button></td>`;
  host().appendChild(tr);
  tr.querySelector('[data-field=node]').value=node;
  tr.querySelector('[data-field=force_unit]').value=unit;
  tr.addEventListener('click',event=>{
    if(event.target.closest('.nodal-delete'))return;
    selectRow(rows().indexOf(tr));
  });
  tr.querySelector('.nodal-delete').addEventListener('click',()=>{
   const list=collect();list.splice(rows().indexOf(tr),1);setRows(list);onChange();
  });
  tr.addEventListener('input',onChange);
  tr.addEventListener('change',onChange);
  selectRow(index);
  if(signal)onChange();
 }
 function updateNodes(nodes){
  const ids=nodes.map(node=>node.id);
  const key=ids.join('\u0000');if(key===cachedNodeIDs)return;
  cachedNodeIDs=key;
  for(const row of rows()){
    const select=row.querySelector('[data-field=node]'),current=select.value;
    const choices=Array.from(new Set([...ids,current])).filter(Boolean);
    select.replaceChildren(...choices.map(id=>{const op=document.createElement('option');op.value=id;op.textContent=id;return op}));
    select.value=current;
    select.classList.toggle('invalid-node',!ids.includes(current));
  }
 }
 function assignNode(id){
   if(!currentNodes().includes(id))throw Error('Nó não pertence à geometria atual');
   if(!rows().length)appendRow({},false);
   const row=rows()[selected]||rows()[0];
   row.querySelector('[data-field=node]').value=id;
   row.querySelector('[data-field=node]').classList.remove('invalid-node');
   selectRow(rows().indexOf(row));onChange();
 }
 return {
  setRows,
  updateNodes,
  addRow:()=>appendRow({},true),
  assignNode,
  read:()=>collect({strict:true}),
  hasRows:()=>rows().length>0,
 };
}
