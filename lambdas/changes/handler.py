import json, os, boto3
from _common import envelope, parse_ist, dispatch

s3 = boto3.client("s3")


def get_recent_deploys(ev):
    deploys = json.loads(s3.get_object(Bucket=os.environ["DATA_BUCKET"], Key=os.environ.get("DEPLOYS_KEY", "changes/deploys.json"))["Body"].read())
    out = [d for d in deploys if d["service"] == ev["service"]]
    if ev.get("since"):
        since = parse_ist(ev["since"])
        out = [d for d in out if parse_ist(d["deployed_at"]) >= since]
    out.sort(key=lambda d: d["deployed_at"], reverse=True)
    return envelope("deploys:changes", f"service={ev['service']} since={ev.get('since')}", {"count": len(out), "deploys": out[:25]})


def lambda_handler(event, context):
    return dispatch(event, context, {"get_recent_deploys": get_recent_deploys})
