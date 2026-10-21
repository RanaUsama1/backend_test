# from flask import Flask, request, jsonify
# from flask_cors import CORS
# from flask import send_file
# from pymongo import MongoClient
# import requests
# from datetime import datetime
# import time
# import os
# import re
# import xml.etree.ElementTree as ET
# from dotenv import load_dotenv
# from Bio import SeqIO
# from io import StringIO
# from io import BytesIO
# from metadata_archive import metadata_get, register_metadata_download
# from gene_service import register_gene_routes
# from protein_service import register_protein_routes
# from nucleotide_service import register_nucleotide_routes
# from ncbi_assembly_parser import parse_datasets_api
# from assembly_normalization import finalize_assembly
# from assembly_source_helpers import parse_ftp_stats_file, parse_ena_xml, exact_stats_url
# from pymongo.errors import DuplicateKeyError, PyMongoError
# from taxonomy_service import register_taxonomy_routes
# from excel_export import register_excel_export

# ASSEMBLY_CACHE_SCHEMA_VERSION = 4

# load_dotenv()

# app = Flask(__name__)
# CORS(app)


# # MongoDB
# MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
# client = MongoClient(MONGODB_URI)
# db = client.ncbi_cache
# # TEMPORARY ERROR TESTING - REMOVE BEFORE FINAL SUBMISSION
# TEST_ERROR_MODE = os.getenv('TEST_ERROR_MODE', '').strip().upper()

# # Collections
# assemblies = db.assemblies
# organism_searches = db.organism_searches
# nucleotides = db.nucleotides
# genes = db.genes
# proteins = db.proteins
# taxonomies = db.taxonomies

# # Create indexes
# assemblies.create_index('accession', unique=True)
# organism_searches.create_index('organism_name', unique=True)
# nucleotides.create_index('accession', unique=True)
# genes.create_index([('symbol', 1), ('tax_id', 1)], unique=True)
# proteins.create_index('accession', unique=True)
# taxonomies.create_index('tax_id', unique=True)

# # Rate limiting
# last_request_time = 0
# MIN_REQUEST_INTERVAL = 0.35
# NCBI_API_KEY = os.getenv('NCBI_API_KEY', '').strip()

# # def rate_limited_request(url, timeout=30):
# #     """Make rate-limited request to NCBI"""
# #     global last_request_time
# #     current_time = time.time()
# #     time_since_last = current_time - last_request_time
# #     if time_since_last < MIN_REQUEST_INTERVAL:
# #         time.sleep(MIN_REQUEST_INTERVAL - time_since_last)
# #     if NCBI_API_KEY and 'ncbi.nlm.nih.gov' in url:
# #         separator = '&' if '?' in url else '?'
# #         url = f"{url}{separator}api_key={NCBI_API_KEY}"
# #     last_request_time = time.time()
# #     return requests.get(url, timeout=timeout)

# def api_error(message, error_code, status_code, query=None):
#     response = {
#         'error_code': error_code,
#         'message': message
#     }

#     if query is not None:
#         response['query'] = query

#     return jsonify(response), status_code


# # TEMPORARY ERROR TESTING - REMOVE BEFORE FINAL SUBMISSION
# def trigger_test_error(error_mode, query):
#     if TEST_ERROR_MODE == error_mode:
#         if error_mode == 'E5':
#             raise requests.RequestException("Temporary NCBI failure test")

#         if error_mode == 'E6':
#             raise RuntimeError("Temporary backend failure test")

#         if error_mode == 'E7':
#             raise Exception("Temporary MongoDB failure test")

# def rate_limited_request(url, timeout=30):
#     """Make a rate-limited request to NCBI with basic response validation."""
#     global last_request_time

#     current_time = time.time()
#     time_since_last = current_time - last_request_time

#     if time_since_last < MIN_REQUEST_INTERVAL:
#         time.sleep(MIN_REQUEST_INTERVAL - time_since_last)

#     if NCBI_API_KEY and 'ncbi.nlm.nih.gov' in url:
#         separator = '&' if '?' in url else '?'
#         url = f"{url}{separator}api_key={NCBI_API_KEY}"

#     last_request_time = time.time()

#     response = metadata_get(
#         url,
#         timeout=timeout,
#         headers={
#             "User-Agent": "NCBI-Metadata-Search/1.0"
#         }
#     )

#     response.raise_for_status()

#     return response

# def detect_database_type(query):
#     """Auto-detect database type from query string"""
#     query = query.strip()
#     if re.match(r'^GC[FA]_\d+\.\d+$', query):
#         return 'assembly'
#     if re.match(r'^N[CGMRW]_\d+\.\d+$', query):
#         return 'nucleotide'
#     if re.match(r'^[NYXWAZ]P_\d+\.\d+$', query):
#         return 'protein'
#     if re.match(r'^\d+$', query):
#         return 'gene'
#     # if re.match(r'^[A-Z][A-Z0-9\-]+$', query, re.IGNORECASE):
#     #     return 'gene'
#     if ' ' in query:
#         return 'organism'
#     return 'unknown'

# # ==================== FTP STATS PARSER ====================

# def fetch_ftp_stats(ftp_url):
#     """Fetch and parse assembly stats from NCBI FTP"""
#     if not ftp_url:
#         return None
#     try:
#         https_url = ftp_url.replace('ftp://', 'https://')
#         resp = metadata_get(https_url, timeout=30)
#         if resp.status_code == 200:
#             return parse_ftp_stats_file(resp.text)
#     except Exception as e:
#         print(f"FTP stats fetch error: {e}")
#     return None

# # ==================== META XML PARSER ====================

# def parse_meta_xml(meta_xml):
#     """Parse ESummary meta XML string"""
#     stats = {}
#     if not meta_xml:
#         return stats

#     matches = re.findall(r'<Stat category="([^"]+)"[^>]*>([^<]+)</Stat>', meta_xml)
#     for category, value in matches:
#         key = category.lower().replace('-', '_')
#         try:
#             if '.' in value:
#                 stats[key] = float(value)
#             else:
#                 stats[key] = int(value)
#         except ValueError:
#             stats[key] = value

#     return stats

# # ==================== DATASETS API PARSER ====================


# # ==================== ENA FETCHER ====================

# def fetch_ena_assembly(accession):
#     try:
#         response = metadata_get(f'https://www.ebi.ac.uk/ena/browser/api/xml/{accession}', timeout=15)
#         if not response.ok:
#             return None
#         return parse_ena_xml(response.content, accession)
#     except Exception as exc:
#         print(f'ENA fetch error: {type(exc).__name__}')
#         return None

# # ==================== BIOSAMPLE FETCHER (NEW) ====================

# def fetch_biosample_data(biosample_accession):
#     """Fetch BioSample metadata from NCBI"""
#     if not biosample_accession:
#         return None

#     try:
#         # Search for BioSample UID
#         search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=biosample&term={biosample_accession}&retmode=json"
#         search_resp = rate_limited_request(search_url)
#         search_data = search_resp.json()

#         if not search_data.get('esearchresult', {}).get('idlist'):
#             return None

#         uid = search_data['esearchresult']['idlist'][0]

#         # Fetch summary
#         summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=biosample&id={uid}&retmode=json"
#         summary_resp = rate_limited_request(summary_url)
#         summary_data = summary_resp.json().get('result', {}).get(str(uid), {})

#         # Parse sampledata XML if present
#         biosample_info = {
#             'accession': biosample_accession,
#             'uid': uid,
#             'title': summary_data.get('title'),
#             'organism': summary_data.get('organism'),
#             'tax_id': summary_data.get('taxonomy'),
#             'submitter': summary_data.get('organization'),
#             'submission_date': summary_data.get('date'),
#             'publication_date': summary_data.get('publicationdate'),
#             'modification_date': summary_data.get('modificationdate'),
#             'package': summary_data.get('package'),
#             'attributes': {},
#             'description': None,
#             'links': {}
#         }

#         # Parse the sampledata XML for detailed info
#         sample_data_xml = summary_data.get('sampledata', '')
#         if sample_data_xml:
#             try:
#                 root = ET.fromstring(sample_data_xml)

#                 for elem in root.iter():
#                     tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag

#                     if tag == 'Title':
#                         if not biosample_info['title']:
#                             biosample_info['title'] = elem.text
#                     elif tag == 'Description':
#                         # Look for Paragraph inside Description
#                         for child in elem.iter():
#                             child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
#                             if child_tag == 'Paragraph' and child.text:
#                                 biosample_info['description'] = child.text
#                     elif tag == 'Attribute':
#                         attr_name = elem.get('attribute_name') or elem.get('harmonized_name')
#                         if attr_name:
#                             biosample_info['attributes'][attr_name] = elem.text
#                     elif tag == 'Link':
#                         link_type = elem.get('type')
#                         link_target = elem.get('target')
#                         link_label = elem.get('label')
#                         if link_target:
#                             biosample_info['links'][link_target] = {
#                                 'type': link_type,
#                                 'label': link_label,
#                                 'value': elem.text
#                             }
#             except Exception as e:
#                 print(f"BioSample XML parse error: {e}")

