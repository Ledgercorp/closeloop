# Architecture

## Target end-state

```text
User
  ↓
Alexa+
  ↓
CloseLoop MCP add-on
  ↓
Action orchestrator (Bedrock + Strands)
  ↓
AgentCore Gateway → AgentCore Policy → Browser/API action
  ↓
Action receipt

Independent verification plane
  ↓
Read-back / evidence collector
  ↓
Deterministic evaluator
  ↓
PASS / FAIL / INCONCLUSIVE
  ↓
Verified / Not completed / Awaiting proof
  ↓
Alexa+ voice response + MCP App proof card
```

## Planned MCP tools

- `start_resolution`
- `confirm_resolution_action`
- `get_resolution_status`
- `get_resolution_evidence`
- `list_open_resolutions`

There will be no `set_verdict` tool.
