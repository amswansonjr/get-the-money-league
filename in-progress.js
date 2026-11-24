async function showCurrentWeekSnapshot(){
  const root=document.getElementById('current-week-snapshot');if(!root)return;
  const make=(tag,text)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;};
  try{
    const response=await fetch('./in-progress.json');if(!response.ok)throw new Error('Snapshot unavailable');const data=await response.json();
    if(data.status==='complete'){if(location.pathname.endsWith('in-progress.html'))root.textContent=`Week ${data.week} is complete. Official results are through Week ${data.completedThroughWeek}.`;return;}
    if(!['in_progress','upcoming'].includes(data.status)||!Array.isArray(data.matches)||data.matches.length!==6)throw new Error('Invalid current-week snapshot');
    root.className='partial-week';const title=make('h2',`${data.season} · Week ${data.week} · ${data.status==='upcoming'?'Upcoming':'In Progress'}`);root.appendChild(title);
    const upcoming=data.status==='upcoming';
    const projected=upcoming&&data.matches.every(match=>match.teams.every(team=>Number.isFinite(team.projectedPoints)));
    root.appendChild(make('p',`${projected?'Projected scores based on saved starting lineups':upcoming?'Team records':'Saved scores'} collected ${data.collectedAt}. Official standings remain through Week ${data.completedThroughWeek}. This snapshot does not refresh automatically.`));
    if(root.dataset.compact==='true'){const link=make('a',`View Week ${data.week} Matchups`);link.href='./in-progress.html';root.appendChild(link);return;}
    const scroll=make('div');scroll.className='scroll';const table=make('table'),head=make('thead'),labels=make('tr');
    for(const label of ['Manager',upcoming?(projected?'Projected Score':'Record'):'Saved Score','Opponent',upcoming?(projected?'Projected Score':'Record'):'Saved Score']){const cell=make('th',label);cell.scope='col';labels.appendChild(cell)}head.appendChild(labels);table.appendChild(head);const body=make('tbody');
    for(const match of data.matches){const row=make('tr');for(const team of match.teams){row.appendChild(make('td',team.manager+(projected&&team.record?` (${team.record})`:'')));row.appendChild(make('td',upcoming?(projected?team.projectedPoints.toFixed(2):(team.record||'—')):team.points.toFixed(2)))}body.appendChild(row)}table.appendChild(body);scroll.appendChild(table);root.appendChild(scroll);
    root.appendChild(make('p',upcoming?'Projections reflect the saved starting lineups and may change as lineups and player outlooks change.':'Partial scores do not assign wins, final awards, playoff clinches, or standings changes.'));
    const link=make('a',`Latest Completed Recap: Week ${data.completedThroughWeek}`);link.href=`./recaps.html?year=${data.season}&week=${data.completedThroughWeek}`;root.appendChild(link);
  }catch(error){root.textContent='The saved current-week snapshot could not be loaded. Completed results remain available.';}
}
showCurrentWeekSnapshot();
