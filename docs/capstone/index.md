# Capstone: an on-call agent for your service

!!! time "90 minutes: 65 minutes of building, then 25 minutes of demos"

## What you will build
An **on-call agent for one service**, built with the Lab B factory. It is the same kind of agent as `payments-gw` in Lab B: it reads
the service's logs, deploys and records, diagnoses an incident and recommends a fix. It never acts on it.

**You or your team** builds one agent for one service. `SQUAD=kyc` is just a name you choose for that project (the workshop's
commands call it a squad). It names your working folder, `squads/kyc/`, which holds everything you build: the charter, the data,
the tool and the test cases. Any short name works, for example your service's name. Each name gets its own folder, so you can try more than one agent side by side. Wherever this guide says "you", it means you or your team.

You start from a ready scenario: a premade service, a planted incident and synthetic data. The factory generates the rest
(the manifest, tool scaffold, Cedar rules, memory and replay cases). On top of that, you make four changes:

1. **The charter:** a short file that tells the agent how to act as the on-call for your service, including what it must never touch and when it hands over to a human.
2. **One edit to the custom tool**, so it answers the question your on-call engineer really asks.
3. **A forbidden zone** (a service or tool the agent stays out of).
4. **One replay case**, an incident you want the agent tested on.

Then you deploy it, run the evals, demo it in 5 minutes and download a starter zip (manifest, charter, tool, Cedar, replay
cases, gate report, `DEMO.md`, `PATH-TO-PROD.md`). The data and the tool are synthetic.

!!! warning "The golden rule: ONE failure mode, ONE custom tool"
    Your agent covers a single way your service breaks, not the whole service. This is the most common way people run out of time.
    Whenever you catch yourself thinking "and it should also handle...", stop. Write it down for later and keep to one.

**How:** pick a profile, edit the charter, deploy, edit the tool and add a zone, then add a replay case, run the evals and
export. The timeline below has the commands.

## Profile
The agent needs a service to investigate, and the workshop allows no real data. A **profile** is a small file that works as
the script for one made-up outage: it describes a service and the incident planted in it. `make new-squad` reads it and generates synthetic logs, records and deploys that look like that service.

You pick one of five ready profiles with `PROFILE=kyc-svc` (see [Ready profiles](../reference/ready-profiles.md)). You do not describe anything yourself.

!!! note "Your own service (optional)"
    If no ready profile fits, copy one, edit it and pass it with `SCHEMA=` instead of `PROFILE=`. Everything after that is the same.
    [Discovery](discovery.md) shows how. `SCHEMA=` is unrelated to the JSON schema that checks `agent.yaml`.

!!! note "Before you start"
    The capstone builds on Lab A's stack and the Lab B factory in the same account. Are you behind? `make solution-part6` brings Lab A to its end.
    **Work in the repo root**, the folder that contains the `Makefile`. Every command in the capstone runs from there, and so does Claude Code.
    The running example on every page is **`SQUAD=kyc PROFILE=kyc-svc`**. Use your own name and profile.

## Ready profiles
Pick one of the five ready profiles in `capstone/profiles/`. Each one is a complete scenario: a planted bad deploy,
correlated error logs, a **red herring** (a second service whose logs look suspicious but are not the cause), a custom tool, 5 past incidents and 2 runbooks.

| Profile | Failure mode (the incident) | Error code | Custom tool | Red herring |
|---|---|---|---|---|
| `kyc-svc` | KYC vendor latency causes onboarding drop-off after a retry-policy change (`v1.8.1`) | `E_KYC_VENDOR_TIMEOUT` | `get_kyc_request(request_id)` | `notifications-svc` SMS latency |
| `mandates-svc` | Spike in UPI AutoPay mandate `REVOKED` after a stricter bank-callback check (`v3.2.0`); looks like a PSP failure but is not | `E_MANDATE_REVOKED` | `get_mandate_status(event_id)` | `payments-gw` PSP latency |
| `ledger-recon` | Nightly reconciliation lag after a schema change drops partition pruning (`v2.5.0`) | `E_RECON_LAG` | `get_recon_run(run_id)` | `kyc-svc` vendor latency |
| `notifications-svc` | OTP SMS delivery failures from provider throttling after a batch-size change (`v0.9.5`) | `E_SMS_THROTTLED` | `get_delivery_status(message_id)` | `kyc-svc` vendor latency |
| `nav-ingest` | Mutual fund NAV file picked up late, so portfolio values are stale (`v1.3.0`); data-pipeline archetype | `E_NAV_MISSING` | `get_ingest_run(run_id)` | `ledger-recon` slow step |

