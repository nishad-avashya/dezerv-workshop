# Open your environment

!!! time "3 minutes"

## 1. Open the Code Editor

Your instructor gives you an event link and an access code for the AWS workshop.
Join the event, then open the **Feature Deep Dive** workspace from the event dashboard.
It is a browser Code Editor that already has AWS credentials for your workshop account, plus Claude Code, the AgentCore CLI and the `aws-agents` skills.

!!! info "Two workspaces, one machine"
    Every participant has two workspaces: **Feature Deep Dive** and **Build With Skills**.
    They run on the same EC2 machine but hold different files, and both have Claude Code installed.

    | Workspace | Used for |
    |---|---|
    | Feature Deep Dive | [Lab A](../lab-a/index.md) |
    | Build With Skills | [Lab B](../lab-b/index.md) |

    Each lab has a folder with a `README.md` that says how to run it (`labs/A/README.md`, `labs/B/README.md`). Both labs use pre-built `make` commands.

!!! info "One account per squad"
    Each squad gets its own workshop account, which is deleted 72 hours after the event.
    Everything you build in the capstone is exported as a zip, so you can keep it.

## 2. Clone the labs

Open a terminal in the Code Editor and run:

```bash
git clone https://github.com/nishad-avashya/dezerv-workshop.git ~/dezerv
cd ~/dezerv
```

Run every command in these labs **from the repo root** (`~/dezerv`).

## 3. Install `make` and `uv` if they're missing

The Workshop Studio editor has no `make`. `bootstrap.sh` installs `make`, `curl` and `uv`, and checks for `python3`, `git` and `go`. It does not touch AWS.

```bash
bash bootstrap.sh
```

??? example "Expected output"
    ```text
    [bootstrap.sh] ok      make -> /usr/bin/make
    [bootstrap.sh] ok      curl -> /usr/bin/curl
    [bootstrap.sh] ok      uv -> /home/participant/.local/bin/uv
    [bootstrap.sh] ok      python3 -> /usr/bin/python3
    [bootstrap.sh] ok      git -> /usr/bin/git
    [bootstrap.sh] note    go not installed: only Lab B Parts 2-3 need it (make go-setup, or make go-prebuilt)

    Ready. Next:
      export EXPECT_ACCOUNT=<12-digit account id>
      make preflight
    ```
    These are representative paths; yours depend on the editor image.

!!! warning "No root and no passwordless sudo?"
    `bootstrap.sh` stops with `cannot install make curl`. Tell your instructor; don't try to work around it.

## 4. Pin the Claude Code model

Everyone should run the same model. This adds the model settings to `~/.claude/settings.json`, keeps anything already in that file, and creates the file if it is missing:

```bash
python3 - <<'EOF'
import json, os
p = os.path.expanduser("~/.claude/settings.json")
os.makedirs(os.path.dirname(p), exist_ok=True)
s = json.load(open(p)) if os.path.exists(p) else {}
s.setdefault("env", {}).update({
    "CLAUDE_CODE_USE_BEDROCK": "1",
    "AWS_REGION": "us-west-2",
    "ANTHROPIC_MODEL": "us.anthropic.claude-sonnet-4-6",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "us.anthropic.claude-sonnet-4-6",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "us.anthropic.claude-sonnet-4-6",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
})
json.dump(s, open(p, "w"), indent=2)
EOF
```

Restart Claude Code if it was running. In Claude Code, `/status` should show `us.anthropic.claude-sonnet-4-6`.

??? note "What this sets"
    The file ends up with an `env` block like this, and it applies to Claude Code in every folder on this machine:

    ```json
    {
      "env": {
        "CLAUDE_CODE_USE_BEDROCK": "1",
        "AWS_REGION": "us-west-2",
        "ANTHROPIC_MODEL": "us.anthropic.claude-sonnet-4-6",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "us.anthropic.claude-sonnet-4-6",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "us.anthropic.claude-sonnet-4-6",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "us.anthropic.claude-haiku-4-5-20251001-v1:0"
      }
    }
    ```
    A repo's own `.claude/settings.json`, or `claude --model`, can still override it.

## 5. Set up the IAM role

`make bootstrap` needs `WSParticipantRole` to be able to pass the Lab A roles to Lambda and AgentCore. Grant that once, from a new terminal (it starts with the default `CodeEditorInstanceRole`):

```bash
cd ~/dezerv
export EXPECT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
make grant-passrole
```

Then switch to `WSParticipantRole`: open a new terminal, paste the credentials `export` command from the workspace home page, and check:

```bash
aws sts get-caller-identity   # the Arn should contain WSParticipantRole
```

!!! important "`WSParticipantRole` is the role for lab commands"
    Every `make` command in the labs runs as `WSParticipantRole`. The credentials belong to the terminal, so **paste the `export` command again in every new terminal**. A new terminal starts as `CodeEditorInstanceRole`.

    **Claude Code needs the opposite: a terminal on `CodeEditorInstanceRole`.** `WSParticipantRole` can't call the model. If Claude Code stops with an IAM error, see [Troubleshooting](../reference/troubleshooting.md#claude-code-fails-with-an-aws-authentication-error).

## 6. Point Claude Code at the labs

Start Claude Code in the repo and give it this prompt:

```text
Read CLAUDE.md and follow the Dezerv agenda.
```

`CLAUDE.md` gives Claude Code the ground rules, the order of the parts, the commands, the checkpoints and the known behaviours. You can work through the labs by asking it, by following this site, or both.
