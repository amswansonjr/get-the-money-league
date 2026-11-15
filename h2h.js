function rivalry(games,a,b,competition,season) {
  const selected=games.filter(g=>((g.managerA===a&&g.managerB===b)||(g.managerA===b&&g.managerB===a))&&
    (season==='all'||String(g.season)===season)&&
    (competition==='all'||(competition==='championship'?g.championshipFinal:competition==='sacko'?g.sackoFinal:g.phase===competition)))
    .sort((x,y)=>y.season-x.season||y.week-x.week);
  return {games:selected,winsA:selected.filter(g=>g.winner===a).length,winsB:selected.filter(g=>g.winner===b).length,
    ties:selected.filter(g=>g.winner===null).length,
    pointsA:selected.reduce((n,g)=>n+(g.managerA===a?g.scoreA:g.scoreB),0),
    pointsB:selected.reduce((n,g)=>n+(g.managerA===b?g.scoreA:g.scoreB),0)};
}
async function loadH2H() {
  const get=id=>document.getElementById(id);
  try {
    const response=await fetch('./h2h.json');
    if(!response.ok)throw new Error('Matchup data request failed');
    const data=await response.json();
    if(data.schemaVersion!==1||typeof data.sourceUpdatedAt!=='string'||!Array.isArray(data.managers)||data.managers.length<2||!Array.isArray(data.games))throw new Error('Invalid data');
    const names=new Map();
    for(const m of data.managers){if(typeof m.id!=='string'||typeof m.name!=='string'||names.has(m.id))throw new Error('Invalid identity');names.set(m.id,m.name)}
    if(!Number.isInteger(data.currentSeason)||!Array.isArray(data.currentManagerIds)||!data.currentManagerIds.length||
      new Set(data.currentManagerIds).size!==data.currentManagerIds.length||!data.currentManagerIds.every(id=>names.has(id)))throw new Error('Missing current-season roster; update h2h.json');
    const keys=new Set();
    for(const g of data.games){
      const key=[g.season,g.week,...[g.managerA,g.managerB].sort()].join(':');
      if(!names.has(g.managerA)||!names.has(g.managerB)||g.managerA===g.managerB||keys.has(key)||
        !Number.isInteger(g.season)||g.season<2010||g.season>2026||!Number.isInteger(g.week)||g.week<1||g.week>18||
        !['Regular season','Championship playoffs','Loser’s bracket'].includes(g.phase)||
        ![g.scoreA,g.scoreB].every(n=>Number.isFinite(n)&&n>=0)||
        ![null,g.managerA,g.managerB].includes(g.winner)||
        !['awardedWinner','championshipFinal','sackoFinal'].every(k=>typeof g[k]==='boolean')||
        (g.winner===null?g.scoreA!==g.scoreB:g.scoreA===g.scoreB?!g.awardedWinner:g.winner!==(g.scoreA>g.scoreB?g.managerA:g.managerB)))throw new Error('Invalid matchup');
      keys.add(key);
    }
    for(const id of ['manager-a','manager-b']){
      const options=document.createDocumentFragment();
      for(const m of data.managers){const o=document.createElement('option');o.value=m.id;o.textContent=m.name;options.appendChild(o)}
      get(id).replaceChildren(options);
    }
    get('manager-a').value='MGR-001';get('manager-b').value='MGR-002';
    for(const year of [...new Set(data.games.map(g=>g.season))].sort((a,b)=>b-a)){
      const option=document.createElement('option');option.value=String(year);option.textContent=String(year);get('season').appendChild(option);
    }
    const number=new Intl.NumberFormat('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
    function render(){
      const a=get('manager-a').value,b=get('manager-b').value;
      if(a===b){get('results').hidden=true;get('summary').textContent='Choose two different managers to compare.';return}
      const result=rivalry(data.games,a,b,get('competition').value,get('season').value),count=result.games.length;
      get('summary').textContent=count?`${names.get(a)} vs ${names.get(b)} · ${count} recorded games under these filters.`:'No recorded matchups under these filters. Early history is incomplete; this does not establish that these managers never met.';
      get('results').hidden=count===0;
      if(!count)return;
      get('name-a').textContent=names.get(a);get('name-b').textContent=names.get(b);
      get('score-a-heading').textContent=names.get(a);get('score-b-heading').textContent=names.get(b);
      get('wins-a').textContent=`${result.winsA} wins`;get('wins-b').textContent=`${result.winsB} wins`;get('ties').textContent=result.ties;
      get('points-a').textContent=`${number.format(result.pointsA)} total points`;
      get('points-b').textContent=`${number.format(result.pointsB)} total points`;
      get('bar-a').style.width=`${100*result.winsA/count}%`;get('bar-b').style.width=`${100*result.winsB/count}%`;
      const rows=document.createDocumentFragment();
      for(const g of result.games){
        const row=document.createElement('tr'),isA=g.managerA===a;
        const notes=[];
        if(g.awardedWinner)notes.push('Tied score; platform-awarded winner');
        if(g.season===2022&&g.championshipFinal)notes.push('Shared title: Andrew Swanson and Ryan Nelson');
        if(g.season<=2012)notes.push('Recovered Yahoo postseason');
        const phase=g.sackoFinal?'Sacko matchup':g.championshipFinal?'Championship final':g.phase;
        const values=[g.season,g.week,phase,number.format(isA?g.scoreA:g.scoreB),number.format(isA?g.scoreB:g.scoreA),g.winner===null?'Tie':`${names.get(g.winner)} wins`,notes.join('; ')||'—'];
        values.forEach((value,i)=>{const cell=document.createElement('td');cell.textContent=value;if(i===3||i===4)cell.className='number';row.appendChild(cell)});rows.appendChild(row);
      }
      get('matchup-body').replaceChildren(rows);
    }
    function renderMatrix(){
      const managers=data.managers.filter(m=>get('matrix-scope').value==='all'||data.currentManagerIds.includes(m.id));
      const competition=get('competition').value,season=get('season').value;
      get('matrix-summary').textContent=`${managers.length} managers · ${get('matrix-scope').value==='all'?'Historical membership':`${data.currentSeason} membership`} · ${season==='all'?'All recorded seasons':season}. Membership limits the names shown; season and competition filters limit the games counted.`;
      get('matrix-caption').textContent=`Row manager vs column opponent · W–L–T · ${competition==='all'?'All games':competition==='sacko'?'Sacko matchup only':competition==='championship'?'Championship final only':competition}`;
      const header=document.createDocumentFragment(),headRow=document.createElement('tr');
      const corner=document.createElement('th');corner.scope='col';corner.textContent='Row manager ↓ / Opponent →';headRow.appendChild(corner);
      for(const m of managers){const th=document.createElement('th');th.scope='col';th.textContent=m.name;headRow.appendChild(th)}
      header.appendChild(headRow);get('matrix-head').replaceChildren(header);
      const body=document.createDocumentFragment();
      for(const a of managers){
        const row=document.createElement('tr'),label=document.createElement('th');label.scope='row';label.textContent=a.name;row.appendChild(label);
        for(const b of managers){
          const cell=document.createElement('td');
          if(a.id!==b.id){
            const r=rivalry(data.games,a.id,b.id,competition,season),button=document.createElement('button');button.type='button';
            button.textContent=r.games.length?`${r.winsA}–${r.winsB}–${r.ties}`:'—';
            button.className=r.winsA>r.winsB?'positive':r.winsA<r.winsB?'negative':'neutral';
            button.setAttribute('aria-label',`${a.name} vs ${b.name}: ${r.games.length?`${r.winsA} wins, ${r.winsB} losses, ${r.ties} ties`:'no recorded matchups'}. Show rivalry.`);
            button.setAttribute('aria-pressed',String(get('manager-a').value===a.id&&get('manager-b').value===b.id));
            button.addEventListener('click',()=>{
              get('manager-a').value=a.id;get('manager-b').value=b.id;render();
              for(const old of get('matrix-body').querySelectorAll('button[aria-pressed="true"]'))old.setAttribute('aria-pressed','false');
              button.setAttribute('aria-pressed','true');get('summary').scrollIntoView({block:'center'});
            });cell.appendChild(button);
          }
          row.appendChild(cell);
        }
        body.appendChild(row);
      }
      get('matrix-body').replaceChildren(body);
    }
    for(const id of ['manager-a','manager-b'])get(id).addEventListener('change',()=>{render();renderMatrix()});
    for(const id of ['competition','season'])get(id).addEventListener('change',()=>{render();renderMatrix()});
    get('matrix-scope').addEventListener('change',renderMatrix);
    render();renderMatrix();get('h2h-content').hidden=false;
    get('load-status').textContent=`Workbook snapshot updated ${data.sourceUpdatedAt}.`;
  }catch(error){get('h2h-content').hidden=true;get('load-status').textContent='Head-to-Head could not be loaded. Please try again later.';console.error(error)}
}
loadH2H();
