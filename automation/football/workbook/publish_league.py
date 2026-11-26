#!/usr/bin/env python3
"""Refresh privately and publish a validated viewing workbook. Standard library only."""
import argparse,copy,datetime,hashlib,json,os,posixpath,re,shutil,subprocess,sys,tempfile,uuid,zipfile
import xml.etree.ElementTree as E
from pathlib import Path
from refresh_league import Book,M,R,q
EXCLUDE={'TEST INFORMATION','Settings Change Review','Refresh Instructions'}
PK='http://schemas.openxmlformats.org/package/2006/relationships'
CT='http://schemas.openxmlformats.org/package/2006/content-types'
def locked(path):return (path.parent/('~$'+path.name)).exists()
def require_closed(path):
 if locked(path):raise ValueError('Save and close this workbook in Excel: '+str(path))
def resolve(part,target):
 return posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join(posixpath.dirname(part),target))
def relationship_part(part):return posixpath.dirname(part)+'/_rels/'+posixpath.basename(part)+'.rels' if part else '_rels/.rels'
def patch_element(raw,local,node):
 text=raw.decode('utf-8');pattern=r'<(?:\w+:)?'+local+r'\b[^>]*>.*?</(?:\w+:)?'+local+r'>'
 replacement=E.tostring(node,encoding='unicode') if node is not None else ''
 text,count=re.subn(pattern,lambda _:replacement,text,flags=re.S)
 if count!=1:raise ValueError('Expected one workbook '+local+' element.')
 return text.encode('utf-8')
def public_copy(master,target):
 b=Book(master)
 for (n,a),formula in b.formulas.items():
  if n not in EXCLUDE and any(("'"+name+"'!") in formula for name in EXCLUDE):raise ValueError('A public report depends on an excluded admin sheet: '+n+'!'+a)
 b.set('HQ Dashboard','A40','League viewing copy. Use table filters to explore the history.')
 b.set('HQ Dashboard','A41','Updated from the private master. Check the completed week and timestamp above.')
 b.save(target)
 with zipfile.ZipFile(target) as z:files={n:z.read(n) for n in z.namelist()}
 wb=E.fromstring(files['xl/workbook.xml']);rels=E.fromstring(files['xl/_rels/workbook.xml.rels']);sheets=wb.find(q('sheets'));old=list(sheets);removed={s.get('{'+R+'}id') for s in old if s.get('name') in EXCLUDE}
 kept=[s for s in old if s.get('name') not in EXCLUDE];mapping={old.index(s):i for i,s in enumerate(kept)};sheets[:]=kept
 for rel in list(rels):
  if rel.get('Id') in removed:rels.remove(rel)
 raw=patch_element(files['xl/workbook.xml'],'sheets',sheets)
 names=wb.find(q('definedNames'))
 if names is not None:
  for node in list(names):
   local=node.get('localSheetId')
   if any(name in (node.text or '') for name in EXCLUDE) or (local is not None and int(local) not in mapping):names.remove(node)
   elif local is not None:node.set('localSheetId',str(mapping[int(local)]))
  raw=patch_element(raw,'definedNames',names if len(names) else None)
 views=wb.find(q('bookViews'))
 if views is not None:
  for view in views:view.set('activeTab','0');view.set('firstSheet','0')
  raw=patch_element(raw,'bookViews',views)
 files['xl/workbook.xml']=raw;files['xl/_rels/workbook.xml.rels']=E.tostring(rels,encoding='utf-8',xml_declaration=True)
 # Follow the OPC relationship graph after removing admin sheet edges. This
 # removes their exclusive drawings/images too, rather than merely hiding tabs.
 reachable={'[Content_Types].xml'}
 def visit(part):
  if part and part in reachable:return
  if part:reachable.add(part)
  relpart=relationship_part(part)
  if relpart not in files:return
  reachable.add(relpart)
  for rel in E.fromstring(files[relpart]):
   if rel.get('TargetMode')=='External':continue
   dest=resolve(part,rel.get('Target'))
   if dest not in files:raise ValueError('Broken workbook relationship: '+dest)
   visit(dest)
 visit('')
 files={n:raw for n,raw in files.items() if n in reachable}
 types=E.fromstring(files['[Content_Types].xml'])
 for node in list(types):
  if node.get('PartName') and node.get('PartName').lstrip('/') not in files:types.remove(node)
 files['[Content_Types].xml']=E.tostring(types,encoding='utf-8',xml_declaration=True)
 # These optional cached document-property lists still name removed tabs.
 if 'docProps/app.xml' in files:
  text=files['docProps/app.xml'].decode('utf-8')
  for local in ['HeadingPairs','TitlesOfParts']:text=re.sub(r'<(?:\w+:)?'+local+r'\b[^>]*>.*?</(?:\w+:)?'+local+r'>','',text,flags=re.S)
  files['docProps/app.xml']=text.encode('utf-8')
 # Keep exactly one active sheet; retaining grouped tabs would permit edits
 # on several sheets if a recipient downloads a personal editable copy.
 for n,part in b.paths.items():
  if n in EXCLUDE or part not in files:continue
  text=files[part].decode('utf-8')
  text=re.sub(r'(<(?:\w+:)?sheetView\b[^>]*?)\s+tabSelected="[01]"',r'\1',text)
  if n=='HQ Dashboard':text=re.sub(r'(<(?:\w+:)?sheetView\b)',r'\1 tabSelected="1"',text,count=1)
  files[part]=text.encode('utf-8')
 with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
  for n,raw in files.items():z.writestr(n,raw)
 validate(target,public=True)
