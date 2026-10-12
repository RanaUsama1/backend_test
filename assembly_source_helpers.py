"""Source-specific metadata parsers; no network calls."""
import xml.etree.ElementTree as ET

def number(value):
    try:return int(value)
    except (ValueError,TypeError):
        try:return float(value)
        except (ValueError,TypeError):return value

def parse_ftp_stats_file(stats_text):
    stats={};headers={};all_stats={}
    for line in (stats_text or '').splitlines():
        if line.startswith('# '):
            key,sep,value=line[2:].partition(':')
            if sep:headers[key.strip()]=value.strip()
        if not line.strip() or line.startswith('#'):continue
        parts=[p.strip() for p in line.split('\t')]
        if len(parts)!=6:continue
        key='_'.join(p.lower().replace(' ','_').replace('-','_') for p in parts[:5]);stats[key]=number(parts[5])
        if all(p.lower()=='all' for p in parts[:4]):all_stats[parts[4].lower().replace('-','_')]=number(parts[5])
    stats['all_summary']=all_stats;stats['headers']=headers
    return stats

def summary_stats(summary):
    root=ET.fromstring('<root>'+(summary.get('meta') or '')+'</root>')
    return {n.get('category').replace('-','_'):number(n.text) for n in root.findall('./Stats/Stat') if n.get('sequence_tag')=='all' and n.get('category')}

def parse_ena_xml(content,accession):
    root=ET.fromstring(content)
    for n in root.iter():n.tag=n.tag.split('}')[-1]
    records=root.findall('./ASSEMBLY')
    if len(records)!=1 or records[0].get('accession')!=accession:raise ValueError('ENA assembly identity mismatch')
    a=records[0];attrs={n.findtext('TAG'):n.findtext('VALUE') for n in a.findall('ASSEMBLY_ATTRIBUTES/ASSEMBLY_ATTRIBUTE')}
    return {'accession':accession,'description':a.findtext('DESCRIPTION'),'assembly_name':a.findtext('NAME'),'assembly_level':a.findtext('ASSEMBLY_LEVEL'),
      'submission_date':a.get('submission_date'),'last_updated':a.get('last_updated') or attrs.get('ENA-LAST-UPDATED'),
      'tax_id':a.findtext('TAXON/TAXON_ID'),'scientific_name':a.findtext('TAXON/SCIENTIFIC_NAME'),'strain':a.findtext('TAXON/STRAIN'),
      'sample_accession':a.findtext('SAMPLE_REF/IDENTIFIERS/PRIMARY_ID'),'study_accession':a.findtext('STUDY_REF/IDENTIFIERS/PRIMARY_ID'),
      'genome_representation':a.findtext('GENOME_REPRESENTATION'),'coverage':a.findtext('COVERAGE'),'attributes':attrs,
      'chromosomes':[{'accession':c.get('accession'),'name':c.findtext('NAME'),'type':c.findtext('TYPE')} for c in a.findall('CHROMOSOMES/CHROMOSOME')]}


def exact_stats_url(accession, summary):
    """Use only an NCBI directory explicitly naming the requested version."""
    from urllib.parse import urlsplit
    key = 'ftppath_refseq' if accession.startswith('GCF_') else 'ftppath_genbank'
    base = (summary or {}).get(key) or ''
    u = urlsplit(base)
    name = u.path.rstrip('/').rsplit('/', 1)[-1]
    if u.hostname != 'ftp.ncbi.nlm.nih.gov' or not name.startswith(accession + '_'):
        return None
    return 'https://ftp.ncbi.nlm.nih.gov' + u.path.rstrip('/') + '/' + name + '_assembly_stats.txt'
