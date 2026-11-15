# Demo script: __SQUAD__ (service __SERVICE__), 5 minutes

1. **The service and the incident** (30 s). One sentence each. The planted failure: see `profile.yaml` -> `incident.root_cause`.
2. **Live run** (2 min). Send the alert and show the diagnosis with citations.
   - `make deploy-agent NAME=__PRODUCT__` (already done) then invoke:
     `make run-forwarder NAME=__PRODUCT__` and `curl -X POST localhost:8090/alert -d @squads/__SQUAD__/alerts/incident.json`
   - Point at: root cause, impact (count via `total_matching`), the cited deploy/log line, the recommended mitigation (human approved), the PAY ticket. Expected marker: `__MARKER__`.
3. **Governance** (1 min). `make prove-denial SQUAD=__SQUAD__` shows the agent trying a forbidden zone and the Gateway answering `denied due to <policy>`. Name the Cedar rule that fired (`agents/__PRODUCT__/policy/`). The injection is ticket __TICKET__.
4. **Quality** (30 s). Gate report: __GATE__. Say what fails if the prompt is broken (`make break-prompt`).
5. **Path to prod** (1 min). Read the three most important lines of `PATH-TO-PROD.md`: real connectors and owners, the data gaps to fix, the first L1 action you would allow.
