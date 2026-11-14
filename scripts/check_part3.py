"""Part 3 acceptance: masking, tagging, freeze, rate limit."""
import json, re, sys, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import mcpc, boto3

REGION = mcpc.load_env().get("AWS_REGION", "us-west-2")
ssm = boto3.client("ssm", region_name=REGION)
fails = 0
def check(label, ok, detail=""):
    global fails
    fails += (not ok)
    print(("PASS " if ok else "FAIL ") + label + (f"   | {detail}" if detail else ""))

PII = [r"\b9999\d{8}\b", r"\b[A-Z]{5}\d{4}[A-Z]\b", r"9000 ?0 ?0\d{4}", r"\b4111\d{12}\b", r"\b\w+@(okhdfc|okicici|oksbi|okaxis|ybl)\b", r"[\w.]+@example\.test", r"acct \d{9,}"]
err, out, _ = mcpc.call_tool("db___get_user_state", {"user_id": "U-1042"})
txt = json.dumps(out)
leaks = [p for p in PII if re.search(p, txt)]
check("get_user_state has no unmasked PII", not err and not leaks, f"leaks={leaks}")

err, out, _ = mcpc.call_tool("tickets___get_ticket", {"key": "PAY-1287"}, "support")
txt = json.dumps(out)
check("ticket text wrapped in <untrusted>", "<untrusted source=" in txt and "aarav42@okhdfc" not in txt)

ssm.put_parameter(Name="/dezerv/freeze", Value="on", Type="String", Overwrite=True); time.sleep(7)
try:
    err, out, _ = mcpc.call_tool("tickets___create_ticket", {"project": "PAY", "summary": "freeze test", "body": "x", "severity": "SEV4"}, "support")
    check("freeze on: create_ticket -> CHANGE_FREEZE", err and "CHANGE_FREEZE" in json.dumps(out), json.dumps(out)[:100])
    err, out, _ = mcpc.call_tool("changes___get_recent_deploys", {"service": "payments-gw"})
    check("freeze on: reads continue", not err)
finally:
    ssm.put_parameter(Name="/dezerv/freeze", Value="off", Type="String", Overwrite=True); time.sleep(7)
err, out, _ = mcpc.call_tool("tickets___create_ticket", {"project": "PAY", "summary": "post-freeze", "body": "x", "severity": "SEV4"}, "support")
check("freeze off: create_ticket works again", not err, json.dumps(out)[:80])

while time.gmtime().tm_sec > 20:      # fixed-window limiter: start early in the minute
    time.sleep(1)
tok = mcpc.token("oncall")
def one(_):
    e, o, _r = mcpc.call_tool("db___get_error_code", {"code": "E_PSP_TIMEOUT"}, "oncall")
    return e and "RATE_LIMITED" in json.dumps(o)
with ThreadPoolExecutor(12) as ex:
    limited = sum(ex.map(one, range(36)))
check("36 calls inside a minute -> some RATE_LIMITED", limited >= 1, f"rate-limited={limited}/36 (expect 6 when starting from an idle minute)")
sys.exit(1 if fails else 0)
