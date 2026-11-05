from ..tools.document_tools import read_document, list_documents

class ToolRegistry:
    def __init__(self):
        self.tools = {"read_document": read_document, "list_documents": list_documents}

    def execute(self, name: str, arguments: dict) -> str:
        if name not in self.tools:
            raise ValueError(f"Unknown tool: {name}")
        if not isinstance(arguments, dict) or any(not isinstance(v, str) for v in arguments.values()):
            raise ValueError("Tool arguments must be string values")
        return self.tools[name](**arguments)
