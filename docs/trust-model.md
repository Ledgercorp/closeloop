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
- the execution receipt is structurally valid and reports that the attempted action was accepted

FAIL when:
- independent account state is readable and fresh
- auto-renew remains true after the attempted cancellation

INCONCLUSIVE when:
- independent state cannot be read
- evidence is stale
- evidence is incomplete

Provider-reported success is never sufficient for PASS.
Malformed receipts, malformed read-back evidence, and a failed execution followed by an apparently
positive read-back are INCONCLUSIVE. A failed receipt cannot support PASS, while a fresh readable
read-back that still shows auto-renew enabled remains FAIL.

## MCP enforcement

- The public MCP surface contains no verdict-write tool.
- Generated tool schemas reject undeclared fields, including attempted verdict/status
  overrides, before a handler runs.
- Confirmation is an exact JSON boolean; truthy strings and numbers are rejected. Public intent and
  resolution identifiers have explicit size bounds before repository access.
- Confirmation also requires a compact attestation verified by a separately configured trusted
  confirmation authority. Signed claims bind the bearer-derived owner key, exact resolution,
  canonical action digest, affirmative decision, issuer, audience, issue time, expiry, and JTI.
- Missing or partial authority configuration selects a deny-all verifier. Production contains no
  issuer, signing endpoint, hard-coded signing secret, or boolean-only bypass.
- Verified attestation provenance is atomically persisted on the `EXECUTING` transition before
  provider execution. SQL compares exact prior history application-side and atomically conditions
  owner, identifier, version, and state; DynamoDB also conditions exact prior history. Repository
  callers therefore cannot replace that provenance.
- Replay protection is scoped to the exact bound resolution. Lifecycle state, optimistic version,
  and history conditions permit one transition winner across instances; the same compact token
  cannot authorize another principal, resolution, or action.
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
- Detailed evidence results must contain the canonical provenance, five-step lifecycle history, and
  a terminal verdict that agrees with a local re-evaluation of the receipt and read-back. Unknown,
  contradictory, forged, reordered, or malformed evidence renders `Proof unavailable`.
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

## Residual boundaries

- Local tests use an explicit test-only signer with the production verifier. They prove the
  CloseLoop resource-server verification and atomic-consumption boundary, not that Alexa+ obtained
  human approval. Production depends on an external OAuth/host authority that mints only after
  independently binding approval to the canonical owner, resolution, and action digest. Alexa+
  account linking authenticates requests but its public documentation does not itself establish
  this per-action attestation.
- A fully self-consistent forged result from a malicious MCP host cannot be distinguished by the
  read-only card without signed server evidence or a trusted host-to-resource channel.
- The HTTP stack bounds public schema fields but does not yet impose a raw request-body byte limit;
  the deployment edge must supply that availability control.
