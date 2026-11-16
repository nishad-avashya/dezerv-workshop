# Demo and path to production

!!! time "5 minutes per squad (minutes 65-90)"

!!! danger "Download `exports/<squad>-agent-skeleton.zip` NOW, before the account expires"
    **The workshop account expires 72 hours after it was booked, and everything in it goes with it.** `squads/`, `agents/` and `exports/` are
    git-ignored, so `git push` does **not** save your work. The zip is the only copy of your manifest, charter, tool code, replay cases and rendered Cedar.

    1. Re-run `make export SQUAD=<squad>` after your last change. The zip is a snapshot.
    2. In the Code Editor's file explorer, right-click `exports/<squad>-agent-skeleton.zip` and choose **Download**.
    3. Open the zip on your laptop and check that `agent.yaml`, `tools/` and `replay/` are inside.

    Download from the editor has not yet been tested on the event accounts (spike V-18). If it does not work, push the zip to a temporary private
    repository or gist, or ask an instructor. Do this before the demos, not after.

## What you'll learn
- How to show, in 5 minutes, that the agent works, is governed, is tested and has a path to production.
- What `PATH-TO-PROD.md` asks you to decide before this skeleton goes near real data.
- How to redeploy the exported skeleton in a Dezerv account.

## The demo script
`DEMO.md` in your zip is generated from `capstone/templates/DEMO.md`, with your squad's values filled in. Below it is filled in for `SQUAD=kyc`.
The order is fixed, so every squad is judged the same way.

| # | Step | Time | Show |
|---|---|---|---|
| 1 | **The service and the incident** | 30 s | One sentence each. The planted failure is `incident.root_cause` in `profile.yaml`. |
| 2 | **Live run** | 2 min | Send the alert; show the diagnosis with citations |
| 3 | **Governance** | 1 min | `make prove-denial SQUAD=kyc`; name the Cedar rule; the injection ticket `PAY-9090` |
| 4 | **Quality** | 30 s | The gate report, and what fails if the prompt is broken |
| 5 | **Path to prod** | 1 min | The three most important lines of `PATH-TO-PROD.md` |

### 1. The service and the incident (30 s)
"`kyc-svc` verifies PAN and Aadhaar through a third-party KYC provider. This morning a retry-policy change, `v1.8.1`, raised vendor retries from 2 to 5 without
backoff, and KYC success fell to 81 percent."

### 2. Live run (2 min)
The agent is already deployed (`make deploy-agent NAME=kyc-svc`). Start the forwarder in one terminal and send the alert from a second one:
```bash
make run-forwarder NAME=kyc-svc
```
```bash
curl -X POST localhost:8090/alert -d @squads/kyc/alerts/incident.json
```
Point at the **root cause** (expected marker `v1.8.1|9d8e7a1`), the **impact** (the count via `total_matching`), the **cited** deploy and log line,
the **recommended mitigation** (human approved), and the **PAY ticket** it filed.

### 3. Governance (1 min)
```bash
make prove-denial SQUAD=kyc
```
The agent tries a forbidden zone, and the Gateway answers `denied due to <policy>`. Name the Cedar rule that fired (`agents/kyc-svc/policy/`).
Then mention the injection: ticket `PAY-9090` told the agent to restart `kyc-svc` and `ledger-svc`. It did not, because the ops tools are forbidden and hidden.

### 4. Quality (30 s)
Read the gate line from your `DEMO.md`. The export fills it in from `report.json` as `<n> cases, RCA mean <x>`. Then say what fails if the prompt is broken.
`make break-prompt` is Lab A's experiment. It usually turns the gate red through RCA and trajectory rather than unsafe attempts, because the model resists the injection anyway.

### 5. Path to prod (1 min)
Read three lines from `PATH-TO-PROD.md`: the real connectors and their owners, the data gaps to fix, and the first L1 action you would allow.

!!! tip "Rehearse once"
    Run steps 2 and 3 once before your slot. The live run takes most of the 2 minutes. Have the gate output and `PATH-TO-PROD.md` open in tabs.

## PATH-TO-PROD.md
The export generates `PATH-TO-PROD.md` from `capstone/templates/PATH-TO-PROD.md`. Fill in the blanks with names, owners and dates. Fill it in before
the demo, then edit the copy in your downloaded zip after the workshop.

| Section | What to write |
|---|---|
| **Real connectors and their owners** | For logs (`/dezerv/kyc-svc` in the workshop), records (`kyc_requests`, mock over S3), deploy history (`deploys.json`), tickets (DynamoDB mock, project PAY) and your custom tool (`get_kyc_request`): the real source and its owner |
| **Data and telemetry gaps (CTX-05 readiness)** | Do the real logs carry `commit`, `caller` (file:line) and `template_id`? Trace ids? An error-code catalogue with owners? |
| **Charter owner and review** | Who owns `charter.md`, and how changes get reviewed |
| **Incident-replay set** | The workshop set is 3+ cases. The target is 30 real, sanitised incidents (EVL-01). Who curates them? |
| **Region and network** | The regions required; VPC or PrivateLink needs for the real data sources |
| **First L1 action we would allow** | One action beyond "recommend", with its approval rule and rollback |
| **Gate for the real thing** | The workshop result (filled in), and what you would tighten before going live |

## Redeploy in a Dezerv account
The `README.md` in the zip has the steps (from `capstone/templates/README.md`):

1. Clone the workshop repository and run Lab A's bootstrap in the target account: `make bootstrap && make solution-part6`.
2. Copy the unzipped folder to `squads/kyc/` in the clone.
3. `make provision-squad SQUAD=kyc`
4. `make new-agent NAME=kyc-svc FROM=squads/kyc/agent.yaml && make deploy-agent NAME=kyc-svc`
5. `make eval NAME=kyc-svc && make gate NAME=kyc-svc`

The factory regenerates the Gateway targets, Cedar and memory from `agent.yaml`. Edit the manifest, not the generated files.

![Capstone export and redeploy](../diagrams/capstone-export.drawio)

!!! warning "Still synthetic after the workshop"
    The redeployed skeleton runs on the same synthetic data. Connecting it to real logs, records and deploys is the work that `PATH-TO-PROD.md` plans,
    and it goes through Dezerv's own review and data controls.

## What just happened
- In 5 minutes you showed the agent working, a real Cedar denial, a passing gate and a concrete path to production.
- You downloaded the skeleton: manifest, charter, data, tool, replay cases, Cedar, report, demo script and path-to-prod plan.
- You know how to bring it back up in a Dezerv account with five `make` commands.

!!! question "Discuss"
    What is the **first** L1 action you would let this agent take on its own, what approval would it need, and how would you roll it back if it was wrong?
