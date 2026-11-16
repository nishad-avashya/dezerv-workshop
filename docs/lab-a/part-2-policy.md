# Part 2: Cedar policy

!!! time "15 minutes"

## What you'll learn
- How an **AgentCore Policy** engine in ENFORCE mode authorizes every `tools/call` with Cedar, outside the model.
- Cedar's two rules that matter most: **default deny**, and **`forbid` beats `permit`**.
- How **JWT scopes** reach Cedar as principal tags, so two personas get different tools from the same Gateway.
- How denials name the policy that fired, and why forbidden tools disappear from `tools/list`.

## Concepts

Part 1 ended with an authenticated agent that could call anything. Cedar fixes that. A **policy engine** is attached
to the Gateway in `ENFORCE` mode; for every tool call the Gateway asks it whether this **principal** may perform this
**action** on this **resource**. The principal is the caller (type `AgentCore::OAuthUser`), the action is the tool
name (`AgentCore::Action::"ops___restart_service"`), and the resource is the Gateway itself. Tool arguments are
available as `context.input`.

Cedar **denies by default**: a call is allowed only if some `permit` matches and no `forbid` matches. A matching
`forbid` always wins, whatever any `permit` says. That is why Dezerv's core rule is a single unconditional `forbid`
in `policy/cedar/30-forbid-mutations.cedar`: nobody, under any scope, may restart, scale or roll back.

**Scopes come from the JWT.** The Cognito token's space-separated `scope` claim is exposed to Cedar as the principal tag
`scope`, so a rule reads it with `principal.hasTag("scope") && principal.getTag("scope") like "*db.read*"`.
Always check `hasTag` before `getTag`. The two personas get these scopes:

| Persona | Scopes in its token | Effect |
|---|---|---|
| `oncall` | `payments/logs.read`, `payments/db.read`, `payments/warehouse.read`, `payments/changes.read`, `payments/tickets.read`, `payments/tickets.write` | reads everything, writes PAY tickets |
| `support` | `payments/tickets.read`, `payments/tickets.write` | reads and writes PAY tickets, nothing else |

![Personas, scopes and Cedar](../diagrams/lab-a-cedar.drawio)

The pack in `policy/cedar/` (11 policies; `{{GATEWAY_ARN}}` is filled in when it is applied):

| File | Rule | Teaching point |
|---|---|---|
| `10-permit-reads.cedar` (CP-1, 5 policies) | permit each read tool when the matching `*.read` scope is present | default deny; scopes as tags |
| `20-permit-ticket-writes.cedar` (CP-2) | permit `create_ticket` / `add_comment` with `tickets.write` **and** `context.input.project == "PAY"` | conditions on tool input |
| `30-forbid-mutations.cedar` (CP-3) | **forbid** restart, scale, rollback for every principal | forbid beats permit |
| `40-forbid-unbounded.cedar` (CP-4) | forbid `find_transactions` / `query_logs` when `limit > 200` | guard input reads with `has` |
| `50-support-no-data.cedar` (CP-5, 3 policies) | forbid db, logs and warehouse tools *unless* the read scope is present | explicit deny that fails closed if the tag is missing |

**Denials name the policy.** A denied call comes back as JSON-RPC error `-32002` with a message like
`Tool Execution Denied ... denied due to P30_forbid_mutations_1`. The policy name is derived from the file
(`30-forbid-mutations.cedar`, statement 1). The audit hook in Part 4 copies that name into its `decision.reason`.

**Forbidden tools are hidden.** With the engine attached, the Gateway also filters `tools/list`: tools the caller can
never use are not listed. The `oncall` agent sees 11 tools, not 14; it cannot even *see* `restart_service`.

## Steps

### 1. Create the policy engine and apply the pack
`make policy` creates the engine `dezerv_laba_pe`, uploads one policy per Cedar statement, waits until each is ACTIVE,
and attaches the engine to the Gateway in ENFORCE mode.
```bash
make policy
```
??? example "Expected output (representative, trimmed)"
    ```text
    [labA] policy P10_permit_reads_1 <- 10-permit-reads.cedar
    ...
    [labA] policy P30_forbid_mutations_1 <- 30-forbid-mutations.cedar
    [labA] policy P40_forbid_unbounded_1 <- 40-forbid-unbounded.cedar
    [labA] policy P50_support_no_data_1 <- 50-support-no-data.cedar
    ...
    [labA] policy engine attached in ENFORCE mode
    ```

!!! info "Why re-applying detaches the engine for a few seconds"
    The policy analyzer rejects new or changed conditional `forbid` rules as "Overly Restrictive" while the engine is
    attached, and accepts identical text while it is detached (a service quirk recorded in `FINDINGS.md`). So
    `make policy` detaches, applies and re-attaches, and re-attaches even if the apply fails. The first apply in this
    part happens before attachment, so there is no gap. Comment lines are stripped before upload for the same reason.

### 2. Retry the restart
The same call that succeeded in Part 1:
```bash
uv run --python 3.12 python scripts/mcp_cli.py call ops___restart_service '{"service":"payments-gw"}'
```
??? example "Expected output (representative)"
    ```text
    ERROR
    {
     "code": -32002,
     "message": "Tool Execution Denied ... denied due to P30_forbid_mutations_1"
    }
    ```
The call never reaches the Lambda, so no new `WOULD_EXECUTE` line is written. List the tools again: the three `ops___*`
tools are gone.
```bash
uv run --python 3.12 python scripts/mcp_cli.py list
```

