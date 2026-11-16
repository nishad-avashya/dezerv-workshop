# Part 3: A Go Lambda as a governed tool

!!! time "10 minutes"

## What you'll learn
- Put a Go function behind the AgentCore Gateway as an MCP tool: a Lambda target on `provided.al2023`, arm64.
- Learn the Gateway-to-Lambda contract. The tool name arrives in the Lambda **client context**, and the arguments
  arrive as the event.
- Let the factory derive the Cedar rules for a custom tool from its `tools.json`, so you write no policy by hand.
- See why a mutating tool is hidden from `tools/list` and denied even if it is called.

## Concepts

Parts 1 and 2 used only the built-in connectors. Squads will have their own data, so here you add your own tool,
written in Go, with **one line** in the manifest.

`tools/mandates-go` is a Go Lambda with two tools:

- `get_mandate_status(user_id)` returns the user's UPI AutoPay mandate state (`ACTIVE`, `PAUSED`, `REVOKED`,
  `EXPIRED` or `PENDING_BANK`). It reads `mongo/mandates.json` from the data bucket in S3, and the VPA and bank
  account number come back masked.
- `revoke_mandate(user_id)` is a **decoy**. It never changes anything, and if it ever runs it writes a `CRITICAL`
  `WOULD_EXECUTE` line to its log. Policy must make sure it never runs.

![Go Lambda as a governed tool](../diagrams/lab-b-go-tool.drawio)

**The Gateway contract.** When the Gateway invokes a Lambda target, the tool name is in the client context as
`bedrockAgentCoreToolName`, in the form `<target>___<tool>` (for example `mandates___get_mandate_status`). The tool
arguments are the event JSON, and the handler returns JSON:

```go title="tools/mandates-go/main.go (excerpt)"
func handler(ctx context.Context, args map[string]any) (map[string]any, error) {
	name := ""
	if lc, ok := lambdacontext.FromContext(ctx); ok {
		name = lc.ClientContext.Custom["bedrockAgentCoreToolName"]
	}
	if name == "" { // fallback for local invocation: tool name inside the payload
		name, _ = args["_tool"].(string)
	}
	return dispatch(ctx, &s3Store{bucket: os.Getenv("DATA_BUCKET")}, name, args), nil
}
```

`dispatch` strips the `mandates___` prefix and switches on the tool name. An unknown name returns `UNKNOWN_TOOL`.

**Built with no Docker.** `make deploy-agent` cross-compiles the tool with
`GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go build -trimpath -tags lambda.norpc`, zips the binary as `bootstrap`, and
creates the Lambda `dezerv-laba-fx-payments-gw-mandates` on runtime `provided.al2023`, arm64. If there is no Go on the
machine, it uses `prebuilt/mandates-go-arm64.zip` instead and says so.

**Masking in two places.** The Gateway's RESPONSE interceptor (Lab A Part 3) already masks PII in every tool
response. The Go tool masks its own output as well (`mask.go`): `aarav42@okhdfc` becomes `***@okhdfc`, and an
account number keeps only its last four digits. That is defence in depth. The tool is safe even if someone ever calls
it outside the Gateway. The tool is also **read-only**. It only reads S3, and the one "mutation" it has is a no-op.

**Policy you don't write.** `tools/mandates-go/tools.json` declares the scope (`payments/mandates.read`) and marks
`revoke_mandate` as `"mutating": true`. From that, the factory renders:

- a **permit** for `mandates___get_mandate_status` when the token's scope contains `mandates.read`
  (`10-permit-reads.cedar`);
- an **explicit deny** for it when that scope is missing (`50-explicit-deny.cedar`), which the `support` persona
  doesn't have;
- a **forbid** for `mandates___revoke_mandate`, added to the CP-3 statement next to restart, scale and rollback
  (`30-forbid-mutations.cedar`).

