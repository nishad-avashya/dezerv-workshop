#!/usr/bin/env python3
"""Lab A bootstrap: build Lambdas, deploy stack DezervLabA, seed data, write .env.  Idempotent.

Run:  uv run --python 3.12 --with boto3 python scripts/bootstrap.py [--expect-account 123456789012]
"""
import argparse, hashlib, json, os, shutil, subprocess, sys, time, zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parent.parent
IST = timezone(timedelta(hours=5, minutes=30))
STACK = "DezervLabA"
FUNCS = {"logs": [], "db": ["mongomock"], "warehouse": ["duckdb"], "changes": [], "tickets": [], "ops": [],
         "interceptor": []}


def log(msg):
    print(f"[bootstrap] {msg}", flush=True)


def pick_anchor(now):
    """Latest 10:40 IST (today or yesterday) that has >= 40 min of 'past' after it (V-9: relative timestamps)."""
    t = now.astimezone(IST).replace(hour=10, minute=40, second=0, microsecond=0)
    if t + timedelta(minutes=40) > now:
        t -= timedelta(days=1)
    return t


def build_lambdas():
    out = ROOT / "build"
    shutil.rmtree(out, ignore_errors=True)
    zips = {}
    for name, deps in FUNCS.items():
        d = out / name
        d.mkdir(parents=True)
        for f in (ROOT / "lambdas" / name).glob("*.py"):
            shutil.copy(f, d)
        shutil.copy(ROOT / "lambdas" / "_common.py", d)
        if deps:
            subprocess.run(["uv", "pip", "install", "--quiet", "--target", str(d), "--python-version", "3.12",
                            "--python-platform", "x86_64-manylinux_2_28", *deps], check=True)
        z = out / f"{name}.zip"
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(d.rglob("*")):
                if p.is_file() and "__pycache__" not in p.parts:
                    zi = zipfile.ZipInfo(str(p.relative_to(d)), (2026, 1, 1, 0, 0, 0))  # deterministic hash
                    zi.external_attr = 0o644 << 16
                    zf.writestr(zi, p.read_bytes(), zipfile.ZIP_DEFLATED)
        zips[name] = z
    h = hashlib.sha256()
    for n in sorted(zips):
        h.update(zips[n].read_bytes())
    return zips, h.hexdigest()[:12]


def ensure_artifact_bucket(s3, acct, region):
    b = f"dezerv-laba-artifacts-{acct}-{region}"
    try:
        s3.head_bucket(Bucket=b)
    except ClientError:
        kw = {} if region == "us-east-1" else {"CreateBucketConfiguration": {"LocationConstraint": region}}
        s3.create_bucket(Bucket=b, **kw)
        s3.put_public_access_block(Bucket=b, PublicAccessBlockConfiguration={
            "BlockPublicAcls": True, "BlockPublicPolicy": True, "IgnorePublicAcls": True, "RestrictPublicBuckets": True})
    return b


def deploy_stack(cf, bucket, code_hash, data_hash="none"):
    body = (ROOT / "infra" / "template.yaml").read_text()
    params = [{"ParameterKey": "ArtifactBucket", "ParameterValue": bucket}, {"ParameterKey": "CodeHash", "ParameterValue": code_hash},
              {"ParameterKey": "DataHash", "ParameterValue": data_hash}]
    kw = dict(StackName=STACK, TemplateBody=body, Parameters=params, Capabilities=["CAPABILITY_NAMED_IAM"])
    try:
        cf.describe_stacks(StackName=STACK)
        exists = True
    except ClientError:
        exists = False
    try:
        if exists:
            cf.update_stack(**kw)
            waiter = "stack_update_complete"
        else:
            cf.create_stack(**kw, OnFailure="DELETE")
            waiter = "stack_create_complete"
    except ClientError as e:
        if "No updates are to be performed" in str(e):
            log("stack already up to date")
            return
        raise
    log(f"waiting for stack ({waiter}) ...")
    cf.get_waiter(waiter).wait(StackName=STACK, WaiterConfig={"Delay": 10, "MaxAttempts": 90})


def seed_s3(s3, bucket, data):
    for rel in ["mongo/txn.json", "mongo/users.json", "mongo/error_codes.json", "mongo/mandates.json", "snowflake/daily_payment_stats.csv",
                "snowflake/query_logs.csv", "changes/deploys.json"]:
        s3.upload_file(str(data / rel), bucket, rel)
    s3.upload_file(str(data / "meta.json"), bucket, "meta.json")
    log("uploaded mock data to S3")


def seed_tickets(ddb, data):
    t = ddb.Table("dezerv-tickets")
    tickets = json.loads((data / "jira/tickets.json").read_text())
    with t.batch_writer() as bw:
        for x in tickets:
            bw.put_item(Item=x)
    try:  # never reset the counter on a re-run (would re-issue ticket keys)
        t.put_item(Item={"key": "COUNTER#PAY", "n": 0}, ConditionExpression="attribute_not_exists(#k)", ExpressionAttributeNames={"#k": "key"})
    except t.meta.client.exceptions.ConditionalCheckFailedException:
        pass
    log(f"loaded {len(tickets)} tickets")


