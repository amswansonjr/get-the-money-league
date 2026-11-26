#!/usr/bin/env python3
"""League Headquarters 7.1: atomic regular-season refresh; Python standard library only."""
import argparse,collections,concurrent.futures,copy,datetime,io,json,math,os,posixpath,re,shutil,sys,tempfile,urllib.request,zipfile
import xml.etree.ElementTree as E
from pathlib import Path
from excel_cache import Engine,TOKEN,colname,colnum,address
M='http://schemas.openxmlformats.org/spreadsheetml/2006/main';R='http://schemas.openxmlformats.org/officeDocument/2006/relationships';q=lambda s:'{'+M+'}'+s
E.register_namespace('',M);E.register_namespace('r',R)
SEASON=2026;LEAGUE='1366250386662379520'
def get(url):
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'LeagueHeadquarters/6.9'}),timeout=30) as r:return json.load(r)
def completed_week(state,scoreboard):
 if int(state.get('season',0))!=SEASON or state.get('season_type')!='regular':raise ValueError('NFL state is outside the supported 2026 regular season. No workbook changed.')
 current=int(state['week']);last=current-1
 if int(scoreboard.get('week',{}).get('number',0))!=current:raise ValueError('NFL scoreboard week does not match Sleeper state.')
 events=scoreboard.get('events',[])
 if not events:raise ValueError('NFL game-status response is empty.')
 if current>14:
  # Tuesday after Week 14 can already be labeled Week 15 by Sleeper.
  if current==15 and not any(e.get('status',{}).get('type',{}).get('completed') is True for e in events):return 14
  raise ValueError('Postseason requires the separately validated bracket workflow. No workbook changed.')
 if all(e.get('status',{}).get('type',{}).get('completed') is True for e in events):last=current
 return max(0,min(last,14))