**Why mutating tools are hidden.** With the policy engine attached, the Gateway filters `tools/list` by policy. A
tool that is forbidden for everyone doesn't appear, so a compliant agent never even sees `revoke_mandate`. If
something calls it anyway (a prompt injection, or a hand-written MCP call), Cedar denies the call before the Lambda
runs.

## Steps

### 1. Add the tool to the manifest

In `labs/B/agent.yaml`, replace the line `custom: []` with:

```yaml title="labs/B/agent.yaml (connectors section)"
  custom:
    - { name: mandates, type: lambda, runtime: go, path: tools/mandates-go }
```

!!! warning "Copy this exact shape"
    `custom` is a list of objects: one `-` and one `{ ... }` per tool. A nested list such as
    `- [{ name: mandates, ... }]` fails schema validation. The reference manifest is
    `labs/B/solutions/agent.part3.yaml`.

- `name` becomes the Gateway target, so the tools are `mandates___get_mandate_status` and `mandates___revoke_mandate`.
  It must be lowercase letters and digits, and it can't reuse a built-in target name.
- `runtime: go` and `path` tell the deployer what to build and where the code is. The renderer reads
  `<path>/tools.json` for the tool schemas and scope.

### 2. Re-render

```bash
make new-agent NAME=payments-gw FROM=labs/B/agent.yaml
```

??? example "Expected output"
    ```text
    rendered agents/payments-gw from manifest@87b535eca4: 10-permit-reads.cedar, 20-permit-ticket-writes.cedar, 30-forbid-mutations.cedar, 40-forbid-unbounded.cedar, 50-explicit-deny.cedar, 60-zones.cedar
    ```
    The sha is `87b535eca4` if your file is identical to `labs/B/solutions/agent.part3.yaml`. Any difference, even
    whitespace, gives a different sha, and that's fine.

Look at what changed. `gateway/targets.json` has a seventh target, `mandates`, with
`"lambda": "${CUSTOM_LAMBDA:mandates}"` and `"build": {"runtime": "go", "path": "tools/mandates-go"}`. The Cedar
grew from 15 to 17 statements, and one statement got longer:

```cedar title="agents/payments-gw/policy/10-permit-reads.cedar (new statement)"
permit(
  principal is AgentCore::OAuthUser,
  action in [
    AgentCore::Action::"mandates___get_mandate_status"
  ],
  resource == AgentCore::Gateway::"{{GATEWAY_ARN}}"
)
when {
  principal.hasTag("scope") && principal.getTag("scope") like "*mandates.read*"
};
```

```cedar title="agents/payments-gw/policy/30-forbid-mutations.cedar"
forbid(
  principal,
  action in [
    AgentCore::Action::"ops___restart_service",
    AgentCore::Action::"ops___scale_service",
    AgentCore::Action::"ops___rollback_deploy",
    AgentCore::Action::"mandates___revoke_mandate"
  ],
  resource == AgentCore::Gateway::"{{GATEWAY_ARN}}"
);
```

### 3. Deploy

```bash
make deploy-agent NAME=payments-gw
```

This builds the Go binary, creates the Lambda, adds the Gateway target and applies the Cedar. It takes a few minutes.

??? example "Expected output (representative output, trimmed)"
    ```text
    [factory] created Lambda dezerv-laba-fx-payments-gw-mandates
    [factory] gateway ready with targets ['changes', 'db', 'logs', 'mandates', 'ops', 'tickets', 'warehouse']
    [factory] detaching engine while policies are applied (brief window without enforcement)
    [factory] 17 Cedar policies ACTIVE
    [factory] policy engine attached (ENFORCE) and interceptor attached
    [factory] runtime READY: arn:aws:bedrock-agentcore:us-west-2:<account>:runtime/fx_payments_gw-...
    [factory] done. state in agents/payments-gw/.state.json
    ```
    Without Go there is an extra first line: `[factory] Go not found: using prebuilt/mandates-go-arm64.zip`.
    On a second deploy, `created Lambda` becomes `updated Lambda`.

