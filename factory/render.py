#!/usr/bin/env python3
"""Dezerv agent factory: validate agent.yaml and render agents/<product>/ (prompt, gateway targets, Cedar, memory, evals).

  render.py validate  --from labs/B/agent.yaml
  render.py new-agent --from labs/B/agent.yaml [--out agents]

Deterministic and idempotent: same manifest in, same files out. Generated files carry a header with the manifest sha.
Fails closed: unknown connector, wildcard forbidden zone, autonomy above L1, forbid_ops=false, fewer than 3 replay cases,
missing charter section, unknown zone target.
"""
import argparse, hashlib, json, re, shutil, sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from schemas import TARGETS  # noqa: E402

CHARTER_SECTIONS = ["Purpose", "SLOs", "Invariants", "Forbidden zones", "Escalation"]
READ_TOOLS = {"logs": ["query_logs", "get_log_patterns"], "db": ["find_transactions", "get_user_state", "get_error_code"],
              "warehouse": ["query_history"], "changes": ["get_recent_deploys"], "tickets": ["search_tickets", "get_ticket"]}
WRITE_TOOLS = {"tickets": ["create_ticket", "add_comment"]}
OPS_TOOLS = ["restart_service", "scale_service", "rollback_deploy"]
SERVICE_TARGETS = {"logs": ["query_logs", "get_log_patterns"], "changes": ["get_recent_deploys"]}   # tools with a `service` input
KNOWN_SERVICES = {"logs": ["payments-gw", "kyc-svc"], "changes": ["payments-gw", "kyc-svc", "ledger-svc", "notifications-svc"]}
SCOPE = {"logs": "logs.read", "db": "db.read", "warehouse": "warehouse.read", "changes": "changes.read", "tickets": "tickets.read"}


class ManifestError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("\n".join(f"  - {e}" for e in errors))


def load_manifest(path):
    path = Path(path).resolve()
    text = path.read_text()
    return path, yaml.safe_load(text), hashlib.sha256(text.encode()).hexdigest()[:10]