def backfill_logs(logs, data, now):
    for group, fname in [("/dezerv/payments-gw", "payments-gw.log"), ("/dezerv/kyc-svc", "kyc-svc.log")]:
        events = []
        for line in (data / "cloudwatch" / fname).read_text().splitlines():
            rec = json.loads(line)
            ts = datetime.fromisoformat(rec["ts"])
            if ts <= now:  # CloudWatch rejects events > 2h in the future; we drop anything after 'now'
                events.append({"timestamp": int(ts.timestamp() * 1000), "message": line})
        events.sort(key=lambda e: e["timestamp"])
        stream = f"backfill-{events[0]['timestamp'] // 1000 // 86400}"  # one stream per anchor day => idempotent
        try:
            logs.create_log_stream(logGroupName=group, logStreamName=stream)
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceAlreadyExistsException":
                raise
            log(f"{group}: {stream} already backfilled, skipping")
            continue
        i = 0
        while i < len(events):
            batch = [events[i]]
            j = i + 1
            while j < len(events) and len(batch) < 5000 and events[j]["timestamp"] - events[i]["timestamp"] < 23 * 3600 * 1000:
                batch.append(events[j]); j += 1
            resp = logs.put_log_events(logGroupName=group, logStreamName=stream, logEvents=batch)
            if resp.get("rejectedLogEventsInfo"):
                log(f"WARNING {group}: rejected events {resp['rejectedLogEventsInfo']}")
            i = j
        log(f"backfilled {len(events)} events into {group}")


def write_env(cf, idp, region, acct, anchor):
    outs = {o["OutputKey"]: o["OutputValue"] for o in cf.describe_stacks(StackName=STACK)["Stacks"][0]["Outputs"]}
    pool = outs["UserPoolId"]
    env = {"AWS_REGION": region, "AWS_ACCOUNT_ID": acct, "LAB_ANCHOR": anchor.isoformat(),
           "DATA_BUCKET": outs["DataBucket"], "GATEWAY_ROLE_ARN": outs["GatewayRoleArn"], "RUNTIME_ROLE_ARN": outs["RuntimeRoleArn"], "TOOL_ROLE_ARN": outs["ToolRoleArn"], "USER_POOL_ID": pool,
           "DISCOVERY_URL": outs["DiscoveryUrl"], "TOKEN_URL": outs["TokenUrl"],
           "ONCALL_CLIENT_ID": outs["OncallClientId"], "SUPPORT_CLIENT_ID": outs["SupportClientId"]}
    for persona, key in (("ONCALL", "OncallClientId"), ("SUPPORT", "SupportClientId")):
        env[f"{persona}_CLIENT_SECRET"] = idp.describe_user_pool_client(UserPoolId=pool, ClientId=outs[key])["UserPoolClient"]["ClientSecret"]
    for k, v in outs.items():
        if k.endswith("FnArn"):
            env[k.replace("FnArn", "").upper() + "_LAMBDA_ARN"] = v
    (ROOT / ".env").write_text("".join(f"{k}={v}\n" for k, v in env.items()))
    os.chmod(ROOT / ".env", 0o600)
    log("wrote .env")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default=os.environ.get("LAB_REGION", "us-west-2"))  # not AWS_REGION: the lab is pinned to us-west-2
    ap.add_argument("--expect-account", default=os.environ.get("EXPECT_ACCOUNT"))
    a = ap.parse_args()
    sess = boto3.Session(region_name=a.region)
    acct = sess.client("sts").get_caller_identity()["Account"]
    log(f"account {acct} region {a.region}")
    if a.expect_account and a.expect_account != acct:
        sys.exit(f"refusing: expected account {a.expect_account}, credentials are for {acct}")
    now = datetime.now(timezone.utc)
    anchor = pick_anchor(now)
    log(f"scenario anchor {anchor.isoformat()}")
    data = ROOT / "data"
    subprocess.run([sys.executable, str(ROOT / "tools" / "gen_data.py"), "--anchor", anchor.isoformat(), "--out", str(data)], check=True)
    (ROOT / "evals" / "replay").mkdir(parents=True, exist_ok=True)
    for f in (ROOT / "evals" / "replay").glob("*.json"):
        f.unlink()
    for f in (data / "replay").glob("*.json"):
        shutil.copy(f, ROOT / "evals" / "replay" / f.name)
    zips, h = build_lambdas()
    s3, cf = sess.client("s3"), sess.client("cloudformation")
    bucket = ensure_artifact_bucket(s3, acct, a.region)
    for n, z in zips.items():
        s3.upload_file(str(z), bucket, f"lambda/{n}-{h}.zip")
    log(f"uploaded {len(zips)} lambda packages (hash {h})")
    dh = hashlib.sha256()
    for rel in sorted(p.relative_to(data).as_posix() for p in (data / "mongo").glob("*.json")) + ["snowflake/daily_payment_stats.csv", "snowflake/query_logs.csv", "changes/deploys.json"]:
        dh.update((data / rel).read_bytes())
    deploy_stack(cf, bucket, h, dh.hexdigest()[:12])   # data hash changes => db/warehouse/changes Lambdas get fresh containers
    outs = {o["OutputKey"]: o["OutputValue"] for o in cf.describe_stacks(StackName=STACK)["Stacks"][0]["Outputs"]}
    seed_s3(s3, outs["DataBucket"], data)
    seed_tickets(sess.resource("dynamodb"), data)
    backfill_logs(sess.client("logs"), data, now)
    write_env(cf, sess.client("cognito-idp"), a.region, acct, anchor)
    log("done")


if __name__ == "__main__":
    main()
