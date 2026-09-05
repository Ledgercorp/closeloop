# CloseLoop Winning Demo Spec

## Objective
Explain CloseLoop to a judge in under 3 minutes and prove the core value with visible evidence.

The judge should understand the product within the first 10 seconds:

> Alexa+ can take action. CloseLoop makes sure "done" actually means done.

## Canonical scenario
Subscription cancellation.

User:
> Alexa, cancel my subscription and make sure I will not be charged again.

CloseLoop should make the lifecycle visible:
1. intent understood
2. consequential action requires confirmation
3. execution begins
4. provider/executor reports what it did
5. CloseLoop independently reads the resulting state
6. deterministic verifier produces the outcome
7. Alexa returns a plain-language completion result with proof

## Three required outcomes
### 1. Verified
Execution succeeds and independent read-back confirms cancellation / auto-renew off.

Show:
- action receipt
- independent read-back
- PASS internally
- `Verified` to the user

### 2. Not completed
Executor/provider claims success, but independent read-back shows the subscription is still active or auto-renew remains on.

Show:
- provider says success
- contradictory independent evidence
- FAIL internally
- `Not completed` to the user

This is the most important trust moment in the demo.

### 3. Awaiting proof
Execution may have happened, but the independent read-back is unavailable, delayed, or insufficient.

Show:
- action was attempted
- evidence gap
- INCONCLUSIVE internally
- `Awaiting proof` to the user

Do not fake certainty.

## Suggested video timing
0:00-0:15 — Problem and one-sentence product value.
0:15-0:55 — Verified happy path.
0:55-1:35 — False-success / Not completed path.
1:35-2:05 — Awaiting proof path.
2:05-2:35 — Quick architecture/trust-boundary reveal: Alexa/planning, execution, independent verification.
2:35-2:50 — AWS/Alexa+/MCP integration proof.
2:50-3:00 — Close with the core line and impact.

## Visual requirements
The UI/proof card should prioritize:
- what the user asked
- current lifecycle stage
- final plain-language status
- why CloseLoop believes that status
- execution evidence versus independent evidence
- timestamp / evidence provenance

Avoid flooding the main demo with developer logs. Advanced evidence can be expandable.

## Winning constraints
- Never spend demo time explaining CUF.
- Never make the product sound like generic observability.
- Never rely on the agent claiming success as proof.
- Make the false-success catch obvious and memorable.
- The demo must work end-to-end on the same paths used by the actual implementation, with simulations clearly labeled if a real provider cannot be safely used.
- Keep the user story consumer-facing even if the underlying architecture is sophisticated.

## Final message
Close on something equivalent to:

> Agents are getting better at taking action. CloseLoop makes completion trustworthy.
