"""On-demand gene metadata and raw archives. No persistent cache or bulk import."""
import hashlib
import html
import io
import json
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlencode, quote
from zipfile import ZipFile, ZIP_DEFLATED
import requests
from flask import jsonify, request, send_file

API = 'https://api.ncbi.nlm.nih.gov/datasets/v2'
EUTILS = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'
# One process: max 1 active gene operation, shared start-rate for NCBI requests.
_slots = threading.BoundedSemaphore(1)
_rate_lock = threading.Lock()
_last_request = 0.0
MAX_SOURCE_BYTES = 12 * 1024 * 1024


def utcnow(): return datetime.now(timezone.utc).isoformat()


def gene_id(value):
    value = str(value).strip()
    if not re.fullmatch(r'[1-9][0-9]{0,11}', value):
        raise ValueError('Enter a positive numeric NCBI GeneID.')
    return value


def canonical(value):
    if isinstance(value, dict):
        return {re.sub(r'(?<!^)(?=[A-Z])', '_', k).lower():canonical(v) for k,v in value.items()}
    if isinstance(value, list): return [canonical(v) for v in value]
    return value


def count(value):
    if value is None or isinstance(value, bool): return None
    return int(value) if re.fullmatch(r'\d+', str(value)) else None


def fetch_source(name, url, params=None):
    """Retain entity bytes BEFORE parsing; bounded responses fail explicitly."""
    global _last_request
    public_params = dict(params or {})
    public_url = url + ('?' + urlencode(public_params) if public_params else '')
    params = dict(public_params)
    key = os.getenv('NCBI_API_KEY')
    if key: params['api_key'] = key
    record = {'name':name, 'url':public_url, 'retrieved_at':utcnow(), 'body':None}
    try:
        with _rate_lock:
            time.sleep(max(0, .4 - (time.monotonic() - _last_request)))
            _last_request = time.monotonic()
        with requests.get(url, params=params, stream=True, timeout=(8, 20),
                          headers={'User-Agent':'NCBI-Metadata-Search/2.0'}) as response:
            record.update(http_status=response.status_code, content_type=response.headers.get('Content-Type',''))
            body = bytearray()
            body_started = time.monotonic()
            for chunk in response.iter_content(65536):
                if time.monotonic() - body_started > 25:
                    record.update(error='response_time_limit', complete=False)
                    return record
                body.extend(chunk)
                if len(body) > MAX_SOURCE_BYTES:
                    record.update(error='response_size_limit', complete=False)
                    return record  # Never present a truncated body as complete.
            record['body'] = bytes(body)
            record['complete'] = True
            record['sha256'] = hashlib.sha256(body).hexdigest()
            if not response.ok: record['error'] = 'http_error'
    except requests.RequestException as exc:
        record.update(error=type(exc).__name__, complete=False)
    return record


def as_json(record):
    if record.get('error') or record.get('body') is None: return None
    try: return json.loads(record['body'])
    except (ValueError, UnicodeError):
        record['parse_error'] = 'invalid_json'
        return None


