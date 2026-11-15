# alert-forwarder

A small Go service that receives an alert webhook and asks the payments on-call agent (AgentCore Runtime) to investigate, then prints the diagnosis. About 170 lines, `aws-sdk-go-v2` (`service/bedrockagentcore`, `InvokeAgentRuntime`, streaming read of the response body), `log/slog` JSON logs.

```
make run-forwarder NAME=payments-gw          # port 8090 (PORT=... to change); or: RUNTIME_ARN=arn:aws:bedrock-agentcore:... go run . -addr :8090
curl -X POST localhost:8090/alert -d @data/alerts/inc-sip-timeout.json
make go-test                                  # five behaviours covered without AWS (fake invoker)
```
No Go on the machine: `make go-prebuilt` installs a prebuilt binary to `bin/alert-forwarder`.

## What to notice
- **Session per alert.** The session id is a hash of alert name, service and window start (`alert-<32 hex>`, at least 33 characters as Runtime requires), so a repeat alert for the same incident reuses the session instead of starting a new investigation.
- **Region comes from the ARN.** The client region is read out of the runtime ARN. A stray `AWS_REGION` in the environment once pointed the client at the wrong region and produced a 404 that looked like an agent problem.
- **Fail safe.** If the agent cannot be invoked, the handler logs an error and returns 502 "escalated to human on-call". It never swallows the alert (NFR-03: if the agent has not acknowledged within the deadline, page a human anyway). In production, that branch calls your paging system.
- **Log fields.** Every line carries `commit` and `caller` (file:line), the same fields as the Lab A service logs, so the forwarder's own logs are citable by the agent (CTX-05).
- **Deadline.** `-timeout` (default 10 min) bounds each alert.

## Mapping to production
`alert source (CloudWatch alarm / PagerDuty webhook) -> this handler (event intake, RUN-01) -> InvokeAgentRuntime -> diagnosis -> ticket + page`. Replace stdout with your incident channel, add authentication on `/alert`, put it behind your normal service platform, and keep the human-paging fallback.

## Not covered
Authentication of callers, retries with backoff, de-duplication across replicas (the session id makes the agent side idempotent, but two replicas would both invoke).
