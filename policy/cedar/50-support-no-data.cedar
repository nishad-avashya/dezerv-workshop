// CP-5 (explicit-deny teaching example): db, logs and warehouse tools are forbidden unless the matching *.read scope is present.
// Missing scope tag => `unless` is false => forbid applies (fail closed).

forbid(
  principal is AgentCore::OAuthUser,
  action in [
    AgentCore::Action::"db___find_transactions",
    AgentCore::Action::"db___get_user_state",
    AgentCore::Action::"db___get_error_code"
  ],
  resource == AgentCore::Gateway::"{{GATEWAY_ARN}}"
)
unless {
  principal.hasTag("scope") && principal.getTag("scope") like "*db.read*"
};

forbid(
  principal is AgentCore::OAuthUser,
  action in [
    AgentCore::Action::"logs___query_logs",
    AgentCore::Action::"logs___get_log_patterns"
  ],
  resource == AgentCore::Gateway::"{{GATEWAY_ARN}}"
)
unless {
  principal.hasTag("scope") && principal.getTag("scope") like "*logs.read*"
};

forbid(
  principal is AgentCore::OAuthUser,
  action in [
    AgentCore::Action::"warehouse___query_history"
  ],
  resource == AgentCore::Gateway::"{{GATEWAY_ARN}}"
)
unless {
  principal.hasTag("scope") && principal.getTag("scope") like "*warehouse.read*"
};
