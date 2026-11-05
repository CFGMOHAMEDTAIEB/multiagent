"""Configuration shared by all backend services, independent of cwd."""
import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent


class OllamaSettings(BaseModel):
    url: str = "http://127.0.0.1:11434"
    model: str = Field(min_length=1)
    timeout_seconds: int = Field(default=120, gt=0)


class AgentSettings(BaseModel):
    max_steps: int = Field(default=5, ge=1, le=100)


class Settings(BaseModel):
    ollama: OllamaSettings
    agent: AgentSettings = Field(default_factory=AgentSettings)


def load_config(path=None):
    source = Path(path) if path is not None else ROOT / "config.yaml"
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Configuration must be a mapping: {source}")
    if os.getenv("OLLAMA_MODEL"):
        data.setdefault("ollama", {})["model"] = os.environ["OLLAMA_MODEL"]
    if os.getenv("OLLAMA_ENDPOINT"):
        data.setdefault("ollama", {})["url"] = os.environ["OLLAMA_ENDPOINT"]
    return Settings.model_validate(data).model_dump()
