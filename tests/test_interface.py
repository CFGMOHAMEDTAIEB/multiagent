import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from master_orchestrator import create_app, SERVICES

class InterfaceTests(unittest.TestCase):
    def test_registry_matches_backend(self):
        root = Path(__file__).resolve().parents[1]
        modules = {'.'.join(path.relative_to(root).with_suffix('').parts[:-1])
                   for path in (root / 'BACKEND').rglob('main.py')}
        self.assertEqual(set(SERVICES.values()), modules)

    def test_built_interface_is_served(self):
        with TestClient(create_app()) as client:
            response = client.get('/')
            self.assertEqual(response.status_code, 200)
            self.assertIn('<div id="root"></div>', response.text)
            self.assertEqual(client.get('/favicon.ico').status_code, 204)
            self.assertEqual(client.get('/unknown-api').status_code, 404)
