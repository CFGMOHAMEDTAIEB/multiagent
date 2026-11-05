class VectorStore:
    """In-memory placeholder. No embeddings or persistence yet."""
    def __init__(self):
        self.items: list[str] = []

    def add(self, text: str) -> None:
        self.items.append(text)

    def search(self, query: str, limit: int = 3) -> list[str]:
        terms = set(query.lower().split())
        return sorted(self.items, key=lambda item: len(terms.intersection(item.lower().split())), reverse=True)[:limit]