#         # Also check infraspecies field
#         infraspecies = summary_data.get('infraspecies', '')
#         if infraspecies and ':' in infraspecies:
#             for item in infraspecies.split(';'):
#                 key, separator, value = item.partition(':')
#                 if separator and key.strip():
#                     biosample_info['attributes'].setdefault(key.strip(), value.strip())

#         return biosample_info

#     except Exception as e:
#         print(f"BioSample fetch error: {e}")
#         return None

# # ==================== ORGANISM NAME SEARCH ====================

# def search_assemblies_by_organism(organism_name, max_results=20):
#     """Search NCBI Assembly database by organism name"""
#     try:
#         search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=assembly&term={organism_name.replace(' ', '+')}[ORGN]&retmode=json&sort=date&retmax={max_results}"
#         search_resp = rate_limited_request(search_url)
#         search_data = search_resp.json()

#         ids = search_data.get('esearchresult', {}).get('idlist', [])
#         if not ids:
#             return []

#         assemblies_list = []

#         for uid in ids:
#             summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=assembly&id={uid}&retmode=json"
#             summary_resp = rate_limited_request(summary_url)
#             summary_data = summary_resp.json()
#             result = summary_data.get('result', {}).get(str(uid), {})

#             if not result:
#                 continue

#             meta_xml = result.get('meta', '')
#             meta_stats = parse_meta_xml(meta_xml)

#             assembly_info = {
#                 'uid': uid,
#                 'accession': result.get('assemblyaccession'),
#                 'assembly_name': result.get('assemblyname'),
#                 'organism': result.get('organism'),
#                 'tax_id': result.get('taxid'),
#                 'species_name': result.get('speciesname'),
#                 'assembly_status': result.get('assemblystatus'),
#                 'assembly_level': result.get('assemblylevel'),
#                 'refseq_category': result.get('refseq_category'),
#                 'submission_date': result.get('submissiondate'),
#                 'last_update_date': result.get('lastupdatedate'),
#                 'submitter': result.get('submitterorganization'),
#                 'coverage': result.get('coverage'),
#                 'biosample': result.get('biosampleaccn'),
#                 'bioproject': result.get('bioproject'),
#                 'ftppath_genbank': result.get('ftppath_genbank'),
#                 'ftppath_refseq': result.get('ftppath_refseq'),
#                 'ftppath_stats_rpt': result.get('ftppath_stats_rpt'),
#                 'genome_size_bp': meta_stats.get('total_sequence_length') or meta_stats.get('total_length'),
#                 'contig_n50': meta_stats.get('contig_n50'),
#                 'scaffold_n50': meta_stats.get('scaffold_n50'),
#                 'number_of_contigs': meta_stats.get('contig_count'),
#                 'number_of_scaffolds': meta_stats.get('scaffold_count'),
#                 'number_of_chromosomes': meta_stats.get('chromosome_count'),
#                 'ungapped_length': meta_stats.get('ungapped_length'),
#                 'coverage': result.get('coverage') if result.get('coverage') else None,
#             }

#             assemblies_list.append(assembly_info)

#         return assemblies_list

#     except Exception as e:
#         print(f"Organism search error: {e}")
#         return []

# def pick_best_assembly(assemblies_list):
#     """Pick the best assembly from a list"""
#     if not assemblies_list:
#         return None

#     def score(asm):
#         s = 0
#         if asm.get('refseq_category') and asm['refseq_category'] != 'na':
#             s += 1000
#         if asm.get('assembly_level') in ['Complete Genome', 'Chromosome']:
#             s += 500
#         elif asm.get('assembly_level') == 'Scaffold':
#             s += 200
#         elif asm.get('assembly_level') == 'Contig':
#             s += 100
#         if asm.get('genome_size_bp'):
#             s += 50
#         if asm.get('coverage'):
#             s += 25
#         if asm.get('accession', '').startswith('GCF_'):
#             s += 10
#         acc = asm.get('accession', '')
#         try:
#             version = float(acc.split('.')[-1]) if '.' in acc else 0
#             s += version
#         except:
#             pass
#         return s

#     sorted_assemblies = sorted(assemblies_list, key=score, reverse=True)
#     return sorted_assemblies[0]

# # ==================== CORE ASSEMBLY FETCHER ====================

# def get_value(*sources):
#     """Get first non-null value from sources"""
#     for src in sources:
#         if src is not None and src != '' and src != []:
#             return src
#     return None

# def fetch_and_parse_assembly(accession):
#     """Core function to fetch and parse assembly data from all sources"""

#     accession = accession.strip().upper()
#     normalization_warnings = []

#     # SOURCE 1: NCBI Datasets API v2
#     datasets_data = None
#     datasets_parsed = {}
#     try:
#         datasets_url = f"https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession/{accession}/dataset_report"
#         datasets_resp = rate_limited_request(datasets_url)
#         if datasets_resp.ok:
#             datasets_data = datasets_resp.json()
#             datasets_parsed = parse_datasets_api(datasets_data, expected_accession=accession)
#             print(f"  Datasets API: {len(datasets_parsed)} fields parsed")
#     except Exception as e:
#         normalization_warnings.append({"source": "datasets", "error_type": type(e).__name__})
#         print(f"  Datasets API error: {type(e).__name__}")

#     # SOURCE 2: NCBI ESummary
#     esummary_data = None
#     meta_stats = {}
#     assembly_id = None
#     ftp_stats_url = None
#     try:
#         search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=assembly&term={accession}&retmode=json"
#         search_resp = rate_limited_request(search_url)
#         search_data = search_resp.json()

#         if search_data.get('esearchresult', {}).get('idlist'):
#             assembly_id = search_data['esearchresult']['idlist'][0]
#             summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=assembly&id={assembly_id}&retmode=json"
#             summary_resp = rate_limited_request(summary_url)
#             esummary_data = summary_resp.json().get('result', {}).get(assembly_id, {})

#             ftp_stats_url = exact_stats_url(accession, esummary_data)
#             if esummary_data.get('assemblyaccession') != accession:
#                 esummary_data = None
#                 raise ValueError('ESummary assembly accession mismatch')
#             meta_xml = esummary_data.get('meta', '')
#             meta_stats = parse_meta_xml(meta_xml)
#             # The requested database/version determines the FTP directory.
#             print(f"  ESummary: ID={assembly_id}, meta has {len(meta_stats)} stats")
#     except Exception as e:
#         normalization_warnings.append({"source": "esummary", "error_type": type(e).__name__})
#         print(f"  ESummary error: {type(e).__name__}")

#     # SOURCE 3: NCBI FTP Stats File
#     ftp_stats = {}
#     try:
#         if ftp_stats_url:
#             ftp_stats = fetch_ftp_stats(ftp_stats_url) or {}
#             identity_key = 'RefSeq assembly accession' if accession.startswith('GCF_') else 'GenBank assembly accession'
#             if (ftp_stats.get('headers') or {}).get(identity_key) != accession:
#                 ftp_stats = {}
#                 normalization_warnings.append({'source': 'ftp_stats', 'error_type': 'missing_or_mismatched_identity'})
#             print(f"  FTP Stats: {len(ftp_stats)} fields parsed")
#         else:
#             normalization_warnings.append({'source': 'ftp_stats', 'error_type': 'no_exact_accession_url'})
#     except Exception as e:
#         normalization_warnings.append({"source": "ftp_stats", "error_type": type(e).__name__})
#         print(f"  FTP stats error: {type(e).__name__}")

#     # SOURCE 4: ENA
#     paired_accession = datasets_parsed.get('paired_accession')
#     if not paired_accession and esummary_data:
#         paired_accession = (esummary_data.get('synonym') or {}).get('genbank')
#     ena_accession = accession if accession.startswith('GCA_') else paired_accession
#     ena_data = (fetch_ena_assembly(ena_accession)
#                 if ena_accession and re.fullmatch(r'GCA_\d+\.\d+', ena_accession) else None)
#     if ena_data:
#         print(f"  ENA: {len(ena_data)} fields parsed")

#     # SOURCE 5: BioSample (NEW)
#     biosample_accession = get_value(
#         datasets_parsed.get('biosample_accession'),
#         esummary_data.get('biosampleaccn') if esummary_data else None
#     )
#     biosample_data = None
#     if biosample_accession:
#         biosample_data = fetch_biosample_data(biosample_accession)
#         if biosample_data:
#             print(f"  BioSample: {biosample_accession} fetched with {len(biosample_data.get('attributes', {}))} attributes")

#     # MERGE ALL SOURCES
#     all_summary = ftp_stats.get('all_summary', {})

#     genome_size = get_value(
#         datasets_parsed.get('genome_size_bp'),
#         meta_stats.get('total_sequence_length'),
#         meta_stats.get('total_length'),
#         all_summary.get('total_length'),
#         all_summary.get('total_sequence_length'),
#         esummary_data.get('assemblylength') if esummary_data else None
#     )

