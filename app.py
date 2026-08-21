"""
NCBI Multi-Database Backend with MongoDB Caching
Supports: Assembly, Nucleotide, Gene, Protein, Taxonomy
"""

# from flask import Flask, request, jsonify
# from flask_cors import CORS
# from pymongo import MongoClient
# import requests
# from datetime import datetime
# import time
# import os
# import re
# from dotenv import load_dotenv

# load_dotenv()

# app = Flask(__name__)
# CORS(app)


# CORS(app, resources={
#     r"/api/*": {
#         "origins": ["http://localhost:5173", "http://127.0.0.1:5173"],
#         "methods": ["GET", "POST", "OPTIONS"],
#         "allow_headers": ["Content-Type", "Authorization"]
#     }
# })

# Explicit CORS
# CORS(app, resources={
#     r"/api/*": {
#         "origins": ["http://localhost:5173", "http://127.0.0.1:5173"],
#         "methods": ["GET", "POST", "OPTIONS"],
#         "allow_headers": ["Content-Type", "Authorization"]
#     }
# })

# # Safety net: add CORS headers to ALL responses including errors
# @app.after_request
# def after_request(response):
#     response.headers.add('Access-Control-Allow-Origin', 'http://localhost:5173')
#     response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
#     response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
#     return response

# # Handle OPTIONS preflight explicitly for all routes
# @app.route('/api/<path:path>', methods=['OPTIONS'])
# def handle_options(path):
#     response = make_response()
#     response.headers.add('Access-Control-Allow-Origin', 'http://localhost:5173')
#     response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
#     response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
#     return response


# # MongoDB
# MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
# client = MongoClient(MONGODB_URI)
# db = client.ncbi_cache

# # Collections for each database
# assemblies = db.assemblies
# nucleotides = db.nucleotides
# genes = db.genes
# proteins = db.proteins
# taxonomies = db.taxonomies

# # Create indexes
# assemblies.create_index('accession', unique=True)
# nucleotides.create_index('accession', unique=True)
# genes.create_index([('symbol', 1), ('tax_id', 1)], unique=True)
# proteins.create_index('accession', unique=True)
# taxonomies.create_index('tax_id', unique=True)

# # Rate limiting
# last_request_time = 0
# MIN_REQUEST_INTERVAL = 0.35
# NCBI_API_KEY = os.getenv('NCBI_API_KEY', '')

# def rate_limited_request(url):
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
#     return requests.get(url, timeout=30)

# def detect_database_type(query):
#     """Auto-detect database type from query string"""
#     query = query.strip()
    
#     # Assembly accessions
#     if re.match(r'^GC[FA]_\d+\.\d+$', query):
#         return 'assembly'
    
#     # Nucleotide accessions
#     if re.match(r'^N[CGMRW]_\d+\.\d+$', query):
#         return 'nucleotide'
    
#     # Protein accessions
#     if re.match(r'^[NYXWAZ]P_\d+\.\d+$', query):
#         return 'protein'
    
#     # Gene ID (numeric)
#     if re.match(r'^\d+$', query):
#         return 'gene'
    
#     # Tax ID or gene symbol
#     if query.isdigit():
#         return 'taxonomy'
    
#     # Gene symbol (letters, possibly with numbers)
#     if re.match(r'^[A-Z][A-Z0-9\-]+$', query, re.IGNORECASE):
#         return 'gene'
    
#     # Organism name (spaces)
#     if ' ' in query:
#         return 'taxonomy'
    
#     return 'unknown'

# # ==================== ASSEMBLY ====================

# @app.route('/api/assembly/<accession>', methods=['GET'])
# def get_assembly(accession):
#     """Fetch assembly data"""
#     cached = assemblies.find_one({'accession': accession})
#     if cached:
#         print(f"✓ Cache HIT: assembly/{accession}")
#         cached['_id'] = str(cached['_id'])
#         cached['from_cache'] = True
#         return jsonify(cached)
    
#     print(f"⚠ Cache MISS: assembly/{accession}")
    
#     try:
#         # Your existing assembly fetch code here
#         datasets_url = f"https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession/{accession}/dataset_report"
#         datasets_resp = rate_limited_request(datasets_url)
#         datasets_data = datasets_resp.json() if datasets_resp.ok else None
        
#         search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=assembly&term={accession}&retmode=json"
#         search_resp = rate_limited_request(search_url)
#         search_data = search_resp.json()
        
#         esummary_data = None
#         if search_data.get('esearchresult', {}).get('idlist'):
#             assembly_id = search_data['esearchresult']['idlist'][0]
#             summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=assembly&id={assembly_id}&retmode=json"
#             summary_resp = rate_limited_request(summary_url)
#             esummary_data = summary_resp.json().get('result', {}).get(assembly_id)
        
#         result = {
#             'accession': accession,
#             'datasets_data': datasets_data,
#             'esummary_data': esummary_data,
#             'fetched_at': datetime.utcnow().isoformat(),
#             'from_cache': False
#         }
        
#         assemblies.insert_one(result.copy())
#         result['_id'] = str(result.get('_id', ''))
#         return jsonify(result)
        
#     except Exception as e:
#         return jsonify({'error': str(e), 'accession': accession}), 500

# # ==================== NUCLEOTIDE ====================

# @app.route('/api/nucleotide/<accession>', methods=['GET'])
# def get_nucleotide(accession):
#     """Fetch nucleotide/sequence data"""
#     cached = nucleotides.find_one({'accession': accession})
#     if cached:
#         print(f"✓ Cache HIT: nucleotide/{accession}")
#         cached['_id'] = str(cached['_id'])
#         cached['from_cache'] = True
#         return jsonify(cached)
    
#     print(f"⚠ Cache MISS: nucleotide/{accession}")
    
#     try:
#         # Search for UID
#         search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=nuccore&term={accession}&retmode=json"
#         search_resp = rate_limited_request(search_url)
#         search_data = search_resp.json()
        
#         if not search_data.get('esearchresult', {}).get('idlist'):
#             return jsonify({'error': 'Accession not found', 'accession': accession}), 404
        
#         uid = search_data['esearchresult']['idlist'][0]
        
#         # Get summary
#         summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=nuccore&id={uid}&retmode=json"
#         summary_resp = rate_limited_request(summary_url)
#         summary_data = summary_resp.json().get('result', {}).get(uid, {})
        
#         # Get detailed record (GenBank format in XML)
#         fetch_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nuccore&id={uid}&rettype=gb&retmode=xml"
#         fetch_resp = rate_limited_request(fetch_url)
#         fetch_data = fetch_resp.text
        
#         result = {
#             'accession': accession,
#             'esummary_data': summary_data,
#             'efetch_data': fetch_data,
#             'fetched_at': datetime.utcnow().isoformat(),
#             'from_cache': False
#         }
        
#         nucleotides.insert_one(result.copy())
#         result['_id'] = str(result.get('_id', ''))
#         return jsonify(result)
        
#     except Exception as e:
#         return jsonify({'error': str(e), 'accession': accession}), 500

# # ==================== GENE ====================

# @app.route('/api/gene/symbol/<symbol>', methods=['GET'])
# def get_gene_by_symbol(symbol):
#     """Fetch gene data by symbol"""
#     organism = request.args.get('organism', 'human')
    
#     # Create cache key
#     cache_key = f"{symbol}_{organism}"
#     cached = genes.find_one({'cache_key': cache_key})
#     if cached:
#         print(f"✓ Cache HIT: gene/{symbol} ({organism})")
#         cached['_id'] = str(cached['_id'])
#         cached['from_cache'] = True
#         return jsonify(cached)
    
#     print(f"⚠ Cache MISS: gene/{symbol} ({organism})")
    
#     try:
#         # Try Datasets API first (better for genes)
#         datasets_url = f"https://api.ncbi.nlm.nih.gov/datasets/v2/gene/symbol/{symbol}/taxon/{organism}/dataset_report"
#         datasets_resp = rate_limited_request(datasets_url)
#         datasets_data = datasets_resp.json() if datasets_resp.ok else None
        
#         # Fallback to E-utilities
#         search_term = f"{symbol}[Gene Name] AND {organism}[Organism]"
#         search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=gene&term={search_term}&retmode=json"
#         search_resp = rate_limited_request(search_url)
#         search_data = search_resp.json()
        
#         esummary_data = None
#         if search_data.get('esearchresult', {}).get('idlist'):
#             gene_id = search_data['esearchresult']['idlist'][0]
#             summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=gene&id={gene_id}&retmode=json"
#             summary_resp = rate_limited_request(summary_url)
#             esummary_data = summary_resp.json().get('result', {}).get(gene_id, {})
        
#         result = {
#             'cache_key': cache_key,
#             'symbol': symbol,
#             'organism': organism,
#             'datasets_data': datasets_data,
#             'esummary_data': esummary_data,
#             'fetched_at': datetime.utcnow().isoformat(),
#             'from_cache': False
#         }
        
#         genes.insert_one(result.copy())
#         result['_id'] = str(result.get('_id', ''))
#         return jsonify(result)
        
#     except Exception as e:
#         return jsonify({'error': str(e), 'symbol': symbol}), 500

# @app.route('/api/gene/id/<gene_id>', methods=['GET'])
# def get_gene_by_id(gene_id):
#     """Fetch gene data by Gene ID"""
#     cached = genes.find_one({'gene_id': gene_id})
#     if cached:
#         print(f"✓ Cache HIT: gene ID {gene_id}")
#         cached['_id'] = str(cached['_id'])
#         cached['from_cache'] = True
#         return jsonify(cached)
    
#     print(f"⚠ Cache MISS: gene ID {gene_id}")
    
#     try:
#         summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=gene&id={gene_id}&retmode=json"
#         summary_resp = rate_limited_request(summary_url)
#         esummary_data = summary_resp.json().get('result', {}).get(gene_id, {})
        
#         result = {
#             'gene_id': gene_id,
#             'esummary_data': esummary_data,
#             'fetched_at': datetime.utcnow().isoformat(),
#             'from_cache': False
#         }
        
#         genes.insert_one(result.copy())
#         result['_id'] = str(result.get('_id', ''))
#         return jsonify(result)
        
#     except Exception as e:
#         return jsonify({'error': str(e), 'gene_id': gene_id}), 500

# # ==================== PROTEIN ====================

# @app.route('/api/protein/<accession>', methods=['GET'])
# def get_protein(accession):
#     """Fetch protein data"""
#     cached = proteins.find_one({'accession': accession})
#     if cached:
#         print(f"✓ Cache HIT: protein/{accession}")
#         cached['_id'] = str(cached['_id'])
#         cached['from_cache'] = True
#         return jsonify(cached)
    
#     print(f"⚠ Cache MISS: protein/{accession}")
    
#     try:
#         search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=protein&term={accession}&retmode=json"
#         search_resp = rate_limited_request(search_url)
#         search_data = search_resp.json()
        
#         if not search_data.get('esearchresult', {}).get('idlist'):
#             return jsonify({'error': 'Protein not found', 'accession': accession}), 404
        
#         uid = search_data['esearchresult']['idlist'][0]
        
#         summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=protein&id={uid}&retmode=json"
#         summary_resp = rate_limited_request(summary_url)
#         summary_data = summary_resp.json().get('result', {}).get(uid, {})
        
