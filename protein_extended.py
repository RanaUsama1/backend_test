"""Bounded, one-hop protein source archive. No database writes or self-HTTP calls."""
import hashlib
import html
import json
import os
import re
import time
import tempfile
from pathlib import Path
import xml.etree.ElementTree as ET
from urllib.parse import urlencode
from zipfile import ZipFile, ZIP_DEFLATED
import requests
from flask import jsonify, send_file
import gene_service as gene

MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_SMALL_SOURCE_BYTES = 4 * 1024 * 1024
MAX_EMBED_BYTES = 256 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_SECONDS = 90
MAX_PER_DATABASE = 2


class Budget:
    def __init__(self, workspace):
        self.workspace = Path(workspace)
        self.deadline = time.monotonic() + MAX_SECONDS
        self.used = 0

    def fetch(self, name, url, params=None):
        public = dict(params or {})
        record = {'name':name,'url':url + ('?' + urlencode(public) if public else ''),
                  'retrieved_at':gene.utcnow(),'complete':False}
        remaining = self.deadline-time.monotonic()
        if remaining <= 0 or self.used >= MAX_TOTAL_BYTES:
            record.update(status='skipped',error='time_budget' if remaining <= 0 else 'total_byte_budget')
            return record
        params = dict(public)
        if os.getenv('NCBI_API_KEY'): params['api_key'] = os.getenv('NCBI_API_KEY')
        path = None
        # Keep JSON and protein XML bounded; large linked XML is validated incrementally.
        limit = MAX_SOURCE_BYTES if name == 'efetch' and public.get('db') in ('gene','nuccore','taxonomy') else min(MAX_SMALL_SOURCE_BYTES, MAX_SOURCE_BYTES)
        record['source_limit_bytes'] = limit
        try:
            with gene._rate_lock:
                delay=max(0,.4-(time.monotonic()-gene._last_request))
                if time.monotonic()+delay >= self.deadline:
                    record.update(status='skipped',error='time_budget');return record
                time.sleep(delay);gene._last_request=time.monotonic()
            left=max(.1,self.deadline-time.monotonic())
            with requests.get(url,params=params,stream=True,timeout=(min(5,left),min(20,left)),
                              headers={'User-Agent':'NCBI-Metadata-Search/3.1'}) as response:
                record.update(http_status=response.status_code,content_type=response.headers.get('Content-Type',''))
                digest=hashlib.sha256();size=0
                with tempfile.NamedTemporaryFile(dir=self.workspace,delete=False) as target:
                    path=Path(target.name)
                    for chunk in response.iter_content(65536):
                        self.used += len(chunk)
                        if time.monotonic() > self.deadline:
                            record.update(status='failed',error='time_budget');return record
                        if self.used > MAX_TOTAL_BYTES or size+len(chunk)>limit:
                            record.update(status='failed',error='total_byte_budget' if self.used>MAX_TOTAL_BYTES else 'source_byte_limit');return record
                        target.write(chunk);digest.update(chunk);size+=len(chunk)
                record.update(_path=str(path),size_bytes=size,complete=True,status='received',sha256=digest.hexdigest())
                if not response.ok: record.update(status='failed',error='http_error')
        except requests.RequestException as exc:
            record.update(status='failed',error=type(exc).__name__)
        except OSError:
            record.update(status='failed',error='temporary_storage_error')
        finally:
            if path is not None and '_path' not in record:
                path.unlink(missing_ok=True)
        return record


def xml_candidates(path, database):
    """Parse the entire XML, removing processed elements to bound tree memory."""
    stack=[];candidates=[];version=None;moltype=None
    for event,node in ET.iterparse(path,events=('start','end')):
        if event=='start':
            stack.append(node)
            if node.tag=='GBSeq':version=None;moltype=None
            continue
        parent=stack[-2] if len(stack)>1 else None
        if database in ('protein','nucleotide'):
            if parent is not None and parent.tag=='GBSeq':
                if node.tag=='GBSeq_accession-version':version=node.text
                elif node.tag=='GBSeq_moltype':moltype=node.text
            if node.tag=='GBSeq' and moltype and (moltype.upper()=='AA')==(database=='protein'):
                candidates.append(version)
        elif database=='gene' and node.tag=='Gene-track_geneid':candidates.append(node.text)
        elif database=='taxonomy' and node.tag=='TaxId' and len(stack)==3 and parent.tag=='Taxon':candidates.append(node.text)
        stack.pop()
        if parent is not None:parent.remove(node)
        node.clear()
    return candidates


