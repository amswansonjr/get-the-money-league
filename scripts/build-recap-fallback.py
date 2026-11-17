"""Build a dated, readable saved edition. Run after updating the recap data."""
import json,re
from pathlib import Path
from html import escape

ROOT=Path(__file__).resolve().parents[1]
def jsdata(name):
    text=(ROOT/name).read_text();return json.loads(text[text.index('=')+1:].strip().removesuffix(';'))
def table(headers,rows):
    return '<div class="scroll"><table><thead><tr>'+''.join('<th scope="col">'+escape(str(h))+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+escape(str(v))+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'
data=json.loads((ROOT/'recaps.json').read_text());recap=max(data['recaps'],key=lambda r:(r['season'],r['week']))
year,week=recap['season'],recap['week'];key=f'{year}-{week}';names={m['id']:m['name'] for m in data['managers']}
editorial=jsdata('recap-editorials.js').get(key)
awards=jsdata('recap-sleeper-awards.js').get(key,[])
transactions=json.loads((ROOT/'recap-transactions.json').read_text())['editions'].get(key)
html=f'<section id="saved-recap-fallback"><p class="eyebrow">{year} · Week {week} · Saved written edition</p><h2>{escape(recap["headline"])}</h2><p>{escape(recap["story"])}</p><p class="subtext">Workbook updated {escape(data["sourceUpdatedAt"])}. Interactive selectors become available when the page scripts load.</p>'
if awards:html+='<h2>Weekly awards</h2>'+table(['Award','Manager','Points','Details'],[[a['title'],names[a['managerId']],f'{a["points"]:.2f}',a['description']] for a in awards])
html+='<h2>The scoreboard</h2>'+table(['Manager','Score','Opponent','Score'],[[names[g['managerA']],f'{g["scoreA"]:.2f}',names[g['managerB']],f'{g["scoreB"]:.2f}'] for g in recap['games']])
html+='<h2>Standings watch</h2>'+table(['Position','Manager','Record','Points For','Points Against'],[[t['rank'],t['manager'],f'{t["wins"]}–{t["losses"]}–{t["ties"]}',f'{t["pointsFor"]:.2f}',f'{t["pointsAgainst"]:.2f}'] for t in recap['standings']])
if recap['artwork']:html+='<h2>Illustrated edition</h2><p class="subtext">Illustrated editions began with Week 7 of 2026.</p><figure><a href="./'+escape(recap['artwork'])+'"><img style="max-width:600px;width:100%;height:auto" src="./'+escape(recap['artwork'])+'" alt="'+escape(recap['artworkAlt'])+'" loading="lazy"></a></figure>'
if editorial:
    html+='<h2>'+escape(editorial['title'])+'</h2><p class="subtext">'+escape(editorial['subtitle'])+'</p><div class="banter">'
    teams={t['managerId']:t for t in recap['standings']}
    for entry in editorial['entries']:
        html+=f'<article><h3>{entry["rank"]:02d} · {escape(teams[entry["managerId"]]["team"])}</h3><p><strong>{escape(entry["headline"])}</strong></p><p>{escape(entry["body"])}</p></article>'
    html+='</div>'
if transactions:
    html+=f'<h2>Transactions</h2><p class="subtext">{transactions["start"]} through {transactions["end"]} · Central time · Saved collection {transactions["collectedAt"]}.</p>'
    html+=table(['Completed at (Central)','Manager','Transaction','Added','Dropped','FAAB'],[[m['timestamp'],m['manager'],m['type'],m['added'] or '—',m['dropped'] or '—',m['bid'] if m['bid'] is not None else '—'] for m in transactions['moves']])
html+='</section>'
page=ROOT/'recaps.html';text=page.read_text();text=re.sub(r'<!-- SAVED-EDITION-START -->.*?<!-- SAVED-EDITION-END -->','<!-- SAVED-EDITION-START -->\n'+html+'\n  <!-- SAVED-EDITION-END -->',text,flags=re.S);page.write_text(text)
home=ROOT/'index.html';tile=f'''<section class="this-week" id="this-week" aria-label="This week in the league"><div><p class="eyebrow">THIS WEEK</p><p data-week-label>{year} · Week {week}</p><h2 data-headline>{escape(recap['headline'])}</h2><p data-story>{escape(recap['story'])}</p><p><a href="./recaps.html?year={year}&amp;week={week}">Read this week’s recap</a></p></div><img src="./{escape(recap['artwork'] or 'league-crest.png')}" alt="{escape(recap['artworkAlt'] or 'League crest')}" loading="lazy"></section>'''
home.write_text(re.sub(r'<!-- THIS-WEEK-START -->.*?<!-- THIS-WEEK-END -->','<!-- THIS-WEEK-START -->\n'+tile+'\n    <!-- THIS-WEEK-END -->',home.read_text(),flags=re.S))
print(f'Built saved {year} Week {week} fallback and homepage feature.')
