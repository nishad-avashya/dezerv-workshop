"""Shared helpers copied into every tool Lambda at build time."""
import json
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist():
    return datetime.now(IST).isoformat(timespec="seconds")


def tool_name(context):
    """Gateway passes the tool as 'target___tool' in the client context (spike V-14)."""
    try:
        full = context.client_context.custom["bedrockAgentCoreToolName"]
    except Exception:
        return None
    return full.split("___", 1)[-1]


def envelope(source, query, data):
    return {"source": source, "query": query, "as_of": now_ist(), "data": data}


def error(msg, code="BAD_REQUEST"):
    return {"error": code, "message": msg, "as_of": now_ist()}


def parse_ist(s):
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=IST)


def dispatch(event, context, table):
    name = tool_name(context) or (event or {}).get("_tool")
    fn = table.get(name)
    if not fn:
        return error(f"unknown tool {name!r}", "UNKNOWN_TOOL")
    try:
        return fn(event or {})
    except ValueError as e:
        return error(str(e))
    except Exception as e:  # surface AWS/service errors as structured tool errors, not Lambda crashes
        import traceback; traceback.print_exc()
        return error(f"{type(e).__name__}: {e}", "TOOL_ERROR")
