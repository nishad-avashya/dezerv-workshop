import json, sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import mcpc
T, T_END = mcpc.at(0), mcpc.at(10)
cases = [
 ("oncall  ops___restart_service      -> DENY", "oncall", "ops___restart_service", {"service": "payments-gw"}, True),
 ("oncall  ops___rollback_deploy      -> DENY", "oncall", "ops___rollback_deploy", {"service": "payments-gw"}, True),
 ("support db___find_transactions     -> DENY", "support", "db___find_transactions", {"filter": {}, "limit": 5}, True),
 ("support logs___query_logs          -> DENY", "support", "logs___query_logs", {"service": "payments-gw", "start": T, "end": T_END}, True),
 ("oncall  db___find_transactions 500 -> DENY", "oncall", "db___find_transactions", {"filter": {}, "limit": 500}, True),
 ("oncall  db___find_transactions 5   -> ALLOW", "oncall", "db___find_transactions", {"filter": {"error_code": "E_PSP_TIMEOUT"}, "limit": 5}, False),
 ("oncall  changes___get_recent_deploys -> ALLOW", "oncall", "changes___get_recent_deploys", {"service": "payments-gw"}, False),
 ("support tickets___get_ticket       -> ALLOW", "support", "tickets___get_ticket", {"key": "PAY-1287"}, False),
 ("support tickets___create_ticket PAY -> ALLOW", "support", "tickets___create_ticket", {"project": "PAY", "summary": "policy test", "body": "x", "severity": "SEV4"}, False),
 ("support tickets___create_ticket OPS -> DENY", "support", "tickets___create_ticket", {"project": "OPS", "summary": "t", "body": "x", "severity": "SEV4"}, True),
]
bad = 0
for label, persona, tool, args, want_deny in cases:
    err, out, raw = mcpc.call_tool(tool, args, persona)
    ok = (err == want_deny)
    bad += not ok
    print(("PASS " if ok else "FAIL ") + label + "   |  " + (json.dumps(out)[:140] if err else "ok"))
sys.exit(1 if bad else 0)
