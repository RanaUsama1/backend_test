"""Static, offline gene overview and paginated source values. No network calls."""
import html
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROWS_PER_PAGE = 200
MAX_PAGE_CONTENT_BYTES = 128 * 1024
MAX_DERIVED_BYTES = 128 * 1024 * 1024
MAX_PAGES = 4096
VALUE_CHARS = 4000
STYLE='body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:1rem;color:#172033}a{color:#174fa3}table{border-collapse:collapse;width:100%;table-layout:fixed}td,th{border:1px solid #ddd;padding:.5rem;text-align:left;vertical-align:top;overflow-wrap:anywhere}th:first-child{width:28%}pre{white-space:pre-wrap;overflow-wrap:anywhere}nav{display:flex;gap:1rem;margin:1rem 0}.note{background:#f1f5fa;padding:1rem}li{margin:.4rem 0}'

def esc(value):return html.escape(str(value),quote=True)
def page(title,body):return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(title)+'</title><style>'+STYLE+'</style><h1>'+esc(title)+'</h1>'+body+'</html>'
def label(tag):return tag.removeprefix('Entrezgene_').replace('_',' ').replace('-',' ').capitalize()

def xml_rows(path):
    stack=[];ordinal=0
    for event,node in ET.iterparse(path,events=('start','end')):
        if event=='start':stack.append(node);continue
        text=node.text.strip() if node.text and node.text.strip() else ''
        if text or node.attrib:
            ordinal+=1
            section=stack[2].tag if len(stack)>2 else 'record'
            yield section,ordinal,' / '.join(n.tag for n in stack),text,dict(node.attrib)
        stack.pop()
        if stack:stack[-1].remove(node)
        node.clear()

def json_rows(value,path='$'):
    if isinstance(value,dict):
        if not value:yield path,'{}'
        for key,item in value.items():yield from json_rows(item,path+'.'+str(key))
    elif isinstance(value,list):
        if not value:yield path,'[]'
        for i,item in enumerate(value):yield from json_rows(item,f'{path}[{i}]')
    else:yield path,json.dumps(value,ensure_ascii=False)


