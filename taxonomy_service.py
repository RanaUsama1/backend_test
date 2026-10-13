"""Fresh taxonomy snapshots. Existing MongoDB records are neither read nor modified."""
import hashlib,html,json,re,tempfile
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import xml.etree.ElementTree as ET
from flask import jsonify,send_file
import gene_service as gene
from protein_extended import Budget

def public(s):return {k:v for k,v in s.items() if not k.startswith('_')}
def tree(n):return {'tag':n.tag,'attributes':dict(n.attrib),'text':n.text,'children':[tree(c) for c in n]}
def normalize(t):
    def text(tag):return t.findtext(tag) or None
    def code(parent,idtag,nametag):
        n=t.find(parent)
        if n is None:return None
        value=n.findtext(idtag)
        return {'id':int(value) if value and value.isdigit() else None,'name':n.findtext(nametag)}
    other=t.find('OtherNames')
    return {'tax_id':text('TaxId'),'scientific_name':text('ScientificName'),'common_name':text('OtherNames/GenbankCommonName') or text('OtherNames/CommonName'),
        'rank':text('Rank'),'division':text('Division'),'parent_tax_id':text('ParentTaxId'),
        'lineage_string':text('Lineage'),'lineage':[{'tax_id':n.findtext('TaxId'),'name':n.findtext('ScientificName'),'rank':n.findtext('Rank')} for n in t.findall('LineageEx/Taxon')],
        'genetic_code':code('GeneticCode','GCId','GCName'),'mitochondrial_genetic_code':code('MitoGeneticCode','MGCId','MGCName'),
        'synonyms':[n.text for n in t.findall('OtherNames/Synonym') if n.text],
        'other_names':tree(other) if other is not None else None,
        'dates':{k:text(tag) for k,tag in [('created','CreateDate'),('updated','UpdateDate'),('published','PubDate')]},
        'source_structure':tree(t)}

def collect(query,folder):
    budget=Budget(folder);sources=[];taxid=query if re.fullmatch(r'[1-9]\d*',query) else None
    if not taxid:
        s=budget.fetch('esearch',gene.EUTILS+'/esearch.fcgi',{'db':'taxonomy','term':query,'retmode':'json','retmax':20});sources.append(s)
        try:
            if s.get('error') or not s.get('_path'):raise ValueError('Search unavailable')

            payload = json.loads(Path(s["_path"]).read_bytes())

            if payload.get("ERROR") or payload.get("error"):
                raise ValueError("NCBI search error")

            search = payload["esearchresult"]
            ids = search["idlist"]
            count = int(search["count"])

            if not isinstance(ids, list) or count < 0:
                raise ValueError("Invalid search response")

            if search.get("ERROR") or search.get("error"):
                raise ValueError("NCBI search error")

            errors = search.get("errorlist") or {}

            # Unknown fields and other errors must not become a normal no-match.
            if any(
                value
                for key, value in errors.items()
                if key != "phrasesnotfound"
            ):
                raise ValueError("Invalid search field or other search error")

            if count == 0 and not ids:
                s["status"] = "validated"
                return None, sources, {
                    "message": "No matching taxonomy record found.",
                    "candidates": [],
                    "total_matches": 0,
                }, 404

            # Do not silently accept a search that dropped part of the query.
            if errors.get("phrasesnotfound"):
                raise ValueError("Search omitted part of the query")

            if len(ids) != min(count, 20) or any(
                not isinstance(i, str) or not i.isdigit() for i in ids
            ):
                raise ValueError("Inconsistent search results")

            s["status"] = "validated"

            if count > 1:
                return None, sources, {
                    "message": "Multiple taxonomy matches. Search using a TaxID.",
                    "candidates": ids,
                    "total_matches": count,
                }, 409

            taxid = ids[0]
      
        except (ValueError,KeyError,TypeError):return None,sources,{'message':'Taxonomy name search failed.'},502
    summary={};parsed={};parse_error=None;resolved=None
    for name in ('esummary','efetch'):
        s=budget.fetch(name,gene.EUTILS+'/'+name+'.fcgi',{'db':'taxonomy','id':taxid,'retmode':'json' if name=='esummary' else 'xml'});sources.append(s);s['identity_validated']=False
        if s.get('error') or not s.get('_path'):continue
        try:
            if name=='esummary':
                data=json.loads(Path(s['_path']).read_bytes()).get('result',{});record=data.get(taxid)
                if not isinstance(record,dict) or str(record.get('taxid',record.get('uid')))!=taxid:raise ValueError('summary_identity_mismatch')
                summary=record;s.update(status='validated',identity_validated=True,resolved_id=taxid)
            else:
                if s['size_bytes']>8*1024*1024:raise ValueError('XML exceeds 8 MiB normalization limit; source retained')
                root=ET.parse(s['_path']).getroot();records=root.findall('./Taxon')
                if len(records)!=1:raise ValueError('expected_one_taxon')
                t=records[0];actual=t.findtext('TaxId');aliases=[n.text for n in t.findall('AkaTaxIds/TaxId')]
                if actual!=taxid and taxid not in aliases:raise ValueError('XML_identity_mismatch')
                resolved=actual;s.update(status='validated',identity_validated=True,resolved_id=actual)
                try:parsed=normalize(t)
                except Exception as e:parse_error=type(e).__name__
        except (ValueError,ET.ParseError,TypeError,KeyError) as e:s.update(status='failed',error=str(e))
    result={'schema_version':2,'query':query,'requested_tax_id':taxid,'tax_id':resolved or taxid,'from_cache':False,'cache_policy':'bypassed_not_persisted','fetched_at':gene.utcnow(),
        'scientific_name':summary.get('scientificname'),'rank':summary.get('rank'),'division':summary.get('division'),'common_name':summary.get('commonname'),
        'lineage':[],'synonyms':[],'genetic_code':None,'mitochondrial_genetic_code':None,**parsed,
        'esummary_data':summary,'normalization_error':parse_error,'source_status':[public(s) for s in sources],
        'status':'validated' if all(s.get('status')=='validated' for s in sources) and parsed and not parse_error else 'partial',
        'scope':'One taxonomy record, including supplied lineage; no descendant or linked genome/gene/protein record expansion.'}
    result['external_links']={'ncbi':'https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id='+str(result['tax_id'])}
    return result,sources,None,200

