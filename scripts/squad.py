#!/usr/bin/env python3
"""Capstone helper.

  squad.py provision <squad>             upload the squad's synthetic data, create/backfill its log groups, add its injection ticket
  squad.py prove-denial <squad>          make the deployed agent try a forbidden zone so the audit log shows a `denied` decision
  squad.py verify <squad> C1|C2|C3       checkpoints (capstone spec section 6)
  squad.py export <squad>                zip the squad folder + DEMO.md + PATH-TO-PROD.md + README.md
  squad.py new-tool <squad> <tool> <arg> [--runtime python|go]   scaffold a custom tool and register it in the manifest
"""
import json, os, re, shutil, subprocess, sys, time, zipfile
from datetime import datetime, timezone
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "factory")); sys.path.insert(0, str(ROOT / "agent"))
import mcpc  # noqa: E402

ENV = dict(mcpc.load_env())
REGION = ENV.get("AWS_REGION", "us-west-2")


def squad_dir(s):
    d = ROOT / "squads" / s
    if not (d / "meta.json").exists():
        sys.exit(f"squads/{s} not found: make new-squad SQUAD={s} PROFILE=<profile>")
    return d


def meta(s):
    return json.loads((squad_dir(s) / "meta.json").read_text())


def agent_state(product):
    p = ROOT / "agents" / product / ".state.json"
    if not p.exists():
        sys.exit(f"agent {product} is not deployed: make new-agent NAME={product} FROM=squads/<squad>/agent.yaml && make deploy-agent NAME={product}")
    return json.loads(p.read_text())


# ------------------------------------------------------------------------------------------------ provision
def provision(squad):
    d, m = squad_dir(squad), meta(squad)
    s3, logs, ddb = (boto3.client(x, region_name=REGION) for x in ("s3", "logs", "dynamodb"))
    n = 0
    for f in sorted((d / "data").rglob("*")):
        rel = f.relative_to(d / "data")
        if f.is_file() and rel.parts[0] in ("mongo", "changes"):
            s3.upload_file(str(f), ENV["DATA_BUCKET"], f"squads/{squad}/data/{rel.as_posix()}"); n += 1
    print(f"uploaded {n} data files to s3://{ENV['DATA_BUCKET']}/squads/{squad}/data/")
    now = datetime.now(timezone.utc)
    for svc in [m["service"]] + m["other_services"]:
        group = f"/dezerv/{svc}"
        exists = bool(logs.describe_log_groups(logGroupNamePrefix=group)["logGroups"] and
                      any(g["logGroupName"] == group for g in logs.describe_log_groups(logGroupNamePrefix=group)["logGroups"]))
        if exists and svc in ("payments-gw", "kyc-svc") and svc != m["service"]:
            print(f"{group}: belongs to Lab A, not touching it"); continue
        if not exists:
            logs.create_log_group(logGroupName=group); logs.put_retention_policy(logGroupName=group, retentionInDays=14)
        lf = d / f"data/cloudwatch/{svc}.log"
        if not lf.exists():
            continue
        events = []
        for line in lf.read_text().splitlines():
            ts = datetime.fromisoformat(json.loads(line)["ts"])
            if ts <= now:
                events.append({"timestamp": int(ts.timestamp() * 1000), "message": line})
        events.sort(key=lambda e: e["timestamp"])
        stream = f"backfill-{squad}-{events[0]['timestamp'] // 1000 // 86400}"
        try:
            logs.create_log_stream(logGroupName=group, logStreamName=stream)
        except logs.exceptions.ResourceAlreadyExistsException:
            print(f"{group}: {stream} already backfilled"); continue
        i = 0
        while i < len(events):
            batch = [events[i]]; j = i + 1
            while j < len(events) and len(batch) < 5000 and events[j]["timestamp"] - events[i]["timestamp"] < 23 * 3600 * 1000:
                batch.append(events[j]); j += 1
            r = logs.put_log_events(logGroupName=group, logStreamName=stream, logEvents=batch)
            if r.get("rejectedLogEventsInfo"):
                print("WARNING rejected:", r["rejectedLogEventsInfo"])
            i = j
        print(f"{group}: backfilled {len(events)} events")
    t = boto3.resource("dynamodb", region_name=REGION).Table("dezerv-tickets")
    for tk in json.loads((d / "data/tickets.json").read_text()):
        t.put_item(Item=tk)
        print(f"ticket {tk['key']} (with the planted injection) added")


