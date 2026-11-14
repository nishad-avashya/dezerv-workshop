// CP-6 (solution): ledger-svc is a forbidden zone. The agent may read payments-gw and kyc-svc history, never ledger-svc.
// Same idea as the `forbidden_zones` list in Lab B's agent.yaml, which renders one rule like this per zone.
// Analyzer notes (found in testing): write it as `when { has && == }`, and scope the principal. `unless`+`like` rules and a rule on
// db___get_user_state were rejected as "Overly Restrictive" even though they are logically fine.
forbid(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"changes___get_recent_deploys",
  resource == AgentCore::Gateway::"{{GATEWAY_ARN}}"
)
when {
  context.input has service && context.input.service == "ledger-svc"
};
