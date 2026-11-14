#!/usr/bin/env python3
"""Package the agent for linux/arm64 and create or update the AgentCore Runtime `dezerv_payments_oncall`.
Run with:  uv run --python 3.12 --with boto3 python scripts/deploy_runtime.py
"""
import json, shutil, subprocess, sys, time, zipfile
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from mcpc import load_env

env = load_env()
region, acct = env["AWS_REGION"], env["AWS_ACCOUNT_ID"]
NAME = "dezerv_payments_oncall"
bucket = f"dezerv-laba-artifacts-{acct}-{region}"
ctl, s3 = boto3.client("bedrock-agentcore-control", region_name=region), boto3.client("s3", region_name=region)


def build():
    out = ROOT / "build" / "agent"
    shutil.rmtree(out, ignore_errors=True); out.mkdir(parents=True)
    subprocess.run(["uv", "pip", "install", "--quiet", "--target", str(out), "--python-version", "3.12", "--python-platform", "aarch64-manylinux_2_28",
                    "strands-agents", "mcp", "bedrock-agentcore", "boto3", "opentelemetry-api"], check=True)
    for f in (ROOT / "agent").glob("*.py"):
        shutil.copy(f, out)
    shutil.copytree(ROOT / "agent" / "prompt", out / "prompt", ignore=shutil.ignore_patterns("*.orig"))
    shutil.copy(ROOT / "scripts" / "mcpc.py", out)
    shutil.copy(ROOT / "lambdas" / "interceptor" / "pii.py", out)
    z = ROOT / "build" / "agent.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(out.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                zf.write(p, p.relative_to(out))
    return z


z = build()
key = f"runtime/agent-{int(time.time())}.zip"
s3.upload_file(str(z), bucket, key)
print(f"uploaded {z.stat().st_size // 1024 // 1024} MB -> s3://{bucket}/{key}")

cfg = {k: env[k] for k in ["GATEWAY_URL", "TOKEN_URL", "ONCALL_CLIENT_ID", "ONCALL_CLIENT_SECRET", "SUPPORT_CLIENT_ID", "SUPPORT_CLIENT_SECRET"]}
cfg["MEMORY_ID"] = env["MEMORY_ID"]
cfg["AWS_REGION"] = region
artifact = {"codeConfiguration": {"code": {"s3": {"bucket": bucket, "prefix": key}}, "runtime": "PYTHON_3_12", "entryPoint": ["runtime.py"]}}
existing = next((r for r in ctl.list_agent_runtimes()["agentRuntimes"] if r["agentRuntimeName"] == NAME), None)
if existing:
    rid = existing["agentRuntimeId"]
    ctl.update_agent_runtime(agentRuntimeId=rid, agentRuntimeArtifact=artifact, roleArn=env["RUNTIME_ROLE_ARN"],
                             networkConfiguration={"networkMode": "PUBLIC"}, environmentVariables=cfg, protocolConfiguration={"serverProtocol": "HTTP"})
else:
    r = ctl.create_agent_runtime(agentRuntimeName=NAME, agentRuntimeArtifact=artifact, roleArn=env["RUNTIME_ROLE_ARN"],
                                 networkConfiguration={"networkMode": "PUBLIC"}, environmentVariables=cfg, protocolConfiguration={"serverProtocol": "HTTP"},
                                 description="Dezerv Lab A payments on-call agent")
    rid = r["agentRuntimeId"]
for _ in range(90):
    rt = ctl.get_agent_runtime(agentRuntimeId=rid)
    print("status", rt["status"], flush=True)
    if rt["status"] == "READY":
        break
    if rt["status"] in ("CREATE_FAILED", "UPDATE_FAILED"):
        sys.exit(f"failed: {rt.get('failureReason')}")
    time.sleep(10)
st = ROOT / ".labA.json"
d = json.loads(st.read_text()); d.update(runtime_id=rid, runtime_arn=rt["agentRuntimeArn"]); st.write_text(json.dumps(d, indent=1))
print("runtime READY:", rt["agentRuntimeArn"])