def validate(source, database, identifier):
    """Validate returned identity, not merely HTTP status. Keep failures as evidence."""
    source['identity_validated']=False
    if source.get('error') or not source.get('_path'): return
    try:
        path=Path(source['_path']);name=source['name']
        if name=='esummary':
            result=json.loads(path.read_bytes()).get('result',{})
            records=[v for v in result.values() if isinstance(v,dict)]
            if database=='protein':
                candidates=[v.get('accessionversion') for v in records if v.get('moltype','').lower()=='aa' and not v.get('error')]
            else: candidates=[str(v.get('uid')) for v in records if not v.get('error')]
        elif name=='datasets':
            result=gene.canonical(json.loads(path.read_bytes()))
            candidates=[str(r.get('gene',r).get('gene_id')) for r in result.get('reports',[])]
        elif name=='genpept':
            candidates=[]
            with path.open('rb') as handle:
                for line in handle:
                    match=re.match(rb'^VERSION\s+(\S+)',line)
                    if match:candidates.append(match[1].decode())
        else:
            candidates=xml_candidates(path,database)
        from protein_service import matches
        valid=[c for c in candidates if c and matches(identifier,c)]
        source['identity_validated']=len(valid)==1
        if len(valid)==1: source.update(resolved_id=valid[0],status='validated')
        else: source.update(status='failed',error='identity_mismatch_or_missing')
    except (ValueError,TypeError,AttributeError,ET.ParseError,UnicodeError):
        source.update(status='failed',error='invalid_source_format')


