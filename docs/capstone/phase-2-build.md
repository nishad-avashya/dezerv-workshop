# Phase 2: Build the agent

!!! time "25 minutes (minutes 25-50), checkpoint C2 at ~50 min"

## What you'll learn
- How one manifest (`squads/<squad>/agent.yaml`) renders and deploys a complete governed agent: Gateway, Cedar, memory and Runtime.
- How a squad's custom tool becomes a governed Gateway tool (AgentCore Gateway Lambda target + Cedar permit on a JWT scope).
- How forbidden zones in the manifest become Cedar `forbid` rules (AgentCore Policy, ENFORCE mode).
- How to run your own incident end to end against the deployed agent (AgentCore Runtime + Memory).

## Concepts
In Lab B you rendered an agent from `labs/B/agent.yaml`. The capstone uses the same factory with the manifest that `make new-squad` wrote.
That manifest has one extra block, `data:`. When the deployer sees it, it creates **private copies** of the Lab A tool Lambdas
(`dezerv-laba-fx-kyc-svc-db`, `-logs`, `-changes`) with environment overrides (`DATA_PREFIX`, `COLLECTIONS`, `PRIMARY_COLLECTION`,
`LOG_SERVICES`, `DEPLOYS_KEY`) that point them at `squads/kyc/data/`. The tool names do not change. `find_transactions` now searches
`kyc_requests`, and `get_recent_deploys` reads your `deploys.json`. The tickets tool stays the shared Lab A Lambda (project `PAY`).

Your **custom tool** is a small Python Lambda (`squads/kyc/tools/get_kyc_request/handler.py`). Its `tools.json` declares the tool schema and the
scope `payments/custom.read`. The factory turns that into a Gateway target named `kyc`, so the tool appears as `kyc___get_kyc_request`. It also adds
Cedar rules that permit the tool only when the caller's JWT has the `custom.read` scope (`10-permit-reads.cedar`), and forbid it otherwise
(`50-explicit-deny.cedar`). A tool marked `"mutating": true` would join the mutation forbid in `30-forbid-mutations.cedar` automatically.

**Forbidden zones** are the charter's "never touch" list, made enforceable. `service:<name>` forbids the log and deploy tools for that service.
`<target>.<tool>` forbids one tool. The connectors scope the agent too: any known service that your `logs` or `changes` connector does not list is
forbidden, so the kyc agent cannot read `payments-gw` deploys even without a zone. All of it renders into `60-zones.cedar`. Cedar is the lock;
the prompt only asks nicely.

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
This creates the custom tool Lambda, the private tool copies, the Gateway `fx-kyc-svc` and its targets, and a policy engine with your Cedar (ENFORCE).
It attaches the interceptor, creates memory `fx_kyc_svc` and seeds it with your 5 incidents and 2 runbooks. Last, it creates the Runtime with the
**rendered** prompt. Expect several minutes: it packages the agent and waits for the Runtime to become `READY`.

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
The profile already gave you your one custom tool. `squads/kyc/tools/get_kyc_request/` contains:

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

It already works: it is a read-only lookup of one record in your primary collection, with PII masked in the tool (defence in depth, because the
Gateway interceptor masks too). Make it answer the question your on-call engineer really asks. For example, add how many failures share this
request's vendor, just before the masking loop:

```python
            same = [x for x in rows() if x.get("vendor") == r.get("vendor") and x.get("error_code")]
            r["vendor_failures"] = len(same)
```

Rules for the edit: **keep it read-only**, keep `PII_FIELDS` masking, and keep returning `envelope(...)`, so the agent can cite `source` and `query`.
If you change the inputs or the purpose, update `description` and `inputSchema` in `tools.json`: the model only sees what that file says.
Then re-render and redeploy (`make new-agent FROM=squads/kyc/agent.yaml && make deploy-agent NAME=kyc-svc`).

