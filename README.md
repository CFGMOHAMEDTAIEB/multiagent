# Multi-agent project

## Layout

- `master_orchestrator.py`: unified FastAPI entry point and explicit service registry.
- `config.yaml`: shared Ollama and agent limits; resolved relative to the repository.
- `BACKEND/`: 11 separately importable services grouped by LLR, LLT, HLT, translation and formatting. Each retains its agents, tools, schemas, provider and orchestrator.
- `FRONTED/ui/`: existing Python UI and React sources. The original directory spelling is retained.
- `RAG/`: retrieval utilities; standalone knowledge base and vector store work independently of the legacy application.
- `llm/`: legacy application LLM adapters.
- `tests/`: backend structure and routing regression checks.

## Run the backend

Requires Python 3.10 or newer. From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn master_orchestrator:app --host 127.0.0.1 --port 8000
```

The configured model is `qwen3:4b-instruct`. Start Ollama with `ollama serve` if it is not already running. `OLLAMA_MODEL` and `OLLAMA_ENDPOINT` override YAML settings. An Ollama server is needed for real inference; imports and health routes do not contact it.

`GET /services` lists chat and documentation URLs. For example, use `POST /agents/llr-generator/chat` with `{"message":"List available documents"}`. Each service also exposes `/health` and `/docs` under its mount. Health indicates API readiness, not model availability.

A service can run separately:

```powershell
python -m uvicorn BACKEND.LLR_Expert.LLR_GENERATOR.main:app --port 8001
```

Run modules from the project root; do not execute nested `main.py` files directly. Place text, Markdown, JSON or CSV evidence in a service's own `documents/` directory (alongside its `main.py`). Importing a service does not create directories. Document tools reject paths outside that service directory.

## Validation

```powershell
python -m unittest discover -s tests -v
```

Tests use mocked model replies; they validate dispatch, not real inference or aerospace correctness.

## Remaining source dependencies

The supplied UI is a partial copy of a larger application. `smartx`, top-level `agents`, `core`, and `validation` packages are absent. They are referenced by the Python UI, `RAG.retriever`, `RAG.project_context`, and legacy local LLM adapters. Restore the matching original application packages before running those features; installing similarly named packages is not a substitute. `requirements.txt` covers the runnable backend only.

The active React agent console loads all services from `/services` and calls their chat endpoints. Legacy frontend sources are preserved but are not the active entry point. Build the console with `npm.cmd run build --prefix FRONTED/ui/react` before starting the backend, then open http://127.0.0.1:8000. Build assets are served from `FRONTED/web-react`. Requests are independent; include relevant context in each request. Tool traces and API errors are displayed per agent. Browser interaction validation remains pending.

All specialist planners currently contain the same generic document-tool prompt. Domain-specific planning and automatic multi-agent workflow scheduling have not been implemented. The master entry point provides explicit service routing.

"# multiagent" 

## Agent files and response downloads

The console's Agent documents section accepts UTF-8 TXT, Markdown, JSON and CSV files up to 1 MB each. Upload names are limited to 100 simple characters; a unique prefix prevents overwrites. Files persist in the selected service's documents directory and are not shared with other agents. Select up to three documents to include their paths in the next request. Tools read at most 16,000 characters per document.

Use Download response to save the generated answer as TXT or Markdown, or as a JSON record containing the agent name and answer. Downloads are created in the browser; they do not write model-selected paths to the server. PDF, DOCX, XLSX and image extraction are not supported.
