#!/usr/bin/env python3
"""Deploy a rendered agent (agents/<product>/) into the account: custom Lambdas, Gateway + targets, policy engine + Cedar,
interceptor, memory (+seed), and the Runtime. Idempotent. Resources are prefixed fx- / fx_ so they sit beside Lab A's.

  deploy.py <product> [--destroy]
"""
import json, os, re, shutil, subprocess, sys, time, zipfile
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from labA import ctl, paged, find, wait  # noqa: E402  (shares the control-plane client and helpers)
from mcpc import load_env  # noqa: E402

ENV = load_env()
REGION, ACCT = ENV["AWS_REGION"], ENV["AWS_ACCOUNT_ID"]
lam = boto3.client("lambda", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)
dp = boto3.client("bedrock-agentcore", region_name=REGION)


def log(m):
    print(f"[factory] {m}", flush=True)


class Agent:
    def __init__(self, product):
        self.p = product
        self.dir = ROOT / "agents" / product
        if not (self.dir / ".manifest.sha").exists():
            sys.exit(f"{self.dir} has not been rendered: run `make new-agent NAME={product} FROM=labs/B/agent.yaml`")
        self.u = product.replace("-", "_")
        self.gw_name, self.pe_name, self.mem_name, self.rt_name = f"fx-{product}", f"fx_{self.u}_pe", f"fx_{self.u}", f"fx_{self.u}"
        self.state_file = self.dir / ".state.json"
        self.state = json.loads(self.state_file.read_text()) if self.state_file.exists() else {}
        self.targets = json.loads((self.dir / "gateway/targets.json").read_text())["targets"]
        import yaml
        self.manifest = yaml.safe_load((self.dir / "agent.yaml").read_text())
        self.mem = json.loads((self.dir / "memory/memory.json").read_text())
        self.gates = json.loads((self.dir / "evals/gates.json").read_text())

    def save(self, **kw):
        self.state.update(kw)
        self.state_file.write_text(json.dumps(self.state, indent=1))