#     genome_size_ungapped = get_value(
#         datasets_parsed.get('genome_size_ungapped'),
#         meta_stats.get('ungapped_length'),
#         all_summary.get('ungapped_length')
#     )

#     gc_content = get_value(
#         datasets_parsed.get('gc_content'),
#         meta_stats.get('gc_percent'),
#         all_summary.get('gc_perc'),
#         all_summary.get('gc_percent')
#     )

#     gc_count = get_value(
#         datasets_parsed.get('gc_count'),
#         meta_stats.get('gc_count'),
#         all_summary.get('gc_count')
#     )
#     atgc_count = get_value(
#         datasets_parsed.get('atgc_count'),
#         meta_stats.get('atgc_count'),
#         all_summary.get('atgc_count')
#     )

#     if gc_content is None and gc_count is not None and atgc_count:
#         gc_content = round((gc_count / atgc_count) * 100, 2)

#     coverage = get_value(
#         datasets_parsed.get('genome_coverage'),
#         esummary_data.get('coverage') if esummary_data else None,
#         meta_stats.get('coverage')
#     )

#     contig_n50 = get_value(
#         datasets_parsed.get('contig_n50'),
#         meta_stats.get('contig_n50'),
#         all_summary.get('contig_n50'),
#         esummary_data.get('contign50') if esummary_data else None
#     )

#     contig_l50 = get_value(
#         datasets_parsed.get('contig_l50'),
#         meta_stats.get('contig_l50'),
#         all_summary.get('contig_l50')
#     )

#     scaffold_n50 = get_value(
#         datasets_parsed.get('scaffold_n50'),
#         meta_stats.get('scaffold_n50'),
#         all_summary.get('scaffold_n50'),
#         esummary_data.get('scaffoldn50') if esummary_data else None
#     )

#     scaffold_l50 = get_value(
#         datasets_parsed.get('scaffold_l50'),
#         meta_stats.get('scaffold_l50'),
#         all_summary.get('scaffold_l50')
#     )

#     num_contigs = get_value(
#         datasets_parsed.get('number_of_contigs'),
#         meta_stats.get('contig_count'),
#         all_summary.get('contig_count')
#     )

#     num_scaffolds = get_value(
#         datasets_parsed.get('number_of_scaffolds'),
#         meta_stats.get('scaffold_count'),
#         all_summary.get('scaffold_count')
#     )

#     num_chromosomes = get_value(
#         datasets_parsed.get('number_of_chromosomes'),
#         meta_stats.get('chromosome_count'),
#         all_summary.get('chromosome_count')
#     )

#     gaps = get_value(
#         datasets_parsed.get('gaps_between_scaffolds'),
#         meta_stats.get('gaps_between_scaffolds_count'),
#         all_summary.get('gaps_between_scaffolds')
#     )

#     result = {
#         'accession': accession,
#         'assembly_id': assembly_id,

#         'genome_size_bp': genome_size,
#         'genome_size_mb': round(genome_size / 1_000_000, 2) if genome_size else None,
#         'genome_size_ungapped_bp': genome_size_ungapped,
#         'genome_size_ungapped_mb': round(genome_size_ungapped / 1_000_000, 2) if genome_size_ungapped else None,
#         'gc_content': gc_content,
#         'gc_count': gc_count,
#         'atgc_count': atgc_count,
#         'genome_coverage': coverage,

#         'contig_n50': contig_n50,
#         'contig_l50': contig_l50,
#         'scaffold_n50': scaffold_n50,
#         'scaffold_l50': scaffold_l50,
#         'number_of_contigs': num_contigs,
#         'number_of_scaffolds': num_scaffolds,
#         'number_of_chromosomes': num_chromosomes,
#         'gaps_between_scaffolds': gaps,
#         'number_of_component_sequences': get_value(
#             datasets_parsed.get('number_of_component_sequences'),
#             meta_stats.get('number_of_component_sequences')
#         ),
#         'number_of_organelles': datasets_parsed.get('number_of_organelles'),

#         'organism_name': get_value(
#             datasets_parsed.get('organism_name'),
#             esummary_data.get('organism') if esummary_data else None,
#             ena_data.get('scientific_name') if ena_data else None
#         ),
#         'common_name': get_value(
#             datasets_parsed.get('common_name'),
#             esummary_data.get('commonname') if esummary_data else None,
#             ena_data.get('common_name') if ena_data else None
#         ),
#         'tax_id': get_value(
#             datasets_parsed.get('tax_id'),
#             esummary_data.get('taxid') if esummary_data else None,
#             ena_data.get('tax_id') if ena_data else None
#         ),

#         'assembly_name': get_value(
#             datasets_parsed.get('assembly_name'),
#             esummary_data.get('assemblyname') if esummary_data else None
#         ),
#         'assembly_level': get_value(
#             datasets_parsed.get('assembly_level'),
#             esummary_data.get('assemblystatus') if esummary_data else None
#         ),
#         'assembly_type': get_value(
#             datasets_parsed.get('assembly_type'),
#             ena_data.get('assembly_type') if ena_data else None
#         ),
#         'assembly_status': datasets_parsed.get('assembly_status'),
#         'description': get_value(
#             datasets_parsed.get('description'),
#             ena_data.get('description') if ena_data else None
#         ),
#         'submitter': get_value(
#             datasets_parsed.get('submitter'),
#             esummary_data.get('submitterorganization') if esummary_data else None
#         ),
#         'submission_date': get_value(
#             datasets_parsed.get('submission_date'),
#             esummary_data.get('submissiondate') if esummary_data else None,
#             ena_data.get('submission_date') if ena_data else None
#         ),
#         'release_date': get_value(
#             datasets_parsed.get('release_date'),
#             esummary_data.get('seqreleasedate') if esummary_data else None
#         ),
#         'last_update_date': esummary_data.get('lastupdatedate') if esummary_data else None,
#         'synonym': datasets_parsed.get('synonym'),

#         'assembly_method': get_value(
#             datasets_parsed.get('assembly_method'),
#             esummary_data.get('assemblymethod') if esummary_data else None
#         ),
#         'sequencing_technology': get_value(
#             datasets_parsed.get('sequencing_technology'),
#             esummary_data.get('sequencingtechnology') if esummary_data else None
#         ),
#         'refseq_category': get_value(
#             datasets_parsed.get('refseq_category'),
#             esummary_data.get('refseq_category') if esummary_data else None
#         ),
#         'genome_representation': ena_data.get('genome_representation') if ena_data else None,

#         'biosample_accession': biosample_accession,
#         'bioproject_accession': get_value(
#             datasets_parsed.get('bioproject_accession'),
#             esummary_data.get('bioproject') if esummary_data else None
#         ),
#         'wgs_project': datasets_parsed.get('wgs_project'),
#         'current_accession': datasets_parsed.get('current_accession'),
#         'paired_accession': datasets_parsed.get('paired_accession'),
#         'source_database': datasets_parsed.get('source_database'),

#         'strain': get_value(
#             datasets_parsed.get('strain'),
#             esummary_data.get('strain') if esummary_data else None
#         ),
#         'isolate': get_value(
#             datasets_parsed.get('isolate'),
#             esummary_data.get('isolate') if esummary_data else None
#         ),

#         'annotation_provider': datasets_parsed.get('annotation_provider'),
#         'annotation_date': datasets_parsed.get('annotation_date'),
#         'annotation_name': datasets_parsed.get('annotation_name'),
#         'annotation_method': datasets_parsed.get('annotation_method'),
#         'annotation_pipeline': datasets_parsed.get('annotation_pipeline'),
#         'annotation_software_version': datasets_parsed.get('annotation_software_version'),
#         'annotation_status': datasets_parsed.get('annotation_status'),
#         'total_genes': datasets_parsed.get('total_genes'),
#         'protein_coding_genes': datasets_parsed.get('protein_coding_genes'),
#         'non_coding_genes': datasets_parsed.get('non_coding_genes'),
#         'pseudogenes': datasets_parsed.get('pseudogenes'),
#         'other_genes': datasets_parsed.get('other_genes'),

#         'ncbi_url': f"https://www.ncbi.nlm.nih.gov/datasets/genome/{accession}/",
#         'ena_url': f"https://www.ebi.ac.uk/ena/browser/view/{accession}",
#         'ftp_path': esummary_data.get('ftppath_genbank') if esummary_data else None,
#         'ftp_path_refseq': esummary_data.get('ftppath_refseq') if esummary_data else None,

#         'ena_data': ena_data,
#         'biosample_data': biosample_data,  # NEW

#         'fetched_at': datetime.utcnow().isoformat(),
#         'from_cache': False
#     }

#     return finalize_assembly(
#         result, datasets_parsed, esummary_data, ftp_stats, normalization_warnings,
#         ASSEMBLY_CACHE_SCHEMA_VERSION, ena_accession)

# # ==================== ERROR / VALIDATION HELPERS ====================

# def api_error(message, error_code, status_code, query=None):
#     response = {
#         'error_code': error_code,
#         'message': message
#     }

#     if query is not None:
#         response['query'] = query

