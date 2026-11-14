// CP-3 (Dezerv core rule): nobody, under any scope, may restart, scale or roll back. forbid always beats permit.
forbid(
  principal,
  action in [
    AgentCore::Action::"ops___restart_service",
    AgentCore::Action::"ops___scale_service",
    AgentCore::Action::"ops___rollback_deploy"
  ],
  resource == AgentCore::Gateway::"{{GATEWAY_ARN}}"
);