### 4. Ask the agent

Terminal 1, as in Part 2:

```bash
make run-forwarder NAME=payments-gw
```

Terminal 2, from the repo root. The forwarder hands the JSON to the agent as an alert, so the question goes in `summary`:

```bash
curl -X POST localhost:8090/alert -d '{"alert":"MandateQuestion","service":"payments-gw","window_start":"2026-01-01T00:00:00+05:30","summary":"Is user U-1042 SIP failing because of their mandate or because of the PSP?"}'
```

??? example "Expected answer (representative output)"
    ```text
    ## Summary
    U-1042's UPI AutoPay mandate is ACTIVE (mandates___get_mandate_status), so the mandate is not the cause.
    Their two failed SIP debits both have error code E_PSP_TIMEOUT: the PSP timed out ...
    ## Evidence
    - mandate state ACTIVE, VPA ***@okhdfc, account XXXX....<last 4> (masked by the tool)
    - 2 transactions for U-1042 with E_PSP_TIMEOUT ...
    ```
    What matters is that the mandate is **ACTIVE** (from the Go tool) and there are **two `E_PSP_TIMEOUT` failures**,
    so the cause is the **PSP**. The data is synthetic. U-1042's two failures are part of the 340 from the Lab A
    incident, and match ticket PAY-1287 ("My SIP failed twice").

## Verify
```bash
make verify-labB-part3
```
!!! success "You should see"
    ```text
    PASS  mandates___get_mandate_status is in tools/list
    PASS  decoy mandates___revoke_mandate is hidden by policy
    PASS  direct MCP call returns a masked VPA and account
    PASS  decoy revoke is denied
    PASS  support persona cannot read mandates
    PASS  agent trace shows the Go tool being called (last 6 h)

    RESULT: PASS
    ```
    The last check looks in `/dezerv/agent-audit` for a `before_tool_call` on `mandates___get_mandate_status` by
    `payments-gw-oncall`. If it fails, ask the agent the question in step 4 first.

## What just happened
- One manifest line produced a Lambda, a Gateway target and three Cedar changes (a permit, an explicit deny and a
  forbid), all derived from `tools/mandates-go/tools.json`.
- The Gateway passed the tool name to Go in the client context (`bedrockAgentCoreToolName`) and the arguments as
  the event.
- The `oncall` token has `payments/mandates.read`, so it can read mandates. `support` doesn't, so it is denied.
  Nobody can call `revoke_mandate`, and nobody even sees it in `tools/list`.
- PII is masked twice, once in the Go tool and again by the Gateway's response interceptor.

!!! tip "Behind?"
    `make solution-labB-part3` copies `labs/B/solutions/agent.part3.yaml` over `labs/B/agent.yaml`, re-renders and
    deploys. It also runs the Part 1 and Part 2 solutions first. Without Go it uses the prebuilt Lambda zip.

## Troubleshooting
| Symptom | Fix |
|---|---|
| `INVALID agent.yaml: connectors.custom.0: ... is not of type 'object'` | You used a nested list. Use `- { name: mandates, ... }` as in step 1 |
| `[factory] Go not found: using prebuilt/mandates-go-arm64.zip` | Expected without Go. The prebuilt zip is the same code |
| `Go is not installed and there is no prebuilt zip: run make go-setup` | The `prebuilt/` folder is missing from your checkout. `git pull` or `make go-setup` |
| Agent never calls the mandates tool | Check `make verify-labB-part3`. If the tool is not in `tools/list`, you didn't re-render or re-deploy |

!!! question "Discuss"
    The Go tool masks its own output, and the Gateway masks it again. Which of Dezerv's services would you trust to
    rely on the interceptor alone? And for a tool that *must* mutate, what would you add on top of a Cedar permit:
    a human approval step, a narrower scope, or something else?
