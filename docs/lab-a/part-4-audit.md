# Part 4: Audit hooks

!!! time "8 minutes"

## What you'll learn
- How **Strands hooks** observe the agent's lifecycle without touching its prompt or tools.
- What one audit record contains, and how the Gateway's decision (allowed, denied and why) ends up in it.
- Where the **session id** comes from and how to pull every record for one run from CloudWatch.

## Concepts

When an agent touches production data, "what did it do, and was it allowed?" needs an answer you can query, not a
chat transcript. The agent registers a `HookProvider`, `AuditHooks` in `agent/audit_hooks.py`, on four Strands
lifecycle events and writes **one JSON line per event** to the CloudWatch log group `/dezerv/agent-audit`:

| Event | Fired by Strands | Extra fields |
|---|---|---|
| `before_invocation` | `BeforeInvocationEvent` | `tool: null`, `tokens: 0` |
| `before_tool_call` | `BeforeToolCallEvent` | `tool`, `input_masked` |
| `after_tool_call` | `AfterToolCallEvent` | `tool`, `input_masked`, `output_sha256`, `latency_ms`, `decision` |
| `after_invocation` | `AfterInvocationEvent` | `tool: null`, `tokens` used by the run |

Every record also carries `ts`, `agent_id` (`payments-gw-oncall`), `session_id`, `task_id`, `principal` (the `sub` of
the persona's JWT), `event` and `trace_id`. Tool inputs are masked with the same detectors as the Gateway
interceptor, and the output is stored only as a SHA-256 hash, so the audit log never becomes a second copy of the data.

The `decision` field is derived from the tool result the Gateway returned. If the call failed and the text contains a
denial marker (`Tool Execution Denied`, `RATE_LIMITED`, `CHANGE_FREEZE`, ...), the hook records
`"result": "denied"` and extracts the reason: `RATE_LIMITED`, `CHANGE_FREEZE`, or the Cedar policy name from
`denied due to P30_forbid_mutations_1`. So the agent's audit trail carries the Gateway's verdict without the agent
having to trust its own account of events.

**Session ids.** A local run (`make run-incident`) makes a new id `sess-<10 hex characters>` in `agent/main.py`
(or uses `--session` if you pass one) and prints it at the end of the run as `[session sess-...]`. On AgentCore
Runtime (Part 6) the id is the Runtime session id; the eval runner uses `eval-<hex>`. Each run writes to its own log
stream named `<session_id>-<6 hex characters>`. For a local run `task_id` equals the session id; the eval sets it to
the replay case id.

!!! note "The hooks are already on"
    The hooks have been registered since Part 1 (`agent/main.py` always adds `AuditHooks` and the `StepLimits` hook,
    which stops a run after 25 tool calls or 300k tokens with an escalation summary). Every run so far has been audited.
    This part is about reading the trail, not switching it on.

## Steps

### 1. Run the incident and note the session id
```bash
make run-incident
```
The first line of the answer block is the session id, for example `[session sess-1a2b3c4d5e]`.

### 2. Read the trail for that session
Pick whichever is easiest:

=== "CloudWatch console"
    Open CloudWatch > Log groups > `/dezerv/agent-audit`. The newest stream starts with your session id.

=== "Logs Insights"
    Paste the query from `labs/A/audit-by-session.txt` and replace `REPLACE_ME` with your session id:
    ```text
    fields @timestamp, event, tool, decision.result as decision, decision.reason as reason, latency_ms, tokens
    | filter session_id = 'REPLACE_ME'
    | sort @timestamp asc
    ```
    Logs Insights can lag a few minutes behind fresh events. If the result is empty, use the console or the CLI.

=== "AWS CLI (read-only)"
    The same filter the eval runner uses:
    ```bash
    aws logs filter-log-events --region us-west-2 --log-group-name /dezerv/agent-audit \
      --filter-pattern '{ $.session_id = "sess-1a2b3c4d5e" }' --query 'events[].message' --output text
    ```

??? example "A sample `after_tool_call` record (representative)"
    ```json
    {
      "ts": "2026-11-16T05:41:07.512345+00:00",
      "agent_id": "payments-gw-oncall",
      "session_id": "sess-1a2b3c4d5e",
      "task_id": "sess-1a2b3c4d5e",
      "principal": "<oncall client id>",
      "event": "after_tool_call",
      "trace_id": "9f2c4b1e0d7a4c3b8e6f5a4d3c2b1a09",
      "tool": "db___find_transactions",
      "input_masked": {"filter": {"error_code": "E_PSP_TIMEOUT"}, "limit": 50},
      "output_sha256": "3b7e...c41a",
      "latency_ms": 812,
      "decision": {"result": "allowed", "reason": null}
    }
    ```
    A denied call looks the same with `"decision": {"result": "denied", "reason": "P30_forbid_mutations_1"}`.
    `trace_id` is random here: there is no OpenTelemetry span in the local process.

Walk the trail top to bottom: `before_invocation`, then a `before_tool_call` / `after_tool_call` pair per tool in the
order of the workflow (log patterns, failure rate, transactions, deploys, ticket), then `after_invocation` with the
token count.

!!! info "Why you will rarely see a denial here"
    Cedar hides forbidden tools from `tools/list`, so a well-behaved agent never *calls* `ops___restart_service` and
    no denial shows up in its trail. To see one, look for `RATE_LIMITED` after `make verify-labA-part3`, or remember the
    capstone's `make prove-denial`, which deliberately calls a visible tool with a forbidden argument.

## Verify
```bash
make verify-labA-part4
```
!!! success "You should see"
    ```text
    PASS  last session has before+after for each tool call (12/12)
    PASS  every after_tool_call has a decision
    PASS  records carry the TLA-07 minimum fields

    RESULT: PASS
    ```
    (Representative: the tool-call count varies by run.) The verify reads the most recently written stream in
    `/dezerv/agent-audit`, so run it straight after `make run-incident`.

## What just happened
- `AuditHooks` subscribes to four Strands lifecycle events and writes one JSON line each to `/dezerv/agent-audit`.
- Inputs are masked and outputs hashed, so the audit log carries no PII.
- `decision.result` and `decision.reason` carry the Gateway's verdict, including the Cedar policy name.
- The session id ties every record of one run together; the eval in Part 6 uses exactly this to score tool trajectories.

!!! question "Discuss"
    The agent writes its own audit trail. Why is that acceptable here, and what would you add for a regulator?
    (Hint: the interceptor writes an independent line per call to `/dezerv/gateway-audit`, outside the agent's control.)

!!! tip "Behind?"
    `make solution-part4` brings you to the end of this part. The hooks need no setup; it runs everything up to
    Part 3 and then reminds you to run `make run-incident` and `make verify-labA-part4`.
