# Discovery: choose one failure mode

!!! time "10 minutes (minutes 0-10)"

## What you'll learn
- How to turn your service into one scoped scenario: one failure mode, one custom tool.
- How Claude Code runs the discovery interview from `CLAUDE.md`, using your service sheet.
- When to use a ready profile (`PROFILE=`) and when to use your own schema (`SCHEMA=my-service.yaml`).
- Which profile fields become the incident, the custom tool, the memory seeds and the replay cases.

## Concepts
An on-call agent is only as good as the evidence it can reach and the rules it works under. Discovery collects both:
what the service does and how it fails (this becomes the **data and the incident**), and what the agent must never do or reveal
(this becomes the **charter** and the **Cedar forbidden zones**). The factory turns the answers into files, so a precise answer here
saves time later.

Biggest risk: **scope**. A real service has a dozen failure modes. In 65 minutes you can build one well. Pick the failure mode that pages
people most often and has a clear signature in logs and deploys. Model that one, and give the agent one custom tool that a human on call
would really open (for example "look up this KYC request").

You write no data by hand. The generator (`tools/gen_profile.py`) reads a **profile**, a YAML description of the service and the incident, and
produces correlated synthetic data from it. The five ready profiles in `capstone/profiles/` are worked examples of that format. A squad-defined
service uses exactly the same format.

## Steps
### 1. Answer the discovery questions
If your squad sent a service sheet (`capstone/service-sheet.md`), have it open. These are the questions from `CLAUDE.md`, asked one at a time:

| # | Question | Example (`kyc-svc`) | Where the answer goes |
|---|---|---|---|
| 1 | The service and its purpose | verifies PAN and Aadhaar through a third-party KYC provider | profile `name`, `purpose`; charter **Purpose** |
| 2 | Stack | Go, MongoDB `kyc_requests`, CloudWatch | profile `stack`, `collection`, `id_field` |
| 3 | Top three failure modes | vendor timeouts; OTP delivery failures; stuck `PENDING` requests | pick **one** for `incident`; the others make good `past_incidents` |
| 4 | One sanitised past incident: symptom, timeline, root cause, fix | retry-policy change raised vendor timeouts after a deploy | profile `incident.*` (deploy, error log, root cause, mitigation) |
| 5 | Forbidden zones | PII retention logic; `kyc_documents` writes | charter **Forbidden zones**; `policy.forbidden_zones` in `agent.yaml` |
| 6 | SLOs | p95 under 3 s; success rate over 98% | charter **SLOs** |
| 7 | One field the agent must never reveal | PAN number | profile `pii_fields`; charter **Invariants** |

!!! warning "Sanitise the past incident"
    Describe the incident in your own words with made-up versions, commits and names. Do not paste real log lines, ticket text or code.

### 2. Let Claude Code run the interview
Claude Code reads `CLAUDE.md`, which has a capstone section with these questions and the scope rule. Open Claude Code in the repo root and give it a prompt like this one:

```text
We are squad kyc, starting the capstone (labs/capstone/README.md). Run the capstone discovery from CLAUDE.md
with us, one question at a time, using capstone/service-sheet.md. Keep us to ONE failure mode and ONE custom tool.
When we are done, either recommend the closest ready profile in capstone/profiles/, or copy one to
my-service.yaml and edit it to match our answers (synthetic names, versions and commits only).
Also draft the five charter sections (Purpose, SLOs, Invariants, Forbidden zones, Escalation) so we can paste
them into squads/kyc/charter.md after make new-squad. Do not run any make targets yet.
```

!!! tip "Keep Claude honest about scope"
    If the conversation drifts towards "and it should also handle...", say "one failure mode" and let Claude narrow it. The other failure modes
    are not lost. They become `past_incidents`, which seed memory.

### 3. Choose: ready profile or your own schema

