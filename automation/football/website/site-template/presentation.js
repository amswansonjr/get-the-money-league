// Display-only helpers. Category ranks never change official standings or tiebreakers.
function categoryRank(teams,team,key){
  const score=Math.round(team[key]*100);
  return 1+teams.filter(other=>key==='pointsAgainst'?Math.round(other[key]*100)<score:Math.round(other[key]*100)>score).length;
}
function rankedPoints(teams,team,key){return `${team[key].toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})} (${categoryRank(teams,team,key)})`;}
function movementBadge(delta){const badge=document.createElement('span');badge.className=delta>0?'movement-up':delta<0?'movement-down':'movement-flat';badge.textContent=delta>0?`↑ ${delta}`:delta<0?`↓ ${-delta}`:'—';return badge;}
function leagueTitleCase(text){
  const minor=new Set(['a','an','and','as','at','but','by','for','from','in','into','nor','of','on','or','per','the','to','via','vs','with']);
  const acronyms=new Set(['PF','PA','ID','NFL','ESPN','H2H','QB','RB','WR','TE','DEF','FAAB','API','JSON','TD','W','L','T','W–L–T','GET']);
  const words=[...text.matchAll(/[A-Za-zÀ-ÿ]+(?:[’'][A-Za-z]+)*/g)];let index=0;
  return text.replace(/[A-Za-zÀ-ÿ]+(?:[’'][A-Za-z]+)*/g,(word,offset)=>{const i=index++,low=word.toLowerCase();if(acronyms.has(word))return word;if(word==='i')return 'I';return i!==0&&i!==words.length-1&&!/[:|·—]\s*$/.test(text.slice(0,offset))&&minor.has(low)?low:word.charAt(0).toUpperCase()+word.slice(1).toLowerCase();});
}
function titleCaseCategoryHeaders(){
  const selectors='h1,h2,h3,th,label,summary,caption,button,.league-nav a';
  const dynamicNames=new Set(['headline','manager-name','score-a-heading','score-b-heading','name-a','name-b']);
  document.querySelectorAll(selectors).forEach(element=>{
    if(element.closest('#weekly-banter')||element.closest('.banter article')||element.hasAttribute('data-headline')||dynamicNames.has(element.id)||element.textContent.includes('GET THE $$$$'))return;
    // Names and dynamic matchup captions are not category headers.
    if(element.closest('#matrix-head')||element.closest('#matrix-body')||element.tagName==='TH'&&element.scope==='row')return;
    for(const node of element.childNodes)if(node.nodeType===Node.TEXT_NODE)node.textContent=leagueTitleCase(node.textContent).replace(/\bPoints for\b/g,'Points For').replace(/\bManager a ID\b/g,'Manager A ID');
  });
}
document.addEventListener('DOMContentLoaded',()=>{
  titleCaseCategoryHeaders();
  // Async renderers can populate category headings after the initial page load.
  const observer=new MutationObserver(records=>{
    const meaningful=records.some(record=>record.type==='childList'&&record.addedNodes.length);
    if(meaningful){observer.disconnect();titleCaseCategoryHeaders();observer.observe(document.body,{childList:true,subtree:true});}
  });
  observer.observe(document.body,{childList:true,subtree:true});
});
