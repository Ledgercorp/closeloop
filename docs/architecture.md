# Architecture

## Implemented architecture

CloseLoop is a persistent responsibility layer for Alexa+ delegated outcomes. Subscription cancellation is the sole executable workflow. `ResolutionType` also models REFUND, RETURN, WARRANTY_CLAIM, SERVICE_REQUEST, and APPOINTMENT for future contracts; those integrations are roadmap only.

```text
Alexa+ / authenticated MCP
        │ create, confirm, retrieve, recheck
        ▼
Owner-scoped ResolutionRecord (SQL or DynamoDB)
  intent · lifecycle · action claim · state history
  last/next check · bounded count · evidence-attempt history
        │
        ├── cancellation provider action (receipt is a claim)
        ├── independent account read-back (fresh evidence)
        └── deterministic cancellation verifier
                 PASS / FAIL / INCONCLUSIVE
                 Verified / Not completed / Awaiting proof

AWAITING_PROOF stays open → bounded recheck → immutable terminal outcome
```

SQL and DynamoDB persist the same record contract; version and state conditions serialize updates. An inconclusive result appends evidence history and schedules an explicit bounded next check. `recheck_resolution` only reads evidence and never repeats the provider action. The demo advances simulated time and recreates a service instance over SQLite; it does not implement a production scheduler. DynamoDB behavior is Moto-tested, not live AWS-tested. Alexa+ is locally MCP-compatible, not live Alexa+-tested.

## MCP tools

- `start_resolution`
- `confirm_resolution_action`
- `get_resolution_status`
- `get_resolution_evidence`
- `list_open_resolutions` (unresolved work only)
- `list_recent_resolutions` (bounded owner-scoped terminal history)
- `recheck_resolution` (explicit follow-up observation; no action replay)

The owner-scoped resolution list is authoritative cross-session memory. Status returns action outcome, verifier state, last/next check time, attempts, and consumer-safe explanation. There is no agent-controlled verdict tool.

## Milestone 2 implementation

The seven tools above are implemented as a Streamable HTTP MCP service mounted at `/mcp`
inside the existing FastAPI application. The current lifecycle is:

```text
REQUESTED -> AWAITING_CONFIRMATION -> EXECUTING -> VERIFYING
VERIFYING -> VERIFIED | NOT_COMPLETED
          \-> AWAITING_PROOF -> VERIFYING (bounded recheck)
          \-> VERIFYING (bounded recovery after interrupted read-back)
```

`start_resolution` stops at `AWAITING_CONFIRMATION`. Only
`confirm_resolution_action(confirmed=true)` may invoke the demo mutation only with a valid trusted
confirmation attestation bound to the authenticated owner, exact resolution, and canonical action
digest. It then records the execution receipt, performs a separate read-back, and passes both into
the deterministic verifier. Status, evidence, and list tools are read-only.

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
MCP client (Alexa+ target) -> protected-resource discovery -> bearer-authenticated /mcp
                                                     |
trusted confirmation attestation -> closed schemas + seven tools
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

Consequential confirmation uses a product-core `ConfirmationAttestationVerifier`. The production
HMAC-JWS adapter is enabled only when a dedicated secret, trusted issuer, and audience are all
configured; otherwise it denies every confirmation. The external confirmation authority—not the
MCP agent—must bind human approval to the bearer-derived owner key and the server-computed,
versioned canonical action digest. After signature, claim, freshness, and expiry verification, the
service stores bounded attestation provenance in the existing JSON lifecycle history and
conditionally writes `EXECUTING` before invoking the provider. SQL and DynamoDB therefore share the
same single-use, cross-instance replay boundary without a database schema change. Pre-v1 records
without an explicit confirmation contract fail closed and require an intentional migration; no
live data migration was performed because CloseLoop has no provisioned production store.

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

## Persistent resolution lifecycle (2026-09-24)

