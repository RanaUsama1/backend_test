"""Protein source capture and display metadata; no persistent protein cache.
Uses the gene service's bounded transport and shared per-process request gate.
"""
import re
import io
import json
import html
import hashlib
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED
from flask import jsonify, send_file
from gene_service import fetch_source, as_json, utcnow, EUTILS, _slots


def accession_id(value):
    value = str(value).strip().upper()
    # RefSeq and GenBank protein accession syntax, with optional version.
    if not re.fullmatch(r'(?:[A-Z]{2}_[0-9]{5,12}|[A-Z]{3}[0-9]{5,12})(?:\.[1-9][0-9]{0,3})?', value):
        raise ValueError('Enter a protein accession, for example NP_000537.3 or XP_008660008.1. Protein names and GeneIDs are not accession searches.')
    return value


def matches(query, actual):
    return bool(actual) and (query == actual if '.' in query else query == actual.split('.')[0])


def number(value):
    try: return int(value) if value is not None else None
    except (TypeError, ValueError): return None


def xml_tree(node):
    """Lossless structural view of XML elements, including unknown/repeated fields."""
    return {'tag':node.tag, 'attributes':dict(node.attrib), 'text':node.text,
            'tail':node.tail, 'children':[xml_tree(child) for child in node]}


def normalize(query, sources):
    by_name = {s['name']:s for s in sources}
    xml = by_name['efetch']; seq = None
    if xml.get('body') is not None and not xml.get('error'):
        try:
            root = ET.fromstring(xml['body'])
            records = root.findall('GBSeq') if root.tag != 'GBSeq' else [root]
            valid = [r for r in records if matches(query, r.findtext('GBSeq_accession-version'))
                     and r.findtext('GBSeq_moltype','').upper() == 'AA']
            if len(valid) == 1: seq = valid[0]
        except ET.ParseError: xml['parse_error'] = 'invalid_xml'
    xml['identity_validated'] = seq is not None
    es = by_name['esummary']; payload = as_json(es)
    summaries = (payload or {}).get('result', {})
    candidates = [s for s in summaries.values() if isinstance(s,dict)
                  and matches(query,s.get('accessionversion')) and s.get('moltype','').lower() == 'aa'
                  and not s.get('error')]
    summary = candidates[0] if len(candidates) == 1 else {}
    # For unversioned requests, don't merge two different resolved versions.
    if seq is not None and summary.get('accessionversion') != seq.findtext('GBSeq_accession-version'):
        summary = {}
    es['identity_validated'] = bool(summary)
    gp = by_name.get('genpept')
    if gp is not None:
        body = gp.get('body') or b''
        version = re.search(rb'^VERSION\s+(\S+)',body,re.M)
        expected = seq.findtext('GBSeq_accession-version') if seq is not None else summary.get('accessionversion') or query
        gp['identity_validated'] = bool(not gp.get('error') and version and matches(expected,version[1].decode('ascii',errors='replace')))
    if seq is None and not summary:
        raise LookupError('No matching protein accession/version in usable NCBI sources.')
    def text(key): return seq.findtext('GBSeq_'+key) if seq is not None else None
    features=[]
    if seq is not None:
        for f in seq.findall('./GBSeq_feature-table/GBFeature'):
            qualifiers={}
            for q in f.findall('./GBFeature_quals/GBQualifier'):
                qualifiers.setdefault(q.findtext('GBQualifier_name'),[]).append(q.findtext('GBQualifier_value'))
            features.append({'type':f.findtext('GBFeature_key'),'location':f.findtext('GBFeature_location'),
                             'qualifiers':qualifiers,'source_structure':xml_tree(f)})
    def values(kind,key):
        return [v for f in features if f['type']==kind for v in f['qualifiers'].get(key,[]) if v is not None]
    def first(items): return items[0] if items else None
    refs=[]
    if seq is not None:
        for r in seq.findall('./GBSeq_references/GBReference'):
            refs.append({'title':r.findtext('GBReference_title'),'journal':r.findtext('GBReference_journal'),
                         'pubmed_id':r.findtext('GBReference_pubmed'),
                         'authors':[a.text for a in r.findall('./GBReference_authors/GBAuthor')],
                         'source_structure':xml_tree(r)})
    genes=list(dict.fromkeys(v.split(':',1)[1] for v in values('CDS','db_xref') if v.startswith('GeneID:')))
    taxids=list(dict.fromkeys(v.split(':',1)[1] for v in values('source','db_xref') if v.startswith('taxon:')))
    coding=[{'coded_by':v,'nucleotide_accessions':list(dict.fromkeys(re.findall(r'([A-Z][A-Z0-9_]*\.[0-9]+):',v)))} for v in values('CDS','coded_by')]
    aa=text('sequence'); actual=text('accession-version') or summary.get('accessionversion')
    mw=number(first(values('Protein','calculated_mol_wt')))
    return {'schema_version':2,'requested_accession':query,'accession':actual,'accession_version':actual,
      'title':text('definition') or summary.get('title'),'uid':summary.get('uid'),
      'organism':{'scientific_name':text('organism') or summary.get('organism'),
                  'tax_id':first(taxids) or summary.get('taxid'),'tax_ids':taxids,'lineage':text('taxonomy')},
      'sequence':{'length':number(text('length')) if seq is not None else number(summary.get('slen')),
                  'amino_acids':aa.upper() if aa else None,'molecule_type':text('moltype') or summary.get('moltype'),
                  'topology':text('topology') or summary.get('topology'),'molecular_weight':mw,
                  'molecular_weight_source':'NCBI Protein feature /calculated_mol_wt' if mw is not None else None},
      'gene':{'symbol':first(values('CDS','gene')),'gene_id':first(genes),'gene_ids':genes,
              'symbols':values('CDS','gene'),'synonyms':values('CDS','gene_synonym'),'cross_references':values('CDS','db_xref')},
      'coding_sequence':{'nucleotide_accession':first(coding[0]['nucleotide_accessions']) if coding else None},
      'coding_associations':coding,'features':features,'references':refs,'comment':text('comment'),
      'keywords':[k.text for k in seq.findall('./GBSeq_keywords/GBKeyword')] if seq is not None else [],
      'dates':{'create_date':text('create-date') or summary.get('createdate'),'update_date':text('update-date') or summary.get('updatedate')},
      'external_links':{'ncbi':f'https://www.ncbi.nlm.nih.gov/protein/{actual}',
                        'gene_link':f'https://www.ncbi.nlm.nih.gov/gene/{genes[0]}' if genes else None},
      'esummary_data':summary,'source_metadata':{'efetch_structure':xml_tree(seq) if seq is not None else None},
      'fetched_at':utcnow(),'from_cache':False,'cache_policy':'not_persisted',
      'coordinate_note':'Original NCBI feature locations preserved; protein and coding nucleotide coordinates have different units.',
      'retrieval_warnings':[{k:v for k,v in s.items() if k!='body'} for s in sources
                            if s.get('error') or s.get('parse_error') or not s.get('identity_validated')]}


