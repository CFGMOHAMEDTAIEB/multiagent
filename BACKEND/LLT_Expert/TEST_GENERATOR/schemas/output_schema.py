from typing import Any, Literal
from pydantic import BaseModel, Field

class Plan(BaseModel):
    action: Literal["respond", "tool"]
    message: str = ""
    tool_name: Literal["list_documents", "read_document"] | None = None
    tool_args: dict[str, str] = Field(default_factory=dict, json_schema_extra={"properties": {"directory": {"type": "string"}, "path": {"type": "string"}}, "additionalProperties": False})

class AgentResponse(BaseModel):
    answer: str
    steps: list[dict[str, Any]] = Field(default_factory=list)

