"""Compatibility import for the existing Ollama provider; no separate integration."""
from .llama_provider import LlamaProvider

__all__ = ['LlamaProvider']
