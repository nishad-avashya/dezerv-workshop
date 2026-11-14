#!/usr/bin/env python3
"""preflight.py: can THIS machine and THIS account run the labs? Read-only except one tiny Bedrock call (about 10 tokens).

  make preflight            (set EXPECT_ACCOUNT=<12-digit id> to make a wrong-account mistake impossible)

PASS = fine, WARN = probably fine / worth knowing, FAIL = the labs will break. Exit code is non-zero on any FAIL.
Run it first on a new account: it answers spike V-1 (can the role create what we need?) in about a minute.
"""
import os, re, shutil, subprocess, sys, urllib.request

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError

REGION = os.environ.get("LAB_REGION", "us-west-2")
MODEL = os.environ.get("MODEL_ID", "us.anthropic.claude-sonnet-4-6")
counts = {"PASS": 0, "WARN": 0, "FAIL": 0}


def say(level, msg, hint=""):
    counts[level] += 1
    print(f"{level:5} {msg}" + (f"\n      -> {hint}" if hint and level != "PASS" else ""))


def code(e):
    return e.response.get("Error", {}).get("Code", type(e).__name__) if isinstance(e, ClientError) else type(e).__name__


# ---------------------------------------------------------------- 1. local tools
print("== this machine")
for tool, need, why in [("uv", True, "every make target runs through uv: pip install uv, or https://docs.astral.sh/uv/"), ("make", True, "install make"),
                        ("python3", True, "install Python 3.9+"), ("curl", True, "used by the Lab B verify script"),
                        ("go", False, "Lab B Parts 2-3 build Go code: make go-setup, or use the prebuilt binaries: make go-prebuilt")]:
    p = shutil.which(tool)
    if p:
        say("PASS", f"{tool} found ({p})")
    else:
        say("FAIL" if need else "WARN", f"{tool} not found", why)
for host, why in [("https://pypi.org/simple/boto3/", "uv downloads Python packages from PyPI"), ("https://files.pythonhosted.org/", "uv downloads wheels from here")]:
    try:
        urllib.request.urlopen(urllib.request.Request(host, method="HEAD"), timeout=10)
        say("PASS", f"internet reachable: {host}")
    except urllib.error.HTTPError:
        say("PASS", f"internet reachable: {host}")
    except Exception as e:
        say("FAIL", f"cannot reach {host} ({type(e).__name__})", why + ". No internet from the editor means bootstrap cannot build the Lambdas.")
if os.environ.get("AWS_REGION") and os.environ["AWS_REGION"] != REGION:
    say("WARN", f"AWS_REGION={os.environ['AWS_REGION']} is set in your shell; the labs pin {REGION} and ignore it", "unset AWS_REGION to avoid confusion with other tools")

# ---------------------------------------------------------------- 2. identity
print("== AWS identity")
sess = boto3.Session(region_name=REGION)
cfg = Config(retries={"max_attempts": 2}, connect_timeout=8, read_timeout=20)
try:
    ident = sess.client("sts", config=cfg).get_caller_identity()
except Exception as e:
    say("FAIL", f"no usable AWS credentials ({code(e)})", "run `aws sts get-caller-identity`; in a workshop editor credentials are normally preconfigured")
    print(f"\nRESULT: FAIL ({counts['FAIL']})"); sys.exit(1)
acct, arn = ident["Account"], ident["Arn"]
say("PASS", f"account {acct}, principal {arn.split(':', 5)[-1]}, region {REGION}")
want = os.environ.get("EXPECT_ACCOUNT")
if want and want != acct:
    say("FAIL", f"EXPECT_ACCOUNT={want} but credentials are for {acct}", "you are pointed at the wrong account; stop")
elif not want:
    say("WARN", "EXPECT_ACCOUNT is not set", f"export EXPECT_ACCOUNT={acct}  (bootstrap then refuses any other account)")

# ---------------------------------------------------------------- 3. service access (read-only)
print("== read access to the services the labs use")
probes = [("cloudformation", "list_stacks", {}), ("lambda", "list_functions", {"MaxItems": 1}), ("dynamodb", "list_tables", {"Limit": 1}),
          ("cognito-idp", "list_user_pools", {"MaxResults": 1}), ("s3", "list_buckets", {}), ("logs", "describe_log_groups", {"limit": 1}),
          ("ssm", "describe_parameters", {"MaxResults": 1}), ("iam", "list_roles", {"MaxItems": 1}),
          ("bedrock-agentcore-control", "list_gateways", {}), ("bedrock-agentcore-control", "list_policy_engines", {}),
          ("bedrock-agentcore-control", "list_memories", {}), ("bedrock-agentcore-control", "list_agent_runtimes", {})]
