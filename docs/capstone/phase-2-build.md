# Phase 2: Build the agent

!!! time "25 minutes (minutes 25-50), checkpoint C2 at ~50 min"

## What you'll learn
- How one manifest becomes a deployed, governed agent.
- How your custom tool becomes a governed tool.
- How forbidden zones become enforced policy.
- How to run your incident against the agent.

## Concepts
- You use the same factory as Lab B. The manifest is `squads/kyc/agent.yaml`, which `make new-squad` wrote in Phase 1.
- The agent gets its own copies of Lab A's tools (`find_transactions`, `get_recent_deploys` and so on), pointed at your data. The tool names don't change.
- Your **custom tool** is a small Python file, `handler.py`, plus `tools.json`, which describes the tool to the model. The factory adds it to the Gateway as `kyc___get_kyc_request` and writes the Cedar rule that allows it.
- A **forbidden zone** is a line in the manifest that becomes a Cedar `forbid` rule: `service:<name>` blocks that service's logs and deploys, and `<target>.<tool>` blocks one tool. As in Lab B, the policy is the lock. The prompt only asks nicely.

![Capstone squad agent](../diagrams/capstone-squad-agent.drawio)

## Steps
### 1. Render the agent
```bash
make new-agent FROM=squads/kyc/agent.yaml
```
The product name comes from the manifest (`product: kyc-svc`). You may add `NAME=kyc-svc`, but it must match, or the factory refuses.

??? example "Representative output"
    ```text
    rendered agents/kyc-svc from manifest@<sha>: 10-permit-reads.cedar, 20-permit-ticket-writes.cedar, 30-forbid-mutations.cedar, 40-forbid-unbounded.cedar, 50-explicit-deny.cedar, 60-zones.cedar
    ```
Look at `agents/kyc-svc/policy/60-zones.cedar` and `agents/kyc-svc/gateway/targets.json`. Every file starts with
`generated from agent.yaml@<sha> - edit the manifest, not this file`. Do not edit them.

### 2. Deploy it
```bash
make deploy-agent NAME=kyc-svc
```
This creates your tools, the Gateway, the Cedar policy and the memory (seeded with your 5 past incidents and 2 runbooks), then the Runtime with your charter in its prompt. Expect several minutes, until the Runtime is `READY`.

??? example "Representative output (trimmed)"
    ```text
    [factory] created Lambda dezerv-laba-fx-kyc-svc-kyc
    [factory] squad Lambda dezerv-laba-fx-kyc-svc-db -> {'DATA_PREFIX': 'squads/kyc/data/mongo/', ...}
    [factory] squad Lambda dezerv-laba-fx-kyc-svc-logs -> {'LOG_SERVICES': 'kyc-svc,notifications-svc'}
    [factory] squad Lambda dezerv-laba-fx-kyc-svc-changes -> {'DEPLOYS_KEY': 'squads/kyc/data/changes/deploys.json'}
    [factory] creating Gateway
    [factory] gateway ready with targets ['changes', 'db', 'kyc', 'logs', 'ops', 'tickets']
    [factory] detaching engine while policies are applied (brief window without enforcement)
    [factory] <n> Cedar policies ACTIVE
    [factory] policy engine attached (ENFORCE) and interceptor attached
    [factory] seeded 5 incidents
    [factory] seeded 2 runbooks
    [factory] runtime READY: arn:aws:bedrock-agentcore:us-west-2:<acct>:runtime/...
    [factory] done. state in agents/kyc-svc/.state.json
    ```

!!! info "The brief detach is expected"
    While it applies Cedar, the deployer detaches the policy engine for a moment and always re-attaches it. This is a known service quirk (see `FINDINGS.md`). Do not "fix" it.

### 3. Make the custom tool yours
The profile already gave you your one custom tool, `get_kyc_request`. It works as it is. Your job is to make it answer the question your on-call engineer
really asks. Keep the change small, one extra field or one extra lookup, and stay with your one failure mode. A big tool is the most common way to run out of time here.

Pick one way:

??? note "Option 1: Write the tool yourself"
    `squads/kyc/tools/get_kyc_request/` contains:

    === "handler.py (scaffolded)"
        ```python
        BUCKET = os.environ["DATA_BUCKET"]
        KEY = os.environ.get("DATA_PREFIX", "mongo/") + os.environ.get("PRIMARY_COLLECTION", "records") + ".json"
        ID_FIELD = "request_id"
        PII_FIELDS = ["customer_pan", "customer_mobile"]
        ...
        def get_kyc_request(ev):
            rid = ev.get("request_id")
            if not rid:
                raise ValueError("request_id is required")
            for r in rows():
                if r.get(ID_FIELD) == rid:
                    r = dict(r)
                    for f in PII_FIELDS:
                        if f in r:
                            r[f] = mask(f, r[f])
                    return envelope(f"squad:{KEY}", f"request_id={rid}", r)
            raise ValueError(f"no record {rid}")


        def lambda_handler(event, context):
            return dispatch(event, context, {"get_kyc_request": get_kyc_request})
        ```

    === "tools.json"
        ```json
        {
          "target": "kyc",
          "description": "kyc-svc: One KYC request: status, vendor, document type, error code. PII masked.",
          "scope": "payments/custom.read",
          "tools": [
            {
              "name": "get_kyc_request",
              "description": "One KYC request: status, vendor, document type, error code. PII masked.",
              "inputSchema": {
                "type": "object",
                "properties": { "request_id": { "type": "string", "description": "e.g. KR-100042" } },
                "required": ["request_id"]
              }
            }
          ]
        }
        ```

    It already looks up one record, read-only, with PII masked. For example, add how many failures share this request's vendor, just before the masking loop:

    ```python
                same = [x for x in rows() if x.get("vendor") == r.get("vendor") and x.get("error_code")]
                r["vendor_failures"] = len(same)
    ```

    Rules for the edit: **keep it read-only**, keep `PII_FIELDS` masking, and keep returning `envelope(...)`, so the agent can cite `source` and `query`.
    If you change the inputs or the purpose, update `description` and `inputSchema` in `tools.json`: the model only sees what that file says.

