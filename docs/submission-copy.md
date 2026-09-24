# CloseLoop submission copy

Copy is written for the Amazon Build, Ship, Shape 2026 submission form. Replace the bracketed video
placeholder only after verifying it anonymously.

## Project title

**CloseLoop: Alexa+ Resolution Ownership**

## One-line tagline

CloseLoop lets you hand Alexa+ a consequential task and keeps responsibility for it until the real-world outcome can actually be verified.

## Short description

Alexa+ can take the action. CloseLoop makes sure the outcome actually happened. It stores each resolution, independent evidence, verification history, and next check so users can leave and return later without losing the task.

## Full description

CloseLoop is an Alexa+-native persistent resolution layer for consequential consumer tasks. Subscription cancellation is the implemented workflow. A user asks Alexa+ to cancel a subscription and make sure it happens. CloseLoop requires action-bound confirmation, records the provider receipt as a claim, reads the account state independently, and lets deterministic code evaluate the evidence.

If the provider says “accepted” while auto-renew is still on, CloseLoop keeps the same resolution open as **Awaiting proof**. It preserves the read-back and schedules a bounded next check. In a later session Alexa+ retrieves that authoritative record; a fresh independent observation can then move it to **Verified**. A provider rejection alone remains a claim. `Not completed` requires a valid accepted receipt plus fresh independent evidence that auto-renew is still on at the final observation of the bounded four-check window. Earlier contradiction and unavailable evidence remain **Awaiting proof**.

The product’s point is simple: requested is not executed, and executed is not resolved. The public repository demo simulates the session boundary, time advance, and provider state change over temporary SQLite. It is not a production scheduler or a live Alexa+ integration.

## Problem

A successful tool call proves that a tool returned success; it does not prove that the customer’s
desired outcome is true. Today’s agent patterns often collapse execution and verification into one
trust domain, creating false completion claims with financial and emotional consequences.

## Solution

CloseLoop gives execution and verdicts different authorities. The action plane may attempt work and
report a receipt. A separate evidence path observes the resulting state. Only a deterministic
verifier may write PASS, FAIL, or INCONCLUSIVE. The conversational and visual layers can explain
that verdict but cannot override it.

## How it works

1. Alexa+ creates an owner-scoped resolution and asks the user to confirm the exact cancellation.
2. CloseLoop verifies the signed, short-lived, single-use confirmation before invoking the provider.
3. CloseLoop stores the action receipt but treats it as a claim.
4. A separate read-back feeds the deterministic verifier.
5. If evidence is inconclusive, the resolution remains open with bounded check count and `next_check_at`.
6. Alexa+ can retrieve open or recently resolved records in a later session, explain the latest evidence, or explicitly request a recheck.
7. Only deterministic verifier output can produce Verified, Not completed, or Awaiting proof.

## Technical architecture

- Python/FastAPI application with an official MCP Python SDK server at `/mcp`.
- Stateless Streamable HTTP supporting MCP `2025-11-25` and `2025-03-26` negotiation.
- Six closed-schema tools; no verdict-write capability.
- Bearer-token resource-server boundary with issuer, audience, expiry, scope, and server-derived
  owner identity validation.
- Versioned signed confirmation-attestation interface with freshness and replay protection.
- Separate execution receipt and independent read-back evidence models.
- Deterministic cancellation verifier with PASS/FAIL/INCONCLUSIVE semantics.
- SQL repository for local/shared relational persistence and optional DynamoDB repository for
  serverless cross-instance state.
- Read-only MCP Apps proof card with escaped content and fail-closed result consistency checks.

## Alexa+ integration

The implemented integration surface is a self-hosted authenticated Streamable HTTP MCP server with seven tools: start, confirm, retrieve status, retrieve evidence, list open work and list recent outcomes, and recheck. It has closed schemas, bearer-derived ownership, protected-resource metadata, and a read-only MCP Apps proof card. Local MCP SDK integration tests exercise the contracts. No Alexa+ account, device, host, or live session has been used for verification.

## AWS integration

DynamoDB can serve as the authoritative durable resolution/evidence repository. Conditional owner, state, version, and history writes protect transitions. The checked-in DynamoDB repository is Moto-tested; no live AWS table or CloudFormation deployment was exercised. A due-check worker can invoke the bounded service recheck with the persisted schedule token, but EventBridge Scheduler, Lambda, and SQS are not implemented.

## Security and trust model

- The agent, provider, Alexa+, and proof card cannot write a verdict.
- Provider-reported success is necessary evidence in the happy path, never sufficient proof.
- Confirmation is signed, action-bound, principal-bound, short-lived, and single-use.
- Principal identity comes from validated bearer context, never a tool payload.
- Every resolution read/write is owner-scoped; unauthorized and missing identifiers are
  indistinguishable.
- Optimistic/conditional writes serialize concurrent transitions and preserve immutable terminal
  outcomes.
- Malformed, contradictory, missing, or unavailable evidence fails closed.
- The UI rechecks result consistency, escapes untrusted text, and cannot manufacture Verified.

