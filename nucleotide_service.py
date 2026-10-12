"""Fresh nucleotide source snapshots with a bounded display and disk-backed archives."""
import re,json,html,hashlib,tempfile
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import xml.etree.ElementTree as ET
from flask import jsonify,send_file
import gene_service as gene
from protein_extended import Budget,validate

MAX_SEQUENCE_LENGTH=2_000_000
DISPLAY_FEATURES=200

def accession_id(value):
    value=str(value).strip().upper()
    if re.match(r'^(?:NP|XP|YP|WP|AP|ZP)_',value):raise ValueError('This is a protein accession. Use the Protein tab.')
    if not re.fullmatch(r'(?:N[CMGRTWZ]_[A-Z]*\d{5,12}|X[MR]_\d{5,12}|[A-Z]\d{5}|[A-Z]{2}\d{6,8}|[A-Z]{4,6}\d{8,12})(?:\.[1-9]\d{0,3})?',value):
        raise ValueError('Enter a nucleotide accession, for example NM_007294.4. Gene symbols and protein accessions are not nucleotide accession searches.')
    return value

def matches(query,actual):return bool(actual) and (query==actual if '.' in query else query==actual.split('.')[0])
def integer(v):
    try:return int(v) if v is not None else None
    except (TypeError,ValueError):return None

def public(source):return {k:v for k,v in source.items() if not k.startswith('_')}
def structure(n):return {'tag':n.tag,'attributes':dict(n.attrib),'text':n.text,'children':[structure(c) for c in n]}

def parse_xml(source,folder):
    """All features go to JSONL on disk; first 200 are returned for interactive display."""
    output=Path(folder)/'features.jsonl';references=[];features=[];fields={};genes=[];cds=[];total=0
    seq_length=None;stack=[];feature_depth=None;reference_depth=None;reference_count=0
    with output.open('w',encoding='utf-8') as out:
        for event,node in ET.iterparse(source['_path'],events=('start','end')):
            if event=='start':
                stack.append(node)
                if node.tag=='GBFeature':feature_depth=len(stack)
                if node.tag=='GBReference':reference_depth=len(stack)
                continue
            parent=stack[-2] if len(stack)>1 else None
            if node.tag=='GBFeature':
                q={}
                for x in node.findall('./GBFeature_quals/GBQualifier'):q.setdefault(x.findtext('GBQualifier_name'),[]).append(x.findtext('GBQualifier_value'))
                f={'type':node.findtext('GBFeature_key'),'location':node.findtext('GBFeature_location'),'qualifiers':q,'source_structure':structure(node)}
                out.write(json.dumps(f,ensure_ascii=False)+'\n');total+=1
                if len(features)<DISPLAY_FEATURES:features.append(f)
                if f['type']=='gene' and len(genes)<DISPLAY_FEATURES:genes.append(f)
                if f['type']=='CDS' and len(cds)<DISPLAY_FEATURES:cds.append(f)
                feature_depth=None
            elif node.tag=='GBReference':
                reference_count+=1
                if len(references)<1000:references.append(structure(node))
                reference_depth=None
            elif node.tag in ('GBKeyword','GBSeqid'):
                fields.setdefault('keywords' if node.tag=='GBKeyword' else 'sequence_ids',[]).append(node.text)
            elif parent is not None and parent.tag=='GBSeq':
                if node.tag=='GBSeq_sequence':
                    sequence=node.text or '';seq_length=len(sequence)
                    (Path(folder)/'sequence.fasta').write_text('>'+str(fields.get('accession-version','nucleotide'))+'\n'+'\n'.join(sequence[i:i+80].upper() for i in range(0,len(sequence),80))+'\n')
                elif not len(node) and node.text and node.text.strip():
                    fields[node.tag.removeprefix('GBSeq_')] = node.text
            if feature_depth is None and reference_depth is None:
                if parent is not None:parent.remove(node)
                node.clear()
            stack.pop()
    return {'fields':fields,'features':features,'feature_count':total,'features_shown':len(features),'genes':genes,'coding_sequences':cds,
            'references':references,'reference_count':reference_count,'reference_display_limit':1000,'sequence_length_received':seq_length,
            'display_note':'Interactive feature/gene/CDS arrays are limited to 200 entries. All feature qualifiers and original structures are in features.jsonl and the source XML. Reference display is limited to 1000; original XML is authoritative.',
            'coordinate_note':'Locations retain the source notation and refer to this nucleotide sequence. No conversion of joined, reverse-strand or uncertain positions.'}

