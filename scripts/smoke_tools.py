#!/usr/bin/env python3
"""Invoke each tool Lambda directly (as the Gateway would) and print a short result. Run before wiring the Gateway."""
import base64, json, sys, boto3
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import mcpc

lam = boto3.client("lambda", region_name="us-west-2")
TESTS = {
 "logs.get_log_patterns": ("logs", "get_log_patterns", {"service": "payments-gw", "start": mcpc.at(-10), "end": mcpc.at(40)}),
 "logs.query_logs": ("logs", "query_logs", {"service": "payments-gw", "start": mcpc.at(0), "end": mcpc.at(10), "filter": "psp", "limit": 2}),
 "db.find_transactions": ("db", "find_transactions", {"filter": {"error_code": "E_PSP_TIMEOUT", "created_at": {"$gte": mcpc.at(0)[:16]}}, "limit": 2}),
 "db.reject_$where": ("db", "find_transactions", {"filter": {"$where": "1==1"}}),
 "db.get_user_state": ("db", "get_user_state", {"user_id": "U-1042"}),
 "db.get_error_code": ("db", "get_error_code", {"code": "E_PSP_TIMEOUT"}),
 "warehouse.ok": ("warehouse", "query_history", {"sql": "select rail, failure_rate from daily_payment_stats order by stat_date desc limit 2"}),
 "warehouse.reject_drop": ("warehouse", "query_history", {"sql": "drop table daily_payment_stats"}),
 "warehouse.reject_cross": ("warehouse", "query_history", {"sql": "select * from query_logs cross join daily_payment_stats a cross join daily_payment_stats b"}),
 "changes.get_recent_deploys": ("changes", "get_recent_deploys", {"service": "payments-gw", "since": mcpc.at(-12 * 60)}),
 "tickets.get_ticket": ("tickets", "get_ticket", {"key": "PAY-1287"}),
 "tickets.reject_project": ("tickets", "create_ticket", {"project": "OPS", "summary": "x", "body": "y", "severity": "SEV3"}),
}
if "--decoy" in sys.argv:
    TESTS["ops.restart_service(decoy)"] = ("ops", "restart_service", {"service": "payments-gw"})
for label, (fn, tool, payload) in TESTS.items():
    cc = base64.b64encode(json.dumps({"custom": {"bedrockAgentCoreToolName": f"{fn}___{tool}"}}).encode()).decode()
    r = lam.invoke(FunctionName=f"dezerv-laba-{fn}", ClientContext=cc, Payload=json.dumps(payload).encode())
    out = r["Payload"].read().decode()
    flag = "FUNCTION_ERROR" if r.get("FunctionError") else "ok"
    print(f"--- {label} [{flag}]\n{out[:420]}")