class Book:
 def __init__(self,path):
  with zipfile.ZipFile(path) as z:self.files={n:z.read(n) for n in z.namelist()}
  self.wb=E.fromstring(self.files['xl/workbook.xml']);rels=E.fromstring(self.files['xl/_rels/workbook.xml.rels']);rm={x.get('Id'):x.get('Target') for x in rels}
  self.paths={s.get('name'):('xl/'+rm[s.get('{'+R+'}id')]).replace('xl//','') for s in self.wb.find(q('sheets'))}
  self.paths={n:(p if not p.startswith('xl/xl/') else p[3:]) for n,p in self.paths.items()}
  self.shared=[]
  if 'xl/sharedStrings.xml' in self.files:
   for si in E.fromstring(self.files['xl/sharedStrings.xml']):self.shared.append(''.join(si.itertext()))
  self.roots={n:E.fromstring(self.files[p]) for n,p in self.paths.items()};self.cells={};self.values={};self.formulas={}
  for n,root in self.roots.items():
   self.cells[n]={c.get('r'):c for c in root.findall('.//'+q('sheetData')+'/'+q('row')+'/'+q('c'))}
   shared_formulas={}
   for a,c in self.cells[n].items():
    f=c.find(q('f'))
    if f is not None and f.get('t')=='shared' and f.text:shared_formulas[f.get('si')]=(a,f.text)
   for a,c in self.cells[n].items():
    f=c.find(q('f'));v=c.find(q('v'));t=c.get('t');value=None
    if t=='inlineStr':value=''.join(c.find(q('is')).itertext())
    elif v is not None and v.text is not None:
     if t=='s':value=self.shared[int(v.text)]
     elif t=='b':value=v.text=='1'
     elif t in ['str','e']:value=v.text
     else:value=float(v.text);value=int(value) if value.is_integer() else value
    if f is not None:
     formula=f.text
     if not formula and f.get('t')=='shared':
      base,formula=shared_formulas[f.get('si')];rr,cc=address(a);br,bc=address(base);formula=translate(formula,rr-br,cc-bc)
     if not formula:raise ValueError('Empty formula '+n+'!'+a)
     self.formulas[n,a]=formula
    else:self.values[n,a]=value
 def ensure(self,n,a):
  if a in self.cells[n]:return self.cells[n][a]
  sd=self.roots[n].find(q('sheetData'));rr=address(a)[0];row=next((r for r in sd if int(r.get('r'))==rr),None)
  if row is None:
   row=E.SubElement(sd,q('row'),r=str(rr))
   if n=='Settings Change Review' and rr>=60:row.set('hidden','1')
  c=E.SubElement(row,q('c'),r=a);self.cells[n][a]=c;return c
 def set(self,n,a,value,formula=None):
  c=self.ensure(n,a)
  for child in list(c):c.remove(child)
  c.attrib.pop('t',None)
  if formula:
   self.formulas[n,a]=formula.lstrip('=');self.values.pop((n,a),None);E.SubElement(c,q('f')).text=formula.lstrip('=')
  else:self.formulas.pop((n,a),None);self.values[n,a]=value
  if isinstance(value,str):
   if formula:c.set('t','str');E.SubElement(c,q('v')).text=value
   else:c.set('t','inlineStr');E.SubElement(E.SubElement(c,q('is')),q('t')).text=value
  elif value is not None:
   if isinstance(value,bool):c.set('t','b');value=int(value)
   E.SubElement(c,q('v')).text=str(value)
 def engine(self):return Engine(self.values,self.formulas)
 def cache(self,engine):
  for n,a in list(self.formulas):self.set(n,a,engine.cell(n,a),self.formulas[n,a])
 def save(self,path):
  # A prior Excel calculation chain can reference rows replaced by the record
  # selector. Excel will rebuild it; retain the current saved formula caches.
  self.files.pop('xl/calcChain.xml',None)
  for part in ['xl/_rels/workbook.xml.rels','[Content_Types].xml']:
   raw=self.files[part].decode('utf-8')
   raw=re.sub(r'<(?:\w+:)?(?:Relationship|Override)\b[^>]*(?:calcChain)[^>]*/>','',raw)
   self.files[part]=raw.encode('utf-8')
  for n,root in self.roots.items():
   sd=root.find(q('sheetData'))
   for row in sd:row[:]=sorted(row,key=lambda c:address(c.get('r'))[1])
   sd[:]=sorted(sd,key=lambda r:int(r.get('r')))
   # Replace only sheetData, retaining Excel's original namespace declarations,
   # extensions, pictures, table relationships, views, notes and validations.
   raw=self.files[self.paths[n]].decode('utf-8');prefix=re.search(r'<((?:\w+:)?)worksheet\b',raw).group(1)
   fragment=E.tostring(sd,encoding='unicode')
   raw,count=re.subn(r'<(?:\w+:)?sheetData\b[^>]*>.*?</(?:\w+:)?sheetData>',lambda _:fragment,raw,flags=re.S)
   if count!=1:raise ValueError('Missing sheetData '+n)
   if n=='League Records':
    merges=root.find(q('mergeCells'));fragment=E.tostring(merges,encoding='unicode')
    raw=re.sub(r'<(?:\w+:)?mergeCells\b[^>]*>.*?</(?:\w+:)?mergeCells>',lambda _:fragment,raw,flags=re.S)
   # Excel's dimension is advisory; remove stale bounds after new report rows.
   raw=re.sub(r'<(?:\w+:)?dimension\b[^>]*/>','',raw)
   self.files[self.paths[n]]=raw.encode('utf-8')
  # Existing workbook calculation settings remain untouched. Saved caches are
  # current even when the user's Excel application is in manual calculation.
  with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
   for n,b in self.files.items():z.writestr(n,b)
def translate(formula,delta,col_delta=0):
 def replace(m):
  if m.group(2) or m.group(3):
   text=m.group(0);prefix=''
   if '!' in text:prefix,text=text.rsplit('!',1);prefix+='!'
   return prefix+re.sub(r'(\$?[A-Z]{1,3})(\$?)(\d+)',lambda x:(x[1] if x[1].startswith('$') else colname(colnum(x[1])+col_delta))+x[2]+str(int(x[3])+(0 if x[2] else delta)),text)
  return m.group(0)
 return TOKEN.sub(replace,formula)
def data_rows(b,sheet,column='A',prefix=None):
 rows=[]
 for a in b.cells[sheet]:
  if re.fullmatch(re.escape(column)+r'\d+',a) and address(a)[0]>1:
   value=b.values.get((sheet,a))
   if prefix is not None and not (isinstance(value,str) and value.startswith(prefix)):continue
   if value is not None or (sheet,a) in b.formulas:rows.append(address(a)[0])
 return sorted(set(rows))
