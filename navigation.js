// Cloudflare may serve /history.html as /history; treat both as the same page.
function leaguePagePath(path) {
  const clean = path.replace(/\/+$/, '').replace(/\.html$/, '');
  return clean === '' || clean === '/index' ? '/' : clean;
}
const currentLeaguePage = leaguePagePath(window.location.pathname);
// Keep the same six destinations on every page from one shared file.
const leagueDestinations = [
  ['./', 'Home'], ['./standings.html', 'Current Standings'],
  ['./history.html', 'Season History'], ['./managers.html', 'Manager Profiles'],
  ['./h2h.html', 'Head-to-Head'], ['./recaps.html', 'Recap Archive']
];
for (const nav of document.querySelectorAll('.league-nav, nav[aria-label="League pages"]')) {
  nav.classList.add('league-nav');
  const links = document.createDocumentFragment();
  for (const [href,label] of leagueDestinations) {
    const link = document.createElement('a');
    link.setAttribute('href',href); link.textContent=label;
    links.appendChild(link);
  }
  nav.replaceChildren(links);
}
for (const link of document.querySelectorAll('.league-nav a')) {
  const destination = new URL(link.getAttribute('href'), window.location.href);
  if (destination.origin === window.location.origin &&
      leaguePagePath(destination.pathname) === currentLeaguePage) {
    link.setAttribute('aria-current', 'page');
  } else {
    link.removeAttribute('aria-current');
  }
}
