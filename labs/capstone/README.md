# Capstone: every squad ships its own on-call agent skeleton (90 min)

Each squad builds an on-call agent **for one of its own services** with the Lab B factory, proves it is governed and tested, demos it (5 minutes), and exports a portable starter.

## Ground rules
1. **Synthetic data only.** No production data, credentials, customer information or proprietary source code in the account. Describe your service; the generator makes mock data.
2. **Autonomy ceiling L0/L1.** The agent observes, diagnoses, recommends and files tickets. Every mutation goes through a decoy tool that policy blocks.
3. **The factory generates; you edit manifests, charters, data and tool code.** The time is for domain thinking, not plumbing.
4. **Scope: ONE failure mode and ONE custom tool.**

## Flow
| Phase | Min | Commands | Checkpoint |
|---|---|---|---|
| 1 Discovery | 10 | Claude asks the discovery questions (see `CLAUDE.md`) and fills `charter.md` | |
| 2 Data and incident | 15 | `make new-squad SQUAD=<squad> PROFILE=<profile>` (or `SCHEMA=my-service.yaml`); `make provision-squad SQUAD=<squad>` | **C1** `make verify-capstone SQUAD=<squad> CHECK=C1` at ~25 min |
| 3 Build | 25 | `make new-agent FROM=squads/<squad>/agent.yaml`; `make deploy-agent NAME=<service>`; optional `make new-tool SQUAD=<squad> TOOL=get_x ARG=some_id`; add forbidden zones; run the incident | **C2** at ~50 min |
| 4 Prove it | 15 | add at least one more replay case; `make eval NAME=<service>`; `make gate NAME=<service>`; `make prove-denial SQUAD=<squad>`; `make export SQUAD=<squad>` | **C3** at ~65 min |
| 5 Demo | 5 each | `DEMO.md` in the export | |

## Your own service
Fill in `capstone/service-sheet.md` (and send it ahead). Or copy a ready profile from `capstone/profiles/`, change the names, the incident story, the error code and the custom tool, and run `make new-squad SQUAD=<squad> SCHEMA=my-service.yaml`. The profile fields are documented by the five examples.
Ready profiles: `kyc-svc`, `mandates-svc`, `ledger-recon`, `notifications-svc`, `nav-ingest`.

## What a squad gets
`squads/<squad>/`: manifest, charter, mock collections, correlated logs (with `commit`, `caller`, `template_id`), deploy history, an alert, a ticket with a planted injection, a red-herring log from another service, 5 past incidents and 2 runbooks for memory, 3 replay cases, and a custom-tool scaffold. The agent runs on **private copies of the generic tools** pointed at that data.

## Scoring (for the demo and an optional prize)
Works end-to-end 30 percent; governed 25; tested 20; realism 15; path to prod 10.

## Download your export
`exports/<squad>-agent-skeleton.zip` contains the manifest, charter, data, replay cases, tools, rendered Cedar, gate report, `DEMO.md`, `PATH-TO-PROD.md` and a redeploy README. **The account expires 72 hours after it was booked.**
