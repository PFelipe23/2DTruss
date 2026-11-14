/* 2DTruss v0.1 — filtros de inspeção sobre resultados FEM já calculados.
 * Todas as propriedades resistentes permanecem fora deste módulo.
 */
function norm(str){return String(str??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase()}
export function filterMembers({members,envelope,axial,group='all',status='all',governor='all',search='',sort='demand'}){
 const maxDemand=m=>Math.max(Math.abs(envelope[m.id]?.max_compression_n||0),Math.abs(envelope[m.id]?.max_tension_n||0));
 let items=members.filter(m=>{
   const e=envelope[m.id]||{},N=axial[m.id]||0;
   if(group!=='all'&&m.group!==group)return false;
   if(governor!=='all'&&e.tension_case!==governor&&e.compression_case!==governor)return false;
   if(search&&!norm(`${m.id} ${m.profile} ${m.group}`).includes(norm(search)))return false;
   if(status==='compression'&&N>=-1e-8)return false;
   if(status==='tension'&&N<=1e-8)return false;
   return true;
 });
 if(sort==='id')items.sort((a,b)=>a.id.localeCompare(b.id,undefined,{numeric:true}));
 else if(sort==='length')items.sort((a,b)=>b.length_mm-a.length_mm);
 else items.sort((a,b)=>maxDemand(b)-maxDemand(a));
 if(status==='critical')items=items.slice(0,10);
 return items;
}
export function renderResultsTable({$,result,dirty,activeCase,forceUnit,num,html,forceShown,selectedElement,onSelect,onSummary}){
 const tbody=$('member-rows');
 if(!result){tbody.innerHTML='<tr><td colspan="4">Execute a análise para visualizar os resultados.</td></tr>';onSummary('Aguardando análise');return}
 const analyses=result.analyses||{},envelope=result.envelope||{},members=result.model.members||[];
 if(dirty){tbody.innerHTML='<tr><td colspan="4">Modelo alterado. Recalcule para atualizar os esforços e as envoltórias.</td></tr>';onSummary('Resultados desatualizados');return}
 const governor=$('member-governor-filter'),prior=governor.value;
 const combos=new Set();
 for(const e of Object.values(envelope))for(const field of ['tension_case','compression_case'])if(e[field])combos.add(e[field]);
 const choices=['all',...Array.from(combos).sort()];
 if(governor.options.length!==choices.length || choices.some((v,i)=>governor.options[i]?.value!==v)){
  governor.replaceChildren(...choices.map((id,i)=>{const op=document.createElement('option');op.value=id;op.textContent=i===0?'Todas as governantes':id;return op}));
  governor.value=choices.includes(prior)?prior:'all';
 }
 const rows=filterMembers({members,envelope,axial:analyses[activeCase].axial_n,
  group:$('member-group-filter').value,status:$('member-status-filter').value,
  governor:governor.value,search:$('member-search').value,sort:$('member-sort').value});
 tbody.innerHTML=rows.length?rows.map(m=>{
  const e=envelope[m.id],N=analyses[activeCase].axial_n[m.id];
  return `<tr tabindex="0" data-member-id="${html(m.id)}" class="member-result-row${selectedElement?.type==='member'&&selectedElement.id===m.id?' active':''}" title="${html(m.profile)} · L=${num(m.length_mm/1000,3)} m" aria-label="Inspecionar barra ${html(m.id)}"><td><b>${html(m.id)}</b><small>${html(m.group)}</small></td><td class="${N<0?'neg':'pos'}">${num(forceShown(N),2)}</td><td class="neg">${num(forceShown(e.max_compression_n),2)}<small>${html(e.compression_case||'—')}</small></td><td class="pos">${num(forceShown(e.max_tension_n),2)}<small>${html(e.tension_case||'—')}</small></td></tr>`;
 }).join(''):'<tr><td colspan="4">Nenhuma barra atende aos filtros selecionados.</td></tr>';
 tbody.querySelectorAll('[data-member-id]').forEach(row=>{
  row.addEventListener('click',()=>onSelect(row.dataset.memberId));
  row.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect(row.dataset.memberId)}});
 });
 onSummary(`Exibindo ${rows.length} de ${members.length} barras · caso ${activeCase} · ${forceUnit} · sem verificação ELU`);
}