for svc, op, kw in probes:
    try:
        getattr(sess.client(svc, config=cfg), op)(**kw)
        say("PASS", f"{svc}:{op}")
    except Exception as e:
        c = code(e)
        hint = ("AgentCore may not be available in this region/account, or the endpoint is blocked" if isinstance(e, EndpointConnectionError) or "Endpoint" in c
                else "the role cannot even list this service: ask for access (spike V-1)")
        say("FAIL", f"{svc}:{op} -> {c}", hint)

# ---------------------------------------------------------------- 4. can the role CREATE things? (IAM simulation)
print("== can this role create what bootstrap, the Gateway, Policy, Memory and Runtime need?")
need = ["iam:CreateRole", "iam:PutRolePolicy", "iam:AttachRolePolicy", "iam:PassRole", "iam:DeleteRole", "cloudformation:CreateStack", "cloudformation:UpdateStack",
        "lambda:CreateFunction", "lambda:InvokeFunction", "dynamodb:CreateTable", "cognito-idp:CreateUserPool", "cognito-idp:CreateUserPoolDomain",
        "s3:CreateBucket", "ssm:PutParameter", "logs:CreateLogGroup", "logs:PutLogEvents", "bedrock-agentcore:CreateGateway", "bedrock-agentcore:CreateGatewayTarget",
        "bedrock-agentcore:CreatePolicyEngine", "bedrock-agentcore:CreatePolicy", "bedrock-agentcore:CreateMemory", "bedrock-agentcore:CreateAgentRuntime",
        "bedrock-agentcore:InvokeAgentRuntime", "bedrock:InvokeModel"]
src = re.sub(r"^arn:aws:sts::(\d+):assumed-role/([^/]+)/.*$", r"arn:aws:iam::\1:role/\2", arn)       # simulate takes the role, not the session
try:
    res = sess.client("iam", config=cfg).simulate_principal_policy(PolicySourceArn=src, ActionNames=need)["EvaluationResults"]
    bad = [r["EvalActionName"] for r in res if r["EvalDecision"] != "allowed"]
    if bad:
        say("WARN", f"IAM simulation says these actions are not allowed: {', '.join(bad)}",
            "the simulation ignores some org-level guardrails and can be wrong; bootstrap is the real test. If it fails, ask for these actions (V-1) or pre-deploy as admin")
    else:
        say("PASS", f"IAM simulation: all {len(need)} create/invoke actions allowed")
except Exception as e:
    say("WARN", f"could not simulate IAM permissions ({code(e)})", "not a problem by itself: the first `make bootstrap` is the real test")

# ---------------------------------------------------------------- 5. the model
print("== Bedrock model access")
try:
    sess.client("bedrock-runtime", config=cfg).converse(modelId=MODEL, messages=[{"role": "user", "content": [{"text": "Say ok"}]}], inferenceConfig={"maxTokens": 5})
    say("PASS", f"can invoke {MODEL}")
except Exception as e:
    c = code(e)
    say("FAIL", f"cannot invoke {MODEL} ({c})", "enable the model (Bedrock console -> Model access) or set MODEL_ID to a Claude profile this account has; the workshop account offers Sonnet 4.6 and Opus 4.6")

# ---------------------------------------------------------------- 6. leftovers from an earlier run
print("== is the account clean?")
try:
    st = sess.client("cloudformation", config=cfg).describe_stacks(StackName="DezervLabA")["Stacks"][0]["StackStatus"]
    say("WARN", f"stack DezervLabA already exists ({st})", "fine if this is a re-run; `make bootstrap` is idempotent. On a fresh workshop account this should not exist")
except ClientError:
    say("PASS", "no DezervLabA stack yet (clean)")
s3 = sess.client("s3", config=cfg)
for b in (f"dezerv-laba-data-{acct}-{REGION}", f"dezerv-laba-artifacts-{acct}-{REGION}"):
    try:
        s3.head_bucket(Bucket=b); say("WARN", f"bucket {b} already exists", "left over from an earlier run (make destroy removes it)")
    except ClientError:
        pass
try:
    d = sess.client("cognito-idp", config=cfg).describe_user_pool_domain(Domain=f"dezerv-laba-{acct}")["DomainDescription"]
    if d.get("UserPoolId"):
        say("WARN", f"Cognito domain dezerv-laba-{acct} is already in use", "left over from an earlier run; delete it or the stack will fail to create")
except ClientError:
    pass

print(f"\nRESULT: {'FAIL' if counts['FAIL'] else 'OK'}  ({counts['PASS']} pass, {counts['WARN']} warn, {counts['FAIL']} fail)")
sys.exit(1 if counts["FAIL"] else 0)