def normalize(gid, sources):
    ds = as_json(sources[0])
    es = as_json(sources[1])
    gene = {}
    for report in (ds or {}).get('reports', []):
        candidate = canonical(report.get('gene', report))
        if str(candidate.get('gene_id')) == gid:
            gene = candidate
            break
    summary = (es or {}).get('result', {}).get(gid, {})
    if str(summary.get('uid')) != gid or summary.get('error'): summary = {}
    # Capture identity for XML without trying to flatten its full heterogeneous tree.
    xml_identity = None
    try:
        if sources[2].get('body') and not sources[2].get('error'):
            root = ET.fromstring(sources[2]['body'])
            xml_identity = root.findtext('.//Gene-track_geneid')
            sources[2]['record_gene_id'] = xml_identity
    except ET.ParseError:
        sources[2]['parse_error'] = 'invalid_xml'
    sources[0]['identity_validated'] = bool(gene)
    sources[1]['identity_validated'] = bool(summary)
    sources[2]['identity_validated'] = xml_identity == gid
    if not gene and not summary:
        raise LookupError('No matching GeneID was validated in Datasets or ESummary. See source archive for upstream details.')
    organism = summary.get('organism') or {}
    # Preserve complete Datasets gene structure plus standardized display fields.
    result = dict(gene)
    result.update(gene_id=gid,
        symbol=gene.get('symbol') or summary.get('name'),
        description=gene.get('description') or summary.get('description'),
        organism={'scientific_name':gene.get('taxname') or organism.get('scientificname'),
                  'common_name':gene.get('common_name') or organism.get('commonname'),
                  'tax_id':str(gene.get('tax_id') or organism.get('taxid') or summary.get('taxid') or '') or None},
        gene_type=gene.get('type') or summary.get('genetypelist') or summary.get('type'),
        transcript_count=count(gene.get('transcript_count')),
        protein_count=count(gene.get('protein_count')),
        annotations=gene.get('annotations', []),
        gene_ontology=gene.get('gene_ontology'),
        summary=gene.get('summary') or summary.get('summary'),
        synonyms=gene.get('synonyms') or [x.strip() for x in summary.get('otheraliases','').split(',') if x.strip()],
        chromosomes=gene.get('chromosomes') or ([summary['chromosome']] if summary.get('chromosome') else []),
        record_status=summary.get('status'), current_gene_id=summary.get('currentid'),
        fetched_at=utcnow(), from_cache=False, cache_policy='not_persisted', schema_version=1,
        source_metadata={'datasets_gene':gene or None,'esummary':summary or None},
        coordinate_note='Source coordinates retained without conversion; assembly and sequence accessions remain attached. No assembly is implicitly selected.')
    result['retrieval_warnings'] = [{k:v for k,v in source.items() if k!='body'} for source in sources
                                    if source.get('error') or source.get('parse_error') or not source.get('identity_validated')]
    return result


def collect(gid):
    gid = gene_id(gid)
    # Independent requests: a failure in one source does not skip later sources.
    sources = [fetch_source('datasets', f'{API}/gene/id/{gid}/dataset_report'),
               fetch_source('esummary', f'{EUTILS}/esummary.fcgi', {'db':'gene','id':gid,'retmode':'json'}),
               fetch_source('efetch', f'{EUTILS}/efetch.fcgi', {'db':'gene','id':gid,'retmode':'xml'})]
    result = None
    error = None
    try: result = normalize(gid, sources)
    except Exception as exc: error = type(exc).__name__
    return result, sources, error


def make_archive(gid, result, sources, error):
    manifest = {'schema_version':1, 'database':'gene','gene_id':gid,'created_at':utcnow(),
                'normalized_status':'failed' if error else 'returned','normalization_error_type':error,
                'completeness':'not_asserted',
                'scope':'Datasets gene report, Gene ESummary and Gene EFetch XML for the requested GeneID. Not all linked nucleotide/protein records or sequences.',
                'sources':[]}
    stream = io.BytesIO()
    panels=[]
    with ZipFile(stream,'w',ZIP_DEFLATED) as z:
        for s in sources:
            entry={k:v for k,v in s.items() if k!='body'}
            if s.get('body') is not None:
                suffix='xml' if s['name']=='efetch' else 'json'
                filename=f"sources/{s['name']}.{suffix}"
                entry.update(file=filename,size_bytes=len(s['body']))
                z.writestr(filename,s['body'])
                panels.append('<details><summary>'+html.escape(s['name'])+'</summary><pre>'+
                              html.escape(s['body'].decode('utf-8',errors='replace'))+'</pre></details>')
            manifest['sources'].append(entry)
        normalized=json.dumps(result,indent=2,ensure_ascii=False)
        manifest_text=json.dumps(manifest,indent=2)
        z.writestr('normalized_metadata.json',normalized)
        z.writestr('manifest.json',manifest_text)
        z.writestr('report.html','<!doctype html><html lang="en"><meta charset="utf-8"><title>Gene '+gid+'</title>'
          '<style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:1rem}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f4f4;padding:1rem}details{margin:1rem 0}</style>'
          '<h1>NCBI Gene '+gid+'</h1><p>Offline source snapshot. Check the manifest for failed, oversized or mismatched sources.</p>'
          '<details><summary>Manifest</summary><pre>'+html.escape(manifest_text)+'</pre></details>'
          '<details><summary>Normalized metadata</summary><pre>'+html.escape(normalized)+'</pre></details>'+''.join(panels)+'</html>')
    stream.seek(0)
    return stream


