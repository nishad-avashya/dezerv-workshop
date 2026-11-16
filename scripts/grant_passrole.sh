#!/usr/bin/env bash
# grant_passrole.sh: let WSParticipantRole pass the Lab A roles to Lambda and AgentCore, which `make bootstrap` needs.
# Run it ONCE per workshop account, from a terminal that still has the default CodeEditorInstanceRole credentials
# (a fresh terminal; do not paste the WSParticipantRole export first). Idempotent: re-running overwrites the same policy.
#
#   export EXPECT_ACCOUNT=<12-digit account id>   # optional guard
#   make grant-passrole
set -euo pipefail

ROLE="${PARTICIPANT_ROLE:-WSParticipantRole}"
POLICY="PassLabARoles"

arn="$(aws sts get-caller-identity --query Arn --output text)"
acct="$(aws sts get-caller-identity --query Account --output text)"
echo "[grant-passrole] caller  $arn"

if [ -n "${EXPECT_ACCOUNT:-}" ] && [ "$EXPECT_ACCOUNT" != "$acct" ]; then
  echo "[grant-passrole] refusing: credentials are for account $acct but EXPECT_ACCOUNT=$EXPECT_ACCOUNT"; exit 1
fi
case "$arn" in
  *"/$ROLE/"*) echo "[grant-passrole] you are already on $ROLE. Open a NEW terminal (default CodeEditorInstanceRole) and run this there."; exit 1 ;;
esac

doc=$(cat <<JSON
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "PassLabARoles",
    "Effect": "Allow",
    "Action": "iam:PassRole",
    "Resource": [
      "arn:aws:iam::${acct}:role/DezervLabA-*",
      "arn:aws:iam::${acct}:role/dezerv-laba-*"
    ],
    "Condition": {"StringEquals": {"iam:PassedToService": ["lambda.amazonaws.com", "bedrock-agentcore.amazonaws.com"]}}
  }]
}
JSON
)

aws iam put-role-policy --role-name "$ROLE" --policy-name "$POLICY" --policy-document "$doc"
echo "[grant-passrole] ok      $ROLE now has inline policy $POLICY (account $acct)"
echo "[grant-passrole] next    switch to $ROLE (paste the credentials from the workspace home page in a new terminal), then: make preflight"
