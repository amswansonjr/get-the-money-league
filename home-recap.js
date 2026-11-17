async function showLatestRecap(){
  try{
    const response=await fetch('./recaps.json');if(!response.ok)return;
    const data=await response.json(),latest=[...data.recaps].sort((a,b)=>b.season-a.season||b.week-a.week)[0];if(!latest)return;
    const root=document.getElementById('this-week');
    root.querySelector('[data-week-label]').textContent=`${latest.season} · Week ${latest.week}`;
    root.querySelector('[data-headline]').textContent=latest.headline;
    root.querySelector('[data-story]').textContent=latest.story;
    root.querySelector('a').href=`./recaps.html?year=${latest.season}&week=${latest.week}`;
    const image=root.querySelector('img');image.hidden=!latest.artwork;if(latest.artwork){image.src='./'+latest.artwork;image.alt=latest.artworkAlt;}
  }catch(error){/* The saved homepage edition remains readable. */}
}
showLatestRecap();