def manager_rows(b,sheet='Career Leaderboard'):return data_rows(b,sheet,prefix='MGR-')
def sort_career(b):
 n='Career Leaderboard';e=b.engine();sd=b.roots[n].find(q('sheetData'));rs=[r for r in sd if int(r.get('r')) in manager_rows(b)];rs.sort(key=lambda r:(-float(e.cell(n,'F'+r.get('r')) or 0),str(e.cell(n,'B'+r.get('r')))))
 oldforms=dict(b.formulas);oldvals=dict(b.values)
 for new,row in enumerate(rs,2):
  old=int(row.get('r'));row.set('r',str(new))
  for c in row:
   a=c.get('r');newa=re.sub(r'\d+$',str(new),a);c.set('r',newa)
   if (n,a) in oldforms:b.formulas[n,newa]=translate(oldforms[n,a],new-old);b.values.pop((n,newa),None);c.find(q('f')).text=b.formulas[n,newa]
   else:b.values[n,newa]=oldvals.get((n,a));b.formulas.pop((n,newa),None)
 b.cells[n]={c.get('r'):c for row in sd for c in row}
def record_rows(b,e):
 games=[]
 for r in data_rows(b,'Matchups'):
  row=[e.cell('Matchups',colname(c)+str(r)) for c in range(1,17)]
  if row[0]:games.append(row)
 rows=[]
 def section(s):rows.append(('section',s,None))
 def record(label,name,value,year=None,week=None,opp=None,note='',fmt='num'):rows.append(('record',[label,name,value,year,week,opp,note],fmt))
 def result(g):return f"{g[8]} beat {g[6] if g[8]==g[4] else g[4]} {g[5] if g[8]==g[4] else g[7]:g}–{g[7] if g[8]==g[4] else g[5]:g}."
 section('REGULAR SEASON RECORDS — WEEKLY COVERAGE 2013 ONWARD');reg=[g for g in games if g[2]=='Regular season'];ps=[(g,name,pts,opp,other) for g in reg for name,pts,opp,other in [(g[4],g[5],g[6],g[7]),(g[6],g[7],g[4],g[5])]]
 for label,key,mode,subset in [('Highest regular-season score',2,max,ps),('Lowest regular-season score',2,min,ps),('Largest regular-season margin',None,max,[p for p in ps if p[2]>p[4]]),('Closest non-tied game',None,min,[p for p in ps if p[2]>p[4]]),('Highest-scoring loss',2,max,[p for p in ps if p[2]<p[4]])]:
  val=lambda p:p[key] if key is not None else p[2]-p[4];extreme=mode(val(p) for p in subset)
  for p in subset:
   if abs(val(p)-extreme)<1e-7:record(label,p[1],val(p),p[0][0],p[0][1],p[3],result(p[0])+' Historical scoring formats differ.')
 career=[]
 for r in manager_rows(b):
  cs=lambda c:e.cell('Career Leaderboard',c+str(r));name=cs('B');completed=[]
  for sr in data_rows(b,'Season History Data'):
   if e.cell('Season History Data','D'+str(sr))==name and e.cell('Season History Data','L'+str(sr))=='Complete':completed.append(sr)
  wins=sum(e.cell('Season History Data','F'+str(sr)) or 0 for sr in completed);loss=sum(e.cell('Season History Data','G'+str(sr)) or 0 for sr in completed);ties=sum(e.cell('Season History Data','O'+str(sr)) or 0 for sr in completed)
  career.append({'name':name,'n':cs('C'),'wins':cs('D'),'pf':cs('G'),'titles':cs('J'),'outright':cs('N'),'avgwins':cs('X'),'avgpf':cs('Y'),'sacko':cs('K'),'loser':cs('R'),'champ':cs('T'),'winpct':(wins+ties/2)/(wins+loss+ties) if completed else None,'avgloss':loss/len(completed) if completed else None})
 def best(label,key,mode,eligible,fmt='num',extra=''):
  val=lambda x:key(x) if callable(key) else x[key];v=mode(val(x) for x in eligible)
  for x in eligible:
   if abs(val(x)-v)<1e-7:record(label,x['name'],v,note=(f"{x['n']} completed seasons. "+extra+(' Yahoo 2010–2012 weekly H2H is partial.' if key in ['champ','loser'] else '')),fmt=fmt)
 section('CAREER RECORDS')
 for label,key in [('Most career regular-season wins','wins'),('Most career regular-season points','pf'),('Most title credits (including shared)','titles'),('Most outright championships','outright')]:best(label,key,max,career,'num' if key=='pf' else 'int','Includes completed 2026 games.' if key in ['wins','pf'] else 'Shared title credits are separate from outright titles.')
 eligible=[x for x in career if x['n']];best('Most wins per completed season','avgwins',max,eligible,extra='Incomplete 2026 excluded.')
 for flag,sacko in [(12,False),(13,True)]:
  section('SACKO FINAL RECORDS' if sacko else 'CHAMPIONSHIP FINAL RECORDS');subset=[g for g in games if g[flag]]
  for label,kind,mode,side in [('Highest points in a final win','score',max,True),('Lowest points in a final win','score',min,True),('Highest points in a final loss','score',max,False),('Lowest points in a final loss','score',min,False),('Largest final win margin','margin',max,True),('Smallest final win margin','margin',min,True)]:
   def value(g):return abs(g[5]-g[7]) if kind=='margin' else g[5] if (g[8]==g[4])==side else g[7]
   extreme=mode(value(g) for g in subset)
   for g in subset:
    if abs(value(g)-extreme)>1e-7:continue
    loser=g[6] if g[8]==g[4] else g[4];note=result(g)+(' Winning margin in points.' if kind=='margin' else ' Points scored by '+('winner.' if side else 'Sacko (loser).' if sacko else 'runner-up (loser).'))
    if g[5]==g[7]:note+=' Declared winner retained despite tied score.'
    if g[0]==2022 and not sacko:note+=' Shared championship; recorded matchup result retained.'
    record(label,g[8] if side else loser,value(g),g[0],g[1],loser if side else g[8],note)
 section('CAREER WALL OF SHAME')
 for label,key,mode,fmt in [('Lowest completed-season win %','winpct',min,'pct'),('Lowest points per completed season','avgpf',min,'num'),('Most Sacko losses','sacko',max,'int'),('Highest Sacko loss rate',lambda x:x['sacko']/x['n'],max,'pct'),('Most Loser’s Bracket seasons','loser',max,'int'),('Highest Loser’s Bracket rate',lambda x:x['loser']/x['n'],max,'pct'),('Most losses per completed season','avgloss',max,'num'),('Fewest championship appearances','champ',min,'int')]:best(label,key,mode,eligible,fmt,'Incomplete 2026 excluded; scoring eras differ for points averages.')
 return rows
