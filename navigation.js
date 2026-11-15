// Cloudflare may serve /history.html as /history; treat both as the same page.
function leaguePagePath(path) {
  const clean = path.replace(/\/+$/, '').replace(/\.html$/, '');
  return clean === '' || clean === '/index' ? '/' : clean;
}
const currentLeaguePage = leaguePagePath(window.location.pathname);
for (const link of document.querySelectorAll('.league-nav a')) {
  const destination = new URL(link.getAttribute('href'), window.location.href);
  if (destination.origin === window.location.origin &&
      leaguePagePath(destination.pathname) === currentLeaguePage) {
    link.setAttribute('aria-current', 'page');
  } else {
    link.removeAttribute('aria-current');
  }
}
