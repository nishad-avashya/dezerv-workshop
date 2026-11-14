// CP-2: ticket writes need tickets.write AND the project must be PAY.
permit(
  principal is AgentCore::OAuthUser,
  action in [
    AgentCore::Action::"tickets___create_ticket",
    AgentCore::Action::"tickets___add_comment"
  ],
  resource == AgentCore::Gateway::"{{GATEWAY_ARN}}"
)
when {
  principal.hasTag("scope") && principal.getTag("scope") like "*tickets.write*" &&
  context.input has project && context.input.project == "PAY"
};
