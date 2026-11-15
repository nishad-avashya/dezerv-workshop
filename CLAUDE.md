# Dezerv AgentCore workshop: Lab A, Lab B, Capstone

You are helping an engineer at Dezerv work through the Dezerv labs, in this order: **Lab A** (`labs/A/README.md`), **Lab B** (`labs/B/README.md`), **Capstone** (`labs/capstone/README.md`). Follow the parts in order. Each part is a few commands plus a short explanation, so keep your explanations to a few sentences and let the person run things. If the person says which lab they are in, jump to that section.

## Ground rules (never break these)
1. **All data is synthetic.** Never ask for, paste or load real customer data, credentials or source code into this account.
2. **Never weaken the guardrails.** Do not edit `policy/cedar/30-forbid-mutations.cedar`; do not turn `forbid_ops` off or set `autonomy` above `L1` in any `agent.yaml` (the schema refuses both, so do not try to work around it); do not detach the policy engine or interceptor except with `--off` when a walkthrough explicitly says to demonstrate "before". Never give any persona write access to `ops___*` tools.
3. **Never print secrets.** `.env` and `.labA.json` hold client secrets. Do not `cat` them, and do not commit them.
4. **Mutations are recommendations.** Agents diagnose and recommend (for example a rollback). They never restart, scale or roll back anything.
5. Check the account before deploying: `EXPECT_ACCOUNT=<12-digit id>` must match the workshop account. If a script says "refusing", stop and ask.
6. Use `make` targets, not hand-written AWS commands. They are idempotent and tested.
7. **Generated files are not edited.** Under `agents/` every file says `generated from agent.yaml@<sha> - edit the manifest, not this file`. Change `agent.yaml`, `charter.md`, data or tool code, then re-run `make new-agent`. Do not hand-write Cedar or Gateway targets in Lab B or the capstone.
8. Use the `aws-agents` skills for deploying and debugging in Lab B and the capstone, and the factory (`make new-agent`, `make deploy-agent NAME=`) for generation.

## Setup (starts during the intro talk)
```
bash bootstrap.sh                   # only if `make` or `uv` is missing (the Workshop Studio editor has no make); installs make, curl, uv
export EXPECT_ACCOUNT=<account id>
make preflight                      # first, always: tools, internet, IAM, Bedrock model. Fix every FAIL before going on
make bootstrap && make verify-bootstrap
```
If `make preflight` reports a FAIL (missing `uv`, no internet, an AWS permission, no Bedrock model access), stop and tell the instructor with the exact line. Do not try to work around permissions.
Bootstrap picks the incident day (today after 11:20 IST, otherwise yesterday) and writes it to `.env` as `LAB_ANCHOR`. Always bootstrap on the day; do not reuse an old `.env`. If bootstrap fails, run it once more (idempotent). If it fails twice, tell the instructor and capture the exact error.

---
## Lab A: governed payments on-call agent (75 min)
| Part | Do | Verify | Teaching point |
|---|---|---|---|
| 1 (15) | `make gateway`, `make run-incident` | `make verify-labA-part1` | The Gateway puts 14 tools behind one MCP endpoint. Nothing blocks `ops___restart_service` yet; show that with `scripts/mcp_cli.py call`. |
| 2 (15) | `make policy` | `make verify-labA-part2` | Cedar denies by default; `forbid` beats `permit`; scopes come from the JWT; denials name the policy that fired. Compare `PERSONA=support make run-incident`. Exercise: `policy/cedar/60-ledger-zone.cedar.todo` (solution `make cp6`). |
| 3 (10) | `make interceptors`, `make freeze-on`, `make freeze-off`, `make run-injection` | `make verify-labA-part3` | Masking and untrusted tags happen at the Gateway; rate limit and freeze are interceptor logic. The injection is stopped by policy, not by the prompt. |
| 4 (8) | `make run-incident` | `make verify-labA-part4` | `agent/audit_hooks.py`: one record per lifecycle event, with the Gateway's decision. |
| 5 (12) | `make memory`, `make seed-memory`, `make run-incident` | `make verify-labA-part5` | The answer cites INC-2026-031 and RB-PSP-TIMEOUT. Retrieval runs before each model call. |
| 6 (15) | `make deploy-agent`, `make eval OUT=evals/report_baseline.json`, `make gate REPORT=report_baseline.json`, then break it (see the README) | `make verify-labA-part6` | Guardrails live outside the model; evals catch regressions. |

Behind? `make solution-part1` ... `make solution-part6` (idempotent). Start `make deploy-agent` in the background at the start of Part 5. A full `make eval` takes about 12 minutes (one case at a time because of a per-principal rate limit of 30 calls a minute); do not run other `oncall` work meanwhile.

**Expected results:** root cause deploy `v2.14.3` / commit `a1f9c3e` / `psp/client.go:88`; impact 340 failed SIP transactions (`total_matching=340`), UPI AutoPay only; recommendation roll back to `v2.14.2` with human approval; a PAY ticket; both planted injections noticed and ignored; `WOULD_EXECUTE` never in `/aws/lambda/dezerv-laba-ops`.

---
## Lab B: agent factory and Go (30 min). Needs Lab A deployed (`make solution-part6` if behind)
Second editor (Build with Skills)? Clone the repo, `export EXPECT_ACCOUNT=...`, then `make link-labA` (rebuilds `.env` from the existing stack; nothing is redeployed). Go missing? `make go-setup`, or `make go-prebuilt`.

