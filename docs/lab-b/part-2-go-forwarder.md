# Part 2: A Go service calls the agent

!!! time "10 minutes"

## What you'll learn
- Call a deployed AgentCore Runtime from Go with `InvokeAgentRuntime` (`aws-sdk-go-v2/service/bedrockagentcore`).
- Map one alert to one Runtime session, so a repeat alert for the same incident reuses the session.
- Keep a human in the loop when the agent can't be reached (fail-safe).

## Concepts

Dezerv's services are written in Go, and most AgentCore samples are Python or TypeScript. The integration path for a
Go service is the AWS SDK for Go v2. Its `bedrockagentcore` data-plane client has `InvokeAgentRuntime`, which takes the
runtime ARN, a session id and a JSON payload, and returns the response body as an `io.ReadCloser`.

`go/alert-forwarder` is a small HTTP service (about 170 lines) shaped like a Dezerv Go service. It receives an alert
webhook on `POST /alert`, asks the factory agent from Part 1 to investigate, and prints the diagnosis. In production
the same handler is the **event intake**: alert source (CloudWatch alarm or PagerDuty webhook), then this handler,
then `InvokeAgentRuntime`, then diagnosis, ticket and page.

![Go service calls the agent](../diagrams/lab-b-go-forwarder.drawio)

Three design choices to notice:

- **Session per alert fingerprint.** The session id is `alert-` plus the first 32 hex characters of
  `sha256(alert | service | window_start)`. That makes 38 characters, and Runtime needs at least 33. A repeat alert
  for the same incident lands in the same session instead of starting a new investigation.
- **Region from the ARN.** The client region is read out of the runtime ARN
  (`arn:aws:bedrock-agentcore:<region>:...`), not from `AWS_REGION`. A stray `AWS_REGION` once pointed the client at
  the wrong region, and the 404 it produced looked like an agent problem.
- **Fail-safe.** If the invoke fails, the handler logs an error and returns `502 agent unavailable; escalated to
  human on-call`. It never swallows the alert. In production that branch calls your paging system. Each alert also
  has a deadline (`-timeout`, default 10 minutes).

The heart of the handler, from `go/alert-forwarder/main.go`:

```go title="go/alert-forwarder/main.go (excerpt)"
func fingerprint(alert map[string]any) string {
	key := fmt.Sprint(alert["alert"], "|", alert["service"], "|", alert["window_start"])
	h := sha256.Sum256([]byte(key))
	return "alert-" + hex.EncodeToString(h[:])[:32]
}

func (r runtimeInvoker) Invoke(ctx context.Context, sessionID string, payload []byte) (io.ReadCloser, error) {
	out, err := r.client.InvokeAgentRuntime(ctx, &bedrockagentcore.InvokeAgentRuntimeInput{
		AgentRuntimeArn: aws.String(r.arn), RuntimeSessionId: aws.String(sessionID), Payload: payload,
		ContentType: aws.String("application/json"), Accept: aws.String("application/json"),
	})
	if err != nil {
		return nil, err
	}
	return out.Response, nil
}

// in handleAlert:
	body, err := s.inv.Invoke(ctx, sid, payload)
	if err != nil {
		lg.Error("agent invoke failed: paging a human (fail-safe)", "err", err)
		http.Error(w, "agent unavailable; escalated to human on-call", http.StatusBadGateway)
		return
	}
```

!!! note "What the response handling really does"
    The code reads the response body in 4 KB chunks, but it collects them and prints the diagnosis **once, after the
    whole body has arrived**. If the body is the agent's JSON envelope (`{"answer": ...}`), it prints just the answer.
    You see nothing for a minute or two, and then the full diagnosis. The comments in `main.go` and the HTTP reply
    ("diagnosis streamed to stdout") say "streaming", but the text doesn't appear chunk by chunk.

Each log line is JSON (`log/slog`, on stderr) with `session_id`, `service`, `caller` and `commit`. These are the same
fields as Lab A's service logs, so the agent could cite the forwarder's own logs too.

## Steps

You need **two terminals**. Terminal 1 runs the forwarder and stays busy, and terminal 2 sends the alert.

### 1. Terminal 1: start the forwarder

```bash
make run-forwarder NAME=payments-gw
```

`scripts/run_forwarder.sh` reads `runtime_arn` from `agents/payments-gw/.state.json`, checks that the port is free,
prints the command for terminal 2, and runs `go run .` in `go/alert-forwarder`. Without Go it runs the prebuilt
`bin/alert-forwarder` from `make go-prebuilt`.

