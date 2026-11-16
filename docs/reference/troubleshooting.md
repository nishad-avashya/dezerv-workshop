# Troubleshooting

Start with the exact error text. Each lab page has its own troubleshooting section; this page collects the problems that cut across labs.

!!! danger "Permission denied on IAM, Cognito, Lambda, Gateway, policy engine, memory or Runtime?"
    The workshop role is more restrictive than expected. **Stop**, note the denied action and tell the instructor.
    Don't widen permissions or work around IAM.

## Claude Code

### Claude Code fails with an AWS authentication error

```text
AWS authentication failed · refresh your AWS credentials (SSO sign-in, access keys, API key or proxy
token) and retry · if credentials are current, check AWS permissions and model access · API Error:
403 {"Message":"User: arn:aws:sts::<account>:assumed-role/WSParticipantRole/Participant is not
authorized to perform: bedrock:InvokeModelWithResponseStream on resource:
arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-sonnet-5 because no identity-based
policy allows the bedrock:InvokeModelWithResponseStream action"}
```

**Cause:** Claude Code is running in a terminal that has the `WSParticipantRole` credentials pasted in. That role can run the labs but isn't allowed to call the Bedrock model. Claude Code works from a terminal on the default `CodeEditorInstanceRole`.

**Fix:**

1. Exit Claude Code.
2. Open a **new terminal**. It starts on `CodeEditorInstanceRole`. Do not paste the credentials.
3. Check the role:

    ```bash
    aws sts get-caller-identity   # the Arn should contain CodeEditorInstanceRole
    ```

4. Start Claude Code again from `~/dezerv`.

Keep a second terminal with the `WSParticipantRole` credentials pasted for the `make` commands.

If the error still appears on `CodeEditorInstanceRole`, tell the instructor with the exact error text.

## Cost breach error

When the account goes over its cost limit, commands and Claude Code start failing with IAM errors (`AccessDenied`, `not authorized to perform ...`), even though they worked before.

**Fix:** do the [IAM setup from the environment steps](../getting-started/environment.md#4-set-up-the-iam-role) again:

1. In a new terminal on `CodeEditorInstanceRole` (no credentials pasted), run `make grant-passrole`.
2. Open another new terminal, paste the `WSParticipantRole` credentials from the workspace home page, and check with `aws sts get-caller-identity`.

If it still fails, tell the instructor with the exact error text.

## Setup

| Symptom | Cause | Fix |
|---|---|---|
| `bash: make: command not found` | The Workshop Studio editor has no `make` | `bash bootstrap.sh` |
| `refusing: expected account X, credentials are for Y` | The `EXPECT_ACCOUNT` guard did its job | Check which account your credentials are for |
| `make bootstrap` prints `FAILED <Resource> ... not authorized to perform: <action>` | The role lacks an action the stack needs | Record the action and tell the instructor. The failed stack is deleted automatically |
| `verify-bootstrap`: `log group has >= 5000 events (found 4303)` | CloudWatch is still indexing the back-dated logs | It waits up to 5 min on its own. Don't re-run `make bootstrap` |
| Logs tools return nothing | Wrong incident day, or a stale `.env` | Re-run `make bootstrap` *on the day* |
| Stray `AWS_REGION=us-east-1` in your shell | Other tools trust it | The lab scripts pin us-west-2 (`LAB_REGION` overrides). Unset `AWS_REGION` anyway |

## Gateway, policy and interceptors

| Symptom | Cause | Fix |
|---|---|---|
| `RATE_LIMITED` | More than 30 calls a minute for one principal | Wait a minute. Don't run two `oncall` workloads (for example an eval and a live demo) at once |
| `tools/list` shows 11 tools, not 14 | With the policy engine attached, the Gateway hides tools the caller can never use | Expected behaviour |
| Everything is allowed after a policy edit | The engine is detached (for example after a failed apply) | `make policy`, which re-attaches even on failure |
| `ConflictException ... already exists` | A policy deleted a moment ago still holds its name | Re-run; the script retries |
| `UPDATE_FAILED` / "Overly Restrictive" on a policy | Analyzer rejection (a service quirk) | Run `make policy`, which detaches, applies and re-attaches |
| Gateway 5xx right after create | Targets are not READY yet | Wait; `make gateway` waits for READY |

## Agent, memory and evals

| Symptom | Cause | Fix |
|---|---|---|
| Wrong agent answer | Usually tools or data, not the prompt | Run the part's `verify` target, then read the audit log for the session, before touching the prompt |
| Memory run does not cite INC-2026-031 | Retrieval and model variance | Re-run; check `make verify-labA-part5` |
| Eval case errors with `RATE_LIMITED` | Another `oncall` workload is running in parallel | Run evals on their own (the runner is sequential) |
| Gate fails on one case | Model runs vary | Re-run only that case with `--cases` (see [Part 6](../lab-a/part-6-evals.md)) before changing the prompt |

## Lab B and the capstone

| Symptom | Cause | Fix |
|---|---|---|
| `deploy-agent NAME=` stalls, then "policy name ... still in use" | Policy names are unique across the **account**; a deleted agent's policy still holds the name | `make destroy-agent` the old agent and wait a minute |
| Go forwarder: "agent unavailable" / 404 | Wrong client region | The forwarder takes the region from the Runtime ARN; check `NAME=` |
| Port already in use | A previous forwarder is still running | `lsof -ti :8090 \| xargs kill`, or `make run-forwarder NAME=payments-gw PORT=8091` |
| `go: command not found` | No Go toolchain | `make go-setup`, or `make go-prebuilt`. The deployer uses the prebuilt Lambda zip automatically |
| Data changed but a tool returns old data | Lambdas cache data per container | Re-run `make bootstrap`; it passes a data hash so the Lambdas get fresh containers |
| Capstone agent can't see the custom tool | Custom tools need the `payments/custom.read` scope | Run `make bootstrap` once (it adds the scope) |
