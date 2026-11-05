import importlib
import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from master_orchestrator import app, SERVICES

class PlanRepairTests(unittest.TestCase):
    def test_string_arguments_are_repaired_for_every_service(self):
        for name, package in SERVICES.items():
            module = importlib.import_module(package + '.main')
            replies = [
                '{"action":"tool","tool_name":"list_documents","tool_args":"./documents"}',
                '{"action":"tool","tool_name":"list_documents","tool_args":{"directory":"."}}',
                '{"action":"respond","message":"Done","tool_args":{}}',
            ]
            with patch.object(module.llm, 'chat', new=AsyncMock(side_effect=replies)) as chat:
                response = TestClient(app).post(f'/agents/{name}/chat', json={'message':'List documents'})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['steps'][0]['args'], {'directory':'.'})
            self.assertEqual(chat.await_count, 3)

    def test_repair_is_bounded(self):
        module = importlib.import_module(SERVICES['llr-generator'] + '.main')
        with patch.object(module.llm, 'chat', new=AsyncMock(return_value='{"tool_args":"bad"}')) as chat:
            response = TestClient(app).post('/agents/llr-generator/chat', json={'message':'List documents'})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(chat.await_count, 2)
        self.assertIn('after one repair attempt', response.json()['detail'])

    def test_ollama_receives_plan_schema(self):
        import httpx
        for package in SERVICES.values():
            module = importlib.import_module(package + '.main')
            response = httpx.Response(200, json={'message':{'content':'{}'}}, request=httpx.Request('POST','http://localhost/api/chat'))
            client = AsyncMock()
            client.post.return_value = response
            with patch('httpx.AsyncClient') as factory:
                factory.return_value.__aenter__.return_value = client
                import asyncio
                asyncio.run(module.llm.chat([], json_mode=True))
            schema = client.post.call_args.kwargs['json']['format']
            self.assertEqual(schema['properties']['tool_args']['type'], 'object')
