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

## Milestone 3 persistence and authorization

The process-local store is replaced by an owner-scoped SQL repository:

```text
Bearer token -> validated issuer + subject -> hashed owner key
                                              |
MCP tool -> lifecycle service -> conditional SQL update -> SQLite/PostgreSQL
                                              |
                                   persisted state + evidence + version
```

Local development uses file-backed SQLite. Serverless deployments require a shared PostgreSQL
URL and never fall back to ephemeral local storage when `VERCEL` is present. SQLAlchemy uses
short-lived connections, and every transition checks both the stored version and allowed prior
state so competing instances cannot execute the same confirmation.

The repository persists confirmation, lifecycle state/history, execution receipt, independent
read-back, verifier result, identifiers, UTC timestamps, and terminal outcome. Once a stored row
is terminal, its update predicate fails closed and the repository reports an immutable-outcome
error. Schema creation is currently idempotent at startup; versioned production migrations remain
a later operational hardening task.
