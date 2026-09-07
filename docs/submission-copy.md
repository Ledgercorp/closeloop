# CloseLoop submission copy

Copy is written for the Amazon Build, Ship, Shape 2026 submission form. Replace the bracketed video
placeholder only after verifying it anonymously.

## Project title

**CloseLoop — Proof Before “Done”**

## One-line tagline

**CloseLoop independently verifies consequential actions before Alexa+ tells you the task is done.**

## Short description

CloseLoop is a self-hosted Alexa+ MCP server that separates an agent’s action from the authority to
declare success. It reads resulting state through a separate evidence path and returns Verified, Not completed, or
Awaiting proof—with an evidence card that shows why.

## Full description

Agents can call tools, receive a success response, and confidently tell a customer that a task is
finished—even when the real-world result is wrong or impossible to verify. That failure is
especially costly for subscriptions, refunds, returns, and other financial life-admin work.

CloseLoop adds a verification boundary to consequential Alexa+ actions. In the flagship demo, a
customer asks, “Alexa, cancel my subscription and make sure I won’t be charged again.” CloseLoop
requires trusted confirmation, executes the cancellation through an action adapter, records the
provider’s receipt as a claim, and independently reads the resulting account state. Deterministic
code—not the agent, provider, Alexa+, or UI—then produces one of three outcomes:

- **Verified:** fresh independent evidence proves auto-renew is off.
- **Not completed:** read-back contradicts the provider’s success claim.
- **Awaiting proof:** evidence is unavailable or insufficient, so CloseLoop refuses to guess.

The Alexa-ready response is self-contained for voice, while a read-only MCP Apps proof card makes
the lifecycle, evidence summary, and provenance visible. Amazon DynamoDB can serve as the
authoritative owner-scoped lifecycle/evidence repository, using consistent reads and conditional
writes to preserve confirmation consumption, concurrency safety, and immutable terminal outcomes.

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

1. Alexa+/an MCP client calls `start_resolution` with the customer’s goal.
2. CloseLoop returns an action digest and stops at `AWAITING_CONFIRMATION`.
3. A trusted confirmation authority signs the exact owner, resolution, action digest, affirmative
   decision, issue/expiry times, and unique replay ID.
4. `confirm_resolution_action` verifies and atomically consumes that attestation before mutation.
5. The provider action receipt is persisted as an execution claim.
6. A separate read-back collects resulting-state evidence.
7. Deterministic predicates return PASS, FAIL, or INCONCLUSIVE.
8. Alexa-ready structured data and the proof card present Verified, Not completed, or Awaiting
   proof with expandable provenance.

## Technical architecture

- Python/FastAPI application with an official MCP Python SDK server at `/mcp`.
- Stateless Streamable HTTP supporting MCP `2025-11-25` and `2025-03-26` negotiation.
- Exactly five closed-schema tools; no verdict-write capability.
- Bearer-token resource-server boundary with issuer, audience, expiry, scope, and server-derived
  owner identity validation.
- Versioned signed confirmation-attestation interface with freshness and replay protection.
- Separate execution receipt and independent read-back evidence models.
- Deterministic cancellation verifier with PASS/FAIL/INCONCLUSIVE semantics.
- SQL repository for local/shared relational persistence and optional DynamoDB repository for
  serverless cross-instance state.
- Read-only MCP Apps proof card with escaped content and fail-closed result consistency checks.

## Alexa+ integration

CloseLoop uses the self-hosted MCP path accepted by the Alexa+ track: Streamable HTTP, MCP
`2025-11-25`, strict tools, protected-resource discovery, bearer-authenticated user operations,
conversation-ready text/structured responses, and a `ui://` MCP Apps resource. Standard MCP
Inspector and local integration tests verified initialization, tool/resource discovery, schemas,
authenticated calls, and the complete lifecycle.

**Verification label: INTEGRATION VERIFIED locally.** Alexa AI CLI/Local Inspector access,
account linking, a live Alexa+ client, and Alexa+ proof-card rendering were unavailable. The project
does not claim a deployed Alexa+ add-on or live Alexa+ verification.

## AWS integration

DynamoDB is not a demo log. When configured, it becomes the authoritative store for owner identity,
resolution state, confirmation provenance, action receipt, independent evidence, verifier result,
timestamps, history, and optimistic version. Composite owner/resolution keys enforce isolation;
strongly consistent reads protect current-state decisions; conditional writes enforce creation,
allowed transitions, single-winner confirmation consumption, and terminal immutability. A
CloudFormation template provisions one encrypted `PAY_PER_REQUEST` table, and the runtime requires
only `GetItem`, `PutItem`, and `Query`.

**Verification label: SIMULATED.** The boto3 contract was exercised with Moto, including races,
corrupt records, re-instantiation, pagination, error translation, and all three outcomes. No live
AWS account, IAM policy, table, or CloudFormation API was exercised.

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

- Complete server-backed demo suite: **214 passed** (pre-integration deployment baseline: 187;
  Milestone 7 baseline: 183).
- Focused confirmation-attestation: **31 passed**.
- General adversarial/security: **78 passed**.
- AWS/lifecycle/verifier: **46 passed**.
- Alexa+/MCP: **12 passed**.
- Proof-card/UI: **16 passed**.
- Canonical demo: PASS → Verified; FAIL → Not completed; INCONCLUSIVE → Awaiting proof.
- Browser: **LOCAL UI/BROWSER VERIFIED**; the public demo is **END-TO-END VERIFIED** against the
  deployed isolated server lifecycle/verifier.
- Alexa+: **INTEGRATION VERIFIED locally; live NOT VERIFIED**.
- AWS: **SIMULATED; live NOT VERIFIED**.
- Public deployment: **VERIFIED** for the signed-out isolated deterministic judge demo; live
  provider/auth/storage execution is not deployed.

## Submission links

- Public repository: **https://github.com/Ledgercorp/closeloop**
- Public video under three minutes: **[ADD VERIFIED YOUTUBE OR VIMEO URL]**
- Public demo: **https://closeloop-zeta.vercel.app/demo/**
- Primary track: **Alexa+**
- Mini challenge: **AWS Builder**
