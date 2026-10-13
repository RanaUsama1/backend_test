"""Append workbook from ZIP members already written, with explicit summary fallback."""
import json
from archive_excel import build_archive_workbook, MAX_BYTES


def add_record_excel(z, database, normalized, manifest, source_entries):
    # Source entries refer to already archived files, so there is no refetch or DB call.
    source_entries = [dict(s, content_type=s.get('content_type') or ('application/json' if str(s.get('file','')).endswith('.json') else 'text/plain')) for s in source_entries]
    public_manifest = dict(manifest)
    public_manifest['sources'] = source_entries
    public_manifest.setdefault('accession', str(manifest.get('requested_accession') or manifest.get('gene_id') or 'multiple'))
    public_manifest.setdefault('retrieval_status',manifest.get('status',manifest.get('normalized_status','not_asserted')))
    captured=[];excluded=[];used=len(json.dumps(normalized,ensure_ascii=True).encode())
    try:
        for s in source_entries:
            name=s.get('file');body=None
            if name:
                size=z.getinfo(name).file_size
                if used+size<=MAX_BYTES:
                    body=z.read(name);used+=len(body)
                else:excluded.append({'file':name,'reason':'workbook_input_limit','size_bytes':size})
            captured.append((s,body))
        info={'status':'included','file':'metadata.xlsx','mode':'summary' if excluded else 'captured_sources',
              'excluded_from_excel':excluded,'scope':'Original ZIP files remain authoritative. Generated HTML/FASTA/feature derivatives are not duplicated as files in Excel.'}
        manifest['excel_export']=info;public_manifest['excel_export']=info
        try:
            workbook=build_archive_workbook(normalized,public_manifest,captured,database)
        except (ValueError, UnicodeError, RecursionError):
            # Uniform fallback keeps archive inventory plus bounded scalar record fields.
            excluded=[{'file':s['file'],'reason':'summary_workbook_only'} for s in source_entries if s.get('file')]
            info.update(mode='summary',excluded_from_excel=excluded,normalized_metadata='Only bounded top-level scalar fields; full metadata remains in ZIP sources or normalized_metadata.json where present.')
            brief={k:v for k,v in (normalized or {}).items() if not isinstance(v,(dict,list)) and len(str(v))<=2000} if isinstance(normalized,dict) else {}
            workbook=build_archive_workbook(brief,public_manifest,[(s,None) for s in source_entries],database)
        z.writestr('metadata.xlsx',workbook)
    except Exception as exc:
        manifest['excel_export']={'status':'omitted','reason':type(exc).__name__, 'scope':'Original ZIP files retained; workbook generation failed or exceeded limits.'}