def rebuild_records(b,rows):
 n='League Records';root=b.roots[n];sd=root.find(q('sheetData'));oldrows={int(r.get('r')):r for r in sd};header=copy.deepcopy(oldrows[1]);body=copy.deepcopy(oldrows[3]);section=copy.deepcopy(oldrows[2]);styles={}
 for fmt,match in [('pct','Lowest completed-season win %'),('int','Most Sacko losses')]:
  for r in oldrows.values():
   a='A'+r.get('r')
   if b.values.get((n,a))==match:styles[fmt]=b.cells[n]['C'+r.get('r')].get('s','0')
 sd[:]=[header];merges=root.find(q('mergeCells'));merges[:]=[]
 for k in list(b.values):
  if k[0]==n and address(k[1])[0]>1:b.values.pop(k)
 for k in list(b.formulas):
  if k[0]==n:b.formulas.pop(k)
 b.cells[n]={c.get('r'):c for c in header}
 for rr,(kind,vs,fmt) in enumerate(rows,2):
  row=copy.deepcopy(section if kind=='section' else body);row.set('r',str(rr));sd.append(row)
  for c in row:c.set('r',re.sub(r'\d+$',str(rr),c.get('r')));b.cells[n][c.get('r')]=c
  for i,v in enumerate([vs]+[None]*6 if kind=='section' else vs,1):b.set(n,colname(i)+str(rr),v)
  if kind=='section':E.SubElement(merges,q('mergeCell'),ref=f'A{rr}:G{rr}')
  elif fmt in styles:b.cells[n]['C'+str(rr)].set('s',styles[fmt])
 merges.set('count',str(len(merges)))