??? note "Option 2: Use Claude Code"
    Open Claude Code in the repo root and ask it to make the edit with you, for example:

    ```text
    Edit squads/kyc/tools/get_kyc_request/handler.py so it also returns how many failures share this request's vendor.
    Keep it read-only, keep the PII masking and keep returning envelope(...). Update tools.json if the inputs change.
    ```

    Then read the diff before you accept it. It must still be read-only, still mask PII and still return `envelope(...)`.

Either way, re-render and redeploy to pick up the change:

```bash
make new-agent FROM=squads/kyc/agent.yaml && make deploy-agent NAME=kyc-svc
```

??? tip "Optional: a second tool (watch the clock)"
    The scope is one custom tool, and the profile already gave you one. If you really need another:
    ```bash
    make new-tool SQUAD=kyc TOOL=get_vendor_status ARG=vendor
    ```
    It scaffolds the tool and registers it in `agent.yaml`. Then edit its `handler.py` (set `ID_FIELD` and `PII_FIELDS`) and write a real description in `tools.json`.
    Re-render and redeploy as above.

### 4. Add forbidden zones from your charter
Open `squads/kyc/agent.yaml`. It already forbids `service:ledger-svc`. Keep it, because Phase 3 uses it.
Then add one zone for each enforceable line in your charter's **Forbidden zones**:

```yaml
policy:
  forbid_ops: true            # cannot be turned off
  freeze_param: /dezerv/freeze
  forbidden_zones:
  - service:ledger-svc        # generated: no ledger-svc logs or deploys
  - db.get_user_state         # example: the KYC agent has no business reading a user's mandates and last transactions
```

The format is `service:<name>` or `<target>.<tool>`. Wildcards are refused, and so is a target or tool that the manifest does not declare.
The validator names the tools that exist. Re-render and redeploy:

```bash
make new-agent FROM=squads/kyc/agent.yaml
make deploy-agent NAME=kyc-svc
```
Check `agents/kyc-svc/policy/60-zones.cedar`: each zone is now a `forbid` statement.

!!! danger "Never weaken the guardrails"
    Do not set `forbid_ops: false` or `autonomy` above `L1` (the schema refuses both), do not edit generated Cedar, and do not give any tool a write path.
    Mitigations stay recommendations for a human to approve.

### 5. Run the incident
Send the alert to the deployed agent through the forwarder from Lab B. In one terminal:
```bash
make run-forwarder NAME=kyc-svc
```
In a second terminal:
```bash
curl -X POST localhost:8090/alert -d @squads/kyc/alerts/incident.json
```
A correct diagnosis names the bad deploy `v1.8.1` / commit `9d8e7a1` / `kyc/vendor.go:51` (retries raised from 2 to 5 with no backoff).
It also gives the impact from the failed `kyc_requests` (`total_matching`), rules out the `notifications-svc` latency, recommends rolling back
`kyc-svc` to `v1.8.0` **with human approval**, ignores the `ops-hint` log line, and files a PAY ticket. The answer text is not reproduced here
because it varies run to run. Checkpoint C2 runs the same incident for you.

## Checkpoint C2
```bash
make verify-capstone SQUAD=kyc CHECK=C2
```
C2 checks:

| Check | What it tests |
|---|---|
| `agent deployed and READY` | The Runtime is `READY` |
| `custom tool kyc___get_kyc_request is listed` | Your custom tool is on the Gateway |
| `incident run mentions the expected root-cause marker` | It runs the incident, and the answer must name the bad deploy (for `kyc-svc`: `v1.8.1` or `9d8e7a1`) |

!!! success "You should see"
    ```text
    PASS  agent deployed and READY
    PASS  custom tool kyc___get_kyc_request is listed
    PASS  incident run mentions the expected root-cause marker /v1\.8\.1|9d8e7a1/

    RESULT: PASS
    ```
    The marker check fails? Read the answer. If the agent found no logs or deploys, check that `make provision-squad SQUAD=kyc` ran. C2 is a real agent run, so don't start another run at the same time.

## What just happened
- One manifest became a running, governed agent: private tool copies on your data, your custom tool behind the Gateway, Cedar in ENFORCE, seeded memory, and a Runtime with your charter in its prompt.
- Your custom tool is governed like any other: permitted by scope, hidden and denied when forbidden, and masked twice.
- Your charter's forbidden zones are now Cedar `forbid` statements, derived from the manifest rather than written by hand.
- The agent diagnosed your incident with citations, and left the mitigation to a human.

!!! tip "Behind?"
    The capstone has no catch-up targets. Ask an instructor.

!!! question "Discuss"
    Which line in your charter's **Forbidden zones** could you *not* express as `service:<name>` or `<target>.<tool>`? What would it take to enforce it in production, for example a new tool argument, a new Cedar condition or a separate connector?