def collect(query,folder,archive=False):
    query=accession_id(query);budget=Budget(folder);sources=[];summary={}
    es=budget.fetch('esummary',gene.EUTILS+'/esummary.fcgi',{'db':'nuccore','id':query,'retmode':'json'});sources.append(es)
    es['identity_validated']=False
    if es.get('_path') and not es.get('error'):
        try:
            payload=json.loads(Path(es['_path']).read_bytes())
            candidates=[v for v in payload.get('result',{}).values() if isinstance(v,dict) and matches(query,v.get('accessionversion')) and v.get('moltype','').lower()!='aa' and not v.get('error')]
            if len(candidates)==1:summary=candidates[0];es.update(identity_validated=True,status='validated',resolved_id=summary['accessionversion'])
            else:es.update(status='failed',error='identity_mismatch_or_missing')
        except (ValueError,AttributeError):es.update(status='failed',error='invalid_json')
    length=integer(summary.get('slen'));large=length is not None and length>MAX_SEQUENCE_LENGTH
    for name,mode in [('efetch','xml')]+([('genbank','text')] if archive else []):
        if large:
            sources.append({'name':name,'status':'skipped','reason':'large_sequence_requires_separate_bulk_or_region_download','sequence_length':length,'complete':False,'identity_validated':False});continue
        # Shared transport gives nucleotide EFetch a 64 MiB per-source disk limit.
        source=budget.fetch('efetch',gene.EUTILS+'/efetch.fcgi',{'db':'nuccore','id':query,'rettype':'gb','retmode':mode});source['name']=name;sources.append(source)
        if name=='efetch':validate(source,'nucleotide',query)
        else:
            source['identity_validated']=False
            if source.get('_path') and not source.get('error'):
                with Path(source['_path']).open('rb') as f:
                    head=f.read(8192);f.seek(max(0,source['size_bytes']-4096));tail=f.read()
                v=re.search(rb'^VERSION\s+(\S+)',head,re.M)
                actual=v[1].decode(errors='replace') if v else None
                if matches(query,actual) and tail.rstrip().endswith(b'//'):source.update(identity_validated=True,status='validated',resolved_id=actual)
                else:source.update(status='failed',error='identity_mismatch_or_missing')
    xml=next(s for s in sources if s['name']=='efetch');parsed=None;parse_error=None
    if xml.get('identity_validated'):
        try:parsed=parse_xml(xml,folder)
        except Exception as exc:parse_error=type(exc).__name__
    actual=xml.get('resolved_id') if xml.get('identity_validated') else summary.get('accessionversion')
    if not actual:return None,sources
    for s in sources:
        if s.get('identity_validated') and s.get('resolved_id')!=actual:s.update(identity_validated=False,status='failed',error='version_mismatch_between_sources')
    if es.get('identity_validated') is False:summary={}
    result={'schema_version':1,'accession':actual,'requested_accession':query,'title':(parsed or {}).get('fields',{}).get('definition') or summary.get('title'),
            'summary':summary,'record':parsed,'large_record':large,'source_status':[public(s) for s in sources],
            'normalization_error':parse_error,'fetched_at':gene.utcnow(),'from_cache':False,'cache_policy':'not_persisted',
            'scope':'One nucleotide record. Related gene, protein and taxonomy records are not separately downloaded.',
            'status':'partial' if parse_error or any(not s.get('identity_validated') for s in sources) else 'validated'}
    return result,sources

