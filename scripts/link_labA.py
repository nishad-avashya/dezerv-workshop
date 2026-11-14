#!/usr/bin/env python3
"""link_labA.py: rebuild .env and .labA.json in THIS checkout from what already exists in the account.

Use it in a second editor (Build with Skills) that shares the account with the Lab A editor: nothing is redeployed. It reads the
CloudFormation outputs, the Cognito client secrets, and finds the Gateway / policy engine / memory / runtime by name, then regenerates
the local data files (same anchor as the Lab A bootstrap, recovered from S3) that Lab B and the capstone read.
"""
import json, os, subprocess, sys
from datetime import datetime
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
region = os.environ.get("LAB_REGION", "us-west-2")
sess = boto3.Session(region_name=region)
acct = sess.client("sts").get_caller_identity()["Account"]
if os.environ.get("EXPECT_ACCOUNT") and os.environ["EXPECT_ACCOUNT"] != acct:
    sys.exit(f"refusing: expected account {os.environ['EXPECT_ACCOUNT']}, credentials are for {acct}")
cf, idp, ctl, s3 = sess.client("cloudformation"), sess.client("cognito-idp"), sess.client("bedrock-agentcore-control"), sess.client("s3")
try:
    outs = {o["OutputKey"]: o["OutputValue"] for o in cf.describe_stacks(StackName="DezervLabA")["Stacks"][0]["Outputs"]}
except Exception:
    sys.exit("stack DezervLabA not found in this account/region: run `make bootstrap` (Lab A) first")
meta = json.loads(s3.get_object(Bucket=outs["DataBucket"], Key="meta.json")["Body"].read())
anchor = datetime.fromisoformat(meta["anchor"])

import bootstrap  # noqa: E402  (reuses write_env so .env has exactly the keys Lab A's bootstrap writes)
bootstrap.write_env(cf, idp, region, acct, anchor)

subprocess.run([sys.executable, str(ROOT / "tools/gen_data.py"), "--anchor", meta["anchor"], "--out", str(ROOT / "data")], check=True, stdout=subprocess.DEVNULL)
(ROOT / "evals/replay").mkdir(parents=True, exist_ok=True)
for f in (ROOT / "evals/replay").glob("*.json"):
    f.unlink()
for f in (ROOT / "data/replay").glob("*.json"):
    (ROOT / "evals/replay" / f.name).write_text(f.read_text())


def paged(fn, key, **kw):
    out, tok = [], None
    while True:
        r = fn(**kw, **({"nextToken": tok} if tok else {}))
        out += r.get(key, [])
        tok = r.get("nextToken")
        if not tok:
            return out


st = {}
g = next((x for x in paged(ctl.list_gateways, "items") if x["name"] == "dezerv-laba-gw"), None)
if g:
    gg = ctl.get_gateway(gatewayIdentifier=g["gatewayId"])
    st.update(gateway_id=g["gatewayId"], gateway_arn=gg["gatewayArn"], gateway_url=gg["gatewayUrl"])
pe = next((x for x in paged(ctl.list_policy_engines, "policyEngines") if x["name"] == "dezerv_laba_pe"), None)
if pe:
    st.update(policy_engine_id=pe["policyEngineId"], policy_engine_arn=ctl.get_policy_engine(policyEngineId=pe["policyEngineId"])["policyEngineArn"])
m = next((x for x in paged(ctl.list_memories, "memories") if x.get("id", "").startswith("dezerv_payments_oncall-")), None)
if m:
    mm = ctl.get_memory(memoryId=m["id"])["memory"]
    st.update(memory_id=m["id"], memory_strategies=json.dumps({s["name"]: s["strategyId"] for s in mm.get("strategies", mm.get("memoryStrategies", []))}))
rt = next((x for x in paged(ctl.list_agent_runtimes, "agentRuntimes") if x["agentRuntimeName"] == "dezerv_payments_oncall"), None)
if rt:
    st.update(runtime_id=rt["agentRuntimeId"], runtime_arn=rt["agentRuntimeArn"])
(ROOT / ".labA.json").write_text(json.dumps(st, indent=1))
print(f"linked to account {acct}: anchor {meta['anchor']}; found " + ", ".join(k for k in ("gateway_id", "policy_engine_id", "memory_id", "runtime_id") if k in st))
missing = [k for k in ("gateway_id", "policy_engine_id", "memory_id", "runtime_id") if k not in st]
if missing:
    print("WARNING: Lab A pieces not found (finish Lab A or `make solution-part6`): " + ", ".join(missing))
