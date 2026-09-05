# Product Feedback

Complete this as each Amazon/AWS component is actually used.

For every tool/API/SDK include:
- what we used it for
- what worked well
- what needs improvement
- onboarding experience
- whether we would build with it again

Planned sections:
- Alexa AI CLI
- Alexa+ MCP Toolkit
- MCP Apps
- Amazon Bedrock
- Strands Agents
- AgentCore Runtime
- AgentCore Gateway
- AgentCore Policy
- AgentCore Browser
- AgentCore Evaluations

## Amazon DynamoDB / boto3

- Used for: an optional authoritative, owner-scoped durable store for the full CloseLoop lifecycle
  and evidence chain.
- Worked well: one conditional `PutItem` can enforce expected version and allowed predecessor state;
  on-demand capacity and a single-table CloudFormation resource keep the deployment small.
- Needs improvement: Query limit/filter/pagination semantics and condition-failure classification
  require careful cross-reading; the official local emulator also requires a separate Java 17 or
  Docker runtime.
- Onboarding: boto3 plus Moto was straightforward, but the host had no AWS credentials, AWS CLI,
  usable Java runtime, or Docker, so live and official-local validation were unavailable.
- Would use again: yes for this low-contention shared state boundary, with live table validation,
  monitoring, backups, and reconciliation design before production.
