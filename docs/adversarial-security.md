# Milestone 7 Adversarial Security Report

## Scope and verification level

Milestone 7 attacks the CloseLoop authorization, confirmation, lifecycle, deterministic verifier,
persistence, MCP, and proof-card boundaries. It introduces no product capability and preserves the
five-tool public MCP surface. The reproducible focused suite contains 78 general adversarial cases
plus 31 confirmation-attestation cases; the proof-card regression contains 16 cases. Validation is
local plus simulated DynamoDB through
Moto. It is therefore **PARTIALLY ADVERSARIAL VERIFIED**, not live Alexa+, live AWS, or production
security verification.

## Threat model and results

| Area | Reproducible attacks | Expected safe behavior | Actual result | Classification |
|---|---|---|---|---|
| A. Verdict manipulation | Top-level and nested `verdict`, `status`, `success`, case variants, encoded values, forged execution claims | Reject undeclared fields; no direct terminal/verdict write | Rejected before handlers; execution receipt alone cannot PASS | PASS after fix |
| B. Confirmation bypass | Missing/false/truthy-string/numeric confirmation, unsigned/tampered/expired/future/wrong-issuer attestations, replay, duplicate, wrong owner/resolution/action digest, invalid order, and two-thread race | Exact trusted-principal, resolution, action, affirmative-decision, issuer, freshness, and single-use binding; at most one execution | The resource server verifies a short-lived signed v1 contract and atomically persists full provenance before execution; missing or invalid configuration denies all confirmations | BLOCKING FINDING fixed locally; live authority unverified |
| C. Cross-principal isolation | Read, evidence, list, and confirmation attempts using real, guessed, case-mutated, percent-encoded, and padded identifiers | Same fail-closed response without existence leakage | Owner remains token-derived; responses do not disclose another owner's record or identifier | PASS |
| D. Lifecycle manipulation | Duplicate/replayed transitions, terminal replay, stale versions, concurrent confirmation, corrupt terminal data | Enforced order and immutable terminal result | SQLite and Moto races have one conditional winner; terminal and stale writes fail closed | PASS |
| E. Forged/contradictory evidence | Failed/malformed receipts, negative/string freshness, invalid dates/types, read-back exception, success/read-back contradiction | Never promote malformed or execution-only claims; contradiction FAIL, insufficiency INCONCLUSIVE | Malformed values previously passed or raised and failed receipts could PASS; strict validation and receipt gating now fail closed | BLOCKING FINDING fixed |
| F. DynamoDB concurrency | Concurrent confirmations, duplicate attestation redemption, stale conditional writes, re-instantiation, corrupt stored attestation/PASS evidence | Atomic owner/version/state/history conditions; replay and corrupt evidence fail closed | Moto confirms one execution/winner; signed-attestation provenance survives re-instantiation; corrupt terminal or attestation evidence raises storage-unavailable | PASS (simulated) |
| G. MCP protocol abuse | Extra/wrong/missing fields, invalid tools, malformed JSON-RPC, unsupported protocol, oversized intent/identifier, replay/order abuse | Strict safe errors and no mutation | Schemas and handlers reject all cases; explicit length bounds added | BLOCKING FINDING fixed |
| H. Authentication/authorization | Missing/malformed/expired/wrong issuer/audience/scope tokens, payload principal spoof, ownership mismatch | Identity only from validated auth context | All fail closed; payload cannot displace authenticated principal | PASS (local tokens) |
| I. UI/proof-card | Contradictory result, forged provenance, reordered history, malformed evidence, unknown state, injected markup | Neutral fallback, escaped text, never manufacture Verified | Outer tuple checks were insufficient; card now recomputes evidence and requires canonical provenance/history; hostile text remains text | BLOCKING FINDING fixed |
| J. Information leakage | Auth, ownership, storage, verifier, and malformed-protocol errors inspected for secrets, identifiers, table/region internals, traces | Stable sanitized errors | Responses remain generic and omit protected identifiers, storage details, secrets, and stack traces | PASS |
| K. Availability/failure | Repository outage, provider/factory/read-back/verifier exception, malformed provider object, partial terminal write, UI bridge failure/unknown result | Never turn failure into Verified | Failures return safe errors or Awaiting proof; partial write remains truthfully VERIFYING; card falls back to Proof unavailable | PASS after fix |

## Blocking findings and fixes

Six blocking classes were found and fixed with bounded changes:

1. Coercible non-boolean confirmation values could execute an action. The MCP schema now uses an
   exact boolean.
2. Malformed read-back evidence could PASS or raise. The verifier now validates exact scalar types,
   nonnegative freshness, and calendar dates before applying predicates.