def collect_extended(query, workspace):
    from protein_service import accession_id
    query=accession_id(query);budget=Budget(workspace);records=[];relationships=[];notes=[]
    def retrieve(database,identifier,specs):
        record={'database':database,'requested_id':identifier,'sources':[]}
        for name,url,params in specs:
            source=budget.fetch(name,url,params)
            validate(source,database,identifier)
            record['sources'].append(source)
        valid=sum(s.get('identity_validated',False) for s in record['sources'])
        record['status']='validated' if valid==len(specs) else 'partial' if valid else ('skipped' if all(s.get('status')=='skipped' for s in record['sources']) else 'failed')
        records.append(record);return record
    protein=retrieve('protein',query,[
        ('efetch',f'{gene.EUTILS}/efetch.fcgi',{'db':'protein','id':query,'rettype':'gp','retmode':'xml'}),
        ('esummary',f'{gene.EUTILS}/esummary.fcgi',{'db':'protein','id':query,'retmode':'json'}),
        ('genpept',f'{gene.EUTILS}/efetch.fcgi',{'db':'protein','id':query,'rettype':'gp','retmode':'text'})])
    source=protein['sources'][0]
    links={'gene':{},'nucleotide':{},'taxonomy':{}}
    resolved=source.get('resolved_id')
    if source.get('identity_validated'):
        root=ET.parse(source['_path']).getroot();seq=root if root.tag=='GBSeq' else next(s for s in root.findall('GBSeq') if s.findtext('GBSeq_accession-version')==resolved)
        for feature in seq.findall('./GBSeq_feature-table/GBFeature'):
            kind=feature.findtext('GBFeature_key')
            for qualifier in feature.findall('./GBFeature_quals/GBQualifier'):
                key=qualifier.findtext('GBQualifier_name');value=qualifier.findtext('GBQualifier_value') or ''
                if kind=='CDS' and key=='db_xref' and re.fullmatch(r'GeneID:[1-9][0-9]*',value):
                    links['gene'].setdefault(value.split(':')[1],[]).append(value)
                elif kind=='source' and key=='db_xref' and re.fullmatch(r'taxon:[1-9][0-9]*',value):
                    links['taxonomy'].setdefault(value.split(':')[1],[]).append(value)
                elif kind=='CDS' and key=='coded_by':
                    accessions=re.findall(r'([A-Z][A-Z0-9_]*\.[0-9]+):',value)
                    if not accessions:notes.append({'reason':'unresolved_coded_by','value':value})
                    for acc in accessions:links['nucleotide'].setdefault(acc,[]).append(value)
        discovery='validated_protein_xml_qualifiers'
    else:
        discovery='unavailable'
        notes.append({'reason':'protein_xml_not_validated','message':'Links cannot be reliably discovered; no related IDs were guessed.'})
    # Prevent silently combining different versions for an unversioned query.
    if resolved:
        for s in protein['sources'][1:]:
            if s.get('identity_validated') and s.get('resolved_id')!=resolved:
                s.update(identity_validated=False,status='failed',error='version_mismatch_between_sources')
        protein['status']='validated' if all(s.get('identity_validated') for s in protein['sources']) else 'partial'
    for database,targets in links.items():
        if not targets:notes.append({'database':database,'reason':'no_direct_identifier_in_validated_protein_record' if resolved else 'discovery_unavailable'})
        for i,(identifier,evidence) in enumerate(targets.items()):
            relationship={'from':{'database':'protein','id':resolved or query},'to':{'database':database,'id':identifier},
                          'evidence':list(dict.fromkeys(evidence)),'discovered_in':'protein EFetch XML'}
            relationships.append(relationship)
            if i >= MAX_PER_DATABASE:
                record={'database':database,'requested_id':identifier,'status':'skipped','reason':'record_count_limit','sources':[]}
                records.append(record);relationship['status']='skipped';continue
            if database=='gene':
                specs=[('datasets',f'{gene.API}/gene/id/{identifier}/dataset_report',{}),
                       ('esummary',f'{gene.EUTILS}/esummary.fcgi',{'db':'gene','id':identifier,'retmode':'json'}),
                       ('efetch',f'{gene.EUTILS}/efetch.fcgi',{'db':'gene','id':identifier,'retmode':'xml'})]
            else:
                params={'db':'nuccore' if database=='nucleotide' else 'taxonomy','id':identifier,'retmode':'xml'}
                if database=='nucleotide':params['rettype']='gb'
                specs=[('efetch',f'{gene.EUTILS}/efetch.fcgi',params)]
            record=retrieve(database,identifier,specs)
            relationship['status']=record['status']
    manifest={'schema_version':2,'database':'protein','archive_type':'extended_direct_links',
              'requested_accession':query,'resolved_accession':resolved,'created_at':gene.utcnow(),
              'scope':'Protein XML, ESummary and GenPept; direct CDS GeneIDs (Datasets, ESummary, EFetch), coded_by nucleotide accessions (GBSeq XML including sequence when supplied), and source TaxIDs (taxonomy XML).',
              'excluded':'No recursive expansion, ELink discovery, IPG, PubMed, structure or domain downloads. Direct identifiers only; this is not every relationship in NCBI.',
              'completeness':'not_asserted','link_discovery':discovery,'notes':notes,
              'limits':{'max_records_per_linked_database':MAX_PER_DATABASE,'max_source_bytes':MAX_SOURCE_BYTES,'max_total_download_bytes':MAX_TOTAL_BYTES,'max_small_source_bytes':MAX_SMALL_SOURCE_BYTES,'max_embedded_source_bytes':MAX_EMBED_BYTES,
                        'request_scheduling_budget_seconds':MAX_SECONDS,'time_note':'Best-effort deadline; an in-flight socket operation and ZIP creation may finish after it.'},
              'transferred_bytes':budget.used,
              'status':'partial' if discovery=='unavailable' or any(r['status']!='validated' for r in records) or any(n.get('reason')=='unresolved_coded_by' for n in notes) else 'all_discovered_records_validated'}
    return manifest,records,relationships


