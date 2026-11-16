# Discovery: choose one failure mode

!!! time "10 minutes (minutes 0-10)"

## What you'll learn
- How to narrow your service to one scenario: one failure mode and one custom tool.
- How to choose between a ready profile (`PROFILE=`) and your own service (`SCHEMA=my-service.yaml`).
- What a service sheet is, and how Claude Code uses it to run the discovery interview.
- Which of your answers end up in the incident, the charter and the forbidden zones.

!!! warning "Stick to ONE failure mode"
    Everything in this capstone is built around a single failure mode and a single custom tool. Discovery is where you decide which one. If your
    answers start covering several, pick the one that pages people most often and drop the rest. Claude Code will hold you to this too.

## Concepts
**Failure mode.** One specific way your service breaks, for example "the KYC vendor times out after a deploy". A real service has a dozen.
In 65 minutes you can build for one well. Pick the one that pages people most often and leaves a clear trail in logs and deploys.

**Custom tool.** The one lookup your on-call engineer would open first, for example "show me this KYC request". You met custom tools in Lab B.
The agent gets one for your service.

**Profile.** A short YAML file that works as the script for one made-up outage: it describes your service and the incident planted in it. The generator (`tools/gen_profile.py`) reads it
and creates the synthetic logs, records and deploys, so you write no data by hand. There are two ways to get one:

- **A ready profile.** Five premade services in `capstone/profiles/`, each one already complete. Pick the closest. This is the fast path.
- **Your own.** Copy a ready profile and edit it so it describes your service. It uses exactly the same format.

**Service sheet.** A one-page form (`capstone/service-sheet.md`) that you or your team may have filled in before the workshop. It has nine fields about
your service: its purpose, main record, top failure modes, one past incident, forbidden zones, SLOs and one field the agent must never reveal.
It is only the *input* to discovery, so you need it only if you are describing your own service. With a ready profile you can skip it.

**Discovery** is the interview that goes through those same questions. The answers become the planted incident and data (in the profile), and the rules the
agent works under (in the charter and the forbidden zones, as in Lab A and Lab B). A precise answer here saves time later.

## Steps
### 1. Choose: ready profile or your own service

=== "Ready profile"
    Pick the profile closest to your service. Nothing to edit. In Phase 1 you pass its name to the generator.

    | Profile | The service |
    |---|---|
    | `kyc-svc` | KYC verification of PAN and Aadhaar through a vendor |
    | `mandates-svc` | UPI AutoPay mandates and their lifecycle |
    | `ledger-recon` | Nightly reconciliation of ledger entries with PSP settlement files |
    | `notifications-svc` | OTP and transactional SMS and email |
    | `nav-ingest` | Daily mutual fund NAV file ingest and publish |

    To choose, read the list, pick the closest and note its name, for example `kyc-svc`. That is all for now. In Phase 1 you pass it to the generator as `PROFILE=kyc-svc`.
    Not sure? Pick `kyc-svc`, the running example on every page. [Ready profiles](../reference/ready-profiles.md) describes each one in full, including its incident.

