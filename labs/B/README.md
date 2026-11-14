# Lab B: Agent factory and Go (30 min; 40 with a stretch)

Lab A built **one** agent by hand. Lab B turns it into a template driven by one file, `agent.yaml`, and connects it to a Go stack in both directions: a Go service **calls** the agent, and a Go function **is a tool** for the agent.

**Prerequisite:** Lab A is deployed (`make verify-labA-part6` passes). Behind? `make solution-part6`.
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
make deploy-agent NAME=payments-gw      # about 3 min
make verify-labB-part1
```
Compare `agents/payments-gw/policy/` with Lab A's `policy/cedar/`: every Lab A statement is there. The extra file `60-zones.cedar` comes from the manifest (services the connectors do not list are out of bounds).
Try breaking the manifest: set `autonomy: L2`, add a wildcard zone, set `forbid_ops: false`. The renderer refuses, with the reason. Fail closed.

## Part 2: a Go service calls the agent (10 min)
`go/alert-forwarder` is a small Go HTTP handler shaped like a Dezerv service. It receives an alert webhook and calls the deployed agent with `InvokeAgentRuntime`, one session per alert fingerprint, logging JSON with `commit` and `caller` fields (the same fields as Lab A's logs).
```
make run-forwarder NAME=payments-gw            # terminal 1
curl -X POST localhost:8080/alert -d @data/alerts/inc-sip-timeout.json     # terminal 2; the diagnosis prints in terminal 1
make verify-labB-part2
```
Read `go/alert-forwarder/README.md` for how this maps to production (event intake, and the fail-safe: if the agent cannot be reached, a human is still paged).

## Part 3: Go is a tool (10 min)
`tools/mandates-go` is a Go Lambda with `get_mandate_status(user_id)` (UPI AutoPay mandate state) and a decoy `revoke_mandate`. Add it to the manifest:
```yaml
  custom:
    - { name: mandates, type: lambda, runtime: go, path: tools/mandates-go }
```
then `make new-agent NAME=payments-gw FROM=labs/B/agent.yaml && make deploy-agent NAME=payments-gw` (builds the Go binary, creates the Lambda, adds the Gateway target and the Cedar rules). Ask the agent:
*"Is user U-1042's SIP failing because of their mandate or because of the PSP?"*
Expected: mandate ACTIVE (from the Go tool), two `E_PSP_TIMEOUT` failures, so it is the PSP. `make verify-labB-part3`.
Notice what you did not write: no Cedar, no Gateway target, no scope. The factory derived them: read permit for `payments/mandates.read`, an explicit deny without it, and a forbid for the decoy `revoke_mandate`.

## Part 4: policy follows the manifest (2 min)
Add a forbidden zone and re-render:
```yaml
  forbidden_zones: [service:ledger-svc]       # or  <target>.<tool>, e.g. tickets.add_comment
```
`make new-agent ...` then look at `agents/payments-gw/policy/60-zones.cedar`; deploy to enforce it. `make verify-labB-part4`.

## Stretch (not built)
S1 a Harness variant of the same agent; S2 a Go MCP server on Runtime. See `INSTRUCTOR.md`.

## Ground rules
Never set `autonomy` above L1; never turn `forbid_ops` off. The workshop schema refuses both.