def update(b,data,last,stamp):
 league=data['league'];assert str(league['season'])==str(SEASON) and league['league_id']==LEAGUE
 if league['settings'].get('playoff_week_start')!=15:raise ValueError('Regular-season rules changed; review required.')
 roster_map={str(b.values['Season History Data','B'+str(r)]):r for r in data_rows(b,'Season History Data') if b.values.get(('Season History Data','A'+str(r)))==SEASON}
 if set(roster_map)!={str(r['roster_id']) for r in data['rosters']}:raise ValueError('Roster IDs no longer match the workbook.')
 owners={str(b.values.get(('Manager Directory','A'+str(r)))):str(b.values.get(('Manager Directory','C'+str(r))) or '') for r in manager_rows(b,'Manager Directory')}
 for roster in data['rosters']:
  sr=roster_map[str(roster['roster_id'])];mid=b.values['Season History Data','C'+str(sr)];expected=owners.get(mid)
  if expected and str(roster.get('owner_id'))!=expected:raise ValueError('Roster ownership changed for '+mid+'. Review manager mapping before refreshing.')
 teams=[]
 for week in range(1,19):
  items=data['week_'+str(week)]
  if len(items)!=12 or len({r['roster_id'] for r in items})!=12:raise ValueError('Expected 12 unique roster rows in Week '+str(week))
  groups=collections.defaultdict(list)
  for r in items:groups[r.get('matchup_id')].append(r)
  if week<=14 and (None in groups or len(groups)!=6 or any(len(v)!=2 for v in groups.values())):raise ValueError('Invalid regular-season matchup pairing.')
  for item in sorted(items,key=lambda r:r['roster_id']):
   points=item.get('custom_points') if item.get('custom_points') is not None else item.get('points')
   if not isinstance(points,(int,float)) or not math.isfinite(points):raise ValueError('Invalid team score.')
   teams.append([SEASON,week,item['roster_id'],item.get('matchup_id'),points,item.get('custom_points'),'Complete' if week<=last else 'Incomplete'])
 for rr,row in enumerate(teams,2):
  for c,v in enumerate(row,1):
   b.set('PQ 2026 Matchups',colname(c)+str(rr),v)
   b.set('2026 Live Source',colname(c)+str(rr),v)
 b.set('2026 Live Source','I2',last)
 b.set('HQ Dashboard','B7',None,'"Through "&B38')
 # Refresh historical 2026 score rows; retain every older source row.
 n='Weekly Scores';sd=b.roots[n].find(q('sheetData'));keepers=[r for r in sd if int(r.get('r'))==1 or b.values.get((n,'A'+r.get('r')))!=SEASON];sd[:]=keepers
 keepkeys={(n,c.get('r')) for row in keepers for c in row}
 for k in list(b.values):
  if k[0]==n and k not in keepkeys:b.values.pop(k)
 b.cells[n]={c.get('r'):c for row in keepers for c in row};nextrow=max(int(r.get('r')) for r in keepers)+1
 for year,week,rid,mid,points,custom,status in teams:
  if status!='Complete':continue
  source_row=roster_map[str(rid)];manager=b.values['Season History Data','D'+str(source_row)];managerid=b.values['Season History Data','C'+str(source_row)]
  for c,v in enumerate([year,week,None,managerid,manager,mid,points,None,None,'Played'],1):b.set(n,colname(c)+str(nextrow),v)
  nextrow+=1
 e=b.engine();ordered=sorted(roster_map.values(),key=lambda r:(e.cell('Season History Data','M'+str(r)),-e.cell('Season History Data','H'+str(r))))
 for rr,sr in enumerate(ordered,4):
  for c,source in [('A','D'),('B','E'),('C','M'),('D','N'),('F','F'),('G','G'),('H','H'),('I','I'),('K','O')]:b.set('Season History',c+str(rr),None,f"'Season History Data'!{source}{sr}")
 sort_career(b);e=b.engine();rows=record_rows(b,e);rebuild_records(b,rows)
 # Keep the terminal historical audit and legacy summary current too.
 for rr in data_rows(b,'Matchups'):
  game=[e.cell('Matchups',colname(c)+str(rr)) for c in range(1,17)]
  for c,v in enumerate([game[0],game[1],game[2],game[4],game[6],game[8],game[5],game[7]],1):b.set('H2H Matchup Audit',colname(c)+str(rr),v)
 for rr in data_rows(b,'H2H Detail'):
  detail=[e.cell('H2H Detail',colname(c)+str(rr)) for c in range(1,16)]
  vals=[detail[0],detail[1],sum(detail[2:5]),detail[2],detail[3],sum(detail[5:11]),detail[5]+detail[8],detail[6]+detail[9],detail[4],detail[7]+detail[10]]
  for c,v in enumerate(vals,1):b.set('Head to Head',colname(c)+str(rr),v)
 games=last*6;b.set('HQ Dashboard','B19','2026 results through Week '+str(last));b.set('HQ Dashboard','B36','REFRESH COMPLETE');b.set('HQ Dashboard','B37',stamp);b.set('HQ Dashboard','B38','2026 Week '+str(last));b.set('HQ Dashboard','B39','Sleeper scores + NFL completion check')
 decisive=0
 for week in range(1,last+1):
  pairs=collections.defaultdict(list)
  for record in data['week_'+str(week)]:pairs[record['matchup_id']].append(record.get('custom_points') if record.get('custom_points') is not None else record['points'])
  decisive+=sum(a!=z for a,z in pairs.values())
 for a,v in [('N2','LIVE REFRESH VALIDATION'),('O3',games),('O4',last*12),('O5',decisive),('O6',decisive),('O7','Launcher; no Power Query required')]:b.set('Refresh Instructions',a,v)
 # Replace the original dashboard snapshot counts with live counts.
 b.set('HQ Dashboard','B10',len([1 for r in data_rows(b,'Matchups') if e.cell('Matchups','A'+str(r))]));b.set('HQ Dashboard','B9',2*b.values['HQ Dashboard','B10'])
 for n in ['README','History Notes']:
  for (sn,a),v in list(b.values.items()):
   if sn==n and isinstance(v,str) and ('2026' in v and ('Week 7' in v or 'week 7' in v)):b.set(n,a,v.replace('Week 7','Week '+str(last)).replace('week 7','week '+str(last)))
 e=b.engine()
 if 'Settings Change Review' in b.roots:
  from settings_review import update_review
  update_review(b,e);e=b.engine()
 b.cache(e)
 assert e.cell('HQ Dashboard','B20')==games
 assert sum(e.cell('Season History Data','F'+str(r)) for r in roster_map.values())==sum(e.cell('Season History Data','G'+str(r)) for r in roster_map.values())
 assert sum(e.cell('Season History Data','P'+str(r)) for r in roster_map.values())==last*12
 return {'completed_week':last,'completed_2026_games':games,'formulas_recalculated':len(e.cache),'record_rows':len(rows)}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--workbook',type=Path);ap.add_argument('--data-dir',type=Path);ap.add_argument('--output',type=Path);args=ap.parse_args()
 folder=Path(__file__).resolve().parent;target=args.workbook or folder/'GET_THE_MONEY_LEAGUE_HEADQUARTERS_V7_MASTER.xlsx';output=args.output or target
 if not target.exists():raise ValueError('Workbook not found: '+str(target))
 if output==target and (target.parent/('~$'+target.name)).exists():raise ValueError('Save and close the workbook in Excel before refreshing.')
 stamp=datetime.datetime.now().astimezone();run=folder/'Refresh Data'/stamp.strftime('%Y%m%d-%H%M%S');run.mkdir(parents=True,exist_ok=True)
 if args.data_dir:
  data={p.stem:json.loads(p.read_text()) for p in args.data_dir.glob('*.json')}
 else:
  base='https://api.sleeper.app/v1/league/'+LEAGUE;urls={'league':base,'rosters':base+'/rosters','state':'https://api.sleeper.app/v1/state/nfl'};urls.update({'week_'+str(w):base+'/matchups/'+str(w) for w in range(1,19)})
  with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:data=dict(zip(urls,pool.map(get,urls.values())))
  data['scoreboard']=get('https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=2026&seasontype=2&week='+str(data['state']['week']))
 for n,v in data.items():(run/(n+'.json')).write_text(json.dumps(v,indent=2))
 last=completed_week(data['state'],data['scoreboard']);print('Completed through Week',last,flush=True)
 b=Book(target);prior=b.engine().cell('HQ Dashboard','B20') or 0
 if last*6<prior:raise ValueError('Source would roll back already completed weeks. No workbook changed.')
 print('Updating reports and recalculating saved values…',flush=True);report=update(b,data,last,stamp.strftime('%Y-%m-%d %H:%M %Z'))
 fd,tmp=tempfile.mkstemp(suffix='.xlsx',dir=output.parent);os.close(fd)
 try:
  b.save(tmp)
  with zipfile.ZipFile(tmp) as z:
   if z.testzip():raise ValueError('Workbook package validation failed.')
  if output.exists():
   backups=folder/'Backups';backups.mkdir(exist_ok=True);shutil.copy2(output,backups/(output.stem+'_'+stamp.strftime('%Y%m%d-%H%M%S')+'.xlsx'))
  os.replace(tmp,output)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
 (run/'refresh_log.json').write_text(json.dumps(report,indent=2));print('REFRESH COMPLETE:',output,report,flush=True)
if __name__=='__main__':
 try:main()
 except Exception as exc:print('REFRESH FAILED — previous workbook kept.\n'+str(exc),file=sys.stderr);sys.exit(1)