#         result = {
#             'accession': accession,
#             'esummary_data': summary_data,
#             'fetched_at': datetime.utcnow().isoformat(),
#             'from_cache': False
#         }
        
#         proteins.insert_one(result.copy())
#         result['_id'] = str(result.get('_id', ''))
#         return jsonify(result)
        
#     except Exception as e:
#         return jsonify({'error': str(e), 'accession': accession}), 500

# # ==================== TAXONOMY ====================

# @app.route('/api/taxonomy/<name_or_id>', methods=['GET'])
# def get_taxonomy(name_or_id):
#     """Fetch taxonomy data by name or Tax ID"""
#     cached = taxonomies.find_one({'query': name_or_id})
#     if cached:
#         print(f"✓ Cache HIT: taxonomy/{name_or_id}")
#         cached['_id'] = str(cached['_id'])
#         cached['from_cache'] = True
#         return jsonify(cached)
    
#     print(f"⚠ Cache MISS: taxonomy/{name_or_id}")
    
#     try:
#         search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=taxonomy&term={name_or_id}&retmode=json"
#         search_resp = rate_limited_request(search_url)
#         search_data = search_resp.json()
        
#         if not search_data.get('esearchresult', {}).get('idlist'):
#             return jsonify({'error': 'Taxonomy not found', 'query': name_or_id}), 404
        
#         tax_id = search_data['esearchresult']['idlist'][0]
        
#         summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=taxonomy&id={tax_id}&retmode=json"
#         summary_resp = rate_limited_request(summary_url)
#         summary_data = summary_resp.json().get('result', {}).get(tax_id, {})
        
#         result = {
#             'query': name_or_id,
#             'tax_id': tax_id,
#             'esummary_data': summary_data,
#             'fetched_at': datetime.utcnow().isoformat(),
#             'from_cache': False
#         }
        
#         taxonomies.insert_one(result.copy())
#         result['_id'] = str(result.get('_id', ''))
#         return jsonify(result)
        
#     except Exception as e:
#         return jsonify({'error': str(e), 'query': name_or_id}), 500

# # ==================== SMART SEARCH ====================

# @app.route('/api/search', methods=['POST'])
# def smart_search():
#     """Auto-detect database and search"""
#     query = request.json.get('query', '')
#     database = detect_database_type(query)
    
#     if database == 'assembly':
#         return get_assembly(query)
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

# @app.route('/search/', methods=['GET'], strict_slashes=False)
# def search_by_params():
#     """Search by query parameters (GET request)"""
#     database = request.args.get('database')           # from ?database=assembly
#     accession_ids = request.args.get('accession_ids') # from ?accession_ids=...
    
#     if not database or not accession_ids:
#         return jsonify({'error': 'Missing database or accession_ids parameter'}), 400
    
#     # Route to the correct handler based on database
#     if database == 'assembly':
#         return get_assembly(accession_ids)
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
#             'nucleotides': nucleotides.count_documents({}),
#             'genes': genes.count_documents({}),
#             'proteins': proteins.count_documents({}),
#             'taxonomies': taxonomies.count_documents({})
#         }
#     })

# @app.route('/api/detect/<query>', methods=['GET'])
# def detect_db(query):
#     """Detect which database a query belongs to"""
#     return jsonify({
#         'query': query,
#         'detected_database': detect_database_type(query)
#     })

# if __name__ == '__main__':
#     app.run(debug=True, port=5001)









# from flask import Flask, request, jsonify
# from flask_cors import CORS
# from pymongo import MongoClient
# import requests
# from datetime import datetime
# import time
# import os
# import re
# import xml.etree.ElementTree as ET
# from dotenv import load_dotenv

# load_dotenv()

# app = Flask(__name__)
# CORS(app)
# # CORS(app, resources={r"/*": {"origins": "http://localhost:5173"}}) 

# # MongoDB
# MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
# client = MongoClient(MONGODB_URI)
# db = client.ncbi_cache

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
# NCBI_API_KEY = os.getenv('NCBI_API_KEY', '1ef10f4cadd8d06a87d8561580419ccaad09')

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
#     if re.match(r'^[A-Z][A-Z0-9\-]+$', query, re.IGNORECASE):
#         return 'gene'
#     if ' ' in query:
#         return 'organism'  # NEW: organism name search
#     return 'unknown'

# # ==================== FTP STATS PARSER ====================

# def parse_ftp_stats_file(stats_text):
#     """Parse NCBI assembly_stats.txt file format"""
#     stats = {}
#     if not stats_text:
#         return stats

#     lines = stats_text.strip().split('\n')

#     for line in lines:
#         line = line.strip()
#         if not line or line.startswith('#'):
#             continue

#         parts = line.split('\t')
#         if len(parts) >= 2:
#             value = parts[-1].strip()
#             key_parts = parts[:-1]

#             if len(key_parts) == 1:
#                 key = key_parts[0].strip().lower().replace(' ', '_').replace('-', '_')
#             else:
#                 stat_name = key_parts[-1].strip().lower().replace(' ', '_').replace('-', '_')
#                 context = '_'.join([p.strip().lower().replace(' ', '_').replace('-', '_') for p in key_parts[:-1] if p.strip()])
#                 key = f"{context}_{stat_name}" if context else stat_name

#             try:
#                 if '.' in value:
#                     stats[key] = float(value)
#                 else:
#                     stats[key] = int(value)
#             except ValueError:
#                 stats[key] = value

#     # Extract "all" summary stats
#     all_stats = {}
#     for line in lines:
#         if not line.strip() or line.startswith('#'):
#             continue
#         parts = line.split('\t')
#         if len(parts) >= 6 and parts[0].strip().lower() == 'all' and parts[1].strip().lower() == 'all':
#             stat_name = parts[4].strip().lower().replace(' ', '_').replace('-', '_')
#             value = parts[5].strip()
#             try:
#                 if '.' in value:
#                     all_stats[stat_name] = float(value)
#                 else:
#                     all_stats[stat_name] = int(value)
#             except ValueError:
#                 all_stats[stat_name] = value

#     stats['all_summary'] = all_stats
#     return stats

# def fetch_ftp_stats(ftp_url):
#     """Fetch and parse assembly stats from NCBI FTP"""
#     if not ftp_url:
#         return None
#     try:
#         https_url = ftp_url.replace('ftp://', 'https://')
#         resp = requests.get(https_url, timeout=30)
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

# def parse_datasets_api(datasets_data):
#     """Parse NCBI Datasets API v2 response"""
#     parsed = {}
#     if not datasets_data or 'reports' not in datasets_data:
#         return parsed

#     reports = datasets_data.get('reports', [])
#     if not reports:
#         return parsed

#     report = reports[0]

#     organism = report.get('organism', {})
#     parsed['organism_name'] = organism.get('sciName') or organism.get('organismName')
#     parsed['common_name'] = organism.get('commonName')
#     parsed['tax_id'] = organism.get('taxId')

#     assembly_info = report.get('assemblyInfo', {})
#     parsed['assembly_level'] = assembly_info.get('assemblyLevel')
#     parsed['assembly_status'] = assembly_info.get('assemblyStatus')
#     parsed['assembly_name'] = assembly_info.get('assemblyName')
#     parsed['assembly_type'] = assembly_info.get('assemblyType')
#     parsed['description'] = assembly_info.get('description')
#     parsed['submitter'] = assembly_info.get('submitter')
#     parsed['submission_date'] = assembly_info.get('submissionDate')
#     parsed['release_date'] = assembly_info.get('releaseDate')
#     parsed['assembly_method'] = assembly_info.get('assemblyMethod')
#     parsed['sequencing_technology'] = assembly_info.get('sequencingTechnology')
#     parsed['refseq_category'] = assembly_info.get('refseqCategory')
#     parsed['biosample_accession'] = assembly_info.get('biosampleAccession')
#     parsed['bioproject_accession'] = assembly_info.get('bioprojectAccession')
#     parsed['strain'] = assembly_info.get('infraspecificNames', {}).get('strain')
#     parsed['isolate'] = assembly_info.get('infraspecificNames', {}).get('isolate')
#     parsed['expected_final_version'] = assembly_info.get('expectedFinalVersion')
#     parsed['synonym'] = assembly_info.get('synonym')

#     assembly_stats = report.get('assemblyStats', {})
#     parsed['genome_size_bp'] = assembly_stats.get('totalSequenceLength')
#     if parsed['genome_size_bp']:
#         parsed['genome_size_mb'] = round(parsed['genome_size_bp'] / 1_000_000, 2)
#     parsed['genome_size_ungapped'] = assembly_stats.get('totalUngappedLength')
#     parsed['gc_content'] = assembly_stats.get('gcPercent')
#     parsed['gc_count'] = assembly_stats.get('gcCount')
#     parsed['atgc_count'] = assembly_stats.get('atgcCount')
#     parsed['genome_coverage'] = assembly_stats.get('genomeCoverage')
#     parsed['number_of_chromosomes'] = assembly_stats.get('totalNumberOfChromosomes')
#     parsed['contig_n50'] = assembly_stats.get('contigN50')
#     parsed['contig_l50'] = assembly_stats.get('contigL50')
#     parsed['number_of_contigs'] = assembly_stats.get('numberOfContigs')
#     parsed['scaffold_n50'] = assembly_stats.get('scaffoldN50')
#     parsed['scaffold_l50'] = assembly_stats.get('scaffoldL50')
#     parsed['number_of_scaffolds'] = assembly_stats.get('numberOfScaffolds')
#     parsed['gaps_between_scaffolds'] = assembly_stats.get('gapsBetweenScaffoldsCount')
#     parsed['number_of_component_sequences'] = assembly_stats.get('numberOfComponentSequences')
#     parsed['number_of_organelles'] = assembly_stats.get('numberOfOrganelles')

#     annotation = report.get('annotationInfo', {})
#     parsed['annotation_provider'] = annotation.get('provider')
#     parsed['annotation_date'] = annotation.get('releaseDate')
#     parsed['annotation_name'] = annotation.get('name')
#     parsed['annotation_method'] = annotation.get('method')
#     parsed['annotation_pipeline'] = annotation.get('pipeline')
#     parsed['annotation_software_version'] = annotation.get('softwareVersion')
#     parsed['annotation_status'] = annotation.get('status')

#     gene_counts = annotation.get('stats', {}).get('geneCounts', {})
#     parsed['total_genes'] = gene_counts.get('total')
#     parsed['protein_coding_genes'] = gene_counts.get('proteinCoding')
#     parsed['non_coding_genes'] = gene_counts.get('nonCoding')
#     parsed['pseudogenes'] = gene_counts.get('pseudogene')
#     parsed['other_genes'] = gene_counts.get('other')

#     wgs = report.get('wgsInfo', {})
#     parsed['wgs_project'] = wgs.get('wgsProjectAccession')

#     paired = report.get('pairedAssembly', {})
#     parsed['paired_accession'] = paired.get('accession')

#     parsed['current_accession'] = report.get('currentAccession')
#     parsed['source_database'] = report.get('sourceDatabase')

#     return parsed

# # ==================== ENA FETCHER ====================

