"""Log tools. Reads with FilterLogEvents (real-time) rather than Logs Insights: Insights indexes
newly written, back-dated events only after several minutes (workshop finding V-9), which would break a
bootstrap that runs during the opening talk. Aggregation is done here."""
import json, re, boto3
from collections import Counter
from _common import envelope, parse_ist, dispatch

logs = boto3.client("logs")
import os
ALLOWED = set(os.environ.get("LOG_SERVICES", "payments-gw,kyc-svc").split(","))
MAX_WINDOW_H = 6
MAX_PAGES = 40


def _events(service, start, end, pattern=None, stop_after=None):
    if service not in ALLOWED:
        raise ValueError(f"service must be one of {sorted(ALLOWED)}")
    s, e = parse_ist(start), parse_ist(end)
    if e <= s:
        raise ValueError("end must be after start")
    if (e - s).total_seconds() > MAX_WINDOW_H * 3600:
        raise ValueError(f"window must be <= {MAX_WINDOW_H}h")
    kw = dict(logGroupName=f"/dezerv/{service}", startTime=int(s.timestamp() * 1000), endTime=int(e.timestamp() * 1000))
    if pattern:
        kw["filterPattern"] = pattern
    out, token, pages = [], None, 0
    while pages < MAX_PAGES:
        r = logs.filter_log_events(**kw, **({"nextToken": token} if token else {}))
        pages += 1
        for ev in r["events"]:
            try:
                rec = json.loads(ev["message"])
            except ValueError:
                rec = {"msg": ev["message"]}
            rec["@timestamp"] = ev["timestamp"]
            out.append(rec)
        token = r.get("nextToken")
        if not token or (stop_after and len(out) >= stop_after):
            break
    out.sort(key=lambda x: x["@timestamp"])
    return out, pages, bool(token)


def query_logs(ev):
    limit = min(int(ev.get("limit", 50)), 200)
    flt = ev.get("filter")
    if flt and not re.fullmatch(r"[\w .:=\-/@]{1,100}", flt):
        raise ValueError("filter may contain only word chars, space and . : = - / @")
    pattern = '"' + flt + '"' if flt else None
    rows, pages, more = _events(ev["service"], ev["start"], ev["end"], pattern, stop_after=limit)
    keep = ("ts", "level", "msg", "service", "commit", "caller", "template_id", "error_code", "trace_id")
    lines = [{k: r[k] for k in keep if k in r} for r in rows[:limit]]
    return envelope(f"cloudwatch:/dezerv/{ev['service']}", f"filter={flt!r} {ev['start']}..{ev['end']} limit={limit}",
                    {"count": len(lines), "truncated": more or len(rows) > limit, "lines": lines})


def get_log_patterns(ev):
    rows, pages, more = _events(ev["service"], ev["start"], ev["end"], "?ERROR ?WARN")
    rows = [r for r in rows if r.get("level") in ("ERROR", "WARN")]
    groups = {}
    for r in rows:
        k = (r.get("template_id"), r.get("level"), r.get("caller"), r.get("commit"))
        g = groups.setdefault(k, {"n": 0, "first_seen": r.get("ts"), "last_seen": r.get("ts"), "example": r.get("msg")})
        g["n"] += 1
        g["last_seen"] = r.get("ts")
    pats = [{"template_id": k[0], "level": k[1], "caller": k[2], "commit": k[3], **v} for k, v in groups.items()]
    pats.sort(key=lambda p: -p["n"])
    return envelope(f"cloudwatch:/dezerv/{ev['service']}", f"ERROR/WARN patterns {ev['start']}..{ev['end']}",
                    {"patterns": pats[:20], "events_scanned": len(rows), "truncated": more})


def lambda_handler(event, context):
    return dispatch(event, context, {"query_logs": query_logs, "get_log_patterns": get_log_patterns})
