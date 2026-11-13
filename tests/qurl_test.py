"""Pruebas de publicación directa y errores de qurl.sh."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from services.qurl_service import upload_pdf, valid_pdf_url


class QurlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'demo.pdf'
        self.path.write_bytes(b'%PDF-1.4\n%%EOF')

    def test_valid_link_and_direct_pdf(self):
        response = Mock()
        response.json.return_value = {'url': 'https://qurl.sh/abc123/demo.pdf'}
        with patch('services.qurl_service.requests.put', return_value=response) as put:
            self.assertEqual(upload_pdf(self.path), 'https://qurl.sh/abc123/demo.pdf?raw=true')
            self.assertEqual(put.call_args.kwargs['headers']['X-Downloads'], '100')
        self.assertTrue(valid_pdf_url('https://qurl.sh/abc123/demo.pdf?raw=true'))

    def test_invalid_response_and_connection_error(self):
        response = Mock()
        response.json.return_value = {'url': 'https://evil.test/abc/demo.pdf'}
        with patch('services.qurl_service.requests.put', return_value=response):
            with self.assertRaises(ValueError):
                upload_pdf(self.path)
        with patch('services.qurl_service.requests.put', side_effect=requests.ConnectionError('offline')):
            with self.assertRaises(requests.ConnectionError):
                upload_pdf(self.path)


if __name__ == '__main__':
    unittest.main()
