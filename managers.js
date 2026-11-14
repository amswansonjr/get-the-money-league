// Reuse history.json: permanent manager IDs connect records across seasons.
function buildProfiles(data) {
  if (data.schemaVersion !== 1 || typeof data.sourceUpdatedAt !== 'string' ||
      !Array.isArray(data.seasons) || data.seasons.length !== 17) throw new Error('Unexpected history data');
  const profiles = new Map(), years = new Set();
  for (const season of data.seasons) {
    if (!Number.isInteger(season.year) || season.year < 2010 || season.year > 2026 || years.has(season.year) ||
        season.status !== (season.year === 2026 ? 'In progress' : 'Complete') ||
        !Array.isArray(season.teams) || season.teams.length !== (season.year === 2010 ? 8 : 12) ||
        !Array.isArray(season.champions) || !season.champions.every(n => typeof n === 'string')) throw new Error('Invalid season');
    years.add(season.year);
    const ids = new Set(), names = new Set();
    for (const team of season.teams) {
      if (typeof team.managerId !== 'string' || !/^MGR-\d{3}$/.test(team.managerId) || ids.has(team.managerId) ||
          typeof team.manager !== 'string' || names.has(team.manager) || typeof team.team !== 'string' ||
          !['wins','losses','ties','games'].every(k => Number.isInteger(team[k]) && team[k] >= 0) ||
          team.wins+team.losses+team.ties !== team.games ||
          !['pointsFor','pointsAgainst'].every(k => Number.isFinite(team[k]) && team[k] >= 0) ||
          !['regularRank','finalRank'].every(k => team[k] === null || (Number.isInteger(team[k]) && team[k] >= 1 && team[k] <= season.teams.length))) throw new Error('Invalid manager record');
      if (season.status === 'Complete' ? team.finalRank === null : team.finalRank !== null) throw new Error('Invalid placement');
      if (season.status === 'Complete' ? !['Playoffs','Sacko'].includes(team.postseasonBracket) : team.postseasonBracket !== null) throw new Error('Missing or invalid tournament classification; update history.json');
      if (season.status !== 'Complete' && (!Number.isInteger(season.throughWeek) || team.games !== season.throughWeek)) throw new Error('Invalid snapshot week');
      ids.add(team.managerId); names.add(team.manager);
      if (!profiles.has(team.managerId)) profiles.set(team.managerId,{id:team.managerId,name:team.manager,seasons:[],wins:0,losses:0,ties:0,completed:0,playoffs:0,sacko:0,titles:[]});
      const profile = profiles.get(team.managerId);
      if (profile.name !== team.manager) throw new Error('Conflicting manager identity');
      profile.seasons.push({year:season.year,status:season.status,throughWeek:season.throughWeek,...team});
      if (season.status === 'Complete') {
        profile.completed++;
        if (team.postseasonBracket === 'Playoffs') profile.playoffs++;
        else profile.sacko++;
        profile.wins+=team.wins; profile.losses+=team.losses; profile.ties+=team.ties;
        if (season.champions.includes(team.manager)) profile.titles.push({year:season.year,shared:season.champions.length>1});
      }
    }
    if (season.champions.some(name => !names.has(name)) || new Set(season.champions).size !== season.champions.length ||
        (season.status === 'Complete' ? season.champions.length === 0 : season.champions.length !== 0)) throw new Error('Invalid champion identity');
  }
  for (const profile of profiles.values()) {
    profile.seasons.sort((a,b)=>b.year-a.year);
    profile.titles.sort((a,b)=>b.year-a.year);
    const games=profile.wins+profile.losses+profile.ties;
    profile.winRate=games ? (profile.wins+0.5*profile.ties)/games : null;
  }
  return [...profiles.values()].sort((a,b)=>a.name.localeCompare(b.name));
}