# def fetch_ena_assembly(accession):
#     """Fetch assembly metadata from ENA"""
#     try:
#         url = f"https://www.ebi.ac.uk/ena/browser/api/xml/{accession}"
#         resp = requests.get(url, timeout=15)
#         if not resp.ok:
#             return None

#         root = ET.fromstring(resp.content)
#         ena_data = {}

#         for elem in root.iter():
#             tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag

#             if tag == 'ASSEMBLY':
#                 ena_data['submission_date'] = elem.get('submission_date')
#                 ena_data['last_updated'] = elem.get('last_updated')
#                 ena_data['accession'] = elem.get('accession')
#             elif tag == 'STUDY_REF':
#                 ena_data['study_accession'] = elem.get('accession')
#             elif tag == 'SAMPLE_REF':
#                 ena_data['sample_accession'] = elem.get('accession')
#             elif tag == 'DESCRIPTION':
#                 ena_data['description'] = elem.text
#             elif tag == 'TAXON':
#                 ena_data['tax_id'] = elem.get('taxon_id')
#                 ena_data['scientific_name'] = elem.get('scientific_name')
#                 ena_data['common_name'] = elem.get('common_name')
#             elif tag == 'ASSEMBLY_TYPE':
#                 ena_data['assembly_type'] = elem.text
#             elif tag == 'GENOME_REPRESENTATION':
#                 ena_data['genome_representation'] = elem.text
#             elif tag == 'EXPECTED_FINAL_VERSION':
#                 ena_data['expected_final_version'] = elem.text
#             elif tag == 'CHROMOSOME_LIST':
#                 chromosomes = []
#                 for chrom in elem.iter('CHROMOSOME'):
#                     chromosomes.append({
#                         'name': chrom.get('chromosome_name'),
#                         'type': chrom.get('chromosome_type'),
#                         'accession': chrom.get('accession')
#                     })
#                 ena_data['chromosomes'] = chromosomes

#         return ena_data
#     except Exception as e:
#         print(f"ENA fetch error: {e}")
#         return None

# # ==================== ORGANISM NAME SEARCH (NEW) ====================

# def search_assemblies_by_organism(organism_name, max_results=20):
#     """Search NCBI Assembly database by organism name, return list of assemblies"""
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

#             # Parse meta XML
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
#                 # Stats from meta XML
#                 'genome_size_bp': meta_stats.get('total_sequence_length') or meta_stats.get('total_length'),
#                 'contig_n50': meta_stats.get('contig_n50'),
#                 'scaffold_n50': meta_stats.get('scaffold_n50'),
#                 'number_of_contigs': meta_stats.get('contig_count'),
#                 'number_of_scaffolds': meta_stats.get('scaffold_count'),
#                 'number_of_chromosomes': meta_stats.get('chromosome_count'),
#                 'ungapped_length': meta_stats.get('ungapped_length'),
#                 # Coverage from root
#                 'coverage': result.get('coverage') if result.get('coverage') else None,
#             }

#             assemblies_list.append(assembly_info)

#         return assemblies_list

#     except Exception as e:
#         print(f"Organism search error: {e}")
#         return []

# def pick_best_assembly(assemblies_list):
#     """Pick the best assembly from a list based on priority criteria"""
#     if not assemblies_list:
#         return None

#     # Priority scoring
#     def score(asm):
#         s = 0
#         # Reference genome gets highest priority
#         if asm.get('refseq_category') and asm['refseq_category'] != 'na':
#             s += 1000
#         # Complete genome/Chromosome level
#         if asm.get('assembly_level') in ['Complete Genome', 'Chromosome']:
#             s += 500
#         # Scaffold level
#         elif asm.get('assembly_level') == 'Scaffold':
#             s += 200
#         # Contig level
#         elif asm.get('assembly_level') == 'Contig':
#             s += 100
#         # Has genome size
#         if asm.get('genome_size_bp'):
#             s += 50
#         # Has coverage info
#         if asm.get('coverage'):
#             s += 25
#         # RefSeq (GCF) preferred over GenBank (GCA)
#         if asm.get('accession', '').startswith('GCF_'):
#             s += 10
#         # More recent (higher version number)
#         acc = asm.get('accession', '')
#         try:
#             version = float(acc.split('.')[-1]) if '.' in acc else 0
#             s += version
#         except:
#             pass
#         return s

#     # Sort by score descending
#     sorted_assemblies = sorted(assemblies_list, key=score, reverse=True)
#     return sorted_assemblies[0]

# # ==================== ASSEMBLY ENDPOINT (BULLETPROOF) ====================

# def get_value(*sources):
#     """Get first non-null value from sources"""
#     for src in sources:
#         if src is not None and src != '' and src != []:
#             return src
#     return None

# def fetch_and_parse_assembly(accession):
#     """Core function to fetch and parse assembly data from all sources"""

#     # === SOURCE 1: NCBI Datasets API v2 ===
#     datasets_data = None
#     datasets_parsed = {}
#     try:
#         datasets_url = f"https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession/{accession}/dataset_report"
#         datasets_resp = rate_limited_request(datasets_url)
#         if datasets_resp.ok:
#             datasets_data = datasets_resp.json()
#             datasets_parsed = parse_datasets_api(datasets_data)
#             print(f"  Datasets API: {len(datasets_parsed)} fields parsed")
#     except Exception as e:
#         print(f"  Datasets API error: {e}")

#     # === SOURCE 2: NCBI ESummary ===
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

#             meta_xml = esummary_data.get('meta', '')
#             meta_stats = parse_meta_xml(meta_xml)
#             ftp_stats_url = esummary_data.get('ftppath_stats_rpt')
#             print(f"  ESummary: ID={assembly_id}, meta has {len(meta_stats)} stats")
#     except Exception as e:
#         print(f"  ESummary error: {e}")

#     # === SOURCE 3: NCBI FTP Stats File ===
#     ftp_stats = {}
#     try:
#         if ftp_stats_url:
#             ftp_stats = fetch_ftp_stats(ftp_stats_url)
#             print(f"  FTP Stats: {len(ftp_stats)} fields parsed")
#     except Exception as e:
#         print(f"  FTP stats error: {e}")

#     # === SOURCE 4: ENA ===
#     ena_data = fetch_ena_assembly(accession)
#     if ena_data:
#         print(f"  ENA: {len(ena_data)} fields parsed")

#     # === MERGE ALL SOURCES ===
#     all_summary = ftp_stats.get('all_summary', {})

#     # Genome size
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

#     # GC content
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

#     if gc_content is None and gc_count and genome_size:
#         gc_content = round((gc_count / genome_size) * 100, 2)
#     elif gc_content is None and gc_count and atgc_count:
#         gc_content = round((gc_count / atgc_count) * 100, 2)

#     # Coverage
#     coverage = get_value(
#         datasets_parsed.get('genome_coverage'),
#         esummary_data.get('coverage') if esummary_data else None,
#         meta_stats.get('coverage')
#     )

#     # Assembly stats
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
#             datasets_parsed.get('assembly_status'),
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

#         'biosample_accession': get_value(
#             datasets_parsed.get('biosample_accession'),
#             esummary_data.get('biosampleaccn') if esummary_data else None
#         ),
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

#         'fetched_at': datetime.utcnow().isoformat(),
#         'from_cache': False
#     }

#     return result

# @app.route('/api/assembly/<accession>', methods=['GET'])
# def get_assembly(accession):
#     """Fetch assembly data by accession"""
#     cached = assemblies.find_one({'accession': accession})
#     if cached:
#         print(f"✓ Cache HIT: assembly/{accession}")
#         cached['_id'] = str(cached['_id'])
#         cached['from_cache'] = True
#         return jsonify(cached)

#     print(f"⚠ Cache MISS: assembly/{accession}")

#     try:
#         result = fetch_and_parse_assembly(accession)
#         assemblies.insert_one(result.copy())
#         result['_id'] = str(result.get('_id', ''))
#         return jsonify(result)

#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         return jsonify({'error': str(e), 'accession': accession}), 500


# # ==================== ORGANISM SEARCH ENDPOINT (NEW) ====================

# @app.route('/api/organism/<path:organism_name>', methods=['GET'])
# def search_by_organism(organism_name):
#     """
#     Search for assemblies by organism name.
#     Returns a list of assemblies and the best one.
#     URL: /api/organism/Arabidopsis%20thaliana
#     """
#     organism_name = organism_name.replace('%20', ' ')

#     # Check cache
#     cached = organism_searches.find_one({'organism_name': organism_name})
#     if cached:
#         print(f"✓ Cache HIT: organism/{organism_name}")
#         cached['_id'] = str(cached['_id'])
#         cached['from_cache'] = True
#         return jsonify(cached)

#     print(f"⚠ Cache MISS: organism/{organism_name}")

#     try:
#         # Step 1: Search for assemblies by organism name
#         assemblies_list = search_assemblies_by_organism(organism_name, max_results=20)

#         if not assemblies_list:
#             return jsonify({
#                 'error': f'No assemblies found for organism: {organism_name}',
#                 'organism_name': organism_name
#             }), 404

#         # Step 2: Pick the best assembly
#         best = pick_best_assembly(assemblies_list)
#         best_accession = best.get('accession')

#         print(f"  Best assembly selected: {best_accession}")

#         # Step 3: Fetch full data for the best assembly
#         full_data = fetch_and_parse_assembly(best_accession)

#         # Step 4: Build response
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

#         organism_searches.insert_one(result.copy())
#         result['_id'] = str(result.get('_id', ''))
#         return jsonify(result)

#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         return jsonify({'error': str(e), 'organism_name': organism_name}), 500


# # ==================== NUCLEOTIDE ====================

# @app.route('/api/nucleotide/<accession>', methods=['GET'])
# def get_nucleotide(accession):
#     cached = nucleotides.find_one({'accession': accession})
#     if cached:
#         cached['_id'] = str(cached['_id'])
#         cached['from_cache'] = True
#         return jsonify(cached)

#     try:
#         search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=nuccore&term={accession}&retmode=json"
#         search_resp = rate_limited_request(search_url)
#         search_data = search_resp.json()

#         if not search_data.get('esearchresult', {}).get('idlist'):
#             return jsonify({'error': 'Accession not found', 'accession': accession}), 404

#         uid = search_data['esearchresult']['idlist'][0]

#         summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=nuccore&id={uid}&retmode=json"
#         summary_resp = rate_limited_request(summary_url)
#         summary_data = summary_resp.json().get('result', {}).get(uid, {})

#         result = {
#             'accession': accession,
#             'uid': uid,
#             'title': summary_data.get('title'),
#             'organism': summary_data.get('organism'),
#             'tax_id': summary_data.get('taxid'),
#             'length': summary_data.get('slen'),
#             'molecule_type': summary_data.get('moltype'),
#             'topology': summary_data.get('topology'),
#             'completeness': summary_data.get('completeness'),
#             'create_date': summary_data.get('createdate'),
#             'update_date': summary_data.get('updatedate'),
#             'definition': summary_data.get('defline'),
#             'gene': summary_data.get('gene'),
#             'location': summary_data.get('location'),
#             'genetic_code': summary_data.get('geneticcode'),
#             'segment': summary_data.get('segment'),
#             'fetched_at': datetime.utcnow().isoformat(),
#             'from_cache': False
#         }

#         nucleotides.insert_one(result.copy())
#         result['_id'] = str(result.get('_id', ''))
#         return jsonify(result)

