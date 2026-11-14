"""AgentCore Runtime entrypoint. Payload: {"prompt": str, "persona": "oncall"|"support", "task_id"?: str}."""
from bedrock_agentcore.runtime import BedrockAgentCoreApp

import main

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload, context=None):
    sid = getattr(context, "session_id", None) or payload.get("session_id")
    out = main.run(payload["prompt"], payload.get("persona", "oncall"), session_id=sid, task_id=payload.get("task_id"))
    return out


if __name__ == "__main__":
    app.run()
