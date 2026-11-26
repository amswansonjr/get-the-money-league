#!/usr/bin/env python3
"""Prepare an immutable, local weekly review package. This module cannot publish."""
import argparse,collections,concurrent.futures,copy,datetime as dt,hashlib,html,importlib.util,io,json,math,os,re,shutil,subprocess,sys,tarfile,time,urllib.request,uuid,zipfile
from pathlib import Path
from zoneinfo import ZoneInfo
from calculated_awards import extra_awards
from upcoming_matchups import enrich as enrich_matchups
ZONE=ZoneInfo('America/Chicago')
PUBLIC_EXTENSIONS={'.html','.css','.js','.json','.png','.svg'}
def require(ok,message):
    if not ok:raise ValueError(message)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def read(path):return json.loads(Path(path).read_text())
def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def git(repo,*args):
    result=subprocess.run(['git','-C',str(repo),*args],capture_output=True,env=dict(os.environ,GIT_TERMINAL_PROMPT='0'))
    require(result.returncode==0,'Repository read failed: '+result.stderr.decode().strip());return result.stdout
def collect(root,run,config):
    raw=run/'collected';raw.mkdir();cache=root/'Source Cache';cache.mkdir(exist_ok=True)
    def get(url):
        request=urllib.request.Request(url,headers={'User-Agent':'LeagueHeadquartersPrepare/1.0'})
        with urllib.request.urlopen(request,timeout=45) as response:return json.load(response)
    state=get('https://api.sleeper.app/v1/state/nfl')
    require(str(state.get('season'))==str(config['season']) and state.get('season_type')=='regular','Season setup does not match Sleeper. Review annual configuration before preparing.')
    current=int(state['week']);require(1<=current<=15,'Postseason preparation needs the validated bracket workflow.')
    base='https://api.sleeper.app/v1/league/'+config['leagueId']
    urls={'league':base,'rosters':base+'/rosters','scoreboard':f'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={config["season"]}&seasontype=2&week={current}'}
    urls.update({f'week_{w}':base+f'/matchups/{w}' for w in range(1,19)})
    urls.update({f'transactions_{w:02d}':base+f'/transactions/{w}' for w in range(19)})
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:data=dict(zip(urls,pool.map(get,urls.values())))
    require(data['league']['league_id']==config['leagueId'] and str(data['league']['season'])==str(config['season']),'League identity mismatch.')
    require(len(data['rosters'])==config['teamCount'],'Unexpected roster count.')
    player_cache=cache/'players-nfl.json';cache_meta=cache/'players-nfl-metadata.json'
    if player_cache.exists() and cache_meta.exists() and time.time()-read(cache_meta)['fetchedEpoch']<86400:
        data['players']=read(player_cache)
    else:
        data['players']=get('https://api.sleeper.app/v1/players/nfl');write(player_cache,data['players']);write(cache_meta,{'fetchedEpoch':time.time()})
    # Save each historical projection response with this immutable review package.
    # Projection failure must not block the score/lineup awards or workbook update.
    projection_errors=[]
    for week in range(1,min(current,config.get('regularSeasonWeeks',14))+1):
        name=f'projections_{week}'
        url=f'https://api.sleeper.app/projections/nfl/{config["season"]}/{week}?season_type=regular'
        urls[name]=url
        try:data[name]=get(url)
        except Exception as error:projection_errors.append({'week':week,'error':str(error)})
    data['projection_collection_errors']=projection_errors
    data['state']=state
    for name,value in data.items():write(raw/(name+'.json'),value)
    now=dt.datetime.now(dt.timezone.utc)
    metadata={'startedAtUtc':now.isoformat(),'collectedAtCentral':now.astimezone(ZONE).strftime('%Y-%m-%d %H:%M %Z'),'sourceUrls':urls,'mode':'PREPARE_ONLY'}
    write(run/'collection.json',metadata);return raw,metadata,data
