"""Keep source-specific statistics separate; provide legacy frontend aliases."""

STAT_KEYS = ('genome_size_bp', 'genome_size_ungapped_bp', 'gc_content', 'gc_count',
             'atgc_count', 'contig_n50', 'contig_l50', 'scaffold_n50', 'scaffold_l50',
             'number_of_contigs', 'number_of_scaffolds', 'number_of_chromosomes',
             'number_of_component_sequences', 'gaps_between_scaffolds')


def first(*values):
    return next((v for v in values if v is not None and v != ''), None)


def finalize_assembly(result, parsed, summary, ftp, warnings, schema_version, ena_accession):
    summary = summary or {}
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
        'gc_content': 'gc_percent', 'gc_count': 'gc_count', 'atgc_count': 'atgc_count',
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
    result.update(selected)
    if result['gc_content'] is None and result['gc_count'] is not None and result['atgc_count']:
        result['gc_content'] = 100 * result['gc_count'] / result['atgc_count']
    for raw, human in [('genome_size_bp', 'genome_size_mb'),
                       ('genome_size_ungapped_bp', 'genome_size_ungapped_mb')]:
        result[human] = round(result[raw] / 1_000_000, 2) if result[raw] is not None else None
    result['statistics_source'] = source
    result['statistics_by_source'] = {
        'datasets': {k: parsed.get('genome_size_ungapped' if k == 'genome_size_ungapped_bp' else k)
                     for k in STAT_KEYS} if parsed else None,
        'ftp_all_units': ftp_all,
        'ftp_contextual_statistics': {k:v for k,v in ftp.items() if k != 'all_summary'}}
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
    result['cache_eligible'] = bool(parsed and summary and bio.get('accession')
                                    and result.get('assembly_name'))
    return result