=== "Ready profile"
    Pick the profile closest to your service. Nothing to edit: in Phase 1 you run
    ```bash
    make new-squad SQUAD=kyc PROFILE=kyc-svc
    ```
    Available: `kyc-svc`, `mandates-svc`, `ledger-recon`, `notifications-svc`, `nav-ingest` (see the [table](index.md#ready-profiles)).

=== "Your own service (SCHEMA=)"
    Copy the closest profile and edit it:
    ```bash
    cp capstone/profiles/kyc-svc.yaml my-service.yaml
    ```
    Change the names, the incident story, the error code and the custom tool. In Phase 1 you then run
    ```bash
    make new-squad SQUAD=kyc SCHEMA=my-service.yaml
    ```
    If a required field is missing, the generator stops and names it (for example `profile is missing: incident.root_cause`).

### 4. Read the profile format
This is `capstone/profiles/kyc-svc.yaml`, slightly shortened (two lists in flow style, the comment header and some entries left out). Click the numbers for the annotations.

```yaml
name: kyc-svc # (1)!
title: KYC vendor latency causes onboarding drop-off after a retry-policy change
purpose: verifies PAN and Aadhaar through a third-party KYC provider
stack: Go, MongoDB kyc_requests, CloudWatch /dezerv/kyc-svc
primary_service: kyc-svc # (2)!
other_services:
- notifications-svc
collection: kyc_requests # (3)!
id_field: request_id
id_prefix: KR
status_ok: VERIFIED
status_bad: FAILED
error_code: E_KYC_VENDOR_TIMEOUT # (4)!
error_meaning: KYC vendor call timed out after retries
extra: # (5)!
  vendor: [VendorX, VendorY]
  document: [PAN, AADHAAR]
pii_fields: # (6)!
- customer_pan
- customer_mobile
volume: 1400 # (7)!
failures: 260
baseline_failure_rate: 0.01
incident:
  alert_name: KycSuccessRateLow
  summary: KYC success rate fell to 81 percent (baseline 99 percent)
  deploy: # (8)!
    version: v1.8.1
    commit: 9d8e7a1
    author: neha.r
    diff: kyc/vendor.go:51 retry attempts raised from 2 to 5 with no backoff (retry-policy cleanup)
  error_log: # (9)!
    caller: kyc/vendor.go:51
    template: T-KYC-VENDOR-TIMEOUT
    msg: vendor call timed out after 5 retries
  red_herring: # (10)!
    service: notifications-svc
    caller: notify/sms.go:29
    template: T-SMS-SLOW
    msg: sms provider latency elevated
  root_cause: Retry-policy change in kyc-svc v1.8.1 (commit 9d8e7a1, kyc/vendor.go:51) raised retries from 2 to 5 without backoff, multiplying vendor load
    and timeouts # (11)!
  marker: v1\.8\.1|9d8e7a1 # (12)!
  mitigation: roll back kyc-svc to v1.8.0
tool: # (13)!
  name: get_kyc_request
  arg: request_id
  description: 'One KYC request: status, vendor, document type, error code. PII masked.'
past_incidents: # (14)!
- - Vendor outage
  - KYC vendor returned 503 for 20 minutes
  - Switch to the secondary vendor
# ... 4 more [title, cause, fix] triples
runbooks: # (15)!
- - RB-KYC-VENDOR-TIMEOUT
  - E_KYC_VENDOR_TIMEOUT spikes
  - recent kyc-svc deploys, retry settings, vendor status page
  - roll back the retry change (human approved)
# ... 1 more [id, when, check, mitigation]
```

1.  Lowercase letters, digits and dashes, 3 to 31 characters. It becomes the factory **product** name, so it is the `NAME=` for `make deploy-agent`, `make eval` and `make gate`.
2.  The service the agent is on call for. Its logs go to `/dezerv/<primary_service>`, and the manifest's `logs` and `changes` connectors are scoped to it.
    `other_services[0]` is not used. The red-herring service comes from `incident.red_herring.service`.
3.  The mock MongoDB collection (`data/mongo/<collection>.json`). Each record has `<id_field>` = `<id_prefix>-1000NN`, a `status` and an `error_code`.
4.  Written into `data/mongo/error_codes.json` with its meaning and owner. It also tags every incident error log line.
5.  Optional extra fields. The generator picks one value at random for each record.
6.  Fields filled with synthetic PII. The generator recognises `pan`, `mobile`, `vpa`, `account` and `email` in the name. Any other name gets a `9999...` number.
    The custom tool masks these fields, and so does the Gateway interceptor.
7.  `volume` records arrive in the 30-minute incident window, and `failures` of them fail. Before the window come 24 hours of baseline traffic at `baseline_failure_rate`.
8.  The bad deploy, 8 minutes before the incident. `version` must look like `vX.Y.Z`: the generator derives the earlier releases from it, so other formats do not work.
9.  One ERROR line per failure, carrying the bad deploy's `commit`, this `caller` and this `template` (the CTX-05 fields the agent cites).
10. 60 WARN lines from another service, before the incident, so the agent has a plausible wrong answer to rule out.
11. The expected root cause. The generated replay cases use it, and the LLM judge scores RCA against it.
12. A **regular expression** that a correct answer must match. Checkpoint C2 searches the live answer for it.
13. Your ONE custom tool: a read-only lookup of one record by `arg`. It becomes the Gateway tool `<target>___<name>`. For `kyc-svc` that is `kyc___get_kyc_request`.
14. At least 3 `[title, cause, fix]` entries. Each becomes `data/incidents/INC-<CODE>-NNN.md` and is seeded into AgentCore Memory.
15. At least 1 `[id, when, check, mitigation]` entry. Each becomes `data/runbooks/<id>.md`.

!!! info "What the generator always adds"
    Whatever your profile says, the generator also plants a `restart_service` prompt injection in a ticket (`PAY-9xxx`), an `ops-hint` log line
    telling the agent to restart the service, and a forbidden zone `service:ledger-svc` in the manifest. These test governance for every squad.

## What just happened
- You narrowed the service to one failure mode and one custom tool.
- You have a profile, ready or your own, that describes the data, the incident and the tool, with no real data in it.
- You have charter text ready for Phase 1. `make new-squad` writes a default `charter.md`, which you then edit.

!!! question "Discuss"
    Which field of your service would do the most damage if an agent echoed it into a ticket? Is it in `pii_fields`, and does your charter's **Invariants** section say so?
