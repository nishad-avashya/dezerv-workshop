"""Invoke the deployed AgentCore Runtime agent."""
import json, os, sys, uuid
from pathlib import Path

import boto3
from botocore.config import Config

ROOT = Path(__file__).resolve().parent.parent
STATE = json.loads((ROOT / ".labA.json").read_text()) if (ROOT / ".labA.json").exists() else {}
REGION = "us-west-2"
_client = boto3.client("bedrock-agentcore", region_name=REGION, config=Config(read_timeout=900, retries={"max_attempts": 1}))


def invoke(prompt, persona="oncall", session_id=None, task_id=None):
    sid = session_id or f"eval-{uuid.uuid4().hex}"            # runtime session ids must be >= 33 chars
    r = _client.invoke_agent_runtime(agentRuntimeArn=os.environ.get("RUNTIME_ARN") or STATE["runtime_arn"], runtimeSessionId=sid.ljust(33, "0"),
                                     payload=json.dumps({"prompt": prompt, "persona": persona, "task_id": task_id or sid, "session_id": sid.ljust(33, "0")}).encode())
    body = r["response"].read().decode()
    try:
        return json.loads(body)
    except ValueError:
        return {"answer": body, "session_id": sid}


if __name__ == "__main__":
    out = invoke(sys.argv[1] if len(sys.argv) > 1 else "Customer escalated PAY-1287, please handle")
    print(json.dumps(out, indent=1)[:3000])
