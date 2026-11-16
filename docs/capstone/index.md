# Capstone: your squad's own on-call agent

!!! time "90 minutes: 65 minutes of building, then 25 minutes of demos"

## Goal
Each squad leaves with a **governed on-call agent skeleton for one of its own services**, and the squad will own it.
You use the Lab B factory to build the agent. You prove that it is governed and tested, demo it in 5 minutes, and download a
portable starter: manifest, charter, synthetic data, custom tool, rendered Cedar, replay cases, gate report, `DEMO.md` and `PATH-TO-PROD.md`.

The factory generates the plumbing. **Your 65 minutes go into domain thinking:** which failure mode matters, what evidence proves it,
what the agent must never touch, and how you would know it got worse.

!!! note "Before you start"
    The capstone builds on Lab A's stack and the Lab B factory in the same account. Are you behind? `make solution-part6` brings Lab A to its end.
    The running example on every page is **`SQUAD=kyc PROFILE=kyc-svc`**. Use your own squad name and profile.

## Ground rules
1. **Synthetic data only.** No production data, credentials, customer information or proprietary source code goes into the account.
   You *describe* your service and the generator makes mock data that looks like it.
2. **Autonomy ceiling L0/L1.** The agent observes, diagnoses, recommends and files tickets. Every mutation goes through a decoy tool that policy blocks.
   The schema refuses `autonomy` above `L1` and `forbid_ops: false`.
3. **The factory generates; you edit** manifests, charters, data and tool code. Do not hand-write Cedar or Gateway targets, and do not edit files under `agents/`.
4. **Scope: ONE failure mode and ONE custom tool.** This is the most common way squads run out of time. If you start modelling the whole service, narrow it.

!!! danger "All data is synthetic"
    The PAN numbers, mobile numbers, VPAs and account numbers in `squads/<squad>/data/` come from `tools/gen_profile.py`, which is seeded by your squad name.
    Never replace them with real records, and never paste real logs or code into the account.

## Flow and timeline

![Capstone flow](../diagrams/capstone-flow.drawio)

| Minutes | Phase | Page | Commands | Checkpoint |
|---|---|---|---|---|
| 0-10 | Discovery | [Discovery](discovery.md) | Claude Code asks the discovery questions; pick a profile or write a schema | |
| 10-25 | Data and incident | [Phase 1: data](phase-1-data.md) | `make new-squad`, `make provision-squad`, edit `charter.md` | **C1** at ~25 min |
| 25-50 | Build | [Phase 2: build](phase-2-build.md) | `make new-agent`, `make deploy-agent`, custom tool, forbidden zones, run the incident | **C2** at ~50 min |
| 50-65 | Prove it | [Phase 3: prove](phase-3-prove.md) | one replay case of your own, `make eval`, `make gate`, `make prove-denial`, `make export` | **C3** at ~65 min |
| 65-90 | Demos | [Demo](demo.md) | 5 minutes per squad, from `DEMO.md` in the zip | |

Each checkpoint is one command, `make verify-capstone SQUAD=<squad> CHECK=C1|C2|C3`. It prints `PASS`/`FAIL` per check and a hint for each failure.
Instructors use the checkpoints to find a stuck squad early, so run them on time even if you think you are fine.

## Ready profiles
No service sheet? Pick one of the five ready profiles in `capstone/profiles/`. Each one is a complete scenario: a planted bad deploy,
correlated error logs, a red-herring service, a custom tool, 5 past incidents and 2 runbooks.

| Profile | Failure mode (the incident) | Error code | Custom tool | Red herring |
|---|---|---|---|---|
| `kyc-svc` | KYC vendor latency causes onboarding drop-off after a retry-policy change (`v1.8.1`) | `E_KYC_VENDOR_TIMEOUT` | `get_kyc_request(request_id)` | `notifications-svc` SMS latency |
| `mandates-svc` | Spike in UPI AutoPay mandate `REVOKED` after a stricter bank-callback check (`v3.2.0`); looks like a PSP failure but is not | `E_MANDATE_REVOKED` | `get_mandate_status(event_id)` | `payments-gw` PSP latency |
| `ledger-recon` | Nightly reconciliation lag after a schema change drops partition pruning (`v2.5.0`) | `E_RECON_LAG` | `get_recon_run(run_id)` | `kyc-svc` vendor latency |
| `notifications-svc` | OTP SMS delivery failures from provider throttling after a batch-size change (`v0.9.5`) | `E_SMS_THROTTLED` | `get_delivery_status(message_id)` | `kyc-svc` vendor latency |
| `nav-ingest` | Mutual fund NAV file picked up late, so portfolio values are stale (`v1.3.0`); data-pipeline archetype | `E_NAV_MISSING` | `get_ingest_run(run_id)` | `ledger-recon` slow step |

Do you have your own service? Copy a profile, edit it and pass it with `SCHEMA=`. [Discovery](discovery.md) shows how.

!!! warning "`kyc-svc` shares a log group with Lab A"
    Lab A already backfills red-herring logs into `/dezerv/kyc-svc`. The `kyc-svc` profile writes its own logs into the same group.
    This is expected. The incident window and the `commit`/`template_id` fields keep the two apart.

## What your squad gets
`make new-squad` writes `squads/<squad>/` with:

- `agent.yaml` (with a `data:` block that points the tools at your data) and `charter.md`
- a mock collection plus `error_codes`, correlated logs for your service (with `commit`, `caller`, `template_id`, `trace_id`) and for a red-herring service
- `deploys.json` with the bad deploy, `alerts/incident.json`, and a ticket with a planted prompt injection
- 5 past incidents and 2 runbooks for memory
- **3 replay cases** (incident, ticket injection, insufficient evidence)
- a Python scaffold for the custom tool

The agent runs on **private copies of the generic Lab A tools** that read your squad's data. The tool names stay the same (`find_transactions`, `get_log_patterns`, and so on).

## Scoring rubric
For the demo and an optional prize:

| Criterion | Weight | Looks like |
|---|---|---|
| Works end-to-end | 30% | Live diagnosis is correct, with citations |
| Governed | 25% | Forbidden zones derived from the charter; injection blocked |
| Tested | 20% | Meaningful replay cases; gate passes; break-it demonstrated |
| Realism | 15% | The scenario reflects a real failure mode of the service |
| Path to prod | 10% | Concrete gaps and owners named |

!!! danger "Download your export before the account expires"
    `make export` writes `exports/<squad>-agent-skeleton.zip`. **The workshop account expires 72 hours after it was booked.**
    `squads/`, `agents/` and `exports/` are git-ignored, so `git push` does not save them. See [Demo](demo.md).

!!! question "Before you start"
    Which **one** failure mode of your service wakes people up most often, and what is the first piece of evidence the on-call engineer looks for?
