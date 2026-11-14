import json, os, boto3, mongomock
from _common import envelope, dispatch

BUCKET = os.environ["DATA_BUCKET"]
PREFIX = os.environ.get("DATA_PREFIX", "mongo/")                     # squads: squads/<name>/data/mongo/
COLLECTIONS = os.environ.get("COLLECTIONS", "txn,users,error_codes").split(",")
PRIMARY = os.environ.get("PRIMARY_COLLECTION", "txn")                 # what find_transactions searches
s3 = boto3.client("s3")
_db = None
FORBIDDEN = {"$where", "$function", "$accumulator", "$out", "$merge", "$set", "$unset", "$inc", "$push", "$pull",
             "$rename", "$expr", "$jsonSchema", "$text"}
MAX_LIMIT = 200


def db():
    global _db
    if _db is None:
        _db = mongomock.MongoClient().payments
        for coll in COLLECTIONS:
            try:
                docs = json.loads(s3.get_object(Bucket=BUCKET, Key=f"{PREFIX}{coll}.json")["Body"].read())
            except s3.exceptions.NoSuchKey:     # a squad may not have every collection (e.g. no users)
                continue
            if docs:
                _db[coll].insert_many(docs)
    return _db


def _guard(node):
    if isinstance(node, dict):
        for k, v in node.items():
            if k in FORBIDDEN or (isinstance(k, str) and k.startswith("$") and k in FORBIDDEN):
                raise ValueError(f"operator {k} is not allowed (read-only)")
            _guard(v)
    elif isinstance(node, list):
        for v in node:
            _guard(v)


def _obj(v, name):
    if isinstance(v, str):
        v = json.loads(v)
    if not isinstance(v, dict):
        raise ValueError(f"{name} must be an object")
    return v


def find_transactions(ev):
    flt = _obj(ev.get("filter") or {}, "filter")
    _guard(flt)
    proj = _obj(ev["projection"], "projection") if ev.get("projection") else None
    limit = min(int(ev.get("limit", 50)), MAX_LIMIT)
    total = db()[PRIMARY].count_documents(flt)
    docs = list(db()[PRIMARY].find(flt, proj or {"_id": 0}).limit(limit))
    for d in docs:
        d.pop("_id", None)
    return envelope(f"mongodb:{PRIMARY}", json.dumps({"filter": flt, "limit": limit}), {"returned": len(docs), "total_matching": total, "transactions": docs})


def get_user_state(ev):
    u = db().users.find_one({"user_id": ev["user_id"]}, {"_id": 0})
    if not u:
        raise ValueError("user not found")
    last = list(db().txn.find({"user_id": ev["user_id"]}, {"_id": 0}).sort("created_at", -1).limit(5))
    return envelope("mongodb:payments.users", f"user_id={ev['user_id']}", {"user": u, "last_transactions": last})


def get_error_code(ev):
    c = db().error_codes.find_one({"code": ev["code"]}, {"_id": 0})
    if not c:
        raise ValueError("unknown error code")
    return envelope("mongodb:payments.error_codes", f"code={ev['code']}", c)


def lambda_handler(event, context):
    return dispatch(event, context, {"find_transactions": find_transactions, "get_user_state": get_user_state,
                                     "get_error_code": get_error_code})
