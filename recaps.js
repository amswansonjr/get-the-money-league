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
      if(r.artworkNotes!==undefined&&(!Array.isArray(r.artworkNotes)||!r.artworkNotes.every(note=>typeof note==='string')))throw new Error('Invalid artwork notes');
    }
    const recaps=[...data.recaps].sort((a,b)=>b.season-a.season||b.week-a.week),select=get('recap-week'),yearSelect=get('recap-year');
    const options=document.createDocumentFragment();
    for(const year of [...new Set(recaps.map(r=>r.season))]){const o=document.createElement('option');o.value=String(year);o.textContent=String(year);options.appendChild(o)}
    const requested=new URLSearchParams(window.location.search);
    const initial=recaps.find(r=>String(r.season)===requested.get('year')&&String(r.week)===requested.get('week'))||recaps[0];
    let transactions={};
    yearSelect.replaceChildren(options);yearSelect.value=String(initial.season);
    function selectYear(preferredWeek){
      const available=recaps.filter(r=>String(r.season)===yearSelect.value),options=document.createDocumentFragment();
      for(const r of available){const o=document.createElement('option');o.value=String(r.week);o.textContent=`Week ${r.week}`;options.appendChild(o)}
      select.replaceChildren(options);select.value=String(available.find(r=>String(r.week)===String(preferredWeek))?.week||available[0].week);render();
    }
    const number=new Intl.NumberFormat('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
    function tableRows(id,records){
      const fragment=document.createDocumentFragment();
      for(const record of records){const row=document.createElement('tr');for(const entry of record){const cell=document.createElement('td');if(entry.href){const a=document.createElement('a');a.href=entry.href;a.textContent=entry.text;cell.appendChild(a)}else cell.textContent=entry.text;cell.className=entry.winner?'winner number':'number';if(String(entry.text).startsWith('↑'))cell.className+=' movement-up';if(String(entry.text).startsWith('↓'))cell.className+=' movement-down';row.appendChild(cell)}fragment.appendChild(row)}
      get(id).replaceChildren(fragment);
    }
    function render(){
      const r=recaps.find(r=>String(r.season)===yearSelect.value&&String(r.week)===select.value);
      const shareURL=new URL(window.location.href);shareURL.search=`?year=${r.season}&week=${r.week}`;shareURL.hash='';
      get('share-link').href=shareURL.href;
      get('share-status').textContent='';
      get('edition').textContent=`${r.season} · WEEK ${r.week}`;
      get('recap-footer').textContent=`Saved ${r.season} workbook results through Week ${r.week}. Updated ${data.sourceUpdatedAt}.`;
      get('week-announcement').textContent=`Showing ${r.season}, Week ${r.week}: ${r.headline}`;
      get('headline').textContent=r.headline;get('story').textContent=r.story;
      const dispatches=document.createDocumentFragment();
      const editorial=recapEditorials[`${r.season}-${r.week}`];
      const priorEditorial=recapEditorials[`${r.season}-${r.week-1}`];
      get('banter-heading').textContent=editorial?.title||'Some Disrespectful Dispatches';
      get('banter-description').textContent=editorial?(editorial.subtitle+(!priorEditorial?' This is the first archived ranked edition; editorial movement begins once a previous edition exists.':'')):'Twelve teams. Six receipts. Nobody gets a bye from the group chat. Score-based league banter for the selected week.';
      const dispatchesForWeek=editorial?editorial.entries.map(entry=>{
        const team=r.standings.find(t=>t.managerId===entry.managerId);
        const game=r.games.find(g=>g.managerA===entry.managerId||g.managerB===entry.managerId);
        const isA=game.managerA===entry.managerId,score=isA?game.scoreA:game.scoreB,opponentScore=isA?game.scoreB:game.scoreA;
        const opponent=names.get(isA?game.managerB:game.managerA);
        return {headline:`${String(entry.rank).padStart(2,'0')} · ${team.team} — ${names.get(entry.managerId)}`,tagline:entry.headline,body:entry.body,lines:[
          `Record: ${team.wins}–${team.losses}${team.ties?`–${team.ties}`:''} · Streak: ${entry.streak}`,
          `Week ${r.week}: ${number.format(score)}–${number.format(opponentScore)} vs. ${opponent}`,
          `Season Points For: ${number.format(team.pointsFor)} · Points Against: ${number.format(team.pointsAgainst)}`,
          ...(priorEditorial?[`Power-ranking movement: ${rankMovement(entry,priorEditorial.entries.find(t=>t.managerId===entry.managerId))}`]:[])
        ]};
      }):buildRecapBanter(r,names);
      for(const dispatch of dispatchesForWeek){
        const article=document.createElement('article'),heading=document.createElement('h3'),list=document.createElement('ul');
        heading.textContent=dispatch.headline;article.appendChild(heading);
        if(dispatch.tagline){const tagline=document.createElement('p'),strong=document.createElement('strong');strong.textContent=dispatch.tagline;tagline.appendChild(strong);article.appendChild(tagline)}
        if(dispatch.body){const paragraph=document.createElement('p');paragraph.textContent=dispatch.body;article.appendChild(paragraph)}
        for(const line of dispatch.lines){const item=document.createElement('li');item.textContent=line;list.appendChild(item)}
        article.appendChild(list);dispatches.appendChild(article);
      }
      get('weekly-banter').replaceChildren(dispatches);
      const reported=sleeperWeeklyAwards[`${r.season}-${r.week}`];
      const calculated=recapAwards(r).filter(a=>['Highest Scorer 😎','Lowest Scorer 💩'].includes(a.title));
      const marginAward=(title,g)=>({title,points:Math.abs(g.scoreA-g.scoreB),ids:[g.winner],description:'Point winning margin from the saved scoreboard.'});
      const awards=reported||[...calculated,marginAward('Biggest Blowout 😂',r.biggestWin),marginAward('Narrow Victory 😱',r.closest)];
      get('awards-source').textContent=reported?'Sleeper weekly-report awards from the supplied report. Team and player scores checked against the saved lineups. Blowout and victory percentages use the losing team’s score.':'These four awards are calculated from the saved scoreboard. Manager-efficiency, projection, and position awards are not attached to this archived week.';
      const groups={team:document.createDocumentFragment(),starter:document.createDocumentFragment(),bench:document.createDocumentFragment()};
      for(const award of awards){const card=document.createElement('div'),heading=document.createElement('h3'),manager=document.createElement('p'),points=document.createElement('p'),detail=document.createElement('p');card.className='card';heading.textContent=award.title;manager.textContent=award.managerId?names.get(award.managerId):award.ids.map(id=>names.get(id)).join(' / ');points.className='value';points.textContent=number.format(award.points);detail.textContent=award.description||'';card.appendChild(heading);card.appendChild(manager);card.appendChild(points);card.appendChild(detail);groups[award.group||'team'].appendChild(card)}
      get('weekly-awards').replaceChildren(groups.team);get('position-awards').replaceChildren(groups.starter);get('bench-awards').replaceChildren(groups.bench);get('position-awards-group').hidden=!reported;
      get('score-caption').textContent=`${r.season} · Week ${r.week} · ${r.games.length} completed matchups`;
      tableRows('scores',r.games.map(g=>[{text:names.get(g.managerA),href:`./managers.html?manager=${g.managerA}`,winner:g.winner===g.managerA},{text:number.format(g.scoreA),winner:g.winner===g.managerA},{text:names.get(g.managerB),href:`./managers.html?manager=${g.managerB}`,winner:g.winner===g.managerB},{text:number.format(g.scoreB),winner:g.winner===g.managerB},{text:'H2H',href:`./h2h.html?a=${g.managerA}&b=${g.managerB}&year=${r.season}`} ]));
      get('week-totals').textContent=`League total: ${number.format(r.leagueTotal)} points · Median team score: ${number.format(r.median)}.`;
      get('standings-caption').textContent=`Regular-season records through Week ${r.week}`;
      const previous=recaps.find(p=>p.season===r.season&&p.week===r.week-1),priorTeams=previous?recapOrder(previous.standings):[];
      tableRows('recap-standings',recapOrder(r.standings).map(t=>[{text:t.rank},{text:rankMovement(t,priorTeams.find(p=>p.managerId===t.managerId))},{text:t.manager,href:`./managers.html?manager=${t.managerId}`},{text:`${t.wins}–${t.losses}–${t.ties}`},{text:number.format(t.pointsFor)},{text:number.format(t.pointsAgainst)}]));
      renderTransactionLedger(get('transaction-ledger'),transactions[`${r.season}-${r.week}`]);
      get('art-figure').hidden=!r.artwork;get('art-unavailable').hidden=Boolean(r.artwork);
      get('art-unavailable').textContent=r.season===2026&&r.week<7?'Illustrated editions began with Week 7 of 2026. Written results are available for this week.':'No illustrated cover is attached to this archived week. Written results are available.';
      const notes=document.createDocumentFragment();
      for(const note of r.artworkNotes??[]){const p=document.createElement('p');p.textContent=note;notes.appendChild(p)}
      get('art-corrections').replaceChildren(notes);get('art-corrections').hidden=!(r.artworkNotes?.length);
      if(r.artwork){get('artwork').src=`./${r.artwork}`;get('artwork').alt=r.artworkAlt;get('art-link').href=`./${r.artwork}`;}
    }
    get('artwork').addEventListener('error',()=>{get('art-figure').hidden=true;get('art-unavailable').hidden=false;get('art-unavailable').textContent='Artwork could not be loaded. The written recap and scoreboard remain available.'});
    yearSelect.addEventListener('change',()=>selectYear());select.addEventListener('change',render);selectYear(initial.week);
    get('share-week').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(get('share-link').href);get('share-status').textContent='Link copied.'}catch{get('share-status').textContent='Copy the link from “Open this week” below.'}});
    fetch('./recap-transactions.json').then(response=>{if(!response.ok)throw new Error('No transaction snapshot');return response.json()}).then(snapshot=>{transactions=snapshot.editions||{};renderTransactionLedger(get('transaction-ledger'),transactions[`${yearSelect.value}-${select.value}`])}).catch(()=>{get('transaction-ledger').textContent='The saved transaction collection could not be loaded. Weekly results remain available.'});
    get('load-status').textContent=`Saved workbook updated ${data.sourceUpdatedAt}.`;
    get('recap-content').hidden=false;
    get('saved-recap-fallback').hidden=true;
  }catch(error){get('recap-content').hidden=true;get('load-status').textContent='Showing the saved written edition below. Interactive week selection is unavailable.';console.error(error)}
}
loadRecaps();
