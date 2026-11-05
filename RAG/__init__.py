from .knowledge_base import KnowledgeBase

__all__ = ["SessionRetriever", "KnowledgeBase"]


def __getattr__(name):
    if name == "SessionRetriever":
        from .retriever import SessionRetriever
        return SessionRetriever
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
