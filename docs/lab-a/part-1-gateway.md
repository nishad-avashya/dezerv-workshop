# Part 1: Gateway and tools

!!! time "15 minutes"

## What you'll learn
- How an **AgentCore Gateway** turns Lambda functions into MCP tools behind a single endpoint.
- How tool names are formed (`<target>___<tool>`) and why that name is what policy will match on later.
- How the Gateway authenticates callers with a **Cognito JWT** (inbound identity).
- Why "the agent can reach the tools" is not the same as "the agent is governed": nothing blocks a mutation yet.

## Concepts

Dezerv's on-call data lives in many places: service logs in CloudWatch, transactions in MongoDB, history in Snowflake,
deploys in CI, tickets in Jira. Wiring each into each agent would give every squad its own credentials, its own
client code and its own idea of "read-only". An **AgentCore Gateway** gives the agent **one MCP endpoint** instead.
Behind it sit **targets**; here every target is an AWS Lambda function with an inline JSON tool schema
(`tools/schemas.py`). The agent sees standard MCP: `tools/list` to discover tools and `tools/call` to call them.

The Gateway names every tool `<target>___<tool>` (three underscores). The `db` target's `find_transactions` tool
becomes `db___find_transactions`. The same name reaches the Lambda in its client context
(`bedrockAgentCoreToolName`), and in Part 2 it becomes the Cedar **action**. Six targets, fourteen tools:

| Target | Tools | Backed by (all synthetic) |
|---|---|---|
| `logs` | `query_logs`, `get_log_patterns` | CloudWatch `FilterLogEvents` on `/dezerv/<service>`; windows of at most 6 h |
| `db` | `find_transactions`, `get_user_state`, `get_error_code` | mock MongoDB over S3 JSON; `$where` and write operators rejected; `limit` at most 200, `total_matching` in the reply |
| `warehouse` | `query_history` | mock Snowflake (DuckDB over S3 CSVs); a single SELECT, 200 rows max |
| `changes` | `get_recent_deploys` | `deploys.json` |
| `tickets` | `search_tickets`, `get_ticket`, `create_ticket`, `add_comment` | mock Jira in DynamoDB, project PAY only |
| `ops` (decoy) | `restart_service`, `scale_service`, `rollback_deploy` | no-ops that log `WOULD_EXECUTE` if they ever run |

Every tool reply carries `source`, `query` and `as_of`, so the agent can cite where each fact came from.

**Inbound auth.** The Gateway uses a `CUSTOM_JWT` authorizer pointed at the Cognito user pool's discovery URL and
accepts tokens from two app clients only: `oncall` and `support`. The agent gets a client-credentials token and sends
it as `Authorization: Bearer <jwt>` on every MCP request. The token's `scope` claim says what the persona may do,
but **in Part 1 nothing reads the scopes yet**: any authenticated caller may call any tool, including the decoy
`ops___restart_service`. That gap is what Part 2 closes.

![Life of one tool call](../diagrams/lab-a-tool-call-flow.drawio)

The diagram shows the full path you will have by the end of Part 3. Right now only steps 1 (validate the JWT) and
4 (run the Lambda) exist.

## Steps

### 1. Create the Gateway and its six targets
`make gateway` creates the Gateway `dezerv-laba-gw`, adds one Lambda target per data source, and waits until the
Gateway and every target are `READY`. It is idempotent: re-running it updates the targets.
```bash
make gateway
```
??? example "Expected output (representative)"
    ```text
    [labA] creating Gateway ...
    [labA] adding target logs (2 tools)
    [labA] adding target db (3 tools)
    [labA] adding target warehouse (1 tools)
    [labA] adding target changes (1 tools)
    [labA] adding target tickets (4 tools)
    [labA] adding target ops (3 tools)
    [labA] gateway ready: https://<gateway-id>.gateway.bedrock-agentcore.us-west-2.amazonaws.com/mcp
    ```

### 2. List the tools the agent will see
`scripts/mcp_cli.py` is a tiny MCP client that talks to the Gateway directly with a persona's token.
```bash
uv run --python 3.12 python scripts/mcp_cli.py list
```
??? example "Expected output (representative)"
    ```text
    14 tools
      changes___get_recent_deploys
      db___find_transactions
      db___get_error_code
      db___get_user_state
      logs___get_log_patterns
      logs___query_logs
      ops___restart_service
      ...
    ```

