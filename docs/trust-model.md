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
