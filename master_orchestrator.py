"""Unified API entry point for the existing specialist services."""
from importlib import import_module
from pathlib import Path

from fastapi import FastAPI
from BACKEND.file_api import create_file_router
from BACKEND.generated_api import create_generated_router
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

SERVICES = {
    "llr-generator": "BACKEND.LLR_Expert.LLR_GENERATOR",
    "llr-checker": "BACKEND.LLR_Expert.LLR_CHECHER",
    "traceability-generator": "BACKEND.LLR_Expert.MATRICE_TRACA_GENERATOR",
    "traceability-checker": "BACKEND.LLR_Expert.MATRICE_TRACA_CHECKER",
    "data-coupling-generator": "BACKEND.LLR_Expert.DATA_COUPLING_GENERATOR",
    "llt-generator": "BACKEND.LLT_Expert.TEST_GENERATOR",
    "llt-checker": "BACKEND.LLT_Expert.TEST_CHECKER",
    "hlt-generator": "BACKEND.HLT_Expert.TEST_GENERATOR",
    "hlt-checker": "BACKEND.HLT_Expert.TEST_CHECKER",
    "json-translator": "BACKEND.JSON_TRANSLATOR",
    "output-formatting": "BACKEND.OUTPUT_FORMATTING",
}


def create_app():
    application = FastAPI(title="Multi-agent API")

    @application.get("/health")
    def health():
        return {"status": "ok", "services": list(SERVICES)}

    @application.get("/services")
    def services():
        return {name: {"chat": f"/agents/{name}/chat", "docs": f"/agents/{name}/docs"}
                for name in SERVICES}

    application.include_router(create_file_router(SERVICES))
    application.include_router(create_generated_router(SERVICES))

    for name, package in SERVICES.items():
        application.mount(f"/agents/{name}", import_module(f"{package}.main").app)

    @application.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(status_code=204)

    frontend = Path(__file__).resolve().parent / "FRONTED" / "web-react"
    if (frontend / "index.html").is_file():
        application.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    else:
        @application.get("/", include_in_schema=False)
        def home():
            return RedirectResponse("/docs")
    return application


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)