async function loadManagers() {
  const get=id=>document.getElementById(id);
  try {
    const response=await fetch('./history.json');
    if (!response.ok) throw new Error(`History request failed: ${response.status}`);
    const data=await response.json();
    const profiles=buildProfiles(data);
    const select=get('manager-select'), options=document.createDocumentFragment();
    for (const profile of profiles) {
      const option=document.createElement('option'); option.value=profile.id; option.textContent=profile.name;
      options.appendChild(option);
    }
    select.replaceChildren(options); select.value=profiles[0].id;
    const points=new Intl.NumberFormat('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
    const percent=new Intl.NumberFormat('en-US',{style:'percent',maximumFractionDigits:1});
    function renderProfile() {
      const profile=profiles.find(p=>p.id===select.value);
      get('manager-name').textContent=profile.name;
      const first=profile.seasons[profile.seasons.length-1].year, latest=profile.seasons[0].year;
      get('participation').textContent=`${profile.seasons.length} recorded season${profile.seasons.length===1?'':'s'} · First: ${first} · Latest: ${latest}`;
      get('completed-seasons').textContent=profile.completed;
      get('career-record').textContent=profile.completed ? `${profile.wins}–${profile.losses}–${profile.ties}` : '—';
      get('win-rate').textContent=profile.winRate===null ? '—' : percent.format(profile.winRate);
      get('title-count').textContent=profile.titles.length;
      get('titles').textContent=profile.titles.length ? `Championship seasons: ${profile.titles.map(t=>`${t.year}${t.shared?' (shared)':''}`).join(', ')}.` : 'No championship credits in the saved history.';
      const current=profile.seasons.find(s=>s.status!=='Complete');
      get('current-season').textContent=current ? `${current.year} snapshot through Week ${current.throughWeek}: ${current.wins}–${current.losses}–${current.ties}. Excluded from the completed-season career totals above.` : 'No 2026 participation recorded in this snapshot.';
      get('bracket-summary').textContent=profile.completed ? `${profile.completed} completed seasons · ${profile.playoffs} playoff appearances · ${profile.sacko} Sacko tournament appearances` : 'No completed seasons yet. Tournament appearance rates are not available.';
      const playoffRate=profile.completed ? profile.playoffs/profile.completed : null;
      const sackoRate=profile.completed ? profile.sacko/profile.completed : null;
      get('playoff-label').textContent=`Playoffs: ${profile.playoffs} seasons · ${playoffRate===null?'Rate unavailable':percent.format(playoffRate)}`;
      get('sacko-label').textContent=`Sacko tournament: ${profile.sacko} seasons · ${sackoRate===null?'Rate unavailable':percent.format(sackoRate)}`;
      get('playoff-bar').style.width=`${(playoffRate??0)*100}%`;
      get('sacko-bar').style.width=`${(sackoRate??0)*100}%`;
      const chips=document.createDocumentFragment();
      for (const season of [...profile.seasons].reverse().filter(s=>s.status==='Complete')) {
        const chip=document.createElement('li');
        chip.textContent=`${season.year} · ${season.postseasonBracket}`;
        if (season.postseasonBracket==='Sacko') chip.className='sacko-season';
        chips.appendChild(chip);
      }
      get('bracket-seasons').replaceChildren(chips);
      const rows=document.createDocumentFragment();
      for (const season of profile.seasons) {
        const row=document.createElement('tr');
        const values=[`${season.year}${season.status==='Complete'?'':' · In progress'}`,season.team,`${season.wins}–${season.losses}–${season.ties}`,season.regularRank??'—',season.finalRank??'Pending',points.format(season.pointsFor),points.format(season.pointsAgainst),season.postseasonBracket??'Pending'];
        values.forEach((value,index)=>{
          const cell=document.createElement('td'); cell.textContent=value;
          if (index===5 || index===6) cell.className='number'; row.appendChild(cell);
        });
        rows.appendChild(row);
      }
      get('manager-seasons').replaceChildren(rows);
    }
    select.addEventListener('change',renderProfile); renderProfile();
    get('manager-count').textContent=`${profiles.length} identities in the saved history, including one unknown owner.`;
    get('load-status').textContent=`Workbook snapshot updated ${data.sourceUpdatedAt}.`;
    get('profile-content').hidden=false;
  } catch (error) {
    get('profile-content').hidden=true;
    get('load-status').textContent='Manager profiles could not be loaded. Please try again later.';
    console.error(error);
  }
}
loadManagers();