#     return jsonify(response), status_code


# def is_valid_assembly_accession(value):
#     """Validate RefSeq/GenBank assembly accession format."""
#     return bool(
#         re.fullmatch(
#             r'GC[FA]_\d+\.\d+',
#             value.strip(),
#             re.IGNORECASE
#         )
#     )

# def is_valid_nucleotide_accession(value):
#     """Validate common NCBI nucleotide accession formats."""
#     return bool(
#         re.fullmatch(
#             r'(?:AC|AP|AY|BK|CP|CR|DQ|EU|FJ|FM|FN|FO|FR|HE|HQ|JF|JQ|'
#             r'JN|KC|KF|KM|KP|KX|KY|LC|LN|LR|MF|MG|MH|MK|MN|MT|MW|'
#             r'NC|NG|NM|NR|NT|NW|NZ|ON|OP|OQ|OR|OX|'
#             r'BC|BT|BU|BX|U|V|X|Y|Z|'
#             r'N[CGMRW]|[A-Z]{2})_\d+(?:\.\d+)?',
#             value.strip(),
#             re.IGNORECASE
#         )
#     )


# def is_valid_protein_accession(value):
#     """Validate common NCBI protein accession formats."""
#     return bool(
#         re.fullmatch(
#             r'(?:NP|XP|YP|WP|AP|ZP|[A-Z]{3})_\d+\.\d+',
#             value.strip(),
#             re.IGNORECASE
#         )
#     )

# def is_valid_gene_id(value):
#     """Validate an NCBI Gene ID."""
#     return value.strip().isdigit()

# def handle_database_error(query):
#     return api_error(
#         "Temporary database/cache error.",
#         "E7",
#         503,
#         query
#     )

# # ==================== Routes / Assembly ====================

# @app.route('/api/assembly/<accession>', methods=['GET'])
# def get_assembly(accession):
#     accession = accession.strip().upper()
#     """Fetch assembly data by accession"""
#     if not accession:
#         return api_error(
#             "Please enter a search query.",
#             "E1",
#             400,
#             accession
#         )

#     if not is_valid_assembly_accession(accession):
#         return api_error(
#             "Invalid accession or no matching record found.",
#             "E3",
#             400,
#             accession
#         )
#     cached = assemblies.find_one({'accession': accession,
#                                   'cache_schema_version': ASSEMBLY_CACHE_SCHEMA_VERSION,
#                                   'cache_eligible': True})
#     if cached:
#         print(f"✓ Cache HIT: assembly/{accession}")
#         cached['_id'] = str(cached['_id'])
#         cached['from_cache'] = True
#         return jsonify(cached)

#     print(f"⚠ Cache MISS: assembly/{accession}")

#     try:
#         result = fetch_and_parse_assembly(accession)
#         if result.get('cache_eligible'):
#             assemblies.replace_one({'accession': accession}, result.copy(), upsert=True)
#         result['_id'] = str(result.get('_id', ''))
#         return jsonify(result)

#     # except Exception as e:
#     #     import traceback
#     #     traceback.print_exc()
#     #     return jsonify({'error': str(e), 'accession': accession}), 500

#     except Exception as e:
#         import traceback
#         traceback.print_exc()

#         return api_error(
#             "An unexpected server error occurred.",
#             "E4",
#             500,
#             accession
#         )


# # ==================== ORGANISM SEARCH ENDPOINT ====================

# @app.route('/api/organism/<path:organism_name>', methods=['GET'])
# def search_by_organism(organism_name):
#     """Search for assemblies by organism name"""
#     organism_name = organism_name.replace('%20', ' ')

#     cached = organism_searches.find_one({'organism_name': organism_name,
#                                          'cache_schema_version': ASSEMBLY_CACHE_SCHEMA_VERSION,
#                                          'assembly_data.cache_eligible': True})
#     if cached:
#         print(f"✓ Cache HIT: organism/{organism_name}")
#         cached['_id'] = str(cached['_id'])
#         cached['from_cache'] = True
#         return jsonify(cached)

#     print(f"⚠ Cache MISS: organism/{organism_name}")

#     try:
#         assemblies_list = search_assemblies_by_organism(organism_name, max_results=20)

#         # if not assemblies_list:
#         #     return jsonify({
#         #         'error': f'No assemblies found for organism: {organism_name}',
#         #         'organism_name': organism_name
#         #     }), 404

#         if not assemblies_list:
#             return api_error(
#                 f"No matching record found for '{organism_name}'.",
#                 "E2",
#                 404,
#                 organism_name
#             )
#         best = pick_best_assembly(assemblies_list)
#         best_accession = best.get('accession')

#         print(f"  Best assembly selected: {best_accession}")

#         full_data = fetch_and_parse_assembly(best_accession)

#         result = {
#             'organism_name': organism_name,
#             'best_assembly': {
#                 'accession': best_accession,
#                 'assembly_name': best.get('assembly_name'),
#                 'assembly_level': best.get('assembly_level'),
#                 'assembly_status': best.get('assembly_status'),
#                 'refseq_category': best.get('refseq_category'),
#                 'coverage': best.get('coverage'),
#                 'submitter': best.get('submitter'),
#                 'submission_date': best.get('submission_date'),
#             },
#             'total_assemblies_found': len(assemblies_list),
#             'all_assemblies': [
#                 {
#                     'accession': a.get('accession'),
#                     'assembly_name': a.get('assembly_name'),
#                     'assembly_level': a.get('assembly_level'),
#                     'assembly_status': a.get('assembly_status'),
#                     'refseq_category': a.get('refseq_category'),
#                     'genome_size_bp': a.get('genome_size_bp'),
#                     'coverage': a.get('coverage'),
#                     'submission_date': a.get('submission_date'),
#                 }
#                 for a in assemblies_list
#             ],
#             'assembly_data': full_data,
#             'fetched_at': datetime.utcnow().isoformat(),
#             'from_cache': False
#         }

#         result['cache_schema_version'] = ASSEMBLY_CACHE_SCHEMA_VERSION
#         if full_data.get('cache_eligible'):
#             organism_searches.replace_one({'organism_name': organism_name}, result.copy(), upsert=True)
#         result['_id'] = str(result.get('_id', ''))
#         return jsonify(result)

#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         return jsonify({'error': str(e), 'organism_name': organism_name}), 500

# register_metadata_download(app, fetch_and_parse_assembly)
# get_gene_by_id, get_gene_by_symbol = register_gene_routes(app)


# get_nucleotide = register_nucleotide_routes(app)

# # ==================== GENE ====================


#         # return api_error(
#         #     "An unexpected server error occurred.",
#         #     "E6",
#         #     500,
#         #     symbol
#         # )



# # ==================== PROTEIN ====================
# get_protein = register_protein_routes(app)

# # ==================== TAXONOMY ====================
# get_taxonomy = register_taxonomy_routes(app)

# # ==================== SMART SEARCH ====================

# @app.route('/api/search', methods=['POST'])
# def smart_search():
#     query = request.json.get('query', '')
#     database = detect_database_type(query)

#     if database == 'assembly':
#         return get_assembly(query)
#     elif database == 'organism':
#         return search_by_organism(query)
#     elif database == 'nucleotide':
#         return get_nucleotide(query)
#     elif database == 'protein':
#         return get_protein(query)
#     elif database == 'gene':
#         if query.isdigit():
#             return get_gene_by_id(query)
#         else:
#             return get_gene_by_symbol(query)
#     elif database == 'taxonomy':
#         return get_taxonomy(query)
#     else:
#         return jsonify({'error': 'Could not detect database type', 'query': query}), 400


# # ==================== GET SEARCH WITH QUERY PARAMS ====================

# @app.route('/search/', methods=['GET'], strict_slashes=False)
# def search_by_params():
#     database = request.args.get('database')
#     accession_ids = request.args.get('accession_ids') or request.args.get('query')

#     if not database or not accession_ids:
#         return jsonify({'error': 'Missing database or accession_ids parameter'}), 400

#     if database == 'assembly':
#         return get_assembly(accession_ids)
#     elif database == 'organism':
#         return search_by_organism(accession_ids)
#     elif database == 'nucleotide':
#         return get_nucleotide(accession_ids)
#     elif database == 'protein':
#         return get_protein(accession_ids)
#     elif database == 'gene':
#         if accession_ids.isdigit():
#             return get_gene_by_id(accession_ids)
#         else:
#             return get_gene_by_symbol(accession_ids)
#     elif database == 'taxonomy':
#         return get_taxonomy(accession_ids)
#     else:
#         return jsonify({'error': f'Unknown database: {database}'}), 400


# # ==================== UTILITY ====================

# @app.route('/api/health', methods=['GET'])
# def health():
#     return jsonify({
#         'status': 'healthy',
#         'timestamp': datetime.utcnow().isoformat(),
#         'databases': {
#             'assemblies': assemblies.count_documents({}),
#             'organism_searches': organism_searches.count_documents({}),
#             'nucleotides': nucleotides.count_documents({}),
#             'genes': genes.count_documents({}),
#             'proteins': proteins.count_documents({}),
#             'taxonomies': taxonomies.count_documents({})
#         }
#     })

