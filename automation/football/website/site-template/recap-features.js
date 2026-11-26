// Saved-data presentation only. No AI calls or live league connections.
function recapOrder(teams){return [...teams].sort((a,b)=>(b.wins+.5*b.ties)-(a.wins+.5*a.ties)||b.pointsFor-a.pointsFor||b.pointsAgainst-a.pointsAgainst).map((t,i)=>({...t,rank:i+1}));}
function recapAwards(recap){
  const scores=recap.games.flatMap(g=>[{id:g.managerA,points:g.scoreA},{id:g.managerB,points:g.scoreB}]);
  const winners=recap.games.filter(g=>g.winner).map(g=>({id:g.winner,points:g.winner===g.managerA?g.scoreA:g.scoreB}));
  const losers=recap.games.filter(g=>g.winner).map(g=>({id:g.winner===g.managerA?g.managerB:g.managerA,points:g.winner===g.managerA?g.scoreB:g.scoreA}));
  const award=(title,entries,high)=>{const points=(high?Math.max:Math.min)(...entries.map(x=>x.points));return {title,points,ids:entries.filter(x=>x.points===points).map(x=>x.id)};};
  return [award('Highest Scorer 😎',scores,true),award('Lowest Scorer 💩',scores,false),...(winners.length?[award('Lowest winning score',winners,false),award('Highest score in a loss',losers,true)]:[])];
}
function rankMovement(current,previous){if(!previous)return '—';const change=previous.rank-current.rank;return change>0?`↑ ${change}`:change<0?`↓ ${-change}`:'—';}
function renderTransactionLedger(container,edition){
  const create=(tag,text)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;};
  container.replaceChildren();
  if(!edition){container.appendChild(create('p','No saved transaction collection is attached to this week.'));return;}
  container.appendChild(create('p',`${edition.start} through ${edition.end} · Tuesday–Monday · Central time. Saved collection: ${edition.collectedAt}.`));
  const rows=edition.moves,counts=rows.reduce((out,r)=>(out[r.type]=(out[r.type]||0)+1,out),{});
  container.appendChild(create('p',`${rows.length} completed moves · ${counts.Waiver||0} waiver claims · ${counts['Free-agent pickup']||0} free-agent pickups · ${counts['Drop only']||0} drops · ${counts.Trade||0} trades`));
  const days=new Map();
  for(const move of rows){const date=move.timestamp.slice(0,10);if(!days.has(date))days.set(date,[]);days.get(date).push(move);}
  for(const [date,moves] of days){
    const section=create('section');section.appendChild(create('h3',new Date(date+'T12:00:00').toLocaleDateString('en-US',{weekday:'long',month:'short',day:'numeric'})));
    const scroll=create('div');scroll.className='scroll';const table=create('table');table.className='transaction-table';
    const head=create('thead'),labels=create('tr');for(const label of ['Manager / transaction','Details']){const th=create('th',label);th.scope='col';labels.appendChild(th)}head.appendChild(labels);table.appendChild(head);
    const body=create('tbody');
    for(const move of moves){
      const row=create('tr'),manager=create('td');manager.appendChild(create('strong',move.manager));
      manager.appendChild(create('p',`${move.timestamp.slice(11,16)} · ${move.type}${move.bid===null?'':` · $${move.bid} FAAB`}`));row.appendChild(manager);
      const details=create('td');for(const [label,players] of [['Added',move.added],['Dropped',move.dropped]])if(players)details.appendChild(create('p',`${label}: ${players}`));
      if(move.otherManagers)details.appendChild(create('p',`Other participants: ${move.otherManagers}`));
      if(move.assets)details.appendChild(create('p',move.assets));row.appendChild(details);body.appendChild(row);
    }
    table.appendChild(body);scroll.appendChild(table);section.appendChild(scroll);container.appendChild(section);
  }
  container.appendChild(create('p','Completed player moves only. Add/drop pairs count as one move. Failed claims, team-name changes, and private roster analysis are excluded.'));
}