3. A failed or malformed execution receipt followed by positive read-back could PASS. A structurally
   valid successful receipt is now necessary, but still never sufficient, for PASS.
4. A forged evidence-shaped proof-card payload could manufacture Verified despite contradictory
   details. The card now checks canonical sources/history and re-evaluates the evidence predicate.
5. Public intent and resolution identifiers lacked explicit schema bounds. MCP and direct lifecycle
   boundaries now reject oversized values before repository work.
6. A plain `{resolution_id, confirmed}` request could not prove that a trusted human approved the
   exact action, could be replayed, and had no trusted freshness boundary. The confirmation tool now
   requires a short-lived signed `closeloop.confirmation/v1` attestation. Its authenticated subject,
   resolution, canonical action digest, affirmative decision, issuer, audience, issue/expiry times,
   and unique attestation ID are verified before any mutation. Full verified provenance is persisted
   on the single `EXECUTING` transition. SQL compares exact prior history before its atomic
   owner/identifier/version/state update, while DynamoDB also conditions exact prior history. Only
   one concurrent redemption for that bound resolution can execute.

Every fixed class has a regression test. Tests were written to fail against the Milestone 6 code
before the fixes were applied; 14 initial exploit variants reproduced unsafe behavior or an
exception. The two former strict xfails for wrong-resolution use and stale confirmation are now
ordinary passing tests.

The final Governor review also found a release-blocking portability regression introduced by the
first replay predicate: comparing a SQLAlchemy `JSON` column in the atomic update would compile to
unsupported equality on PostgreSQL `json`. The database-side history comparison was removed only
from SQL. Its owner/identifier/version/state predicate remains the atomic single-winner guard, the
owner-scoped read still compares exact history, and a PostgreSQL-dialect compile regression now
protects this contract. DynamoDB retains its exact-history condition.

A nonce returned through the same potentially malicious agent is insufficient because it proves
only that the caller can echo server data. The replacement requires integrity from a configured
trusted confirmation authority. Production has no default key, issuer, or audience: incomplete
configuration selects a deny-all verifier. The deterministic HMAC test issuer lives only under
`tests/`, while the validation builder labels its local signer as simulated. An external production
issuer must independently observe and authorize the exact human decision before signing; blindly
signing caller-supplied fields would not satisfy this boundary.

## Residual findings

Five non-blocking residual findings remain explicit:

1. A fully self-consistent forged result from a malicious MCP host is indistinguishable to the card
   without signed evidence or a trusted host channel.
2. Field lengths are bounded, but the application does not impose a raw HTTP request-body byte
   limit; deployment-edge controls are still required for volumetric abuse.
3. The browser resource depends on a pinned jsDelivr module. Its CSP narrows origin access, but
   availability and supply-chain trust are external.
4. Replay protection is single-use for the exact bound resolution, not a global JTI registry. Exact
   principal/resolution/action binding prevents reuse elsewhere, while conditional history
   preservation prevents replacement or repeated consumption on that resolution. A future
   multi-resource confirmation contract would need a global replay namespace.
5. Direct database mutation that rewrites history without incrementing the version is outside the
   repository authorization boundary. Normal SQL and DynamoDB repository callers cannot do this;
   deployment credentials must deny untrusted direct writes.

These require future product, protocol, or deployment decisions. None can directly alter an
authoritative stored terminal verdict through the tested server path.

## Untested live risks

- No Alexa+ client, Local Inspector, device, account linking, production OAuth attack, or live
  confirmation authority was available. Official Alexa+ documentation establishes bearer-token
  authentication for user/write tools, but does not document a per-action human-confirmation
  attestation; CloseLoop does not claim that Alexa+ currently emits this contract.
- No live AWS account/table/IAM policy, DynamoDB Local, multi-process network partition, or regional
  failure was exercised; DynamoDB behavior is Moto-simulated with inspected request contracts.
- No real external provider account/read-back system was available, so provider authenticity,
  rate-limit, webhook, and outage behavior remain adapter-level simulations.
- PostgreSQL parity, formal penetration testing, load/DoS testing, browser assistive technology,
  and CDN compromise were not exercised.

## Stop condition

Milestone 7 is **PARTIALLY ADVERSARIAL VERIFIED**: 31 focused confirmation-attestation tests, 78
general adversarial tests, all regression groups, and the 183-test complete suite pass. The
CRITICAL-risk Development Governor final review found no remaining BLOCKING/HIGH implementation
issue after the PostgreSQL predicate correction. Live Alexa+/authorization-server issuance remains
an explicitly unverified external integration boundary and must not be presented as live
verification. This milestone does not authorize Milestone 8, demo optimization, submission
packaging, providers, or new features.
