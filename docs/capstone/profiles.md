# Ready profiles

!!! time "2 minutes to choose"

A **profile** is a YAML file that describes a service and one incident. `make new-squad` turns it into your squad's synthetic
data, alert, past incidents, custom tool and replay cases. Pick the profile whose service looks most like yours. The data is
synthetic, so the choice only changes the story your agent investigates. The steps are the same for all five.

## The five profiles

| Profile | Service does | Stack | Incident | Custom tool |
|---|---|---|---|---|
| [`kyc-svc`](#kyc-svc) | Verifies PAN and Aadhaar through a KYC provider | Go, MongoDB | Vendor timeouts after a retry change | `get_kyc_request(request_id)` |
| [`mandates-svc`](#mandates-svc) | Manages UPI AutoPay mandates | Go, MongoDB | Mandates wrongly `REVOKED` after a stricter bank check | `get_mandate_status(event_id)` |
| [`ledger-recon`](#ledger-recon) | Reconciles ledger entries with PSP settlement files | Python, Snowflake, MongoDB | Nightly reconciliation lags after a schema change | `get_recon_run(run_id)` |
| [`notifications-svc`](#notifications-svc) | Sends OTP and transactional SMS and email | Go, MongoDB | SMS provider throttles after a batch-size change | `get_delivery_status(message_id)` |
| [`nav-ingest`](#nav-ingest) | Ingests daily mutual fund NAV files and publishes them | Python, S3, MongoDB | NAV published late after a cron change | `get_ingest_run(run_id)` |

Every profile has the same shape: a bad deploy that caused the incident, error logs, a **red herring** (a second service whose
logs look suspicious but are not the cause), 5 past incidents, 2 runbooks, and one planted prompt injection in a ticket.

### kyc-svc
- **Incident:** KYC success rate falls to 81 percent. Deploy `v1.8.1` raised vendor retries from 2 to 5 with no backoff.
- **Red herring:** `notifications-svc` SMS latency.
- **Good for:** a first pass. It is the running example in every capstone page, so what you see matches the docs.
- **Shares a log group with Lab A.** See the note in the [overview](index.md#ready-profiles).

### mandates-svc
- **Incident:** mandate revocations jump to 17 percent. Deploy `v3.2.0` added a stricter bank-callback signature check.
- **Red herring:** `payments-gw` PSP latency.
- **Good for:** an agent that must resist the obvious answer. It looks like a PSP failure, but the PSP is healthy.

### ledger-recon
- **Incident:** reconciliation runs 3 hours behind its SLA. Deploy `v2.5.0` widened a join and dropped partition pruning.
- **Red herring:** `kyc-svc` vendor latency.
- **Good for:** batch jobs and data teams. The failure is slowness, not errors.

### notifications-svc
- **Incident:** OTP delivery falls to 78 percent. Deploy `v0.9.5` raised the batch size from 50 to 500, and the provider returns 429.
- **Red herring:** `kyc-svc` vendor latency.
- **Good for:** privacy rules. Both the mobile number and the email must stay masked in the evidence.

### nav-ingest
- **Incident:** NAV is not published for 140 schemes by 09:00. Deploy `v1.3.0` moved the file pickup from 06:00 to 09:30.
- **Red herring:** `ledger-recon` slow step.
- **Good for:** data pipelines. It has no PII fields, so the forbidden-zone work is about tools and services rather than data.

## You picked a profile. What is left for you to do?

Choosing the profile does most of the setup. `make new-squad SQUAD=<squad> PROFILE=<profile>` already generates the data,
the alert, the incident, the custom tool, a draft charter, the manifest and 3 replay cases. You don't write any of those.

Your work is the part that needs your judgment:

| Step | What you do | Page |
|---|---|---|
| Make it your service | Edit `squads/<squad>/charter.md`: the invariants, SLOs, forbidden zones and who to escalate to | [Phase 1](phase-1-data.md) |
| Build and deploy | `make new-agent`, `make deploy-agent`, then run the incident and read the answer | [Phase 2](phase-2-build.md) |
| Sharpen the tool | Edit `handler.py` so the tool answers the question your on-call engineer really asks. Keep it read-only | [Phase 2](phase-2-build.md#3-make-the-custom-tool-yours) |
| Add forbidden zones | Add what the agent must never touch to `policy.forbidden_zones` | [Phase 2](phase-2-build.md) |
| Prove it | Write one replay case of your own, run `make eval` and `make gate`, then `make prove-denial` and `make export` | [Phase 3](phase-3-prove.md) |

The factory does the rest: the Lambda, the Gateway target, the Cedar and the memory.

## No profile fits your service

Copy the closest profile, edit it and pass it with `SCHEMA=`:

```bash
cp capstone/profiles/kyc-svc.yaml my-service.yaml
make new-squad SQUAD=<squad> SCHEMA=my-service.yaml
```

[Discovery](discovery.md#4-read-the-profile-format) explains each field in the file. If a required field is missing, the
generator stops and names it.
