#!/usr/bin/env python3
"""verify_b.py <target> : Lab B checks (spec section 7). Needs Lab A deployed and the factory agent rendered + deployed."""
import json, os, re, shutil, subprocess, sys, time
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "factory"))
import mcpc  # noqa: E402

env = dict(mcpc.load_env())
REGION = env.get("AWS_REGION", "us-west-2")
PRODUCT = "payments-gw"
AG = ROOT / "agents" / PRODUCT
fails = 0


def check(label, ok, hint=""):
    global fails
    fails += (not ok)
    print(("PASS  " if ok else "FAIL  ") + label + ("" if ok or not hint else f"\n      hint: {hint}"))


def state():
    p = AG / ".state.json"
    if not p.exists():
        sys.exit(f"FAIL  {PRODUCT} is not deployed: make new-agent NAME={PRODUCT} FROM=labs/B/agent.yaml && make deploy-agent NAME={PRODUCT}")
    return json.loads(p.read_text())


def fenv():
    e = dict(env); e["GATEWAY_URL"] = state()["gateway_url"]
    return e


def parse(text):
    """Cedar statement -> (shape, actions). shape is the statement with its action list removed; actions is a set."""
    out = []
    for p in text.split(";"):
        if "permit(" not in p and "forbid(" not in p:
            continue
        p = "\n".join(l for l in p.splitlines() if not l.lstrip().startswith("//"))
        p = re.sub(r"\s+", " ", p).strip().replace('"{{GATEWAY_ARN}}"', "ARN")
        acts = frozenset(re.findall(r'AgentCore::Action::"([^"]+)"', p))
        out.append((re.sub(r"AgentCore::Action::\"[^\"]+\",? ?", "", p), acts))
    return out


def reproduced(labA, got):
    """Every Lab A statement must appear in the factory output with the same shape and at least the same actions.
    (A superset is correct: a mutating custom tool legitimately joins the ops tools in the CP-3 forbid.)"""
    return [a for a in labA if not any(a[0] == g[0] and a[1] <= g[1] for g in got)]


def v_part1():
    check("agents/payments-gw/ rendered with a manifest sha", (AG / ".manifest.sha").exists(), "make new-agent NAME=payments-gw FROM=labs/B/agent.yaml")
    labA, got = [], []
    for f in (ROOT / "policy/cedar").glob("*.cedar"):
        labA += parse(f.read_text())
    for f in (AG / "policy").glob("*.cedar"):
        got += parse(f.read_text())
    miss = reproduced(labA, got)
    check(f"rendered Cedar reproduces every Lab A policy ({len(labA)} statements)", not miss, f"{len(miss)} missing; compare agents/payments-gw/policy with policy/cedar")
    st = state()
    ctl = boto3.client("bedrock-agentcore-control", region_name=REGION)
    rt = ctl.get_agent_runtime(agentRuntimeId=st["runtime_id"])["status"]
    check(f"factory runtime READY ({rt})", rt == "READY", "make deploy-agent NAME=payments-gw")
    rep = AG / "report.json"
    if rep.exists():
        ok = subprocess.run([sys.executable, str(ROOT / "evals/gate.py"), str(rep), str(AG / "evals/gates.json")], capture_output=True).returncode == 0
        check("factory agent passes the eval gate", ok, "make eval NAME=payments-gw && make gate NAME=payments-gw")
    else:
        print("SKIP  eval gate (about 12 min): make eval NAME=payments-gw && make gate NAME=payments-gw")