# ------------------------------------------------------------------------------------------------ prove-denial
def prove_denial(squad):
    m = meta(squad)
    product = m["service"]
    st = agent_state(product)
    import main as agent_main
    env = agent_main.get_env(); env["GATEWAY_URL"] = st["gateway_url"]; env["PRODUCT"] = product
    os.environ["PRODUCT"] = product
    sink = []
    agent, client, sid = agent_main.build_agent("oncall", env=env, audit_sink=sink)
    # The Agent starts and owns its MCP client, so do not enter it again with `with client:`.
    try:
        agent.tool.changes___get_recent_deploys(service="ledger-svc")      # a forbidden zone: the tool is visible, the argument is not allowed
    except Exception as e:
        print("tool call raised:", str(e)[:120])
    time.sleep(2)
    dec = [(r["tool"], r["decision"]) for r in sink if r["event"] == "after_tool_call"]
    print("audit records:", json.dumps(dec, indent=1))
    ok = any(d["result"] == "denied" for _, d in dec)
    print("DENIED recorded in /dezerv/agent-audit" if ok else "no denial recorded: is `service:ledger-svc` in forbidden_zones and the agent deployed with it?")
    sys.exit(0 if ok else 1)


# ------------------------------------------------------------------------------------------------ verify
fails = 0


def check(label, ok, hint=""):
    global fails
    fails += (not ok)
    print(("PASS  " if ok else "FAIL  ") + label + ("" if ok or not hint else f"\n      hint: {hint}"))


def verify(squad, cp):
    import render
    d, m = squad_dir(squad), meta(squad)
    product = m["service"]
    if cp == "C1":
        try:
            _, man, sha, _, _ = render.validate(d / "agent.yaml"); ok, msg = True, ""
        except render.ManifestError as e:
            ok, msg = False, str(e)
        check("agent.yaml validates (and charter.md has every required section)", ok, msg)
        check("mock data generated", (d / f"data/mongo/{m['collection']}.json").exists() and (d / f"data/cloudwatch/{m['service']}.log").exists(), "make new-squad")
        check("incident alert exists", (d / "alerts/incident.json").exists())
    elif cp == "C2":
        st = agent_state(product)
        ctl = boto3.client("bedrock-agentcore-control", region_name=REGION)
        check("agent deployed and READY", ctl.get_agent_runtime(agentRuntimeId=st["runtime_id"])["status"] == "READY", "make deploy-agent NAME=" + product)
        e = dict(ENV); e["GATEWAY_URL"] = st["gateway_url"]
        names = [t["name"] for t in mcpc.list_tools("oncall", e)]
        check(f"custom tool {m['target']}___{m['tool']} is listed", f"{m['target']}___{m['tool']}" in names, "the custom connector must be in agent.yaml")
        os.environ["RUNTIME_ARN"] = st["runtime_arn"]
        sys.path.insert(0, str(ROOT / "evals"))
        from runtime_client import invoke
        alert = json.loads((d / "alerts/incident.json").read_text())
        out = invoke("Investigate this alert and follow your workflow:\n" + json.dumps(alert, indent=1), "oncall", task_id=f"{squad}-c2")
        check(f"incident run mentions the expected root-cause marker /{m['marker']}/", bool(re.search(m["marker"], out.get("answer", ""))), "read the answer; check the logs and deploy data were provisioned (make provision-squad)")
    elif cp == "C3":
        n = len(list((d / "replay").glob("*.json")))
        check(f">= 3 replay cases (found {n}), including an injection case", n >= 3 and any(json.loads(f.read_text())["category"] == "injection" for f in (d / "replay").glob("*.json")))
        rep, gates = ROOT / "agents" / product / "report.json", ROOT / "agents" / product / "evals/gates.json"
        ok = rep.exists() and subprocess.run([sys.executable, str(ROOT / "evals/gate.py"), str(rep), str(gates)], capture_output=True).returncode == 0
        check("make gate passes", ok, f"make eval NAME={product} && make gate NAME={product}")
        logs = boto3.client("logs", region_name=REGION)
        found, tok = False, None
        while not found:
            r = logs.filter_log_events(logGroupName="/dezerv/agent-audit", startTime=int((time.time() - 12 * 3600) * 1000),
                                       filterPattern='{ $.agent_id = "%s-oncall" && $.event = "after_tool_call" && $.decision.result = "denied" }' % product,
                                       **({"nextToken": tok} if tok else {}))
            found, tok = bool(r["events"]), r.get("nextToken")
            if not tok:
                break
        check("a denied decision exists in the audit log", found, f"make prove-denial SQUAD={squad}")
        check("export zip created", (ROOT / "exports" / f"{squad}-agent-skeleton.zip").exists(), f"make export SQUAD={squad}")
    print("\nRESULT:", "PASS" if not fails else f"FAIL ({fails} check(s))")
    sys.exit(1 if fails else 0)


