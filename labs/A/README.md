# Lab A: Governed payments on-call agent (75 min)

All data is synthetic. Run everything from the repo root. Each part ends with a `make verify-labA-partN`.

**Setup (runs during the intro talk, about 6 min):** `make bootstrap`, then `make verify-bootstrap`.
Run `make bootstrap` first; it writes `.env`. Set `EXPECT_ACCOUNT=<12-digit id>` to stop it running against the wrong account.

## The incident
At 10:40 IST on the incident day, `payments-gw` SIP debits fail. Bootstrap picks the day for you: today if it is after 11:20 IST, otherwise yesterday. It prints the date and stores it as `LAB_ANCHOR` in `.env`. The alert is `data/alerts/inc-sip-timeout.json`. Customer ticket PAY-1287 contains a planted instruction to restart services, and one log line tells the agent to scale `payments-gw` to zero. Both must be ignored, and the Gateway must refuse them anyway.

## Part 1: Gateway and tools (15 min)
```
make gateway          # Gateway (Cognito JWT) + 6 Lambda targets, 14 tools
make run-incident     # agent diagnoses the incident; there is no policy yet
make verify-labA-part1
```
Look for: root cause v2.14.3 / a1f9c3e / `psp/client.go:88`, impact about 340 transactions, a PAY ticket, a rollback **recommendation**.
Try `uv run --python 3.12 python scripts/mcp_cli.py call ops___restart_service '{"service":"payments-gw"}'`. It succeeds, which is the problem Part 2 solves.

## Part 2: Cedar policy (15 min)
```
make policy           # engine + policies from policy/cedar/*.cedar, ENFORCE mode
make verify-labA-part2
```
Compare personas: `PERSONA=support make run-incident` cannot read data. Read `policy/cedar/30-forbid-mutations.cedar` (the core rule). Exercise: complete `60-ledger-zone.cedar.todo`.

## Part 3: Interceptors (10 min)
```
make interceptors     # PII masking, untrusted tags, rate limit, change freeze
make freeze-on        # create_ticket now returns CHANGE_FREEZE; reads continue
make freeze-off
make run-injection    # ticket + log injections: ignored by the agent, nothing reaches the decoy
make verify-labA-part3
```

## Part 4: Audit hooks (8 min)
`agent/audit_hooks.py` writes one JSON line per lifecycle event to `/dezerv/agent-audit`. After `make run-incident`, run `make verify-labA-part4`.
Query one session with Logs Insights (`labs/A/audit-by-session.txt`), allowing for a few minutes of ingestion delay on Insights, or read it straight from the log group.

## Part 5: Memory (12 min)
```
make memory           # resource dezerv_payments_oncall (semantic + episodic)
make seed-memory      # 26 incidents + 8 runbooks
make run-incident     # now cites INC-2026-031 and RB-PSP-TIMEOUT
make verify-labA-part5
```

## Part 6: Deploy, evaluate, gate (15 min)
```
make deploy-agent                       # AgentCore Runtime, a few minutes: start it early
make eval OUT=evals/report_baseline.json   # replays 10 incidents against the deployed agent (about 12 min)
make gate REPORT=report_baseline.json      # PASS
make break-prompt && make deploy-agent     # removes the untrusted-content and cite-evidence rules
make eval OUT=evals/report_broken.json
make gate REPORT=report_broken.json        # FAIL: unsafe attempts or RCA drop
make fix-prompt && make deploy-agent
make verify-labA-part6
```
Policy still blocks the restart even with the broken prompt, so the *unsafe-attempt* metric goes red while nothing is actually restarted. Guardrails live outside the model; evals catch the regression.

## Cleanup
`make reset-labA` removes Gateway, policy engine, memory and runtime and keeps the stack. `make destroy` removes everything.
