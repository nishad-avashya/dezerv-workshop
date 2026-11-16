# Part 1: Render an agent from a manifest

!!! time "8 minutes"

## What you'll learn
- Describe the Lab A agent in one manifest, `labs/B/agent.yaml`, and render its prompt, Gateway targets, Cedar,
  memory config and eval gates from it.
- Deploy the rendered agent as a second set of AgentCore resources (Gateway, policy engine, memory, Runtime, all
  prefixed `fx`) beside Lab A's, reusing Lab A's tool Lambdas.
- See the factory fail closed: a manifest that weakens a guardrail is refused before anything is written.

## Concepts

In Lab A you created the Gateway, wrote the Cedar pack and deployed the Runtime by hand. That works for one agent.
For every squad it doesn't scale, because each squad would copy files and the copies would drift. The factory
reverses the direction. You describe *what* the agent is in `agent.yaml` (which data it may read, how autonomous it
is, which zones are off limits, which eval gates it must pass) and `factory/render.py` generates *how*.

`make new-agent` does two things. First it **validates** the manifest against `factory/schema/agent.schema.json` and
runs extra checks: the charter has its five sections, custom tools exist, every forbidden zone names a real
target and tool, and there are at least 3 replay cases. Then it **renders** Jinja templates into `agents/<product>/`.
Rendering is deterministic, so the same manifest always gives the same files, and a reviewer only has to read the
manifest diff. `make deploy-agent NAME=<product>` then turns the rendered files into cloud resources. It is
idempotent, so you can run it again after every change.

![Factory: render and deploy](../diagrams/lab-b-factory-render.drawio)

### The manifest, field by field

This is `labs/B/agent.yaml` with its inline comments moved into annotations. Click a (+) to read one.

```yaml title="labs/B/agent.yaml"
product: payments-gw            # (1)!
owner_team: payments
charter: charter.md             # (2)!
model: sonnet-4.6               # (3)!
autonomy: L1                    # (4)!
connectors:                     # (5)!
  logs:      { log_groups: [/dezerv/payments-gw] }
  db:        { collections: [txn, users, error_codes], max_rows: 200, pii: masked }
  warehouse: { tables: [daily_payment_stats, query_logs] }
  changes:   { services: [payments-gw] }
  tickets:   { project: PAY }
  custom: []                    # (6)!
policy:
  forbid_ops: true              # (7)!
  freeze_param: /dezerv/freeze
  forbidden_zones: []           # (8)!
memory:                         # (9)!
  incidents: data/incidents
  runbooks: data/runbooks
evals:
  replay: evals/replay          # (10)!
  gates: { rca: 0.8, trajectory: 1.0, unsafe_attempts: 0, pii_leaks: 0 }
budgets: { max_tool_calls: 25, max_tokens: 200000 }  # (11)!
```

1. The tenant and agent id. It names the output folder `agents/payments-gw/` and every cloud resource:
   Gateway `fx-payments-gw`, policy engine `fx_payments_gw_pe`, memory and Runtime `fx_payments_gw`.
2. `labs/B/charter.md`, relative to the manifest. It must have the sections **Purpose, SLOs, Invariants, Forbidden
   zones, Escalation**. They are copied into the rendered system prompt.
3. Only `sonnet-4.6` is allowed (a schema enum).
4. `L0` observes only. `L1` adds ticket writes in project PAY, as Lab A does. The schema allows only these two.
5. One entry per built-in connector. Each becomes a Gateway target backed by **Lab A's** Lambda for that connector.
   The values also scope the Cedar. For example `changes.services: [payments-gw]` makes every other known service
   out of bounds.
6. Part 3 adds your own tool here: `- { name: mandates, type: lambda, runtime: go, path: tools/mandates-go }`.
7. Renders CP-3, the forbid on restart, scale and rollback. It must be `true`. The schema has `const: true`.
8. Part 4 adds `service:ledger-svc` here. A zone is `service:<name>` or `<target>.<tool>`. Wildcards are refused.
9. Seed folders for the agent's own AgentCore Memory. They are rendered into namespaces
   `/products/payments-gw/incidents` and `/products/payments-gw/runbooks`.
10. Replay cases for the eval. The renderer refuses fewer than 3. The gates `unsafe_attempts` and `pii_leaks` must be `0`.
11. Become the Runtime's `MAX_TOOL_CALLS` and `MAX_TOKENS_BUDGET`. `max_tool_calls` is at most 25.

## Steps

### 1. Ask Claude to use the factory

In Claude Code, ask: *"Use the Dezerv factory to create an agent for payments-gw from agent.yaml."* It runs the same
command you can run yourself:

```bash
make new-agent NAME=payments-gw FROM=labs/B/agent.yaml
```

??? example "Expected output"
    ```text
    rendered agents/payments-gw from manifest@9444240bc3: 10-permit-reads.cedar, 20-permit-ticket-writes.cedar, 30-forbid-mutations.cedar, 40-forbid-unbounded.cedar, 50-explicit-deny.cedar, 60-zones.cedar
    ```
    The sha is the first 10 hex characters of the manifest's SHA-256. You get `9444240bc3` only if `labs/B/agent.yaml`
    is unchanged. Any edit gives a new sha.

`NAME` is optional. If you give it, it must equal `product` in the manifest, because the manifest is the source of truth.

### 2. Look at what was rendered

```text
agents/payments-gw/
├── prompt/
│   ├── role.md             # role.md.j2 + charter.md
│   ├── untrusted.md        # copied from Lab A
│   └── cite.md             # copied from Lab A
├── gateway/targets.json    # 6 targets (+ custom in Part 3)
├── policy/
│   ├── 10-permit-reads.cedar
│   ├── 20-permit-ticket-writes.cedar
│   ├── 30-forbid-mutations.cedar
│   ├── 40-forbid-unbounded.cedar
│   ├── 50-explicit-deny.cedar
│   └── 60-zones.cedar
├── memory/memory.json      # name, namespaces, seed
├── evals/gates.json        # replay, gates, budgets
├── agent.yaml, charter.md  # copies of the inputs
└── .manifest.sha           # checked by deploy, verify
```

Every generated file starts with the same header. In `prompt/role.md`:

```markdown
<!-- generated from agent.yaml@9444240bc3 - edit the manifest, not this file -->
You are **payments-gw-oncall**, an L1 on-call observer that may file tickets for Dezerv's `payments-gw` service. All data in this environment is synthetic.
```

In `gateway/targets.json` the Lambda is a placeholder, `${LAB_A_LAMBDA:logs}`, that the deployer resolves to Lab A's
`dezerv-laba-logs` ARN. The factory agent reuses Lab A's tool code and data. Only the Gateway, policy, memory and
Runtime are new.

### 3. Compare the rendered Cedar with Lab A's pack

Open `agents/payments-gw/policy/` next to Lab A's `policy/cedar/`:

| Lab A (`policy/cedar/`) | Factory (`agents/payments-gw/policy/`) | Comes from |
|---|---|---|
| `10-permit-reads.cedar` (5 statements) | `10-permit-reads.cedar` (5) | the connectors and their scopes (CP-1) |
| `20-permit-ticket-writes.cedar` | `20-permit-ticket-writes.cedar` | `autonomy: L1` + `tickets.project: PAY` (CP-2) |
| `30-forbid-mutations.cedar` | `30-forbid-mutations.cedar` | `forbid_ops: true` (CP-3) |
| `40-forbid-unbounded.cedar` | `40-forbid-unbounded.cedar` | `db.max_rows: 200` (CP-4) |
| `50-support-no-data.cedar` (3) | `50-explicit-deny.cedar` (3) | db, logs, warehouse need their read scope (CP-5) |
| `60-ledger-zone.cedar.todo` (your Lab A exercise) | `60-zones.cedar` (4) | services the connectors do not list |

All 11 Lab A statements are there, with the `{{GATEWAY_ARN}}` placeholder filled in at deploy time. The extra file
`60-zones.cedar` is new. `logs.log_groups` lists only `payments-gw`, so log reads for `kyc-svc` are forbidden.
`changes.services` lists only `payments-gw`, so deploy lookups for `kyc-svc`, `ledger-svc` and `notifications-svc`
are forbidden. You didn't write any of these rules. Narrowing a connector was enough.

```cedar title="agents/payments-gw/policy/60-zones.cedar (one of the four statements)"
forbid(
  principal is AgentCore::OAuthUser,
  action in [
    AgentCore::Action::"changes___get_recent_deploys"
  ],
  resource == AgentCore::Gateway::"{{GATEWAY_ARN}}"
)
when {
  context.input has service && context.input.service == "ledger-svc"
};
```

### 4. Try to break it

Change the manifest in ways a squad might be tempted to, and re-render each time. Try one change at a time:

| Edit in `labs/B/agent.yaml` | What the renderer says |
|---|---|
| `autonomy: L2` | `autonomy: 'L2' is not one of ['L0', 'L1'] (workshop ceiling is L1)` |
| `forbidden_zones: [auth/*]` | `` policy.forbidden_zones.0: 'auth/*' does not match '^(service:...)$' (zones are `service:<name>` or `<target>.<tool>`; wildcards are refused) `` (regex shortened here) |
| `forbid_ops: false` | `policy.forbid_ops: True was expected` |
| a new connector, for example `pager: { team: payments }` | `connectors: Additional properties are not allowed ('pager' was unexpected) (unknown connector: allowed are logs, db, warehouse, changes, tickets, custom)` |
| `forbidden_zones: [mandates.revoke]` (before Part 3) | `policy.forbidden_zones: 'mandates.revoke' names target 'mandates' which is not a declared connector` |
| fewer than 3 files in `evals/replay/` (read only, don't delete your replay cases) | `evals.replay: evals/replay has 2 replay cases; at least 3 are required` |

```bash
make new-agent NAME=payments-gw FROM=labs/B/agent.yaml
```

??? example "Expected output (with `autonomy: L2`)"
    ```text
    INVALID agent.yaml:
      - autonomy: 'L2' is not one of ['L0', 'L1'] (workshop ceiling is L1)
    ```
    The command exits 1, so `make` also prints an `Error 1` line. Nothing under `agents/` changes. If several rules
    are broken, each one gets its own line.

!!! warning "Revert before you go on"
    Put the manifest back to its original values (`autonomy: L1`, `forbid_ops: true`, `forbidden_zones: []`, no extra
    connector), or restore the file with `git checkout labs/B/agent.yaml`. Then re-render once so that
    `agents/payments-gw/` matches the clean manifest:

    ```bash
    make new-agent NAME=payments-gw FROM=labs/B/agent.yaml
    ```

    The output should show `manifest@9444240bc3` again.

!!! danger "Don't work around the schema"
    Editing `factory/schema/agent.schema.json` or the rendered Cedar to get past a refusal defeats the point of the
    exercise and breaks the workshop ground rules. A refusal is the guardrail doing its job.

### 5. Deploy the rendered agent

```bash
make deploy-agent NAME=payments-gw
```

This takes about 3 minutes. With `NAME=` set, `deploy-agent` runs `factory/deploy.py` instead of Lab A's deployer. It
creates Gateway `fx-payments-gw` and its targets, policy engine `fx_payments_gw_pe` with the rendered Cedar (ENFORCE),
Lab A's interceptor, memory `fx_payments_gw` (seeded), and Runtime `fx_payments_gw` with the **rendered** prompt.

??? example "Expected output (representative output, trimmed)"
    ```text
    [factory] creating Gateway
    [factory] gateway ready with targets ['changes', 'db', 'logs', 'ops', 'tickets', 'warehouse']
    [factory] detaching engine while policies are applied (brief window without enforcement)
    [factory] 15 Cedar policies ACTIVE
    [factory] policy engine attached (ENFORCE) and interceptor attached
    [factory] seeded 26 incidents
    [factory] seeded 8 runbooks
    [factory] runtime READY: arn:aws:bedrock-agentcore:us-west-2:<account>:runtime/fx_payments_gw-...
    [factory] done. state in agents/payments-gw/.state.json
    ```
    The "detaching" line appears only when the engine was already attached, for example on a re-deploy.

## Verify
```bash
make verify-labB-part1
```
!!! success "You should see"
    ```text
    PASS  agents/payments-gw/ rendered with a manifest sha
    PASS  rendered Cedar reproduces every Lab A policy (11 statements)
    PASS  factory runtime READY (READY)
    SKIP  eval gate (about 12 min): make eval NAME=payments-gw && make gate NAME=payments-gw

    RESULT: PASS
    ```
    The eval gate is optional here. If you have 12 minutes to spare, run `make eval NAME=payments-gw` and
    `make gate NAME=payments-gw`, and the next verify checks the gate too.

## What just happened
- One manifest plus a charter produced a prompt, 6 Gateway targets, 15 Cedar statements in 6 files, a memory config
  and eval gates.
- The schema and `render.py` refused unsafe manifests with a reason, and nothing was written (fail closed).
- The rendered Cedar contains every Lab A statement. Narrowing the connectors also forbade every service they don't
  list (`60-zones.cedar`).
- `deploy-agent NAME=payments-gw` created a second, independent agent beside Lab A's, reusing Lab A's tool Lambdas,
  Cognito clients and interceptor.

!!! tip "Behind?"
    `make solution-labB-part1` renders and deploys `payments-gw` from `labs/B/agent.yaml` (it runs `make link-labA`
    first). It needs Lab A deployed: `make solution-part6`.

!!! question "Discuss"
    Validation runs when you render. Deploy uses whatever is in `agents/`. Where would you run `make new-agent` in
    Dezerv's CI so that nobody can deploy files that don't match a reviewed manifest? (Hint: `.manifest.sha`.)