def archive_zip(query,result,sources,folder):
    archive=tempfile.TemporaryFile('w+b');entries=[]
    try:
        with ZipFile(archive,'w',ZIP_DEFLATED) as z:
            for s in sources:
                item=public(s)
                if s.get('_path'):
                    name='sources/'+s['name']+{'esummary':'.json','efetch':'.xml','genbank':'.gb'}[s['name']]
                    digest=hashlib.sha256();size=0
                    with Path(s['_path']).open('rb') as incoming,z.open(name,'w',force_zip64=True) as out:
                        while chunk:=incoming.read(65536):out.write(chunk);digest.update(chunk);size+=len(chunk)
                    if size!=s['size_bytes'] or digest.hexdigest()!=s['sha256']:raise OSError('Source integrity failure')
                    item['file']=name
                entries.append(item)
            manifest={'database':'nucleotide','requested_accession':query,'created_at':gene.utcnow(),'sources':entries,'status':result['status'] if result else 'failed',
                      'scope':'ESummary, nucleotide GBSeq XML and GenBank text; no linked-record expansion. Large sequences over 2 million bases use summary-only mode when length is known.',
                      'completeness':'not_asserted','normalization_error':result.get('normalization_error') if result else 'identity_not_validated'}
            z.writestr('manifest.json',json.dumps(manifest,indent=2));z.writestr('normalized_metadata.json',json.dumps(result,indent=2,ensure_ascii=False))
            pages=[];featurefile=Path(folder)/'features.jsonl'
            if result and result.get('record') and featurefile.exists():
                # Feature JSONL copied in chunks; HTML pages contain at most 50 features.
                with featurefile.open('rb') as inc,z.open('features.jsonl','w',force_zip64=True) as out:
                    while chunk:=inc.read(65536):out.write(chunk)
                batch=[]
                def flush():
                    n=len(pages)+1;name=f'features/page_{n:04d}.html';pages.append(name)
                    content=''.join('<section><h2>'+html.escape(f['type'] or '')+' — '+html.escape(f['location'] or '')+'</h2><pre>'+html.escape(json.dumps(f['qualifiers'],indent=2,ensure_ascii=False)[:20000])+'</pre>'+('<p>Large feature preview shortened. Complete values are in features.jsonl and source XML.</p>' if len(json.dumps(f['qualifiers'],indent=2,ensure_ascii=False))>20000 else '')+'</section>' for f in batch)
                    z.writestr(name,html_page('Nucleotide features', '<a href="../report.html">Back to report</a>'+content))
                with featurefile.open(encoding='utf-8') as inc:
                    for line in inc:
                        feature=json.loads(line)
                        if batch and sum(min(20000,len(json.dumps(f['qualifiers'],indent=2,ensure_ascii=False))) for f in batch)+min(20000,len(json.dumps(feature['qualifiers'],indent=2,ensure_ascii=False)))>100000:flush();batch=[]
                        batch.append(feature)
                        if len(batch)==50:flush();batch=[]
                if batch:flush()
                fasta=Path(folder)/'sequence.fasta'
                if fasta.exists():z.writestr('sequence.fasta',fasta.read_bytes())
            links=''.join('<li><a href="'+p+'">Feature page '+str(i)+'</a></li>' for i,p in enumerate(pages,1))
            details=(result or {}).get('record') or {};fields=details.get('fields',{})
            overview={k:v for k,v in fields.items() if k!='comment'}
            body=overview_cards(result)+'<p>Extract the entire ZIP. This report works offline. Original sources are authoritative; check failures and skips in the manifest.</p><h2>Record overview</h2><pre>'+html.escape(json.dumps(overview or (result or {}).get('summary',{}),indent=2,ensure_ascii=False))+'</pre>'
            body+='<p>Total features: '+str(details.get('feature_count','not retrieved'))+'</p><ul>'+links+'</ul><h2>Original files</h2><ul>'+''.join('<li><a href="'+s['file']+'">'+s['file']+'</a></li>' for s in entries if 'file' in s)+'</ul>'
            if pages:body+='<p><a href="features.jsonl">All features, including qualifiers and source structures</a></p>'
            if 'sequence.fasta' in z.namelist():body+='<p><a href="sequence.fasta">Nucleotide sequence FASTA</a></p>'
            if details.get('references'):
                for i in range(0,len(details['references']),25):
                    name=f'references/page_{i//25+1:04d}.html'
                    z.writestr(name,html_page('References','<a href="../report.html">Back to report</a><pre>'+html.escape(json.dumps(details['references'][i:i+25],indent=2,ensure_ascii=False))+'</pre>'))
                    body+='<p><a href="'+name+'">References '+str(i+1)+'–'+str(min(i+25,len(details['references'])))+'</a></p>'
            body+='<h2>Comments</h2><pre>'+html.escape(fields.get('comment') or '')+'</pre><h2>Manifest</h2><pre>'+html.escape(json.dumps(manifest,indent=2))+'</pre>'
            z.writestr('report.html',html_page(query,body))
        archive.seek(0);return archive
    except Exception:archive.close();raise

