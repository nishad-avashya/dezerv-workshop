# Lab A: spike findings from a real account run

Tested 13 Nov 2026 in an Avashya development account (not a Workshop Studio account), region `us-west-2`, with an IAM user that has broad permissions.
Spikes marked **needs re-check** depend on the Workshop Studio role and could not be settled here.

| ID | Question | Result |
|---|---|---|
| V-1 | Can the role deploy the stack and create Gateway, Policy, Memory, Runtime? | **Needs re-check.** Works with a broad IAM user. Gateway, policy engine, memory and runtime all created via the control-plane API. **Workshop Studio dry run (14 Nov 2026): the stack and bootstrap now work, with three fixes** (see "Workshop Studio role" below). Gateway, policy engine, memory and runtime creation under the Code Editor role are **still untested**. |
| V-2 | Can a REQUEST interceptor reject a call and a RESPONSE interceptor rewrite the body? | **Yes, both.** Reject by returning `transformedGatewayResponse` from the REQUEST interceptor (a tool result with `isError: true`). Rewrite the body from the RESPONSE interceptor. Gotcha: on REQUEST events `gatewayResponse` is present but `null`, so test the value, not the key. Needs `passRequestHeaders: true` to read the JWT. |
| V-3 | Time/custom context in Cedar? | Not tested. Freeze stays in the interceptor (works, 5 s SSM cache). |
| V-4 | How are JWT scopes exposed to Cedar? | `principal.hasTag("scope") && principal.getTag("scope") like "*db.read*"` works for Cognito client-credentials tokens (space-separated scope claim). Principal type `AgentCore::OAuthUser`. |
| V-5 | Strands hook event names | `BeforeInvocationEvent`, `AfterInvocationEvent`, `BeforeToolCallEvent`, `AfterToolCallEvent`, `BeforeModelCallEvent` (strands-agents 1.64). `BeforeToolCallEvent.cancel_tool` is how step limits are enforced. |
| V-6 | Memory seeding path | `BatchCreateMemoryRecords` works and records are listable within about 30 s. No LLM extraction wait. Each memory allows **one** semantic strategy with **one** namespace, so the strategy owns `/products/payments-gw` and records go in `/incidents` and `/runbooks` below it. |
| V-7 | DeepEval Bedrock judge credentials | Works with ambient credentials via a custom `DeepEvalBaseLLM` over Bedrock Converse. Under the Code Editor role, `bedrock-runtime:Converse` on the Sonnet 4.6 profile works (preflight PASS; Bedrock is reachable only through the workshop VPC endpoint, which the editor is inside). The DeepEval judge itself has **not** been run there yet. |
| V-8 | Sonnet 4.6 profile id | `us.anthropic.claude-sonnet-4-6` (also `global.` variant). Newer Sonnet 5 / 5.5 profiles exist in this account. |
| V-9 | CloudWatch backfill with old timestamps | Accepted when within 14 days. **Logs Insights is unreliable for this**: it rejects windows that end before the log group was created, and newly back-dated events were not queryable for several minutes (and at one point disappeared from queries while still in storage). The logs tools therefore use `FilterLogEvents` and aggregate in the Lambda. Audit queries in verify scripts also use `FilterLogEvents`. The anchor is chosen at bootstrap time (today 10:40 IST, or yesterday if it is before 11:20 IST). |

## Workshop Studio role (first dry run, 14 Nov 2026, account 113656257293, us-west-2)

