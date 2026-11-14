// CP-4: no unbounded reads. limit above 200 is refused (the tools also cap at 200).
forbid(
  principal,
  action in [
    AgentCore::Action::"db___find_transactions",
    AgentCore::Action::"logs___query_logs"
  ],
  resource == AgentCore::Gateway::"{{GATEWAY_ARN}}"
)
when {
  context.input has limit && context.input.limit > 200
};
