// CP-1: permit every read tool when the caller's scope claim includes the matching *.read scope.
// Default is deny, so anything not permitted here or in CP-2 is refused.

permit(
  principal is AgentCore::OAuthUser,
  action in [
    AgentCore::Action::"logs___query_logs",
    AgentCore::Action::"logs___get_log_patterns"
  ],
  resource == AgentCore::Gateway::"{{GATEWAY_ARN}}"
)
when {
  principal.hasTag("scope") && principal.getTag("scope") like "*logs.read*"
};

permit(
  principal is AgentCore::OAuthUser,
  action in [
    AgentCore::Action::"db___find_transactions",
    AgentCore::Action::"db___get_user_state",
    AgentCore::Action::"db___get_error_code"
  ],
  resource == AgentCore::Gateway::"{{GATEWAY_ARN}}"
)
when {
  principal.hasTag("scope") && principal.getTag("scope") like "*db.read*"
};

permit(
  principal is AgentCore::OAuthUser,
  action in [
    AgentCore::Action::"warehouse___query_history"
  ],
  resource == AgentCore::Gateway::"{{GATEWAY_ARN}}"
)
when {
  principal.hasTag("scope") && principal.getTag("scope") like "*warehouse.read*"
};

permit(
  principal is AgentCore::OAuthUser,
  action in [
    AgentCore::Action::"changes___get_recent_deploys"
  ],
  resource == AgentCore::Gateway::"{{GATEWAY_ARN}}"
)
when {
  principal.hasTag("scope") && principal.getTag("scope") like "*changes.read*"
};

permit(
  principal is AgentCore::OAuthUser,
  action in [
    AgentCore::Action::"tickets___search_tickets",
    AgentCore::Action::"tickets___get_ticket"
  ],
  resource == AgentCore::Gateway::"{{GATEWAY_ARN}}"
)
when {
  principal.hasTag("scope") && principal.getTag("scope") like "*tickets.read*"
};