`AWAITING_PROOF` is now an open state, not a terminal outcome. `ResolutionRecord` persists the modeled resolution type, last and next check time, bounded check count, final resolution time/reason, and historical independent evidence/results. Old SQL tables receive additive nullable columns on schema initialization; older records are read with cancellation defaults. DynamoDB mappings use the same serialized record contract. `VERIFIED` and `NOT_COMPLETED` remain immutable.

A recheck claims `VERIFYING` through an owner/version/state-conditional save before read-back. Scheduled calls must present the exact `next_check_at` token; duplicate or stale schedules fail. User-triggered MCP rechecks may bypass the wait time but not the attempt budget. Rechecks call only the independent provider read path. A stale `VERIFYING` record can be resumed after five minutes without replaying the original action. Four total observations are allowed, including the initial check; exhaustion leaves the task open with no next scheduled attempt.

The public journey uses a temporary SQLite file and a second service instance to demonstrate persistence across an explicitly simulated session boundary. Time advancement and provider-state change are deterministic demo behavior. No production scheduler or worker is present.

## Outcome management and closed-loop recovery

The bounded intent interpreter supports subscription cancellation and persists an `OutcomeContract` containing the desired `auto_renew == false` state, an optional Friday/tomorrow deadline, independent-read requirement, prohibited renewal-charge outcome, and user-confirmation recovery policy. Unsupported task types fail closed; this is not a general natural-language contract compiler.

The attention policy derives SILENT, INFORMATIONAL, ACTION_NEEDED, or URGENT from stored contract/evidence and deadline proximity. A persisted dedupe key suppresses repeated notices for an unchanged condition. On an eligible open resolution, CloseLoop may persist a target-bound `RecoveryAction`. A second attestation is bound to the exact recovery ID, owner, resolution, target digest, action type, and expiry. The provider receipt is recorded as a claim; recovery does not set a verdict or repeat cancellation. A later independent read-back still determines the original resolution.

The recovery and post-deadline renewal-charge scenes use a deterministic simulated provider and simulated spoken confirmation in `/demo/`. Billing observation must be correlated to the original owner, resolution, target, prohibited outcome, and deadline before the verifier can return FAIL. The violation, receipt, attention history, and recovery provenance are projected from persisted records. No refund is sent.

Recovery metadata may be version-updated while a resolution remains in a nonterminal state without appending a fake lifecycle transition. The SQL and DynamoDB conditional writes still check owner, version, current state, and exact state history. Terminal VERIFIED and NOT_COMPLETED rows remain immutable. A due-check worker and Alexa notification adapter are roadmap; no production scheduler or live Alexa Proactive Events delivery is implemented.


## Consumer lifecycle view (judge demo)

```text
Ask Alexa normally
       |
       v
Persistent outcome obligation
       |
       +--> separately confirmed cancellation action
       |
       +--> provider response (claim only)
       |
       +--> independent account evidence
                    |
                    v
          deterministic verifier
           /        |         \
     Verified   Not completed   Awaiting proof (open)
           \        |         /
             attention policy
                    |
             recovery proposal
                    |
       new action-bound confirmation
                    |
          bounded recovery action
                    |
       independent re-verification
                    |
            resolution receipt
```

The browser demo selects only a bounded server-side scenario; it cannot submit a verdict, evidence, or confirmation attestation. StreamBox, billing observations, time, and spoken Alexa consent are simulated. The attention, recovery, and verification code paths are CloseLoop behavior. Live Alexa+ invocation, Proactive Events delivery, a scheduler/worker, live provider integration, and live DynamoDB remain unverified or future work; none is drawn as a deployed service here. Recovery execution and its receipt do not alter the verifier’s authority.

### Future integrations (not implemented or deployed)

```text
Alexa Proactive Events adapter ─────── planned attention delivery
EventBridge Scheduler / worker ────── planned due-check delivery
Live subscription provider adapter ── simulated by StreamBox in the demo
```

These are roadmap boundaries, not runtime components. No production schedule, proactive Alexa notification, or connected provider is represented by the diagram above.
