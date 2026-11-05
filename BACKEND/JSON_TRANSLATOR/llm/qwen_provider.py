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
            payload["format"] = Plan.model_json_schema()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.url}/api/chat", json=payload)
            response.raise_for_status()
            return response.json()["message"]["content"]

