"""League median review. Derived results rebuild from recorded sources on refresh."""
import collections
NAME='Settings Change Review'
VERSION='Median review v2'

def calculate(b,e,baseline=False):
 from refresh_league import data_rows
 def rows(n,cols):
  return [[e.cell(n,c+str(r)) for c in cols] for r in data_rows(b,n)]
 seasons=collections.defaultdict(dict)
 for y,n,rank,final,status,wb in rows('Season History Data',['A','D','M','N','L','S']):
  if isinstance(y,(int,float)) and y>=2013:seasons[int(y)][n]={'rank':rank,'final':final,'complete':status=='Complete','field':wb==1}
 weeks=collections.defaultdict(dict);scores={};post=collections.defaultdict(list)
 for y,w,phase,a,ap,z,zp,win,champ,sacko in rows('Matchups',['A','B','C','E','F','G','H','I','M','N']):
  if not isinstance(y,(int,float)) or y<2013 or not isinstance(ap,(int,float)) or not isinstance(zp,(int,float)):continue
  y,w=int(y),int(w)
  if phase=='Regular season':
   if win not in [a,z,'Tie']:continue
   for n,p in [(a,ap),(z,zp)]:
    if n in weeks[y,w]:raise ValueError('Duplicate weekly team '+str((y,w,n)))
    weeks[y,w][n]=(round(p,2),int(win==n),int(win not in [n,'Tie']),int(win=='Tie'))
  else:
   post[y].append(dict(week=w,phase=phase,a=a,b=z,ap=ap,bp=zp,winner=win,champ=champ,sacko=sacko))
   for n,p in [(a,ap),(z,zp)]:scores[y,w,n]=round(p,2)
 for y,w,n,p,status in rows('Weekly Scores',['A','B','E','G','J']):
  if isinstance(p,(int,float)) and status=='Played':scores.setdefault((y,w,n),round(p,2))
 standings=[];weekly=[];summaries=[];games=[];career=collections.defaultdict(lambda:dict(seasons=0,up=0,down=0,delta=0,median=0,week=0,w=0,t=0))
 diagnostics=[]
 for y,people in sorted(seasons.items()):
  if len(people)!=12:continue
  ds={n:dict(w=0,l=0,t=0,mw=0,ml=0,mt=0,pf=0) for n in people};ys=sorted((w,ts) for (yy,w),ts in weeks.items() if yy==y)
  for w,ts in ys:
   if len(ts)!=12 or set(ts)!=set(people):raise ValueError('Incomplete weekly coverage '+str((y,w)))
   sc=sorted(v[0] for v in ts.values());median=round((sc[5]+sc[6])/2,4)
   for n,(p,win,loss,tie) in ts.items():
    d=ds[n];d['w']+=win;d['l']+=loss;d['t']+=tie;d['pf']+=p
    d['mw']+=p>median+1e-8;d['ml']+=p<median-1e-8;d['mt']+=abs(p-median)<=1e-8
    weekly.append([y*10000+(sorted(people).index(n)+1)*100+w,y,w,n,p,median,1 if p>median+1e-8 else -1 if p<median-1e-8 else 0])
  if not ys:continue
  assert sum(d['w'] for d in ds.values())==sum(d['l'] for d in ds.values())
  assert sum(d['mw']+d['ml']+d['mt'] for d in ds.values())==12*len(ys)
  rankkey=lambda n: (-(ds[n]['w']+ds[n]['mw']+(ds[n]['t']+ds[n]['mt'])/2),-round(ds[n]['pf'],2))
  ordered=sorted(ds,key=lambda n:(rankkey(n),n));ranks={n:1+sum(rankkey(m)<rankkey(n) for m in ds) for n in ds}
  boundary=rankkey(ordered[5])==rankkey(ordered[6]);complete=all(p['complete'] for p in people.values())
  entrants=[];exits=[]
  for i,n in enumerate(sorted(ds),1):
   d=ds[n];old=people[n]['rank'];new=ranks[n];delta=old-new;innew=new<=6
   effect='Boundary tie' if boundary else ('Enters' if innew and not people[n]['field'] else 'Exits' if not innew and people[n]['field'] else 'Unchanged') if complete else ('Into current top 6' if innew and old>6 else 'Out of current top 6' if not innew and old<=6 else 'Unchanged')
   if effect=='Enters':entrants.append(n)
   if effect=='Exits':exits.append(n)
   standings.append([y*100+i,y,n,old,d['w'],d['l'],d['t'],d['mw'],d['ml'],d['mt'],d['w']+d['mw'],d['l']+d['ml'],d['t']+d['mt'],(d['w']+d['mw']+(d['t']+d['mt'])/2)/(2*len(ys)),new,delta,effect,round(d['pf'],2),len(ys)])
   if complete:
    c=career[n];c['seasons']+=1;c['up']+=effect=='Enters';c['down']+=effect=='Exits';c['delta']+=delta;c['median']+=d['mw']+d['mt']/2;c['week']+=len(ys);c['w']+=d['w'];c['t']+=d['t']
  champ=sacko='Pending';status='In progress — no postseason replay'
  if complete:
   if len(set(ranks.values()))<12:status='Unresolved standings tie — no postseason replay';champ=sacko='Unresolved'
   else:
    seed_actual={p['rank']:n for n,p in people.items()};newseed={ranks[n]:n for n in ds}
    assert set(seed_actual)==set(range(1,13))
    swap={n:(n if baseline else newseed[r]) for r,n in seed_actual.items()}
    history={};valid=True;unresolved=False
    for idx,g in enumerate(sorted(post[y],key=lambda g:(g['week'],g['phase'],g['a'])),1):
     def origin(n):
      # Only previous rounds determine routing; simultaneous placement games cannot feed one another.
      prior=[x for x in history.get(n,[]) if x[0]<g['week']]
      return prior[-1][1] if prior else swap[n]
     aa,bb=origin(g['a']),origin(g['b']);ap=scores.get((y,g['week'],aa));bp=scores.get((y,g['week'],bb))
     note='';winner=loser=None
     if not aa or not bb or ap is None or bp is None:note='Unresolved — missing lineup score or prior result';unresolved=True
     elif y==2022 and g['champ']:note='Unresolved — canceled Bills–Bengals game';unresolved=True
     elif ap==bp:
      if {aa,bb}=={g['a'],g['b']} and g['winner'] in [aa,bb]:winner=g['winner'];loser=bb if winner==aa else aa;note='Recorded tiebreak retained for identical matchup'
      else:note='Unresolved — tied hypothetical score';unresolved=True
     else:winner,loser=(aa,bb) if ap>bp else (bb,aa)
     actualwinner=g['winner'];actualloser=g['b'] if actualwinner==g['a'] else g['a']
     if actualwinner not in [g['a'],g['b']]:valid=False
     else:
      history.setdefault(actualwinner,[]).append((g['week'],winner));history.setdefault(actualloser,[]).append((g['week'],loser))
     label='Championship Final' if g['champ'] else 'Sacko Final' if g['sacko'] else "Winner's Bracket" if g['phase']=='Championship playoffs' else "Loser's Bracket"
     if g['champ']:champ=winner or 'Unresolved'
     if g['sacko']:sacko=loser or 'Unresolved'
     games.append([y*100+idx,y,g['week'],label,aa or 'Unresolved',ap if ap is not None else '',bb or 'Unresolved',bp if bp is not None else '',winner or 'Unresolved',('Sacko: '+loser if loser and g['sacko'] else note or 'Higher score wins')])
    status='Replay has unresolved branches' if unresolved or not valid else 'Replayed actual bracket routing'
    if champ=='Pending':champ='Unavailable';status='Final coverage unavailable'
    if sacko=='Pending':sacko='Unavailable';status='Final coverage unavailable'
  summaries.append([y,len(ys),'Complete' if complete else 'In progress',len(entrants) if complete and not boundary else '',', '.join(entrants) or ('None' if complete else 'Pending'),', '.join(exits) or ('None' if complete else 'Pending'),champ,sacko,status])
  diagnostics.append({'year':y,'weeks':len(ys),'entries':entrants,'exits':exits,'champion':champ,'sacko':sacko,'status':status})
 careers=[]
 for n,c in sorted(career.items(),key=lambda t:(-(t[1]['up']-t[1]['down']),-t[1]['delta'],t[0])):
  careers.append([n,c['seasons'],c['up'],c['down'],c['up']-c['down'],c['delta']/c['seasons'],c['median']/c['week'],(c['w']+c['t']/2)/c['week'],(c['median']-c['w']-c['t']/2)/c['seasons']])
 return dict(standings=standings,weekly=weekly,summaries=summaries,careers=careers,games=games,diagnostics=diagnostics)