### 3. Run the agent on the incident
`make run-incident` starts the Strands agent locally (Claude Sonnet 4.6 on Bedrock) with the `oncall` token and sends
it the alert from `data/alerts/inc-sip-timeout.json`. The prompt (`agent/prompt/role.md`) gives it a workflow:
intake, triage, evidence, hypotheses, recommend, ticket. One run takes a minute or two (about 67k tokens).
```bash
make run-incident
```
??? example "Expected output (representative, trimmed)"
    ```text
    (no memory configured)

    [session sess-1a2b3c4d5e]
    ## Summary
    SIP debit failures on payments-gw from 10:40 IST are caused by deploy v2.14.3 (commit a1f9c3e), which lowered
    the PSP client timeout at psp/client.go:88 from 8s to 2s. 340 UPI AutoPay transactions failed with E_PSP_TIMEOUT ...
    ## Timeline
    ## Evidence
    ## Hypotheses tried
    ## Recommended next step (needs human approval)
    Roll back payments-gw to v2.14.2 ... requires human approval. Ticket PAY-... created.
    ```
    `(no memory configured)` is expected until Part 5.

Look for: root cause `v2.14.3` / `a1f9c3e` / `psp/client.go:88`, impact of about 340 transactions, a PAY ticket, and
a rollback **recommendation** (not an action).

### 4. Show the problem: nothing stops a restart
Call the decoy restart tool directly, as the `oncall` persona, with no policy in place:
```bash
uv run --python 3.12 python scripts/mcp_cli.py call ops___restart_service '{"service":"payments-gw"}'
```
??? example "Expected output (representative)"
    ```text
    OK
    {
     "source": "ops-decoy",
     "query": "restart_service",
     "as_of": "2026-11-16T11:05:12+05:30",
     "data": {
      "executed": false,
      "note": "no-op decoy"
     }
    }
    ```
It **succeeds**. The decoy does nothing, but it also writes a `WOULD_EXECUTE` line to `/aws/lambda/dezerv-laba-ops`:
had this been a real restart tool, a prompt injection would have been one tool call away from production.

!!! warning "This call only works before Part 2"
    Once `make policy` has attached Cedar, the same command prints `ERROR` and a JSON-RPC error `-32002`
    ("Tool Execution Denied ... denied due to P30_forbid_mutations_1"), and `mcp_cli.py list` no longer shows the
    three `ops___*` tools at all. If you are already past Part 2, that is the result you should see.
    The `WOULD_EXECUTE` line written now does not affect later checks: `make verify-labA-part3` only counts lines
    written during its own run.

## Verify
```bash
make verify-labA-part1
```
!!! success "You should see"
    ```text
    PASS  gateway exposes >= 12 tools across its targets (found 14)
    PASS  tools/list matches (found 14, expected 14)
    PASS  incident run mentions v2.14.3 or a1f9c3e

    RESULT: PASS
    ```
    The verify runs the agent once more, so it takes a minute or two. If you have already attached policy, the second
    line reads `found 11, expected 11 = ops tools hidden by policy`, which is also a pass.

## What just happened
- One Gateway (`dezerv-laba-gw`) now fronts six Lambda targets and 14 tools; the agent only knows one MCP URL.
- Tool names are `<target>___<tool>`; that string is what Cedar will match in Part 2.
- The Gateway checked the Cognito JWT on every call, so only the `oncall` and `support` clients get in.
- Authentication is not authorization: an authenticated caller could still call `ops___restart_service`.

!!! question "Discuss"
    The model correctly *recommended* a rollback and did not attempt one. Why is that not good enough for Dezerv?
    What would happen with a weaker model, a different prompt, or the injected ticket you will meet in Part 3?

!!! tip "Behind?"
    `make solution-part1` brings you to the end of this part (it runs `bootstrap` and `gateway`).

## Troubleshooting
- **Gateway 5xx right after create:** the targets were not READY yet. `make gateway` waits for READY; re-run it.
- **Agent cites no logs:** usually a stale `.env` (wrong `LAB_ANCHOR`). Re-run `make bootstrap` on the day.
- **`RATE_LIMITED`** does not apply yet (no interceptor); it appears from Part 3.