def pairings(rows,expected=12):
    require(len(rows)==expected and len({r['roster_id'] for r in rows})==expected,'Expected one matchup row per roster.')
    groups=collections.defaultdict(list)
    for row in rows:
        points=row['custom_points'] if row.get('custom_points') is not None else row.get('points')
        require(type(points) in (int,float) and math.isfinite(points),'Missing or invalid team score.')
        groups[row.get('matchup_id')].append(row)
    require(None not in groups and len(groups)==expected//2 and all(len(g)==2 for g in groups.values()),'Incomplete or duplicate regular-season pairings.')
    return groups
def apply_headers(path,edits):
    """Apply previously reviewed artifact-authored labels without changing numeric/formula XML."""
    with zipfile.ZipFile(path) as z:files={name:z.read(name) for name in z.namelist()}
    import xml.etree.ElementTree as E
    ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    rels={r.get('Id'):r.get('Target') for r in E.fromstring(files['xl/_rels/workbook.xml.rels'])}
    paths={s.get('name'):('xl/'+rels[s.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')]).replace('xl//','') for s in E.fromstring(files['xl/workbook.xml']).find('s:sheets',ns)}
    shared=[]
    if 'xl/sharedStrings.xml' in files:shared=[''.join(s.itertext()) for s in E.fromstring(files['xl/sharedStrings.xml'])]
    count=0;mapping={}
    for edit in edits:
        if edit['sheet'] not in paths:continue
        part=paths[edit['sheet']];text=files[part].decode();address=edit['cell']
        pattern=r'(<(?:\w+:)?c\b[^>]*\br="'+re.escape(address)+r'"[^>]*>)(.*?)(</(?:\w+:)?c>)'
        match=re.search(pattern,text,re.S);require(match is not None,'Header cell missing: '+edit['sheet']+'!'+address)
        node=E.fromstring('<root xmlns="'+ns['s']+'">'+match.group()+'</root>')[0]
        require(node.find('s:f',ns) is None,'Header edit would change a formula.')
        value=node.find('s:v',ns)
        current=''.join(node.find('s:is',ns).itertext()) if node.get('t')=='inlineStr' else shared[int(value.text)] if node.get('t')=='s' else value.text if value is not None else ''
        require(current in (edit['before'],edit['after']),'Header differs from approved wording: '+edit['sheet']+'!'+address)
        if current==edit['after']:continue
        opening=re.sub(r'\s+t="[^"]*"','',match[1])[:-1]+' t="inlineStr">'
        replacement=opening+'<is><t xml:space="preserve">'+html.escape(edit['after'])+'</t></is>'+match[3]
        files[part]=(text[:match.start()]+replacement+text[match.end():]).encode();count+=1;mapping[edit['before']]=edit['after']
    for part,raw in list(files.items()):
        if part.startswith('xl/tables/') and part.endswith('.xml'):
            files[part]=re.sub(r'(<(?:\w+:)?tableColumn\b[^>]*\bname=")([^"]*)(")',lambda m:m[1]+html.escape(mapping.get(html.unescape(m[2]),html.unescape(m[2])),quote=True)+m[3],raw.decode()).encode()
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for name,value in files.items():z.writestr(name,value)
    return count
def js_data(path):
    text=Path(path).read_text();return json.loads(text[text.index('=')+1:].strip().removesuffix(';'))
def js_write(path,name,value):Path(path).write_text('const '+name+' = '+json.dumps(value,ensure_ascii=False,indent=2)+';\n')
def score_signature(recap):
    return sorted((g['week'],g['managerA'],g['managerB'],g['scoreA'],g['scoreB'],g['winner']) for g in recap['games'])
def transactions(data,directory,season,last,current,stamp,config):
    players=data['players']
    def name(pid):
        p=players.get(pid,{})
        full=p.get('full_name') or ' '.join(filter(None,[p.get('first_name'),p.get('last_name')]))
        require(bool(full),'Unresolved transaction player: '+pid);return full
    start=dt.date.fromisoformat(config['seasonStartTuesday']);require(start.weekday()==1,'Season start must be Tuesday.')
    unique={}
    for week in range(19):
        for tx in data[f'transactions_{week:02d}']:
            tid=tx['transaction_id'];require(tid not in unique or unique[tid]==tx,'Conflicting transaction records.');unique[tid]=tx
    editions={}
    for week in range(1,min(current,config['regularSeasonWeeks'])+1):
        day=start+dt.timedelta(weeks=week-1);end=day+dt.timedelta(days=7);moves=[]
        for tid,tx in sorted(unique.items(),key=lambda item:(item[1].get('status_updated') or item[1]['created'],item[0])):
            if tx['status']!='complete' or tx['type'] not in ('waiver','free_agent','trade'):continue
            completed=dt.datetime.fromtimestamp((tx.get('status_updated') or tx['created'])/1000,ZONE)
            if not day<=completed.date()<end:continue
            parties=sorted(tx.get('roster_ids') or [])
            require(parties and all(p in directory for p in parties),'Unresolved transaction manager.')
            adds=tx.get('adds') or {};drops=tx.get('drops') or {}
            move_type='Trade' if tx['type']=='trade' else 'Waiver' if tx['type']=='waiver' else 'Free-agent pickup' if adds else 'Drop only'
            assets=[]
            if move_type=='Trade':
                for pid,to in adds.items():assets.append(f'{directory[to]["manager"]} received {name(pid)}')
                for pick in tx.get('draft_picks') or []:assets.append(f'{directory[pick["owner_id"]]["manager"]} received {pick["season"]} round {pick["round"]} pick (original roster {pick["roster_id"]})')
                for budget in tx.get('waiver_budget') or []:assets.append(f'{directory[budget["receiver"]]["manager"]} received ${budget["amount"]} FAAB from {directory[budget["sender"]]["manager"]}')
            first=parties[0]
            moves.append({'id':tid,'timestamp':completed.strftime('%Y-%m-%d %H:%M:%S'),'manager':directory[first]['manager'],'type':move_type,'added':'; '.join(name(p) for p,to in adds.items() if to==first),'dropped':'; '.join(name(p) for p,fr in drops.items() if fr==first),'bid':(tx.get('settings') or {}).get('waiver_bid') if move_type=='Waiver' else None,'otherManagers':'; '.join(directory[p]['manager'] for p in parties[1:]),'assets':'; '.join(assets)})
        editions[f'{season}-{week}']={'start':day.isoformat(),'end':(end-dt.timedelta(days=1)).isoformat(),'collectedAt':stamp,'moves':moves}
    return {'schemaVersion':1,'editions':editions}
def awards(data,directory,recaps,reported,old_recaps,warnings):
    old={(r['season'],r['week']):r for r in old_recaps['recaps']};result={}
    for recap in recaps['recaps']:
        if recap['season']!=int(data['league']['season']):continue
        key=f'{recap["season"]}-{recap["week"]}';prior=old.get((recap['season'],recap['week']))
        games=recap['games'];scores=[(g['manager'+side],g['score'+side]) for g in games for side in ('A','B')]
        low=min(p for _,p in scores);high=max(p for _,p in scores)
        generated=[]
        for title,target in [('Highest Scorer 😎',high),('Lowest Scorer 💩',low)]:
            ids=[mid for mid,p in scores if p==target]
            generated.append({'title':title,'points':target,'ids':ids,'description':'Calculated from saved team scores.','group':'team','source':'saved_scores'})
        decided=[g for g in games if g['winner']]
        if decided:
            for title,fn in [('Biggest Blowout 😂',max),('Narrow Victory 😱',min)]:
                margin=fn(abs(g['scoreA']-g['scoreB']) for g in decided)
                for g in decided:
                    if abs(abs(g['scoreA']-g['scoreB'])-margin)>.00001:continue
                    winner=g['winner'];score=g['scoreA'] if winner==g['managerA'] else g['scoreB'];loser=g['managerB'] if winner==g['managerA'] else g['managerA']
                    generated.append({'title':title,'managerId':winner,'points':score,'description':f'Over {next(t["manager"] for t in recap["standings"] if t["managerId"]==loser)} by {margin:.2f} points.','group':'team','source':'saved_scores'})
        generated.extend(extra_awards(data,directory,recap['week'],warnings))
        result[key]=generated
    return result
def prepare(root,fixture=None,no_open=False,saved=False):
    tools=root/'Tools/Website';config=read(tools/'season-config.json');book_config=read(root/'Tools/Workbook/publish_config.json')
    source_paths={k:Path(book_config[k]) for k in ('master','published')}
    require(all(p.is_file() for p in source_paths.values()),'Both authoritative workbook paths must exist.')
    source_hashes={k:sha(p) for k,p in source_paths.items()}
    updates=root/'Weekly Updates';updates.mkdir(exist_ok=True)
    run=updates/(dt.datetime.now(ZONE).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]);run.mkdir()
    status={'schemaVersion':1,'status':'PREPARING','reviewDecision':'NOT_REVIEWED','published':False,'sourceHashes':source_hashes,'season':config['season'],'packageDirectory':str(run)};write(run/'package.json',status)
    try:
        repo=root/'Website Repository';remote=read(root/'website-publishing.json')['remote'];require(git(repo,'remote','get-url','origin').decode().strip()==remote,'Unexpected website repository.')
        if not fixture:git(repo,'fetch','origin','main')
        base=git(repo,'rev-parse','origin/main').decode().strip();status['baseCommit']=base
        template_meta=read(tools/'site-template/baseline.json')
        for name,expected in template_meta['sourceHashes'].items():
            actual=hashlib.sha256(git(repo,'show','origin/main:'+name)).hexdigest();require(actual==expected,'Website template changed upstream: '+name+'. Merge it before preparing another package.')
        if fixture:
            raw=run/'collected';shutil.copytree(fixture,raw);data={p.stem:read(p) for p in raw.glob('*.json')};require('players' in data,'Fixture has no player metadata.');metadata=read(fixture/'collection-metadata.json' if (fixture/'collection-metadata.json').exists() else fixture.parent/'collection.json')
        else:raw,metadata,data=collect(root,run,config)
        write(run/'collection.json',metadata)
        sys.path.insert(0,str(root/'Tools/Workbook'))
        refresh=load_module('weekly_refresh',root/'Tools/Workbook/refresh_league.py');last=refresh.completed_week(data['state'],data['scoreboard']);current=int(data['state']['week'])
        for week in range(1,min(current,14)+1):pairings(data[f'week_{week}'],config['teamCount'])
        print(f'Confirmed completed results through Week {last}; current NFL week {current}.',flush=True)
        books=run/'workbooks';books.mkdir();master=books/'Review - Private Master.xlsx';view=books/'Review - League Viewing Copy.xlsx'
        shutil.copy2(source_paths['master'],master);shutil.copy2(source_paths['published'],view)
        stage_config=run/'workbook-config.json';write(stage_config,{'master':str(master),'published':str(view)})
        if not saved:
            inputs=run/'workbook-inputs';inputs.mkdir()
            for name in ['league','rosters','state','scoreboard',*[f'week_{w}' for w in range(1,19)]]:shutil.copy2(raw/(name+'.json'),inputs/(name+'.json'))
            subprocess.run([sys.executable,str(root/'Tools/Workbook/publish_league.py'),'--config',str(stage_config),'--data-dir',str(inputs)],check=True)
        else:
            # A saved-master preview still rebuilds the viewing copy and never commits originals.
            require(last*6==float(refresh.Book(master).cells['HQ Dashboard']['B20'].find(refresh.q('v')).text),'Saved master does not match the collected completed week. Use Prepare Weekly Update.')
        publisher=load_module('weekly_book_publish',root/'Tools/Workbook/publish_league.py')
        label_edits=read(tools/'header-edits.json');header_counts={p.name:apply_headers(p,label_edits) for p in (master,view)}
        master_check=publisher.validate(master);view_check=publisher.validate(view,True)
        require(master_check['completed_games_2026']==view_check['completed_games_2026']==last*6,'Workbook completed-week counters differ.')
        preview=load_module('weekly_web_export',tools/'website_preview.py');export_config=copy.deepcopy(config);export_config['workbook']=str(master)
        files,art,validation=preview.export(export_config,tools,master)
        require(all(sha(p)==source_hashes[k] for k,p in source_paths.items()),'Original workbook changed during preparation. Package must be rebuilt.')
        site=run/'website';site.mkdir()
        archive=git(repo,'archive','origin/main')
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for member in tar:
                relative=Path(member.name)
                if not member.isfile() or relative.is_absolute() or '..' in relative.parts:continue
                if len(relative.parts)==1 and relative.suffix in PUBLIC_EXTENSIONS or member.name=='scripts/build-recap-fallback.py':
                    dest=site/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(tar.extractfile(member).read())
        old_recaps=read(site/'recaps.json')
        old_editorials=js_data(site/'recap-editorials.js');reported=js_data(site/'recap-sleeper-awards.js')
        curated=tools/'editorial/recap-editorials.js'
        if curated.exists():
            old_editorials.update(js_data(curated))
            curated_recaps=read(tools/'editorial/recaps.json')
            existing={(r['season'],r['week']) for r in old_recaps['recaps']}
            old_recaps['recaps'].extend(r for r in curated_recaps['recaps'] if (r['season'],r['week']) not in existing)
        for path in (tools/'site-template').iterdir():
            if path.name!='baseline.json' and path.is_file():shutil.copy2(path,site/path.name)
        for name,value in files.items():write(site/name,value)
        for name,path in art.items():shutil.copy2(path,site/name)
        recaps=files['recaps.json'];directory={t['rosterId']:t for t in files[f'standings-{config["season"]}.json']['standings']};warnings=list(validation['warnings'])
        old_index={(r['season'],r['week']):r for r in old_recaps['recaps']};new_index={(r['season'],r['week']):r for r in recaps['recaps']}
        corrections=[]
        for key,old in old_index.items():
            new=new_index.get(key)
            if new and score_signature(old)!=score_signature(new):corrections.append({'season':key[0],'week':key[1]})
        for key in list(old_editorials):
            year,week=map(int,key.split('-'));old=old_index.get((year,week));new=new_index.get((year,week))
            if not old or not new or score_signature(old)!=score_signature(new) or old['standings']!=new['standings']:
                del old_editorials[key];warnings.append(f'Week {week}: written editorial withheld pending review of changed source results.')
        js_write(site/'recap-editorials.js','recapEditorials',old_editorials)
        tx=transactions(data,directory,config['season'],last,current,metadata['collectedAtCentral'],config);write(site/'recap-transactions.json',tx)
        computed_awards=awards(data,directory,recaps,reported,old_recaps,warnings);js_write(site/'recap-sleeper-awards.js','sleeperWeeklyAwards',computed_awards)
        nfl_started=any(e['status']['type'].get('state') in ('in','post') for e in data['scoreboard']['events'])
        active={'schemaVersion':1,'season':config['season'],'week':current,'status':'complete' if current==last else 'in_progress' if nfl_started else 'upcoming','completedThroughWeek':last,'collectedAt':metadata['collectedAtCentral'],'liveRefresh':False,'matches':[]}
        if current>last and current<=14:
            for mid,rows in sorted(pairings(data[f'week_{current}']).items()):
                active['matches'].append({'matchupId':mid,'teams':[{'managerId':directory[r['roster_id']]['managerId'],'manager':directory[r['roster_id']]['manager'],'points':r['custom_points'] if r.get('custom_points') is not None else r['points']} for r in rows]})
        enrich_matchups(active,data,directory)
        write(site/'in-progress.json',active)
        status.update(completedThroughWeek=last,currentWeek=current,currentWeekStatus=active['status'],collectedAt=metadata['collectedAtCentral'],statCorrections=corrections,headerEdits=header_counts,workbookValidation={'master':master_check,'viewingCopy':view_check},warnings=warnings)
        warnings.append('Playoff clinch and bye indicators are not assigned until their rule/data source is validated.')
        if not any(r['season']==config['season'] and r['week']==last and r['artwork'] for r in recaps['recaps']):warnings.append('Latest completed week has no illustrated cover attached.')
        builder=site/'scripts/build-recap-fallback.py'
        builder_text=builder.read_text().replace("names[a['managerId']]","names[a['managerId']] if a.get('managerId') else ' / '.join(names[i] for i in a['ids'])")
        # The builder retains numeric sources; parenthetical ranks are display-only.
        builder_text=builder_text.replace("f'{t[\"pointsFor\"]:.2f}'","f'{t[\"pointsFor\"]:,.2f} ({1+sum(o[\"pointsFor\"]>t[\"pointsFor\"] for o in recap[\"standings\"])})'")
        builder_text=builder_text.replace("f'{t[\"pointsAgainst\"]:.2f}'","f'{t[\"pointsAgainst\"]:,.2f} ({1+sum(o[\"pointsAgainst\"]<t[\"pointsAgainst\"] for o in recap[\"standings\"])})'")
        for before,after in [('Weekly awards','Weekly Awards'),('The scoreboard','The Scoreboard'),('Standings watch','Standings Watch'),('Illustrated edition','Illustrated Edition')]:builder_text=builder_text.replace(before,after)
        builder.write_text(builder_text)
        subprocess.run([sys.executable,str(builder)],check=True)
        # Build a plain in-progress page; the same component is also used on Home, Standings, and Recaps.
        for path in site.glob('*.html'):
            text=path.read_text()
            if path.name in ('index.html','standings.html','recaps.html'):
                if path.name=='index.html':position=text.index('<div class="cards">');panel='<div id="current-week-snapshot" data-compact="true"></div>'
                else:position=text.index('</h1>')+len('</h1>');panel='<div id="current-week-snapshot"></div>'
                text=text[:position]+panel+text[position:]
                text=text.replace('</head>','<script src="./in-progress.js" defer></script></head>')
            text=text.replace('>THIS WEEK<','>LATEST COMPLETED WEEK<');path.write_text(text)
        (site/'in-progress.html').write_text('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="./site.css"><script src="./in-progress.js" defer></script><title>Current Week | GET THE $$$$</title></head><body><main><nav class="league-nav"><a href="./">Home</a><a href="./standings.html">Current Standings</a><a href="./recaps.html">Weekly Recaps</a></nav><h1>Current Week</h1><div id="current-week-snapshot"></div></main></body></html>')
        manifest={p.relative_to(site).as_posix():sha(p) for p in site.rglob('*') if p.is_file()}
        require(not any(Path(n).suffix=='.xlsx' for n in manifest),'Workbook included in public candidate.')
        write(run/'manifest.json',{'files':manifest,'mode':'PREPARED_NOT_PUBLISHED','workbooks':{'master':sha(master),'viewingCopy':sha(view)},'collectionFiles':{p.name:sha(p) for p in raw.glob('*.json')}})
        require(all(sha(p)==source_hashes[k] for k,p in source_paths.items()),'Original workbook changed during preparation.')
        status.update(status='READY_FOR_REVIEW',originalWorkbooksUnchanged=True,websiteFileCount=len(manifest),transactionCount=sum(len(e['moves']) for e in tx['editions'].values()))
        write(run/'package.json',status)
        write(root/'latest-weekly-package.json',{'packageDirectory':str(run),'status':'READY_FOR_REVIEW','published':False})
        if os.environ.get("GTM_HEADLESS_PREPARE")=="1":return run
        from review_server import open_package
        url=open_package(run,not no_open)
        print('\nPREPARED — REVIEW REQUIRED. NOTHING PUBLISHED.\nReview: '+url+'\nPackage: '+str(run),flush=True)
        return run
    except Exception as exc:
        status.update(status='FAILED',error=str(exc),published=False);write(run/'package.json',status);raise
def latest(root):
    path=Path(read(root/'latest-weekly-package.json')['packageDirectory']).resolve()
    require(path.parent==(root/'Weekly Updates').resolve(),'Latest package path is outside Weekly Updates.')
    return path
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]);parser.add_argument('--fixture',type=Path);parser.add_argument('--no-open',action='store_true');parser.add_argument('--saved-master',action='store_true');parser.add_argument('--open-latest',action='store_true');parser.add_argument('--hold',action='store_true');parser.add_argument('--status',action='store_true');args=parser.parse_args()
    try:
        if args.hold:
            from review_server import hold_package
            hold_package(latest(args.root),'Confirmed in the local launcher');print('REVIEWED — PUBLICATION HELD. Nothing published.');return
        if args.status:
            package=latest(args.root);p=read(package/'package.json')
            print(f"Package: {package.name}\nStatus: {p['status'].replace('_',' ')}\nOfficial Results: Through Week {p['completedThroughWeek']}\nCurrent Week: {p['currentWeek']} — {p['currentWeekStatus'].replace('_',' ')}\nCollected: {p['collectedAt']}\nPublished: No\nOriginal Workbooks: Unchanged")
            return
        if args.open_latest:
            from review_server import open_package
            print(open_package(latest(args.root),True));return
        prepare(args.root,args.fixture,args.no_open,args.saved_master)
    except Exception as exc:print('PREPARATION STOPPED — '+str(exc),file=sys.stderr);raise SystemExit(1)
if __name__=='__main__':main()
