"""Validated, persistent generated files isolated by service."""
import json
import re
from importlib import import_module
from pathlib import Path
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

class GenerateRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=80)
    format: Literal["json", "txt", "md"] = "json"
    sources: list[str] = Field(default_factory=list, max_length=3)
    content: str | None = Field(default=None, max_length=1_000_000)

def create_generated_router(services):
    router = APIRouter(prefix="/generated")

    def roots(service):
        if service not in services:
            raise HTTPException(404, "Unknown agent")
        docs = import_module(services[service] + ".tools.document_tools").WORKSPACE.resolve()
        return docs, docs.parent / "generated"

    def safe_path(root, name):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,119}", name) or ".." in name:
            raise HTTPException(400, "Use a simple filename without directory paths.")
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise HTTPException(400, "Invalid file path")
        return path

    @router.get("/{service}")
    def listing(service: str):
        _, root = roots(service)
        if not root.exists():
            return []
        return [{"name": p.name, "size": p.stat().st_size}
                for p in sorted(root.iterdir(), key=lambda p: p.name, reverse=True)
                if p.is_file() and not p.is_symlink() and p.suffix in {".json", ".txt", ".md"}]

    @router.post("/{service}", status_code=201)
    def generate(service: str, body: GenerateRequest):
        docs, root = roots(service)
        if bool(body.sources) == (body.content is not None):
            raise HTTPException(400, "Provide either selected sources or response content.")
        if body.sources:
            if body.format != "json":
                raise HTTPException(400, "Source conversion produces JSON.")
            documents = []
            for name in body.sources:
                path = safe_path(docs, name)
                if not path.is_file():
                    raise HTTPException(404, "Selected document not found.")
                if path.stat().st_size > 1_000_000:
                    raise HTTPException(413, "Source exceeds 1 MB.")
                try:
                    content = path.read_text(encoding="utf-8-sig")
                except UnicodeDecodeError:
                    raise HTTPException(415, "Source must be UTF-8.") from None
                documents.append({"filename": name, "content": content})
            text = json.dumps({"documents": documents}, ensure_ascii=False, indent=2)
        else:
            text = body.content
            if not text or not text.strip():
                raise HTTPException(400, "Cannot save an empty response.")
            if body.format == "json":
                candidate = text.strip()
                if candidate.startswith("```") and candidate.endswith("```"):
                    candidate = candidate.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                try:
                    parsed = json.loads(candidate, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
                    text = json.dumps(parsed, ensure_ascii=False, indent=2, allow_nan=False)
                except (ValueError, TypeError):
                    raise HTTPException(422, "Response is not valid JSON. Choose TXT/Markdown or request JSON output.") from None
        stem = Path(body.filename).stem
        safe_path(root, stem)
        name = uuid4().hex[:12] + "_" + stem + "." + body.format
        target = safe_path(root, name)
        root.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8", newline="") as output:
            output.write(text)
        return {"name": name, "size": target.stat().st_size}

    @router.get("/{service}/{filename}")
    def download(service: str, filename: str, preview: bool = False):
        _, root = roots(service)
        path = safe_path(root, filename)
        if not path.is_file() or path.suffix not in {".json", ".txt", ".md"}:
            raise HTTPException(404, "Generated file not found.")
        if preview:
            with path.open(encoding="utf-8") as source:
                text = source.read(20001)
            return {"content": text[:20000], "truncated": len(text) > 20000}
        return FileResponse(path, filename=filename, media_type="application/json" if path.suffix == ".json" else "text/plain")
    return router
