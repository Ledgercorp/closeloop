# CloseLoop resolution demo

## Recording setup

Run the local FastAPI application using the commands in the README, then open `/demo/`. The browser exercise uses the production lifecycle, SQLite repository, independent verifier, and proof-card contract with a deterministic demo provider. It uses simulated time and a temporary database. No Alexa+ account, live provider, AWS account, EventBridge schedule, or production action is involved.

The `persistent_resolution` scenario models a later session by constructing a new `ResolutionService` over the same SQLite database and advancing the check time to the stored `next_check_at`. It demonstrates the real persistence contract, not a deployed scheduler.

## Three-minute walkthrough

### 0:00 — Delegate

Say: “Alexa, cancel StreamBox before next Friday and make sure I don’t get charged again.”

Show the request and confirmation-required stage. State that no provider action occurs before confirmation.

### 0:25 — Accepted is not resolved

Select **Confirm cancellation**. The provider accepts the request, but the independent account read-back still shows auto-renew enabled. Read the response:

> “StreamBox accepted the cancellation request, but auto-renew is still on. I’m not marking this resolved yet.”

Point out that the same resolution is `AWAITING_PROOF`, remains open, and retains the check schedule and evidence.

### 1:00 — Return in a later session

Show **Later session** retrieving the same resolution ID and open state. No new cancellation is started. The stored due time drives one bounded independent recheck.

### 1:30 — Resolve with proof

Show fresh read-back with auto-renew off and an effective end date. The deterministic verifier moves the same resolution to `VERIFIED`. Read:

> “It’s verified canceled now. Auto-renew is off and your access ends October 3.”

Expand provenance to show the provider claim, both independent observations, and state history.

### 2:05 — Preserve uncertainty

Select **See when evidence is unavailable**. Read-back is unavailable, so the state remains `AWAITING_PROOF`; CloseLoop does not claim completion.

### 2:20 — Not completed outcome
Select **See a verified not completed outcome**. The simulation performs four bounded fresh read-backs. Auto-renew remains enabled on the final check, so the deterministic verifier returns `NOT_COMPLETED`. This result comes from independent evidence, not provider rejection.

### 2:25 — Architecture and limits

Explain that SQL/DynamoDB repositories persist owner-scoped records, and conditional writes protect transitions. The check budget is four total observations, with deterministic backoff. A worker may later trigger the due-check boundary; no production scheduler is implemented. DynamoDB is tested with Moto, not live AWS. Alexa+ integration has not been exercised on an Alexa account or device.

## Keep visible

Lead with the request, current resolution, what remains open, next check, and final answer. Keep hashes, digests, JSON, and protocol details inside **View evidence and provenance**. Never describe provider acceptance as resolution, simulated time as a production scheduler, or this local demo as live Alexa+ or AWS.

## Recovery and outcome-violation scenes

The consumer demo also offers two bounded scenarios. **See CloseLoop help recover** advances simulated time to the deadline window, surfaces ACTION_NEEDED from fresh enabled-state evidence, shows a new confirmation bound to `prepare_support_followup`, records the simulated provider receipt, then independently rechecks the same resolution and renders its persisted receipt. The simulated storyline includes the user's “Handle it” confirmation; the browser does not mint or submit a trusted attestation.

**See a renewal charge after cancellation** records a simulated, deadline-bound billing read-back correlated to the same owner, resolution, and provider target. The verifier returns **Not completed** from that evidence, CloseLoop records URGENT attention, and a separately confirmed simulation prepares (but does not send) a refund-request draft. This is not bank monitoring or a real charge/refund integration.

All demo timing, provider state changes, billing observations, and user confirmations are isolated simulations. No production scheduler, Alexa Proactive Events delivery, live Alexa+ session, or real customer account is exercised.