def archive(result,sources,error):
    stream=tempfile.TemporaryFile()
    try:
        with ZipFile(stream,'w',ZIP_DEFLATED) as z:
            entries=[]
            for s in sources:
                entry=public(s)
                if s.get('_path'):
                    name='sources/'+s['name']+('.xml' if s['name']=='efetch' else '.json');digest=hashlib.sha256();size=0
                    with open(s['_path'],'rb') as src,z.open(name,'w') as dst:
                        while True:
                            chunk=src.read(65536)
                            if not chunk:break
                            digest.update(chunk);size+=len(chunk);dst.write(chunk)
                    if digest.hexdigest()!=s['sha256'] or size!=s['size_bytes']:raise OSError('Archive source integrity failure')
                    entry['file']=name
                    entry.setdefault('content_type', 'application/xml' if s['name']=='efetch' else 'application/json')
                entries.append(entry)
            manifest={'schema_version':2,'status':(result or {}).get('status','partial'),'sources':entries,'error':error,'scope':(result or {}).get('scope'),'completeness':'not_asserted'}
            manifest['excel_export'] = {'status':'included','file':'metadata.xlsx',
                'scope':'Taxonomy snapshot, manifest and captured source text; original bytes remain in sources/.'}
            try:
                from archive_excel import build_archive_workbook, MAX_BYTES
                total = len(json.dumps(result,ensure_ascii=True).encode('utf-8'))
                captured = []
                for source in sources:
                    body = None
                    if source.get('_path'):
                        remaining = MAX_BYTES - total
                        if remaining < 0: raise ValueError('excel_input_limit_4_MiB')
                        with open(source['_path'], 'rb') as handle:
                            body = handle.read(remaining + 1)
                        total += len(body)
                        if total > MAX_BYTES: raise ValueError('excel_input_limit_4_MiB')
                    captured.append((public(source), body))
                workbook = build_archive_workbook(result, manifest, captured, database='taxonomy')
                z.writestr('metadata.xlsx',workbook)
            except Exception as exc:
                reason = str(exc) if isinstance(exc,ValueError) and str(exc) in (
                    'excel_generation_busy','excel_input_limit_4_MiB','excel_row_limit_30000',
                    'excel_cell_limit','nesting_limit') else type(exc).__name__
                manifest['excel_export'] = {'status':'omitted','reason':reason,
                    'note':'All archived original sources remain available; no partial workbook was included.'}
            z.writestr('manifest.json',json.dumps(manifest,indent=2));z.writestr('normalized_metadata.json',json.dumps(result,indent=2,ensure_ascii=False))
            d=result or {};escape=lambda v:html.escape(str(v) if v is not None else 'Not supplied')
            body='<h1>'+escape(d.get('scientific_name') or 'Taxonomy retrieval report')+'</h1><p>Extract the whole ZIP. This overview is not a substitute for the preserved sources. External NCBI records are not included.</p><div class="grid">'
            for title,value in [('Identity',{k:d.get(k) for k in ('tax_id','requested_tax_id','rank','division','common_name')}),('Genetic codes',{k:d.get(k) for k in ('genetic_code','mitochondrial_genetic_code')}),('Dates',d.get('dates')),('Lineage',d.get('lineage')),('Other names',d.get('other_names'))]:body+='<section><h2>'+title+'</h2><pre>'+escape(json.dumps(value,indent=2,ensure_ascii=False))+'</pre></section>'
            if manifest['excel_export']['status']=='included':body+='<p><a href="metadata.xlsx">Download Excel workbook</a></p>'
            body+='</div><h2>Original sources</h2><ul>'+''.join('<li><a href="'+s['file']+'">'+s['file']+'</a></li>' for s in entries if s.get('file'))+'</ul><p><a href="normalized_metadata.json">Parsed metadata and full XML element structure</a></p><h2>Retrieval manifest</h2><pre>'+escape(json.dumps(manifest,indent=2))+'</pre>'
            z.writestr('report.html','<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Taxonomy report</title><style>body{font:15px system-ui;max-width:1200px;margin:2rem auto;padding:1rem;color:#123;background:#f6f9fc}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}section{background:white;border:1px solid #dce4ef;border-radius:12px;padding:16px}pre{white-space:pre-wrap;overflow-wrap:anywhere}h2{font-size:18px}</style>'+body+'</html>')
        stream.seek(0);return stream
    except Exception:stream.close();raise

