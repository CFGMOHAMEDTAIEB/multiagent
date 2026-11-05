"""Agent-scoped UTF-8 document uploads; originals are never overwritten."""
from importlib import import_module
from pathlib import Path
import re
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

LIMIT = 1_000_000
EXTENSIONS = {".txt", ".md", ".json", ".csv"}


def create_file_router(services):
    router = APIRouter(prefix="/files")

    def workspace(service):
        if service not in services:
            raise HTTPException(404, "Unknown agent")
        return import_module(services[service] + ".tools.document_tools").WORKSPACE

    def safe_name(filename):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,119}", filename) or ".." in filename:
            raise HTTPException(400, "Use a simple filename of up to 120 characters without directory paths.")
        if Path(filename).suffix.lower() not in EXTENSIONS:
            raise HTTPException(415, "Supported formats: TXT, Markdown, JSON and CSV (UTF-8).")
        return filename

    @router.get("/{service}")
    def list_files(service: str):
        root = workspace(service)
        if not root.exists():
            return []
        return [{"name": p.name, "size": p.stat().st_size}
                for p in sorted(root.iterdir())
                if p.is_file() and not p.is_symlink() and p.suffix.lower() in EXTENSIONS]

    @router.post("/{service}", status_code=201)
    async def upload(service: str, filename: str, request: Request):
        root = workspace(service)
        filename = safe_name(filename)
        if len(filename) > 100:
            raise HTTPException(400, "Upload filenames must be at most 100 characters.")
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > LIMIT:
                raise HTTPException(413, "File exceeds the 1 MB limit.")
        if not content:
            raise HTTPException(400, "File is empty.")
        try:
            decoded = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(415, "Save this document as UTF-8 text before uploading.") from None
        if "\x00" in decoded:
            raise HTTPException(415, "Binary files are not supported.")
        root.mkdir(parents=True, exist_ok=True)
        # Unique names prevent collisions and preserve previous uploads.
        stored = uuid4().hex[:12] + "_" + filename
        with (root / stored).open("xb") as output:
            output.write(content)
        return {"name": stored, "size": len(content)}

    @router.get("/{service}/{filename}")
    def download(service: str, filename: str):
        root = workspace(service).resolve()
        safe_name(filename)
        target = root / filename
        if target.is_symlink() or not target.resolve().is_relative_to(root) or not target.is_file():
            raise HTTPException(404, "Document not found.")
        return FileResponse(target, filename=filename, media_type="application/octet-stream")

    return router


