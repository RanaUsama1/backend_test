"""NCBI assembly parser replacement and standalone fetch check.

Replace the existing parse_datasets_api function with an import from this module.
The output retains the application's existing field names. This module does not
modify MongoDB or deploy anything. See backend_review.md for integration changes.
"""
import argparse
import json
import re
from urllib.request import Request, urlopen


def _snake_keys(value):
    if isinstance(value, dict):
        return {re.sub(r'(?<!^)(?=[A-Z])', '_', k).lower(): _snake_keys(v)
                for k, v in value.items()}
    if isinstance(value, list):
        return [_snake_keys(v) for v in value]
    return value


def _first(*values):
    return next((v for v in values if v is not None and v != ''), None)


def _integer(value):
    if value is None or value == '':
        return None
    if isinstance(value, bool) or not re.fullmatch(r'\d+', str(value)):
        raise ValueError(f'Expected a nonnegative integer, received {value!r}')
    return int(value)


def _number(value):
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        raise ValueError('Boolean is not a numeric statistic')
    result = float(value)
    if not (-float('inf') < result < float('inf')):
        raise ValueError('Non-finite numeric statistic')
    return result


def parse_datasets_api(datasets_data, expected_accession=None):
    """Parse one REST dataset_report response; accept snake_case/camelCase keys.

    Empty reports return {}, preserving the old parser's fallback behavior.
    Malformed/mismatched records raise ValueError. The caller must not cache a
    failed lookup as a successful empty result.
    """
    if not isinstance(datasets_data, dict):
        raise ValueError('NCBI response must be an object')
    reports = datasets_data.get('reports')
    if reports == []:
        return {}
    if not isinstance(reports, list) or len(reports) != 1:
        raise ValueError('Expected exactly one assembly report')
    report = _snake_keys(reports[0])
    if not isinstance(report, dict) or not report.get('accession'):
        raise ValueError('Assembly report has no accession')
    if expected_accession and report['accession'] != expected_accession:
        raise ValueError('Returned assembly accession does not match the request')

    organism = report.get('organism') or {}
    info = report.get('assembly_info') or {}
    stats = report.get('assembly_stats') or {}
    annotation = report.get('annotation_info') or {}
    counts = (annotation.get('stats') or {}).get('gene_counts') or {}
    biosample = info.get('biosample') or {}
    infra = organism.get('infraspecific_names') or {}
    paired = info.get('paired_assembly') or {}
    result = {
        'accession': report['accession'],
        'organism_name': _first(organism.get('organism_name'), organism.get('sci_name')),
        'common_name': organism.get('common_name'),
        'tax_id': _integer(organism.get('tax_id')),
        'assembly_level': info.get('assembly_level'),
        'assembly_status': info.get('assembly_status'),
        'assembly_name': info.get('assembly_name'),
        'assembly_type': info.get('assembly_type'),
        'description': info.get('description'),
        'submitter': info.get('submitter'),
        'submission_date': info.get('submission_date'),
        'release_date': info.get('release_date'),
        'assembly_method': info.get('assembly_method'),
        'sequencing_technology': _first(info.get('sequencing_tech'), info.get('sequencing_technology')),
        'refseq_category': info.get('refseq_category'),
        'biosample_accession': _first(biosample.get('accession'), info.get('biosample_accession')),
        'bioproject_accession': info.get('bioproject_accession'),
        'strain': infra.get('strain'),
        'isolate': infra.get('isolate'),
        'cultivar': _first(infra.get('cultivar'), biosample.get('cultivar')),
        'expected_final_version': info.get('expected_final_version'),
        'synonym': info.get('synonym'),
        'annotation_provider': annotation.get('provider'),
        'annotation_date': annotation.get('release_date'),
        'annotation_name': annotation.get('name'),
        'annotation_method': annotation.get('method'),
        'annotation_pipeline': annotation.get('pipeline'),
        'annotation_software_version': annotation.get('software_version'),
        'annotation_status': annotation.get('status'),
        'wgs_project': (report.get('wgs_info') or {}).get('wgs_project_accession'),
        'paired_accession': _first(report.get('paired_accession'), paired.get('accession')),
        'current_accession': report.get('current_accession'),
        'source_database': report.get('source_database'),
        'organelle_info': report.get('organelle_info') or [],
        'biosample_metadata': biosample,
        'busco': annotation.get('busco'),
        'paired_assembly': paired,
        'statistics_source': 'NCBI Datasets assembly_stats; organelle_info retained separately',
    }
    integer_fields = {
        'genome_size_bp': 'total_sequence_length',
        'genome_size_ungapped': 'total_ungapped_length',
        'gc_count': 'gc_count', 'atgc_count': 'atgc_count',
        'number_of_chromosomes': 'total_number_of_chromosomes',
        'contig_n50': 'contig_n50', 'contig_l50': 'contig_l50',
        'number_of_contigs': 'number_of_contigs',
        'scaffold_n50': 'scaffold_n50', 'scaffold_l50': 'scaffold_l50',
        'number_of_scaffolds': 'number_of_scaffolds',
        'gaps_between_scaffolds': 'gaps_between_scaffolds_count',
        'number_of_component_sequences': 'number_of_component_sequences',
        'number_of_organelles': 'number_of_organelles',
    }
    for output, source in integer_fields.items():
        result[output] = _integer(stats.get(source))
    result['gc_content'] = _number(stats.get('gc_percent'))
    result['genome_coverage'] = _number(stats.get('genome_coverage'))
    bp = result['genome_size_bp']
    result['genome_size_mb'] = round(bp / 1_000_000, 2) if bp is not None else None
    for output, source in {'total_genes':'total', 'protein_coding_genes':'protein_coding',
                           'non_coding_genes':'non_coding', 'pseudogenes':'pseudogene',
                           'other_genes':'other'}.items():
        result[output] = _integer(counts.get(source))
    return result


def fetch_assembly(accession):
    accession = accession.strip().upper()
    if not re.fullmatch(r'GC[FA]_\d+\.\d+', accession):
        raise ValueError('Expected a versioned assembly accession such as GCF_902167145.1')
    url = f'https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession/{accession}/dataset_report'
    req = Request(url, headers={'User-Agent': 'NCBI-Metadata-Search/1.0'})
    with urlopen(req, timeout=45) as response:
        data = json.load(response)
    parsed = parse_datasets_api(data, expected_accession=accession)
    if not parsed:
        raise LookupError(f'No assembly report returned for {accession}')
    return parsed


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description='Fetch and display normalized NCBI assembly metadata')
    cli.add_argument('accession')
    args = cli.parse_args()
    print(json.dumps(fetch_assembly(args.accession), indent=2, allow_nan=False))
