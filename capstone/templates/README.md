# __SQUAD__ agent skeleton (service __SERVICE__)

Exported from the Dezerv AgentCore workshop. All data is synthetic.

Contents: `agent.yaml` (manifest), `charter.md`, `data/` (mock collections, logs, deploys, incidents, runbooks), `alerts/`, `replay/` (eval cases), `tools/` (custom tool), `policy/` (rendered Cedar), `evals/report.json`, `DEMO.md`, `PATH-TO-PROD.md`.

## Redeploy in a Dezerv account
1. Clone `dezerv-agentcore-labs` and run Lab A's bootstrap in the target account: `make bootstrap && make solution-part6`.
2. Copy this folder to `squads/__SQUAD__/` in the clone.
3. `make provision-squad SQUAD=__SQUAD__`
4. `make new-agent NAME=__PRODUCT__ FROM=squads/__SQUAD__/agent.yaml && make deploy-agent NAME=__PRODUCT__`
5. `make eval NAME=__PRODUCT__ && make gate NAME=__PRODUCT__`

The factory regenerates the Gateway targets, Cedar and memory from `agent.yaml`; edit the manifest, not the generated files.