#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         return jsonify({'error': str(e), 'accession': accession}), 500


# # ==================== GENE ====================

# @app.route('/api/gene/symbol/<symbol>', methods=['GET'])
# def get_gene_by_symbol(symbol):
#     organism = request.args.get('organism', 'human')
#     cache_key = f"{symbol}_{organism}"
#     cached = genes.find_one({'cache_key': cache_key})
#     if cached:
#         cached['_id'] = str(cached['_id'])
#         cached['from_cache'] = True
#         return jsonify(cached)

#     try:
#         datasets_url = f"https://api.ncbi.nlm.nih.gov/datasets/v2/gene/symbol/{symbol}/taxon/{organism}/dataset_report"
#         datasets_resp = rate_limited_request(datasets_url)
#         datasets_data = datasets_resp.json() if datasets_resp.ok else None

#         search_term = f"{symbol}[Gene Name] AND {organism}[Organism]"
#         search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=gene&term={search_term}&retmode=json"
#         search_resp = rate_limited_request(search_url)
#         search_data = search_resp.json()

#         esummary_data = None
#         gene_id = None
#         if search_data.get('esearchresult', {}).get('idlist'):
#             gene_id = search_data['esearchresult']['idlist'][0]
#             summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=gene&id={gene_id}&retmode=json"
#             summary_resp = rate_limited_request(summary_url)
#             esummary_data = summary_resp.json().get('result', {}).get(gene_id, {})

#         result = {
#             'cache_key': cache_key,
#             'symbol': symbol,
#             'organism': organism,
#             'gene_id': gene_id,
#             'name': esummary_data.get('name') if esummary_data else None,
#             'description': esummary_data.get('description') if esummary_data else None,
#             'chromosome': esummary_data.get('chromosome') if esummary_data else None,
#             'map_location': esummary_data.get('maplocation') if esummary_data else None,
#             'gene_type': esummary_data.get('type') if esummary_data else None,
#             'summary': esummary_data.get('summary') if esummary_data else None,
#             'aliases': esummary_data.get('otheraliases', '').split(', ') if esummary_data and esummary_data.get('otheraliases') else [],
#             'ensembl_id': esummary_data.get('ensemblgeneid') if esummary_data else None,
#             'mim': esummary_data.get('mim') if esummary_data else None,
#             'fetched_at': datetime.utcnow().isoformat(),
#             'from_cache': False
#         }

#         genes.insert_one(result.copy())
#         result['_id'] = str(result.get('_id', ''))
#         return jsonify(result)

#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         return jsonify({'error': str(e), 'symbol': symbol}), 500

# @app.route('/api/gene/id/<gene_id>', methods=['GET'])
# def get_gene_by_id(gene_id):
#     cached = genes.find_one({'gene_id': gene_id})
#     if cached:
#         cached['_id'] = str(cached['_id'])
#         cached['from_cache'] = True
#         return jsonify(cached)

#     try:
#         summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=gene&id={gene_id}&retmode=json"
#         summary_resp = rate_limited_request(summary_url)
#         esummary_data = summary_resp.json().get('result', {}).get(gene_id, {})

#         result = {
#             'gene_id': gene_id,
#             'name': esummary_data.get('name'),
#             'description': esummary_data.get('description'),
#             'chromosome': esummary_data.get('chromosome'),
#             'map_location': esummary_data.get('maplocation'),
#             'gene_type': esummary_data.get('type'),
#             'summary': esummary_data.get('summary'),
#             'aliases': esummary_data.get('otheraliases', '').split(', ') if esummary_data.get('otheraliases') else [],
#             'ensembl_id': esummary_data.get('ensemblgeneid'),
#             'mim': esummary_data.get('mim'),
#             'fetched_at': datetime.utcnow().isoformat(),
#             'from_cache': False
#         }

#         genes.insert_one(result.copy())
#         result['_id'] = str(result.get('_id', ''))
#         return jsonify(result)

#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         return jsonify({'error': str(e), 'gene_id': gene_id}), 500


# # ==================== PROTEIN ====================

# @app.route('/api/protein/<accession>', methods=['GET'])
# def get_protein(accession):
#     cached = proteins.find_one({'accession': accession})
#     if cached:
#         cached['_id'] = str(cached['_id'])
#         cached['from_cache'] = True
#         return jsonify(cached)

#     try:
#         search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=protein&term={accession}&retmode=json"
#         search_resp = rate_limited_request(search_url)
#         search_data = search_resp.json()

#         if not search_data.get('esearchresult', {}).get('idlist'):
#             return jsonify({'error': 'Protein not found', 'accession': accession}), 404

#         uid = search_data['esearchresult']['idlist'][0]

#         summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=protein&id={uid}&retmode=json"
#         summary_resp = rate_limited_request(summary_url)
#         summary_data = summary_resp.json().get('result', {}).get(uid, {})

#         result = {
#             'accession': accession,
#             'uid': uid,
#             'title': summary_data.get('title'),
#             'organism': summary_data.get('organism'),
#             'tax_id': summary_data.get('taxid'),
#             'length': summary_data.get('slen'),
#             'molecular_weight': summary_data.get('molecularweight'),
#             'molecule_type': summary_data.get('moltype'),
#             'create_date': summary_data.get('createdate'),
#             'update_date': summary_data.get('updatedate'),
#             'definition': summary_data.get('defline'),
#             'gene': summary_data.get('gene'),
#             'gene_id': summary_data.get('geneid'),
#             'fetched_at': datetime.utcnow().isoformat(),
#             'from_cache': False
#         }

#         proteins.insert_one(result.copy())
#         result['_id'] = str(result.get('_id', ''))
#         return jsonify(result)

#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         return jsonify({'error': str(e), 'accession': accession}), 500


# # ==================== TAXONOMY ====================

# @app.route('/api/taxonomy/<name_or_id>', methods=['GET'])
# def get_taxonomy(name_or_id):
#     cached = taxonomies.find_one({'query': name_or_id})
#     if cached:
#         cached['_id'] = str(cached['_id'])
#         cached['from_cache'] = True
#         return jsonify(cached)

#     try:
#         search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=taxonomy&term={name_or_id}&retmode=json"
#         search_resp = rate_limited_request(search_url)
#         search_data = search_resp.json()

#         if not search_data.get('esearchresult', {}).get('idlist'):
#             return jsonify({'error': 'Taxonomy not found', 'query': name_or_id}), 404

#         tax_id = search_data['esearchresult']['idlist'][0]

#         summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=taxonomy&id={tax_id}&retmode=json"
#         summary_resp = rate_limited_request(summary_url)
#         summary_data = summary_resp.json().get('result', {}).get(tax_id, {})

#         result = {
#             'query': name_or_id,
#             'tax_id': tax_id,
#             'scientific_name': summary_data.get('scientificname'),
#             'common_name': summary_data.get('commonname'),
#             'rank': summary_data.get('rank'),
#             'division': summary_data.get('division'),
#             'lineage': summary_data.get('lineage'),
#             'genetic_code': summary_data.get('geneticcode'),
#             'fetched_at': datetime.utcnow().isoformat(),
#             'from_cache': False
#         }

#         taxonomies.insert_one(result.copy())
#         result['_id'] = str(result.get('_id', ''))
#         return jsonify(result)

#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         return jsonify({'error': str(e), 'query': name_or_id}), 500


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

# @app.route('/api/detect/<query>', methods=['GET'])
# def detect_db(query):
#     return jsonify({
#         'query': query,
#         'detected_database': detect_database_type(query)
#     })

# if __name__ == '__main__':
#     app.run(debug=True, port=5000)






####.  Working code with some changes




# from flask import Flask, request, jsonify
# from flask_cors import CORS
# from pymongo import MongoClient
# import requests
# from datetime import datetime
# import time
# import os
# import re
# import xml.etree.ElementTree as ET
# from dotenv import load_dotenv

# load_dotenv()

# app = Flask(__name__)
# CORS(app)


# # Explicit CORS
# # CORS(app, resources={
# #     r"/api/*": {
# #         "origins": ["http://localhost:5173", "http://127.0.0.1:5173"],
# #         "methods": ["GET", "POST", "OPTIONS"],
# #         "allow_headers": ["Content-Type", "Authorization"]
# #     }
# # })

# # MongoDB
# MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
# client = MongoClient(MONGODB_URI)
# db = client.ncbi_cache

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
# NCBI_API_KEY = os.getenv('NCBI_API_KEY', '')

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
#     if re.match(r'^[A-Z][A-Z0-9\-]+$', query, re.IGNORECASE):
#         return 'gene'
#     if ' ' in query:
#         return 'organism'
#     return 'unknown'

# # ==================== FTP STATS PARSER ====================

# def parse_ftp_stats_file(stats_text):
#     """Parse NCBI assembly_stats.txt file format"""
#     stats = {}
#     if not stats_text:
#         return stats

#     lines = stats_text.strip().split('\n')

#     for line in lines:
#         line = line.strip()
#         if not line or line.startswith('#'):
#             continue

#         parts = line.split('\t')
#         if len(parts) >= 2:
#             value = parts[-1].strip()
#             key_parts = parts[:-1]

#             if len(key_parts) == 1:
#                 key = key_parts[0].strip().lower().replace(' ', '_').replace('-', '_')
#             else:
#                 stat_name = key_parts[-1].strip().lower().replace(' ', '_').replace('-', '_')
#                 context = '_'.join([p.strip().lower().replace(' ', '_').replace('-', '_') for p in key_parts[:-1] if p.strip()])
#                 key = f"{context}_{stat_name}" if context else stat_name

#             try:
#                 if '.' in value:
#                     stats[key] = float(value)
#                 else:
#                     stats[key] = int(value)
#             except ValueError:
#                 stats[key] = value

#     # Extract "all" summary stats
#     all_stats = {}
#     for line in lines:
#         if not line.strip() or line.startswith('#'):
#             continue
#         parts = line.split('\t')
#         if len(parts) >= 6 and parts[0].strip().lower() == 'all' and parts[1].strip().lower() == 'all':
#             stat_name = parts[4].strip().lower().replace(' ', '_').replace('-', '_')
#             value = parts[5].strip()
#             try:
#                 if '.' in value:
#                     all_stats[stat_name] = float(value)
#                 else:
#                     all_stats[stat_name] = int(value)
#             except ValueError:
#                 all_stats[stat_name] = value

#     stats['all_summary'] = all_stats
#     return stats

# def fetch_ftp_stats(ftp_url):
#     """Fetch and parse assembly stats from NCBI FTP"""
#     if not ftp_url:
#         return None
#     try:
#         https_url = ftp_url.replace('ftp://', 'https://')
#         resp = requests.get(https_url, timeout=30)
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

# def parse_datasets_api(datasets_data):
#     """Parse NCBI Datasets API v2 response"""
#     parsed = {}
#     if not datasets_data or 'reports' not in datasets_data:
#         return parsed

#     reports = datasets_data.get('reports', [])
#     if not reports:
#         return parsed

#     report = reports[0]

#     organism = report.get('organism', {})
#     parsed['organism_name'] = organism.get('sciName') or organism.get('organismName')
#     parsed['common_name'] = organism.get('commonName')
#     parsed['tax_id'] = organism.get('taxId')

