from pathlib import Path

WORKSPACE = (Path(__file__).resolve().parents[1] / "documents").resolve()

def _safe_path(path: str) -> Path:
    candidate = (WORKSPACE / path).resolve()
    if not candidate.is_relative_to(WORKSPACE):
        raise ValueError("Path outside documents workspace")
    return candidate

def read_document(path: str) -> str:
    target = _safe_path(path)
    if not target.is_file() or target.suffix.lower() not in {".txt", ".md", ".json", ".csv"}:
        raise ValueError("File not found or unsupported format (txt/md/json/csv)")
    if target.stat().st_size > 1_000_000:
        raise ValueError("File exceeds 1 MB limit")
    return target.read_text(encoding="utf-8")[:16000]

def list_documents(directory: str = ".") -> str:
    target = _safe_path(directory)
    if target == WORKSPACE and not target.exists():
        return "No documents found in this directory."
    if not target.is_dir():
        raise ValueError("Directory not found")
    return "\n".join(p.name for p in sorted(target.iterdir())[:100]) or "No documents found in this directory."

