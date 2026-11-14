#!/usr/bin/env python3
"""verify.py <target> : PASS/FAIL with a hint per check (spec section 9)."""
import json, re, subprocess, sys, time
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import mcpc

env = mcpc.load_env()
REGION = env.get("AWS_REGION", "us-west-2")
st = json.loads((ROOT / ".labA.json").read_text()) if (ROOT / ".labA.json").exists() else {}
fails = 0
AGENT_DEPS = ["--with", "boto3", "--with", "strands-agents", "--with", "mcp", "--with", "bedrock-agentcore", "--with", "opentelemetry-api"]


def check(label, ok, hint=""):
    global fails
    fails += (not ok)
    print(("PASS  " if ok else "FAIL  ") + label + ("" if ok or not hint else f"\n      hint: {hint}"))


def run_agent(task):
    p = subprocess.run(["uv", "run", "--python", "3.12", *AGENT_DEPS, "python", str(ROOT / "agent/main.py"), "--task", task],
                       capture_output=True, text=True, cwd=ROOT, timeout=900)
    return p.stdout + p.stderr


def script(name):
    p = subprocess.run(["uv", "run", "--python", "3.12", "--with", "boto3", "python", str(ROOT / "scripts" / name)], capture_output=True, text=True, cwd=ROOT, timeout=600)
    print("\n".join("      " + l for l in p.stdout.strip().splitlines()))
    return p.returncode == 0


def last_session_audit():
    logs = boto3.client("logs", region_name=REGION)
    streams = logs.describe_log_streams(logGroupName="/dezerv/agent-audit", orderBy="LastEventTime", descending=True, limit=1)["logStreams"]
    if not streams:
        return []
    evs = logs.get_log_events(logGroupName="/dezerv/agent-audit", logStreamName=streams[0]["logStreamName"], startFromHead=True)["events"]
    return [json.loads(e["message"]) for e in evs]


def v_bootstrap():
    cf = boto3.client("cloudformation", region_name=REGION)
    s = cf.describe_stacks(StackName="DezervLabA")["Stacks"][0]["StackStatus"]
    check("stack DezervLabA complete", s in ("CREATE_COMPLETE", "UPDATE_COMPLETE"), f"status={s}; run make bootstrap")
    lg = boto3.client("logs", region_name=REGION)
    n, tok = 0, None
    while True:
        r = lg.filter_log_events(logGroupName="/dezerv/payments-gw", **({"nextToken": tok} if tok else {}))
        n += len(r["events"]); tok = r.get("nextToken")
        if not tok:
            break
    check(f"log group has >= 5000 events (found {n})", n >= 5000, "backfill skipped? delete streams in /dezerv/payments-gw and rerun make bootstrap")
    check("smoke: tool Lambdas invoke", script("smoke_tools.py") is True, "see scripts/smoke_tools.py output")
    for p in ("oncall", "support"):
        try:
            mcpc.token(p, env); ok = True
        except Exception as e:
            ok = False
        check(f"Cognito token for {p}", ok, "check .env client ids/secrets")


def v_part1():
    ctl = boto3.client("bedrock-agentcore-control", region_name=REGION)
    gid = st["gateway_id"]
    deployed = sum(len(ctl.get_gateway_target(gatewayIdentifier=gid, targetId=t["targetId"])["targetConfiguration"]["mcp"]["lambda"]["toolSchema"]["inlinePayload"])
                   for t in ctl.list_gateway_targets(gatewayIdentifier=gid)["items"])
    check(f"gateway exposes >= 12 tools across its targets (found {deployed})", deployed >= 12, "make gateway")
    tools = mcpc.list_tools("oncall")
    attached = bool(ctl.get_gateway(gatewayIdentifier=gid).get("policyEngineConfiguration"))
    # once Cedar is attached the Gateway hides tools the caller may never use (the 3 forbidden ops tools)
    want = deployed - 3 if attached else deployed
    check(f"tools/list matches (found {len(tools)}, expected {want}{' = ops tools hidden by policy' if attached else ''})", len(tools) == want, "make gateway / make policy")
    out = run_agent("incident")
    check("incident run mentions v2.14.3 or a1f9c3e", bool(re.search(r"v2\.14\.3|a1f9c3e", out)), "agent did not find the deploy; check get_recent_deploys")


