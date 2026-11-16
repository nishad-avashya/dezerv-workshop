# Getting started

!!! time "About 10 minutes of your time (bootstrap then runs about 6 minutes in the background)"

Before the labs, you need three things: an editor connected to your workshop account, a copy of the labs repo, and the shared Dezerv infrastructure deployed into the account.

| Step | What | Time |
|---|---|---|
| 1 | [Open your environment](environment.md): Code Editor, Claude Code, clone the repo | 3 min |
| 2 | [Bootstrap the account](bootstrap.md): preflight, deploy the stack, seed synthetic data | ~6 min (run during the intro talk) |

## Ground rules for the day

!!! danger "Never break these"
    1. **All data is synthetic.** Do not paste real customer data, credentials or source code into the account.
    2. **Never weaken the guardrails.** Don't edit `policy/cedar/30-forbid-mutations.cedar`. Don't set `forbid_ops: false` or `autonomy` above `L1`. Don't detach the policy engine or the interceptor.
    3. **Never print secrets.** `.env` and `.labA.json` hold Cognito client secrets. Don't `cat` them, and don't commit them.
    4. **Agents recommend, they don't act.** No agent ever restarts, scales or rolls back anything.
    5. **Use `make` targets**, not hand-written AWS commands. They are idempotent and tested, and they refuse to run against the wrong account.

## Region

The labs run in **us-west-2**, the region the AWS workshop is validated in. The scripts pin the region and ignore `AWS_REGION` in your shell.
Coverage for Mumbai and Hyderabad is covered in the Production Q&A at the end of the day.
