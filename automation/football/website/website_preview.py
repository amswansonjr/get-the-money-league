#!/usr/bin/env python3
"""Read-only saved-workbook export. Standard library; no network or Git writes."""
import argparse, datetime as dt, hashlib, json, math, os, posixpath, re, shutil
import statistics, sys, tempfile, uuid, zipfile
from collections import defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET

NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
def require(condition,message):
    if not condition: raise ValueError(message)
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def integer(value):
    n=float(value);require(math.isfinite(n) and n.is_integer(),'Expected whole number: '+str(value));return int(n)
def points(value):
    n=float(value);require(math.isfinite(n),'Nonfinite points');return round(n,2)
def write_json(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
class Workbook:
    def __init__(self,path):
        self.z=zipfile.ZipFile(path)
        rels={r.get('Id'):r.get('Target') for r in ET.fromstring(self.z.read('xl/_rels/workbook.xml.rels'))}
        self.paths={}
        for s in ET.fromstring(self.z.read('xl/workbook.xml')).findall('s:sheets/s:sheet',NS):
            target=rels[s.get('{'+REL+'}id')]
            self.paths[s.get('name')]=posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/'+target)
        self.strings=[''.join(si.itertext()) for si in ET.fromstring(self.z.read('xl/sharedStrings.xml'))] if 'xl/sharedStrings.xml' in self.z.namelist() else []
        self.cache={}
    def rows(self,name):
        if name not in self.cache:
            result=[]
            for row in ET.fromstring(self.z.read(self.paths[name])).findall('s:sheetData/s:row',NS):
                values={}
                for c in row:
                    value=c.find('s:v',NS);value=(value.text or '') if value is not None else ''
                    if c.get('t')=='s' and value:value=self.strings[int(value)]
                    if c.get('t')=='inlineStr':value=''.join(c.find('s:is',NS).itertext())
                    values[re.sub(r'\d','',c.get('r'))]=value
                result.append((int(row.get('r')),values))
            self.cache[name]=result
        return self.cache[name]
    def cell(self,name,address):
        col=re.sub(r'\d','',address);row=int(re.sub(r'\D','',address))
        return next((v.get(col,'') for i,v in self.rows(name) if i==row),'')
    def data(self,name):return [r for i,r in self.rows(name) if i>1]

def export(config,base,source):
    year=integer(config['season']);size=integer(config['teamCount']);regular=integer(config['regularSeasonWeeks'])
    require(year==2026,'This first preview release supports the existing 2026 website contracts only. New-season and postseason support require validation before activation.')
    book=Workbook(source)
    directory={r['A']:r['B'] for r in book.data('Manager Directory') if r.get('A')}
    originals=dict(directory);mapping={}
    corrections=config.get('identityCorrections',[])
    for fix in corrections:
        require(directory.get(fix['managerId'])==fix['manager'],'Correction target identity missing')
        require(fix['previousManagerId']!=fix['managerId'],'Invalid identity correction')
        mapping[(fix['season'],fix['previousManagerId'])]=fix['managerId']
    def corrected(season,id):return mapping.get((season,id),id)
    latest=integer(book.cell(f'{year} Live Source','I2'))
    require(1<=latest<=regular,'Completed week is outside validated regular-season range')
    stamp=book.cell('HQ Dashboard','B37');require(bool(stamp),'Missing saved refresh timestamp')
    groups=defaultdict(list);rosters={}
    for r in book.data('Season History Data'):
        if not r.get('A'):continue
        y=integer(r['A']);require(y<=year,'Workbook contains a later season than configuration')
        require(originals.get(r['C'])==r['D'],'Season manager ID/name mismatch')
        id=corrected(y,r['C'])
        rank=lambda x:integer(x) if x not in ('','N/A','TBD') else None
        completed=r['L']=='Complete'
        require(r['L'] in ('Complete','In progress'),'Unknown season status')
        require(completed==(y<year),'Current or historical season completion status changed; review required')
        require(r.get('S') in ('0','1') if completed else r.get('S','')=='','Unknown postseason classification')
        t=dict(managerId=id,manager=directory[id],team=r['E'],wins=integer(r['F']),losses=integer(r['G']),ties=integer(r['O']),games=integer(r['P']),pointsFor=points(r['H']),pointsAgainst=points(r['I']),regularRank=rank(r['M']),finalRank=rank(r['N']),postseasonBracket=('Playoffs' if r['S']=='1' else 'Loser’s bracket') if completed else None)
        require(t['wins']+t['losses']+t['ties']==t['games'],'Season record arithmetic mismatch')
        require(abs(points(r['J'])-(t['pointsFor']-t['pointsAgainst']))<.011,'Season differential mismatch')
        groups[y].append(t)
        if y==year:rosters[id]=integer(r['B'])
    require(year in groups and len(groups[year])==size,'Current roster count mismatch')
    titles={integer(r['A']):r for r in book.data('Finals & Titles') if r.get('A')}
    seasons=[]
    for y,teams in sorted(groups.items(),reverse=True):
        require(len({t['managerId'] for t in teams})==len(teams),'Duplicate manager in season')
        require(sum(t['wins'] for t in teams)==sum(t['losses'] for t in teams),'Season wins/losses not balanced')
        require(round(sum(t['pointsFor']-t['pointsAgainst'] for t in teams),2)==0,'Season PF/PA not balanced')
        ranks=[t['regularRank'] for t in teams if t['regularRank'] is not None]
        require(len(ranks)==len(set(ranks)) and all(1<=r<=len(teams) for r in ranks),'Duplicate or invalid regular ranks')
        completed=y<year
        if completed:
            require(sorted(t['finalRank'] for t in teams)==list(range(1,len(teams)+1)),'Missing final placements')
            require(next(t for t in teams if t['finalRank']==1)['manager']==titles[y]['B'],'Final placement/title mismatch')
        else:
            require(all(t['games']==latest and t['finalRank'] is None for t in teams),'Current season does not match completed week')
            require(sorted(ranks)==list(range(1,size+1)),'Current ranks are incomplete')
        champs=[] if not completed else [titles[y]['B']]+([titles[y]['Q']] if titles[y].get('Q') else [])
        notes=[]
        if y<=2012:notes.append('Yahoo: recovered season totals and postseason games; full regular-season matchup schedules are unavailable. — means unavailable rank.')
        if y==2012:notes.append('Alabama Hot Pockets belongs to Timothy Doan, confirmed November 14, 2026; source-workbook identity corrected in website export only.')
        if y==2022:notes.append('Shared champions: Andrew Swanson and Ryan Nelson. Recorded final placements and matchup winner remain unchanged.')
        if not completed:notes.append(f'Season in progress through Week {latest}. Final placement is pending.')
        seasons.append(dict(year=y,status='Complete' if completed else 'In progress',throughWeek=None if completed else latest,platform='Yahoo' if y<=2012 else 'ESPN' if y<=2020 else 'Sleeper',champions=champs,notes=notes,teams=teams))
    # Cached Matchups contains intentionally blank formula placeholders. A partly populated record must fail.
    games=[];seen=set();name_ids={v:k for k,v in originals.items()}
    for r in book.data('Matchups'):
        if not r.get('A'):
            require(not any(r.get(k) for k in ['B','C','E','F','G','H','I','K','L']),'Partly populated matchup row');continue
        y=integer(r['A']);w=integer(r['B'])
        require(y<=year and (y!=year or w<=latest),'Unexpected future/uncompleted matchup')
        a=r.get('K') or name_ids.get(r.get('E'));b=r.get('L') or name_ids.get(r.get('G'))
        require(a in originals and b in originals and originals[a]==r['E'] and originals[b]==r['G'],'Game identity mismatch')
        a,b=corrected(y,a),corrected(y,b)
        require(a!=b,'Self-matchup after correction')
        score_a,score_b=points(r['F']),points(r['H'])
        winner=None if r['I']=='Tie' else a if r['I']==r['E'] else b if r['I']==r['G'] else 'INVALID'
        awarded=r.get('P')=='1'
        require(winner!='INVALID','Unrecognized declared winner')
        require((score_a==score_b) if winner is None else ((score_a==score_b) if awarded else (score_a>score_b if winner==a else score_b>score_a)),'Declared result conflicts with scores')
        key=(y,w,*sorted((a,b)));require(key not in seen,'Duplicate matchup');seen.add(key)
        phase={'Regular season':'Regular season','Championship playoffs':'Championship playoffs','Sacko tournament':'Loser’s bracket','Loser’s bracket':'Loser’s bracket'}.get(r['C'])
        require(phase is not None,'Unknown matchup phase')
        games.append(dict(season=y,week=w,phase=phase,managerA=a,managerB=b,scoreA=score_a,scoreB=score_b,winner=winner,awardedWinner=awarded,championshipFinal=r['M']=='1',sackoFinal=r['N']=='1',source=r['O']))
    current=[g for g in games if g['season']==year]
    require(len(current)==latest*size//2 and all(g['phase']=='Regular season' for g in current),'Current matchup coverage mismatch')
    # Compare current game records with an independent workbook live-game table.
    live=[r for r in book.data('Live 2026 Games') if r.get('K')=='Complete']
    require(len(live)==len(current),'Live-game table count mismatch')
    canonical=lambda a,b,pa,pb:tuple(sorted(((a,pa),(b,pb))))
    live_keys={(integer(r['B']),canonical(name_ids[r['F']],name_ids[r['G']],points(r['H']),points(r['I']))) for r in live}
    require(live_keys=={(g['week'],canonical(g['managerA'],g['managerB'],g['scoreA'],g['scoreB'])) for g in current},'Live and historical game tables disagree')
    members={t['managerId'] for s in seasons for t in s['teams']}
    managers=sorted([dict(id=id,name=directory[id]) for id in members],key=lambda m:m['name'])
    require(all(g[k] in members for g in games for k in ['managerA','managerB']),'Game manager absent from history')
    metadata=dict(sourceWorkbook=source.name,sourceSha256=digest(source),sourceUpdatedAt=stamp)
    history=dict(schemaVersion=1,**metadata,seasons=seasons,identityCorrections=corrections)
    h2h=dict(schemaVersion=1,**metadata,currentSeason=year,currentManagerIds=sorted(rosters),managers=managers,games=games,identityCorrections=corrections,coverage=f'2010–2012: recovered postseason only; regular-season H2H begins in 2013. {year} through Week {latest}.')
    standings=[]
    for t in groups[year]:
        standings.append(dict(rank=t['regularRank'],rosterId=rosters[t['managerId']],**{k:t[k] for k in ['managerId','manager','team','wins','losses','ties','pointsFor','pointsAgainst']}))
    standings.sort(key=lambda t:t['rank'])
    standings_data=dict(season=year,throughWeek=latest,**metadata,ranking='Saved workbook regular-season ranks; season in progress.',standings=standings)
    # Preserve reviewed archive prose/art only when the underlying scores/results are unchanged.
    editorial_path=(base/config['editorialArchive']).resolve()
    prior=json.loads(editorial_path.read_text())
    archive={(r['season'],r['week']):r for r in prior['recaps']}
    totals={id:dict(wins=0,losses=0,ties=0,pointsFor=0,pointsAgainst=0) for id in rosters}
    recaps=[];art_files={};warnings=[]
    signature=lambda gs:sorted((g['week'],canonical(g['managerA'],g['managerB'],g['scoreA'],g['scoreB']),g['winner']) for g in gs)
    for week in range(1,latest+1):
        week_games=[g for g in current if g['week']==week]
        require(len(week_games)==size//2 and len({g[k] for g in week_games for k in ['managerA','managerB']})==size,'Incomplete/duplicate weekly pairings')
        scores=[]
        for g in week_games:
            for a,b,pf,pa in [(g['managerA'],g['managerB'],g['scoreA'],g['scoreB']),(g['managerB'],g['managerA'],g['scoreB'],g['scoreA'])]:
                t=totals[a];t['wins']+=g['winner']==a;t['losses']+=g['winner']==b;t['ties']+=g['winner'] is None
                t['pointsFor']=round(t['pointsFor']+pf,2);t['pointsAgainst']=round(t['pointsAgainst']+pa,2)
                scores.append(dict(managerId=a,manager=directory[a],points=pf))
        high=max(scores,key=lambda t:t['points']);low=min(scores,key=lambda t:t['points'])
        margin=lambda g:abs(g['scoreA']-g['scoreB'])
        close=min(week_games,key=margin);big=max(week_games,key=margin)
        rows=[dict(managerId=id,manager=directory[id],team=next(t['team'] for t in groups[year] if t['managerId']==id),**t) for id,t in totals.items()]
        rows.sort(key=lambda t:(-(t['wins']+.5*t['ties']),-t['pointsFor'],-t['pointsAgainst']))
        for rank,t in enumerate(rows,1):t['rank']=rank
        r=dict(season=year,week=week,headline=f"Week {week}: {high['manager']} leads the scoring",story=f"{high['manager']} posted the week's high score of {high['points']:.2f}. The closest matchup finished with a {margin(close):.2f}-point margin; the biggest margin was {margin(big):.2f}.",highScore=high,lowScore=low,closest=close,biggestWin=big,leagueTotal=round(sum(t['points'] for t in scores),2),median=round(statistics.median(t['points'] for t in scores),2),games=week_games,standings=rows,artwork=None,artworkAlt=None)
        old=archive.get((year,week))
        if old and signature(old['games'])==signature(week_games) and old.get('standings')==rows:
            for k in ['headline','story']:r[k]=old[k]
            if old.get('artwork'):
                filename=f'recap-week-{week:02d}-{year}.png'
                require(old['artwork']==filename,'Artwork filename convention mismatch')
                art=editorial_path.parent/filename
                if art.is_file():
                    art_files[filename]=art;r.update({k:old[k] for k in ['artwork','artworkAlt']})
                    if old.get('artworkNotes'):r['artworkNotes']=old['artworkNotes']
                else:warnings.append(f'Week {week} artwork unavailable; exported text only.')
        elif old:warnings.append(f'Week {week} scores or accumulated standings changed; prior prose/art withheld and factual draft regenerated.')
        recaps.append(r)
    for t in groups[year]:
        require(all(t[k]==totals[t['managerId']][k] for k in ['wins','losses','ties','pointsFor','pointsAgainst']),'Game-derived standings disagree with saved season totals')
    # Keep past-year editorial archive entries intact; none are invented from season totals.
    recaps.extend(r for r in prior['recaps'] if r['season']<year)
    require(not any(r['season']>year for r in prior['recaps']),'Archive contains future year; review configuration')
    recap_data=dict(schemaVersion=1,season=year,throughWeek=latest,**metadata,editorialStatus='Published weekly recap archive; saved workbook results.',managers=managers,recaps=recaps)
    book.z.close()
    report=dict(season=year,throughWeek=latest,sourceUpdatedAt=stamp,managers=len(managers),teamSeasons=sum(len(s['teams']) for s in seasons),matchups=len(games),currentGames=len(current),recaps=len(recaps),warnings=warnings,checks=['Workbook identities and season totals','Permanent identity corrections','Unique games and declared winners','Live-game table reconciliation','Weekly complete pairings','Game-derived totals match standings/history','Single source hash and timestamp across all datasets'])
    return {f'standings-{year}.json':standings_data,'history.json':history,'h2h.json':h2h,'recaps.json':recap_data},art_files,report

def run(config_path,source_override=None):
    base=config_path.resolve().parent;config=json.loads(config_path.read_text())
    source=Path(source_override or config['workbook']).expanduser().resolve()
    require(source.is_file(),'Master workbook not found: '+str(source))
    require(not (source.parent/('~$'+source.name)).exists(),'Save and close the master workbook in Excel before exporting a preview.')
    before=digest(source)
    output=(base/config.get('outputDirectory','previews')).resolve();output.mkdir(parents=True,exist_ok=True)
    run_dir=output/(dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6])
    run_dir.mkdir()
    try:
        files,art,report=export(config,base,source)
        require(digest(source)==before,'Source changed during export; preview rejected')
        public=run_dir/'website-files';public.mkdir()
        for filename,data in files.items():write_json(public/filename,data)
        for filename,path in art.items():shutil.copy2(path,public/filename)
        require(digest(source)==before,'Source changed during export; preview rejected')
        report.update(status='PASS',sourceUnchanged=True,sourcePath=str(source),sourceSha256=before,mode='saved-workbook preview; no network, workbook save, Git commit or deployment')
        report['files']={p.name:digest(p) for p in sorted(public.iterdir())}
        write_json(run_dir/'validation.json',report)
        write_json(run_dir/'manifest.json',dict(status='PASS',season=report['season'],throughWeek=report['throughWeek'],files=report['files']))
        # The marker changes only after the complete bundle passes; earlier runs are retained.
        fd,tmp=tempfile.mkstemp(dir=output,prefix='.latest-',suffix='.json');os.close(fd)
        try:
            write_json(Path(tmp),dict(previewDirectory=str(run_dir),status='PASS',throughWeek=report['throughWeek']))
            os.replace(tmp,output/'latest-success.json')
        finally:
            if Path(tmp).exists():Path(tmp).unlink()
        print(f"PASS — {report['season']} through Week {report['throughWeek']}; {report['currentGames']} current games.\nPreview: {run_dir}\nWorkbook unchanged. Nothing published.")
        return run_dir
    except Exception as exc:
        write_json(run_dir/'validation.json',dict(status='FAIL',error=str(exc),sourceUnchanged=digest(source)==before))
        raise

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=Path(__file__).with_name('season-config.json'))
    parser.add_argument('--workbook',help='Optional source override; always read-only')
    args=parser.parse_args()
    try:run(args.config,args.workbook)
    except Exception as exc:print('PREVIEW FAILED — previous successful preview retained.\n'+str(exc),file=sys.stderr);return 1
    return 0
if __name__=='__main__':sys.exit(main())
