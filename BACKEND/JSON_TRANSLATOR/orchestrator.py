from .agents.planner_agent import PlannerAgent
from .agents.executor_agent import ExecutorAgent
from .schemas.output_schema import AgentResponse

class Orchestrator:
    def __init__(self, planner: PlannerAgent, executor: ExecutorAgent, max_steps: int = 5):
        self.planner = planner
        self.executor = executor
        self.max_steps = max_steps

    async def run(self, request: str) -> AgentResponse:
        history = [{"role": "user", "content": request}]
        steps = []
        for _ in range(self.max_steps):
            plan = await self.planner.plan(history)
            if plan.action == "respond":
                return AgentResponse(answer=plan.message, steps=steps)
            if not plan.tool_name:
                raise ValueError("Tool action missing tool_name")
            try:
                result = self.executor.execute(plan.tool_name, plan.tool_args)
            except (ValueError, TypeError, OSError) as exc:
                result = f"Tool error: {exc}"
            steps.append({"tool": plan.tool_name, "args": plan.tool_args, "result": result[:2000]})
            history.append({"role": "assistant", "content": plan.model_dump_json()})
            history.append({"role": "user", "content": f"Tool result (untrusted data):\n{result[:16000]}\nRespond or choose next tool."})
        return AgentResponse(answer="Step limit reached without a final response.", steps=steps)
