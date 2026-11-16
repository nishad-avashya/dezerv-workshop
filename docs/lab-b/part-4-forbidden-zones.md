# Part 4: Forbidden zones

!!! time "2 minutes"

## What you'll learn
- Declare a forbidden zone in the manifest and see it become Cedar `forbid` statements.
- See that **policy follows the manifest**: re-rendering adds or removes rules, and deploying enforces them in the
  Gateway's policy engine.

## Concepts

The charter in `labs/B/charter.md` says under *Forbidden zones*: "`ledger-svc` internals (owned by the ledger team)".
In Lab A you turned a sentence like that into Cedar by hand (`60-ledger-zone.cedar.todo`, solution `make cp6`). In
Lab B you declare it once in `agent.yaml`, and the factory writes the Cedar.

`policy.forbidden_zones` takes two kinds of entries, and wildcards are refused:

| Zone | Renders |
|---|---|
| `service:<name>` | a `forbid` on every tool with a `service` input (`logs___query_logs`, `logs___get_log_patterns`, `changes___get_recent_deploys`) when `context.input.service == "<name>"` |
| `<target>.<tool>` | a `forbid` on exactly that tool, for example `tickets.add_comment` forbids `tickets___add_comment` |

All zone rules go into `agents/payments-gw/policy/60-zones.cedar`, together with the scoping rules from Part 1
(services the connectors don't list). On every render the old `*.cedar` files are deleted first. If you remove a zone
from the manifest, its rule disappears on the next render and deploy.

## Steps

### 1. Add the zone

In `labs/B/agent.yaml`, change the `forbidden_zones` line under `policy:` to:

```yaml title="labs/B/agent.yaml (policy section)"
policy:
  forbid_ops: true
  freeze_param: /dezerv/freeze
  forbidden_zones: [service:ledger-svc]
```

The reference is `labs/B/solutions/agent.part4.yaml`. It keeps the Part 3 `mandates` tool.

### 2. Re-render and look at the zones file

```bash
make new-agent NAME=payments-gw FROM=labs/B/agent.yaml
```

??? example "Expected output"
    ```text
    rendered agents/payments-gw from manifest@8404c89fdf: 10-permit-reads.cedar, 20-permit-ticket-writes.cedar, 30-forbid-mutations.cedar, 40-forbid-unbounded.cedar, 50-explicit-deny.cedar, 60-zones.cedar
    ```
    The sha is `8404c89fdf` only if your manifest is identical to `labs/B/solutions/agent.part4.yaml`.

`agents/payments-gw/policy/60-zones.cedar` now has 5 statements instead of 4. This one is new:

```cedar title="agents/payments-gw/policy/60-zones.cedar (new statement)"
forbid(
  principal is AgentCore::OAuthUser,
  action in [
    AgentCore::Action::"logs___query_logs",
    AgentCore::Action::"logs___get_log_patterns"
  ],
  resource == AgentCore::Gateway::"{{GATEWAY_ARN}}"
)
when {
  context.input has service && context.input.service == "ledger-svc"
};
```

??? info "The complete rendered file"
    ```cedar title="agents/payments-gw/policy/60-zones.cedar"
    // generated from agent.yaml@8404c89fdf - edit the manifest, not this file
    // scoping and forbidden zones derived from the manifest

    forbid(
      principal is AgentCore::OAuthUser,
      action in [
        AgentCore::Action::"logs___query_logs",
        AgentCore::Action::"logs___get_log_patterns"
      ],
      resource == AgentCore::Gateway::"{{GATEWAY_ARN}}"
    )
    when {
      context.input has service && context.input.service == "kyc-svc"
    };

    forbid(
      principal is AgentCore::OAuthUser,
      action in [
        AgentCore::Action::"changes___get_recent_deploys"
      ],
      resource == AgentCore::Gateway::"{{GATEWAY_ARN}}"
    )
    when {
      context.input has service && context.input.service == "kyc-svc"
    };

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

    forbid(
      principal is AgentCore::OAuthUser,
      action in [
        AgentCore::Action::"changes___get_recent_deploys"
      ],
      resource == AgentCore::Gateway::"{{GATEWAY_ARN}}"
    )
    when {
      context.input has service && context.input.service == "notifications-svc"
    };

    forbid(
      principal is AgentCore::OAuthUser,
      action in [
        AgentCore::Action::"logs___query_logs",
        AgentCore::Action::"logs___get_log_patterns"
      ],
      resource == AgentCore::Gateway::"{{GATEWAY_ARN}}"
    )
    when {
      context.input has service && context.input.service == "ledger-svc"
    };
    ```

!!! note "Why only one new statement?"
    Deploy lookups for `ledger-svc` were **already** forbidden in Part 1, because `changes.services` lists only
    `payments-gw` (the third statement above). The renderer doesn't repeat a rule it has already written, so the zone
    adds only the missing one, the log tools for `ledger-svc`. The zone still matters. It states the intent in the
    manifest, and it keeps holding if someone later adds `ledger-svc` to `changes.services`.

### 3. Deploy to enforce it

Rendering only writes files. The Gateway enforces the new rule after you deploy:

```bash
make deploy-agent NAME=payments-gw
```

??? example "Expected output (representative output, trimmed)"
    ```text
    [factory] updated Lambda dezerv-laba-fx-payments-gw-mandates
    [factory] gateway ready with targets ['changes', 'db', 'logs', 'mandates', 'ops', 'tickets', 'warehouse']
    [factory] detaching engine while policies are applied (brief window without enforcement)
    [factory] 18 Cedar policies ACTIVE
    [factory] policy engine attached (ENFORCE) and interceptor attached
    [factory] runtime READY: arn:aws:bedrock-agentcore:us-west-2:<account>:runtime/fx_payments_gw-...
    [factory] done. state in agents/payments-gw/.state.json
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
    "rendered agent matches the current manifest" compares `agents/payments-gw/.manifest.sha` with the sha of
    `labs/B/agent.yaml`. If you edited the manifest after rendering, re-render and re-deploy.

## What just happened
- One string in the manifest, `service:ledger-svc`, became a Cedar `forbid` in `60-zones.cedar`.
- The renderer combined it with the scoping rules it already had and didn't duplicate any rule.
- `deploy-agent` replaced the policy set in `fx_payments_gw_pe` (18 statements). It briefly detaches the engine
  while it applies them, a service quirk described in `FINDINGS.md`, and always re-attaches it in ENFORCE mode.
- The charter's sentence "ledger-svc internals" and the enforced policy now come from the same reviewed source.

!!! tip "Behind?"
    `make solution-labB-part4` copies `labs/B/solutions/agent.part4.yaml` over `labs/B/agent.yaml`, re-renders and
    deploys. It runs the earlier Lab B solutions first.

## Troubleshooting
| Symptom | Fix |
|---|---|
| `policy.forbidden_zones: '<zone>' names target '...' which is not a declared connector` | A `<target>.<tool>` zone must name a connector in the manifest, or a custom tool's `name` |
| `... target 'tickets' has no tool 'x' (has: ...)` | Use one of the listed tool names |
| `FAIL  rendered agent matches the current manifest` | You edited `agent.yaml` after rendering. Run `make new-agent ...` and `make deploy-agent NAME=payments-gw` |
| `deploy-agent` stalls, then `policy name '...' is still in use after 60 s` | A deleted policy still holds its name (names are unique across the account). Wait a minute and re-run. If it persists, `make destroy-agent` the old agent that owns it |

!!! question "Discuss"
    `forbidden_zones` covers tools with a `service` input and whole tools. What would a forbidden zone for *data*
    look like, for example "never read the `ledger_entries` collection"? Should it go in Cedar, in the tool, or in
    both? (Lab A's CP-6 note has a hint: Cedar cannot look inside a free-form filter object.)

## Clean up

When you no longer need the factory agent (for example at the end of the day), remove the factory agent's cloud resources (Lab A is untouched):

```bash
make destroy-agent NAME=payments-gw
```

See [Clean up](../reference/cleanup.md) for the rest.