=== "Your own service"
    ??? question "Confused about how to write this YAML?"
        A profile is a script for one made-up outage. It is not an AI prompt. The generator is a plain Python script (`tools/gen_profile.py`).
        It copies your values into fixed templates and uses a seeded random generator for the bulk. Your name always gives the same data.
        You give it the facts of your service and the story of the incident. It builds the rest.

        | You write | The generator makes |
        |---|---|
        | `collection`, `id_prefix`, `volume`, `failures` | Fake records, for example `KR-100042`. It picks `failures` of the `volume` records at random and marks them failed with your `error_code` |
        | `pii_fields` | Fake personal values in those records. A field with "pan" in its name gets a PAN-shaped value, and "mobile" gets a phone number |
        | `incident.error_log` and `incident.deploy` | One ERROR line per failed record, carrying your commit and file, plus a deploy `v1.8.1` 8 minutes before the errors start |
        | `incident.red_herring` | 60 noisy log lines from a second service |
        | `incident.alert_name` and `summary` | The alert that starts the incident |
        | `incident.root_cause` | The answer the agent is scored against |
        | `tool` | The scaffold of your custom tool |
        | `past_incidents` and `runbooks` | The agent's memory: 3 or more past incidents and at least 1 runbook |

        The generator also adds a few things on its own: routine log lines and earlier releases, a ticket and a log line that tell the agent to restart things,
        and 3 replay cases. Everything is timed around one incident day, so the logs, deploy and alert tell one story.

        **Let Claude Code write it.** Claude Code can read the format and follow it closely, which is easier than filling in every field by hand.
        Copy a ready profile first, then ask:

        ```text
        Copy capstone/profiles/kyc-svc.yaml to my-service.yaml in the repo root, then rewrite it for our service using our
        discovery answers. Keep every field and the same structure, use synthetic names, versions and commits only, and keep ONE
        failure mode and ONE custom tool. Do not run any make targets.
        ```

        Then read the result. If the generator later says a field is missing, ask Claude Code to fix it.

        Every profile must have a fixed set of required fields. The full list is on the Ready profiles page.

        Don't start from a blank file. Copy a ready profile, then change the names, the story and the error code. The field-by-field format is on the
        [Ready profiles](../reference/ready-profiles.md#the-profile-format) page.

    Copy the closest profile and edit it. [Ready profiles](../reference/ready-profiles.md#the-profile-format) shows the format:
    ```bash
    cp capstone/profiles/kyc-svc.yaml my-service.yaml
    ```
    Run it from the repo root. It creates `my-service.yaml` there, next to the `Makefile`, and leaves the original in `capstone/profiles/` untouched. Keep your copy in the repo root, because that is where Phase 1 looks for it.
    Change the names, the incident story, the error code and the custom tool. In Phase 1 you pass the file to the generator with `SCHEMA=my-service.yaml`.
    If a required field is missing, the generator stops and names it (for example `profile is missing: incident.root_cause`).

### 2. Answer the discovery questions
There are seven questions. None asks about your tech stack, because nothing from your real stack is deployed. You can either:

- **answer them yourself**, with your service sheet open if you have one, or
- **let Claude Code interview you**, one question at a time (step 3 has the prompt).

The questions are the same either way. The example column uses `kyc-svc`. If you chose a ready profile, read the example as your own answers.
The last column shows where each answer ends up. Names in code font are fields of the profile.

| # | Question | Example (`kyc-svc`) | Where the answer goes |
|---|---|---|---|
| 1 | The service and its purpose | verifies PAN and Aadhaar through a third-party KYC provider | profile `name`, `purpose`; charter **Purpose** |
| 2 | The main record your on-call looks up, and its ID | `kyc_requests`, ID `request_id` | profile `collection`, `id_field`; the custom tool |
| 3 | Top three failure modes | vendor timeouts; OTP delivery failures; stuck `PENDING` requests | pick **one** for the incident; the others become past incidents (see the tip below) |
| 4 | One sanitised past incident: symptom, timeline, root cause, fix | retry-policy change raised vendor timeouts after a deploy | profile `incident.*` (deploy, error log, root cause, mitigation) |
| 5 | Forbidden zones | PII retention logic; `kyc_documents` writes | charter **Forbidden zones**; `policy.forbidden_zones` in `agent.yaml` |
| 6 | SLOs | p95 under 3 s; success rate over 98% | charter **SLOs** |
| 7 | One field the agent must never reveal | PAN number | profile `pii_fields`; charter **Invariants** |

The **charter** is the file of rules for your agent. You edit it in Phase 1.

!!! warning "Sanitise the past incident"
    Describe the incident in your own words with made-up versions, commits and names. Do not paste real log lines, ticket text or code.

### 3. Let Claude Code run the interview
Claude Code reads `CLAUDE.md`, as in the earlier labs. Its capstone section holds these questions and the scope rule. Open Claude Code in the repo root and give it a prompt like this one:

```text
We are starting the capstone (labs/capstone/README.md). Run the capstone discovery from CLAUDE.md
with us, one question at a time, using capstone/service-sheet.md. Keep us to ONE failure mode and ONE custom tool.
When we are done, either recommend the closest ready profile in capstone/profiles/, or copy one to
my-service.yaml and edit it to match our answers (synthetic names, versions and commits only).
Finish with a short summary of our seven answers. Do not run any make targets.
```

!!! tip "Keep Claude honest about scope"
    If the conversation drifts towards "and it should also handle...", say "one failure mode" and let Claude narrow it. The other failure modes
    are not lost. They become **past incidents** (earlier problems of the same service), which the agent recalls from memory as in Lab A.

## What just happened
- You narrowed the service to one failure mode and one custom tool.
- You have a profile, ready or your own, that describes the data, the incident and the tool, with no real data in it.
- You have your seven answers written down. In Phase 1 they go into the charter.

!!! question "Discuss"
    Which field of your service would do the most damage if an agent echoed it into a ticket? Is it in `pii_fields`, and does your charter's **Invariants** section say so?
