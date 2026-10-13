"""Python 3.9+ taxonomy archive validator. No third-party dependencies."""
import argparse,csv,hashlib,json,posixpath,time,urllib.request,urllib.error,urllib.parse,xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile
from html.parser import HTMLParser
class Links(HTMLParser):
 def __init__(self):super().__init__();self.links=[]
 def handle_starttag(self,tag,attrs):self.links.extend(v for k,v in attrs if k in ('href','src') and v)
def tree(n):return {'tag':n.tag,'attributes':dict(n.attrib),'text':n.text,'children':[tree(c) for c in n]}
def audit(path,case):
 errors=[];checks=[];coverage={};query=case['query']
 def check(ok,label):(checks if ok else errors).append(label)
 with ZipFile(path) as z:
  names=z.namelist()
  if sum(i.file_size for i in z.infolist())>128*1024*1024:raise ValueError('Expanded archive exceeds 128 MiB client limit')
  check(len(names)==len(set(names)),'unique filenames');m=json.loads(z.read('manifest.json'));d=json.loads(z.read('normalized_metadata.json'));sources=m.get('sources',[])
  for s in sources:
   if s.get('file'):
    h=hashlib.sha256()
    with z.open(s['file']) as f:
     while True:
      chunk=f.read(65536)
      if not chunk:break
      h.update(chunk)
    check(h.hexdigest()==s.get('sha256'),s['name']+' checksum');check(z.getinfo(s['file']).file_size==s.get('size_bytes'),s['name']+' size')
   if s.get('status')=='validated':check(bool(s.get('file')) and s.get('complete') is True,s['name']+' source retained')
  excel=m.get('excel_export',{})
  if excel.get('status')=='included':
   check(excel.get('file')=='metadata.xlsx' and 'metadata.xlsx' in names,'Excel workbook present')
   if 'metadata.xlsx' in names:
    import io
    try:
     with ZipFile(io.BytesIO(z.read('metadata.xlsx'))) as workbook:
      check(workbook.testzip() is None and 'xl/workbook.xml' in workbook.namelist(),'Excel package integrity')
    except Exception:check(False,'Excel package readable')
  elif excel.get('status')=='omitted':
   check(bool(excel.get('reason')) and 'metadata.xlsx' not in names,'Excel omission explained')
  coverage['excel_status']=excel.get('status','not_requested')
  # Name searches can intentionally produce a diagnostic ZIP without a record.
  expected=case.get('expected','record');error=m.get('error') or {};count=error.get('total_matches')
  diagnostic=(expected=='ambiguous' and isinstance(count,int) and count>1) or (expected=='not_found' and count==0)
  if not d:
   if expected in ('ambiguous','not_found'):check(diagnostic,'expected name-search diagnostic')
   outcome='FAIL' if errors else 'EXPECTED_DIAGNOSTIC' if diagnostic else 'PARTIAL'
  else:
   check(d.get('query')==query,'query identity');check(d.get('schema_version')==2,'schema version');check(d.get('from_cache') is False,'fresh retrieval')
   if case.get('tax_id'):check(d.get('tax_id')==case['tax_id'],'expected resolved TaxID')
   if query.isdigit():check(d.get('requested_tax_id')==query,'requested TaxID')
   check({'esummary','efetch'}.issubset({s.get('name') for s in sources}),'both sources accounted for')
   xml=next((s for s in sources if s.get('name')=='efetch' and s.get('status')=='validated'),None)
   if xml:
    with z.open(xml['file']) as f:root=ET.parse(f).getroot()
    ts=root.findall('./Taxon');check(len(ts)==1,'one top-level Taxon');t=ts[0];actual=t.findtext('TaxId');aliases=[n.text for n in t.findall('AkaTaxIds/TaxId')]
    check(actual==d.get('tax_id'),'XML resolved identity');check(d.get('requested_tax_id')==actual or d.get('requested_tax_id') in aliases,'requested ID or documented alias')
    check(tree(t)==d.get('source_structure'),'complete parsed XML structure')
    for tag,key in [('ScientificName','scientific_name'),('Rank','rank'),('Division','division'),('ParentTaxId','parent_tax_id'),('Lineage','lineage_string')]:check((t.findtext(tag) or None)==d.get(key),key+' mapping')
    lineage=[{'tax_id':n.findtext('TaxId'),'name':n.findtext('ScientificName'),'rank':n.findtext('Rank')} for n in t.findall('LineageEx/Taxon')];check(lineage==d.get('lineage'),'all lineage entries')
    other=t.find('OtherNames');check((tree(other) if other is not None else None)==d.get('other_names'),'all name classes')
    check([n.text for n in t.findall('OtherNames/Synonym') if n.text]==d.get('synonyms'),'synonyms')
    for tag,key,idtag,nametag in [('GeneticCode','genetic_code','GCId','GCName'),('MitoGeneticCode','mitochondrial_genetic_code','MGCId','MGCName')]:
     n=t.find(tag);v=n.findtext(idtag) if n is not None else None;expected_code=None if n is None else {'id':int(v) if v and v.isdigit() else None,'name':n.findtext(nametag)};check(expected_code==d.get(key),key+' including null and zero')
    for tag,key in [('CreateDate','created'),('UpdateDate','updated'),('PubDate','published')]:check((t.findtext(tag) or None)==(d.get('dates') or {}).get(key),'date '+key)
    coverage={'tax_id':actual,'name':t.findtext('ScientificName'),'rank':t.findtext('Rank'),'lineage_entries':len(lineage),'name_entries':len(other) if other is not None else 0}
   summary=next((s for s in sources if s.get('name')=='esummary' and s.get('status')=='validated'),None)
   if summary:
    records=json.loads(z.read(summary['file'])).get('result',{});s=records.get(d.get('requested_tax_id'));check(isinstance(s,dict) and s==d.get('esummary_data'),'summary content preserved')
   complete=bool(xml and summary) and all(s.get('status')=='validated' for s in sources) and not d.get('normalization_error')
   if m.get('status')=='validated':check(complete,'manifest success is justified')
   if expected in ('ambiguous','not_found') and complete:check(False,'unexpected record for negative case')
   outcome='FAIL' if errors else 'PASS' if complete else 'PARTIAL'
  check('report.html' in names,'offline report present')
  for name in names:
   if name.endswith('.html'):
    parser=Links();parser.feed(z.read(name).decode())
    for link in parser.links:
     parts=urllib.parse.urlsplit(link)
     if parts.scheme or parts.netloc or not parts.path:continue
     target=posixpath.normpath(posixpath.join(posixpath.dirname(name),urllib.parse.unquote(parts.path)));check(target in names,'offline link '+target)
  if errors:outcome='FAIL'
 return {'query':query,'outcome':outcome,'checks_passed':len(checks),'errors':errors,'coverage':coverage,'excel_export':m.get('excel_export'),'sources':sources,'diagnostic':error,'archive':str(path)}