[Ready profiles](../reference/ready-profiles.md) describes each one in full. Do you have your own service? Copy a profile, edit it and pass it with `SCHEMA=`. [Discovery](discovery.md) shows how.

!!! warning "`kyc-svc` shares a log group with Lab A"
    Lab A already backfills red-herring logs into `/dezerv/kyc-svc`. The `kyc-svc` profile writes its own logs into the same group.
    This is expected. The incident window and the `commit`/`template_id` fields keep the two apart.

## Ground rules
1. **Synthetic data only.** No production data, credentials, customer information or proprietary source code goes into the account.
   The generator creates fake data from your profile, so you never type or paste any.
2. **The agent only recommends.** It reads, diagnoses and files tickets, and never restarts, scales or rolls back anything.
   The `autonomy` field in `agent.yaml` sets how much the agent may do: `L0` only reads, `L1` also files tickets. The factory
   refuses anything higher, and refuses `forbid_ops: false`.
3. **The factory generates; you edit** manifests, charters, data and tool code. Do not hand-write Cedar or Gateway targets, and do not edit files under `agents/`.
4. **Scope: ONE failure mode and ONE custom tool.** This is the most common way people run out of time. If you start modelling the whole service, narrow it.

!!! danger "All data is synthetic"
    The PAN numbers, mobile numbers, VPAs and account numbers in `squads/<squad>/data/` come from `tools/gen_profile.py`, which is seeded by your squad name.
    Never replace them with real records, and never paste real logs or code into the account.

## Flow and timeline

![Capstone flow](../diagrams/capstone-flow.drawio)

| Minutes | Phase | Page | Commands | Checkpoint |
|---|---|---|---|---|
| 0-10 | Discovery | [Discovery](discovery.md) | Claude Code asks the discovery questions (from your optional [service sheet](discovery.md#concepts)); pick a ready profile or write your own (`SCHEMA=`) | |
| 10-25 | Data and incident | [Phase 1: data](phase-1-data.md) | `make new-squad`, `make provision-squad`, edit `charter.md` | **C1** at ~25 min |
| 25-50 | Build | [Phase 2: build](phase-2-build.md) | `make new-agent`, `make deploy-agent`, custom tool, forbidden zones, run the incident | **C2** at ~50 min |
| 50-65 | Prove it | [Phase 3: prove](phase-3-prove.md) | one replay case of your own, `make eval`, `make gate`, `make prove-denial`, `make export` | **C3** at ~65 min |
| 65-90 | Demos | [Demo](demo.md) | 5 minutes per project, from `DEMO.md` in the zip | |

Each checkpoint is one command, `make verify-capstone SQUAD=<squad> CHECK=C1|C2|C3`. It prints `PASS`/`FAIL` per check and a hint for each failure.
Instructors use the checkpoints to find anyone who is stuck early, so run them on time even if you think you are fine.

## What you get
`make new-squad` writes `squads/<squad>/` with:

- `agent.yaml` (with a `data:` block that points the tools at your data) and `charter.md`
- fake records for your service (for example `kyc_requests`), an `error_codes` table that explains each error code, and correlated logs for your service (with `commit`, `caller`, `template_id`, `trace_id`) and for a red-herring service
- `deploys.json` with the bad deploy, `alerts/incident.json`, and a ticket with a planted prompt injection
- 5 past incidents and 2 runbooks for memory
- **3 replay cases** (incident, ticket injection, insufficient evidence)
- a Python scaffold for the custom tool

The agent runs on **private copies of the generic Lab A tools** that read your data. The tool names stay the same (`find_transactions`, `get_log_patterns`, and so on).

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