def validate(path,public=False):
 with zipfile.ZipFile(path) as z:
  if z.testzip():raise ValueError('Invalid ZIP package: '+str(path))
  wb=E.fromstring(z.read('xl/workbook.xml'));names=[s.get('name') for s in wb.find(q('sheets'))]
  if public and EXCLUDE.intersection(names):raise ValueError('Admin/test sheet retained in public workbook.')
  if 'HQ Dashboard' not in names or 'Matchups' not in names:raise ValueError('Missing required report/source sheets.')
  if not public:
   for s in wb.find(q('sheets')):
    # The review may be visible privately; public_copy removes it regardless.
    if s.get('name')=='TEST INFORMATION' and s.get('state')!='hidden':raise ValueError('Private test sheet should be hidden.')
  for n in z.namelist():
   if n.startswith('xl/worksheets/') and n.endswith('.xml'):
    r=E.fromstring(z.read(n))
    merges=r.find(q('mergeCells'))
    if merges is not None and len({x.get('ref') for x in merges})!=len(merges):raise ValueError('Duplicate merged cells: '+n)
    for c in r.findall('.//'+q('c')):
     if c.get('t')=='e':raise ValueError('Saved formula error in '+n+'!'+c.get('r'))
 b=Book(path);gamecell=b.cells['HQ Dashboard']['B20'];gamevalue=gamecell.find(q('v'));games=float(gamevalue.text) if gamevalue is not None else None
 if not isinstance(games,(int,float)) or games<0 or games%6:raise ValueError('Invalid completed-game count.')
 for row in range(3,7):
  c=b.cells.get('Refresh Instructions',{}).get('Q'+str(row))
  if c is not None:
   value=c.find(q('v'))
   if value is not None and value.text!='PASS':raise ValueError('Live refresh validation did not pass.')
 return {'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),'sheets':len(names),'completed_games_2026':int(games)}
def commit_pair(master_stage,master,public_stage,published,backups):
 stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6];backups.mkdir(parents=True,exist_ok=True);previous={}
 for kind,path in [('master',master),('published',published)]:
  require_closed(path)
  if path.exists():
   backup=backups/(kind+'_'+stamp+'.xlsx');shutil.copy2(path,backup);previous[path]=backup
 # Both stages are already in their destination directories for same-volume
 # atomic replacement. Roll back the master if the second commit fails.
 changed=[]
 try:
  for stage,target in [(master_stage,master),(public_stage,published)]:os.replace(stage,target);changed.append(target)
 except Exception:
  for target in reversed(changed):
   if target in previous:
    temp=target.with_name('.rollback-'+uuid.uuid4().hex+'.xlsx');shutil.copy2(previous[target],temp);os.replace(temp,target)
   elif target.exists():target.unlink()
  raise
 return {str(k):str(v) for k,v in previous.items()}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--config',type=Path);ap.add_argument('--data-dir',type=Path);ap.add_argument('--publish-only',action='store_true');args=ap.parse_args()
 folder=Path(__file__).resolve().parent;config=json.loads((args.config or folder/'publish_config.json').read_text());master=Path(config['master']).expanduser();published=Path(config['published']).expanduser()
 if master.resolve()==published.resolve():raise ValueError('Master and published paths must differ.')
 # Scripts/raw backups must never live underneath the shared destination.
 if published.parent.resolve()==folder.resolve() or published.parent.resolve() in folder.resolve().parents:raise ValueError('Admin folder must not be inside the shared destination folder.')
 if not published.parent.is_dir():raise ValueError('Shared destination folder is missing: '+str(published.parent))
 require_closed(master);require_closed(published)
 token=uuid.uuid4().hex;stage=master.parent/('.validated-master-'+token+'.xlsx');pubstage=published.parent/('.validated-view-'+token+'.xlsx')
 try:
  if args.publish_only:shutil.copy2(master,stage)
  else:
   cmd=[sys.executable,str(folder/'refresh_league.py'),'--workbook',str(master),'--output',str(stage)]
   if args.data_dir:cmd+=['--data-dir',str(args.data_dir.resolve())]
   subprocess.run(cmd,check=True)
  private_report=validate(stage);public_copy(stage,pubstage);public_report=validate(pubstage,True)
  if private_report['completed_games_2026']!=public_report['completed_games_2026']:raise ValueError('Master/viewing-copy mismatch.')
  saved=commit_pair(stage,master,pubstage,published,folder/'Backups')
  report={'completed_at':datetime.datetime.now().astimezone().isoformat(),'master':str(master),'published':str(published),'master_validation':private_report,'published_validation':public_report,'backups':saved,'OneDrive_sync':'not verified by local publication','sharing_permissions':'not modified'}
  logs=folder/'Publish Logs';logs.mkdir(exist_ok=True);(logs/(datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.json')).write_text(json.dumps(report,indent=2))
  print('REFRESH AND PUBLISH COMPLETE\nMaster: '+str(master)+'\nLeague viewing copy: '+str(published),flush=True)
 finally:
  for p in [stage,pubstage]:
   if p.exists():p.unlink()
if __name__=='__main__':
 try:main()
 except Exception as exc:print('PUBLISH FAILED — last published copy retained.\n'+str(exc),file=sys.stderr);sys.exit(1)
