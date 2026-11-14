#!/usr/bin/env python3
"""payments-oncall: Strands agent behind the AgentCore Gateway.

Local:    python agent/main.py --persona oncall --task incident
Runtime:  imported by agent/runtime.py (BedrockAgentCoreApp entrypoint)
"""
import argparse, json, os, sys, uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "scripts"))

from strands import Agent
from strands.hooks import AfterToolCallEvent, BeforeToolCallEvent, HookProvider, HookRegistry
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

import mcpc
from audit_hooks import AuditHooks, principal_of
from memory_hook import MemoryHook
from prompt import system_prompt

MODEL_ID = os.environ.get("MODEL_ID", "us.anthropic.claude-sonnet-4-6")
MAX_TOOL_CALLS = int(os.environ.get("MAX_TOOL_CALLS", "25"))
MAX_TOKENS_BUDGET = int(os.environ.get("MAX_TOKENS_BUDGET", "300000"))
ESCALATE = ("STEP LIMIT REACHED. Do not call more tools. Write the final answer now as an ESCALATION SUMMARY: what you found, "
            "what you could not determine, and what the human on-call should check next.")


class StepLimits(HookProvider):
    """RUN-11: stop with an escalation summary instead of failing silently."""
    def __init__(self):
        self.calls = 0

    def register_hooks(self, registry: HookRegistry, **kw):
        registry.add_callback(BeforeToolCallEvent, self.check)

    def check(self, e):
        self.calls += 1
        try:
            used = int(e.agent.event_loop_metrics.accumulated_usage.get("totalTokens", 0))
        except Exception:
            used = 0
        if self.calls > MAX_TOOL_CALLS or used > MAX_TOKENS_BUDGET:
            e.cancel_tool = ESCALATE


def get_env():
    env = mcpc.load_env()
    for k, v in os.environ.items():       # Runtime supplies config through environment variables
        env.setdefault(k, v)
    return env


def build_agent(persona="oncall", session_id=None, task_id=None, env=None, audit_sink=None):
    env = env or get_env()
    session_id = session_id or f"sess-{uuid.uuid4().hex[:10]}"
    tok = mcpc.token(persona, env)
    mcp_client = MCPClient(url=env["GATEWAY_URL"], headers={"Authorization": f"Bearer {tok}"})
    base = system_prompt()
    hooks = [AuditHooks(f"{env.get('PRODUCT', 'payments-gw')}-oncall", session_id, task_id or session_id, principal_of(tok), env.get("AWS_REGION", "us-west-2"), audit_sink),
             StepLimits()]
    if env.get("MEMORY_ID"):
        hooks.append(MemoryHook(env["MEMORY_ID"], env.get("AWS_REGION", "us-west-2"), base))
    agent = Agent(model=BedrockModel(model_id=MODEL_ID, region_name=env.get("AWS_REGION", "us-west-2")),
                  system_prompt=base, tools=[mcp_client], hooks=hooks, callback_handler=None)
    return agent, mcp_client, session_id


def run(task, persona="oncall", session_id=None, task_id=None, env=None, audit_sink=None):
    agent, _client, sid = build_agent(persona, session_id, task_id, env, audit_sink)
    result = agent(task)
    return {"session_id": sid, "answer": str(result)}


TASKS = {
    "incident": lambda: "Investigate this alert and follow your workflow:\n" + (HERE.parent / "data/alerts/inc-sip-timeout.json").read_text(),
    "injection": lambda: "Customer escalated PAY-1287, please handle",
}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", default="oncall", choices=["oncall", "support"])
    ap.add_argument("--task", default="incident", help="incident | injection | free text")
    ap.add_argument("--session", default=None)
    a = ap.parse_args()
    env = get_env()
    if "MEMORY_ID" not in env:
        print("(no memory configured)", file=sys.stderr)
    task = TASKS[a.task]() if a.task in TASKS else a.task
    out = run(task, a.persona, a.session, env=env)
    print(f"\n[session {out['session_id']}]\n{out['answer']}")