def collect(query, archive=False):
    query=accession_id(query)
    sources=[fetch_source('efetch',f'{EUTILS}/efetch.fcgi',{'db':'protein','id':query,'rettype':'gp','retmode':'xml'}),
             fetch_source('esummary',f'{EUTILS}/esummary.fcgi',{'db':'protein','id':query,'retmode':'json'})]
    if archive:
        sources.append(fetch_source('genpept',f'{EUTILS}/efetch.fcgi',{'db':'protein','id':query,'rettype':'gp','retmode':'text'}))
    try: return normalize(query,sources),sources,None
    except Exception as exc: return None,sources,type(exc).__name__


def make_archive(query,result,sources,error):
    manifest={'database':'protein','schema_version':2,'requested_accession':query,'created_at':utcnow(),
              'resolved_accession':result.get('accession') if result else None,
              'normalized_status':'failed' if error else 'returned','normalization_error_type':error,
              'scope':'Returned protein EFetch XML, GenPept text and ESummary. Linked records and IPG are not fetched.',
              'completeness':'not_asserted','sources':[]}
    stream=io.BytesIO(); panels=[]
    with ZipFile(stream,'w',ZIP_DEFLATED) as z:
        for s in sources:
            entry={k:v for k,v in s.items() if k!='body'}
            if s.get('body') is not None:
                name='sources/'+s['name']+{'efetch':'.xml','esummary':'.json','genpept':'.gp'}[s['name']]
                entry.update(file=name,size_bytes=len(s['body']),sha256=hashlib.sha256(s['body']).hexdigest())
                z.writestr(name,s['body'])
                panels.append('<details><summary>'+html.escape(name)+'</summary><pre>'+html.escape(s['body'].decode('utf-8',errors='replace'))+'</pre></details>')
            manifest['sources'].append(entry)
        normalized=json.dumps(result,indent=2,ensure_ascii=False); mt=json.dumps(manifest,indent=2)
        z.writestr('manifest.json',mt);z.writestr('normalized_metadata.json',normalized)
        z.writestr('report.html','<!doctype html><meta charset="utf-8"><title>Protein metadata</title>'
          '<style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:1rem}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f5f5;padding:1rem}details{margin:1rem 0}</style>'
          '<h1>Protein '+html.escape(query)+'</h1><p>Offline source snapshot. Check source failures and identity validation below. External linked records are not included.</p>'
          '<details open><summary>Manifest</summary><pre>'+html.escape(mt)+'</pre></details>'
          '<details><summary>Display metadata</summary><pre>'+html.escape(normalized)+'</pre></details>'+''.join(panels))
    stream.seek(0);return stream


def register_protein_routes(app):
    from protein_extended import register_extended_route
    register_extended_route(app)
    def serve(query,archive=False):
        try: query=accession_id(query)
        except ValueError as exc: return jsonify(message=str(exc)),400
        if not _slots.acquire(blocking=False): return jsonify(message='Gene/protein service is busy; retry shortly.'),429
        try:
            result,sources,error=collect(query,archive=archive)
            if archive:
                if not any(s.get('body') is not None for s in sources):
                    return jsonify(message='No source bodies received. Retry later.'),502
                response=send_file(make_archive(query,result,sources,error),mimetype='application/zip',as_attachment=True,
                                   download_name=f'protein_{query}_metadata.zip',max_age=0)
            elif result is None:
                return jsonify(message='Unable to validate protein metadata. Try the source archive for diagnostics.'),502
            else: response=jsonify(result)
            response.headers['Cache-Control']='no-store';return response
        finally: _slots.release()

    @app.get('/api/protein/<accession>')
    def protein_lookup(accession): return serve(accession)

    @app.get('/api/protein/<accession>/download')
    def protein_download(accession): return serve(accession,True)

    return protein_lookup
