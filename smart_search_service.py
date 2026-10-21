"""Rule-based routing; classification makes no network or database calls."""
import re
from flask import jsonify, request

DATABASES = {'assembly', 'gene', 'nucleotide', 'protein', 'taxonomy'}

def classify(query):
    if not isinstance(query, str) or not query.strip() or len(query) > 200:
        raise ValueError('Enter a query of 1–200 characters.')
    q = query.strip()
    upper = q.upper()
    candidates, reason, kind = [], '', 'unknown'
    if re.fullmatch(r'GC[FA]_\d+\.\d+', upper):
        candidates, reason, kind = ['assembly'], 'Assembly accession pattern.', 'accession'
        q = upper
    elif re.fullmatch(r'(?:NC|NG|NM|NR|NT|NW|NZ|XM|XR)_\d+\.\d+', upper):
        candidates, reason, kind = ['nucleotide'], 'Supported nucleotide accession pattern.', 'accession'
        q = upper
    elif re.fullmatch(r'(?:NP|XP|YP|WP|AP|ZP)_\d+\.\d+', upper):
        candidates, reason, kind = ['protein'], 'Supported protein accession pattern.', 'accession'
        q = upper
    elif re.fullmatch(r'[1-9]\d{0,11}', q):
        candidates, reason, kind = ['gene', 'taxonomy'], 'A number alone does not distinguish GeneID from TaxID.', 'numeric'
    elif re.fullmatch(r'[A-Za-z]+_?\d+(?:\.\d+)?', q) and ('.' in q or '_' in q):
        candidates, reason, kind = ['nucleotide', 'protein', 'assembly'], 'Unrecognized or unversioned accession: choose a resource; its handler will validate it.', 'accession_candidate'
    elif re.fullmatch(r'[A-Za-z][A-Za-z0-9.-]{0,119}', q):
        candidates, reason, kind = ['gene', 'taxonomy', 'assembly'], 'This could be a gene symbol or a single-word organism name.', 'name'
    elif re.fullmatch(r'[A-Za-z][A-Za-z0-9 .()\-]{0,119}', q) and ' ' in q:
        candidates, reason, kind = ['assembly', 'taxonomy'], 'An organism name can be searched in Assembly or Taxonomy.', 'organism'
    else:
        reason = 'Unsupported query format. Use a record accession, numeric ID, gene symbol or organism name.'
    return {'query': q, 'kind': kind, 'candidates': candidates,
            'detected_database': candidates[0] if len(candidates) == 1 else None,
            'reason': reason}

def register_smart_search(app, handlers):
    """handlers: assembly, organism, nucleotide, protein, gene_id, gene_symbol, taxonomy.

    Gene symbol organism is passed as ?organism=... so the existing handler
    receives its usual request.args, without a second HTTP request.
    """
    @app.get('/api/detect/<path:query>')
    def smart_detect(query):
        try:
            return jsonify(classify(query))
        except ValueError as exc:
            return jsonify(message=str(exc)), 400

    @app.post('/api/search')
    def smart_search_v2():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify(message='Send a JSON object containing query.'), 400
        try:
            detection = classify(body.get('query'))
        except ValueError as exc:
            return jsonify(message=str(exc)), 400
        selected = body.get('database')
        if selected is not None and (not isinstance(selected, str) or selected not in DATABASES):
            return jsonify(message='Unsupported database selection.'), 400
        candidates = detection['candidates']
        if not candidates:
            return jsonify(status='unsupported', **detection, message=detection['reason']), 400
        if selected is not None and selected not in candidates:
            return jsonify(status='mismatch', **detection, message='The selected database does not match this query format.'), 400
        database = selected or detection['detected_database']
        if database is None:
            return jsonify(status='needs_selection', **detection)
        q = detection['query']
        organism = request.args.get('organism', '').strip()
        if database == 'gene' and detection['kind'] != 'numeric' and not organism:
            return jsonify(status='needs_organism', database=database, **detection,
                           message='Enter an organism name or TaxID for this gene-symbol search.')
        if database == 'gene':
            handler = 'gene_id' if detection['kind'] == 'numeric' else 'gene_symbol'
        elif database == 'assembly' and detection['kind'] in {'name', 'organism'}:
            handler = 'organism'
        else:
            handler = database
        response = app.make_response(handlers[handler](q))
        payload = response.get_json(silent=True)
        if response.status_code >= 400:
            problem = payload if isinstance(payload, dict) else {}
            out = jsonify(status='error', database=database, **detection,
                          message=problem.get('message') or problem.get('error') or 'Resource lookup failed.',
                          resource_error=payload)
            if response.headers.get('Retry-After'):
                out.headers['Retry-After'] = response.headers['Retry-After']
            return out, response.status_code
        if not isinstance(payload, dict):
            return jsonify(message='Resource handler returned an invalid metadata response.'), 502
        # Keep the original handler response intact inside data.
        record = payload.get('assembly_data') or payload
        record_id = None
        if handler != 'gene_symbol':
            if database == 'gene': record_id = record.get('gene_id') or q
            elif database == 'taxonomy': record_id = record.get('tax_id')
            else: record_id = record.get('accession') or (q if handler != 'organism' else None)
        return jsonify(status='candidates' if handler == 'gene_symbol' else 'success',
                       database=database, record_id=str(record_id) if record_id is not None else None,
                       selection='user' if selected else 'automatic', **detection, data=payload)