def overview_cards(result):
    result=result or {};record=result.get('record') or {};f=record.get('fields') or {};summary=result.get('summary') or {}
    def esc(v):
        if v is None or v=='':v='Not supplied in this record'
        if isinstance(v,(dict,list)):v=json.dumps(v,ensure_ascii=False)
        return html.escape(str(v))
    def card(title,items):
        return '<section class="card"><h2>'+esc(title)+'</h2>'+''.join('<div class="row"><span>'+esc(k)+'</span><strong>'+esc(v)+'</strong></div>' for k,v in items)+'</section>'
    def features(title,items):
        return '<section class="card"><h2>'+esc(title)+'</h2>'+(''.join('<details><summary>'+esc(x.get('type'))+' · '+esc(x.get('location'))+'</summary><pre>'+esc(x.get('qualifiers'))+'</pre></details>' for x in items) or '<p>No entries supplied in this response.</p>')+'</section>'
    source=[x for x in record.get('features',[]) if x.get('type')=='source']
    cards=card('Sequence information',[('Accession',result.get('accession')),('Molecule type',f.get('moltype',summary.get('biomol'))),('Topology',f.get('topology',summary.get('topology'))),('Length (bp)',f.get('length',summary.get('slen'))),('Keywords',f.get('keywords'))])
    cards+=card('Organism and dates',[('Organism',f.get('organism',summary.get('organism'))),('Taxonomy ID',summary.get('taxid')),('Created',f.get('create-date',summary.get('createdate'))),('Updated',f.get('update-date',summary.get('updatedate')))])
    cards+=features('Genes — overview, first 10',record.get('genes',[])[:10])+features('Coding sequences — overview, first 10',record.get('coding_sequences',[])[:10])+features('Source and location — first 10',source[:10])
    cards+=card('Record contents',[('Features',record.get('feature_count')),('References',record.get('reference_count')),('Retrieval status',result.get('status'))])
    return '<p class="subtitle">'+esc(result.get('title'))+'</p><div class="grid">'+cards+'</div><p>Overview lists are limited to ten entries. Use the feature pages and preserved sources for additional details. Linked database records are not included.</p>'

def html_page(title,body):
    css='body{font:15px system-ui;color:#14213d;background:#f5f8fc;max-width:1200px;margin:2rem auto;padding:1rem}h1{font-size:28px}h2{font-size:17px}a{color:#225ed8}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f8fafc;padding:12px;border-radius:8px}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.card{background:white;border:1px solid #dce4ef;border-radius:12px;padding:16px;min-width:0}.row{display:flex;justify-content:space-between;gap:16px;padding:9px 0;border-bottom:1px solid #eef2f7}.row span{color:#64748b}.row strong{text-align:right;overflow-wrap:anywhere;min-width:0}summary{cursor:pointer;padding:10px 0}section{margin-bottom:12px}.subtitle{color:#526078}@media(max-width:850px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:550px){.grid{grid-template-columns:1fr}}'
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+css+'</style></head><body><h1>'+html.escape(title)+'</h1>'+body+'</body></html>'

def register_nucleotide_routes(app):
    def serve(query,download=False):
        try:query=accession_id(query)
        except ValueError as exc:return jsonify(message=str(exc)),400
        if not gene._slots.acquire(blocking=False):return jsonify(message='Metadata service is busy; retry shortly.'),429
        stream=None
        try:
            with tempfile.TemporaryDirectory(prefix='ncbi-nucleotide-') as folder:
                result,sources=collect(query,folder,archive=download)
                if download:
                    if not any(s.get('_path') for s in sources):return jsonify(message='No source responses received.'),502
                    stream=archive_zip(query,result,sources,folder)
                elif result is None:return jsonify(message='No matching nucleotide record could be validated. Try the source ZIP for diagnostics.'),502
                else:return jsonify(result)
            response=send_file(stream,mimetype='application/zip',as_attachment=True,download_name=f'nucleotide_{query}_metadata.zip',max_age=0)
            response.headers['Cache-Control']='no-store';response.direct_passthrough=False;response.call_on_close(stream.close);return response
        except OSError:
            if stream:stream.close()
            return jsonify(message='Temporary storage or archive integrity failure.'),503
        finally:gene._slots.release()
    @app.get('/api/nucleotide/<accession>')
    def nucleotide_lookup(accession):return serve(accession)
    @app.get('/api/nucleotide/<accession>/download')
    def nucleotide_download(accession):return serve(accession,True)
    return nucleotide_lookup