#     assembly_info = report.get('assemblyInfo', {})
#     parsed['assembly_level'] = assembly_info.get('assemblyLevel')
#     parsed['assembly_status'] = assembly_info.get('assemblyStatus')
#     parsed['assembly_name'] = assembly_info.get('assemblyName')
#     parsed['assembly_type'] = assembly_info.get('assemblyType')
#     parsed['description'] = assembly_info.get('description')
#     parsed['submitter'] = assembly_info.get('submitter')
#     parsed['submission_date'] = assembly_info.get('submissionDate')
#     parsed['release_date'] = assembly_info.get('releaseDate')
#     parsed['assembly_method'] = assembly_info.get('assemblyMethod')
#     parsed['sequencing_technology'] = assembly_info.get('sequencingTechnology')
#     parsed['refseq_category'] = assembly_info.get('refseqCategory')
#     parsed['biosample_accession'] = assembly_info.get('biosampleAccession')
#     parsed['bioproject_accession'] = assembly_info.get('bioprojectAccession')
#     parsed['strain'] = assembly_info.get('infraspecificNames', {}).get('strain')
#     parsed['isolate'] = assembly_info.get('infraspecificNames', {}).get('isolate')
#     parsed['expected_final_version'] = assembly_info.get('expectedFinalVersion')
#     parsed['synonym'] = assembly_info.get('synonym')

#     assembly_stats = report.get('assemblyStats', {})
#     parsed['genome_size_bp'] = assembly_stats.get('totalSequenceLength')
#     if parsed['genome_size_bp']:
#         parsed['genome_size_mb'] = round(parsed['genome_size_bp'] / 1_000_000, 2)
#     parsed['genome_size_ungapped'] = assembly_stats.get('totalUngappedLength')
#     parsed['gc_content'] = assembly_stats.get('gcPercent')
#     parsed['gc_count'] = assembly_stats.get('gcCount')
#     parsed['atgc_count'] = assembly_stats.get('atgcCount')
#     parsed['genome_coverage'] = assembly_stats.get('genomeCoverage')
#     parsed['number_of_chromosomes'] = assembly_stats.get('totalNumberOfChromosomes')
#     parsed['contig_n50'] = assembly_stats.get('contigN50')
#     parsed['contig_l50'] = assembly_stats.get('contigL50')
#     parsed['number_of_contigs'] = assembly_stats.get('numberOfContigs')
#     parsed['scaffold_n50'] = assembly_stats.get('scaffoldN50')
#     parsed['scaffold_l50'] = assembly_stats.get('scaffoldL50')
#     parsed['number_of_scaffolds'] = assembly_stats.get('numberOfScaffolds')
#     parsed['gaps_between_scaffolds'] = assembly_stats.get('gapsBetweenScaffoldsCount')
#     parsed['number_of_component_sequences'] = assembly_stats.get('numberOfComponentSequences')
#     parsed['number_of_organelles'] = assembly_stats.get('numberOfOrganelles')

#     annotation = report.get('annotationInfo', {})
#     parsed['annotation_provider'] = annotation.get('provider')
#     parsed['annotation_date'] = annotation.get('releaseDate')
#     parsed['annotation_name'] = annotation.get('name')
#     parsed['annotation_method'] = annotation.get('method')
#     parsed['annotation_pipeline'] = annotation.get('pipeline')
#     parsed['annotation_software_version'] = annotation.get('softwareVersion')
#     parsed['annotation_status'] = annotation.get('status')

#     gene_counts = annotation.get('stats', {}).get('geneCounts', {})
#     parsed['total_genes'] = gene_counts.get('total')
#     parsed['protein_coding_genes'] = gene_counts.get('proteinCoding')
#     parsed['non_coding_genes'] = gene_counts.get('nonCoding')
#     parsed['pseudogenes'] = gene_counts.get('pseudogene')
#     parsed['other_genes'] = gene_counts.get('other')

#     wgs = report.get('wgsInfo', {})
#     parsed['wgs_project'] = wgs.get('wgsProjectAccession')

#     paired = report.get('pairedAssembly', {})
#     parsed['paired_accession'] = paired.get('accession')

#     parsed['current_accession'] = report.get('currentAccession')
#     parsed['source_database'] = report.get('sourceDatabase')

#     return parsed

# # ==================== ENA FETCHER ====================

# def fetch_ena_assembly(accession):
#     """Fetch assembly metadata from ENA"""
#     try:
#         url = f"https://www.ebi.ac.uk/ena/browser/api/xml/{accession}"
#         resp = requests.get(url, timeout=15)
#         if not resp.ok:
#             return None

#         root = ET.fromstring(resp.content)
#         ena_data = {}

#         for elem in root.iter():
#             tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag

#             if tag == 'ASSEMBLY':
#                 ena_data['submission_date'] = elem.get('submission_date')
#                 ena_data['last_updated'] = elem.get('last_updated')
#                 ena_data['accession'] = elem.get('accession')
#             elif tag == 'STUDY_REF':
#                 ena_data['study_accession'] = elem.get('accession')
#             elif tag == 'SAMPLE_REF':
#                 ena_data['sample_accession'] = elem.get('accession')
#             elif tag == 'DESCRIPTION':
#                 ena_data['description'] = elem.text
#             elif tag == 'TAXON':
#                 ena_data['tax_id'] = elem.get('taxon_id')
#                 ena_data['scientific_name'] = elem.get('scientific_name')
#                 ena_data['common_name'] = elem.get('common_name')
#             elif tag == 'ASSEMBLY_TYPE':
#                 ena_data['assembly_type'] = elem.text
#             elif tag == 'GENOME_REPRESENTATION':
#                 ena_data['genome_representation'] = elem.text
#             elif tag == 'EXPECTED_FINAL_VERSION':
#                 ena_data['expected_final_version'] = elem.text
#             elif tag == 'CHROMOSOME_LIST':
#                 chromosomes = []
#                 for chrom in elem.iter('CHROMOSOME'):
#                     chromosomes.append({
#                         'name': chrom.get('chromosome_name'),
#                         'type': chrom.get('chromosome_type'),
#                         'accession': chrom.get('accession')
#                     })
#                 ena_data['chromosomes'] = chromosomes

#         return ena_data
#     except Exception as e:
#         print(f"ENA fetch error: {e}")
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
#                         for child in elem:
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
#             parts = infraspecies.split(':', 1)
#             biosample_info['attributes'][parts[0].strip()] = parts[1].strip()

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

#     # SOURCE 1: NCBI Datasets API v2
#     datasets_data = None
#     datasets_parsed = {}
#     try:
#         datasets_url = f"https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession/{accession}/dataset_report"
#         datasets_resp = rate_limited_request(datasets_url)
#         if datasets_resp.ok:
#             datasets_data = datasets_resp.json()
#             datasets_parsed = parse_datasets_api(datasets_data)
#             print(f"  Datasets API: {len(datasets_parsed)} fields parsed")
#     except Exception as e:
#         print(f"  Datasets API error: {e}")

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

#             meta_xml = esummary_data.get('meta', '')
#             meta_stats = parse_meta_xml(meta_xml)
#             ftp_stats_url = esummary_data.get('ftppath_stats_rpt')
#             print(f"  ESummary: ID={assembly_id}, meta has {len(meta_stats)} stats")
#     except Exception as e:
#         print(f"  ESummary error: {e}")

#     # SOURCE 3: NCBI FTP Stats File
#     ftp_stats = {}
#     try:
#         if ftp_stats_url:
#             ftp_stats = fetch_ftp_stats(ftp_stats_url)
#             print(f"  FTP Stats: {len(ftp_stats)} fields parsed")
#     except Exception as e:
#         print(f"  FTP stats error: {e}")

#     # SOURCE 4: ENA
#     ena_data = fetch_ena_assembly(accession)
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

#     if gc_content is None and gc_count and genome_size:
#         gc_content = round((gc_count / genome_size) * 100, 2)
#     elif gc_content is None and gc_count and atgc_count:
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
#             datasets_parsed.get('assembly_status'),
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

#     return result

# def map_to_frontend_format(data):
#     # --- biosample attributes ---
#     attributes = {}

#     # 1) From imported data (list of {name, value})
#     if 'biosample_attributes' in data and isinstance(data['biosample_attributes'], list):
#         for attr in data['biosample_attributes']:
#             if isinstance(attr, dict) and 'name' in attr and 'value' in attr:
#                 attributes[attr['name']] = attr['value']

#     # 2) From fresh fetch (biosample_data dict with 'attributes')
#     elif 'biosample_data' in data and data['biosample_data']:
#         biosample = data['biosample_data']
#         if 'attributes' in biosample:
#             if isinstance(biosample['attributes'], dict):
#                 attributes.update(biosample['attributes'])
#             elif isinstance(biosample['attributes'], list):
#                 for attr in biosample['attributes']:
#                     if isinstance(attr, dict) and 'name' in attr and 'value' in attr:
#                         attributes[attr['name']] = attr['value']

#     # --- biosample metadata ---
#     biosample_accession = data.get('biosample_accession')
#     biosample_description = None
#     biosample_submitter = data.get('submitter')

#     if 'biosample_data' in data and data['biosample_data']:
#         bs = data['biosample_data']
#         biosample_accession = bs.get('accession') or biosample_accession
#         biosample_description = bs.get('description')
#         biosample_submitter = bs.get('submitter') or biosample_submitter

#     # --- main document ---
#     return {
#         "accession": data.get("accession"),
#         "organism": {
#             "scientific_name": data.get("organism_name"),
#             "common_name": data.get("common_name"),
#             "tax_id": data.get("tax_id"),
#         },
#         "assembly": {
#             "name": data.get("assembly_name"),
#             "level": data.get("assembly_level"),
#             "submission_date": data.get("submission_date"),
#             "last_update": data.get("last_update_date") or data.get("release_date"),
#         },
#         "statistics": {
#             "genome_size_bp": data.get("genome_size_bp"),
#             "genome_size_human": f"{data.get('genome_size_mb')} Mb" if data.get('genome_size_mb') else None,
#             "gc_percent": data.get("gc_content"),
#             "genome_coverage": data.get("genome_coverage"),
#             "contigs": {
#                 "count": data.get("number_of_contigs"),
#                 "n50": data.get("contig_n50"),
#                 "l50": data.get("contig_l50"),
#             },
#             "scaffolds": {
#                 "count": data.get("number_of_scaffolds"),
#                 "n50": data.get("scaffold_n50"),
#                 "l50": data.get("scaffold_l50"),
#             },
#         },
#         "biosample": {
#             "accession": biosample_accession,
#             "description": biosample_description,
#             "submitter": biosample_submitter,
#             "attributes": attributes,
#         },
#         "assembly_metadata": {
#             "quality": "N/A",   # you can derive from assembly_status/refseq_category if desired
#             "completeness": data.get("completeness"),
#             "contamination": data.get("contamination"),
#         },
#         "external_links": {
#             "ncbi": data.get("ncbi_url"),
#             "ena": data.get("ena_url"),
#         },
#     }

