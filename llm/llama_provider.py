import json
import os
import urllib.request
import time
from .errors import connection_error


class LlamaProvider:
	def __init__(self, endpoint=None, model=None, timeout=None, retries=2):
		self.endpoint = endpoint or os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434")
		self.model = model or os.getenv("OLLAMA_MODEL", "")
		self.timeout, self.retries = timeout if timeout is not None else float(os.getenv("OLLAMA_TIMEOUT", "120")), retries

	def complete(self, prompt: str) -> str:
		return self._generate(prompt)

	def complete_json(self, prompt: str) -> str:
		return self._generate(prompt, json_mode=True)

	def structured(self, role, config, context, logs, *, output_limit=512):
		from agents.universal import OllamaAgents
		from copy import deepcopy
		settings=deepcopy(config)
		settings['model']=settings.get('model') or self.model
		if not settings['model']:raise ValueError('Assign a local Qwen model before invoking an AI agent')
		service=getattr(self,'agent_service',None) or OllamaAgents(self.endpoint)
		return service.execute(role,settings,context,logs,output_limit=output_limit)

	def _generate(self, prompt: str, json_mode=False) -> str:
		from agents.universal import OllamaAgents
		service = OllamaAgents(self.endpoint)
		if not self.model:
			compatible = []
			for item in service.discover():
				try:
					service.inspect(item['name']); compatible.append(item['name'])
				except ValueError:
					continue
			if not compatible: raise ValueError('No compatible installed Qwen model; AI operation blocked')
			self.model = compatible[0]
		service.inspect(self.model)
		from agents.qwen_policy import GUARD
		body = {"model": self.model, "system": GUARD, "prompt": prompt, "stream": False, "options":{"temperature":0,"num_gpu":0}}
		if json_mode:
			body.update(format="json", options={"temperature": 0, "num_gpu":0, "num_predict": getattr(self, "json_num_predict", 768), "num_ctx": getattr(self, "json_num_ctx", 8192)})
		last_error = None
		for attempt in range(self.retries + 1):
			try:
				content = service.transport('/api/generate',body,self.timeout).get('response','')
				if not isinstance(content,str) or not content.strip():raise ValueError('Empty completion')
				return content
			except Exception as exc:
				last_error = connection_error(exc)
				if last_error.status and last_error.status < 500 and last_error.status != 429:
					break
				if attempt < self.retries:
					time.sleep(0.2 * (attempt + 1))
		raise last_error

	def connection_test(self) -> dict:
		self.complete("Return the word OK.")
		return {"ok": True, "provider": "ollama", "model": self.model}

	def list_models(self):
		with urllib.request.urlopen(self.endpoint.rstrip("/") + "/api/tags", timeout=min(self.timeout, 10)) as response:
			return [item["name"] for item in json.loads(response.read())["models"]]