Milestone 7 attempted 109 focused security/confirmation cases. Seven blocking findings were found
and fixed. **Security label: PARTIALLY ADVERSARIAL VERIFIED** because live Alexa+, AWS, provider,
PostgreSQL, penetration, and load testing remain outside the available environment.

## What makes it different

CloseLoop is not a Q&A assistant and not an MCP wrapper that equates a successful call with a
successful outcome. Its defining product behavior is refusing to say “done” when the executor is
wrong or evidence is missing. The false-success and evidence-outage paths receive the same design
attention as the happy path, and the proof is understandable to a consumer rather than hidden in
developer logs.

## Challenges and friction

- Alexa+ tooling is limited to selected partners; CLI, Local Inspector, Add-on Agent Skill, and
  authenticated onboarding were unavailable on this host.
- Alexa+ auth guidance defines account linking for user/write tools but not a standard per-action
  human-confirmation attestation, so CloseLoop added a separate deny-by-default authority contract.
- MCP SDK authentication defaults required a narrow compatibility adjustment for Alexa+ discovery.
- MCP Apps browser validation required careful script-context escaping and bridge sequencing.
- Live DynamoDB validation was blocked by absent AWS credentials/CLI and unavailable Java/Docker
  for DynamoDB Local; Moto provided bounded simulation instead.
- Vercel generated deployment URLs are protected, but the actual production alias is public. Its
  isolated deterministic demo calls the real server lifecycle/verifier; protected MCP actions
  remain bearer-gated.

## What we learned

Trustworthy agent UX needs an explicit uncertainty state, not just better success messages. A small
deterministic verifier and durable evidence model can create more customer trust than adding more
agent orchestration. Visual proof works best when the primary answer stays simple and provenance is
available progressively. Finally, infrastructure status and tool responses must be treated as
claims until the customer-visible outcome is independently observed.

## Future roadmap

1. Obtain Alexa+ partner access and validate the real add-on, account-linking, confirmation, and MCP
   Apps lifecycle with Local Inspector and an Alexa+ client.
2. Connect one authorized real subscription provider plus an independent read-back source.
3. Deploy production OAuth/confirmation authority and shared DynamoDB or PostgreSQL safely.
4. Add recovery for resolutions left truthfully in EXECUTING/VERIFYING after a process failure.
5. Extend to refunds, returns, and warranty claims only after preserving the same evidence contract.

## Repository and open-source notes

- Repository: **https://github.com/Ledgercorp/closeloop**
- License: Apache-2.0, with canonical license text in `LICENSE`.
- Setup, deterministic demo, architecture, tests, and limitations are documented in `README.md`.
- CloseLoop was built during the hackathon window. Prior CUF experience informed the general
  PASS/FAIL/INCONCLUSIVE concept, but no CUF source was copied into this repository.
- If entering the separate Open Source mini challenge, add the required contribution URL, GitHub
  username, and contribution description; this package does not assume that entry is selected.

## Testing and evidence summary

- Current recovery working tree: **249 passed, 0 failed, 0 skipped** with Playwright/Chromium enabled. The pre-recovery baseline had 235 passed and one browser test skipped before Playwright was installed.
- Focused confirmation-attestation: **31 passed**.
- General adversarial/security: **78 passed**.
- AWS/lifecycle/verifier: **46 passed**.
- Alexa+/MCP: **12 passed**.
- Proof-card/UI: **16 passed**.
- Canonical demo: PASS → Verified; FAIL → Not completed; INCONCLUSIVE → Awaiting proof.
- Browser: **LOCAL UI/BROWSER VERIFIED** for persistent resolution, recovery, and violation flows. Production checks below cover only the reconciled pre-recovery release until the recovery commit is deployed.
  deployed isolated server lifecycle/verifier.
- Alexa+: **INTEGRATION VERIFIED locally; live NOT VERIFIED**.
- AWS: **SIMULATED; live NOT VERIFIED**.
- Public deployment: the reconciled persistent-resolution baseline was signed-out verified; the current recovery evolution remains **NOT VERIFIED IN PRODUCTION** until its own commit is deployed and exercised.

## Submission links

- Public repository: **https://github.com/Ledgercorp/closeloop**
- Public video under three minutes: **[ADD VERIFIED YOUTUBE OR VIMEO URL]**
- Public demo: **https://closeloop-zeta.vercel.app/demo/**
- Primary track: **Alexa+**
- Mini challenge: **AWS Builder**

## Outcome management and recovery claim

CloseLoop is an outcome-management layer for Alexa+: it keeps ownership of a consequential request until independent evidence shows the result, then helps the user recover safely when reality does not cooperate. The cancellation demo has a bounded supported intent, persisted outcome contract, deterministic attention-event deduplication, separately confirmed simulated follow-up, independent reverification, and a deadline-bound simulated renewal-charge violation that prepares a refund-request draft without sending it. The lifecycle and verifier run locally; attention delivery to Alexa, provider/billing changes, and spoken consent are not live integrations. It is not a real refund service, billing monitor, production scheduler, live Alexa+ integration, or live AWS deployment.