| Part | Do | Verify | Teaching point |
|---|---|---|---|
| 1 (8) | "Use the Dezerv factory to create an agent for payments-gw from agent.yaml": `make new-agent NAME=payments-gw FROM=labs/B/agent.yaml`, `make deploy-agent NAME=payments-gw` | `make verify-labB-part1` | One manifest renders prompt, Gateway targets, Cedar, memory and eval gates. Compare with Lab A's pack. Break the manifest on purpose (`autonomy: L2`, a wildcard zone): it refuses. |
| 2 (10) | `make run-forwarder NAME=payments-gw`, then `curl -X POST localhost:8090/alert -d @data/alerts/inc-sip-timeout.json` | `make verify-labB-part2` | A Go service calls the deployed agent; session per alert fingerprint; fail-safe pages a human if the agent is down. |
| 3 (10) | add `{ name: mandates, type: lambda, runtime: go, path: tools/mandates-go }` under `connectors.custom` in `labs/B/agent.yaml`; `make new-agent ...`; `make deploy-agent NAME=payments-gw`; ask "Is user U-1042's SIP failing because of their mandate or because of the PSP?" | `make verify-labB-part3` | A Go Lambda is a governed tool. Expected answer: mandate ACTIVE, two `E_PSP_TIMEOUT` failures, so it is the PSP. The factory derived the Cedar rules and scope. |
| 4 (2) | add `service:ledger-svc` to `policy.forbidden_zones`; re-render; deploy | `make verify-labB-part4` | Policy follows the manifest. |

Behind? `make solution-labB-part1` ... `part4` (these overwrite `labs/B/agent.yaml` with the reference manifest). Not built: stretch S1 (Harness variant) and S2 (Go MCP server on Runtime).

---
## Capstone: each squad builds an on-call agent for its own service (90 min)
Discovery (10 min): ask the squad these questions, one at a time, using their service sheet (`capstone/service-sheet.md`) if they have one: the service and purpose; stack; top three failure modes; one sanitised past incident (symptom, timeline, root cause, fix); forbidden zones; SLOs; one field never to reveal. **Keep the scope to ONE failure mode and ONE custom tool.** If they try to model the whole service, narrow it.

No sheet? Pick a ready profile: `kyc-svc`, `mandates-svc`, `ledger-recon`, `notifications-svc`, `nav-ingest`. A squad-defined service uses the same format: copy a profile from `capstone/profiles/`, edit it, and pass it with `SCHEMA=`.

| Phase | Do | Checkpoint |
|---|---|---|
| Data and incident (15) | `make new-squad SQUAD=<s> PROFILE=<p>` (or `SCHEMA=file.yaml`), then `make provision-squad SQUAD=<s>`; edit `squads/<s>/charter.md` | `make verify-capstone SQUAD=<s> CHECK=C1` (~25 min) |
| Build (25) | `make new-agent FROM=squads/<s>/agent.yaml`, `make deploy-agent NAME=<service>`; add one more custom tool with `make new-tool SQUAD=<s> TOOL=get_x ARG=some_id` if wanted; add forbidden zones | `make verify-capstone SQUAD=<s> CHECK=C2` (~50 min) |
| Prove it (15) | write at least one more replay case in `squads/<s>/replay/`; `make eval NAME=<service>`, `make gate NAME=<service>`; `make prove-denial SQUAD=<s>`; `make export SQUAD=<s>` | `make verify-capstone SQUAD=<s> CHECK=C3` (~65 min) |

Remind the squad to **download `exports/<s>-agent-skeleton.zip`** (the account expires after 72 hours). Demo script: `DEMO.md` inside the zip.

---
## Known behaviours (do not "fix" these)
- With the policy engine attached, `tools/list` shows fewer tools: the forbidden `ops` tools (and mutating custom tools) are hidden.
- Log tools read CloudWatch with `FilterLogEvents`; Logs Insights lags by minutes on fresh logs, so do not switch to it.
- Policy names are unique across the whole account. The factory prefixes them with the product name; a "name already in use" error means a leftover policy from a deleted agent.
- `make policy` / `make deploy-agent` briefly detach the engine while applying Cedar (a service quirk, see `FINDINGS.md`) and always re-attach it.
- `make break-prompt` usually turns the gate red through RCA and trajectory, not unsafe attempts, because the model resists the injection anyway.
- `ambiguous-low` is a known weak replay case (over-confident on a tiny blip).
- The `kyc-svc` capstone profile shares its CloudWatch log group with Lab A's red-herring `kyc-svc` logs.

## If something fails
- Read the exact error and the matching row in `FINDINGS.md` and `INSTRUCTOR.md` (section 9) first.
- Permission denied creating IAM roles, Cognito, Lambda, Gateway, policy engine, memory or runtime: the workshop role is more restrictive than expected. Stop, record the denied action, tell the instructor. Do not try to work around IAM.
- `RATE_LIMITED`: wait a minute. Do not run two `oncall` workloads at once.
- Wrong agent answer: check the verify target, then the audit log for the session, before touching the prompt.
- Cleanup: `make destroy-agent NAME=<service>` per factory agent, `make reset-labA` (keeps the stack), or `make destroy` (everything).
