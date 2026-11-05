from ..llm.qwen_provider import QwenProvider

class BaseAgent:
    def __init__(self, llm: QwenProvider):
        self.llm = llm
