"""Gateway interceptor: one Lambda, REQUEST + RESPONSE interception points (lab spec 7.4)."""
import base64, json, os, time
from datetime import datetime, timezone
import boto3
from pii import mask_obj, tag_untrusted

ddb = boto3.resource("dynamodb")
ssm = boto3.client("ssm")
logs = boto3.client("logs")

RATE_TABLE = os.environ.get("RATE_TABLE", "dezerv-ratelimit")
FREEZE_PARAM = os.environ.get("FREEZE_PARAM", "/dezerv/freeze")
AUDIT_GROUP = os.environ.get("AUDIT_GROUP", "/dezerv/gateway-audit")
LIMIT_PER_MIN = int(os.environ.get("LIMIT_PER_MIN", "30"))
WRITE_TOOLS = {"tickets___create_ticket", "tickets___add_comment", "ops___restart_service", "ops___scale_service", "ops___rollback_deploy"}

_freeze_cache = (0.0, "off")
_stream = None


def claims_of(headers):
    tok = (headers or {}).get("Authorization") or (headers or {}).get("authorization") or ""
    tok = tok.split(" ")[-1]
    try:
        p = tok.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))
    except Exception:
        return {}


def freeze_on(now=None):
    """'on' | 'off' | '<iso-start>/<iso-end>' window."""
    global _freeze_cache
    if time.time() - _freeze_cache[0] > 5:
        try:
            v = ssm.get_parameter(Name=FREEZE_PARAM)["Parameter"]["Value"].strip()
        except Exception:
            v = "off"
        _freeze_cache = (time.time(), v)
    v = _freeze_cache[1]
    if v == "on":
        return True
    if "/" in v:
        try:
            a, b = (datetime.fromisoformat(x) for x in v.split("/"))
            return a <= (now or datetime.now(timezone.utc)) <= b
        except Exception:
            return False
    return False


def over_limit(sub):
    minute = int(time.time() // 60)
    r = ddb.Table(RATE_TABLE).update_item(
        Key={"pk": f"{sub}#{minute}"}, UpdateExpression="ADD calls :one SET expires_at = :ttl",
        ExpressionAttributeValues={":one": 1, ":ttl": minute * 60 + 300}, ReturnValues="UPDATED_NEW")
    return int(r["Attributes"]["calls"]) > LIMIT_PER_MIN


def audit(rec):
    global _stream
    rec["ts"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(rec))
    try:
        if _stream is None:
            _stream = f"interceptor-{int(time.time())}-{os.getpid()}"
            logs.create_log_stream(logGroupName=AUDIT_GROUP, logStreamName=_stream)
        logs.put_log_events(logGroupName=AUDIT_GROUP, logStreamName=_stream,
                            logEvents=[{"timestamp": int(time.time() * 1000), "message": json.dumps(rec)}])
    except Exception as e:  # audit must never break the call path
        print("audit write failed:", e)


def tool_error(req_id, code, msg):
    body = {"jsonrpc": "2.0", "id": req_id, "result": {"isError": True,
            "content": [{"type": "text", "text": json.dumps({"error": code, "message": msg})}]}}
    return {"interceptorOutputVersion": "1.0", "mcp": {"transformedGatewayResponse": {"statusCode": 200, "body": body}}}


def handle_request(mcp):
    gr = mcp["gatewayRequest"]
    body = gr.get("body") or {}
    passthrough = {"interceptorOutputVersion": "1.0", "mcp": {"transformedGatewayRequest": {"body": body}}}
    if body.get("method") != "tools/call":
        return passthrough
    tool = (body.get("params") or {}).get("name", "")
    c = claims_of(gr.get("headers"))
    sub = c.get("sub") or c.get("client_id") or "unknown"
    rec = {"point": "REQUEST", "principal": sub, "client_id": c.get("client_id"), "tool": tool}
    if over_limit(sub):
        audit({**rec, "decision": "denied", "reason": "RATE_LIMITED"})
        return tool_error(body.get("id"), "RATE_LIMITED", f"limit of {LIMIT_PER_MIN} tool calls per minute exceeded")
    if tool in WRITE_TOOLS and freeze_on():
        audit({**rec, "decision": "denied", "reason": "CHANGE_FREEZE"})
        return tool_error(body.get("id"), "CHANGE_FREEZE", "change freeze is active: write tools are disabled, reads continue")
    audit({**rec, "decision": "allowed"})
    return passthrough


def handle_response(mcp):
    gres = mcp.get("gatewayResponse") or {}
    body = gres.get("body")
    tool = ((mcp.get("gatewayRequest") or {}).get("body") or {}).get("params", {}).get("name", "")
    out = {"interceptorOutputVersion": "1.0", "mcp": {"transformedGatewayResponse": {"statusCode": gres.get("statusCode", 200), "body": body}}}
    if not isinstance(body, dict):
        return out
    result = body.get("result") or {}
    for item in result.get("content", []) or []:
        if item.get("type") != "text":
            continue
        try:
            data = json.loads(item["text"])
            item["text"] = json.dumps(mask_obj(tag_untrusted(tool, data)))
        except ValueError:
            item["text"] = mask_obj(item["text"])
    if "structuredContent" in result:
        result["structuredContent"] = mask_obj(tag_untrusted(tool, result["structuredContent"]))
    if tool:
        audit({"point": "RESPONSE", "tool": tool, "masked": True})
    return out


def lambda_handler(event, context):
    mcp = event["mcp"]
    # REQUEST events carry "gatewayResponse": null, so test the value, not the key
    return handle_response(mcp) if mcp.get("gatewayResponse") is not None else handle_request(mcp)
