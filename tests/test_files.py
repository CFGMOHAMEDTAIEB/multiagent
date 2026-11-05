import importlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from master_orchestrator import app, SERVICES

class FileTests(unittest.TestCase):
    def test_upload_read_download_and_isolation(self):
        module = importlib.import_module(SERVICES['llr-generator'] + '.tools.document_tools')
        with tempfile.TemporaryDirectory() as directory, patch.object(module, 'WORKSPACE', Path(directory)):
            client = TestClient(app)
            response = client.post('/files/llr-generator?filename=evidence.txt', content=b'Requirement ABC')
            self.assertEqual(response.status_code, 201, response.text)
            name = response.json()['name']
            self.assertEqual(module.read_document(name), 'Requirement ABC')
            self.assertEqual(client.get('/files/llr-generator/' + name).content, b'Requirement ABC')
            self.assertEqual(client.get('/files/llt-generator/' + name).status_code, 404)
            second = client.post('/files/llr-generator?filename=evidence.txt', content=b'Second')
            self.assertNotEqual(name, second.json()['name'])
            self.assertEqual(len(client.get('/files/llr-generator').json()), 2)

    def test_rejected_uploads(self):
        client = TestClient(app)
        for filename, body, status in [
            ('../escape.txt', b'bad', 400), ('file.pdf', b'bad', 415),
            ('file.txt', b'', 400), ('file.txt', b'\xff', 415),
            ('file.txt', b'\x00', 415), ('file.txt', b'a' * 1000001, 413),
        ]:
            with self.subTest(filename=filename, status=status):
                self.assertEqual(client.post('/files/llr-generator', params={'filename':filename}, content=body).status_code, status)
        self.assertEqual(client.post('/files/missing?filename=a.txt', content=b'a').status_code, 404)
