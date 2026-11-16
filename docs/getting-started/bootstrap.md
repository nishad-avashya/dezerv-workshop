# Bootstrap the account

!!! time "About 6 minutes, mostly waiting. Start it during the mental-model talk."

## What you'll set up

`make bootstrap` deploys the shared infrastructure that every Dezerv lab builds on. It:

- deploys the CloudFormation stack `DezervLabA`: 7 Lambdas, a Cognito user pool with the `oncall` and `support` clients, DynamoDB tables for tickets and rate limits, the SSM freeze parameter and the log groups;
- generates the **synthetic** data set: about 4.3k transactions, 200 users, 15 deploys, 40 tickets, 26 past incidents, 8 runbooks and 10 alerts;
- uploads the data to S3 and back-fills about 6.1k `payments-gw` and 500 `kyc-svc` log lines into CloudWatch;
- writes `.env` with resource ids and Cognito client secrets.

!!! info "The incident day is chosen for you"
    The lab incident happens at **10:40 IST**. Bootstrap uses today if it runs after 11:20 IST, and yesterday otherwise.
    It prints the date and stores it in `.env` as `LAB_ANCHOR`. **Always bootstrap on the day**; an old `.env` points the tools at the wrong window.

## Steps

### 1. Pin the account

Every script refuses to run if your credentials are for a different account. Find your account id and export it:

```bash
aws sts get-caller-identity --query Account --output text
export EXPECT_ACCOUNT=<12-digit account id>
```

### 2. Run preflight

`make preflight` is read-only and takes about a minute. It checks:

- tools and internet access to PyPI;
- account and region;
- read access to every service the labs use;
- an IAM simulation;
- a tiny Bedrock call to `us.anthropic.claude-sonnet-4-6`.

```bash
make preflight
```

??? example "Expected output (representative)"
    ```text
    == this machine
    PASS  uv found (/home/participant/.local/bin/uv)
    PASS  make found (/usr/bin/make)
    PASS  python3 found (/usr/bin/python3)
    PASS  curl found (/usr/bin/curl)
    WARN  go not found
    PASS  internet reachable: https://pypi.org/simple/boto3/
    PASS  internet reachable: https://files.pythonhosted.org/
    == AWS identity
    PASS  account 123456789012, principal assumed-role/..., region us-west-2
    == read access to the services the labs use
    PASS  ssm:get_parameter (parameter does not exist yet, access is fine)
    ...
    == can this role create what bootstrap, the Gateway, Policy, Memory and Runtime need?
    WARN  could not simulate IAM permissions (AccessDenied)
    == Bedrock model access
    PASS  can invoke us.anthropic.claude-sonnet-4-6
    == is the account clean?
    PASS  no DezervLabA stack yet (clean)

    RESULT: OK  (… pass, 2 warn, 0 fail)
    ```

`PASS` is fine. `WARN` is worth knowing: the IAM-simulation warning is expected on workshop accounts, and `go` is only needed for Lab B (see [Lab B prerequisites](../lab-b/index.md)). **`FAIL` means the labs will break.**

!!! warning "Any FAIL? Stop here"
    Tell the instructor and give them the exact line. Don't try to work around IAM or model-access failures.

### 3. Bootstrap and verify

```bash
make bootstrap && make verify-bootstrap
```

`verify-bootstrap` checks that:

- the stack is complete;
- the `payments-gw` log group has at least 5000 searchable events;
- every tool Lambda answers a smoke call;
- Cognito issues tokens for both personas.

??? example "Expected output"
    ```text
    PASS  stack DezervLabA complete
          ... 4303 log events searchable so far; CloudWatch is still indexing the backfill, waiting (up to 5 min)
    PASS  log group has >= 5000 events (found 6080)
    PASS  smoke: tool Lambdas invoke
    PASS  Cognito token for oncall
    PASS  Cognito token for support

    RESULT: PASS
    ```

!!! note "Waiting on log indexing is normal"
    CloudWatch takes a few minutes to make back-dated events searchable, so `verify-bootstrap` waits up to 5 minutes by itself.
    Don't re-run `make bootstrap` while it waits: the log stream already exists, so bootstrap would skip the backfill.

## If bootstrap fails

- Run `make bootstrap` once more. It is idempotent.
- If it fails twice, capture the `FAILED <Resource> ... not authorized to perform: <action>` lines and tell the instructor.
  A failed stack create deletes the stack, and bootstrap prints the real cause from the deleted stack's events.

## Using a second editor?

The AWS Track 2 uses a different Code Editor. If it is in the same account, clone the repo there and run `make link-labA` instead of bootstrapping again. It rebuilds `.env` from the existing stack and redeploys nothing.

```bash
git clone https://github.com/nishad-avashya/dezerv-workshop.git ~/dezerv && cd ~/dezerv
export EXPECT_ACCOUNT=<12-digit account id>
make link-labA
```

[Next: Lab A :octicons-arrow-right-24:](../lab-a/index.md){ .md-button .md-button--primary }
