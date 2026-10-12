from assembly_source_helpers import summary_stats
"""Keep source-specific statistics separate; provide legacy frontend aliases."""

STAT_KEYS = ('genome_size_bp', 'genome_size_ungapped_bp', 'gc_content', 'gc_count',
             'atgc_count', 'contig_n50', 'contig_l50', 'scaffold_n50', 'scaffold_l50',
             'number_of_contigs', 'number_of_scaffolds', 'number_of_chromosomes',
             'number_of_component_sequences', 'gaps_between_scaffolds')


def first(*values):
    return next((v for v in values if v is not None and v != ''), None)


def finalize_assembly(result, parsed, summary, ftp, warnings, schema_version, ena_accession):
    summary = summary or {}
    parsed = parsed or {}
    ftp = ftp or {}
    if not parsed and summary.get('assemblyaccession') != result['accession']:
        raise LookupError('No identity-validated assembly record was retrieved')

    # Preserve the entire statistics payload for each source; never fill a missing
    # Datasets statistic with a statistic from a different assembly scope.
    ftp_all = ftp.get('all_summary') or {}
    ftp_map = {
        'genome_size_bp': 'total_length', 'genome_size_ungapped_bp': 'ungapped_length',
        'contig_n50': 'contig_n50', 'contig_l50': 'contig_l50',
        'scaffold_n50': 'scaffold_n50', 'scaffold_l50': 'scaffold_l50',
        'number_of_contigs': 'contig_count', 'number_of_scaffolds': 'scaffold_count',
        'number_of_chromosomes': 'chromosome_count',
        'number_of_component_sequences': 'component_count',
        'gc_content': 'gc_perc', 'gc_count': 'gc_count', 'atgc_count': 'atgc_count',
        'gaps_between_scaffolds': 'gaps_between_scaffolds'}
    if parsed:
        selected = {k: parsed.get('genome_size_ungapped' if k == 'genome_size_ungapped_bp' else k)
                    for k in STAT_KEYS}
        source = 'NCBI Datasets assembly_stats'
    elif ftp_all:
        selected = {k: ftp_all.get(ftp_map[k]) for k in STAT_KEYS}
        source = 'NCBI assembly_stats.txt all/all'
    else:
        selected = dict.fromkeys(STAT_KEYS)
        source = 'unavailable'
    # Only use ESummary stats for the same exact accession, with explicit provenance.
    try:
        meta = summary_stats(summary) if summary.get('assemblyaccession') == result['accession'] else {}
    except Exception:
        meta = {}
        warnings.append({'source':'esummary_meta','error_type':'invalid_xml'})
    provenance = {k:source for k,v in selected.items() if v is not None}
    if not parsed:
        for key, stat in ftp_map.items():
            if selected[key] is None and meta.get(stat) is not None:
                selected[key] = meta[stat]
                provenance[key] = 'NCBI ESummary meta: sequence_tag=all, exact accession'
    result.update(selected)
    result['statistics_field_sources'] = provenance
    result['esummary_all_statistics'] = meta
    if result['gc_content'] is None and result['gc_count'] is not None and result['atgc_count']:
        result['gc_content'] = 100 * result['gc_count'] / result['atgc_count']
    for raw, human in [('genome_size_bp', 'genome_size_mb'),
                       ('genome_size_ungapped_bp', 'genome_size_ungapped_mb')]:
        result[human] = round(result[raw] / 1_000_000, 2) if result[raw] is not None else None
    result['statistics_source'] = source + ('; ESummary all-sequence fallbacks (see statistics_field_sources)' if any('ESummary' in v for v in provenance.values()) else '')
    result['statistics_by_source'] = {
        'datasets': {k: parsed.get('genome_size_ungapped' if k == 'genome_size_ungapped_bp' else k)
                     for k in STAT_KEYS} if parsed else None,
        'ftp_all_units': ftp_all,
        'ftp_contextual_statistics': {k:v for k,v in ftp.items() if k not in ('all_summary','headers')}}
    result['statistics_scope_note'] = ('Datasets and FTP all-unit statistics are kept separate. '
        'Do not combine their counts or lengths; assembly units and organelle inclusion can differ.')
    for key in ('cultivar', 'organelle_info', 'busco', 'paired_assembly', 'biosample_metadata'):
        result[key] = parsed.get(key)
    result['paired_accession'] = first(parsed.get('paired_accession'),
                                       (summary.get('synonym') or {}).get('genbank')
                                       if result['accession'].startswith('GCF_') else
                                       (summary.get('synonym') or {}).get('refseq'))
    result['paired_status'] = (parsed.get('paired_assembly') or {}).get('status')
    result['ena_url'] = f'https://www.ebi.ac.uk/ena/browser/view/{ena_accession}' if ena_accession else None
    result['annotation_release_date'] = result.get('annotation_date')
    result['wgs_project'] = first(result.get('wgs_project'), summary.get('wgs'))
    result['wgs_project_accession'] = result.get('wgs_project')
    projects = summary.get('gb_bioprojects') or []
    result['bioproject_accession'] = first(result.get('bioproject_accession'),
                                          projects[0].get('bioprojectaccn') if projects else None)
    result['bioprojects_by_source'] = {'genbank': projects, 'refseq': summary.get('rs_bioprojects') or []}

    headers = ftp.get('headers') or {}
    result['assembly_report_headers'] = headers
    if headers.get('RefSeq assembly accession' if result['accession'].startswith('GCF_') else 'GenBank assembly accession') != result['accession']:
        headers = {}  # Do not promote headers of an unrelated assembly.
    field_sources = {}
    def fill(key, value, origin):
        if result.get(key) is None or result.get(key) == '':
            result[key] = value
            if value is not None:field_sources[key]=origin
    fill('assembly_type',summary.get('assemblytype'),'ESummary assemblytype')
    fill('assembly_method',headers.get('Assembly method'),'assembly_stats header')
    fill('sequencing_technology',headers.get('Sequencing technology'),'assembly_stats header')
    infra={x.get('sub_type'):x.get('sub_value') for x in (summary.get('biosource') or {}).get('infraspecieslist',[])}
    fill('strain',infra.get('strain'),'ESummary biosource')
    fill('ecotype',infra.get('ecotype'),'ESummary biosource')
    fill('current_accession',summary.get('latestaccession'),'ESummary latestaccession')
    result['latest_accession']=summary.get('latestaccession')
    result['assembly_properties']=summary.get('propertylist') or []
    result['is_replaced']='replaced' in result['assembly_properties']
    result['version_notice']=('Requested version is replaced; latest reported accession: '+str(result['latest_accession'])) if result['is_replaced'] else None
    result['paired_similarity']=(summary.get('synonym') or {}).get('similarity')
    result['release_dates_by_source']={'genbank':summary.get('asmreleasedate_genbank'),'refseq':summary.get('asmreleasedate_refseq'),'sequence':summary.get('seqreleasedate')}
    specific_date=summary.get('asmreleasedate_refseq' if result['accession'].startswith('GCF_') else 'asmreleasedate_genbank')
    if specific_date:
        result['release_date']=specific_date;field_sources['release_date']='ESummary release date for requested database'
    fill('busco',summary.get('busco'),'ESummary busco (original ratios retained)')
    result['annotation_report_url']=summary.get('annotrpturl')
    result['field_sources']=field_sources

    # Standardize BioSample while retaining original Datasets object separately.
    bio = dict(result.get('biosample_data') or {})
    ds = parsed.get('biosample_metadata') or {}
    attrs = {a['name']: a.get('value') for a in ds.get('attributes', []) if a.get('name')}
    attrs.update(bio.get('attributes') or {})
    description = ds.get('description') or {}
    bio['accession'] = first(bio.get('accession'), ds.get('accession'), result.get('biosample_accession'))
    bio['description'] = first(bio.get('description'), description.get('comment'))
    bio['submitter'] = first(bio.get('submitter'), (ds.get('owner') or {}).get('name'))
    # Detailed Datasets/XML timestamps differ from ESummary's summary date.
    bio['esummary_submission_date'] = bio.get('submission_date')
    bio['submission_date'] = first(ds.get('submission_date'), bio.get('submission_date'))
    bio['publication_date'] = first(ds.get('publication_date'), bio.get('publication_date'))
    bio['modification_date'] = first(ds.get('last_updated'), bio.get('modification_date'))
    bio['attributes'] = attrs
    result['biosample_data'] = bio
    result['common_name'] = first(result.get('common_name'), attrs.get('common name'))
    result['cultivar'] = first(result.get('cultivar'), attrs.get('cultivar'))
    # Compatibility fields for the frontend parser supplied in this conversation.
    for output, key in {'biosample_description':'description', 'biosample_submitter':'submitter',
        'biosample_submission_date':'submission_date', 'biosample_publication_date':'publication_date',
        'biosample_last_updated':'modification_date', 'biosample_attributes':'attributes',
        'biosample_package':'package'}.items():
        result[output] = bio.get(key)
    for key in ('host', 'isolation_source', 'collection_date', 'project_name'):
        result[key] = first(attrs.get(key), attrs.get(key.replace('_', ' ')))
    result['biosample_collection_date'] = result.get('collection_date')
    result['geo_loc_name'] = first(attrs.get('geo_loc_name'), attrs.get('geo_location'))
    # Keep coverage compatible with the frontend's string type.
    coverage = result.get('genome_coverage')
    result['genome_coverage'] = str(coverage) if coverage is not None else None
    result['cache_schema_version'] = schema_version
    result['normalization_warnings'] = warnings
    result['cache_eligible'] = bool(parsed and result.get('assembly_name') and not warnings)
    result['statistics_warnings'] = []
    if result.get('atgc_count') is not None and result.get('genome_size_bp') is not None and result['atgc_count'] > result['genome_size_bp']:
        result['statistics_warnings'].append('Source ATGC count exceeds the selected total length; statistical scope is unresolved. Original values are retained.')
    raw_busco = result.get('busco')
    result['busco_original'] = raw_busco
    if not isinstance(raw_busco, dict) or not any(v is not None and v != '' for v in raw_busco.values()):
        result['busco'] = None
        result['field_sources'].pop('busco', None)
    else:
        canonical = dict(raw_busco)
        for target, alias in [('busco_lineage', 'buscolineage'), ('busco_ver', 'buscover'), ('single_copy', 'singlecopy'), ('total_count', 'totalcount')]:
            if canonical.get(target) in (None, ''):
                canonical[target] = raw_busco.get(alias)
        result['busco'] = canonical
    return result