??? example "Expected output"
    ```text
    ================================================================================
     Alert forwarder on :8090  ->  fx_payments_gw-<id>
     This terminal stays busy (Ctrl-C stops it). In a SECOND terminal run:

       cd /path/to/dezerv-workshop
       curl -X POST localhost:8090/alert -d @data/alerts/inc-sip-timeout.json

     The diagnosis prints here; it can take a minute or two.
    ================================================================================
    ```
    It is followed by a JSON log line `"msg":"listening","addr":":8090"`.

!!! info "Why port 8090?"
    The workshop editor already uses 8080. To pick another port, run `make run-forwarder NAME=payments-gw PORT=9000`
    and use the same port in the `curl`.

### 2. Terminal 2: send the alert

Run it from the repo root, because the `@data/...` path is relative:

```bash
cd <repo root>
curl -X POST localhost:8090/alert -d @data/alerts/inc-sip-timeout.json
```

The alert is synthetic: `PaymentsFailureRateHigh` on `payments-gw`, "SIP debit failure rate 18% (baseline 0.6%)".
`curl` waits until the agent has finished, which takes 1 to 2 minutes.

??? example "Expected output (representative output)"
    Terminal 2, when the agent is done:
    ```text
    diagnosis streamed to stdout (<n> bytes), session alert-<32 hex>
    ```
    Terminal 1, the JSON logs and then the diagnosis:
    ```text
    {"time":"...","level":"INFO","msg":"invoking agent","session_id":"alert-...","service":"payments-gw","caller":"alert-forwarder/main.go:handleAlert","commit":"dev","alert":"PaymentsFailureRateHigh"}
    ## Summary
    ... deploy v2.14.3 (commit a1f9c3e) ... psp/client.go:88 ... 340 failed SIP transactions ...
    ## Recommended next step (needs human approval)
    Roll back payments-gw to v2.14.2 ...
    {"time":"...","level":"INFO","msg":"diagnosis complete","session_id":"alert-...", ... ,"bytes":<n>}
    ```

### 3. (Optional) Send it again

Run the same `curl` once more. The session id in the reply is identical, because the alert, service and window are
the same, so Runtime routes it to the same session.

## Verify

Run this after the diagnosis has appeared. You can stop the forwarder in terminal 1 first (++ctrl+c++). Verify starts
its own forwarder on port 8098.

```bash
make verify-labB-part2
```
!!! success "You should see"
    ```text
    PASS  go test ./... (alert-forwarder)
    PASS  forwarder accepted the alert
    PASS  Go process printed a diagnosis containing the root-cause marker

    RESULT: PASS
    ```
    Without Go, the first line is `PASS  alert-forwarder binary present (no Go installed)`. The marker is
    `v2.14.3` or `a1f9c3e`. Verify waits up to 10 minutes for the agent.

`make go-test` runs `go vet` and `go test` for both Go modules without AWS. The forwarder tests use a fake invoker
and cover a stable fingerprint, the happy path, a repeat alert reusing the session, the agent-down fail-safe, bad
JSON and parsing the region from the ARN.

## What just happened
- A Go HTTP handler called the deployed factory agent with `InvokeAgentRuntime` from `aws-sdk-go-v2`, signed with the
  editor's AWS credentials, in the region taken from the runtime ARN.
- The session id came from the alert's fingerprint, so the agent side is idempotent per incident.
- The forwarder read the full response, unwrapped `answer`, and printed it. If the invoke had failed, it would have
  answered 502 and escalated to a human.
- The agent itself is unchanged from Part 1. The Gateway, Cedar and interceptor still govern every tool call it makes.

!!! tip "Behind?"
    `make solution-labB-part2` brings you to the end of this part. It runs `solution-labB-part1` and then
    `make go-test`, because the forwarder needs no deployment.

## Troubleshooting
| Symptom | Fix |
|---|---|
| `ERROR: port 8090 is already in use` | An old forwarder is still running (`go run` can leave its compiled child on the port). Stop it, or use `PORT=9000` |
| `ERROR: agents/payments-gw/.state.json not found` | Deploy first: `make new-agent NAME=payments-gw FROM=labs/B/agent.yaml && make deploy-agent NAME=payments-gw` |
| `ERROR: Go not found` | `make go-setup`, or `make go-prebuilt` for the prebuilt binary |
| `curl` warns it can't read the data file, and the forwarder replies `invalid JSON: EOF` | You are not in the repo root. `cd` there, because the `@data/...` path is relative |
| 502 `agent unavailable; escalated to human on-call` | The fail-safe fired. Read the `agent invoke failed` log line in terminal 1 for the AWS error |

!!! question "Discuss"
    The forwarder makes the agent side idempotent per incident, but two replicas of the forwarder would both invoke
    the agent for the same alert. Where would you de-duplicate in Dezerv's stack, and what deadline would you give
    the agent before paging a human anyway?