# # ==================== DOWNLOAD DATABASE ====================
# @app.route('/api/download/genbank/<database>/<accession>', methods=['GET'])
# def download_genbank(database, accession):

#     try:
#         database_map = {
#             'nucleotide': 'nuccore',
#             'protein': 'protein'
#         }

#         ncbi_db = database_map.get(database)

#         if not ncbi_db:
#             return jsonify({
#                 'error': 'GenBank download is supported only for nucleotide and protein'
#             }), 400

#         url = (
#             "https://eutils.ncbi.nlm.nih.gov/"
#             "entrez/eutils/efetch.fcgi"
#             f"?db={ncbi_db}"
#             f"&id={accession}"
#             f"&rettype={'gp' if database == 'protein' else 'gb'}"
#             f"&retmode=text"
#         )

#         response = rate_limited_request(url)

#         if not response.ok or not response.content.strip():
#             return jsonify({
#                 'error': 'Unable to retrieve GenBank record',
#                 'accession': accession
#             }), 502

#         return send_file(
#             BytesIO(response.content),
#             mimetype='text/plain',
#             as_attachment=True,
#             download_name=f"{accession}.{'gp' if database == 'protein' else 'gb'}"
#         )

#     except Exception as e:

#         import traceback
#         traceback.print_exc()

#         return jsonify({
#             'error': str(e),
#             'accession': accession
#         }), 500

# @app.route('/api/detect/<query>', methods=['GET'])
# def detect_db(query):
#     return jsonify({
#         'query': query,
#         'detected_database': detect_database_type(query)
#     })

# def api_error(message, error_code, status_code, query=None):
#     response = {
#         "error_code": error_code,
#         "message": message,
#     }

#     if query is not None:
#         response["query"] = query

#     return jsonify(response), status_code

# register_excel_export(app)

# if __name__ == '__main__':
#     app.run(debug=True, port=5001)



from smart_search_service import register_smart_search
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask import send_file
from pymongo import MongoClient
import requests
from datetime import datetime
import time
import os
import re
import certifi
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
from Bio import SeqIO
from io import StringIO
from io import BytesIO
from metadata_archive import metadata_get, register_metadata_download
from gene_service import register_gene_routes
from protein_service import register_protein_routes
from nucleotide_service import register_nucleotide_routes
from ncbi_assembly_parser import parse_datasets_api
from assembly_normalization import finalize_assembly
from assembly_source_helpers import parse_ftp_stats_file, parse_ena_xml, exact_stats_url
from pymongo.errors import DuplicateKeyError, PyMongoError
from taxonomy_service import register_taxonomy_routes
from excel_export import register_excel_export

ASSEMBLY_CACHE_SCHEMA_VERSION = 4

load_dotenv()

app = Flask(__name__)
CORS(app)


# MongoDB
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
# client = MongoClient(MONGODB_URI)
client = MongoClient(
    MONGODB_URI,
    tls=True,
    tlsCAFile=certifi.where(),
    serverSelectionTimeoutMS=10000,
)
db = client.ncbi_cache
# TEMPORARY ERROR TESTING - REMOVE BEFORE FINAL SUBMISSION
TEST_ERROR_MODE = os.getenv('TEST_ERROR_MODE', '').strip().upper()

# Collections
assemblies = db.assemblies
organism_searches = db.organism_searches
nucleotides = db.nucleotides
genes = db.genes
proteins = db.proteins
taxonomies = db.taxonomies

# Create indexes
assemblies.create_index('accession', unique=True)
organism_searches.create_index('organism_name', unique=True)
nucleotides.create_index('accession', unique=True)
genes.create_index([('symbol', 1), ('tax_id', 1)], unique=True)
proteins.create_index('accession', unique=True)
taxonomies.create_index('tax_id', unique=True)

# Rate limiting
last_request_time = 0
MIN_REQUEST_INTERVAL = 0.35
NCBI_API_KEY = os.getenv('NCBI_API_KEY', '').strip()

# def rate_limited_request(url, timeout=30):
#     """Make rate-limited request to NCBI"""
#     global last_request_time
#     current_time = time.time()
#     time_since_last = current_time - last_request_time
#     if time_since_last < MIN_REQUEST_INTERVAL:
#         time.sleep(MIN_REQUEST_INTERVAL - time_since_last)
#     if NCBI_API_KEY and 'ncbi.nlm.nih.gov' in url:
#         separator = '&' if '?' in url else '?'
#         url = f"{url}{separator}api_key={NCBI_API_KEY}"
#     last_request_time = time.time()
#     return requests.get(url, timeout=timeout)

def api_error(message, error_code, status_code, query=None):
    response = {
        'error_code': error_code,
        'message': message
    }

    if query is not None:
        response['query'] = query

    return jsonify(response), status_code


# TEMPORARY ERROR TESTING - REMOVE BEFORE FINAL SUBMISSION
def trigger_test_error(error_mode, query):
    if TEST_ERROR_MODE == error_mode:
        if error_mode == 'E5':
            raise requests.RequestException("Temporary NCBI failure test")

        if error_mode == 'E6':
            raise RuntimeError("Temporary backend failure test")

        if error_mode == 'E7':
            raise Exception("Temporary MongoDB failure test")

def rate_limited_request(url, timeout=30):
    """Make a rate-limited request to NCBI with basic response validation."""
    global last_request_time

    current_time = time.time()
    time_since_last = current_time - last_request_time

    if time_since_last < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - time_since_last)

    if NCBI_API_KEY and 'ncbi.nlm.nih.gov' in url:
        separator = '&' if '?' in url else '?'
        url = f"{url}{separator}api_key={NCBI_API_KEY}"

    last_request_time = time.time()

    response = metadata_get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": "NCBI-Metadata-Search/1.0"
        }
    )

    response.raise_for_status()

    return response


# ==================== FTP STATS PARSER ====================

def fetch_ftp_stats(ftp_url):
    """Fetch and parse assembly stats from NCBI FTP"""
    if not ftp_url:
        return None
    try:
        https_url = ftp_url.replace('ftp://', 'https://')
        resp = metadata_get(https_url, timeout=30)
        if resp.status_code == 200:
            return parse_ftp_stats_file(resp.text)
    except Exception as e:
        print(f"FTP stats fetch error: {e}")
    return None

# ==================== META XML PARSER ====================

def parse_meta_xml(meta_xml):
    """Parse ESummary meta XML string"""
    stats = {}
    if not meta_xml:
        return stats

    matches = re.findall(r'<Stat category="([^"]+)"[^>]*>([^<]+)</Stat>', meta_xml)
    for category, value in matches:
        key = category.lower().replace('-', '_')
        try:
            if '.' in value:
                stats[key] = float(value)
            else:
                stats[key] = int(value)
        except ValueError:
            stats[key] = value

    return stats

# ==================== DATASETS API PARSER ====================


# ==================== ENA FETCHER ====================

def fetch_ena_assembly(accession):
    try:
        response = metadata_get(f'https://www.ebi.ac.uk/ena/browser/api/xml/{accession}', timeout=15)
        if not response.ok:
            return None
        return parse_ena_xml(response.content, accession)
    except Exception as exc:
        print(f'ENA fetch error: {type(exc).__name__}')
        return None

# ==================== BIOSAMPLE FETCHER (NEW) ====================

def fetch_biosample_data(biosample_accession):
    """Fetch BioSample metadata from NCBI"""
    if not biosample_accession:
        return None

    try:
        # Search for BioSample UID
        search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=biosample&term={biosample_accession}&retmode=json"
        search_resp = rate_limited_request(search_url)
        search_data = search_resp.json()

        if not search_data.get('esearchresult', {}).get('idlist'):
            return None

        uid = search_data['esearchresult']['idlist'][0]

        # Fetch summary
        summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=biosample&id={uid}&retmode=json"
        summary_resp = rate_limited_request(summary_url)
        summary_data = summary_resp.json().get('result', {}).get(str(uid), {})

        # Parse sampledata XML if present
        biosample_info = {
            'accession': biosample_accession,
            'uid': uid,
            'title': summary_data.get('title'),
            'organism': summary_data.get('organism'),
            'tax_id': summary_data.get('taxonomy'),
            'submitter': summary_data.get('organization'),
            'submission_date': summary_data.get('date'),
            'publication_date': summary_data.get('publicationdate'),
            'modification_date': summary_data.get('modificationdate'),
            'package': summary_data.get('package'),
            'attributes': {},
            'description': None,
            'links': {}
        }

        # Parse the sampledata XML for detailed info
        sample_data_xml = summary_data.get('sampledata', '')
        if sample_data_xml:
            try:
                root = ET.fromstring(sample_data_xml)

                for elem in root.iter():
                    tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag

                    if tag == 'Title':
                        if not biosample_info['title']:
                            biosample_info['title'] = elem.text
                    elif tag == 'Description':
                        # Look for Paragraph inside Description
                        for child in elem.iter():
                            child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                            if child_tag == 'Paragraph' and child.text:
                                biosample_info['description'] = child.text
                    elif tag == 'Attribute':
                        attr_name = elem.get('attribute_name') or elem.get('harmonized_name')
                        if attr_name:
                            biosample_info['attributes'][attr_name] = elem.text
                    elif tag == 'Link':
                        link_type = elem.get('type')
                        link_target = elem.get('target')
                        link_label = elem.get('label')
                        if link_target:
                            biosample_info['links'][link_target] = {
                                'type': link_type,
                                'label': link_label,
                                'value': elem.text
                            }
            except Exception as e:
                print(f"BioSample XML parse error: {e}")

        # Also check infraspecies field
        infraspecies = summary_data.get('infraspecies', '')
        if infraspecies and ':' in infraspecies:
            for item in infraspecies.split(';'):
                key, separator, value = item.partition(':')
                if separator and key.strip():
                    biosample_info['attributes'].setdefault(key.strip(), value.strip())

        return biosample_info

    except Exception as e:
        print(f"BioSample fetch error: {e}")
        return None

