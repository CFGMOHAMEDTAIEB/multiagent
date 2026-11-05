import importlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from master_orchestrator import app, SERVICES
from BACKEND.configuration import load_config


class StructureTests(unittest.TestCase):
    def test_all_service_routes(self):
        with TestClient(app) as client:
            self.assertEqual(client.get('/health').status_code, 200)
            self.assertEqual(len(client.get('/services').json()), 11)
            for name in SERVICES:
                self.assertEqual(client.get(f'/agents/{name}/health').status_code, 200)
                self.assertEqual(client.get(f'/agents/{name}/openapi.json').status_code, 200)
                self.assertEqual(client.post(f'/agents/{name}/chat', json={'message': ''}).status_code, 422)

    def test_chat_dispatch(self):
        with TestClient(app) as client:
            for name, package in SERVICES.items():
                module = importlib.import_module(package + '.main')
                async def answer(messages, json_mode=False):
                    return '{"action":"respond","message":"checked","tool_args":{}}'
                with patch.object(module.llm, 'chat', side_effect=answer):
                    response = client.post(f'/agents/{name}/chat', json={'message': 'hello'})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['answer'], 'checked')

    def test_configuration_outside_project(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                self.assertGreater(load_config()['agent']['max_steps'], 0)
            finally:
                os.chdir(previous)

    def test_document_isolation_and_traversal(self):
        workspaces = set()
        for package in SERVICES.values():
            module = importlib.import_module(package + '.tools.document_tools')
            self.assertNotIn(module.WORKSPACE, workspaces)
            workspaces.add(module.WORKSPACE)
            with self.assertRaises(ValueError):
                module._safe_path('../outside.txt')
            with tempfile.TemporaryDirectory() as directory:
                with patch.object(module, 'WORKSPACE', Path(directory)):
                    Path(directory, 'evidence.txt').write_text('test evidence', encoding='utf-8')
                    self.assertEqual(module.read_document('evidence.txt'), 'test evidence')
                    self.assertIn('evidence.txt', module.list_documents())

    def test_standalone_rag_imports(self):
        from RAG import KnowledgeBase
        from RAG.vectorstore import VectorStore
        self.assertTrue(callable(KnowledgeBase))
        self.assertTrue(callable(VectorStore))


if __name__ == '__main__':
    unittest.main()
