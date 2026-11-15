# Lab B: Agent factory and Go (30 min; 40 with a stretch)

Lab A built **one** agent by hand. Lab B turns it into a template driven by one file, `agent.yaml`, and connects it to a Go stack in both directions: a Go service **calls** the agent, and a Go function **is a tool** for the agent.

**Prerequisite:** Lab A is deployed: the Gateway, policy engine, memory and Runtime exist. Check with `make link-labA`, which should print `found gateway_id, policy_engine_id, memory_id, runtime_id`. Behind? `make solution-part6` (about 10 minutes; it does not run the eval). `make verify-labA-part6` also needs the baseline eval (`make eval`, about 12 minutes), which Lab B does not need.
**Second editor?** The Build-with-Skills editor is a separate machine in the same account. Clone the repo, then run `make link-labA`: it rebuilds `.env` from the existing stack. Nothing is redeployed. Set `EXPECT_ACCOUNT` first.
**Go:** `go version`. If missing: `make go-setup`. If you cannot install Go: `make go-prebuilt` (forwarder) and the factory uses the prebuilt Lambda zip automatically.

## The idea in one picture
```
labs/B/agent.yaml  +  labs/B/charter.md
        |  make new-agent   (validate -> render, deterministic)
        v
agents/payments-gw/   prompt/  gateway/targets.json  policy/*.cedar  memory/  evals/gates.json     <- generated, do not edit
        |  make deploy-agent NAME=payments-gw
        v
Gateway fx-payments-gw + policy engine + memory + Runtime  (beside Lab A's, prefix fx-)
```
You edit the manifest; the renderer generates. Every generated file starts with `generated from agent.yaml@<sha> - edit the manifest, not this file`.

## Part 1: the factory (8 min)
Ask Claude: *"Use the Dezerv factory to create an agent for payments-gw from agent.yaml."* It runs:
```
make new-agent NAME=payments-gw FROM=labs/B/agent.yaml
make deploy-agent NAME=payments-gw
make verify-labB-part1
```
- `deploy-agent` takes about 3 minutes.
Compare `agents/payments-gw/policy/` with Lab A's `policy/cedar/`: every Lab A statement is there. The extra file `60-zones.cedar` comes from the manifest (services the connectors do not list are out of bounds).
Try breaking the manifest: set `autonomy: L2`, add a wildcard zone, set `forbid_ops: false`. The renderer refuses, with the reason. Fail closed.

## Part 2: a Go service calls the agent (10 min)
`go/alert-forwarder` is a small Go HTTP handler shaped like a Dezerv service. It receives an alert webhook and calls the deployed agent with `InvokeAgentRuntime`, one session per alert fingerprint, logging JSON with `commit` and `caller` fields (the same fields as Lab A's logs).
Use **two terminals**. Terminal 1 starts the forwarder and stays busy; terminal 2 sends the alert.

Terminal 1:
```
make run-forwarder NAME=payments-gw
```
- It prints the exact `curl` for terminal 2, then listens on `:8090`.

Terminal 2:
```
cd <repo root>
curl -X POST localhost:8090/alert -d @data/alerts/inc-sip-timeout.json
```
- Run it from the repo root, because the `@data/...` path is relative to it.
- The diagnosis prints in terminal 1 and takes 1-2 minutes.

Then verify:
```
make verify-labB-part2
```
- Run it after the diagnosis appeared. It starts its own forwarder on `:8098`.

Notes:
- `make` finds Go by itself. Only if you type `go` by hand in a **new terminal** do you need it on your PATH: `export PATH=$HOME/.local/go/bin:$PATH` (once per terminal), or save it for good with `echo 'export PATH=$HOME/.local/go/bin:$PATH' >> ~/.bashrc`.
- The port is 8090 because the workshop editor uses 8080. Pick another with `make run-forwarder NAME=payments-gw PORT=9000` (and use it in the `curl`).
- No Go? `make go-prebuilt` once; `make run-forwarder` then uses the prebuilt binary.

Read `go/alert-forwarder/README.md` for how this maps to production (event intake, and the fail-safe: if the agent cannot be reached, a human is still paged).

## Part 3: Go is a tool (10 min)
- Parts 1 and 2 used the built-in connectors. Here you add your own tool, written in Go, with one line in the manifest.
- `tools/mandates-go` is a Go Lambda with two tools:
  - `get_mandate_status(user_id)`: returns the user's UPI AutoPay mandate state (ACTIVE, PAUSED, REVOKED, EXPIRED or PENDING_BANK), with the VPA and account number masked.
  - `revoke_mandate(user_id)`: a decoy that does nothing. Policy must forbid it.

**Add it to the manifest**
- In `labs/B/agent.yaml`, replace `custom: []` with:
```yaml
  custom:
    - [{ name: mandates, type: lambda, runtime: go, path: tools/mandates-go }]
```
- `name` becomes the Gateway target, so the tools are called `mandates___get_mandate_status` and so on.
- `runtime: go` and `path` tell the factory what to build and where the code is.

**Render and deploy**
- Run:
```
make new-agent NAME=payments-gw FROM=labs/B/agent.yaml
make deploy-agent NAME=payments-gw
```
- `new-agent` re-renders `agents/payments-gw/` with the new target and its Cedar rules.
- `deploy-agent` builds the Go binary, creates the Lambda, adds the Gateway target and applies the Cedar (a few minutes).

**Ask the agent**
- Terminal 1: `make run-forwarder NAME=payments-gw`, as in Part 2.
- Terminal 2, from the repo root:
```
curl -X POST localhost:8090/alert -d '{"alert":"MandateQuestion","service":"payments-gw","window_start":"2026-01-01T00:00:00+05:30","summary":"Is user U-1042 SIP failing because of their mandate or because of the PSP?"}'
```
- The forwarder hands the JSON to the agent as an alert, so the question goes in `summary`.
- Expected answer: the mandate is ACTIVE (from the Go tool) and there are two `E_PSP_TIMEOUT` failures, so the cause is the PSP.

**Verify**
- Run:
```
make verify-labB-part3
```
- It checks that `get_mandate_status` is listed, `revoke_mandate` is hidden and denied, the `support` persona cannot read mandates, and the audit log shows the agent calling the Go tool.

**What you did not write**
- No Cedar, no Gateway target, no scope. The factory derived them from the tool's `tools.json`:
  - a read permit for `payments/mandates.read`
  - an explicit deny when that scope is missing
  - a forbid for the decoy `revoke_mandate`

## Part 4: policy follows the manifest (2 min)
Add a forbidden zone and re-render:
```yaml
  forbidden_zones: [service:ledger-svc]
```
- A zone can also be `<target>.<tool>`, for example `tickets.add_comment`.
`make new-agent ...` then look at `agents/payments-gw/policy/60-zones.cedar`; deploy to enforce it. `make verify-labB-part4`.

**Render and deploy**

- Run:

```
make new-agent NAME=payments-gw FROM=labs/B/agent.yaml
make deploy-agent NAME=payments-gw
```

- `new-agent` re-renders `agents/payments-gw/` with the new target and its Cedar rules.
- `deploy-agent` builds the Go binary, creates the Lambda, adds the Gateway target and applies the Cedar (a few minutes).

## Stretch (not built)
S1 a Harness variant of the same agent; S2 a Go MCP server on Runtime. See `INSTRUCTOR.md`.

## Ground rules
Never set `autonomy` above L1; never turn `forbid_ops` off. The workshop schema refuses both.
