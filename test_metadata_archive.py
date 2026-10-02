import json
import sys
import types
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from metadata_archive import build_archive, metadata_get, register_metadata_download


class Response:
    status_code = 200
    url = 'https://example.org/report?api_key=SECRET'
    headers = {'Content-Type': 'application/json'}
    content = b'{"reports":[{"unexpected_field":{"future_value":42},"zero":0,"html":"<script>bad()</script>"}]}'


class ArchiveTests(unittest.TestCase):
    def capture(self, fetcher, response=None, side_effect=None):
        fake = types.ModuleType('requests')
        fake.get = lambda *args, **kwargs: response or Response()
        if side_effect:
            def fail(*args, **kwargs):
                raise side_effect
            fake.get = fail
        with patch.dict(sys.modules, {'requests': fake}):
            return build_archive('GCF_902167145.1', fetcher)

    def test_unknown_fields_preserved_despite_normalization_failure(self):
        def fetcher(acc):
            metadata_get(Response.url)
            raise KeyError('field not mapped')
        stream, manifest = self.capture(fetcher)
        with ZipFile(stream) as z:
            self.assertEqual(z.read('sources/001.json'), Response.content)
            self.assertEqual(z.read('normalized_metadata.json'), b'null')
            html = z.read('report.html').decode()
            self.assertNotIn('<script>bad()', html)
            self.assertIn('&lt;script&gt;', html)
            self.assertNotIn('SECRET', z.read('manifest.json').decode())
        self.assertEqual(manifest['normalization_error_type'], 'KeyError')

    def test_malformed_json_still_archived(self):
        response = Response()
        response.content = b'{broken json'
        def fetcher(acc):
            return json.loads(metadata_get(Response.url).content)
        stream, manifest = self.capture(fetcher, response)
        with ZipFile(stream) as z:
            self.assertEqual(z.read('sources/001.json'), response.content)
        self.assertEqual(manifest['normalized_status'], 'failed')

    def test_http_failure_body_preserved(self):
        response = Response()
        response.status_code = 503
        response.content = b'upstream unavailable'
        stream, manifest = self.capture(lambda a: metadata_get(Response.url) and {}, response)
        self.assertEqual(manifest['http_success_count'], 0)
        with ZipFile(stream) as z:
            self.assertEqual(z.read('sources/001.json'), response.content)

    def test_transport_failure_and_context_reset(self):
        _, manifest = self.capture(lambda a: metadata_get(Response.url), side_effect=TimeoutError('SECRET'))
        self.assertEqual(manifest['captured_response_count'], 0)
        self.assertEqual(manifest['sources'][0]['transport_error'], 'TimeoutError')
        _, next_manifest = self.capture(lambda a: {})
        self.assertEqual(next_manifest['sources'], [])

    def test_invalid_accession_never_calls_fetcher(self):
        with self.assertRaises(ValueError):
            build_archive('../../bad', lambda a: self.fail('unexpected fetch'))

    def test_zero_and_nested_values_survive(self):
        def fetcher(acc):
            metadata_get(Response.url)
            return {'zero': 0, 'nested': {'x': None}}
        stream, manifest = self.capture(fetcher)
        with ZipFile(stream) as z:
            self.assertEqual(json.loads(z.read('normalized_metadata.json'))['zero'], 0)
        self.assertEqual(manifest['http_success_count'], 1)


if __name__ == '__main__':
    unittest.main()

class FlaskRouteTests(unittest.TestCase):
    def test_zip_response_and_validation(self):
        from flask import Flask
        app = Flask(__name__)
        def fetcher(acc):
            metadata_get(Response.url)
            raise KeyError('mapping failed')
        register_metadata_download(app, fetcher)
        with app.test_client() as client:
            with patch('requests.get', return_value=Response()):
                response = client.get('/api/assembly/GCF_902167145.1/download')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, 'application/zip')
            self.assertIn('GCF_902167145.1_metadata.zip', response.headers['Content-Disposition'])
            from io import BytesIO
            with ZipFile(BytesIO(response.data)) as z:
                self.assertEqual(z.read('sources/001.json'), Response.content)
            self.assertEqual(client.get('/api/assembly/maize/download').status_code, 400)

    def test_no_sources_is_502(self):
        from flask import Flask
        app = Flask(__name__)
        register_metadata_download(app, lambda acc: {})
        with app.test_client() as client:
            self.assertEqual(client.get('/api/assembly/GCF_902167145.1/download').status_code, 502)
