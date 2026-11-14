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
      const values = [team.rank, team.manager, team.team,
        `${team.wins}–${team.losses}–${team.ties}`, points.format(team.pointsFor), points.format(team.pointsAgainst)];
      values.forEach((value,index) => {
        const cell = document.createElement('td');
        // textContent displays names literally, including apostrophes and emoji.
        cell.textContent = value;
        if (index>=4) cell.className='number';
        row.appendChild(cell);
      });
      fragment.appendChild(row);
    }
    document.getElementById('standings-body').replaceChildren(fragment);
    status.textContent = `Through Week ${data.throughWeek} · Workbook updated ${data.sourceUpdatedAt}`;
    document.getElementById('table-region').hidden = false;
  } catch (error) {
    status.textContent = 'Standings could not be loaded. Please try again later.';
    console.error(error);
  }
}
loadStandings();
