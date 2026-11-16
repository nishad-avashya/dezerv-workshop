# Open your environment

!!! time "3 minutes"

## 1. Open the Code Editor

Your instructor gives you an event link and an access code for the AWS workshop.
Join the event, then open the **Code Editor** from the event dashboard, as the AWS workshop instructs.
It is a browser IDE that already has AWS credentials for your workshop account, plus Claude Code, the AgentCore CLI and the `aws-agents` skills.

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

## 4. Point Claude Code at the labs

Start Claude Code in the repo and give it this prompt:

```text
Read CLAUDE.md and follow the Dezerv agenda.
```

`CLAUDE.md` gives Claude Code the ground rules, the order of the parts, the commands, the checkpoints and the known behaviours. You can work through the labs by asking it, by following this site, or both.

[Next: bootstrap the account :octicons-arrow-right-24:](bootstrap.md){ .md-button .md-button--primary }