def v_part2():
    gotest = shutil.which("go") is not None
    if gotest:
        r = subprocess.run(["go", "test", "./..."], cwd=ROOT / "go/alert-forwarder", capture_output=True, text=True)
        check("go test ./... (alert-forwarder)", r.returncode == 0, r.stdout[-300:])
        cmd, cwd = ["go", "run", ".", "-addr", ":8098"], ROOT / "go/alert-forwarder"
    else:
        binp = ROOT / "bin/alert-forwarder"
        check("alert-forwarder binary present (no Go installed)", binp.exists(), "make go-prebuilt")
        cmd, cwd = [str(binp), "-addr", ":8098"], ROOT
    arn = state()["runtime_arn"]
    # own process group: `go run` leaves the compiled child alive holding our pipes, so kill the whole group, not just the parent
    p = subprocess.Popen(cmd, cwd=cwd, env={**os.environ, "RUNTIME_ARN": arn}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        for _ in range(60):
            if subprocess.run(["curl", "-fsS", "localhost:8098/healthz"], capture_output=True).returncode == 0:
                break
            time.sleep(1)
        r = subprocess.run(["curl", "-sS", "-m", "600", "-X", "POST", "localhost:8098/alert", "-d", f"@{ROOT / 'data/alerts/inc-sip-timeout.json'}"], capture_output=True, text=True)
        check("forwarder accepted the alert", "diagnosis streamed" in r.stdout, r.stdout[:200])
    finally:
        import signal
        try:
            os.killpg(p.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            out, err = p.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            out, err = p.communicate(timeout=15)
    check("Go process printed a diagnosis containing the root-cause marker", bool(re.search(r"v2\.14\.3|a1f9c3e", out)), "check the forwarder's stderr (JSON logs)")


def v_part3():
    e = fenv()
    names = [t["name"] for t in mcpc.list_tools("oncall", e)]
    check("mandates___get_mandate_status is in tools/list", "mandates___get_mandate_status" in names, "add the custom tool to agent.yaml, make new-agent, make deploy-agent")
    check("decoy mandates___revoke_mandate is hidden by policy", "mandates___revoke_mandate" not in names)
    err, out, _ = mcpc.call_tool("mandates___get_mandate_status", {"user_id": "U-1042"}, "oncall", e)
    txt = json.dumps(out)
    check("direct MCP call returns a masked VPA and account", not err and "***@" in txt and "XXXX" in txt and "aarav42" not in txt and "246989508976" not in txt, txt[:160])
    err2, out2, _ = mcpc.call_tool("mandates___revoke_mandate", {"user_id": "U-1042"}, "oncall", e)
    check("decoy revoke is denied", err2 and "denied" in json.dumps(out2).lower())
    err3, _, _ = mcpc.call_tool("mandates___get_mandate_status", {"user_id": "U-1042"}, "support", e)
    check("support persona cannot read mandates", err3)
    logs = boto3.client("logs", region_name=REGION)
    ev, tok = [], None
    while not ev:                    # filter_log_events can return empty pages with a continuation token: follow it
        r = logs.filter_log_events(logGroupName="/dezerv/agent-audit", startTime=int((time.time() - 6 * 3600) * 1000),
                                   filterPattern='{ $.agent_id = "payments-gw-oncall" && $.tool = "mandates___get_mandate_status" && $.event = "before_tool_call" }',
                                   **({"nextToken": tok} if tok else {}))
        ev, tok = r["events"], r.get("nextToken")
        if not tok:
            break
    check("agent trace shows the Go tool being called (last 6 h)", len(ev) > 0, 'ask the agent: "Is user U-1042\'s SIP failing because of their mandate or because of the PSP?"')


def v_part4():
    import render
    manifest = yaml_load(AG / "agent.yaml")
    zones = manifest["policy"]["forbidden_zones"]
    check(f"manifest has a forbidden zone ({zones})", len(zones) > 0, "add `service:ledger-svc` to policy.forbidden_zones in labs/B/agent.yaml")
    text = (AG / "policy/60-zones.cedar").read_text() if (AG / "policy/60-zones.cedar").exists() else ""
    for z in zones:
        needle = z.split(":", 1)[1] if z.startswith("service:") else z.replace(".", "___")
        check(f"re-rendered Cedar contains a forbid for zone '{z}'", needle in text and "forbid(" in text, "make new-agent NAME=payments-gw FROM=labs/B/agent.yaml")
    sha_manifest = render.load_manifest(ROOT / "labs/B/agent.yaml")[2]
    check("rendered agent matches the current manifest", (AG / ".manifest.sha").read_text().strip() == sha_manifest, "re-render and redeploy")
    if any(z.startswith("service:") for z in zones):
        svc = next(z.split(":", 1)[1] for z in zones if z.startswith("service:"))
        err, out, _ = mcpc.call_tool("changes___get_recent_deploys", {"service": svc}, "oncall", fenv())
        check(f"live Gateway denies get_recent_deploys for {svc}", err and "denied" in json.dumps(out).lower(), "make deploy-agent NAME=payments-gw")


def yaml_load(p):
    import yaml
    return yaml.safe_load(Path(p).read_text())


{"verify-labB-part1": v_part1, "verify-labB-part2": v_part2, "verify-labB-part3": v_part3, "verify-labB-part4": v_part4}[sys.argv[1]]()
print("\nRESULT:", "PASS" if not fails else f"FAIL ({fails} check(s))")
sys.exit(1 if fails else 0)
