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

## Milestone 2 implementation

The five tools above are implemented as a Streamable HTTP MCP service mounted at `/mcp`
inside the existing FastAPI application. The current lifecycle is:

```text
REQUESTED -> AWAITING_CONFIRMATION -> EXECUTING -> VERIFYING
  -> VERIFIED | NOT_COMPLETED | AWAITING_PROOF
```

`start_resolution` stops at `AWAITING_CONFIRMATION`. Only
`confirm_resolution_action(confirmed=true)` may invoke the demo mutation. It then records
the execution receipt, performs a separate read-back, and passes both into the existing
deterministic verifier. Status, evidence, and list tools are read-only.

Milestone 2 deliberately keeps records in a locked process-local store. This is sufficient
for the deterministic MCP lifecycle and demo acceptance tests, but it is not durable across
Vercel instances or process restarts. Durable storage is the next lifecycle-hardening step;
it is not hidden behind a false persistence claim here.