def register_taxonomy_routes(app):
    def serve(query,download=False):
        query=query.strip()
        if not query or len(query)>200:return jsonify(message='Enter a TaxID or a name of at most 200 characters.'),400
        if not gene._slots.acquire(blocking=False):return jsonify(message='Metadata service is busy; retry shortly.'),429
        stream=None
        try:
            with tempfile.TemporaryDirectory(prefix='ncbi-taxonomy-') as folder:
                result,sources,error,status=collect(query,folder)
                if download:
                    if not any(s.get('_path') for s in sources):return jsonify(error or {'message':'No source response available.'}),502
                    stream=archive(result,sources,error)
                else:
                    if error:return jsonify(error),status
                    if not any(s.get('identity_validated') for s in sources):return jsonify(message='No matching taxonomy record was validated. Try the ZIP for diagnostics.'),502
                    return jsonify(result)
            response=send_file(stream,mimetype='application/zip',as_attachment=True,download_name='taxonomy_'+str((result or {}).get('tax_id','diagnostic'))+'_metadata.zip',max_age=0)
            response.headers['Cache-Control']='no-store';response.direct_passthrough=False;response.call_on_close(stream.close);return response
        except Exception:
            if stream:stream.close()
            app.logger.exception('Taxonomy retrieval failed');return jsonify(message='Taxonomy retrieval or archive generation failed.'),502
        finally:gene._slots.release()
    @app.get('/api/taxonomy/<name_or_id>')
    def taxonomy_lookup(name_or_id):return serve(name_or_id)
    @app.get('/api/taxonomy/<name_or_id>/download')
    def taxonomy_download(name_or_id):return serve(name_or_id,True)
    return taxonomy_lookup
