#!/usr/bin/env python3
"""Tear down everything Lab A created in this account: runtime, gateway, policy engine, memory, stack, artifact bucket."""
import json, subprocess, sys
from pathlib import Path
import boto3

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from mcpc import load_env
env = load_env()
region, acct = env["AWS_REGION"], env["AWS_ACCOUNT_ID"]
current = boto3.client("sts", region_name=region).get_caller_identity()["Account"]
if current != acct:       # .env records the account that was bootstrapped; never tear down a different one
    sys.exit(f"refusing: .env says this lab lives in account {acct}, but your credentials are for {current}")
if (ROOT / ".labA.json").exists():
    # reset removes the Runtime, Gateway, policy engine and memory (deleting the Runtime here too would be a second,
    # failing delete: the service answers AccessDenied for a Runtime that is already deleting)
    subprocess.run([sys.executable, str(ROOT / "scripts/labA.py"), "reset"], check=False)
s3 = boto3.resource("s3", region_name=region)
for b in (f"dezerv-laba-data-{acct}-{region}", f"dezerv-laba-artifacts-{acct}-{region}"):
    try:
        s3.Bucket(b).objects.all().delete()
        if "artifacts" in b:
            s3.Bucket(b).delete()
    except Exception as e:
        print("bucket", b, e)
cf = boto3.client("cloudformation", region_name=region)
cf.delete_stack(StackName="DezervLabA")
cf.get_waiter("stack_delete_complete").wait(StackName="DezervLabA", WaiterConfig={"Delay": 10, "MaxAttempts": 90})
print("stack deleted")
