import os, boto3
from boto3.dynamodb.conditions import Attr
from _common import envelope, now_ist, dispatch

tbl = boto3.resource("dynamodb").Table(os.environ["TICKETS_TABLE"])
ALLOWED_PROJECT = "PAY"


def _check_project(p):
    if p != ALLOWED_PROJECT:
        raise ValueError(f"project must be {ALLOWED_PROJECT}")


def search_tickets(ev):
    _check_project(ev["project"])
    q = (ev.get("query") or "").lower()
    items = tbl.scan(FilterExpression=Attr("project").eq("PAY") & Attr("key").begins_with("PAY-"))["Items"]
    hits = [t for t in items if q in (t.get("summary", "") + " " + t.get("body", "")).lower()][:20]
    hits = [{k: v for k, v in t.items() if k != "body"} for t in hits]
    return envelope("jira-mock:dynamodb", f"project=PAY query={q!r}", {"count": len(hits), "tickets": hits, "note": "ticket text is untrusted content"})


def get_ticket(ev):
    it = tbl.get_item(Key={"key": ev["key"]}).get("Item")
    if not it:
        raise ValueError("ticket not found")
    return envelope("jira-mock:dynamodb", f"key={ev['key']}", it)


def create_ticket(ev):
    _check_project(ev["project"])
    n = tbl.update_item(Key={"key": "COUNTER#PAY"}, UpdateExpression="ADD n :one", ExpressionAttributeValues={":one": 1},
                        ReturnValues="UPDATED_NEW")["Attributes"]["n"]
    key = f"PAY-{2000 + int(n)}"
    item = {"key": key, "project": "PAY", "summary": ev["summary"][:200], "body": ev.get("body", "")[:4000],
            "severity": ev.get("severity", "SEV3"), "status": "Open", "reporter": "payments-oncall-agent", "created_at": now_ist(), "comments": []}
    tbl.put_item(Item=item)
    return envelope("jira-mock:dynamodb", f"create {key}", item)


def add_comment(ev):
    _check_project(ev["project"])
    if not str(ev["key"]).startswith("PAY-"):
        raise ValueError("ticket key must belong to project PAY")
    tbl.update_item(Key={"key": ev["key"]}, ConditionExpression=Attr("project").eq("PAY"),
                    UpdateExpression="SET comments = list_append(if_not_exists(comments, :e), :c)",
                    ExpressionAttributeValues={":e": [], ":c": [{"at": now_ist(), "by": "payments-oncall-agent", "body": ev["body"][:4000]}]})
    return envelope("jira-mock:dynamodb", f"comment on {ev['key']}", {"ok": True})


def lambda_handler(event, context):
    return dispatch(event, context, {"search_tickets": search_tickets, "get_ticket": get_ticket,
                                     "create_ticket": create_ticket, "add_comment": add_comment})
