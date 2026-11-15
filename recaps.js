async function loadRecaps() {
  const get=id=>document.getElementById(id);
  try {
    const response=await fetch('./recaps.json');if(!response.ok)throw new Error('Recap request failed');
    const data=await response.json();
    if(data.schemaVersion!==1||!Array.isArray(data.recaps)||!data.recaps.length||!Array.isArray(data.managers))throw new Error('Invalid recap data');
    const names=new Map(data.managers.map(m=>[m.id,m.name])),weeks=new Set();
    for(const r of data.recaps){
      const key=`${r.season}-${r.week}`;
      if(!Number.isInteger(r.season)||r.season<2010||!Number.isInteger(r.week)||r.week<1||r.week>18||weeks.has(key)||typeof r.headline!=='string'||typeof r.story!=='string'||!Array.isArray(r.games)||!r.games.length||!Array.isArray(r.standings)||!r.standings.length)throw new Error('Invalid week');
      weeks.add(key);const ids=new Set();
      for(const g of r.games){
        if(g.week!==r.week||g.season!==r.season||!names.has(g.managerA)||!names.has(g.managerB)||g.managerA===g.managerB||ids.has(g.managerA)||ids.has(g.managerB)||![g.scoreA,g.scoreB].every(n=>Number.isFinite(n)&&n>=0)||![null,g.managerA,g.managerB].includes(g.winner))throw new Error('Invalid scoreboard');
        ids.add(g.managerA);ids.add(g.managerB);
      }
      if(r.artwork!==null&&(r.artwork!==`recap-week-${String(r.week).padStart(2,'0')}-${r.season}.png`||typeof r.artworkAlt!=='string'))throw new Error('Invalid artwork path');
    }
    const recaps=[...data.recaps].sort((a,b)=>b.season-a.season||b.week-a.week),select=get('recap-week'),yearSelect=get('recap-year');
    const options=document.createDocumentFragment();
    for(const year of [...new Set(recaps.map(r=>r.season))]){const o=document.createElement('option');o.value=String(year);o.textContent=String(year);options.appendChild(o)}
    yearSelect.replaceChildren(options);yearSelect.value=String(recaps[0].season);
    function selectYear(){
      const available=recaps.filter(r=>String(r.season)===yearSelect.value),options=document.createDocumentFragment();
      for(const r of available){const o=document.createElement('option');o.value=String(r.week);o.textContent=`Week ${r.week}`;options.appendChild(o)}
      select.replaceChildren(options);select.value=String(available[0].week);render();
    }
    const number=new Intl.NumberFormat('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
    function tableRows(id,records){
      const fragment=document.createDocumentFragment();
      for(const record of records){const row=document.createElement('tr');for(const entry of record){const cell=document.createElement('td');cell.textContent=entry.text;cell.className=entry.winner?'winner number':'number';row.appendChild(cell)}fragment.appendChild(row)}
      get(id).replaceChildren(fragment);
    }
    function render(){
      const r=recaps.find(r=>String(r.season)===yearSelect.value&&String(r.week)===select.value);
      get('edition').textContent=`${r.season} · WEEK ${r.week} · RECAP DRAFT`;
      get('week-announcement').textContent=`Showing ${r.season}, Week ${r.week}: ${r.headline}`;
      get('headline').textContent=r.headline;get('story').textContent=r.story;
      get('high-manager').textContent=r.highScore.manager;get('high-points').textContent=number.format(r.highScore.points);
      get('close-manager').textContent=`${names.get(r.closest.winner)} over ${names.get(r.closest.winner===r.closest.managerA?r.closest.managerB:r.closest.managerA)}`;
      get('close-margin').textContent=number.format(Math.abs(r.closest.scoreA-r.closest.scoreB));
      get('big-manager').textContent=names.get(r.biggestWin.winner);get('big-margin').textContent=number.format(Math.abs(r.biggestWin.scoreA-r.biggestWin.scoreB));
      get('score-caption').textContent=`${r.season} · Week ${r.week} · ${r.games.length} completed matchups`;
      tableRows('scores',r.games.map(g=>[{text:names.get(g.managerA),winner:g.winner===g.managerA},{text:number.format(g.scoreA),winner:g.winner===g.managerA},{text:names.get(g.managerB),winner:g.winner===g.managerB},{text:number.format(g.scoreB),winner:g.winner===g.managerB}]));
      get('week-totals').textContent=`League total: ${number.format(r.leagueTotal)} points · Median team score: ${number.format(r.median)}.`;
      get('standings-caption').textContent=`Regular-season records through Week ${r.week}`;
      tableRows('recap-standings',r.standings.map(t=>[{text:t.rank},{text:t.manager},{text:`${t.wins}–${t.losses}–${t.ties}`},{text:number.format(t.pointsFor)}]));
      get('art-figure').hidden=!r.artwork;get('art-unavailable').hidden=Boolean(r.artwork);
      get('art-unavailable').textContent='No illustrated cover is attached to this archived week. The written recap and verified scoreboard are available.';
      if(r.artwork){get('artwork').src=`./${r.artwork}`;get('artwork').alt=r.artworkAlt;get('art-link').href=`./${r.artwork}`;}
    }
    get('artwork').addEventListener('error',()=>{get('art-figure').hidden=true;get('art-unavailable').hidden=false;get('art-unavailable').textContent='Artwork could not be loaded. The written recap and scoreboard remain available.'});
    yearSelect.addEventListener('change',selectYear);select.addEventListener('change',render);selectYear();
    get('load-status').textContent=`Saved workbook updated ${data.sourceUpdatedAt}.`;
    get('recap-content').hidden=false;
  }catch(error){get('recap-content').hidden=true;get('load-status').textContent='Weekly recaps could not be loaded. Please try again later.';console.error(error)}
}
loadRecaps();