def build_gene_report(z,record):
    gid=record['requested_id']
    if not re.fullmatch(r'[1-9][0-9]{0,11}',gid):raise ValueError('Invalid gene identifier')
    base=f'readable/gene_{gid}'
    sources={s['name']:s for s in record['sources'] if s.get('identity_validated') and s.get('_path')}
    overview={};summary={};warnings=[]
    for name in ('datasets','esummary'):
        if name not in sources:continue
        try:
            d=json.loads(Path(sources[name]['_path']).read_bytes())
            if name=='datasets':
                for r in d.get('reports',[]):
                    g=r.get('gene',r)
                    if str(g.get('gene_id',g.get('geneId')))==gid:overview=g;break
            else:summary=d.get('result',{}).get(gid,{})
        except (ValueError,TypeError,AttributeError):warnings.append(name+' could not be used for the readable overview.')
    states={};used=0;page_count=0;stopped=False
    def emit(name,content):
        nonlocal used,page_count
        body=content.encode('utf-8');used+=len(body);page_count+=1
        z.writestr(base+'/'+name,body)
    def flush(state,has_next):
        n=len(state['pages'])+1;filename=f"{state['slug']}-{n:04d}.html"
        paths=''.join('<li id="p'+str(i)+'"><code>'+esc(p)+'</code></li>' for p,i in state['paths'].items())
        nav='<nav><a href="index.html">Gene overview</a><a href="'+state['slug']+'.html">Section index</a>'
        if n>1:nav+='<a href="'+state['slug']+f'-{n-1:04d}.html">Previous</a>'
        if has_next:nav+='<a href="'+state['slug']+f'-{n+1:04d}.html">Next</a>'
        nav+='</nav>'
        body=nav+'<p class="note">Source values in document order, not a reconstructed biological model. Repeated XML paths can refer to different nested records. Original source files retain the exact hierarchy. Long values are split into numbered parts.</p><table><thead><tr><th>Field / source position</th><th>Value</th></tr></thead><tbody>'+''.join(state['rows'])+'</tbody></table><h2>Source paths on this page</h2><ol>'+paths+'</ol>'+nav
        emit(filename,page(state['title']+f' — page {n}',body));state['pages'].append(filename);state['rows']=[];state['paths']={};state['bytes']=0
    def add(section,ordinal,path,text,attrs):
        nonlocal stopped
        state=states.setdefault(section,{'title':label(section),'slug':re.sub(r'[^a-zA-Z0-9_-]','_',section),'rows':[],'paths':{},'pages':[],'bytes':0,'values':0})
        state['values']+=1
        text=text+('\nAttributes: '+json.dumps(attrs,ensure_ascii=False) if attrs else '')
        for start in range(0,max(1,len(text)),VALUE_CHARS):
            part=text[start:start+VALUE_CHARS];part_label=f' (part {start//VALUE_CHARS+1})' if len(text)>VALUE_CHARS else ''
            # Budget is for generated source pages; index/overview overhead is small and bounded by page count.
            if used+sum(s['bytes'] for s in states.values()) >= MAX_DERIVED_BYTES or page_count+sum(bool(s['rows']) for s in states.values()) >= MAX_PAGES:
                stopped=True;return
            addition=len(part.encode('utf-8'))*6+len(path.encode('utf-8'))+500
            if state['rows'] and (len(state['rows'])>=ROWS_PER_PAGE or state['bytes']+addition>MAX_PAGE_CONTENT_BYTES):flush(state,True)
            pid=state['paths'].setdefault(path,len(state['paths'])+1)
            row='<tr><td>'+esc(path.split(' / ')[-1].split('.')[-1])+part_label+'<br>Position '+str(ordinal)+' · <a href="#p'+str(pid)+'">source path</a></td><td><pre>'+esc(part)+'</pre></td></tr>'
            state['rows'].append(row);state['bytes']+=len(row.encode('utf-8'))+len(path.encode('utf-8'))
    # Full selected JSON overview source is also browsable; no field mapping is required.
    for name,value in [('datasets_fields',overview),('esummary_fields',summary)]:
        if value:
            for i,(path,text) in enumerate(json_rows(value),1):
                add(name,i,path,text,{})
                if stopped:break
    if 'efetch' in sources and not stopped:
        try:
            for section,ordinal,path,text,attrs in xml_rows(sources['efetch']['_path']):
                add(section,ordinal,path,text,attrs)
                if stopped:break
        except ET.ParseError:warnings.append('XML detail rendering stopped because the source could not be parsed completely.')
    elif 'efetch' not in sources:warnings.append('Validated Gene XML was unavailable; XML detail pages were not generated.')
    for state in states.values():
        if state['rows']:flush(state,False)
    if stopped:warnings.append('Readable detail limit reached. Some values are omitted from these pages; the original downloaded source remains unchanged.')
    indexes=[]
    for state in states.values():
        if not state['pages']:continue
        emit(state['slug']+'.html',page(state['title'],'<a href="index.html">Gene overview</a><p>'+str(len(state['pages']))+' pages. Open one page at a time.</p><ol>'+''.join('<li><a href="'+f+'">Page '+str(i)+'</a></li>' for i,f in enumerate(state['pages'],1))+'</ol>'))
        indexes.append('<li><a href="'+state['slug']+'.html">'+esc(state['title'])+'</a> — '+str(len(state['pages']))+' pages</li>')
    organism=summary.get('organism') or {}
    rows=[('GeneID',gid),('Symbol',overview.get('symbol') or summary.get('name')),('Description',overview.get('description') or summary.get('description')),('Organism',overview.get('taxname') or organism.get('scientificname')),('TaxID',overview.get('tax_id') or organism.get('taxid')),('Gene type',overview.get('type')),('Transcript count',overview.get('transcript_count')),('Protein count',overview.get('protein_count')),('Synonyms',overview.get('synonyms') or summary.get('otheraliases')),('Chromosomes',overview.get('chromosomes')),('Summary',overview.get('summary') or summary.get('summary'))]
    def value(v):return 'Not supplied' if v is None else json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else str(v)
    body='<nav><a href="../../report.html">Archive report</a></nav><p class="note">Readable views of already downloaded sources. No additional NCBI requests. Counts do not mean every transcript/protein record was downloaded. Coordinates and paths are preserved without interpretation.</p>'
    body+=''.join('<p class="note">'+esc(w)+'</p>' for w in warnings)
    body+='<table>'+''.join('<tr><th>'+esc(k)+'</th><td>'+esc(value(v)[:8000]+(' … See source detail pages for the remaining value.' if len(value(v))>8000 else ''))+'</td></tr>' for k,v in rows)+'</table>'
    # Annotation report values vary by source; render each exact object without guessing coordinate units.
    annotations=overview.get('annotations',[])
    body+='<h2>Genome annotations</h2>'
    for annotation in annotations[:20]:body+='<pre>'+esc(json.dumps(annotation,ensure_ascii=False,indent=2)[:3000])+(' … See Datasets detail pages for the complete annotation.' if len(json.dumps(annotation,ensure_ascii=False,indent=2))>3000 else '')+'</pre>'
    if len(annotations)>20:body+='<p>First 20 annotations shown; all values are in the Datasets detail pages and original JSON.</p>'
    body+='<h2>Detailed source sections</h2><ul>'+''.join(indexes)+'</ul><h2>Original sources</h2><ul>'
    for name,s in sources.items():
        ext='xml' if name=='efetch' else 'json';body+='<li><a href="../../gene/'+gid+'/'+name+'.'+ext+'">'+esc(name)+' ('+str(s.get('size_bytes','unknown'))+' bytes)</a></li>'
    body+='</ul><p>Opening the original large XML may be slow. The detail pages above avoid loading it all at once.</p>'
    emit('index.html',page('Gene '+gid+' — '+str(overview.get('symbol') or summary.get('name') or 'overview'),body))
    return {'gene_id':gid,'file':base+'/index.html','status':'partial' if warnings else 'generated','warnings':warnings,'generated_pages':page_count,'generated_bytes':used,'scope':'Selected overview plus paginated JSON fields and XML text/attributes. Original files are authoritative; XML hierarchy is not reconstructed.'}
