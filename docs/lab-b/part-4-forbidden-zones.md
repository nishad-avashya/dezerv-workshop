# Part 4: Forbidden zones

!!! time "2 minutes"

## What you'll learn
- Declare a forbidden zone in the manifest and see it become Cedar `forbid` statements.
- Know what you can do next while building your own agent: test it, replay incidents, run evals.

## Concepts

The charter in `labs/B/charter.md` says under *Forbidden zones*: "`ledger-svc` internals (owned by the ledger team)".
In Lab A you turned that sentence into Cedar by hand. In Lab B you declare it once in `agent.yaml`, and the factory
writes the Cedar.

`policy.forbidden_zones` takes two kinds of entries. Wildcards are refused.

| Zone | Blocks |
|---|---|
| `service:<name>` | every tool with a `service` input (logs, deploys) when it is called for that service |
| `<target>.<tool>` | exactly that tool, for example `tickets.add_comment` |

## Steps

### 1. Add the zone

In `labs/B/agent.yaml`, change the `forbidden_zones` line under `policy:` to:

```yaml title="labs/B/agent.yaml (policy section)"
policy:
  forbid_ops: true
  freeze_param: /dezerv/freeze
  forbidden_zones: [service:ledger-svc]
```

The reference is `labs/B/solutions/agent.part4.yaml`. It keeps the Part 3 `mandates` tool, so keep yours in `custom`.

### 2. Re-render

```bash
make new-agent NAME=payments-gw FROM=labs/B/agent.yaml
```

The Cedar is written to `agents/payments-gw/policy/60-zones.cedar` (under the repo root). It now has 5 `forbid`
statements instead of 4. Check:

```bash
grep -n 'ledger-svc' agents/payments-gw/policy/60-zones.cedar
```

!!! note "Notes"
    - Each render deletes and rewrites every `*.cedar` file, so a missing file is recreated and a zone you remove from
      the manifest disappears on the next render.
    - Only one statement is new. Deploy lookups for `ledger-svc` were already forbidden in Part 1, because
      `changes.services` lists only `payments-gw`. The zone states the intent, and keeps holding if someone later adds
      `ledger-svc` to `changes.services`.
    - Your sha differs from the docs if your manifest differs from `agent.part4.yaml`. That is expected.

### 3. Deploy to enforce it

Rendering only writes files. The Gateway enforces the new rule after you deploy:

```bash
make deploy-agent NAME=payments-gw
```

??? example "Expected output (trimmed)"
    ```text
    [factory] 18 Cedar policies ACTIVE
    [factory] policy engine attached (ENFORCE) and interceptor attached
    [factory] runtime READY: arn:aws:bedrock-agentcore:us-west-2:<account>:runtime/fx_payments_gw-...
    ```

## Verify
```bash
make verify-labB-part4
```
!!! success "You should see"
    ```text
    PASS  manifest has a forbidden zone (['service:ledger-svc'])
    PASS  re-rendered Cedar contains a forbid for zone 'service:ledger-svc'
    PASS  rendered agent matches the current manifest
    PASS  live Gateway denies get_recent_deploys for ledger-svc

    RESULT: PASS
    ```
    If "rendered agent matches the current manifest" fails, you edited `agent.yaml` after rendering. Re-render and
    re-deploy.

## While you build your own agent

Once an agent is deployed, this is the loop you use in the capstone. Change `agent.yaml` (or the charter, or a tool),
then `make new-agent` and `make deploy-agent`, then try one of these.

**Test it with an incident.** Start the forwarder in one terminal and send an alert from a second:

```bash
make run-forwarder NAME=payments-gw
curl -X POST localhost:8090/alert -d @data/alerts/replay-psp-5xx.json
```

`data/alerts/` has ten alerts. To ask your own question, put it in `summary`, as in Part 3.

**Replay many incidents and check the gates.** The replay cases in `evals/replay/` and the pass marks in `agent.yaml`
(`evals.gates`) are used by:

```bash
make eval NAME=payments-gw     # replays every case against the deployed agent, about 12 minutes
make gate NAME=payments-gw     # exits 1 if any gate is missed
```

**Add a case.** Copy a file in `evals/replay/`, then change the alert, `expected_root_cause` and `expected_tools`. The
renderer needs at least 3 cases.

**Add another tool or zone.** Add a tool under `connectors.custom` (Part 3) or an entry under `forbidden_zones`, then
re-render and deploy.

Run evals again after you change the prompt, the model, a tool or the policy. That catches regressions.

## Troubleshooting
| Symptom | Fix |
|---|---|
| `policy.forbidden_zones: '<zone>' names target '...' which is not a declared connector` | A `<target>.<tool>` zone must name a connector in the manifest, or a custom tool's `name` |
| `... target 'tickets' has no tool 'x' (has: ...)` | Use one of the listed tool names |
| `FAIL  rendered agent matches the current manifest` | You edited `agent.yaml` after rendering. Run `make new-agent ...` and `make deploy-agent NAME=payments-gw` |
| `deploy-agent` stalls, then `policy name '...' is still in use after 60 s` | A deleted policy still holds its name (names are unique across the account). Wait a minute and re-run. If it persists, `make destroy-agent` the old agent that owns it |

!!! tip "Behind?"
    `make solution-labB-part4` copies `labs/B/solutions/agent.part4.yaml` over `labs/B/agent.yaml`, re-renders and
    deploys. It runs the earlier Lab B solutions first.

## Clean up

When you no longer need the factory agent (for example at the end of the day), remove its cloud resources (Lab A is untouched):

```bash
make destroy-agent NAME=payments-gw
```

See [Clean up](../reference/cleanup.md) for the rest.
