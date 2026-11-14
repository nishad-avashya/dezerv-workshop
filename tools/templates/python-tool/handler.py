"""Custom squad tool: __TOOL__(__ARG__). A read-only lookup in the squad's primary collection.
Scaffolded by `make new-tool` / the capstone generator. Edit the lookup, keep it read-only, keep masking in the tool
(defence in depth: the Gateway interceptor masks too)."""
import json, os, re, boto3
from _common import envelope, dispatch

BUCKET = os.environ["DATA_BUCKET"]
KEY = os.environ.get("DATA_PREFIX", "mongo/") + os.environ.get("PRIMARY_COLLECTION", "records") + ".json"
ID_FIELD = "__ID_FIELD__"
PII_FIELDS = __PII__
s3 = boto3.client("s3")
_cache = None


def mask(field, value):
    if not isinstance(value, str):
        return value
    digits = re.sub(r"\D", "", value)
    if "@" in value:
        return "***@" + value.split("@", 1)[1]
    return ("X" * max(0, len(value) - 3)) + value[-3:] if len(value) > 3 else "XXX"


def rows():
    global _cache
    if _cache is None:
        _cache = json.loads(s3.get_object(Bucket=BUCKET, Key=KEY)["Body"].read())
    return _cache


def __TOOL__(ev):
    rid = ev.get("__ARG__")
    if not rid:
        raise ValueError("__ARG__ is required")
    for r in rows():
        if r.get(ID_FIELD) == rid:
            r = dict(r)
            for f in PII_FIELDS:
                if f in r:
                    r[f] = mask(f, r[f])
            return envelope(f"squad:{KEY}", f"__ARG__={rid}", r)
    raise ValueError(f"no record {rid}")


def lambda_handler(event, context):
    return dispatch(event, context, {"__TOOL__": __TOOL__})
