# Architecture

Every Dezerv lab uses the same shape: an agent that reaches every tool through **one AgentCore Gateway**, where
identity, interceptors and Cedar policy are enforced outside the model.

![Lab A architecture](diagrams/lab-a-architecture.drawio)

## The life of one tool call

1. **The agent** (Strands, Claude Sonnet 4.6) gets a client-credentials token from **Amazon Cognito**. The token's `scope` claim says what the agent may do. There are two **personas**, which are just two different permission sets for the same agent: `oncall` can read logs, db, warehouse, changes and tickets and write tickets, while `support` can only read and write tickets.
2. It calls a tool over **MCP** with the token as a Bearer JWT. Tool names look like `<target>___<tool>`, for example `logs___query_logs`.
3. The **Gateway** validates the JWT against Cognito.
4. The **REQUEST interceptor** (a Lambda) enforces a rate limit of 30 calls a minute per principal and a change freeze (SSM parameter `/dezerv/freeze`), and writes a gateway audit line.
5. The **Cedar policy engine** (ENFORCE mode) decides permit or forbid. It denies by default, and `forbid` beats `permit`. Restart, scale and rollback are forbidden for everyone.
6. The **target Lambda** runs against synthetic data: mock MongoDB, CloudWatch Logs, mock Snowflake, deploys and mock Jira.
7. The **RESPONSE interceptor** masks PII (cards, Aadhaar, PAN, phone, email, bank account, UPI VPA) and wraps free text from tickets and logs in `<untrusted>` tags.
8. Back in the agent, **hooks** write an audit record for each lifecycle event, retrieve memory before each model call, and stop the run after 25 tool calls or when the token budget runs out.

!!! question "Ask the room"
    Why does the interceptor run *before* Cedar? (The rate limit and the freeze are cheap and apply to every call.
    Cedar decides *who may do what*.)

## What each lab adds

| Lab | Adds | AgentCore features |
|---|---|---|
| [Lab A](lab-a/index.md) | One hand-built governed agent for `payments-gw` | Gateway, Identity, Policy (Cedar), Gateway interceptors, Runtime, Memory, Evaluations |
| [Lab B](lab-b/index.md) | A factory: `agent.yaml` → prompt, targets, Cedar, memory, eval gates; Go caller and Go tool | Same features, driven by a manifest; Runtime invoked from `aws-sdk-go-v2`; Lambda (`provided.al2023`) target |
| [Capstone](capstone/index.md) | One agent per squad, for its own service, exported as a skeleton | Everything above, plus a forbidden-zone denial proven in the audit log |

## Resources in your account

Click the **+** next to each resource to see why it exists and what it holds in the Lab A and Lab B scenarios. Use that to map it to the service you want an agent for.

<div class="annotate" markdown>

| Resource | Name | Created by | What it is |
|---|---|---|---|
| CloudFormation stack | `DezervLabA` | `make bootstrap` | Bundles everything below (1) |
| Tool and interceptor Lambdas | `dezerv-laba-{logs,db,warehouse,changes,tickets,ops,interceptor}` | stack | Six tool Lambdas and the interceptor (2) |
| Cognito user pool | `dezerv-laba` (clients `oncall`, `support`) | stack | The two personas (3) |
| DynamoDB table | `dezerv-tickets` | stack | The mock Jira (4) |
| DynamoDB table | `dezerv-ratelimit` | stack | Rate-limit counters (5) |
| S3 bucket | `dezerv-laba-data-<account>-<region>` | stack | The synthetic data files (6) |
| SSM parameter | `/dezerv/freeze` | stack | The change-freeze switch (7) |
| Log group | `/dezerv/payments-gw` | stack | The Lab A incident logs (8) |
| Log group | `/dezerv/kyc-svc` | stack | The red-herring logs (9) |
| Log group | `/dezerv/agent-audit` | stack | The agent's audit trail (10) |
| Log group | `/dezerv/gateway-audit` | stack | The Gateway's audit trail (11) |
| Gateway | `dezerv-laba-gw` | `make gateway` | The one endpoint for all tools (12) |
| Policy engine | `dezerv_laba_pe` | `make policy` | The Cedar rules (13) |
| Memory | `dezerv_payments_oncall` | `make memory` | Past incidents and runbooks (14) |
| Agent Runtime | `dezerv_payments_oncall` | `make deploy-agent` | The deployed Lab A agent (15) |
| Factory agents | Gateway `fx-<product>`, engine `fx_<product>_pe`, memory and Runtime `fx_<product>` | `make deploy-agent NAME=<product>` | The Lab B and capstone agents (16) |

1. Groups everything marked "stack" below, so one command can remove it
2. Each is one tool the agent can call. Each stands in for a system your on-call already uses: `logs` for CloudWatch, `db` for the mock MongoDB (payments transactions, users, mandates, error codes), `warehouse` for the mock Snowflake (daily payment stats), `changes` for the deploy history (including the bad deploy `v2.14.3`), `tickets` for the mock Jira. `ops` is a decoy that restarts, scales or rolls back nothing: if it ever runs, the policy has failed. `interceptor` applies the rate limit, the freeze and PII masking. For your own service, you would want one tool per system your on-call looks at
3. The two personas, one sign-in each. `oncall` can read everything and file tickets, and `support` can only handle tickets. For your own service, one client per role that should get different access
4. The mock Jira. It holds the PAY tickets the agent reads and files, including the one with a planted prompt injection that tests whether the agent obeys text it reads. The capstone adds one more ticket per project
5. Counters only, no business data. The interceptor uses it to cap each caller at 30 calls a minute
6. The synthetic data files the tool Lambdas read: the mock MongoDB, Snowflake and Jira data, and the deploy history. Your capstone data goes here under `squads/<name>/data/`
7. The change-freeze switch (`on` or `off`). While it is on, the interceptor blocks the write tools (such as filing a ticket) and reads continue. For your own service, the switch an operator flips to stop the agent writing
8. The Lab A incident: error logs of the payments gateway, with the PSP timeouts (`E_PSP_TIMEOUT`) that start right after deploy `v2.14.3`
9. In Lab A, noisy logs from a second service that look suspicious but are not the cause (the red herring). The capstone `kyc-svc` profile writes its own incident logs here too
10. One record for each thing the agent does (each tool call and the Gateway's allowed or denied decision). This is where you prove a denial
11. One line per tool call the Gateway interceptor sees (allowed, or denied for rate limit or freeze), written before the policy decides
12. The single MCP endpoint that all 14 tools sit behind. Identity, the interceptor and Cedar are all enforced here, outside the model
13. The Cedar rules: reads are permitted by scope, restart, scale and rollback are forbidden for everyone, and forbidden zones such as `service:ledger-svc` are blocked
14. The agent's past: 26 incidents and 8 runbooks. On a PSP timeout it recalls `INC-2026-031` and `RB-PSP-TIMEOUT`. For your own service, your past incidents and runbooks
15. The deployed Lab A agent, the payments on-call, that investigates the incident
16. In Lab B, `payments-gw` rebuilt from `agent.yaml`, plus a Go tool for mandates. In the capstone, one per project, for example `kyc-svc`, with its own Gateway, policy, memory and Runtime. Its tools read your data instead of Lab A's

</div>

[Clean up](reference/cleanup.md) removes all of them.
