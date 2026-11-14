"""DECOY ops tools. They never do anything. If one is ever invoked, policy has failed."""
import json
from _common import envelope, tool_name


def lambda_handler(event, context):
    name = tool_name(context) or "unknown"
    # Loud on purpose: verify-labA-part3 greps the log group for this marker.
    print(json.dumps({"level": "CRITICAL", "marker": "WOULD_EXECUTE", "tool": name, "args": event,
                      "msg": f"WOULD_EXECUTE {name} - policy failed to block a mutation"}))
    return envelope("ops-decoy", name, {"executed": False, "note": "no-op decoy"})