# @app.route('/api/assembly/<accession>', methods=['GET'])
# def get_assembly(accession):
#     """Fetch assembly data by accession"""
#     cached = assemblies.find_one({'accession': accession})
#     if cached:
#         print(f"✓ Cache HIT: assembly/{accession}")
#         cached['_id'] = str(cached['_id'])
#         cached['from_cache'] = True
#         # return jsonify(cached)
#         return jsonify(map_to_frontend_format(cached))   # ✅ call with data

#     print(f"⚠ Cache MISS: assembly/{accession}")

#     try:
#         # result = fetch_and_parse_assembly(accession)
#         # mapped = map_to_frontend_format(result)
#         # # assemblies.insert_one(result.copy())
#         # assemblies.insert_one(result)  # store flat version
#         # mapped['_id'] = str(mapped.get('_id', ''))
#         # # result['_id'] = str(result.get('_id', ''))
#         # return jsonify(result)

#         result = fetch_and_parse_assembly(accession)
#         assemblies.insert_one(result.copy())
#         result['_id'] = str(result.get('_id', ''))
#         # ✅ Call the mapper with the fresh result
#         return jsonify(map_to_frontend_format(result))

#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         return jsonify({'error': str(e), 'accession': accession}), 500


# # ==================== ORGANISM SEARCH ENDPOINT ====================

# @app.route('/api/organism/<path:organism_name>', methods=['GET'])
# def search_by_organism(organism_name):
#     """Search for assemblies by organism name"""
#     organism_name = organism_name.replace('%20', ' ')

#     cached = organism_searches.find_one({'organism_name': organism_name})
#     if cached:
#         print(f"✓ Cache HIT: organism/{organism_name}")
#         cached['_id'] = str(cached['_id'])
#         cached['from_cache'] = True
#         return jsonify(cached)

#     print(f"⚠ Cache MISS: organism/{organism_name}")

#     try:
#         assemblies_list = search_assemblies_by_organism(organism_name, max_results=20)

#         if not assemblies_list:
#             return jsonify({
#                 'error': f'No assemblies found for organism: {organism_name}',
#                 'organism_name': organism_name
#             }), 404

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

#         organism_searches.insert_one(result.copy())
#         result['_id'] = str(result.get('_id', ''))
#         return jsonify(result)

#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         return jsonify({'error': str(e), 'organism_name': organism_name}), 500


# # ==================== NUCLEOTIDE ====================

# @app.route('/api/nucleotide/<accession>', methods=['GET'])
# def get_nucleotide(accession):
#     cached = nucleotides.find_one({'accession': accession})
#     if cached:
#         cached['_id'] = str(cached['_id'])
#         cached['from_cache'] = True
#         return jsonify(cached)

#     try:
#         search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=nuccore&term={accession}&retmode=json"
#         search_resp = rate_limited_request(search_url)
#         search_data = search_resp.json()

#         if not search_data.get('esearchresult', {}).get('idlist'):
#             return jsonify({'error': 'Accession not found', 'accession': accession}), 404

#         uid = search_data['esearchresult']['idlist'][0]

#         summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=nuccore&id={uid}&retmode=json"
#         summary_resp = rate_limited_request(summary_url)
#         summary_data = summary_resp.json().get('result', {}).get(uid, {})

#         result = {
#             'accession': accession,
#             'uid': uid,
#             'title': summary_data.get('title'),
#             'organism': summary_data.get('organism'),
#             'tax_id': summary_data.get('taxid'),
#             'length': summary_data.get('slen'),
#             'molecule_type': summary_data.get('moltype'),
#             'topology': summary_data.get('topology'),
#             'completeness': summary_data.get('completeness'),
#             'create_date': summary_data.get('createdate'),
#             'update_date': summary_data.get('updatedate'),
#             'definition': summary_data.get('defline'),
#             'gene': summary_data.get('gene'),
#             'location': summary_data.get('location'),
#             'genetic_code': summary_data.get('geneticcode'),
#             'segment': summary_data.get('segment'),
#             'fetched_at': datetime.utcnow().isoformat(),
#             'from_cache': False
#         }

#         nucleotides.insert_one(result.copy())
#         result['_id'] = str(result.get('_id', ''))
#         return jsonify(result)

#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         return jsonify({'error': str(e), 'accession': accession}), 500


# # ==================== GENE ====================

# @app.route('/api/gene/symbol/<symbol>', methods=['GET'])
# def get_gene_by_symbol(symbol):
#     organism = request.args.get('organism', 'human')
#     cache_key = f"{symbol}_{organism}"
#     cached = genes.find_one({'cache_key': cache_key})
#     if cached:
#         cached['_id'] = str(cached['_id'])
#         cached['from_cache'] = True
#         return jsonify(cached)

#     try:
#         datasets_url = f"https://api.ncbi.nlm.nih.gov/datasets/v2/gene/symbol/{symbol}/taxon/{organism}/dataset_report"
#         datasets_resp = rate_limited_request(datasets_url)
#         datasets_data = datasets_resp.json() if datasets_resp.ok else None

#         search_term = f"{symbol}[Gene Name] AND {organism}[Organism]"
#         search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=gene&term={search_term}&retmode=json"
#         search_resp = rate_limited_request(search_url)
#         search_data = search_resp.json()

#         esummary_data = None
#         gene_id = None
#         if search_data.get('esearchresult', {}).get('idlist'):
#             gene_id = search_data['esearchresult']['idlist'][0]
#             summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=gene&id={gene_id}&retmode=json"
#             summary_resp = rate_limited_request(summary_url)
#             esummary_data = summary_resp.json().get('result', {}).get(gene_id, {})

#         result = {
#             'cache_key': cache_key,
#             'symbol': symbol,
#             'organism': organism,
#             'gene_id': gene_id,
#             'name': esummary_data.get('name') if esummary_data else None,
#             'description': esummary_data.get('description') if esummary_data else None,
#             'chromosome': esummary_data.get('chromosome') if esummary_data else None,
#             'map_location': esummary_data.get('maplocation') if esummary_data else None,
#             'gene_type': esummary_data.get('type') if esummary_data else None,
#             'summary': esummary_data.get('summary') if esummary_data else None,
#             'aliases': esummary_data.get('otheraliases', '').split(', ') if esummary_data and esummary_data.get('otheraliases') else [],
#             'ensembl_id': esummary_data.get('ensemblgeneid') if esummary_data else None,
#             'mim': esummary_data.get('mim') if esummary_data else None,
#             'fetched_at': datetime.utcnow().isoformat(),
#             'from_cache': False
#         }

#         genes.insert_one(result.copy())
#         result['_id'] = str(result.get('_id', ''))
#         return jsonify(result)

#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         return jsonify({'error': str(e), 'symbol': symbol}), 500

# @app.route('/api/gene/id/<gene_id>', methods=['GET'])
# def get_gene_by_id(gene_id):
#     cached = genes.find_one({'gene_id': gene_id})
#     if cached:
#         cached['_id'] = str(cached['_id'])
#         cached['from_cache'] = True
#         return jsonify(cached)

#     try:
#         summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=gene&id={gene_id}&retmode=json"
#         summary_resp = rate_limited_request(summary_url)
#         esummary_data = summary_resp.json().get('result', {}).get(gene_id, {})

#         result = {
#             'gene_id': gene_id,
#             'name': esummary_data.get('name'),
#             'description': esummary_data.get('description'),
#             'chromosome': esummary_data.get('chromosome'),
#             'map_location': esummary_data.get('maplocation'),
#             'gene_type': esummary_data.get('type'),
#             'summary': esummary_data.get('summary'),
#             'aliases': esummary_data.get('otheraliases', '').split(', ') if esummary_data.get('otheraliases') else [],
#             'ensembl_id': esummary_data.get('ensemblgeneid'),
#             'mim': esummary_data.get('mim'),
#             'fetched_at': datetime.utcnow().isoformat(),
#             'from_cache': False
#         }

#         genes.insert_one(result.copy())
#         result['_id'] = str(result.get('_id', ''))
#         return jsonify(result)

#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         return jsonify({'error': str(e), 'gene_id': gene_id}), 500


# # ==================== PROTEIN ====================

# @app.route('/api/protein/<accession>', methods=['GET'])
# def get_protein(accession):
#     cached = proteins.find_one({'accession': accession})
#     if cached:
#         cached['_id'] = str(cached['_id'])
#         cached['from_cache'] = True
#         return jsonify(cached)

#     try:
#         search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=protein&term={accession}&retmode=json"
#         search_resp = rate_limited_request(search_url)
#         search_data = search_resp.json()

#         if not search_data.get('esearchresult', {}).get('idlist'):
#             return jsonify({'error': 'Protein not found', 'accession': accession}), 404

#         uid = search_data['esearchresult']['idlist'][0]

#         summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=protein&id={uid}&retmode=json"
#         summary_resp = rate_limited_request(summary_url)
#         summary_data = summary_resp.json().get('result', {}).get(uid, {})

#         result = {
#             'accession': accession,
#             'uid': uid,
#             'title': summary_data.get('title'),
#             'organism': summary_data.get('organism'),
#             'tax_id': summary_data.get('taxid'),
#             'length': summary_data.get('slen'),
#             'molecular_weight': summary_data.get('molecularweight'),
#             'molecule_type': summary_data.get('moltype'),
#             'create_date': summary_data.get('createdate'),
#             'update_date': summary_data.get('updatedate'),
#             'definition': summary_data.get('defline'),
#             'gene': summary_data.get('gene'),
#             'gene_id': summary_data.get('geneid'),
#             'fetched_at': datetime.utcnow().isoformat(),
#             'from_cache': False
#         }

#         proteins.insert_one(result.copy())
#         result['_id'] = str(result.get('_id', ''))
#         return jsonify(result)

#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         return jsonify({'error': str(e), 'accession': accession}), 500


# # ==================== TAXONOMY ====================

# @app.route('/api/taxonomy/<name_or_id>', methods=['GET'])
# def get_taxonomy(name_or_id):
#     cached = taxonomies.find_one({'query': name_or_id})
#     if cached:
#         cached['_id'] = str(cached['_id'])
#         cached['from_cache'] = True
#         return jsonify(cached)

#     try:
#         search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=taxonomy&term={name_or_id}&retmode=json"
#         search_resp = rate_limited_request(search_url)
#         search_data = search_resp.json()

#         if not search_data.get('esearchresult', {}).get('idlist'):
#             return jsonify({'error': 'Taxonomy not found', 'query': name_or_id}), 404

#         tax_id = search_data['esearchresult']['idlist'][0]

#         summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=taxonomy&id={tax_id}&retmode=json"
#         summary_resp = rate_limited_request(summary_url)
#         summary_data = summary_resp.json().get('result', {}).get(tax_id, {})

#         result = {
#             'query': name_or_id,
#             'tax_id': tax_id,
#             'scientific_name': summary_data.get('scientificname'),
#             'common_name': summary_data.get('commonname'),
#             'rank': summary_data.get('rank'),
#             'division': summary_data.get('division'),
#             'lineage': summary_data.get('lineage'),
#             'genetic_code': summary_data.get('geneticcode'),
#             'fetched_at': datetime.utcnow().isoformat(),
#             'from_cache': False
#         }

#         taxonomies.insert_one(result.copy())
#         result['_id'] = str(result.get('_id', ''))
#         return jsonify(result)

#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         return jsonify({'error': str(e), 'query': name_or_id}), 500


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

