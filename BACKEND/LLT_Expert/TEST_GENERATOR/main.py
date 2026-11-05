from BACKEND.configuration import load_config
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from .llm.qwen_provider import QwenProvider
from .agents.planner_agent import PlannerAgent
from .agents.executor_agent import ExecutorAgent
from .tools.registry import ToolRegistry
from .orchestrator import Orchestrator
from .schemas.output_schema import AgentResponse

config = load_config()
llm = QwenProvider(config["ollama"]["url"], config["ollama"]["model"], config["ollama"]["timeout_seconds"])
agent = Orchestrator(PlannerAgent(llm), ExecutorAgent(ToolRegistry()), config["agent"]["max_steps"])
app = FastAPI(title="Qwen Local AI Agent")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["POST", "GET"], allow_headers=["*"])

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)

@app.get("/health")
def health():
    return {"status": "ok", "model": llm.model}

@app.post("/chat", response_model=AgentResponse)
async def chat(body: ChatRequest):
    try:
        return await agent.run(body.message)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Agent failed: {type(exc).__name__}: {exc}") from exc