def parse_charter(text):
    sections, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^#{2,3}\s+(.*?)\s*$", line)
        if m:
            cur = m.group(1)
            sections[cur] = []
        elif cur:
            sections[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


def validate(path):
    path, m, sha = load_manifest(path)
    schema = json.loads((ROOT / "factory/schema/agent.schema.json").read_text())
    errs = []
    for e in sorted(Draft202012Validator(schema).iter_errors(m), key=lambda e: list(e.path)):
        where = ".".join(str(p) for p in e.path) or "(root)"
        hint = ""
        if where == "autonomy":
            hint = " (workshop ceiling is L1)"
        if where.startswith("connectors") and e.validator == "additionalProperties":
            hint = " (unknown connector: allowed are logs, db, warehouse, changes, tickets, custom)"
        if where.startswith("policy.forbidden_zones"):
            hint = " (zones are `service:<name>` or `<target>.<tool>`; wildcards are refused)"
        errs.append(f"{where}: {e.message}{hint}")
    if errs:
        raise ManifestError(errs)
    charter_path = (path.parent / m["charter"]).resolve()
    if not charter_path.exists():
        errs.append(f"charter: file not found: {m['charter']}")
        charter = {}
    else:
        charter = parse_charter(charter_path.read_text())
        errs += [f"charter.md is missing the required section '{s}'" for s in CHARTER_SECTIONS if not charter.get(s)]
    custom = m["connectors"].get("custom") or []
    names = [c["name"] for c in custom]
    if len(set(names)) != len(names) or set(names) & set(READ_TOOLS) | ({"ops"} & set(names)):
        errs.append("connectors.custom: names must be unique and must not reuse a built-in target name")
    custom_tools = {}
    for c in custom:
        tj = ROOT / c["path"] / "tools.json"
        if not tj.exists():
            errs.append(f"connectors.custom[{c['name']}]: {c['path']}/tools.json not found")
        else:
            custom_tools[c["name"]] = json.loads(tj.read_text())
    targets = {k for k in m["connectors"] if k != "custom"} | set(names)
    for z in m["policy"]["forbidden_zones"]:
        if z.startswith("service:"):
            continue
        target, tool = z.split(".", 1)
        known = {t: [x["name"] for x in TARGETS[t][1]] for t in TARGETS if t in targets}
        known.update({n: [x["name"] for x in v["tools"]] for n, v in custom_tools.items()})
        if target not in known:
            errs.append(f"policy.forbidden_zones: '{z}' names target '{target}' which is not a declared connector")
        elif tool not in known[target]:
            errs.append(f"policy.forbidden_zones: '{z}': target '{target}' has no tool '{tool}' (has: {', '.join(known[target])})")
    replay = ROOT / m["evals"]["replay"]
    n_replay = len(list(replay.glob("*.json"))) if replay.exists() else 0
    if n_replay < 3:
        errs.append(f"evals.replay: {m['evals']['replay']} has {n_replay} replay cases; at least 3 are required")
    for k in ("incidents", "runbooks"):
        if not (ROOT / m["memory"][k]).exists():
            errs.append(f"memory.{k}: directory {m['memory'][k]} not found (run make bootstrap first)")
    if errs:
        raise ManifestError(errs)
    return path, m, sha, charter, custom_tools


# ------------------------------------------------------------------------------------------------ rendering
def normalise(stmt):
    stmt = "\n".join(l for l in stmt.splitlines() if not l.lstrip().startswith("//"))
    return re.sub(r"\s+", " ", stmt).strip()


def cedar_actions(target, tools):
    return cedar_pairs([(target, t) for t in tools])


def cedar_pairs(pairs):
    acts = ",\n".join(f'    AgentCore::Action::"{a}___{b}"' for a, b in pairs)
    return f"  action in [\n{acts}\n  ],"


def policy_files(m, custom_tools, env):
    t = env.get_template("cedar/policies.j2").make_module()
    c, auto = m["connectors"], m["autonomy"]
    builtin = [k for k in READ_TOOLS if k in c]
    files = {}

    def emit(name, stmts, why):
        stmts = [s for s in stmts if s]
        if stmts:
            files[name] = (why, stmts)

    emit("10-permit-reads.cedar", [t.permit_reads(k, READ_TOOLS[k], SCOPE[k]) for k in builtin] +
         [t.permit_reads(n, [x["name"] for x in v["tools"] if not x.get("mutating")], v["scope"].split("/", 1)[-1]) for n, v in custom_tools.items()],
         "CP-1: permit read tools when the scope claim matches")
    if auto == "L1" and "tickets" in c:
        emit("20-permit-ticket-writes.cedar", [t.permit_ticket_writes(c["tickets"]["project"])], "CP-2: ticket writes need tickets.write and the right project")
    mut = [("ops", o) for o in OPS_TOOLS] + [(n, x["name"]) for n, v in custom_tools.items() for x in v["tools"] if x.get("mutating")]
    emit("30-forbid-mutations.cedar", [t.forbid_mutations(mut)], "CP-3: nobody may restart, scale, roll back or mutate (forbid_ops)")
    unb = [(k, READ_TOOLS[k][0]) for k in ("db", "logs") if k in c]
    unb = [(k, "find_transactions" if k == "db" else "query_logs") for k, _ in sorted(unb, key=lambda x: x[0])]
    if unb:
        emit("40-forbid-unbounded.cedar", [t.forbid_unbounded(unb, c.get("db", {}).get("max_rows", 200))], "CP-4: no unbounded reads (max_rows)")
    emit("50-explicit-deny.cedar", [t.explicit_deny(k, READ_TOOLS[k], SCOPE[k]) for k in ("db", "logs", "warehouse") if k in c] +
         [t.explicit_deny(n, [x["name"] for x in v["tools"] if not x.get("mutating")], v["scope"].split("/", 1)[-1]) for n, v in custom_tools.items()],
         "CP-5: data tools are forbidden unless the matching read scope is present")
    zone_stmts, seen = [], set()
    for k, tools in SERVICE_TARGETS.items():                     # services not listed in the connector are out of bounds
        if k not in c:
            continue
        allowed = {g.rsplit("/", 1)[-1] for g in c["logs"]["log_groups"]} if k == "logs" else set(c["changes"]["services"])
        for svc in KNOWN_SERVICES[k]:
            if svc not in allowed:
                seen.add((k, svc)); zone_stmts.append(t.forbid_service(k, tools, svc))
    for z in m["policy"]["forbidden_zones"]:
        if z.startswith("service:"):
            svc = z.split(":", 1)[1]
            for k, tools in SERVICE_TARGETS.items():
                if k in c and (k, svc) not in seen:
                    seen.add((k, svc)); zone_stmts.append(t.forbid_service(k, tools, svc))
        else:
            zone_stmts.append(t.forbid_tool(*z.split(".", 1)))
    emit("60-zones.cedar", zone_stmts, "scoping and forbidden zones derived from the manifest")
    return files


def render(manifest_path, out_root="agents"):
    path, m, sha, charter, custom_tools = validate(manifest_path)
    env = Environment(loader=FileSystemLoader(str(ROOT / "factory/templates")), undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
    env.globals.update(cedar_actions=cedar_actions, cedar_pairs=cedar_pairs)
    out = ROOT / out_root / m["product"]
    hdr = f"generated from agent.yaml@{sha} - edit the manifest, not this file"
    (out / "policy").mkdir(parents=True, exist_ok=True)
    for old in (out / "policy").glob("*.cedar"):          # a removed zone must disappear (idempotent re-render)
        old.unlink()
    c = m["connectors"]
    reads = ", ".join(x for x in ["logs", "transactions", "warehouse history", "deploys", "tickets"] if {"logs": "logs", "transactions": "db", "warehouse history": "warehouse", "deploys": "changes", "tickets": "tickets"}[x] in c)
    ticket_project = c.get("tickets", {}).get("project")
    role = env.get_template("prompt/role.md.j2").render(product=m["product"], autonomy=m["autonomy"], owner_team=m["owner_team"], charter=charter,
                                                       reads=reads, has_warehouse=("warehouse" in c), can_write=(m["autonomy"] == "L1" and bool(ticket_project)),
                                                       ticket_project=ticket_project, max_tool_calls=m["budgets"]["max_tool_calls"])
    (out / "prompt").mkdir(exist_ok=True)
    (out / "prompt/role.md").write_text(f"<!-- {hdr} -->\n" + role)
    for f in ("untrusted.md", "cite.md"):
        shutil.copy(ROOT / "agent/prompt" / f, out / "prompt" / f)
    # gateway targets
    targets = []
    for k in [k for k in READ_TOOLS if k in c]:
        names = list(READ_TOOLS[k]) + (WRITE_TOOLS.get(k, []) if m["autonomy"] == "L1" else [])
        tools = [x for x in TARGETS[k][1] if x["name"] in names]
        targets.append({"name": k, "description": TARGETS[k][0], "lambda": f"${{LAB_A_LAMBDA:{k}}}", "tools": tools, "config": c[k]})
    targets.append({"name": "ops", "description": TARGETS["ops"][0], "lambda": "${LAB_A_LAMBDA:ops}", "tools": TARGETS["ops"][1], "config": {}})
    for cu in c.get("custom") or []:
        tj = custom_tools[cu["name"]]
        targets.append({"name": cu["name"], "description": tj["description"], "lambda": f"${{CUSTOM_LAMBDA:{cu['name']}}}", "tools": tj["tools"],
                        "build": {"runtime": cu["runtime"], "path": cu["path"]}, "config": {}})
    (out / "gateway").mkdir(exist_ok=True)
    (out / "gateway/targets.json").write_text(json.dumps({"_generated": hdr, "targets": targets}, indent=1) + "\n")
    # cedar
    pf = policy_files(m, custom_tools, env)
    for name, (why, stmts) in pf.items():
        (out / "policy" / name).write_text(f"// {hdr}\n// {why}\n\n" + "\n\n".join(stmts) + "\n")
    # memory + evals + copies
    (out / "memory").mkdir(exist_ok=True)
    p = m["product"]
    (out / "memory/memory.json").write_text(json.dumps({"_generated": hdr, "name": f"fx_{p.replace('-', '_')}",
        "namespaces": {"incidents": f"/products/{p}/incidents", "runbooks": f"/products/{p}/runbooks"},
        "seed": {"incidents": m["memory"]["incidents"], "runbooks": m["memory"]["runbooks"]}}, indent=1) + "\n")
    (out / "evals").mkdir(exist_ok=True)
    (out / "evals/gates.json").write_text(json.dumps({"_generated": hdr, "replay": m["evals"]["replay"], "gates": m["evals"]["gates"], "budgets": m["budgets"]}, indent=1) + "\n")
    shutil.copy(path, out / "agent.yaml")
    shutil.copy((path.parent / m["charter"]), out / "charter.md")
    (out / ".manifest.sha").write_text(sha + "\n")
    return out, sha, sorted(pf)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["validate", "new-agent"])
    ap.add_argument("--from", dest="src", required=True)
    ap.add_argument("--out", default="agents")
    ap.add_argument("--name", default=None, help="optional: must equal the manifest product")
    a = ap.parse_args()
    try:
        if a.cmd == "validate":
            _, m, sha, _, _ = validate(a.src)
            print(f"OK: {m['product']} (autonomy {m['autonomy']}) manifest@{sha}")
        else:
            _, mm, _, _, _ = validate(a.src)
            if a.name and a.name != mm["product"]:
                raise ManifestError([f"NAME={a.name} does not match product '{mm['product']}' in the manifest (the manifest is the source of truth)"])
            out, sha, files = render(a.src, a.out)
            print(f"rendered {out.relative_to(ROOT)} from manifest@{sha}: " + ", ".join(files))
    except ManifestError as e:
        print("INVALID agent.yaml:\n" + str(e), file=sys.stderr)
        sys.exit(1)
