# Architecture

Every Dezerv lab uses the same shape: an agent that reaches every tool through **one AgentCore Gateway**, where
identity, interceptors and Cedar policy are enforced outside the model.

![Lab A architecture](diagrams/lab-a-architecture.drawio)

## The life of one tool call

1. **The agent** (Strands, Claude Sonnet 4.6) gets a client-credentials token from **Amazon Cognito**. The token's `scope` claim says what the persona may do: `oncall` can read logs, db, warehouse, changes and tickets and write tickets, while `support` can only read and write tickets.
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

| Resource | Name | Created by |
|---|---|---|
| CloudFormation stack | `DezervLabA` | `make bootstrap` |
| Tool and interceptor Lambdas | `dezerv-laba-{logs,db,warehouse,changes,tickets,ops,interceptor}` | stack |
| Cognito user pool | `dezerv-laba` (clients `oncall`, `support`) | stack |
| DynamoDB tables | `dezerv-tickets`, `dezerv-ratelimit` | stack |
| Log groups | `/dezerv/payments-gw`, `/dezerv/kyc-svc`, `/dezerv/agent-audit`, `/dezerv/gateway-audit` | stack |
| Gateway | `dezerv-laba-gw` | `make gateway` |
| Policy engine | `dezerv_laba_pe` | `make policy` |
| Memory | `dezerv_payments_oncall` | `make memory` |
| Agent Runtime | `dezerv_payments_oncall` | `make deploy-agent` |
| Factory agents | Gateway `fx-<product>`, engine `fx_<product>_pe`, memory and Runtime `fx_<product>` | `make deploy-agent NAME=<product>` |

[Clean up](reference/cleanup.md) removes all of them.