def run():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base-url',default='http://127.0.0.1:5001');p.add_argument('--cases',default=str(Path(__file__).with_name('cases.json')));p.add_argument('--out',default='taxonomy_validation_results');p.add_argument('--limit',type=int,default=12);p.add_argument('--delay',type=float,default=2);p.add_argument('--keep-zips',action='store_true');p.add_argument('--archive');p.add_argument('--query');a=p.parse_args()
 out=Path(a.out);out.mkdir(parents=True,exist_ok=True);results=[]
 if a.archive:
  if not a.query:p.error('--archive requires --query')
  results=[audit(a.archive,{'query':a.query})]
 else:
  cases=json.loads(Path(a.cases).read_text())[:max(0,a.limit)]
  local=urllib.parse.urlsplit(a.base_url).hostname in ('127.0.0.1','localhost','::1');opener=urllib.request.build_opener(urllib.request.ProxyHandler({})) if local else urllib.request.build_opener()
  for i,case in enumerate(cases):
   query=case['query'];path=out/('%05d.zip'%i)
   try:
    url=a.base_url.rstrip('/')+'/api/taxonomy/'+urllib.parse.quote(query,safe='')+'/download'
    with opener.open(url,timeout=180) as response,path.open('wb') as f:
     size=0
     while True:
      chunk=response.read(65536)
      if not chunk:break
      size+=len(chunk)
      if size>96*1024*1024:raise ValueError('Download exceeds 96 MiB client limit')
      f.write(chunk)
    row=audit(path,case)
   except urllib.error.HTTPError as e:row={'query':query,'outcome':'REQUEST_ERROR','http_status':e.code,'errors':[e.read(2048).decode(errors='replace')]}
   except Exception as e:row={'query':query,'outcome':'ERROR','errors':[type(e).__name__+': '+str(e)]}
   row['group']=case.get('group');results.append(row)
   if row['outcome'] in ('PASS','EXPECTED_DIAGNOSTIC') and not a.keep_zips:path.unlink(missing_ok=True)
   row['archive_retained']=path.exists();print(query,row['outcome'],flush=True);(out/'results.json').write_text(json.dumps(results,indent=2))
   if i+1<len(cases):time.sleep(max(1,a.delay))
 (out/'results.json').write_text(json.dumps(results,indent=2))
 with (out/'summary.csv').open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['query','outcome','checks_passed','errors']);w.writerows([r['query'],r['outcome'],r.get('checks_passed',0),'; '.join(r.get('errors',[]))] for r in results)
 print('Reports:',out.resolve());return int(any(r['outcome'] in ('FAIL','ERROR','REQUEST_ERROR') for r in results))
if __name__=='__main__':raise SystemExit(run())