# @app.route('/api/detect/<query>', methods=['GET'])
# def detect_db(query):
#     return jsonify({
#         'query': query,
#         'detected_database': detect_database_type(query)
#     })

# if __name__ == '__main__':
#     app.run(debug=True, port=5001)






from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import requests
from datetime import datetime
import time
import os
import re
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)


# MongoDB
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
client = MongoClient(MONGODB_URI)
db = client.ncbi_cache

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
NCBI_API_KEY = os.getenv('NCBI_API_KEY', '')

def rate_limited_request(url, timeout=30):
    """Make rate-limited request to NCBI"""
    global last_request_time
    current_time = time.time()
    time_since_last = current_time - last_request_time
    if time_since_last < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - time_since_last)
    if NCBI_API_KEY and 'ncbi.nlm.nih.gov' in url:
        separator = '&' if '?' in url else '?'
        url = f"{url}{separator}api_key={NCBI_API_KEY}"
    last_request_time = time.time()
    return requests.get(url, timeout=timeout)

def detect_database_type(query):
    """Auto-detect database type from query string"""
    query = query.strip()
    if re.match(r'^GC[FA]_\d+\.\d+$', query):
        return 'assembly'
    if re.match(r'^N[CGMRW]_\d+\.\d+$', query):
        return 'nucleotide'
    if re.match(r'^[NYXWAZ]P_\d+\.\d+$', query):
        return 'protein'
    if re.match(r'^\d+$', query):
        return 'gene'
    if re.match(r'^[A-Z][A-Z0-9\-]+$', query, re.IGNORECASE):
        return 'gene'
    if ' ' in query:
        return 'organism'
    return 'unknown'

# ==================== FTP STATS PARSER ====================

def parse_ftp_stats_file(stats_text):
    """Parse NCBI assembly_stats.txt file format"""
    stats = {}
    if not stats_text:
        return stats

    lines = stats_text.strip().split('\n')

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        parts = line.split('\t')
        if len(parts) >= 2:
            value = parts[-1].strip()
            key_parts = parts[:-1]

            if len(key_parts) == 1:
                key = key_parts[0].strip().lower().replace(' ', '_').replace('-', '_')
            else:
                stat_name = key_parts[-1].strip().lower().replace(' ', '_').replace('-', '_')
                context = '_'.join([p.strip().lower().replace(' ', '_').replace('-', '_') for p in key_parts[:-1] if p.strip()])
                key = f"{context}_{stat_name}" if context else stat_name

            try:
                if '.' in value:
                    stats[key] = float(value)
                else:
                    stats[key] = int(value)
            except ValueError:
                stats[key] = value

    # Extract "all" summary stats
    all_stats = {}
    for line in lines:
        if not line.strip() or line.startswith('#'):
            continue
        parts = line.split('\t')
        if len(parts) >= 6 and parts[0].strip().lower() == 'all' and parts[1].strip().lower() == 'all':
            stat_name = parts[4].strip().lower().replace(' ', '_').replace('-', '_')
            value = parts[5].strip()
            try:
                if '.' in value:
                    all_stats[stat_name] = float(value)
                else:
                    all_stats[stat_name] = int(value)
            except ValueError:
                all_stats[stat_name] = value

    stats['all_summary'] = all_stats
    return stats

def fetch_ftp_stats(ftp_url):
    """Fetch and parse assembly stats from NCBI FTP"""
    if not ftp_url:
        return None
    try:
        https_url = ftp_url.replace('ftp://', 'https://')
        resp = requests.get(https_url, timeout=30)
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

def parse_datasets_api(datasets_data):
    """Parse NCBI Datasets API v2 response"""
    parsed = {}
    if not datasets_data or 'reports' not in datasets_data:
        return parsed

    reports = datasets_data.get('reports', [])
    if not reports:
        return parsed

    report = reports[0]

    organism = report.get('organism', {})
    parsed['organism_name'] = organism.get('sciName') or organism.get('organismName')
    parsed['common_name'] = organism.get('commonName')
    parsed['tax_id'] = organism.get('taxId')

    assembly_info = report.get('assemblyInfo', {})
    parsed['assembly_level'] = assembly_info.get('assemblyLevel')
    parsed['assembly_status'] = assembly_info.get('assemblyStatus')
    parsed['assembly_name'] = assembly_info.get('assemblyName')
    parsed['assembly_type'] = assembly_info.get('assemblyType')
    parsed['description'] = assembly_info.get('description')
    parsed['submitter'] = assembly_info.get('submitter')
    parsed['submission_date'] = assembly_info.get('submissionDate')
    parsed['release_date'] = assembly_info.get('releaseDate')
    parsed['assembly_method'] = assembly_info.get('assemblyMethod')
    parsed['sequencing_technology'] = assembly_info.get('sequencingTechnology')
    parsed['refseq_category'] = assembly_info.get('refseqCategory')
    parsed['biosample_accession'] = assembly_info.get('biosampleAccession')
    parsed['bioproject_accession'] = assembly_info.get('bioprojectAccession')
    parsed['strain'] = assembly_info.get('infraspecificNames', {}).get('strain')
    parsed['isolate'] = assembly_info.get('infraspecificNames', {}).get('isolate')
    parsed['expected_final_version'] = assembly_info.get('expectedFinalVersion')
    parsed['synonym'] = assembly_info.get('synonym')

    assembly_stats = report.get('assemblyStats', {})
    parsed['genome_size_bp'] = assembly_stats.get('totalSequenceLength')
    if parsed['genome_size_bp']:
        parsed['genome_size_mb'] = round(parsed['genome_size_bp'] / 1_000_000, 2)
    parsed['genome_size_ungapped'] = assembly_stats.get('totalUngappedLength')
    parsed['gc_content'] = assembly_stats.get('gcPercent')
    parsed['gc_count'] = assembly_stats.get('gcCount')
    parsed['atgc_count'] = assembly_stats.get('atgcCount')
    parsed['genome_coverage'] = assembly_stats.get('genomeCoverage')
    parsed['number_of_chromosomes'] = assembly_stats.get('totalNumberOfChromosomes')
    parsed['contig_n50'] = assembly_stats.get('contigN50')
    parsed['contig_l50'] = assembly_stats.get('contigL50')
    parsed['number_of_contigs'] = assembly_stats.get('numberOfContigs')
    parsed['scaffold_n50'] = assembly_stats.get('scaffoldN50')
    parsed['scaffold_l50'] = assembly_stats.get('scaffoldL50')
    parsed['number_of_scaffolds'] = assembly_stats.get('numberOfScaffolds')
    parsed['gaps_between_scaffolds'] = assembly_stats.get('gapsBetweenScaffoldsCount')
    parsed['number_of_component_sequences'] = assembly_stats.get('numberOfComponentSequences')
    parsed['number_of_organelles'] = assembly_stats.get('numberOfOrganelles')

    annotation = report.get('annotationInfo', {})
    parsed['annotation_provider'] = annotation.get('provider')
    parsed['annotation_date'] = annotation.get('releaseDate')
    parsed['annotation_name'] = annotation.get('name')
    parsed['annotation_method'] = annotation.get('method')
    parsed['annotation_pipeline'] = annotation.get('pipeline')
    parsed['annotation_software_version'] = annotation.get('softwareVersion')
    parsed['annotation_status'] = annotation.get('status')

    gene_counts = annotation.get('stats', {}).get('geneCounts', {})
    parsed['total_genes'] = gene_counts.get('total')
    parsed['protein_coding_genes'] = gene_counts.get('proteinCoding')
    parsed['non_coding_genes'] = gene_counts.get('nonCoding')
    parsed['pseudogenes'] = gene_counts.get('pseudogene')
    parsed['other_genes'] = gene_counts.get('other')

    wgs = report.get('wgsInfo', {})
    parsed['wgs_project'] = wgs.get('wgsProjectAccession')

    paired = report.get('pairedAssembly', {})
    parsed['paired_accession'] = paired.get('accession')

    parsed['current_accession'] = report.get('currentAccession')
    parsed['source_database'] = report.get('sourceDatabase')

    return parsed

# ==================== ENA FETCHER ====================

def fetch_ena_assembly(accession):
    """Fetch assembly metadata from ENA"""
    try:
        url = f"https://www.ebi.ac.uk/ena/browser/api/xml/{accession}"
        resp = requests.get(url, timeout=15)
        if not resp.ok:
            return None

        root = ET.fromstring(resp.content)
        ena_data = {}

        for elem in root.iter():
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag

            if tag == 'ASSEMBLY':
                ena_data['submission_date'] = elem.get('submission_date')
                ena_data['last_updated'] = elem.get('last_updated')
                ena_data['accession'] = elem.get('accession')
            elif tag == 'STUDY_REF':
                ena_data['study_accession'] = elem.get('accession')
            elif tag == 'SAMPLE_REF':
                ena_data['sample_accession'] = elem.get('accession')
            elif tag == 'DESCRIPTION':
                ena_data['description'] = elem.text
            elif tag == 'TAXON':
                ena_data['tax_id'] = elem.get('taxon_id')
                ena_data['scientific_name'] = elem.get('scientific_name')
                ena_data['common_name'] = elem.get('common_name')
            elif tag == 'ASSEMBLY_TYPE':
                ena_data['assembly_type'] = elem.text
            elif tag == 'GENOME_REPRESENTATION':
                ena_data['genome_representation'] = elem.text
            elif tag == 'EXPECTED_FINAL_VERSION':
                ena_data['expected_final_version'] = elem.text
            elif tag == 'CHROMOSOME_LIST':
                chromosomes = []
                for chrom in elem.iter('CHROMOSOME'):
                    chromosomes.append({
                        'name': chrom.get('chromosome_name'),
                        'type': chrom.get('chromosome_type'),
                        'accession': chrom.get('accession')
                    })
                ena_data['chromosomes'] = chromosomes

        return ena_data
    except Exception as e:
        print(f"ENA fetch error: {e}")
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
                        for child in elem:
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
            parts = infraspecies.split(':', 1)
            biosample_info['attributes'][parts[0].strip()] = parts[1].strip()

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

    # SOURCE 1: NCBI Datasets API v2
    datasets_data = None
    datasets_parsed = {}
    try:
        datasets_url = f"https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession/{accession}/dataset_report"
        datasets_resp = rate_limited_request(datasets_url)
        if datasets_resp.ok:
            datasets_data = datasets_resp.json()
            datasets_parsed = parse_datasets_api(datasets_data)
            print(f"  Datasets API: {len(datasets_parsed)} fields parsed")
    except Exception as e:
        print(f"  Datasets API error: {e}")

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

            meta_xml = esummary_data.get('meta', '')
            meta_stats = parse_meta_xml(meta_xml)
            ftp_stats_url = esummary_data.get('ftppath_stats_rpt')
            print(f"  ESummary: ID={assembly_id}, meta has {len(meta_stats)} stats")
    except Exception as e:
        print(f"  ESummary error: {e}")

    # SOURCE 3: NCBI FTP Stats File
    ftp_stats = {}
    try:
        if ftp_stats_url:
            ftp_stats = fetch_ftp_stats(ftp_stats_url)
            print(f"  FTP Stats: {len(ftp_stats)} fields parsed")
    except Exception as e:
        print(f"  FTP stats error: {e}")

    # SOURCE 4: ENA
    ena_data = fetch_ena_assembly(accession)
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

    if gc_content is None and gc_count and genome_size:
        gc_content = round((gc_count / genome_size) * 100, 2)
    elif gc_content is None and gc_count and atgc_count:
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
            datasets_parsed.get('assembly_status'),
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

    return result