??? tip "Optional: a second tool with `make new-tool` (watch the clock)"
    The scope rule is one custom tool, and the profile already gave you one. If your squad really needs another one:
    ```bash
    make new-tool SQUAD=kyc TOOL=get_vendor_status ARG=vendor
    ```
    ```text
    scaffolded squads/kyc/tools/get_vendor_status (target 'status') and registered it in squads/kyc/agent.yaml. Edit the handler, then make new-agent && make deploy-agent.
    ```
    What the command does:

    - The target name is the last `_` word of the tool name (`get_vendor_status` becomes target `status`, tool `status___get_vendor_status`).
      It must not clash with a built-in target (`logs`, `db`, `warehouse`, `changes`, `tickets`, `ops`) or another custom one.
    - The Python scaffold sets `ID_FIELD` to your `ARG` and `PII_FIELDS = []`. Set both correctly. The default lookup returns the first record whose `ARG` field equals the input.
    - `tools.json` has `"description": "TODO describe get_vendor_status"`. Write a real one.
    - It appends a `connectors.custom` entry to `agent.yaml`. It rewrites the file, so YAML comments are lost.
    - `RUNTIME=go` copies `tools/mandates-go` (which implements `get_mandate_status` and the decoy `revoke_mandate`). You must change `main.go` to serve your tool name.
      Deploying it needs a Go toolchain (`make go-setup`), because there is no prebuilt zip for a new Go tool.

### 4. Add forbidden zones from your charter
Open `squads/kyc/agent.yaml`. The generator already added `service:ledger-svc`. Keep it, because `make prove-denial` in Phase 3 relies on it.
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
Check `agents/kyc-svc/policy/60-zones.cedar`: each zone is now a `forbid` statement. A forbidden tool also disappears from the agent's `tools/list`.

!!! danger "Never weaken the guardrails"
    Do not set `forbid_ops: false` or `autonomy` above `L1` (the schema refuses both), do not edit generated Cedar, and do not give any tool a write path.
    Mitigations stay recommendations for a human to approve.

### 5. Run the incident
Send the alert to the deployed agent through the Lab B Go forwarder. In one terminal:
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
C2 checks, from `scripts/squad.py`:

| Check | What it tests |
|---|---|
| `agent deployed and READY` | `agents/kyc-svc/.state.json` exists and `GetAgentRuntime` reports `READY` |
| `custom tool kyc___get_kyc_request is listed` | `tools/list` on your Gateway, as the `oncall` persona, includes the profile's custom tool |
| `incident run mentions the expected root-cause marker /<marker>/` | It invokes the Runtime with `alerts/incident.json`, and the answer must match the profile's `marker` regex (for `kyc-svc`: `v1\.8\.1` or `9d8e7a1`) |

!!! success "You should see"
    ```text
    PASS  agent deployed and READY
    PASS  custom tool kyc___get_kyc_request is listed
    PASS  incident run mentions the expected root-cause marker /v1\.8\.1|9d8e7a1/

    RESULT: PASS
    ```
    The marker check fails? Read the answer. Did the agent find no logs or deploys? Then check `make provision-squad SQUAD=kyc` ran. C2 is a real agent run,
    so do not start an eval or another `oncall` run at the same time (per-principal rate limit, 30 calls a minute).

## What just happened
- One manifest became a running, governed agent: private tool copies on your data, your custom tool behind the Gateway, Cedar in ENFORCE, seeded memory, and a Runtime with your charter in its prompt.
- Your custom tool is governed like any other: permitted by scope, hidden and denied when forbidden, and masked twice.
- Your charter's forbidden zones are now Cedar `forbid` statements, derived from the manifest rather than written by hand.
- The agent diagnosed your incident with citations, and left the mitigation to a human.

!!! tip "Behind?"
    The capstone has no `solution-*` targets. Ask an instructor. The capstone plan includes a "golden" fallback account with every ready profile deployed, for squads whose account breaks.

!!! question "Discuss"
    Which line in your charter's **Forbidden zones** could you *not* express as `service:<name>` or `<target>.<tool>`? What would it take to enforce it in production, for example a new tool argument, a new Cedar condition or a separate connector?