# ------------------------------------------------------------------------------------------------ export
def export(squad):
    import yaml
    d, m = squad_dir(squad), meta(squad)
    product = m["service"]
    ag = ROOT / "agents" / product
    rep = ag / "report.json"
    gate = "not run yet"
    if rep.exists():
        r = json.loads(rep.read_text()); rca = [x["rca"] for x in r if x.get("rca") is not None]
        gate = f"{len(r)} cases, RCA mean {sum(rca) / len(rca):.2f}" if rca else f"{len(r)} cases"
    sub = dict(SQUAD=squad, SERVICE=m["service"], MARKER=m["marker"].replace("\\", ""), TICKET=m["ticket"], TOOL=m["tool"], TARGET=m["target"],
               COLLECTION=m["collection"], GATE=gate, PRODUCT=product)
    def fill(t):
        for k, v in sub.items():
            t = t.replace(f"__{k}__", str(v))
        return t
    out_dir = ROOT / "exports"; out_dir.mkdir(exist_ok=True)
    z = out_dir / f"{squad}-agent-skeleton.zip"
    base = f"{squad}-agent-skeleton"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(d.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                zf.write(f, f"{base}/{f.relative_to(d).as_posix()}")
        if (ag / "policy").exists():
            for f in sorted((ag / "policy").glob("*.cedar")):
                zf.write(f, f"{base}/policy/{f.name}")
        if rep.exists():
            zf.write(rep, f"{base}/evals/report.json")
        for tmpl, name in (("DEMO.md", "DEMO.md"), ("PATH-TO-PROD.md", "PATH-TO-PROD.md"), ("README.md", "README.md")):
            zf.writestr(f"{base}/{name}", fill((ROOT / "capstone/templates" / tmpl).read_text()))
    print(f"wrote {z.relative_to(ROOT)} ({z.stat().st_size // 1024} KB). Download it before the account expires (72 h).")


# ------------------------------------------------------------------------------------------------ new-tool
def new_tool(squad, tool, arg, runtime="python"):
    import yaml
    d, m = squad_dir(squad), meta(squad)
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,40}", tool):
        sys.exit("tool name: lowercase letters, digits, underscores")
    tdir = d / "tools" / tool
    if tdir.exists():
        sys.exit(f"{tdir} already exists")
    target = re.sub(r"[^a-z0-9]", "", tool.split("_")[-1] or tool)[:18] or "custom2"
    if runtime == "python":
        tdir.mkdir(parents=True)
        t = (ROOT / "tools/templates/python-tool/handler.py").read_text()
        (tdir / "handler.py").write_text(t.replace("__TOOL__", tool).replace("__ARG__", arg).replace("__ID_FIELD__", arg).replace("__PII__", "[]"))
    else:
        shutil.copytree(ROOT / "tools/mandates-go", tdir, ignore=shutil.ignore_patterns("*_test.go", "go.sum"))
    json.dump({"target": target, "description": f"{m['service']}: {tool}", "scope": "payments/custom.read",
               "tools": [{"name": tool, "description": f"TODO describe {tool}", "inputSchema": {"type": "object", "properties": {arg: {"type": "string", "description": arg}}, "required": [arg]}}]},
              open(tdir / "tools.json", "w"), indent=2)
    mf = d / "agent.yaml"
    man = yaml.safe_load(mf.read_text())
    man["connectors"].setdefault("custom", []).append({"name": target, "type": "lambda", "runtime": runtime, "path": f"squads/{squad}/tools/{tool}"})
    mf.write_text("# (re-written by new-tool)\n" + yaml.safe_dump(man, sort_keys=False, width=150))
    print(f"scaffolded {tdir.relative_to(ROOT)} (target '{target}') and registered it in squads/{squad}/agent.yaml. Edit the handler, then make new-agent && make deploy-agent.")


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 2:
        sys.exit(__doc__)
    {"provision": lambda: provision(a[1]), "prove-denial": lambda: prove_denial(a[1]), "export": lambda: export(a[1]),
     "verify": lambda: verify(a[1], a[2]), "new-tool": lambda: new_tool(a[1], a[2], a[3], a[a.index("--runtime") + 1] if "--runtime" in a else "python")}[a[0]]()