@app.route('/api/assembly/<accession>', methods=['GET'])
def get_assembly(accession):
    """Fetch assembly data by accession"""
    cached = assemblies.find_one({'accession': accession})
    if cached:
        print(f"✓ Cache HIT: assembly/{accession}")
        cached['_id'] = str(cached['_id'])
        cached['from_cache'] = True
        return jsonify(cached)

    print(f"⚠ Cache MISS: assembly/{accession}")

    try:
        result = fetch_and_parse_assembly(accession)
        assemblies.insert_one(result.copy())
        result['_id'] = str(result.get('_id', ''))
        return jsonify(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'accession': accession}), 500


# ==================== ORGANISM SEARCH ENDPOINT ====================

@app.route('/api/organism/<path:organism_name>', methods=['GET'])
def search_by_organism(organism_name):
    """Search for assemblies by organism name"""
    organism_name = organism_name.replace('%20', ' ')

    cached = organism_searches.find_one({'organism_name': organism_name})
    if cached:
        print(f"✓ Cache HIT: organism/{organism_name}")
        cached['_id'] = str(cached['_id'])
        cached['from_cache'] = True
        return jsonify(cached)

    print(f"⚠ Cache MISS: organism/{organism_name}")

    try:
        assemblies_list = search_assemblies_by_organism(organism_name, max_results=20)

        if not assemblies_list:
            return jsonify({
                'error': f'No assemblies found for organism: {organism_name}',
                'organism_name': organism_name
            }), 404

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

        organism_searches.insert_one(result.copy())
        result['_id'] = str(result.get('_id', ''))
        return jsonify(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'organism_name': organism_name}), 500


# ==================== NUCLEOTIDE ====================

@app.route('/api/nucleotide/<accession>', methods=['GET'])
def get_nucleotide(accession):
    cached = nucleotides.find_one({'accession': accession})
    if cached:
        cached['_id'] = str(cached['_id'])
        cached['from_cache'] = True
        return jsonify(cached)

    try:
        search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=nuccore&term={accession}&retmode=json"
        search_resp = rate_limited_request(search_url)
        search_data = search_resp.json()

        if not search_data.get('esearchresult', {}).get('idlist'):
            return jsonify({'error': 'Accession not found', 'accession': accession}), 404

        uid = search_data['esearchresult']['idlist'][0]

        summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=nuccore&id={uid}&retmode=json"
        summary_resp = rate_limited_request(summary_url)
        summary_data = summary_resp.json().get('result', {}).get(uid, {})

        result = {
            'accession': accession,
            'uid': uid,
            'title': summary_data.get('title'),
            'organism': summary_data.get('organism'),
            'tax_id': summary_data.get('taxid'),
            'length': summary_data.get('slen'),
            'molecule_type': summary_data.get('moltype'),
            'topology': summary_data.get('topology'),
            'completeness': summary_data.get('completeness'),
            'create_date': summary_data.get('createdate'),
            'update_date': summary_data.get('updatedate'),
            'definition': summary_data.get('defline'),
            'gene': summary_data.get('gene'),
            'location': summary_data.get('location'),
            'genetic_code': summary_data.get('geneticcode'),
            'segment': summary_data.get('segment'),
            'fetched_at': datetime.utcnow().isoformat(),
            'from_cache': False
        }

        nucleotides.insert_one(result.copy())
        result['_id'] = str(result.get('_id', ''))
        return jsonify(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'accession': accession}), 500


# ==================== GENE ====================

@app.route('/api/gene/symbol/<symbol>', methods=['GET'])
def get_gene_by_symbol(symbol):
    organism = request.args.get('organism', 'human')
    cache_key = f"{symbol}_{organism}"
    cached = genes.find_one({'cache_key': cache_key})
    if cached:
        cached['_id'] = str(cached['_id'])
        cached['from_cache'] = True
        return jsonify(cached)

    try:
        datasets_url = f"https://api.ncbi.nlm.nih.gov/datasets/v2/gene/symbol/{symbol}/taxon/{organism}/dataset_report"
        datasets_resp = rate_limited_request(datasets_url)
        datasets_data = datasets_resp.json() if datasets_resp.ok else None

        search_term = f"{symbol}[Gene Name] AND {organism}[Organism]"
        search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=gene&term={search_term}&retmode=json"
        search_resp = rate_limited_request(search_url)
        search_data = search_resp.json()

        esummary_data = None
        gene_id = None
        if search_data.get('esearchresult', {}).get('idlist'):
            gene_id = search_data['esearchresult']['idlist'][0]
            summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=gene&id={gene_id}&retmode=json"
            summary_resp = rate_limited_request(summary_url)
            esummary_data = summary_resp.json().get('result', {}).get(gene_id, {})

        result = {
            'cache_key': cache_key,
            'symbol': symbol,
            'organism': organism,
            'gene_id': gene_id,
            'name': esummary_data.get('name') if esummary_data else None,
            'description': esummary_data.get('description') if esummary_data else None,
            'chromosome': esummary_data.get('chromosome') if esummary_data else None,
            'map_location': esummary_data.get('maplocation') if esummary_data else None,
            'gene_type': esummary_data.get('type') if esummary_data else None,
            'summary': esummary_data.get('summary') if esummary_data else None,
            'aliases': esummary_data.get('otheraliases', '').split(', ') if esummary_data and esummary_data.get('otheraliases') else [],
            'ensembl_id': esummary_data.get('ensemblgeneid') if esummary_data else None,
            'mim': esummary_data.get('mim') if esummary_data else None,
            'fetched_at': datetime.utcnow().isoformat(),
            'from_cache': False
        }

        genes.insert_one(result.copy())
        result['_id'] = str(result.get('_id', ''))
        return jsonify(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'symbol': symbol}), 500

@app.route('/api/gene/id/<gene_id>', methods=['GET'])
def get_gene_by_id(gene_id):
    cached = genes.find_one({'gene_id': gene_id})
    if cached:
        cached['_id'] = str(cached['_id'])
        cached['from_cache'] = True
        return jsonify(cached)

    try:
        summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=gene&id={gene_id}&retmode=json"
        summary_resp = rate_limited_request(summary_url)
        esummary_data = summary_resp.json().get('result', {}).get(gene_id, {})

        result = {
            'gene_id': gene_id,
            'name': esummary_data.get('name'),
            'description': esummary_data.get('description'),
            'chromosome': esummary_data.get('chromosome'),
            'map_location': esummary_data.get('maplocation'),
            'gene_type': esummary_data.get('type'),
            'summary': esummary_data.get('summary'),
            'aliases': esummary_data.get('otheraliases', '').split(', ') if esummary_data.get('otheraliases') else [],
            'ensembl_id': esummary_data.get('ensemblgeneid'),
            'mim': esummary_data.get('mim'),
            'fetched_at': datetime.utcnow().isoformat(),
            'from_cache': False
        }

        genes.insert_one(result.copy())
        result['_id'] = str(result.get('_id', ''))
        return jsonify(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'gene_id': gene_id}), 500


# ==================== PROTEIN ====================

@app.route('/api/protein/<accession>', methods=['GET'])
def get_protein(accession):
    cached = proteins.find_one({'accession': accession})
    if cached:
        cached['_id'] = str(cached['_id'])
        cached['from_cache'] = True
        return jsonify(cached)

    try:
        search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=protein&term={accession}&retmode=json"
        search_resp = rate_limited_request(search_url)
        search_data = search_resp.json()

        if not search_data.get('esearchresult', {}).get('idlist'):
            return jsonify({'error': 'Protein not found', 'accession': accession}), 404

        uid = search_data['esearchresult']['idlist'][0]

        summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=protein&id={uid}&retmode=json"
        summary_resp = rate_limited_request(summary_url)
        summary_data = summary_resp.json().get('result', {}).get(uid, {})

        result = {
            'accession': accession,
            'uid': uid,
            'title': summary_data.get('title'),
            'organism': summary_data.get('organism'),
            'tax_id': summary_data.get('taxid'),
            'length': summary_data.get('slen'),
            'molecular_weight': summary_data.get('molecularweight'),
            'molecule_type': summary_data.get('moltype'),
            'create_date': summary_data.get('createdate'),
            'update_date': summary_data.get('updatedate'),
            'definition': summary_data.get('defline'),
            'gene': summary_data.get('gene'),
            'gene_id': summary_data.get('geneid'),
            'fetched_at': datetime.utcnow().isoformat(),
            'from_cache': False
        }

        proteins.insert_one(result.copy())
        result['_id'] = str(result.get('_id', ''))
        return jsonify(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'accession': accession}), 500


# ==================== TAXONOMY ====================

@app.route('/api/taxonomy/<name_or_id>', methods=['GET'])
def get_taxonomy(name_or_id):
    cached = taxonomies.find_one({'query': name_or_id})
    if cached:
        cached['_id'] = str(cached['_id'])
        cached['from_cache'] = True
        return jsonify(cached)

    try:
        search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=taxonomy&term={name_or_id}&retmode=json"
        search_resp = rate_limited_request(search_url)
        search_data = search_resp.json()

        if not search_data.get('esearchresult', {}).get('idlist'):
            return jsonify({'error': 'Taxonomy not found', 'query': name_or_id}), 404

        tax_id = search_data['esearchresult']['idlist'][0]

        summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=taxonomy&id={tax_id}&retmode=json"
        summary_resp = rate_limited_request(summary_url)
        summary_data = summary_resp.json().get('result', {}).get(tax_id, {})

        result = {
            'query': name_or_id,
            'tax_id': tax_id,
            'scientific_name': summary_data.get('scientificname'),
            'common_name': summary_data.get('commonname'),
            'rank': summary_data.get('rank'),
            'division': summary_data.get('division'),
            'lineage': summary_data.get('lineage'),
            'genetic_code': summary_data.get('geneticcode'),
            'fetched_at': datetime.utcnow().isoformat(),
            'from_cache': False
        }

        taxonomies.insert_one(result.copy())
        result['_id'] = str(result.get('_id', ''))
        return jsonify(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'query': name_or_id}), 500


# ==================== SMART SEARCH ====================

@app.route('/api/search', methods=['POST'])
def smart_search():
    query = request.json.get('query', '')
    database = detect_database_type(query)

    if database == 'assembly':
        return get_assembly(query)
    elif database == 'organism':
        return search_by_organism(query)
    elif database == 'nucleotide':
        return get_nucleotide(query)
    elif database == 'protein':
        return get_protein(query)
    elif database == 'gene':
        if query.isdigit():
            return get_gene_by_id(query)
        else:
            return get_gene_by_symbol(query)
    elif database == 'taxonomy':
        return get_taxonomy(query)
    else:
        return jsonify({'error': 'Could not detect database type', 'query': query}), 400


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

@app.route('/api/detect/<query>', methods=['GET'])
def detect_db(query):
    return jsonify({
        'query': query,
        'detected_database': detect_database_type(query)
    })

if __name__ == '__main__':
    app.run(debug=True, port=5001)
