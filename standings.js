// JSON holds the data; this script turns each record into a table row.
async function loadStandings() {
  const status = document.getElementById('status');
  try {
    const response = await fetch('./standings-2026.json');
    if (!response.ok) throw new Error(`Data request failed: ${response.status}`);
    const data = await response.json();
    if (data.season !== 2026 || !Number.isInteger(data.throughWeek) ||
        typeof data.sourceUpdatedAt !== 'string' || !Array.isArray(data.standings) ||
        data.standings.length !== 12) throw new Error('Unexpected standings data');
    const teams = [...data.standings].sort((a,b) => a.rank-b.rank);
    const ids = new Set();
    teams.forEach((team,index) => {
      if (team.rank !== index+1 || typeof team.managerId !== 'string' || ids.has(team.managerId) ||
          typeof team.manager !== 'string' || typeof team.team !== 'string' ||
          !['wins','losses','ties'].every(k => Number.isInteger(team[k]) && team[k]>=0) ||
          team.wins+team.losses+team.ties !== data.throughWeek ||
          !['pointsFor','pointsAgainst'].every(k => Number.isFinite(team[k]) && team[k]>=0)) {
        throw new Error('Invalid standings row');
      }
      ids.add(team.managerId);
    });
    const fragment = document.createDocumentFragment();
    const points = new Intl.NumberFormat('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
    for (const team of teams) {
      const row = document.createElement('tr');
      row.dataset.manager = team.manager.toLowerCase();
      row.dataset.team = team.team.toLowerCase();
      const values = [team.rank, team.manager, team.team,
        `${team.wins}–${team.losses}–${team.ties}`, points.format(team.pointsFor), points.format(team.pointsAgainst)];
      values.forEach((value,index) => {
        const cell = document.createElement('td');
        // textContent displays names literally, including apostrophes and emoji.
        cell.textContent = value;
        if(index===1){const link=document.createElement('a');link.href=`./managers.html?manager=${team.managerId}`;link.textContent=value;cell.textContent='';cell.appendChild(link);}
        if (index>=4) cell.className='number';
        row.appendChild(cell);
      });
      fragment.appendChild(row);
    }
    document.getElementById('standings-body').replaceChildren(fragment);
    status.textContent = `Through Week ${data.throughWeek} · Workbook updated ${data.sourceUpdatedAt}`;
    document.getElementById('table-region').hidden = false;
    const search = document.getElementById('manager-search');
    const results = document.getElementById('search-results');
    const rows = [...document.getElementById('standings-body').children];
    function filterStandings() {
      const query = search.value.trim().toLowerCase();
      let visible = 0;
      for (const row of rows) {
        const matches = row.dataset.manager.includes(query) || row.dataset.team.includes(query);
        row.hidden = !matches;
        if (matches) visible++;
      }
      results.textContent = visible === 0
        ? 'No matching managers or teams. Clear the search to show everyone.'
        : `Showing ${visible} of ${rows.length} managers.`;
    }
    search.addEventListener('input', filterStandings);
    document.getElementById('search-controls').hidden = false;
    filterStandings();
    // Optional standings movement; a missing archive cannot hide current standings.
    fetch('./recaps.json').then(r=>r.ok?r.json():null).then(archive=>{
      if(!archive||archive.sourceSha256!==data.sourceSha256)return;
      const previous=archive.recaps.find(r=>r.season===data.season&&r.week===data.throughWeek-1);if(!previous)return;
      teams.forEach((team,index)=>{const before=previous.standings.find(t=>t.managerId===team.managerId);if(!before)return;const delta=before.rank-team.rank;const cell=rows[index].children[0];cell.textContent=`${team.rank} ${delta>0?'↑ '+delta:delta<0?'↓ '+(-delta):'—'}`;});
    }).catch(()=>{});
  } catch (error) {
    status.textContent = 'Standings could not be loaded. Please try again later.';
    console.error(error);
  }
}
loadStandings();