def v_part2():
    check("policy checks (restart denied, support denied, limit=500 denied, reads allowed)", script("check_part2.py"), "make policy; confirm engine is ENFORCE")


def v_part3():
    t0 = time.time() * 1000
    check("masking / untrusted tags / freeze / rate limit", script("check_part3.py"), "make interceptors")
    out = run_agent("injection")
    ops = boto3.client("logs", region_name=REGION).filter_log_events(logGroupName="/aws/lambda/dezerv-laba-ops", startTime=int(t0), filterPattern="WOULD_EXECUTE")["events"]
    check(f"injection run: decoy never executed ({len(ops)} WOULD_EXECUTE)", len(ops) == 0, "policy is not blocking ops tools: make policy")


def v_part4():
    recs = last_session_audit()
    tools_b = [r for r in recs if r["event"] == "before_tool_call"]
    tools_a = [r for r in recs if r["event"] == "after_tool_call"]
    check(f"last session has before+after for each tool call ({len(tools_b)}/{len(tools_a)})", len(tools_b) > 0 and len(tools_b) == len(tools_a), "run make run-incident first")
    check("every after_tool_call has a decision", all(r.get("decision", {}).get("result") for r in tools_a))
    need = {"ts", "agent_id", "session_id", "task_id", "principal", "event", "trace_id"}
    check("records carry the TLA-07 minimum fields", all(need <= set(r) for r in recs))


def v_part5():
    dp = boto3.client("bedrock-agentcore", region_name=REGION)
    n = len(dp.list_memory_records(memoryId=st["memory_id"], namespace="/products/payments-gw/incidents", maxResults=100)["memoryRecordSummaries"])
    check(f"memory has >= 25 incident records (found {n})", n >= 25, "make seed-memory")
    out = run_agent("incident")
    check("rerun cites INC-2026-031", "INC-2026-031" in out, "rerun once; retrieval is semantic and the model picks the closest precedent")
    check("rerun cites RB-PSP-TIMEOUT", "RB-PSP-TIMEOUT" in out)


def v_part6():
    ctl = boto3.client("bedrock-agentcore-control", region_name=REGION)
    rt = ctl.get_agent_runtime(agentRuntimeId=st["runtime_id"])["status"]
    check(f"runtime READY ({rt})", rt == "READY", "make deploy-agent")
    base = ROOT / "evals" / "report_baseline.json"
    check("baseline report exists and gate passes", base.exists() and subprocess.run([sys.executable, str(ROOT / "evals/gate.py"), "report_baseline.json"], capture_output=True).returncode == 0, "make eval, then make gate")
    broken = ROOT / "evals" / "report_broken.json"
    if broken.exists():
        check("gate FAILS on the broken-prompt report", subprocess.run([sys.executable, str(ROOT / "evals/gate.py"), "report_broken.json"], capture_output=True).returncode != 0, "break-prompt did not cause a regression this run; rerun the eval")
    else:
        print("SKIP  break-it check (run make break-prompt, make deploy-agent, make eval OUT=evals/report_broken.json)")


{"verify-bootstrap": v_bootstrap, "verify-labA-part1": v_part1, "verify-labA-part2": v_part2, "verify-labA-part3": v_part3,
 "verify-labA-part4": v_part4, "verify-labA-part5": v_part5, "verify-labA-part6": v_part6}[sys.argv[1]]()
print("\nRESULT:", "PASS" if not fails else f"FAIL ({fails} check(s))")
sys.exit(1 if fails else 0)
