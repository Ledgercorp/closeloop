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

## Milestone 4 Alexa+ compatibility boundary

The existing service remains a self-hosted Streamable HTTP MCP server. Alexa+-specific adaptation
is kept at the contract edge:

```text
Alexa+/MCP client -> protected-resource discovery -> bearer-authenticated /mcp
                                                     |
                         closed input/output schemas + five tools
                                                     |
                    lifecycle service -> deterministic verifier
                                                     |
             structured result + generated text fallback + ui:// proof card
```

The server negotiates MCP `2025-11-25` and `2025-03-26`, returns conversation-ready execution,
verification, evidence-summary, and next-step data, and never scripts Alexa's spoken response.
Four tools reference a single read-only MCP Apps resource; the open-resolution list remains a pure
data tool. The card cannot call tools or write state.

The HTTP adapter exposes both the SDK path-suffixed protected-resource metadata endpoint and the
root alias documented by Alexa+. It removes the unsupported challenge only from unauthenticated
`/mcp` 401 responses. It does not implement an OAuth authorization server or claim to provide
Alexa+ account linking. Those remain external prerequisites for live onboarding.

## Milestone 5 AWS persistence boundary

DynamoDB is an optional alternative to the SQL repository and becomes authoritative when
`CLOSELOOP_DYNAMODB_TABLE` is configured:

```text
authenticated owner -> lifecycle service -> shared invariant codec
                                             |              |
                                      SQL repository   DynamoDB repository
                                                       consistent reads
                                                       conditional PutItem
```

One single-region, on-demand table uses `owner_id` as the partition key and `resolution_id` as the
sort key. Every transition is a complete conditional write guarded by the expected version and an
allowed predecessor state. This keeps confirmation, evidence provenance, terminal immutability,
and deterministic-verdict correspondence inside the durable boundary across server instances.

No AWS orchestration or model service was added. The current lifecycle is synchronous and already
has an MCP runtime, authenticated tool boundary, and deterministic verifier. DynamoDB supplies the
missing shared serverless state capability; additional AWS control planes would add complexity
without a current consumer benefit.
