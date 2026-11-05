from ..tools.registry import ToolRegistry

class ExecutorAgent:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def execute(self, name: str, arguments: dict) -> str:
        return self.registry.execute(name, arguments)