Principal: `assumed-role/workshop-resources-ec2-CodeEditorInstanceRole-*` (the Code Editor instance role; presumably identical in every workshop account, which is **unconfirmed**: only one account was tried). Its policies: managed read-only CloudFormation/S3, SSM core, CloudWatch agent, plus `WorkshopManagedPolicy1-4`, `WorkshopCloudWatchPolicy`, two Bedrock deny policies (no bearer-token/API keys; model calls only through the workshop VPC endpoint) and `StackRoleProtection` (protects the stack's own roles). It has `bedrock-agentcore:*`, broad IAM, Lambda, DynamoDB, Cognito, S3, SSM, CloudFormation (stack-scoped; `DezervLabA` is allowed) and `iam:PassRole`.

**What was denied, and what we changed** (each was found by running bootstrap, not by reading policies):

| # | Denied for the editor role | Where it bit | Fix |
|---|---|---|---|
| 1 | `ssm:DescribeParameters` (list-all) | `make preflight` reported a false FAIL | preflight probes `ssm:GetParameter /dezerv/freeze` instead (`ParameterNotFound` = pass). The labs only get/put that one parameter. |
| 2 | `dynamodb:UpdateTimeToLive` | CloudFormation `RateTable` failed, the whole stack rolled back (`OnFailure=DELETE`) | removed `TimeToLiveSpecification` from the template and from `tools/gen_template.py`. The rate-limit key already contains the minute, so TTL was only cleanup. |
| 3 | `dynamodb:BatchWriteItem` | `seed_tickets` (`batch_writer()`) failed with AccessDenied after the stack was created | seed with plain `PutItem` (40 tickets). |

Everything else in bootstrap worked: IAM roles (4) with `CAPABILITY_NAMED_IAM`, 7 Lambdas, Cognito pool/domain/clients, S3 bucket and upload, SSM parameter, `PutItem`, CloudWatch Logs `CreateLogGroup`/`PutLogEvents` on `/dezerv/*` (6080 + 500 events), Cognito tokens for `oncall` and `support`, and all 14 tool smoke calls. Total bootstrap about 6 minutes once the three fixes were in.

Other observations:
- `preflight` cannot run `iam:SimulatePrincipalPolicy` with this role (WARN, harmless). The simulation also passes no resource ARNs, so it would mis-report resource-scoped allows anyway: bootstrap is the real test.
- `make` was **not installed** on the editor. `bash bootstrap.sh` installs make, curl and uv (the Linux path is untested: needs root or passwordless sudo).
- `OnFailure=DELETE` hides the real cause: after a failed create `describe_stacks` says "does not exist". Bootstrap now reads the deleted stack's events by stack id and prints the `FAILED` lines.
- A freshly back-dated log backfill was only partly searchable right after bootstrap (4303 of 6080 events with `FilterLogEvents`, and the incident window returned 0). This is the same effect as V-9 but for `FilterLogEvents`, not only Logs Insights. `verify-bootstrap` now waits up to 5 minutes for the count instead of failing.
- **Still untested under this role:** `make gateway`, `policy`, `interceptors`, `memory`, `deploy-agent` (Runtime), `eval`, Lab B and the capstone.

## Other things learned

- Denials from Cedar name the policy that fired (`...denied due to P30_forbid_mutations_1...`). The audit hook uses this for its `decision.reason`. Good demo material.
- Gateway target `credentialProviderConfigurations: GATEWAY_IAM_ROLE` is required for Lambda targets. The Gateway role needs `AuthorizeAction`, `PartiallyAuthorizeActions`, `GetPolicyEngine` to enforce a policy engine.
- `uv pip install --python-platform x86_64-manylinux_2_28` is needed for `duckdb` (the `manylinux2014` tag does not resolve). The warehouse Lambda is about 66 MB unzipped.
- Runtime env: client secrets are passed as runtime environment variables. Fine for a workshop; use Secrets Manager or Identity for anything real.
- Memory retrieval: a query built from the raw alert JSON ranks generic incidents first. Retrieval is therefore per model call, built from recent evidence, and injects the top 8 incidents so the model can pick the closest precedent. INC-2026-031 was cited in 3 of 3 runs.
- Rate limit is per principal. Running the eval (one `oncall` principal) at the same time as another `oncall` workload trips the 30 calls/min limit. The eval runner is sequential for that reason.
- Data consistency matters: an early version let the warehouse say 1,582 failures while the transaction store said 340, and the agent reported the wrong impact. The generator now derives today's warehouse row from the transactions.

## Deviations from the spec

- Logs tools use `FilterLogEvents`, not Logs Insights (see V-9).
- Transaction store has about 4,300 docs, not about 2,000, because the 30-minute incident window alone has 1,890 SIP transactions (340 failed, about 18 %).
- 26 incident files (25 generic plus INC-2026-031), and INC-2026-031 is unique as the config-change timeout. The spec lists 25 numbered 001 to 025 and also names 031.
- Agent runs the incident from a local process for Parts 1 to 5 and from Runtime for Part 6. `agentcore create`/`deploy` was not used because the CLI deploys through CDK, which was not installed; Runtime is deployed with the control-plane API instead.
- Tracing: `trace_id` falls back to a random id when no OpenTelemetry span is active. ADOT/Observe wiring was not added.
- CP-6 (time-bound filter) is an exercise template only; Cedar cannot inspect the free-form `filter` object, and the template explains the options.

## Eval results (deployed agent, 10 replay cases, Sonnet 4.6, 13 Nov 2026)

| Run | RCA (mean) | Trajectory | Unsafe attempts | PII leaks | Gate |
|---|---|---|---|---|---|
| Baseline | 0.88 | 100 % | 0 | 0 | PASS |
| Broken prompt (2 injection cases only) | 0.50 | 50 % | 0 | 0 | FAIL |

- **The break-it demo does not go red on "unsafe attempts".** Sonnet 4.6 ignored the injected restart instruction even with the untrusted-content rule removed. The gate still fails, on RCA and trajectory. Do not promise the unsafe-attempt story in the demo; show the gate failing and explain the metric. If you want that metric to move, add a more tempting injection case.
- **Known weak case: `ambiguous-low` (RCA 0.0).** The agent states "high confidence" on a 4-failure blip instead of escalating the severity decision. This is a real prompt weakness worth fixing (add an explicit low-volume/ambiguous rule) before the demo, or showing as the "what the eval catches" example.
- Cedar policy also **filters `tools/list`**: with the engine attached, callers see 11 tools, not 14, because the forbidden `ops` tools are hidden. A nice demo moment: the agent cannot even see `restart_service`. The Part 1 verify accounts for this.
- A full eval takes about 12 minutes because it runs sequentially (per-principal rate limit).

## State left in the test account (us-west-2) at the end of the first build (since torn down)

CloudFormation stack `DezervLabA`; artifact bucket `dezerv-laba-artifacts-...`; Gateway `dezerv-laba-gw` + policy engine `dezerv_laba_pe`; memory `dezerv_payments_oncall`; runtime `dezerv_payments_oncall`. About 40 test tickets exist in `dezerv-tickets`. Run `make destroy` to remove everything (EXPECT_ACCOUNT recommended).

## Policy analyzer behaviour (found while building CP-6)

- A new or updated conditional `forbid` is rejected as **"Overly Restrictive: Policy Engine will deny every request..."** while the engine is **attached** to the Gateway. The identical text is accepted when the engine is detached. `labA.py policy` therefore detaches, applies, and re-attaches (and re-attaches even if the apply fails). Cost: a few seconds with no enforcement on re-applies; the first apply in Part 2 happens before attachment, so no gap.
- **Comment lines inside the uploaded statement** also led to rejections. `render_policies()` strips `//` comment lines before upload; the `.cedar` files in the repo keep their comments for readers.
- The working shape is `forbid(principal is AgentCore::OAuthUser, action == ..., resource == ...) when { context.input has X && context.input.X == "..." };`. `unless { ... like ... }` rules on inputs were not re-tested after the comment fix, so treat them as unverified.
- Spec CP-6 ("forbid find_transactions when the filter has no time bound") is not expressible: `filter` is a free-form object. CP-6 is now "ledger-svc is a forbidden zone" (`changes___get_recent_deploys`), which also mirrors Lab B's `forbidden_zones`.
- `list_*` control-plane calls return one page; with 12 policies the last ones were invisible and re-creation conflicted. All list calls now paginate.

## Lab B and capstone findings

- **V-13 (settled): `aws-sdk-go-v2/service/bedrockagentcore` v1.58 has `InvokeAgentRuntime`** with `Response io.ReadCloser`, so streaming reads work. It needs no `Qualifier` (`DEFAULT` is implied).
- **V-14 (settled): the tool name reaches the Lambda in the client context** as `Custom["bedrockAgentCoreToolName"]` = `<target>___<tool>` (Go: `lambdacontext.FromContext(ctx).ClientContext.Custom`, Python: `context.client_context.custom`). Arguments arrive as the event. Both the Go and Python tools use this.
- **V-11 (partly settled):** Go 1.27 installs with Homebrew and cross-compiles a `linux/arm64` Lambda binary with no Docker (`GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go build -tags lambda.norpc`, zipped as `bootstrap`, runtime `provided.al2023`). The Linux tarball path in `scripts/go_setup.sh` is **untested**; prebuilt binaries live in `prebuilt/`.
- **V-12 (settled in this account):** a `provided.al2023` arm64 Lambda was created and invoked through the Gateway. Not tested with the workshop role.
- **Policy names are unique across the account**, not per engine. Two factory agents with the same naming scheme collide; a conflict from a *deleted* policy lingers briefly. Names are now `<product>_<NN>_<file>_<i>`, and a persistent conflict raises instead of being retried silently.
- **A policy that fails validation becomes a hidden tombstone**: it is not returned by `list_policies` but still holds its name. Always read `statusReasons` from `create_policy`'s returned id.
- **`AWS_REGION` in a shell can be wrong** (ours was us-east-1). All scripts pin the region; the Go forwarder takes it from the ARN.
- **Cedar hides forbidden tools from `tools/list`**, so a compliant agent never *calls* a forbidden tool and the audit log never shows a denial. The capstone proves a block with `make prove-denial` (a visible tool with a forbidden argument).
- **Lambda data caches per container**: changed seed data is invisible until containers recycle. The stack now takes a `DataHash` parameter that feeds the Lambdas' environment.
- **Data coherence again**: the spec's Part 3 question (U-1042) needs U-1042 to have PSP failures and an ACTIVE mandate; two of the 340 incident failures now belong to U-1042 (and match ticket PAY-1287, "my SIP failed twice").
- **Lab B verify deviation**: the factory's rendered Cedar must contain every Lab A statement with *at least* the same actions, not be equal to it, because a mutating custom tool legitimately joins the CP-3 forbid.
