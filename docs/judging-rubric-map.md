# Judging Rubric Map

## Technical implementation
- Alexa+ MCP server using current required MCP version and Streamable HTTP
- MCP App evidence card
- Bedrock + Strands planning/orchestration
- AgentCore Runtime/Gateway/Policy/Browser
- deterministic verification using code-based evaluation / Lambda
- durable async task state
- public fault-injection tests

## Design
- voice-first: Ask → Confirm → Work → Verify → Evidence
- plain-language consumer states
- explicit confirmation for consequential actions
- rich proof card only as an enhancement, not a requirement

## Potential impact
- cancellations
- refunds
- returns
- warranty claims
- other life-admin workflows where false completion has financial consequences

## Quality of idea
- action and verdict are separate trust domains
- the system demonstrates success, contradiction, and uncertainty
- the most memorable behavior is refusing to say "done" when proof is absent
