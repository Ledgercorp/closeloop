# CloseLoop submission-ready copy

## Project title

**CloseLoop: Alexa+ Outcome Management**

## One-line description

**CloseLoop gives Alexa+ responsibility for the outcome, not just the action.**

## Short description

Ask Alexa to handle a consequential task. CloseLoop keeps the request open, independently checks whether the outcome actually happened, and can propose a safe, separately authorized recovery when reality goes wrong.

## Problem

A successful API call proves that a request returned successfully. It does not prove that a subscription stopped renewing, a refund arrived, or another real-world outcome changed. When assistants collapse action execution and success into one claim, users inherit the cost of false completion.

## Solution

CloseLoop persists the user’s supported request and desired outcome. It requires trusted confirmation before the cancellation action, records the provider response as a claim, and evaluates fresh, target-bound account evidence separately. If the evidence is missing, the task stays open. If a bounded recovery is appropriate, CloseLoop asks for new authorization and checks the outcome again afterward.

## Differentiator

CloseLoop combines **persistent outcome ownership, independent verification, quiet deterministic attention, separately authorized recovery, and reverification**. It handles the unresolved gap between “the action ran” and “reality now matches what I asked for.” Recovery does not certify itself.

## What the demo shows

The recommended public story starts with a normal cancellation request, then shows provider acceptance while auto-renew remains on. CloseLoop keeps the resolution open, advances simulated time toward the deadline, asks for separate recovery authorization, prepares a simulated support follow-up, and independently checks the account again before showing the receipt. An alternate scenario records a simulated post-cancellation $19.99 renewal charge and offers an unsent refund-request draft. The demo also exposes Verified, evidence-supported Not completed, and Awaiting proof when evidence is unavailable.

## Technical depth

- Alexa+-designed, authenticated Streamable HTTP MCP server with seven closed-schema tools.
- Persistent owner-scoped resolutions in SQL, with an optional DynamoDB repository contract.
- Deterministic PASS / FAIL / INCONCLUSIVE verifier; no client verdict-write operation.
- Fresh evidence correlated to owner, resolution, target/resource, and verification attempt.
- Signed, short-lived, single-use, action-bound confirmation with replay and concurrency protections.
- Bounded observational rechecks that never repeat the cancellation action.
- Deterministic attention and notification deduplication.
- Separate recovery action records and recovery-specific confirmation, execution receipt, and provenance.
- Recovery receipts remain claims; independent reverification determines the resolution outcome.
- Consumer Resolution Receipts and expandable evidence/provenance.
- Adversarial API, MCP, repository, lifecycle, confirmation, recovery, and browser regression coverage.

## Honest limitations

- StreamBox is a simulated provider; no real subscription is canceled.
- Billing observations, time advancement, and spoken Alexa interactions are simulated.
- No live Alexa+ session, Alexa Proactive Events delivery, or confirmation authority is verified.
- The demo uses isolated temporary state; there is no production autonomous scheduler or worker.
- No live AWS DynamoDB table or CloudFormation deployment has been exercised. DynamoDB repository behavior is Moto-tested.
- No real billing account is monitored, no refund is sent, and no live provider integration is claimed.
- The current executable provider workflow is subscription cancellation; other request types are not executable integrations.

## Future Alexa+ fit

CloseLoop is designed as an outcome-management layer beneath Alexa+ experiences, not a vocabulary users must learn. A future Alexa+ experience could offer to keep watching after an eligible action. Live Alexa+ invocation, account linking, and proactive notification delivery remain unverified.

## Skeptical judge questions

**Isn’t this a reminder app?** A reminder says when to check. CloseLoop stores the outcome obligation, checks independent state, preserves uncertainty, and can begin a separately authorized recovery.

**Isn’t this just verification?** Verification decides whether the requested state is true. CloseLoop also keeps unresolved work open, decides when attention is warranted, offers bounded recovery, and verifies again afterward.

**Why does Alexa+ need this?** An assistant can report that a tool accepted an action. The consumer needs to know whether the real account changed, and what happens when it did not.

**Why not trust the provider API?** The provider response is recorded as a claim. A separate account read-back supplies the evidence used by the deterministic verifier.

**What if CloseLoop does not know?** It says Awaiting proof, leaves the resolution open, and does not convert missing evidence into success or failure.

**Can it perform the cancellation twice?** Rechecks are observational and cannot call the cancellation action. The original confirmation is single-use and action-bound.

**Can AI mark its own work successful?** No. The execution plane, provider claim, browser, Alexa/LLM, and recovery receipt have no verdict-writing authority.

**Can it recover without permission?** No. Consequential recovery needs a new confirmation bound to that exact recovery action.

**Are the integrations real?** The CloseLoop lifecycle and verifier code paths are exercised. StreamBox, billing, spoken Alexa interactions, and time are simulated; live Alexa+, AWS, and providers are not claimed.

## Video and links

- Recording target: **2:45**, hard limit 3:00. See [the timed script and shot list](demo-script.md).
- Public demo: https://closeloop-zeta.vercel.app/demo/
- Source: https://github.com/Ledgercorp/closeloop
- Public video URL: **not recorded or uploaded yet**.
