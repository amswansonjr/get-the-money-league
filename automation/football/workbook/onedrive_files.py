"""OneDrive transport for approved workbook bytes. No credentials or files embedded.

The caller supplies a short-lived delegated Graph access token from an encrypted
credential store. This module never creates sharing links or changes permissions.
"""
import hashlib,json,urllib.request,urllib.error,urllib.parse

class DeliveryError(Exception):pass
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def sha(data):return hashlib.sha256(data).hexdigest()
def allowed_transfer_url(url):
    p=urllib.parse.urlsplit(url)
    return p.scheme=='https' and not p.username and not p.password and p.port in (None,443) and any(p.hostname and (p.hostname==suffix or p.hostname.endswith('.'+suffix)) for suffix in ('1drv.com','onedrive.com','sharepoint.com','live.com','microsoftpersonalcontent.com'))

class GraphFiles:
    def __init__(self,access_token,targets,opener=None):
        if not access_token:raise DeliveryError('MICROSOFT_CONNECTION_REQUIRED')
        self.token=access_token;self.targets=targets;self.open=opener or urllib.request.build_opener(NoRedirect()).open
    def item_url(self,key):
        if key not in ('privateMaster','viewingCopy') or key not in self.targets:raise DeliveryError('UNAPPROVED_TARGET')
        t=self.targets[key]
        return 'https://graph.microsoft.com/v1.0/drives/'+urllib.parse.quote(t['driveId'],safe='')+'/items/'+urllib.parse.quote(t['itemId'],safe='')
    def request(self,url,method='GET',data=None,headers=None,graph=True):
        if graph and not url.startswith('https://graph.microsoft.com/v1.0/'):raise DeliveryError('UNAPPROVED_GRAPH_HOST')
        if not graph and not allowed_transfer_url(url):raise DeliveryError('UNAPPROVED_TRANSFER_HOST')
        h={'Authorization':'Bearer '+self.token} if graph else {}
        h.update(headers or {})
        try:
            with self.open(urllib.request.Request(url,data=data,headers=h,method=method),timeout=45) as response:return response.status,response.read()
        except urllib.error.HTTPError as error:
            # Never expose token, preauthenticated URL or upstream body in logs.
            raise DeliveryError('GRAPH_PRECONDITION_FAILED' if error.code==412 else 'GRAPH_HTTP_'+str(error.code)) from None
    def metadata(self,key):
        _,body=self.request(self.item_url(key));item=json.loads(body)
        if item.get('id')!=self.targets[key]['itemId'] or not item.get('eTag') or not item.get('file'):raise DeliveryError('FILE_IDENTITY_UNVERIFIED')
        expected_name=self.targets[key].get('name')
        if expected_name and item.get('name')!=expected_name:raise DeliveryError('FILE_NAME_CHANGED')
        return item
    def download(self,key,item=None):
        item=item or self.metadata(key);url=item.get('@microsoft.graph.downloadUrl')
        if not url:raise DeliveryError('DOWNLOAD_URL_UNAVAILABLE')
        _,body=self.request(url,graph=False)
        if len(body)!=item.get('size'):raise DeliveryError('DOWNLOAD_SIZE_MISMATCH')
        return body
    def replace(self,key,body,expected_etag):
        item=self.metadata(key)
        if item['eTag']!=expected_etag:raise DeliveryError('FILE_CHANGED_SINCE_REVIEW')
        payload=json.dumps({'item':{'@microsoft.graph.conflictBehavior':'replace'}}).encode()
        _,raw=self.request(self.item_url(key)+'/createUploadSession','POST',payload,{'Content-Type':'application/json','If-Match':expected_etag})
        url=json.loads(raw).get('uploadUrl')
        if not url or not allowed_transfer_url(url):raise DeliveryError('UPLOAD_URL_UNVERIFIED')
        chunk_size=320*1024
        for start in range(0,len(body),chunk_size):
            chunk=body[start:start+chunk_size];status,raw=self.request(url,'PUT',chunk,{'Content-Type':'application/octet-stream','Content-Length':str(len(chunk)),'Content-Range':f'bytes {start}-{start+len(chunk)-1}/{len(body)}'},graph=False)
            if status not in (200,201,202):raise DeliveryError('UPLOAD_NOT_ACCEPTED')
        updated=self.metadata(key)
        if sha(self.download(key,updated))!=sha(body):raise DeliveryError('DELIVERY_HASH_MISMATCH')
        return {'status':'VERIFIED','itemId':updated['id'],'sha256':sha(body),'eTag':updated['eTag']}

def deliver_pair(client,prepared,approval,backup_dir):
    """Separate receipts; a partial delivery is never reported as all-complete."""
    from pathlib import Path
    if not approval.get('packageId') or approval.get('decision')!='APPROVED_TO_PUBLISH':raise DeliveryError('EXACT_APPROVAL_REQUIRED')
    for key in ('privateMaster','viewingCopy'):
        if approval.get('workbookHashes',{}).get(key)!=sha(prepared[key]):raise DeliveryError('APPROVED_WORKBOOK_CHANGED')
        if approval.get('targets',{}).get(key)!=client.targets[key]:raise DeliveryError('APPROVED_TARGET_CHANGED')
    backup=Path(backup_dir);backup.mkdir(parents=True,exist_ok=False)
    # Preflight both targets and save both originals before replacing either.
    for key in ('privateMaster','viewingCopy'):
        item=client.metadata(key)
        if item['eTag']!=approval['sourceEtags'][key]:raise DeliveryError('FILE_CHANGED_SINCE_REVIEW')
        (backup/(key+'.xlsx')).write_bytes(client.download(key,item))
    result={'packageId':approval['packageId'],'complete':False,'privateMaster':{'status':'NOT_ATTEMPTED'},'viewingCopy':{'status':'NOT_ATTEMPTED'}}
    for key in ('privateMaster','viewingCopy'):
        try:result[key]=client.replace(key,prepared[key],approval['sourceEtags'][key])
        except DeliveryError as error:
            result[key]={'status':'FAILED','code':str(error)};break
    result['complete']=all(result[k]['status']=='VERIFIED' for k in ('privateMaster','viewingCopy'))
    (backup/'delivery-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