# ------------------------------------------------------------------------------------------------ custom lambdas
def build_go(path, out_zip):
    src = ROOT / path
    tmp = ROOT / "build" / f"go-{src.name}"
    shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir(parents=True)
    env = {**os.environ, "GOOS": "linux", "GOARCH": "arm64", "CGO_ENABLED": "0"}
    subprocess.run(["go", "build", "-trimpath", "-tags", "lambda.norpc", "-o", str(tmp / "bootstrap"), "."], cwd=src, env=env, check=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        zi = zipfile.ZipInfo("bootstrap"); zi.external_attr = 0o755 << 16
        z.writestr(zi, (tmp / "bootstrap").read_bytes(), zipfile.ZIP_DEFLATED)


def build_python(path, out_zip):
    src = ROOT / path
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for f in list(src.glob("*.py")) + [ROOT / "lambdas/_common.py"]:
            z.write(f, f.name)


def ensure_custom_lambda(a, t):
    b = t["build"]
    fn = f"dezerv-laba-fx-{a.p}-{t['name']}"[:64]          # matches the gateway role's dezerv-laba-* invoke grant
    z = ROOT / "build" / f"{fn}.zip"
    z.parent.mkdir(exist_ok=True)
    go = b["runtime"] == "go"
    pre = ROOT / "prebuilt" / f"{Path(b['path']).name}-arm64.zip"
    if go and shutil.which("go") is None:                      # spike V-11 fallback: no toolchain, use the prebuilt zip
        if not pre.exists():
            sys.exit("Go is not installed and there is no prebuilt zip: run `make go-setup`")
        log(f"Go not found: using {pre.relative_to(ROOT)}")
        shutil.copy(pre, z)
    else:
        (build_go if go else build_python)(b["path"], z)
    cfg = dict(Runtime="provided.al2023" if go else "python3.12", Handler="bootstrap" if go else "handler.lambda_handler",
               Architectures=["arm64" if go else "x86_64"], Role=ENV["TOOL_ROLE_ARN"], Timeout=30, MemorySize=256,
               Environment={"Variables": {"DATA_BUCKET": ENV["DATA_BUCKET"],
                                          **({"DATA_PREFIX": a.manifest["data"]["prefix"], "PRIMARY_COLLECTION": a.manifest["data"]["primary_collection"]} if a.manifest.get("data") else {})}})
    try:
        lam.get_function(FunctionName=fn)
        lam.update_function_code(FunctionName=fn, ZipFile=z.read_bytes())
        lam.get_waiter("function_updated").wait(FunctionName=fn)
        lam.update_function_configuration(FunctionName=fn, **{k: v for k, v in cfg.items() if k not in ("Architectures",)})
        log(f"updated Lambda {fn}")
    except lam.exceptions.ResourceNotFoundException:
        lam.create_function(FunctionName=fn, Code={"ZipFile": z.read_bytes()}, **cfg)
        log(f"created Lambda {fn}")
    lam.get_waiter("function_active_v2").wait(FunctionName=fn)
    lam.get_waiter("function_updated_v2").wait(FunctionName=fn)
    return lam.get_function(FunctionName=fn)["Configuration"]["FunctionArn"]


def squad_lambdas(a):
    """Capstone: when the manifest has a `data` block, run private copies of the generic tool Lambdas (same code as Lab A's)
    with environment overrides that point them at the squad's data. Returns {target: arn} to override the Lab A Lambdas."""
    import urllib.request
    d = a.manifest.get("data")
    if not d:
        return {}
    over = {"db": {"DATA_PREFIX": d["prefix"], "COLLECTIONS": ",".join(d["collections"]), "PRIMARY_COLLECTION": d["primary_collection"]},
            "logs": {"LOG_SERVICES": ",".join(d["log_services"])},
            "changes": {"DEPLOYS_KEY": d["deploys_key"]}}
    out = {}
    for target, extra in over.items():
        if target not in {t["name"] for t in a.targets}:
            continue
        src = lam.get_function(FunctionName=f"dezerv-laba-{target}")
        cfg = src["Configuration"]
        fn = f"dezerv-laba-fx-{a.p}-{target}"[:64]
        env = {**cfg.get("Environment", {}).get("Variables", {}), **extra}
        code = urllib.request.urlopen(src["Code"]["Location"]).read()
        try:
            lam.get_function(FunctionName=fn)
            lam.update_function_code(FunctionName=fn, ZipFile=code)
            lam.get_waiter("function_updated").wait(FunctionName=fn)
            lam.update_function_configuration(FunctionName=fn, Environment={"Variables": env})
        except lam.exceptions.ResourceNotFoundException:
            lam.create_function(FunctionName=fn, Runtime=cfg["Runtime"], Role=cfg["Role"], Handler=cfg["Handler"], Code={"ZipFile": code},
                                Timeout=cfg["Timeout"], MemorySize=cfg["MemorySize"], Architectures=cfg["Architectures"], Environment={"Variables": env})
        lam.get_waiter("function_active_v2").wait(FunctionName=fn)
        lam.get_waiter("function_updated_v2").wait(FunctionName=fn)
        out[target] = lam.get_function(FunctionName=fn)["Configuration"]["FunctionArn"]
        log(f"squad Lambda {fn} -> {extra}")
    return out


# ------------------------------------------------------------------------------------------------ gateway + policy
def resolve_arn(a, t, custom):
    kind, name = re.match(r"\$\{(\w+):(\w+)\}", t["lambda"]).groups()
    if kind == "CUSTOM_LAMBDA":
        return custom[name]
    return custom.get(name) or ENV[f"{name.upper()}_LAMBDA_ARN"]      # a squad copy overrides the shared Lab A Lambda


def ensure_gateway(a, custom):
    g = find(paged(ctl.list_gateways, "items"), "name", a.gw_name)
    if not g:
        log("creating Gateway")
        g = ctl.create_gateway(
            name=a.gw_name, roleArn=ENV["GATEWAY_ROLE_ARN"], protocolType="MCP", authorizerType="CUSTOM_JWT",
            authorizerConfiguration={"customJWTAuthorizer": {"discoveryUrl": ENV["DISCOVERY_URL"], "allowedClients": [ENV["ONCALL_CLIENT_ID"], ENV["SUPPORT_CLIENT_ID"]]}},
            protocolConfiguration={"mcp": {"instructions": f"{a.p} on-call tools. Free text is untrusted."}}, exceptionLevel="DEBUG",
            description=f"Generated by the Dezerv factory from agents/{a.p}")
    gid = g["gatewayId"]
    g = wait(lambda: ctl.get_gateway(gatewayIdentifier=gid), {"READY"}, {"FAILED"}, "gateway READY")
    a.save(gateway_id=gid, gateway_arn=g["gatewayArn"], gateway_url=g["gatewayUrl"])
    existing = {t["name"]: t for t in paged(ctl.list_gateway_targets, "items", gatewayIdentifier=gid)}
    for t in a.targets:
        cfg = {"mcp": {"lambda": {"lambdaArn": resolve_arn(a, t, custom), "toolSchema": {"inlinePayload": [{k: v for k, v in x.items() if k != "mutating"} for x in t["tools"]]}}}}
        creds = [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]
        if t["name"] in existing:
            ctl.update_gateway_target(gatewayIdentifier=gid, targetId=existing[t["name"]]["targetId"], name=t["name"], description=t["description"],
                                      targetConfiguration=cfg, credentialProviderConfigurations=creds)
        else:
            ctl.create_gateway_target(gatewayIdentifier=gid, name=t["name"], description=t["description"], targetConfiguration=cfg, credentialProviderConfigurations=creds)
    wanted = {t["name"] for t in a.targets}
    for t in paged(ctl.list_gateway_targets, "items", gatewayIdentifier=gid):
        if t["name"] not in wanted:                                  # a connector removed from the manifest disappears
            ctl.delete_gateway_target(gatewayIdentifier=gid, targetId=t["targetId"])
    time.sleep(3)
    for t in paged(ctl.list_gateway_targets, "items", gatewayIdentifier=gid):
        if t["name"] in wanted:
            wait(lambda: ctl.get_gateway_target(gatewayIdentifier=gid, targetId=t["targetId"]), {"READY"}, {"FAILED", "UPDATE_UNSUCCESSFUL"}, f"target {t['name']}")
    log(f"gateway ready with targets {sorted(wanted)}")


def gw_update(a, **changes):
    cur = ctl.get_gateway(gatewayIdentifier=a.state["gateway_id"])
    keep = ["name", "description", "roleArn", "protocolType", "protocolConfiguration", "authorizerType", "authorizerConfiguration", "kmsKeyArn",
            "interceptorConfigurations", "policyEngineConfiguration", "exceptionLevel"]
    params = {k: cur[k] for k in keep if k in cur}
    params.update(changes)
    for k in [k for k, v in changes.items() if v is None]:
        params.pop(k, None)
    ctl.update_gateway(gatewayIdentifier=a.state["gateway_id"], **params)
    wait(lambda: ctl.get_gateway(gatewayIdentifier=a.state["gateway_id"]), {"READY"}, {"FAILED", "UPDATE_UNSUCCESSFUL"}, "gateway update")


def cedar_statements(a):
    arn = a.state["gateway_arn"]
    out = []
    for f in sorted((a.dir / "policy").glob("*.cedar")):
        text = "\n".join(l for l in f.read_text().splitlines() if not l.lstrip().startswith("//")).replace("{{GATEWAY_ARN}}", arn)
        parts = [p.strip() for p in re.split(r";\s*\n\s*\n", text) if "permit(" in p or "forbid(" in p]
        for i, p in enumerate(parts):
            # Policy names are unique across the whole account (not per engine), so namespace them by product.
            out.append((re.sub(r"[^A-Za-z0-9_]", "_", f"{a.u[:14]}_{f.stem.split('-')[0]}_{f.stem.split('-', 1)[1]}_{i + 1}")[:48], p if p.endswith(";") else p + ";"))
    return out


def ensure_policy(a):
    pe = find(paged(ctl.list_policy_engines, "policyEngines"), "name", a.pe_name) or ctl.create_policy_engine(name=a.pe_name, description=f"Generated from agents/{a.p}")
    peid = pe["policyEngineId"]
    pe = wait(lambda: ctl.get_policy_engine(policyEngineId=peid), {"ACTIVE"}, {"CREATE_FAILED"}, "policy engine")
    a.save(policy_engine_id=peid, policy_engine_arn=pe["policyEngineArn"])
    attached = bool(ctl.get_gateway(gatewayIdentifier=a.state["gateway_id"]).get("policyEngineConfiguration"))
    if attached:                          # same analyzer quirk as Lab A (see FINDINGS.md): apply with the engine detached
        log("detaching engine while policies are applied (brief window without enforcement)")
        gw_update(a, policyEngineConfiguration=None)
    try:
        existing = {p["name"]: p for p in paged(ctl.list_policies, "policies", policyEngineId=peid)}
        stmts = cedar_statements(a)
        keep = {n for n, _ in stmts}
        for n, p in existing.items():
            if n not in keep:
                ctl.delete_policy(policyEngineId=peid, policyId=p["policyId"])
        existing = {n: p for n, p in existing.items() if n in keep}
        for n, stmt in stmts:
            defn = {"cedar": {"statement": stmt}}
            if n in existing:
                ctl.update_policy(policyEngineId=peid, policyId=existing[n]["policyId"], definition=defn, validationMode="FAIL_ON_ANY_FINDINGS")
            else:
                for _ in range(12):
                    try:
                        ctl.create_policy(policyEngineId=peid, name=n, definition=defn, validationMode="FAIL_ON_ANY_FINDINGS"); break
                    except ctl.exceptions.ConflictException:     # a policy deleted a moment ago can still hold its name
                        time.sleep(5)
                else:
                    raise SystemExit(f"policy name '{n}' is still in use after 60 s (policy names are unique across the account)")
        for p in paged(ctl.list_policies, "policies", policyEngineId=peid):
            wait(lambda: ctl.get_policy(policyEngineId=peid, policyId=p["policyId"]), {"ACTIVE"}, {"CREATE_FAILED", "UPDATE_FAILED"}, f"policy {p['name']}")
        log(f"{len(stmts)} Cedar policies ACTIVE")
    finally:                              # never leave the Gateway without its engine, even when an apply fails
        gw_update(a, policyEngineConfiguration={"arn": pe["policyEngineArn"], "mode": "ENFORCE"},
                  interceptorConfigurations=[{"interceptor": {"lambda": {"arn": ENV["INTERCEPTOR_LAMBDA_ARN"]}}, "interceptionPoints": ["REQUEST", "RESPONSE"],
                                              "inputConfiguration": {"passRequestHeaders": True}}])
    log("policy engine attached (ENFORCE) and interceptor attached")


# ------------------------------------------------------------------------------------------------ memory
def ensure_memory(a):
    existing = [m for m in paged(ctl.list_memories, "memories") if m.get("id", "").startswith(a.mem_name + "-")]
    if existing:
        mid = existing[0]["id"]
    else:
        mid = ctl.create_memory(name=a.mem_name, description=f"{a.p}: past incidents and runbooks", eventExpiryDuration=30,
                                memoryStrategies=[{"semanticMemoryStrategy": {"name": "facts", "namespaces": [f"/products/{a.p}"]}},
                                                  {"episodicMemoryStrategy": {"name": "episodes", "namespaces": [f"/products/{a.p}/episodes/{{sessionId}}"],
                                                                              "reflectionConfiguration": {"namespaces": [f"/products/{a.p}/episodes"]}}}])["memory"]["id"]
    m = wait(lambda: ctl.get_memory(memoryId=mid)["memory"], {"ACTIVE"}, {"FAILED"}, "memory", every=10)
    sid = next(s["strategyId"] for s in m.get("strategies", m.get("memoryStrategies", [])) if s["name"] == "facts")
    a.save(memory_id=mid, memory_strategy_id=sid)
    for key in ("incidents", "runbooks"):
        ns = a.mem["namespaces"][key]
        files = sorted((ROOT / a.mem["seed"][key]).glob("*.md"))
        if len(dp.list_memory_records(memoryId=mid, namespace=ns, maxResults=100).get("memoryRecordSummaries", [])) >= len(files):
            continue
        from datetime import datetime, timezone
        import uuid
        recs = [{"requestIdentifier": f.stem, "namespaces": [ns], "memoryStrategyId": sid, "content": {"text": f.read_text()}, "timestamp": datetime.now(timezone.utc)} for f in files]
        for i in range(0, len(recs), 10):
            dp.batch_create_memory_records(memoryId=mid, records=recs[i:i + 10], clientToken=str(uuid.uuid4()))
        log(f"seeded {len(recs)} {key}")


# ------------------------------------------------------------------------------------------------ runtime
def ensure_runtime(a):
    bucket = f"dezerv-laba-artifacts-{ACCT}-{REGION}"
    out = ROOT / "build" / f"agent-{a.p}"
    shutil.rmtree(out, ignore_errors=True); out.mkdir(parents=True)
    subprocess.run(["uv", "pip", "install", "--quiet", "--target", str(out), "--python-version", "3.12", "--python-platform", "aarch64-manylinux_2_28",
                    "strands-agents", "mcp", "bedrock-agentcore", "boto3", "opentelemetry-api"], check=True)
    for f in (ROOT / "agent").glob("*.py"):
        shutil.copy(f, out)
    shutil.copytree(a.dir / "prompt", out / "prompt")                # the RENDERED prompt, not Lab A's
    shutil.copy(ROOT / "scripts/mcpc.py", out)
    shutil.copy(ROOT / "lambdas/interceptor/pii.py", out)
    z = ROOT / "build" / f"agent-{a.p}.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(out.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                zf.write(p, p.relative_to(out))
    key = f"runtime/{a.p}-{int(time.time())}.zip"
    s3.upload_file(str(z), bucket, key)
    cfg = {k: ENV[k] for k in ["TOKEN_URL", "ONCALL_CLIENT_ID", "ONCALL_CLIENT_SECRET", "SUPPORT_CLIENT_ID", "SUPPORT_CLIENT_SECRET"]}
    cfg.update(GATEWAY_URL=a.state["gateway_url"], MEMORY_ID=a.state["memory_id"], AWS_REGION=REGION, PRODUCT=a.p,
               MAX_TOOL_CALLS=str(a.gates["budgets"]["max_tool_calls"]), MAX_TOKENS_BUDGET=str(a.gates["budgets"]["max_tokens"]))
    art = {"codeConfiguration": {"code": {"s3": {"bucket": bucket, "prefix": key}}, "runtime": "PYTHON_3_12", "entryPoint": ["runtime.py"]}}
    kw = dict(agentRuntimeArtifact=art, roleArn=ENV["RUNTIME_ROLE_ARN"], networkConfiguration={"networkMode": "PUBLIC"},
              environmentVariables=cfg, protocolConfiguration={"serverProtocol": "HTTP"})
    ex = find(paged(ctl.list_agent_runtimes, "agentRuntimes"), "agentRuntimeName", a.rt_name)
    if ex:
        rid = ex["agentRuntimeId"]; ctl.update_agent_runtime(agentRuntimeId=rid, **kw)
    else:
        rid = ctl.create_agent_runtime(agentRuntimeName=a.rt_name, description=f"Generated from agents/{a.p}", **kw)["agentRuntimeId"]
    time.sleep(5)
    rt = wait(lambda: ctl.get_agent_runtime(agentRuntimeId=rid), {"READY"}, {"CREATE_FAILED", "UPDATE_FAILED"}, "runtime READY", every=10)
    a.save(runtime_id=rid, runtime_arn=rt["agentRuntimeArn"])
    log(f"runtime READY: {rt['agentRuntimeArn']}")


def deploy(product):
    a = Agent(product)
    custom = {t["name"]: ensure_custom_lambda(a, t) for t in a.targets if "build" in t}
    custom.update(squad_lambdas(a))
    ensure_gateway(a, custom)
    ensure_policy(a)
    ensure_memory(a)
    ensure_runtime(a)
    log("done. state in " + str(a.state_file.relative_to(ROOT)))


def destroy(product):
    a = Agent(product)
    st = a.state
    if st.get("runtime_id"):
        ctl.delete_agent_runtime(agentRuntimeId=st["runtime_id"]); log("runtime deleting")
    if st.get("gateway_id"):
        gid = st["gateway_id"]
        gw_update(a, policyEngineConfiguration=None, interceptorConfigurations=None)
        for t in paged(ctl.list_gateway_targets, "items", gatewayIdentifier=gid):
            ctl.delete_gateway_target(gatewayIdentifier=gid, targetId=t["targetId"])
        while paged(ctl.list_gateway_targets, "items", gatewayIdentifier=gid):
            time.sleep(3)
        ctl.delete_gateway(gatewayIdentifier=gid); log("gateway deleted")
    if st.get("policy_engine_id"):
        for p in paged(ctl.list_policies, "policies", policyEngineId=st["policy_engine_id"]):
            ctl.delete_policy(policyEngineId=st["policy_engine_id"], policyId=p["policyId"])
        while paged(ctl.list_policies, "policies", policyEngineId=st["policy_engine_id"]):
            time.sleep(3)
        ctl.delete_policy_engine(policyEngineId=st["policy_engine_id"]); log("policy engine deleted")
    if st.get("memory_id"):
        ctl.delete_memory(memoryId=st["memory_id"]); log("memory deleting")
    for t in a.targets:
        if "build" in t or (a.manifest.get("data") and t["name"] in ("db", "logs", "changes")):
            try:
                lam.delete_function(FunctionName=f"dezerv-laba-fx-{a.p}-{t['name']}"[:64]); log(f"lambda {t['name']} deleted")
            except Exception as e:
                log(f"lambda delete skipped: {e}")
    a.state_file.unlink(missing_ok=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    (destroy if "--destroy" in sys.argv else deploy)(sys.argv[1])