# ==================== ORGANISM NAME SEARCH ====================

def search_assemblies_by_organism(organism_name, max_results=20):
    """Search NCBI Assembly database by organism name"""
    try:
        search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=assembly&term={organism_name.replace(' ', '+')}[ORGN]&retmode=json&sort=date&retmax={max_results}"
        search_resp = rate_limited_request(search_url)
        search_data = search_resp.json()

        ids = search_data.get('esearchresult', {}).get('idlist', [])
        if not ids:
            return []

        assemblies_list = []

        for uid in ids:
            summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=assembly&id={uid}&retmode=json"
            summary_resp = rate_limited_request(summary_url)
            summary_data = summary_resp.json()
            result = summary_data.get('result', {}).get(str(uid), {})

            if not result:
                continue

            meta_xml = result.get('meta', '')
            meta_stats = parse_meta_xml(meta_xml)

            assembly_info = {
                'uid': uid,
                'accession': result.get('assemblyaccession'),
                'assembly_name': result.get('assemblyname'),
                'organism': result.get('organism'),
                'tax_id': result.get('taxid'),
                'species_name': result.get('speciesname'),
                'assembly_status': result.get('assemblystatus'),
                'assembly_level': result.get('assemblylevel'),
                'refseq_category': result.get('refseq_category'),
                'submission_date': result.get('submissiondate'),
                'last_update_date': result.get('lastupdatedate'),
                'submitter': result.get('submitterorganization'),
                'coverage': result.get('coverage'),
                'biosample': result.get('biosampleaccn'),
                'bioproject': result.get('bioproject'),
                'ftppath_genbank': result.get('ftppath_genbank'),
                'ftppath_refseq': result.get('ftppath_refseq'),
                'ftppath_stats_rpt': result.get('ftppath_stats_rpt'),
                'genome_size_bp': meta_stats.get('total_sequence_length') or meta_stats.get('total_length'),
                'contig_n50': meta_stats.get('contig_n50'),
                'scaffold_n50': meta_stats.get('scaffold_n50'),
                'number_of_contigs': meta_stats.get('contig_count'),
                'number_of_scaffolds': meta_stats.get('scaffold_count'),
                'number_of_chromosomes': meta_stats.get('chromosome_count'),
                'ungapped_length': meta_stats.get('ungapped_length'),
                'coverage': result.get('coverage') if result.get('coverage') else None,
            }

            assemblies_list.append(assembly_info)

        return assemblies_list

    except Exception as e:
        print(f"Organism search error: {e}")
        return []

def pick_best_assembly(assemblies_list):
    """Pick the best assembly from a list"""
    if not assemblies_list:
        return None

    def score(asm):
        s = 0
        if asm.get('refseq_category') and asm['refseq_category'] != 'na':
            s += 1000
        if asm.get('assembly_level') in ['Complete Genome', 'Chromosome']:
            s += 500
        elif asm.get('assembly_level') == 'Scaffold':
            s += 200
        elif asm.get('assembly_level') == 'Contig':
            s += 100
        if asm.get('genome_size_bp'):
            s += 50
        if asm.get('coverage'):
            s += 25
        if asm.get('accession', '').startswith('GCF_'):
            s += 10
        acc = asm.get('accession', '')
        try:
            version = float(acc.split('.')[-1]) if '.' in acc else 0
            s += version
        except:
            pass
        return s

    sorted_assemblies = sorted(assemblies_list, key=score, reverse=True)
    return sorted_assemblies[0]

# ==================== CORE ASSEMBLY FETCHER ====================

def get_value(*sources):
    """Get first non-null value from sources"""
    for src in sources:
        if src is not None and src != '' and src != []:
            return src
    return None

