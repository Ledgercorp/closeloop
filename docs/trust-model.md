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
