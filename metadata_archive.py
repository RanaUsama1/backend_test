"""Capture metadata HTTP responses before application parsing; Flask ZIP route."""
from contextvars import ContextVar
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
from io import BytesIO
import json
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from zipfile import ZipFile, ZIP_DEFLATED

_capture = ContextVar('metadata_capture', default=None)


def now():
    return datetime.now(timezone.utc).isoformat()


def public_url(url):
    parts = urlsplit(url)
    secret_names = {'api_key', 'apikey', 'token', 'access_token', 'email'}
    query = [(k, '[REDACTED]' if k.lower() in secret_names else v)
             for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ''))


def metadata_get(url, **kwargs):
    """Drop-in for requests.get in metadata helpers. Does NOT raise for status.

    Callers retain their current status checks and rate limiting. Store decoded
    HTTP entity bytes (Requests .content), not compressed on-the-wire bytes.
    Capture is request-local and active only during build_archive().
    """
    import requests
    entries = _capture.get()
    if entries is None:
        return requests.get(url, **kwargs)
    record = {'requested_url': public_url(url), 'retrieved_at': now()}
    entries.append((record, None))
    index = len(entries) - 1
    try:
        response = requests.get(url, **kwargs)
        body = response.content  # Capture BEFORE .json(), XML parsing, or status raising.
        record.update(url=public_url(response.url), http_status=response.status_code,
                      http_success=200 <= response.status_code < 300,
                      content_type=response.headers.get('Content-Type', ''),
                      size_bytes=len(body), sha256=sha256(body).hexdigest())
        entries[index] = (record, body)
        return response
    except Exception as exc:
        # Exception messages may embed credentials or API keys in URLs.
        record.update(http_success=False, transport_error=type(exc).__name__)
        raise


def build_archive(accession, fetcher):
    """Always archive captured responses, even if fetcher/parsing raises.

    fetcher must perform fresh fetches and use metadata_get in its HTTP helpers.
    A completed fetcher can still have swallowed parser errors or null values;
    normalized_status is not a completeness/validation claim.
    """
    accession = accession.strip().upper()
    if not re.fullmatch(r'GC[FA]_\d+\.\d+', accession):
        raise ValueError('A versioned GCF_ or GCA_ assembly accession is required.')
    entries = []
    token = _capture.set(entries)
    normalized = None
    status = 'returned'
    error = None
    try:
        normalized = fetcher(accession)
        # Validate serialization separately; raw sources survive this too.
        normalized_bytes = json.dumps(normalized, indent=2, ensure_ascii=False,
                                      allow_nan=False).encode('utf-8')
    except Exception as exc:
        status = 'failed'
        error = type(exc).__name__
        normalized_bytes = b'null'
    finally:
        _capture.reset(token)

    manifest = {
        'schema_version': 1, 'accession': accession, 'created_at': now(),
        'fresh_fetch': True, 'normalized_status': status,
        'normalization_error_type': error,
        'scope': 'Responses attempted by the existing assembly metadata fetcher; '
                 'not all NCBI records, linked genes, proteins, or sequences.',
        'completeness': 'not_asserted',
        'note': 'HTTP success is not proof of a valid record. Inspect source bodies. '
                'Existing helpers may catch parser errors internally. Null normalized '
                'values do not establish that the source lacks the field.',
        'sources': []}
    sections = []
    stream = BytesIO()
    with ZipFile(stream, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('normalized_metadata.json', normalized_bytes)
        for index, (record, body) in enumerate(entries, 1):
            record = dict(record)
            if body is not None:
                content_type = record.get('content_type', '').lower()
                extension = 'json' if 'json' in content_type else ('xml' if 'xml' in content_type else 'txt')
                path = f'sources/{index:03d}.{extension}'
                record['file'] = path
                archive.writestr(path, body)
                readable = body.decode('utf-8', errors='replace')
                try:
                    readable = json.dumps(json.loads(body), indent=2, ensure_ascii=False)
                except (ValueError, UnicodeError):
                    pass
                sections.append('<details><summary>' + escape(path) + ' — HTTP ' +
                                str(record['http_status']) + '</summary><p>' +
                                escape(record['url']) + '</p><pre>' + escape(readable) + '</pre></details>')
            manifest['sources'].append(record)
        manifest['captured_response_count'] = sum(body is not None for _, body in entries)
        manifest['http_success_count'] = sum(bool(r.get('http_success')) for r, _ in entries)
        manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode('utf-8')
        archive.writestr('manifest.json', manifest_bytes)
        html = ('<!doctype html><html lang="en"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>Assembly metadata archive</title><style>'
                'body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:1rem}'
                'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f4f6;padding:1rem}'
                'details{margin:1rem 0}summary{cursor:pointer;font-weight:600}</style>'
                '<h1>' + escape(accession) + '</h1><p>Offline snapshot. Source responses are '
                'preserved independently of field mapping. This package does not claim '
                'all NCBI metadata was fetched.</p><details><summary>Fetch manifest</summary><pre>' +
                escape(manifest_bytes.decode()) + '</pre></details><details><summary>'
                'Normalized metadata (may contain missing values)</summary><pre>' +
                escape(normalized_bytes.decode()) + '</pre></details><h2>Source responses</h2>' +
                ''.join(sections) + '</html>')
        archive.writestr('report.html', html)
    stream.seek(0)
    return stream, manifest


def register_metadata_download(app, fetcher):
    from flask import jsonify, send_file

    @app.get('/api/assembly/<accession>/download', endpoint='assembly_metadata_archive')
    def download_assembly_metadata(accession):
        if not re.fullmatch(r'GC[FA]_\d+\.\d+', accession.strip().upper()):
            return jsonify(message='Use a versioned GCF_ or GCA_ assembly accession.'), 400
        accession = accession.strip().upper()
        stream, manifest = build_archive(accession, fetcher)
        if not manifest['captured_response_count']:
            return jsonify(message='No source responses were captured. Check upstream '
                           'connectivity and metadata_get integration.', manifest=manifest), 502
        # Even upstream error bodies are downloadable, explicitly marked in manifest.
        response = send_file(stream, mimetype='application/zip', as_attachment=True,
                             download_name=f'{accession}_metadata.zip', max_age=0)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Metadata-HTTP-Success-Count'] = str(manifest['http_success_count'])
        return response
