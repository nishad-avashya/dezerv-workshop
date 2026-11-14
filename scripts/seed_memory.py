#!/usr/bin/env python3
"""Seed AgentCore Memory with 25 incidents + 8 runbooks (spec 7.7, spike V-6).

Uses BatchCreateMemoryRecords: records are written directly into the semantic namespaces, so they are retrievable
as soon as they are indexed (no LLM extraction wait). Re-runnable: skips if the namespaces already have records.
"""
import json, sys, time, uuid
from datetime import datetime, timezone
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from mcpc import load_env

env = load_env()
st = json.loads((ROOT / ".labA.json").read_text())
mem, strategies = st["memory_id"], json.loads(st["memory_strategies"])
dp = boto3.client("bedrock-agentcore", region_name=env.get("AWS_REGION", "us-west-2"))

SETS = [("/products/payments-gw/incidents", strategies["payments_facts"], sorted((ROOT / "data/incidents").glob("*.md"))),
        ("/products/payments-gw/runbooks", strategies["payments_facts"], sorted((ROOT / "data/runbooks").glob("*.md")))]


def count(ns):
    n, tok = 0, None
    while True:
        r = dp.list_memory_records(memoryId=mem, namespace=ns, **({"nextToken": tok} if tok else {}))
        n += len(r.get("memoryRecordSummaries", []))
        tok = r.get("nextToken")
        if not tok:
            return n


def wipe(ns):
    while True:
        ids = [r["memoryRecordId"] for r in dp.list_memory_records(memoryId=mem, namespace=ns, maxResults=50).get("memoryRecordSummaries", [])]
        if not ids:
            return
        dp.batch_delete_memory_records(memoryId=mem, records=[{"memoryRecordId": i} for i in ids])


if "--force" in sys.argv:
    for ns, _, _ in SETS:
        wipe(ns)
    print("wiped existing records")

for ns, sid, files in SETS:
    have = count(ns)
    if have >= len(files):
        print(f"{ns}: already has {have} records, skipping")
        continue
    recs = [{"requestIdentifier": f.stem, "namespaces": [ns], "memoryStrategyId": sid,
             "content": {"text": f.read_text()}, "timestamp": datetime.now(timezone.utc)} for f in files]
    for i in range(0, len(recs), 10):
        r = dp.batch_create_memory_records(memoryId=mem, records=recs[i:i + 10], clientToken=str(uuid.uuid4()))
        bad = r.get("failedRecords") or []
        if bad:
            sys.exit(f"failed: {bad}")
    print(f"{ns}: wrote {len(recs)} records")

print("polling until records are listable ...")
for _ in range(30):
    inc, rb = count(SETS[0][0]), count(SETS[1][0])
    print(f"  incidents={inc} runbooks={rb}")
    if inc >= 25 and rb >= 8:
        print("memory seeded"); sys.exit(0)
    time.sleep(10)
sys.exit("timed out waiting for records")
