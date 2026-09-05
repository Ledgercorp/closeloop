# Trust Model

## Principle

The component that performs an action must not be the authority that decides whether the requested outcome is true.

## Action plane

May:
- interpret intent
- formulate a plan
- request user confirmation
- invoke mutation tools
- receive provider action receipts

May not:
- write the final verdict
- alter verifier predicates at runtime
- turn a successful tool response directly into a consumer completion claim

## Verification plane

May:
- independently read resulting state
- evaluate deterministic predicates
- write PASS / FAIL / INCONCLUSIVE
- produce an evidence record

May not:
- perform the mutation being evaluated

## Cancellation predicates

PASS when:
- independent account state is readable
- evidence is fresh
- auto-renew is false
- an effective end date is present

FAIL when:
- independent account state is readable and fresh
- auto-renew remains true after the attempted cancellation

INCONCLUSIVE when:
- independent state cannot be read
- evidence is stale
- evidence is incomplete

Provider-reported success is never sufficient for PASS.

## MCP enforcement

- The public MCP surface contains no verdict-write tool.
- Generated tool schemas reject undeclared fields, including attempted verdict/status
  overrides, before a handler runs.
- The confirmation tool can move a resolution into execution but cannot choose its terminal
  state.
- Execution receipts and independent read-back observations are stored as different evidence
  record types with source, identifier, and timestamp provenance.
- Only the deterministic verifier result maps a resolution to `VERIFIED`, `NOT_COMPLETED`,
  or `AWAITING_PROOF`.

## Ownership boundary

- MCP endpoints require a valid, unexpired, issuer- and audience-bound bearer token with the
  `closeloop:resolutions` scope.
- The owner key is derived from the validated `iss` and `sub` claims and is never supplied in tool
  arguments.
- Every repository lookup and mutation matches both resolution ID and owner key. Missing and
  unauthorized IDs return the same error so callers cannot enumerate another owner.
- Open-resolution queries always filter by owner.
- Optimistic versions serialize cross-instance updates; stale writers fail rather than repeating
  a consequential action.
- A row whose stored state is terminal cannot be updated, even if a caller presents an older or
  fabricated in-memory state.

## Alexa+ and proof-card boundary

- Alexa+ may choose when to call a disclosed tool and may compose voice/screen language from the
  returned data; it cannot provide, replace, or override a verifier result.
- Conversation fields such as `evidence_summary` and `recommended_next_step` are derived views of
  authoritative lifecycle/evidence state. They do not create or mutate that state.
- The MCP Apps proof card is read-only. It receives a tool result, renders escaped text through
  `textContent`, exposes no mutation control, and has no verdict-write or tool-call path.
- Protected-resource metadata describes the resource-server boundary only. It is not proof of an
  Alexa+ authorization server, account-linking flow, authenticated Alexa client, or live add-on.

## AWS persistence boundary

- DynamoDB may persist and return state and evidence; it does not calculate or select verdicts.
- Every mutation is a conditional write over owner identity, resolution identity, optimistic
  version, and allowed predecessor state. A diagnostic read after a rejected write cannot
  authorize a retry or overwrite.
- Strongly consistent owner-scoped reads prevent an eventually consistent view from being treated
  as current verification state.
- The runtime has no table deletion, scan, stream, index, orchestration, model, or verdict-write
  permission/path.
- AWS failures and corrupt records become storage-unavailable errors, never successful outcomes.
- A crash after external execution may leave an in-progress record. CloseLoop does not claim
  exactly-once recovery and must not blindly repeat the consequential action.
