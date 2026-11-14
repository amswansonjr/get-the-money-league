// Load one saved data file, then display the season selected by the visitor.
async function loadHistory() {
  const get = id => document.getElementById(id);
  try {
    const response = await fetch('./history.json');
    if (!response.ok) throw new Error(`History request failed: ${response.status}`);
    const data = await response.json();
    if (data.schemaVersion !== 1 || typeof data.sourceUpdatedAt !== 'string' ||
        !Array.isArray(data.seasons) || data.seasons.length !== 17) throw new Error('Unexpected history data');
    const years = new Set();
    for (const season of data.seasons) {
      if (!Number.isInteger(season.year) || season.year < 2010 || season.year > 2026 || years.has(season.year) ||
          season.status !== (season.year === 2026 ? 'In progress' : 'Complete') ||
          typeof season.platform !== 'string' || !Array.isArray(season.notes) ||
          !season.notes.every(n => typeof n === 'string') || !Array.isArray(season.champions) ||
          !season.champions.every(n => typeof n === 'string') ||
          !Array.isArray(season.teams) || season.teams.length !== (season.year === 2010 ? 8 : 12)) throw new Error('Invalid season');
      years.add(season.year);
      const ids = new Set(), finals = new Set(), ranks = new Set();
      for (const team of season.teams) {
        if (typeof team.managerId !== 'string' || ids.has(team.managerId) ||
            typeof team.manager !== 'string' || typeof team.team !== 'string' ||
            !['wins','losses','ties','games'].every(k => Number.isInteger(team[k]) && team[k] >= 0) ||
            team.wins + team.losses + team.ties !== team.games ||
            !['pointsFor','pointsAgainst'].every(k => Number.isFinite(team[k]) && team[k] >= 0)) throw new Error('Invalid team');
        ids.add(team.managerId);
        for (const [key,seen] of [['regularRank',ranks],['finalRank',finals]]) {
          const value = team[key];
          if (value !== null && (!Number.isInteger(value) || value < 1 || value > season.teams.length || seen.has(value))) throw new Error('Invalid rank');
          if (value !== null) seen.add(value);
        }
        if (season.status === 'Complete' ? team.finalRank === null : team.finalRank !== null) throw new Error('Invalid final placement');
      }
      if (season.status !== 'Complete' && (!Number.isInteger(season.throughWeek) || !season.teams.every(t => t.games === season.throughWeek))) throw new Error('Invalid snapshot week');
    }
    const seasons = [...data.seasons].sort((a,b) => b.year-a.year);
    const select = get('season-select');
    const options = document.createDocumentFragment();
    for (const season of seasons) {
      const option = document.createElement('option');
      option.value = String(season.year);
      option.textContent = `${season.year} · ${season.status}`;
      options.appendChild(option);
    }
    select.replaceChildren(options);
    // Start with the latest completed season; 2026 remains selectable.
    select.value = String(seasons.find(s => s.status === 'Complete').year);
    const points = new Intl.NumberFormat('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
    function renderSeason() {
      const season = seasons.find(s => String(s.year) === select.value);
      const completed = season.status === 'Complete';
      const sortKey = completed ? 'finalRank' : 'regularRank';
      const teams = [...season.teams].sort((a,b) => (a[sortKey] ?? Infinity)-(b[sortKey] ?? Infinity));
      get('season-summary').textContent = `${season.year} · ${season.platform} · ${season.teams.length} teams · ${completed ? 'Completed season' : `In progress through Week ${season.throughWeek}`}`;
      get('champions').textContent = completed
        ? `${season.champions.length > 1 ? 'Shared champions' : 'Champion'}: ${season.champions.join(' and ')}`
        : 'Champion: Pending';
      const notes = document.createDocumentFragment();
      for (const note of season.notes) {
        const p = document.createElement('p'); p.textContent = note; notes.appendChild(p);
      }
      get('season-notes').replaceChildren(notes);
      get('history-caption').textContent = `${season.year} results · Ordered by ${completed ? 'final placement' : 'regular-season rank'}`;
      const rows = document.createDocumentFragment();
      for (const team of teams) {
        const row = document.createElement('tr');
        const values = [team.finalRank ?? (completed ? '—' : 'Pending'),team.regularRank ?? '—',team.manager,team.team,
          `${team.wins}–${team.losses}–${team.ties}`,points.format(team.pointsFor),points.format(team.pointsAgainst)];
        values.forEach((value,index) => {
          const cell = document.createElement('td'); cell.textContent = value;
          if (index >= 5) cell.className = 'number';
          row.appendChild(cell);
        });
        rows.appendChild(row);
      }
      get('history-body').replaceChildren(rows);
    }
    select.addEventListener('change',renderSeason);
    renderSeason();
    get('load-status').textContent = `Workbook snapshot updated ${data.sourceUpdatedAt}.`;
    get('history-content').hidden = false;
  } catch (error) {
    get('history-content').hidden = true;
    get('load-status').textContent = 'Season history could not be loaded. Please try again later.';
    console.error(error);
  }
}
loadHistory();