def register_gene_routes(app):
    def failure(message, status=502): return jsonify(message=message), status

    @app.get('/api/gene/id/<gid>')
    def gene_lookup(gid):
        try: gid=gene_id(gid)
        except ValueError as exc: return failure(str(exc),400)
        if not _slots.acquire(blocking=False): return failure('Gene service is busy. Try again shortly.',429)
        try:
            result, sources, error=collect(gid)
            if result is None:
                return failure('Unable to validate gene metadata. The source download may contain diagnostic responses.',502)
            return jsonify(result)
        finally: _slots.release()

    @app.get('/api/gene/id/<gid>/download')
    def gene_download(gid):
        try: gid=gene_id(gid)
        except ValueError as exc: return failure(str(exc),400)
        if not _slots.acquire(blocking=False): return failure('Gene service is busy. Try again shortly.',429)
        try:
            result,sources,error=collect(gid)
            if not any(s.get('body') is not None for s in sources):
                return failure('No source bodies were received. Retry later or check source size limits.',502)
            response=send_file(make_archive(gid,result,sources,error),mimetype='application/zip',
                               as_attachment=True,download_name=f'gene_{gid}_metadata.zip',max_age=0)
            response.headers['Cache-Control']='no-store'
            return response
        finally: _slots.release()

    @app.get('/api/gene/symbol/<path:symbol>')
    def gene_symbol(symbol):
        organism=request.args.get('organism','').strip()
        symbol=symbol.strip()
        if not symbol or len(symbol)>120 or not organism or len(organism)>120:
            return failure('Provide a gene symbol and an organism name or numeric TaxID.',400)
        # Quote user input; prevent it from changing the search field expression.
        if any(c in symbol+organism for c in '\"[]\n\r'):
            return failure('Use a plain symbol and organism name or numeric TaxID.',400)
        term=f'"{symbol}"[Gene Name] AND '+(f'txid{organism}[Organism:noexp]' if organism.isdigit() else f'"{organism}"[Organism]')
        if not _slots.acquire(blocking=False): return failure('Gene service is busy. Try again shortly.',429)
        try:
            source=fetch_source('search',f'{EUTILS}/esearch.fcgi',{'db':'gene','term':term,'retmode':'json','retmax':20})
            data=as_json(source)
            if not data or 'esearchresult' not in data: return failure('NCBI gene search failed.')
            ids=data['esearchresult'].get('idlist',[])
            total=int(data['esearchresult'].get('count',0))
            candidates=[]
            if ids:
                source=fetch_source('candidates',f'{EUTILS}/esummary.fcgi',{'db':'gene','id':','.join(ids),'retmode':'json'})
                summaries=(as_json(source) or {}).get('result',{})
                for gid in ids:
                    s=summaries.get(gid,{})
                    candidates.append({'gene_id':gid,'symbol':s.get('name'),'description':s.get('description'),
                        'organism':s.get('organism'),'status':s.get('status'),'current_gene_id':s.get('currentid')})
            return jsonify(query=symbol,organism_query=organism,total_matches=total,
                           candidates=candidates,truncated=total>len(candidates),
                           message='Select a GeneID. No ambiguous match is chosen automatically.')
        finally: _slots.release()

    return gene_lookup, gene_symbol