### 3. Compare the personas
Now look at what the `support` persona can see. Its token carries only the two ticket scopes, so every data tool is
either forbidden (CP-5) or never permitted.
```bash
uv run --python 3.12 python scripts/mcp_cli.py list --persona support
```
??? example "Expected output (representative)"
    ```text
    4 tools
      tickets___add_comment
      tickets___create_ticket
      tickets___get_ticket
      tickets___search_tickets
    ```
    The exact count was not recorded in testing; what matters is that no `logs___`, `db___`, `warehouse___` or
    `ops___` tool is listed.

Then run the whole incident as `support`:
```bash
PERSONA=support make run-incident
```
The agent cannot read logs, transactions, the warehouse or deploys, so it cannot reach a root cause. Expect it to say
so and escalate (the prompt tells it to escalate rather than guess). Compare that with the `oncall` answer from Part 1:
same agent, same prompt, same Gateway; only the token differs.

### 4. Exercise: declare a forbidden zone (CP-6)
Dezerv squads declare **forbidden zones**: services an agent must never look at. Write one: the agent may read deploys
for `payments-gw` and `kyc-svc`, but never for `ledger-svc`.

1. Rename the template so it is picked up (`make policy` only reads `*.cedar`):
    ```bash
    mv policy/cedar/60-ledger-zone.cedar.todo policy/cedar/60-ledger-zone.cedar
    ```
2. Edit `policy/cedar/60-ledger-zone.cedar`: uncomment the `forbid(...)` block and replace `/* TODO */` with a condition
   on the `service` input. Two analyzer rules learned in testing: guard every input read
   (`context.input has service && context.input.service == "..."`), and use `when { ... }` with
   `principal is AgentCore::OAuthUser` rather than `unless { ... like ... }`.
3. Apply it:
    ```bash
    make policy
    ```
4. Test both sides. `ledger-svc` must be denied and name your policy (`P60_ledger_zone_1`); `payments-gw` must still work:
    ```bash
    uv run --python 3.12 python scripts/mcp_cli.py call changes___get_recent_deploys '{"service":"ledger-svc"}'
    uv run --python 3.12 python scripts/mcp_cli.py call changes___get_recent_deploys '{"service":"payments-gw"}'
    ```

??? tip "Solution"
    The reference rule is in `policy/solutions/60-forbid-ledger-zone.cedar`:
    ```text
    forbid(
      principal is AgentCore::OAuthUser,
      action == AgentCore::Action::"changes___get_recent_deploys",
      resource == AgentCore::Gateway::"{{GATEWAY_ARN}}"
    )
    when {
      context.input has service && context.input.service == "ledger-svc"
    };
    ```
    `make cp6` copies it into `policy/cedar/` and runs `make policy` (the denial then names `P60_forbid_ledger_zone_1`).
    `make cp6-off` removes it again and re-applies. `cp6-off` only removes the solution file: if you wrote your own
    `60-ledger-zone.cedar`, delete it yourself and run `make policy`, so you do not end up with two copies of the rule.

!!! note "Why not 'forbid unbounded transaction searches'?"
    The original exercise idea was to forbid `find_transactions` when the filter has no time bound. Cedar cannot
    express it: `filter` is a free-form MongoDB object and Cedar cannot look inside it. A good question for the room:
    what is Cedar good for, and what belongs in the tool itself? (Lab B renders zone rules like this one from a manifest.)

## Verify
```bash
make verify-labA-part2
```
!!! success "You should see"
    ```text
          PASS oncall  ops___restart_service      -> DENY   |  {"code": -32002, ...
          PASS oncall  ops___rollback_deploy      -> DENY   |  ...
          PASS support db___find_transactions     -> DENY   |  ...
          PASS support logs___query_logs          -> DENY   |  ...
          PASS oncall  db___find_transactions 500 -> DENY   |  ...
          PASS oncall  db___find_transactions 5   -> ALLOW   |  ok
          PASS oncall  changes___get_recent_deploys -> ALLOW   |  ok
          PASS support tickets___get_ticket       -> ALLOW   |  ok
          PASS support tickets___create_ticket PAY -> ALLOW   |  ok
          PASS support tickets___create_ticket OPS -> DENY   |  ...
    PASS  policy checks (restart denied, support denied, limit=500 denied, reads allowed)

    RESULT: PASS
    ```
    (Representative: the denial text after `|` varies.) The check creates one test ticket in PAY as `support`.

## What just happened
- Every `tools/call` is now authorized by Cedar in ENFORCE mode, outside the model and before any Lambda runs.
- Default deny plus a single `forbid` means no persona can mutate anything, whatever the prompt or a ticket says.
- Personas differ only by the `scope` claim in their JWT, read in Cedar as a principal tag.
- Denials name the policy that fired (`P30_forbid_mutations_1`), and forbidden tools vanish from `tools/list`.

!!! question "Discuss"
    `50-support-no-data.cedar` forbids data tools *unless* the read scope is present, although default deny would
    already refuse `support`. Why write the explicit deny anyway? (Hint: what happens if someone later adds a broad
    `permit`, or the scope tag is missing from a token?)

!!! tip "Behind?"
    `make solution-part2` brings you to the end of this part.

## Troubleshooting
- **Everything allowed after a policy edit:** the engine is detached, for example after a failed apply. Run `make policy`; it re-attaches.
- **`UPDATE_FAILED` / "Overly Restrictive":** an analyzer rejection; see the info box above and `FINDINGS.md`. Check the rule shape and re-run `make policy`.
- **`ConflictException ... already exists`:** a policy deleted a moment ago still holds its name. The script retries; re-run if it gives up.
