"""Evaluate the small, audited Excel formula subset used by League Headquarters.
No macros, network calls or Python evaluation of workbook text.
"""
import re, fnmatch, math

TOKEN=re.compile(r'''\s*(?:("(?:[^"]|"")*")|('(?:[^']|'')*'!\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?)|((?:[A-Za-z_][A-Za-z0-9_.]*!)?\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?)|(\d+(?:\.\d*)?(?:[Ee][+-]?\d+)?)|([A-Za-z_][A-Za-z0-9_.]*)|(<>|<=|>=|[=<>+*/^&(),%:-]))''')
def colnum(a):
 n=0
 for c in a:n=n*26+ord(c)-64
 return n
def address(a):
 m=re.fullmatch(r'\$?([A-Z]+)\$?(\d+)',a);return int(m[2]),colnum(m[1])
def colname(n):
 s=''
 while n:n,r=divmod(n-1,26);s=chr(65+r)+s
 return s
class FormulaError(Exception):pass
class Engine:
 def __init__(self,values,formulas):
  self.values=values;self.formulas=formulas;self.cache={};self.active=set();self.asts={};self.ranges={};self.queries={}
 def parse(self,text):
  if text in self.asts:return self.asts[text]
  tokens=[];pos=0
  while pos<len(text):
   m=TOKEN.match(text,pos)
   if not m:raise FormulaError('Unsupported formula at '+text[pos:pos+80])
   group=next((i,v) for i,v in enumerate(m.groups()) if v is not None);tokens.append(group);pos=m.end()
  i=0
  precedence={'=':1,'<>':1,'<':1,'>':1,'<=':1,'>=':1,'&':2,'+':3,'-':3,'*':4,'/':4,'^':5}
  def expr(level=0):
   nonlocal i
   typ,t=tokens[i];i+=1
   if t in ['+','-']:node=('unary',t,expr(6))
   elif t=='(':
    node=expr();assert tokens[i][1]==')';i+=1
   elif typ==0:node=('literal',t[1:-1].replace('""','"'))
   elif typ in [1,2]:node=('ref',t)
   elif typ==3:node=('literal',float(t) if any(c in t for c in '.eE') else int(t))
   elif typ==4:
    if t in ['TRUE','FALSE']:node=('literal',t=='TRUE')
    else:
     assert tokens[i][1]=='(',(t,tokens[i]);i+=1;args=[]
     if tokens[i][1]!=')':
      while True:
       args.append(expr())
       if tokens[i][1]!=',':break
       i+=1
     assert tokens[i][1]==')';i+=1;node=('call',t.replace('_xlfn.','').upper(),args)
   else:raise FormulaError('Unexpected '+t)
   while i<len(tokens):
    op=tokens[i][1]
    if op=='%':i+=1;node=('binary','/',node,('literal',100));continue
    if op not in precedence or precedence[op]<level:break
    i+=1;node=('binary',op,node,expr(precedence[op]+1))
   return node
  ast=expr()
  if i!=len(tokens):raise FormulaError('Unparsed '+str(tokens[i:]))
  self.asts[text]=ast;return ast
 def cell(self,sheet,a):
  key=(sheet,a.replace('$',''))
  if key in self.cache:return self.cache[key]
  if key not in self.formulas:return self.values.get(key)
  if key in self.active:raise FormulaError('Circular reference '+str(key))
  self.active.add(key)
  try:v=self.run(self.parse(self.formulas[key].lstrip('=')),sheet)
  finally:self.active.remove(key)
  if isinstance(v,float) and not math.isfinite(v):raise FormulaError('Nonfinite '+str(key))
  self.cache[key]=v;return v
 def ref(self,sheet,text):
  if '!' in text:
   sheet,text=text.rsplit('!',1);sheet=sheet.strip("'").replace("''", "'")
  text=text.replace('$','')
  if ':' not in text:return self.cell(sheet,text)
  key=(sheet,text)
  if key not in self.ranges:
   a,b=text.split(':');r1,c1=address(a);r2,c2=address(b)
   self.ranges[key]=[self.cell(sheet,colname(c)+str(r)) for r in range(r1,r2+1) for c in range(c1,c2+1)]
  return self.ranges[key]
 @staticmethod
 def number(v):
  if v is None or v=='':return 0
  if isinstance(v,(int,float)):return v
  try:return float(v)
  except (ValueError,TypeError):raise FormulaError('Expected number '+str(v))
 @staticmethod
 def text(v):
  if v is None:return ''
  if isinstance(v,float) and v.is_integer():return str(int(v))
  return str(v)
 def equal(self,a,b):
  if a is None:a=''
  if b is None:b=''
  if isinstance(a,str) and isinstance(b,str):return a.casefold()==b.casefold()
  if (a=='' and isinstance(b,(int,float))) or (b=='' and isinstance(a,(int,float))):return self.number(a)==self.number(b)
  return a==b
 def criterion(self,value,criterion):
  if not isinstance(criterion,str):return self.equal(value,criterion)
  m=re.match(r'^(<>|<=|>=|=|<|>)(.*)$',criterion);op,target=m.groups() if m else ('=',criterion)
  try:target=float(target);value=self.number(value)
  except (ValueError,FormulaError):
   if value is None:value=''
   if '*' in target or '?' in target:
    hit=fnmatch.fnmatchcase(str(value).casefold(),target.casefold());return not hit if op=='<>' else hit
  if op=='=':return self.equal(value,target)
  if op=='<>':return not self.equal(value,target)
  if not isinstance(value,(int,float))==isinstance(target,(int,float)):return False
  return {'<':lambda:value<target,'>':lambda:value>target,'<=':lambda:value<=target,'>=':lambda:value>=target}[op]()
 def run(self,node,sheet):
  kind=node[0]
  if kind=='literal':return node[1]
  if kind=='ref':return self.ref(sheet,node[1])
  if kind=='unary':return self.number(self.run(node[2],sheet))*(-1 if node[1]=='-' else 1)
  if kind=='binary':
   op=node[1];a=self.run(node[2],sheet);b=self.run(node[3],sheet)
   if isinstance(a,list) or isinstance(b,list):
    aa=a if isinstance(a,list) else [a]*len(b);bb=b if isinstance(b,list) else [b]*len(a)
    return [self.run(('binary',op,('literal',x),('literal',y)),sheet) for x,y in zip(aa,bb)]
   if op=='&':return self.text(a)+self.text(b)
   if op in ['=','<>']:return self.equal(a,b) if op=='=' else not self.equal(a,b)
   if op in ['<','>','<=','>=']:
    if a is None:a=0
    if b is None:b=0
    return {'<':lambda:a<b,'>':lambda:a>b,'<=':lambda:a<=b,'>=':lambda:a>=b}[op]()
   a,b=self.number(a),self.number(b)
   return {'+':lambda:a+b,'-':lambda:a-b,'*':lambda:a*b,'/':lambda:a/b,'^':lambda:a**b}[op]()
  _,name,args=node
  if name=='IF':return self.run(args[1] if self.run(args[0],sheet) else args[2],sheet)
  if name=='IFERROR':
   try:return self.run(args[0],sheet)
   except (FormulaError,ZeroDivisionError,ValueError,IndexError):return self.run(args[1],sheet)
  # Cache repeated COUNTIFS/SUMIFS lookups, using range identities and resolved criteria.
  if name in ['COUNTIFS','SUMIFS','MINIFS','MAXIFS','COUNTIF']:
   offset=0 if name in ['COUNTIFS','COUNTIF'] else 1
   crit=[(args[i][1],self.run(args[i+1],sheet)) for i in range(offset,len(args),2)]
   key=(sheet,name,args[0][1] if offset else '',tuple((r,self.text(c)) for r,c in crit))
   if key in self.queries:return self.queries[key]
   arrays=[self.run(args[i],sheet) for i in range(offset,len(args),2)];hits=[]
   for i,vs in enumerate(zip(*arrays)):
    if all(self.criterion(v,c[1]) for v,c in zip(vs,crit)):hits.append(i)
   if offset:
    nums=self.run(args[0],sheet);values=[self.number(nums[i]) for i in hits]
    result=(sum(values) if name=='SUMIFS' else min(values) if name=='MINIFS' and values else max(values) if values else 0)
   else:result=len(hits)
   self.queries[key]=result;return result
  vs=[self.run(a,sheet) for a in args]
  if name=='SUM':return sum(self.number(x) for v in vs for x in (v if isinstance(v,list) else [v]) if isinstance(x,(int,float)) or x is None)
  if name=='AND':return all(vs)
  if name=='ISNUMBER':return isinstance(vs[0],(int,float)) and not isinstance(vs[0],bool)
  if name=='ABS':return abs(self.number(vs[0]))
  if name=='TEXT':return str(int(round(self.number(vs[0])))) if vs[1]=='0' else self.text(vs[0])
  if name=='MATCH':
   for i,x in enumerate(vs[1],1):
    if self.equal(x,vs[0]):return i
   raise FormulaError('MATCH not found')
  if name=='INDEX':return vs[0][int(vs[1])-1]
  if name=='LOOKUP':
   hit=None
   for i,v in enumerate(vs[1]):
    if isinstance(v,(int,float)) and v<=vs[0]:hit=i
   if hit is None:raise FormulaError('LOOKUP not found')
   return (vs[2] if len(vs)>2 else vs[1])[hit]
  raise FormulaError('Unsupported function '+name)