def update_review(b,e):
 if NAME not in b.roots:return
 # Retain compatibility when an older workbook is used accidentally.
 if b.values.get((NAME,'A1'))!='TWO RESULTS. ONE DIFFERENT LEAGUE.':raise ValueError('Settings Change Review layout needs V7.2 master; restore matching workbook/script backup.')
 d=calculate(b,e)
 from excel_cache import colname
 # Clear only generated helper blocks; visible formulas remain intact.
 blocks=[('standings',200,1,250,19),('weekly',500,1,3000,7),('games',200,21,250,10)]
 for key,start,col,capacity,width in blocks:
  for r in range(start,start+capacity):
   for c in range(col,col+width):
    a=colname(c)+str(r)
    if (NAME,a) in b.values:b.set(NAME,a,None)
  if len(d[key])>capacity:raise ValueError('Review helper capacity exceeded: '+key)
  for r,row in enumerate(d[key],start):
   for c,v in enumerate(row,col):b.set(NAME,colname(c)+str(r),v)
 for r,row in enumerate(reversed(d['summaries']),9):
  # Compact visible summary: links/merged output positions are stable.
  for c,v in zip(['A','B','C','D','E','H','K','N','Q'],row):b.set(NAME,c+str(r),v)
 for r in range(112,140):
  for c in range(1,10):b.set(NAME,colname(c)+str(r),None)
 for r,row in enumerate(d['careers'],112):
  for c,v in enumerate(row,1):b.set(NAME,colname(c)+str(r),v)
 b.set(NAME,'R3',max(x[0] for x in d['summaries']))
 return d
