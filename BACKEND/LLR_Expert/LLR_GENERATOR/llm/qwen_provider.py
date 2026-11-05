import httpx
from ..schemas.output_schema import Plan

class QwenProvider:
    def __init__(self, url: str, model: str, timeout: int = 120):
        self.url = url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def chat(self, messages: list[dict], json_mode: bool = False) -> str:
        payload = {"model": self.model, "messages": messages, "stream": False,
                   "options": {"temperature": 0.1}}
        if json_mode:
            schema = Plan.model_json_schema()
            schema["anyOf"] = [
                {"properties": {"action": {"const": "respond"}, "message": {"type": "string", "minLength": 1}}, "required": ["action", "message"]},
                {"properties": {
                    "action": {"const": "tool"},
                    "tool_name": {"const": "read_document"},
                    "tool_args": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False}
                }, "required": ["action", "tool_name", "tool_args"]},
                {"properties": {
                    "action": {"const": "tool"},
                    "tool_name": {"const": "list_documents"},
                    "tool_args": {"type": "object", "properties": {"directory": {"type": "string"}}, "additionalProperties": False}
                }, "required": ["action", "tool_name", "tool_args"]},
            ]
            payload["format"] = schema
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.url}/api/chat", json=payload)
            if response.status_code == 400 and json_mode:
                # Some Ollama builds reject compound JSON grammars.
                error = response.text.lower()
                if any(word in error for word in ("schema", "grammar", "format")):
                    payload["format"] = Plan.model_json_schema()
                    response = await client.post(f"{self.url}/api/chat", json=payload)
            if response.is_error:
                try:
                    detail = response.json().get("error", "No error details")
                except ValueError:
                    detail = response.text
                raise RuntimeError(f"Ollama returned {response.status_code}: {str(detail)[:500]}")
            return response.json()["message"]["content"]




