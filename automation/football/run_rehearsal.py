#!/usr/bin/env python3
"""Prepare-only owner-dispatched job. No public artifacts or OneDrive writes."""
import contextlib,datetime,hashlib,io,json,os,re,shutil,subprocess,sys,tempfile,urllib.parse,urllib.request
from pathlib import Path
ORIGIN='https://football-league-admin.swansonfamily.workers.dev'
REPOSITORY='https://github.com/amswansonjr/get-the-money-league.git'
BUNDLE=Path(__file__).resolve().parent
sys.path.insert(0,str(BUNDLE/'workbook'))
from onedrive_files import GraphFiles,NoRedirect

def request(url,method='GET',body=None,headers=None):
    with urllib.request.build_opener(NoRedirect()).open(urllib.request.Request(url,data=body,headers=headers or {},method=method),timeout=60) as response:return response.read()
def token():
    url=os.environ['ACTIONS_ID_TOKEN_REQUEST_URL']
    if not url.startswith('https://') or not urllib.parse.urlsplit(url).hostname.endswith('.actions.githubusercontent.com'):raise ValueError('OIDC_HOST_REJECTED')
    url+=('&' if '?' in url else '?')+urllib.parse.urlencode({'audience':ORIGIN})
    return json.loads(request(url,headers={'Authorization':'Bearer '+os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']}))['value']
def api(job,operation,body=None,name=None):
    headers={'Authorization':'Bearer '+token()};url=ORIGIN+'/api/runner/'+job+'/'+operation
    if name is not None:
        url+='?'+urllib.parse.urlencode({'name':name});headers.update({'Content-Type':'application/octet-stream','X-Content-SHA256':hashlib.sha256(body).hexdigest()});method='PUT'
    else:
        method='GET' if body is None else 'POST'
        if body is not None:body=json.dumps(body,allow_nan=False).encode();headers['Content-Type']='application/json'
    return json.loads(request(url,method,body,headers))
def write(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2)+'\n')
def git(*args,cwd):
    result=subprocess.run(['git',*args],cwd=cwd,capture_output=True,env={**os.environ,'GIT_TERMINAL_PROMPT':'0'},check=True);return result.stdout.decode().strip()
def prepare(context,workspace,root,fixture=None):
    if context['mode']!='PREPARE_ONLY':raise ValueError('PREPARE_ONLY_REQUIRED')
    client=GraphFiles(context['graphAccessToken'],context['targets']);metadata={k:client.metadata(k) for k in context['targets']}
    sources=root/'sources';sources.mkdir();paths={}
    for key in ('privateMaster','viewingCopy'):
        paths[key]=sources/(key+'.xlsx');paths[key].write_bytes(client.download(key,metadata[key]))
    tools=root/'Tools';shutil.copytree(BUNDLE/'website',tools/'Website');shutil.copytree(BUNDLE/'workbook',tools/'Workbook')
    repo=root/'Website Repository';git('clone','--shared',str(workspace),str(repo),cwd=root);git('remote','set-url','origin',REPOSITORY,cwd=repo)
    git('update-ref','refs/remotes/origin/main',context['baseCommit'],cwd=repo)
    config=json.loads((tools/'Website/season-config.json').read_text());config['workbook']=str(paths['privateMaster']);write(tools/'Website/season-config.json',config)
    write(tools/'Workbook/publish_config.json',{'master':str(paths['privateMaster']),'published':str(paths['viewingCopy'])})
    write(root/'website-publishing.json',{'remote':REPOSITORY})
    editorial=tools/'Website/editorial';editorial.mkdir()
    for p in workspace.iterdir():
        if p.name in ('recaps.json','recap-editorials.js') or re.fullmatch(r'recap-week-\d{2}-2026\.png',p.name):shutil.copy2(p,editorial/p.name)
    sys.path.insert(0,str(tools/'Website'));os.environ['GTM_HEADLESS_PREPARE']='1'
    from weekly_prepare import prepare as prepare_package,js_data
    # Existing tools print private paths and details; retain no stdout in public logs.
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        # The workbook subprocess also needs captured output, not just Python redirection.
        old_run=subprocess.run
        def quiet_run(*args,**kwargs):
            if not kwargs.get('capture_output') and not any(k in kwargs for k in ('stdout','stderr')):kwargs['capture_output']=True
            return old_run(*args,**kwargs)
        subprocess.run=quiet_run
        try:run=prepare_package(root,fixture=fixture,no_open=True)
        finally:subprocess.run=old_run
    status=json.loads((run/'package.json').read_text());manifest=json.loads((run/'manifest.json').read_text())
    if status['baseCommit']!=context['baseCommit']:raise ValueError('REPOSITORY_CHANGED_DURING_PREPARATION')
    if any(client.metadata(k)['eTag']!=metadata[k]['eTag'] for k in metadata):raise ValueError('WORKBOOK_CHANGED_DURING_PREPARATION')
    files={p.name:p for p in (run/'website').iterdir() if p.is_file() and p.suffix in ('.html','.css','.js','.json','.svg')}
    files.update({'_workbooks/privateMaster.xlsx':run/'workbooks/Review - Private Master.xlsx','_workbooks/viewingCopy.xlsx':run/'workbooks/Review - League Viewing Copy.xlsx'})
    hashes={n:hashlib.sha256(p.read_bytes()).hexdigest() for n,p in files.items()}
    if len(files)>45 or any(p.stat().st_size>1800000 for p in files.values()) or sum(p.stat().st_size for p in files.values())>8000000:raise ValueError('FREE_STORAGE_GUARD')
    through=status['completedThroughWeek'];key=f'2026-{through}';editorials=js_data(run/'website/recap-editorials.js');recaps=json.loads((run/'website/recaps.json').read_text());recap=next(r for r in recaps['recaps'] if r['season']==2026 and r['week']==through)
    report={'mode':'PREPARED_NOT_DELIVERED','files':hashes,'currentWeek':status['currentWeek'],'collectedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'awards':js_data(run/'website/recap-sleeper-awards.js')[key],'editorial':{'written':'EXISTING_EDITION' if key in editorials else 'PENDING','illustration':'EXISTING_EDITION' if recap.get('artwork') else 'PENDING'},'sourceEtags':{k:v['eTag'] for k,v in metadata.items()},'workbookHashes':{'privateMaster':hashes['_workbooks/privateMaster.xlsx'],'viewingCopy':hashes['_workbooks/viewingCopy.xlsx']},'workbookValidation':{'privateMaster':status['workbookValidation']['master'],'viewingCopy':status['workbookValidation']['viewingCopy']},'corrections':status.get('statCorrections',[]),'warnings':status['warnings'],'collectionHashes':manifest['collectionFiles']}
    return files,report

def main():
    job=os.environ.get('GTM_JOB_ID','')
    if not re.fullmatch(r'[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}',job):raise ValueError('INVALID_JOB_ID')
    if os.environ.get('GITHUB_REPOSITORY')!='amswansonjr/get-the-money-league' or os.environ.get('GITHUB_EVENT_NAME')!='workflow_dispatch':raise ValueError('OWNER_DISPATCH_REQUIRED')
    context=api(job,'context');workspace=Path(os.environ['GITHUB_WORKSPACE']).resolve()
    if git('rev-parse','HEAD',cwd=workspace)!=context['baseCommit']:raise ValueError('CHECKOUT_CHANGED')
    with tempfile.TemporaryDirectory(prefix='football-private-',dir=os.environ.get('RUNNER_TEMP')) as temp:
        files,report=prepare(context,workspace,Path(temp))
        for name,p in files.items():api(job,'file',p.read_bytes(),name)
        receipt=api(job,'complete',report)
        if receipt.get('status')!='READY_FOR_REVIEW':raise ValueError('REVIEW_NOT_READY')
    print('READY FOR PRIVATE REVIEW. Website not published. OneDrive originals not replaced.')
if __name__=='__main__':
    try:main()
    except Exception:
        try:
            if re.fullmatch(r'[0-9a-f-]{36}',os.environ.get('GTM_JOB_ID','')):api(os.environ['GTM_JOB_ID'],'failed',{})
        except Exception:pass
        print('Cloud preparation stopped. Review the private admin status. No publication was attempted.',file=sys.stderr)
        sys.exit(1)