def make_extended_archive(manifest,records,relationships):
    # Anonymous disk file: released on close; never put full ZIP in a BytesIO.
    stream=tempfile.TemporaryFile(mode='w+b');entries=[]
    try:
        with ZipFile(stream,'w',ZIP_DEFLATED) as z:
            for record in records:
                entry={k:v for k,v in record.items() if k!='sources'};entry['sources']=[]
                for source in record['sources']:
                    public={k:v for k,v in source.items() if not k.startswith('_')}
                    if source.get('_path'):
                        extension={'efetch':'xml','datasets':'json','esummary':'json','genpept':'gp'}[source['name']]
                        filename=f"{record['database']}/{record['requested_id']}/{source['name']}.{extension}"
                        public.update(file=filename)
                        # Hash the bytes actually written to ZIP, not just the network chunks.
                        digest=hashlib.sha256();size=0
                        with Path(source['_path']).open('rb') as incoming, z.open(filename,'w',force_zip64=True) as outgoing:
                            while True:
                                chunk=incoming.read(65536)
                                if not chunk:break
                                outgoing.write(chunk);digest.update(chunk);size+=len(chunk)
                        if size!=source['size_bytes'] or digest.hexdigest()!=source['sha256']:
                            raise OSError('Source integrity check failed during archive creation')
                    entry['sources'].append(public)
                entries.append(entry)
            from gene_offline_report import build_gene_report
            readable=[]
            for record in records:
                if record['database']=='gene':
                    try:readable.append(build_gene_report(z,record))
                    except Exception as exc:
                        readable.append({'gene_id':record['requested_id'],'status':'failed','error':type(exc).__name__})
            manifest=dict(manifest,records=entries,readable_reports=readable)
            from record_excel import add_record_excel
            add_record_excel(z,'protein_extended',{'records':entries,'relationships':relationships},manifest,[s for r in entries for s in r['sources']])
            mt=json.dumps(manifest,indent=2);rt=json.dumps(relationships,indent=2)
            z.writestr('manifest.json',mt);z.writestr('relationships.json',rt)
            with z.open('report.html','w') as out:
                def write(value):out.write(value.encode('utf-8'))
                write('<!doctype html><meta charset="utf-8"><title>Extended protein metadata</title><style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:1rem}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f6f6;padding:1rem}details{margin:1rem 0}</style><h1>Extended protein metadata</h1><p>Extract the entire ZIP before opening this report. Small sources are embedded below. Large sources are preserved in full as linked files beside this report. Keep the extracted folders together for offline viewing. Check the manifest for failures and omissions.</p>')
                write('<h2>Readable gene reports</h2><ul>')
                for item in readable:
                    if item.get('file'):
                        write('<li><a href="'+html.escape(item['file'],quote=True)+'">Gene '+html.escape(item['gene_id'])+' — overview and detail pages</a> ('+html.escape(item['status'])+')</li>')
                    else:write('<li>Gene '+html.escape(item['gene_id'])+': readable report unavailable; original sources remain below.</li>')
                write('</ul>')
                write('<details open><summary>Manifest</summary><pre>'+html.escape(mt)+'</pre></details>')
                write('<details><summary>Relationships</summary><pre>'+html.escape(rt)+'</pre></details>')
                for record,entry in zip(records,entries):
                    for source,public in zip(record['sources'],entry['sources']):
                        if not source.get('_path'):continue
                        filename=public['file']
                        write('<details><summary>'+html.escape(filename)+'</summary>')
                        write('<p><a href="'+html.escape(filename,quote=True)+'">Open full source file</a> ('+str(public['size_bytes'])+' bytes)</p>')
                        if public['size_bytes']<=MAX_EMBED_BYTES:
                            write('<pre>'+html.escape(Path(source['_path']).read_text(encoding='utf-8',errors='replace'))+'</pre>')
                        else:
                            write('<p>The full file is included in the ZIP. It is not duplicated inside this HTML report because of its size.</p>')
                        write('</details>')
        stream.seek(0);return stream
    except Exception:
        stream.close();raise


def register_extended_route(app):
    @app.get('/api/protein/<accession>/download/extended')
    def protein_extended_download(accession):
        from protein_service import accession_id
        try: accession=accession_id(accession)
        except ValueError as exc:return jsonify(message=str(exc)),400
        if not gene._slots.acquire(blocking=False):return jsonify(message='Gene/protein service is busy; retry shortly.'),429
        archive=None
        try:
            with tempfile.TemporaryDirectory(prefix='ncbi-protein-') as workspace:
                manifest,records,relationships=collect_extended(accession,workspace)
                if not any(s.get('_path') for r in records for s in r['sources']):
                    return jsonify(message='No complete source responses received. Retry later; check available temporary storage.'),502
                archive=make_extended_archive(manifest,records,relationships)
            # All individual source files are now cleaned up; only the ZIP stays open.
            response=send_file(archive,mimetype='application/zip',as_attachment=True,
                               download_name=f'protein_{accession}_extended.zip',max_age=0)
            response.headers['Cache-Control']='no-store'
            response.direct_passthrough=False
            response.call_on_close(archive.close)
            return response
        except OSError:
            if archive is not None:archive.close()
            return jsonify(message='Temporary storage unavailable while creating the archive.'),503
        except Exception:
            if archive is not None:archive.close()
            raise
        finally:gene._slots.release()