def fetch_and_parse_assembly(accession):
    """Core function to fetch and parse assembly data from all sources"""

    accession = accession.strip().upper()
    normalization_warnings = []

    # SOURCE 1: NCBI Datasets API v2
    datasets_data = None
    datasets_parsed = {}
    try:
        datasets_url = f"https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession/{accession}/dataset_report"
        datasets_resp = rate_limited_request(datasets_url)
        if datasets_resp.ok:
            datasets_data = datasets_resp.json()
            datasets_parsed = parse_datasets_api(datasets_data, expected_accession=accession)
            print(f"  Datasets API: {len(datasets_parsed)} fields parsed")
    except Exception as e:
        normalization_warnings.append({"source": "datasets", "error_type": type(e).__name__})
        print(f"  Datasets API error: {type(e).__name__}")

    # SOURCE 2: NCBI ESummary
    esummary_data = None
    meta_stats = {}
    assembly_id = None
    ftp_stats_url = None
    try:
        search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=assembly&term={accession}&retmode=json"
        search_resp = rate_limited_request(search_url)
        search_data = search_resp.json()

        if search_data.get('esearchresult', {}).get('idlist'):
            assembly_id = search_data['esearchresult']['idlist'][0]
            summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=assembly&id={assembly_id}&retmode=json"
            summary_resp = rate_limited_request(summary_url)
            esummary_data = summary_resp.json().get('result', {}).get(assembly_id, {})

            ftp_stats_url = exact_stats_url(accession, esummary_data)
            if esummary_data.get('assemblyaccession') != accession:
                esummary_data = None
                raise ValueError('ESummary assembly accession mismatch')
            meta_xml = esummary_data.get('meta', '')
            meta_stats = parse_meta_xml(meta_xml)
            # The requested database/version determines the FTP directory.
            print(f"  ESummary: ID={assembly_id}, meta has {len(meta_stats)} stats")
    except Exception as e:
        normalization_warnings.append({"source": "esummary", "error_type": type(e).__name__})
        print(f"  ESummary error: {type(e).__name__}")

    # SOURCE 3: NCBI FTP Stats File
    ftp_stats = {}
    try:
        if ftp_stats_url:
            ftp_stats = fetch_ftp_stats(ftp_stats_url) or {}
            identity_key = 'RefSeq assembly accession' if accession.startswith('GCF_') else 'GenBank assembly accession'
            if (ftp_stats.get('headers') or {}).get(identity_key) != accession:
                ftp_stats = {}
                normalization_warnings.append({'source': 'ftp_stats', 'error_type': 'missing_or_mismatched_identity'})
            print(f"  FTP Stats: {len(ftp_stats)} fields parsed")
        else:
            normalization_warnings.append({'source': 'ftp_stats', 'error_type': 'no_exact_accession_url'})
    except Exception as e:
        normalization_warnings.append({"source": "ftp_stats", "error_type": type(e).__name__})
        print(f"  FTP stats error: {type(e).__name__}")

    # SOURCE 4: ENA
    paired_accession = datasets_parsed.get('paired_accession')
    if not paired_accession and esummary_data:
        paired_accession = (esummary_data.get('synonym') or {}).get('genbank')
    ena_accession = accession if accession.startswith('GCA_') else paired_accession
    ena_data = (fetch_ena_assembly(ena_accession)
                if ena_accession and re.fullmatch(r'GCA_\d+\.\d+', ena_accession) else None)
    if ena_data:
        print(f"  ENA: {len(ena_data)} fields parsed")

    # SOURCE 5: BioSample (NEW)
    biosample_accession = get_value(
        datasets_parsed.get('biosample_accession'),
        esummary_data.get('biosampleaccn') if esummary_data else None
    )
    biosample_data = None
    if biosample_accession:
        biosample_data = fetch_biosample_data(biosample_accession)
        if biosample_data:
            print(f"  BioSample: {biosample_accession} fetched with {len(biosample_data.get('attributes', {}))} attributes")

    # MERGE ALL SOURCES
    all_summary = ftp_stats.get('all_summary', {})

    genome_size = get_value(
        datasets_parsed.get('genome_size_bp'),
        meta_stats.get('total_sequence_length'),
        meta_stats.get('total_length'),
        all_summary.get('total_length'),
        all_summary.get('total_sequence_length'),
        esummary_data.get('assemblylength') if esummary_data else None
    )

    genome_size_ungapped = get_value(
        datasets_parsed.get('genome_size_ungapped'),
        meta_stats.get('ungapped_length'),
        all_summary.get('ungapped_length')
    )

    gc_content = get_value(
        datasets_parsed.get('gc_content'),
        meta_stats.get('gc_percent'),
        all_summary.get('gc_perc'),
        all_summary.get('gc_percent')
    )

    gc_count = get_value(
        datasets_parsed.get('gc_count'),
        meta_stats.get('gc_count'),
        all_summary.get('gc_count')
    )
    atgc_count = get_value(
        datasets_parsed.get('atgc_count'),
        meta_stats.get('atgc_count'),
        all_summary.get('atgc_count')
    )

    if gc_content is None and gc_count is not None and atgc_count:
        gc_content = round((gc_count / atgc_count) * 100, 2)

    coverage = get_value(
        datasets_parsed.get('genome_coverage'),
        esummary_data.get('coverage') if esummary_data else None,
        meta_stats.get('coverage')
    )

    contig_n50 = get_value(
        datasets_parsed.get('contig_n50'),
        meta_stats.get('contig_n50'),
        all_summary.get('contig_n50'),
        esummary_data.get('contign50') if esummary_data else None
    )

    contig_l50 = get_value(
        datasets_parsed.get('contig_l50'),
        meta_stats.get('contig_l50'),
        all_summary.get('contig_l50')
    )

    scaffold_n50 = get_value(
        datasets_parsed.get('scaffold_n50'),
        meta_stats.get('scaffold_n50'),
        all_summary.get('scaffold_n50'),
        esummary_data.get('scaffoldn50') if esummary_data else None
    )

    scaffold_l50 = get_value(
        datasets_parsed.get('scaffold_l50'),
        meta_stats.get('scaffold_l50'),
        all_summary.get('scaffold_l50')
    )

    num_contigs = get_value(
        datasets_parsed.get('number_of_contigs'),
        meta_stats.get('contig_count'),
        all_summary.get('contig_count')
    )

    num_scaffolds = get_value(
        datasets_parsed.get('number_of_scaffolds'),
        meta_stats.get('scaffold_count'),
        all_summary.get('scaffold_count')
    )

    num_chromosomes = get_value(
        datasets_parsed.get('number_of_chromosomes'),
        meta_stats.get('chromosome_count'),
        all_summary.get('chromosome_count')
    )

    gaps = get_value(
        datasets_parsed.get('gaps_between_scaffolds'),
        meta_stats.get('gaps_between_scaffolds_count'),
        all_summary.get('gaps_between_scaffolds')
    )

    result = {
        'accession': accession,
        'assembly_id': assembly_id,

        'genome_size_bp': genome_size,
        'genome_size_mb': round(genome_size / 1_000_000, 2) if genome_size else None,
        'genome_size_ungapped_bp': genome_size_ungapped,
        'genome_size_ungapped_mb': round(genome_size_ungapped / 1_000_000, 2) if genome_size_ungapped else None,
        'gc_content': gc_content,
        'gc_count': gc_count,
        'atgc_count': atgc_count,
        'genome_coverage': coverage,

        'contig_n50': contig_n50,
        'contig_l50': contig_l50,
        'scaffold_n50': scaffold_n50,
        'scaffold_l50': scaffold_l50,
        'number_of_contigs': num_contigs,
        'number_of_scaffolds': num_scaffolds,
        'number_of_chromosomes': num_chromosomes,
        'gaps_between_scaffolds': gaps,
        'number_of_component_sequences': get_value(
            datasets_parsed.get('number_of_component_sequences'),
            meta_stats.get('number_of_component_sequences')
        ),
        'number_of_organelles': datasets_parsed.get('number_of_organelles'),

        'organism_name': get_value(
            datasets_parsed.get('organism_name'),
            esummary_data.get('organism') if esummary_data else None,
            ena_data.get('scientific_name') if ena_data else None
        ),
        'common_name': get_value(
            datasets_parsed.get('common_name'),
            esummary_data.get('commonname') if esummary_data else None,
            ena_data.get('common_name') if ena_data else None
        ),
        'tax_id': get_value(
            datasets_parsed.get('tax_id'),
            esummary_data.get('taxid') if esummary_data else None,
            ena_data.get('tax_id') if ena_data else None
        ),

        'assembly_name': get_value(
            datasets_parsed.get('assembly_name'),
            esummary_data.get('assemblyname') if esummary_data else None
        ),
        'assembly_level': get_value(
            datasets_parsed.get('assembly_level'),
            esummary_data.get('assemblystatus') if esummary_data else None
        ),
        'assembly_type': get_value(
            datasets_parsed.get('assembly_type'),
            ena_data.get('assembly_type') if ena_data else None
        ),
        'assembly_status': datasets_parsed.get('assembly_status'),
        'description': get_value(
            datasets_parsed.get('description'),
            ena_data.get('description') if ena_data else None
        ),
        'submitter': get_value(
            datasets_parsed.get('submitter'),
            esummary_data.get('submitterorganization') if esummary_data else None
        ),
        'submission_date': get_value(
            datasets_parsed.get('submission_date'),
            esummary_data.get('submissiondate') if esummary_data else None,
            ena_data.get('submission_date') if ena_data else None
        ),
        'release_date': get_value(
            datasets_parsed.get('release_date'),
            esummary_data.get('seqreleasedate') if esummary_data else None
        ),
        'last_update_date': esummary_data.get('lastupdatedate') if esummary_data else None,
        'synonym': datasets_parsed.get('synonym'),

        'assembly_method': get_value(
            datasets_parsed.get('assembly_method'),
            esummary_data.get('assemblymethod') if esummary_data else None
        ),
        'sequencing_technology': get_value(
            datasets_parsed.get('sequencing_technology'),
            esummary_data.get('sequencingtechnology') if esummary_data else None
        ),
        'refseq_category': get_value(
            datasets_parsed.get('refseq_category'),
            esummary_data.get('refseq_category') if esummary_data else None
        ),
        'genome_representation': ena_data.get('genome_representation') if ena_data else None,

        'biosample_accession': biosample_accession,
        'bioproject_accession': get_value(
            datasets_parsed.get('bioproject_accession'),
            esummary_data.get('bioproject') if esummary_data else None
        ),
        'wgs_project': datasets_parsed.get('wgs_project'),
        'current_accession': datasets_parsed.get('current_accession'),
        'paired_accession': datasets_parsed.get('paired_accession'),
        'source_database': datasets_parsed.get('source_database'),

        'strain': get_value(
            datasets_parsed.get('strain'),
            esummary_data.get('strain') if esummary_data else None
        ),
        'isolate': get_value(
            datasets_parsed.get('isolate'),
            esummary_data.get('isolate') if esummary_data else None
        ),

        'annotation_provider': datasets_parsed.get('annotation_provider'),
        'annotation_date': datasets_parsed.get('annotation_date'),
        'annotation_name': datasets_parsed.get('annotation_name'),
        'annotation_method': datasets_parsed.get('annotation_method'),
        'annotation_pipeline': datasets_parsed.get('annotation_pipeline'),
        'annotation_software_version': datasets_parsed.get('annotation_software_version'),
        'annotation_status': datasets_parsed.get('annotation_status'),
        'total_genes': datasets_parsed.get('total_genes'),
        'protein_coding_genes': datasets_parsed.get('protein_coding_genes'),
        'non_coding_genes': datasets_parsed.get('non_coding_genes'),
        'pseudogenes': datasets_parsed.get('pseudogenes'),
        'other_genes': datasets_parsed.get('other_genes'),

        'ncbi_url': f"https://www.ncbi.nlm.nih.gov/datasets/genome/{accession}/",
        'ena_url': f"https://www.ebi.ac.uk/ena/browser/view/{accession}",
        'ftp_path': esummary_data.get('ftppath_genbank') if esummary_data else None,
        'ftp_path_refseq': esummary_data.get('ftppath_refseq') if esummary_data else None,

        'ena_data': ena_data,
        'biosample_data': biosample_data,  # NEW

        'fetched_at': datetime.utcnow().isoformat(),
        'from_cache': False
    }

    return finalize_assembly(
        result, datasets_parsed, esummary_data, ftp_stats, normalization_warnings,
        ASSEMBLY_CACHE_SCHEMA_VERSION, ena_accession)

# ==================== ERROR / VALIDATION HELPERS ====================

def api_error(message, error_code, status_code, query=None):
    response = {
        'error_code': error_code,
        'message': message
    }

    if query is not None:
        response['query'] = query

    return jsonify(response), status_code


def is_valid_assembly_accession(value):
    """Validate RefSeq/GenBank assembly accession format."""
    return bool(
        re.fullmatch(
            r'GC[FA]_\d+\.\d+',
            value.strip(),
            re.IGNORECASE
        )
    )

