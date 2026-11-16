# Lab B: Agent factory and Go

!!! time "30 minutes"

Lab A built **one** governed agent by hand. Dezerv wants every squad to own agents. A team should get one by
committing a declarative manifest, not by repeating Lab A. Lab B turns the Lab A agent into a template driven by one
file, `labs/B/agent.yaml`, and connects it to a Go stack in both directions:

- **A Go service calls the agent.** `go/alert-forwarder` receives an alert webhook and calls the deployed agent with
  `InvokeAgentRuntime` from `aws-sdk-go-v2`.
- **A Go function is a tool for the agent.** `tools/mandates-go` is a Go Lambda behind the Gateway, governed by Cedar
  rules the factory writes for you.

![Lab B overview](../diagrams/lab-b-overview.drawio)

## Why a factory

If 50 squads each hand-write a prompt, Gateway targets and Cedar, those files drift apart. With a factory, a human
edits and reviews one small manifest (`agent.yaml` plus `charter.md`), and a deterministic renderer generates
everything else. Every generated file says so in its first line:

```text
generated from agent.yaml@<sha> - edit the manifest, not this file
```

The renderer also **fails closed**. A manifest that asks for more autonomy than the workshop allows, a wildcard
forbidden zone, or `forbid_ops: false` is refused before anything is written. You don't have to trust each squad to
remember the guardrails, because the schema holds them.

## What you'll learn

| # | You can... | AgentCore feature |
|---|---|---|
| LB1 | Describe an agent in a manifest and render its prompt, Gateway targets, Cedar, memory and eval gates from it | Gateway, Policy, Memory, Runtime driven by `factory/` |
| LB2 | Drive the factory from a conversation with Claude Code ("use the Dezerv factory to create an agent...") | Build with Skills, `aws-agents` skills |
| LB3 | Invoke a deployed agent from a Go service | Runtime `InvokeAgentRuntime` via `aws-sdk-go-v2` |
| LB4 | Expose a Go function as a governed tool behind the Gateway | Gateway Lambda target (`provided.al2023`) + Cedar |

## Prerequisites

**Lab A is deployed.** Lab B reuses Lab A's stack: its Cognito clients, interceptor and tool Lambdas. Check it from
the repo root:

```bash
make link-labA
```

It should end with `found gateway_id, policy_engine_id, memory_id, runtime_id`.

!!! tip "Behind on Lab A?"
    `make solution-part6` brings your account to the end of Lab A Part 6 in about 10 minutes. It does not run the
    12-minute eval. Lab B doesn't need the eval.

!!! info "Working from a second editor (Build with Skills)?"
    The Build with Skills editor is a separate machine in the **same account**. Clone the repo there, then:

    ```bash
    export EXPECT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
    make link-labA
    ```

    `link-labA` rebuilds `.env` and `.labA.json` from the existing CloudFormation stack and finds the Gateway, policy
    engine, memory and runtime by name. It also regenerates the local synthetic data. Nothing is redeployed. Don't
    open or paste `.env` or `.labA.json`: they hold client secrets.

**Go toolchain.** Check with `go version`. If it is missing:

=== "Install Go"

    ```bash
    make go-setup
    ```

    It uses an existing Go, then Homebrew, then the official tarball (checksum-verified) into `~/.local/go`. `make`
    targets find Go there by themselves. Only if you type `go` by hand in a new terminal do you need
    `export PATH=$HOME/.local/go/bin:$PATH`.

=== "Cannot install Go"

    ```bash
    make go-prebuilt
    ```

    It installs the prebuilt forwarder for your machine to `bin/alert-forwarder`, and `make run-forwarder` uses it.
    For the Go Lambda in Part 3, the factory falls back to `prebuilt/mandates-go-arm64.zip` automatically.

!!! warning "Not yet tested on the Workshop Studio editor"
    The Go tool and forwarder were built and tested on macOS arm64 with Go 1.27. The Linux `make go-setup` tarball
    path is untested, so keep `make go-prebuilt` in mind.

## Parts

| Part | Time | You do | Verify |
|---|---|---|---|
| [1. Render an agent from a manifest](part-1-factory.md) | 8 min | `make new-agent`, `make deploy-agent NAME=payments-gw`, then try to break the manifest | `make verify-labB-part1` |
| [2. A Go service calls the agent](part-2-go-forwarder.md) | 10 min | `make run-forwarder NAME=payments-gw`, `curl` an alert from a second terminal | `make verify-labB-part2` |
| [3. A Go Lambda as a governed tool](part-3-go-tool.md) | 10 min | Add `mandates` under `connectors.custom`, re-render, deploy, ask about U-1042 | `make verify-labB-part3` |
| [4. Forbidden zones](part-4-forbidden-zones.md) | 2 min | Add `service:ledger-svc`, re-render, deploy | `make verify-labB-part4` |

!!! tip "Behind?"
    `make solution-labB-part1` to `make solution-labB-part4` bring your account to the end of each part. They
    **overwrite `labs/B/agent.yaml`** with the reference manifest, so copy your edits somewhere first if you want to
    keep them. See [Catch-up targets](../reference/catch-up.md).

!!! danger "Ground rules"
    Never set `autonomy` above `L1` (`L0` only reads, `L1` also files tickets) and never turn `forbid_ops` off. The workshop schema refuses both, so don't try to
    work around it. Don't hand-edit anything under `agents/`. Change the manifest and re-render.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `make deploy-agent` prints `Go not found: using prebuilt/mandates-go-arm64.zip` | No Go toolchain on this machine | Nothing to fix. The factory uses the prebuilt Lambda zip. If the zip is also missing, it stops with `run make go-setup` |
| `make run-forwarder` says `port 8090 is already in use` | An old forwarder (`go run` can leave its child process on the port) or another tool | `make run-forwarder NAME=payments-gw PORT=9000`, and use the same port in the `curl` |
| Forwarder returns `agent unavailable; escalated to human on-call`, or a 404 `No endpoint or agent found` | The agent could not be invoked. Before the fix this was a stray `AWS_REGION` | The forwarder now takes the region from the runtime ARN. Check that `make deploy-agent NAME=payments-gw` finished (`runtime READY`) |
| A tool still returns old data after you changed the seed data | Lambdas cache data per container | The stack's `DataHash` parameter gives Lab A's Lambdas fresh containers when the data changes. Re-run `make bootstrap` |
| `deploy-agent` stalls, then `policy name '...' is still in use after 60 s` | Policy names are unique across the **account**, and a deleted agent's policy can still hold its name | The factory prefixes names with the product. If you still see it, `make destroy-agent NAME=<old product>` and wait a minute |
| `make new-agent` prints `INVALID agent.yaml:` | The manifest breaks a rule (see [Part 1](part-1-factory.md#4-try-to-break-it)) | Read the line. It names the field. Fix the manifest, not the schema |

More in the [workshop troubleshooting page](../reference/troubleshooting.md).