def is_valid_nucleotide_accession(value):
    """Validate common NCBI nucleotide accession formats."""
    return bool(
        re.fullmatch(
            r'(?:AC|AP|AY|BK|CP|CR|DQ|EU|FJ|FM|FN|FO|FR|HE|HQ|JF|JQ|'
            r'JN|KC|KF|KM|KP|KX|KY|LC|LN|LR|MF|MG|MH|MK|MN|MT|MW|'
            r'NC|NG|NM|NR|NT|NW|NZ|ON|OP|OQ|OR|OX|'
            r'BC|BT|BU|BX|U|V|X|Y|Z|'
            r'N[CGMRW]|[A-Z]{2})_\d+(?:\.\d+)?',
            value.strip(),
            re.IGNORECASE
        )
    )


def is_valid_protein_accession(value):
    """Validate common NCBI protein accession formats."""
    return bool(
        re.fullmatch(
            r'(?:NP|XP|YP|WP|AP|ZP|[A-Z]{3})_\d+\.\d+',
            value.strip(),
            re.IGNORECASE
        )
    )

def is_valid_gene_id(value):
    """Validate an NCBI Gene ID."""
    return value.strip().isdigit()

def handle_database_error(query):
    return api_error(
        "Temporary database/cache error.",
        "E7",
        503,
        query
    )

# ==================== Routes / Assembly ====================

@app.route('/api/assembly/<accession>', methods=['GET'])
def get_assembly(accession):
    accession = accession.strip().upper()
    """Fetch assembly data by accession"""
    if not accession:
        return api_error(
            "Please enter a search query.",
            "E1",
            400,
            accession
        )

    if not is_valid_assembly_accession(accession):
        return api_error(
            "Invalid accession or no matching record found.",
            "E3",
            400,
            accession
        )
    cached = assemblies.find_one({'accession': accession,
                                  'cache_schema_version': ASSEMBLY_CACHE_SCHEMA_VERSION,
                                  'cache_eligible': True})
    if cached:
        print(f"✓ Cache HIT: assembly/{accession}")
        cached['_id'] = str(cached['_id'])
        cached['from_cache'] = True
        return jsonify(cached)

    print(f"⚠ Cache MISS: assembly/{accession}")

    try:
        result = fetch_and_parse_assembly(accession)
        if result.get('cache_eligible'):
            assemblies.replace_one({'accession': accession}, result.copy(), upsert=True)
        result['_id'] = str(result.get('_id', ''))
        return jsonify(result)

    # except Exception as e:
    #     import traceback
    #     traceback.print_exc()
    #     return jsonify({'error': str(e), 'accession': accession}), 500

    except Exception as e:
        import traceback
        traceback.print_exc()

        return api_error(
            "An unexpected server error occurred.",
            "E4",
            500,
            accession
        )


# ==================== ORGANISM SEARCH ENDPOINT ====================

@app.route('/api/organism/<path:organism_name>', methods=['GET'])
def search_by_organism(organism_name):
    """Search for assemblies by organism name"""
    organism_name = organism_name.replace('%20', ' ')

    cached = organism_searches.find_one({'organism_name': organism_name,
                                         'cache_schema_version': ASSEMBLY_CACHE_SCHEMA_VERSION,
                                         'assembly_data.cache_eligible': True})
    if cached:
        print(f"✓ Cache HIT: organism/{organism_name}")
        cached['_id'] = str(cached['_id'])
        cached['from_cache'] = True
        return jsonify(cached)

    print(f"⚠ Cache MISS: organism/{organism_name}")

    try:
        assemblies_list = search_assemblies_by_organism(organism_name, max_results=20)

        # if not assemblies_list:
        #     return jsonify({
        #         'error': f'No assemblies found for organism: {organism_name}',
        #         'organism_name': organism_name
        #     }), 404

        if not assemblies_list:
            return api_error(
                f"No matching record found for '{organism_name}'.",
                "E2",
                404,
                organism_name
            )
        best = pick_best_assembly(assemblies_list)
        best_accession = best.get('accession')

        print(f"  Best assembly selected: {best_accession}")

        full_data = fetch_and_parse_assembly(best_accession)

        result = {
            'organism_name': organism_name,
            'best_assembly': {
                'accession': best_accession,
                'assembly_name': best.get('assembly_name'),
                'assembly_level': best.get('assembly_level'),
                'assembly_status': best.get('assembly_status'),
                'refseq_category': best.get('refseq_category'),
                'coverage': best.get('coverage'),
                'submitter': best.get('submitter'),
                'submission_date': best.get('submission_date'),
            },
            'total_assemblies_found': len(assemblies_list),
            'all_assemblies': [
                {
                    'accession': a.get('accession'),
                    'assembly_name': a.get('assembly_name'),
                    'assembly_level': a.get('assembly_level'),
                    'assembly_status': a.get('assembly_status'),
                    'refseq_category': a.get('refseq_category'),
                    'genome_size_bp': a.get('genome_size_bp'),
                    'coverage': a.get('coverage'),
                    'submission_date': a.get('submission_date'),
                }
                for a in assemblies_list
            ],
            'assembly_data': full_data,
            'fetched_at': datetime.utcnow().isoformat(),
            'from_cache': False
        }

        result['cache_schema_version'] = ASSEMBLY_CACHE_SCHEMA_VERSION
        if full_data.get('cache_eligible'):
            organism_searches.replace_one({'organism_name': organism_name}, result.copy(), upsert=True)
        result['_id'] = str(result.get('_id', ''))
        return jsonify(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'organism_name': organism_name}), 500

register_metadata_download(app, fetch_and_parse_assembly)
get_gene_by_id, get_gene_by_symbol = register_gene_routes(app)


get_nucleotide = register_nucleotide_routes(app)

# ==================== GENE ====================


        # return api_error(
        #     "An unexpected server error occurred.",
        #     "E6",
        #     500,
        #     symbol
        # )



# ==================== PROTEIN ====================
get_protein = register_protein_routes(app)

# ==================== TAXONOMY ====================
get_taxonomy = register_taxonomy_routes(app)

# ==================== SMART SEARCH ====================



# ==================== GET SEARCH WITH QUERY PARAMS ====================

@app.route('/search/', methods=['GET'], strict_slashes=False)
def search_by_params():
    database = request.args.get('database')
    accession_ids = request.args.get('accession_ids') or request.args.get('query')

    if not database or not accession_ids:
        return jsonify({'error': 'Missing database or accession_ids parameter'}), 400

    if database == 'assembly':
        return get_assembly(accession_ids)
    elif database == 'organism':
        return search_by_organism(accession_ids)
    elif database == 'nucleotide':
        return get_nucleotide(accession_ids)
    elif database == 'protein':
        return get_protein(accession_ids)
    elif database == 'gene':
        if accession_ids.isdigit():
            return get_gene_by_id(accession_ids)
        else:
            return get_gene_by_symbol(accession_ids)
    elif database == 'taxonomy':
        return get_taxonomy(accession_ids)
    else:
        return jsonify({'error': f'Unknown database: {database}'}), 400


# ==================== UTILITY ====================

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'databases': {
            'assemblies': assemblies.count_documents({}),
            'organism_searches': organism_searches.count_documents({}),
            'nucleotides': nucleotides.count_documents({}),
            'genes': genes.count_documents({}),
            'proteins': proteins.count_documents({}),
            'taxonomies': taxonomies.count_documents({})
        }
    })

# ==================== DOWNLOAD DATABASE ====================
@app.route('/api/download/genbank/<database>/<accession>', methods=['GET'])
def download_genbank(database, accession):

    try:
        database_map = {
            'nucleotide': 'nuccore',
            'protein': 'protein'
        }

        ncbi_db = database_map.get(database)

        if not ncbi_db:
            return jsonify({
                'error': 'GenBank download is supported only for nucleotide and protein'
            }), 400

        url = (
            "https://eutils.ncbi.nlm.nih.gov/"
            "entrez/eutils/efetch.fcgi"
            f"?db={ncbi_db}"
            f"&id={accession}"
            f"&rettype={'gp' if database == 'protein' else 'gb'}"
            f"&retmode=text"
        )

        response = rate_limited_request(url)

        if not response.ok or not response.content.strip():
            return jsonify({
                'error': 'Unable to retrieve GenBank record',
                'accession': accession
            }), 502

        return send_file(
            BytesIO(response.content),
            mimetype='text/plain',
            as_attachment=True,
            download_name=f"{accession}.{'gp' if database == 'protein' else 'gb'}"
        )

    except Exception as e:

        import traceback
        traceback.print_exc()

        return jsonify({
            'error': str(e),
            'accession': accession
        }), 500


def api_error(message, error_code, status_code, query=None):
    response = {
        "error_code": error_code,
        "message": message,
    }

    if query is not None:
        response["query"] = query

    return jsonify(response), status_code

register_excel_export(app)

register_smart_search(app, {
    'assembly': get_assembly, 'organism': search_by_organism,
    'gene_id': get_gene_by_id, 'gene_symbol': get_gene_by_symbol,
    'nucleotide': get_nucleotide, 'protein': get_protein,
    'taxonomy': get_taxonomy,
})

if __name__ == '__main__':
    app.run(debug=True, port=5001)
