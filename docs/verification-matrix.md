# Final verification matrix

Labels describe evidence actually established; they are not interchangeable.

| Surface | Status | Evidence | Limitation |
|---|---|---|---|
| Deterministic verifier | **VERIFIED** | Unit, lifecycle, persistence, and adversarial tests cover PASS/FAIL/INCONCLUSIVE and malformed evidence | Current executable predicate is subscription cancellation only |
| Lifecycle and immutable outcomes | **VERIFIED** | State-order, stale-write, race, replay, terminal-corruption, and restart tests | A persisted VERIFYING record can resume read-back after five minutes; a crash before an execution receipt is stored remains an unresolved provider-reconciliation boundary |
| Confirmation trust | **INTEGRATION VERIFIED** | Production verifier contract exercised with signed test attestations; freshness, tamper, owner/action binding, and atomic consumption tested | No live Alexa+/authorization-server confirmation issuer |
| Authentication and authorization | **INTEGRATION VERIFIED** | Authenticated ASGI/MCP calls test issuer/audience/scope, bearer-derived owner, and cross-principal isolation | Local tokens only; no live OAuth account linking |
| SQL persistence | **INTEGRATION VERIFIED** | SQLite cross-instance/restart/race tests and PostgreSQL-dialect predicate compilation | No live PostgreSQL server |
| DynamoDB persistence | **SIMULATED** | boto3 repository exercised through Moto with consistent-read and conditional-write contract assertions | No live AWS table, IAM, regional behavior, or CloudFormation API |
| MCP protocol | **INTEGRATION VERIFIED** | Standard MCP Inspector plus tests cover Streamable HTTP, 2025-11-25/2025-03-26, strict calls, and safe errors | Inspector ran on an unsupported older Node patch with successful commands |
| Alexa+ integration | **INTEGRATION VERIFIED** | Server implements documented self-hosted MCP contracts, schemas, protected-resource metadata, and conversational results | No Alexa AI CLI, add-on, Local Inspector, simulator, device, account link, or live client |
| MCP Apps resource | **INTEGRATION VERIFIED** | Resource discovery/read, metadata linkage, MIME profile, AppBridge result delivery, and text fallback tested | Not rendered by an Alexa+ host; CDN runtime dependency remains |
| Proof-card UI | **INTEGRATION VERIFIED** | Production MCP App contract, result validation, open `AWAITING_PROOF` history checks, safe text rendering, and generated lifecycle fixtures are covered locally | The updated open-resolution card was not rendered in a browser during this evolution; not rendered by an Alexa+ host; not a formal assistive-technology/WCAG audit |
| Adversarial/security | **PARTIALLY ADVERSARIAL VERIFIED** | 31 confirmation plus 78 general adversarial cases; seven blocking findings fixed; Governor final review | No formal penetration, load/DoS, live identity, live cloud, or network-partition testing |
| Demo provider | **SIMULATED** | Deterministic healthy, false-success, evidence-outage, and terminal-failure modes traverse the real adapter/lifecycle/verifier path | No real subscription account or third-party provider |
| Public repository | **VERIFIED** | Anonymous GitHub and raw-content requests returned 200; GitHub detects Apache-2.0 and the public license matches canonical bytes | Submission video remains a separate manual publication step |
| Persistent demo API flow (local) | **BROWSER VERIFIED LOCALLY** | API and Chromium tests exercise the lifecycle, simulated provider, independent read-back, deterministic verifier, three outcomes, recovery/violation stories, and scenario-only requests | Temporary SQLite and simulated provider only |
| Previous public demo release | **HISTORICAL UI/BROWSER VERIFIED** | Deployment dpl_7qzhdU8867s5w6yQZKCY2hU124AA for commit 5c36387 was checked signed out; Chromium and Playwright WebKit iPhone emulation exercised the then-current demo, including without DecompressionStream | This predates persistent resolutions and does not verify the current /demo/ experience or API |
| Reconciled persistent-resolution deployment baseline | **SIGNED-OUT VERIFIED** | `e38bff72616faaa536bdccbf72419a26fdc6c77f` `/demo/` returned 200; Chromium exercised Verified, Not completed, and Awaiting proof; 390/820/1280 widths had no overflow; no page errors | Does not verify the recovery changes |
| Live AWS | **NOT VERIFIED** | None claimed | Credentials, table, IAM, and CloudFormation execution unavailable |
| Live Alexa+ | **NOT VERIFIED** | None claimed | Partner tooling, onboarding, public endpoint, OAuth, confirmation authority, and host rendering unavailable |

## Final evidence counts

- Current recovery working tree (2026-09-24): **249 passed, 0 failed, 0 skipped** with Playwright enabled; full suite and Chromium browser regression passed.
- Reconciled pre-recovery baseline: **235 passed, 0 failed, 1 skipped** (236 collected); its browser regression was skipped before Playwright was installed.
- Focused MCP/Alexa contract and demo API suite: **49 passed, 0 failed, 0 skipped**.
- Previous milestone counts below are historical and predate this evolution (pre-integration deployment baseline: 187; Milestone 7 baseline: 183; previous full-suite total: 214).
- Previous public demo API/browser/security: **27 passed**; existing MCP/demo cases: **12 passed**; combined focused checkpoint: **39 passed**.
- Confirmation-attestation suite: **31 passed**.
- General adversarial/security suite: **78 passed**.
- AWS/lifecycle/verifier regression: **46 passed**.
- Alexa+/MCP regression: **12 passed**.
- Proof-card/UI regression: **16 passed**.
- Submission demo package: **2 passed**.

## Persistent resolution coverage

The public terminal-failure scenario repeatedly performs only independent read-back; the browser selects the scenario and never submits evidence or an outcome. The `test_persistent_resolution.py` checks cover SQLite restart between sessions, the same owner-scoped resolution surviving `AWAITING_PROOF`, accumulated evidence history, a later independent read resolving that record, owner isolation, consumed schedule-token replay, four-check exhaustion with known-failure, unknown-truth, and early-manual-recheck paths, concurrent check claims, recovery from a persisted `VERIFYING` record without repeating the action, owner-scoped simulated target digests bound into confirmation, and rejection of wrong-resource and prior-attempt evidence. MCP/public-demo tests cover the explicit recheck tool, open/recent status contract, cross-session story, and uncertainty path.

DynamoDB follow-up metadata and conditional updates are covered through Moto-backed tests. Live AWS and live Alexa+ execution remain unverified.


## Current repository/demo state (2026-09-24)

The signed-out production baseline at `e38bff72616faaa536bdccbf72419a26fdc6c77f` was checked on 2026-09-24: `/demo/` was public, the three lifecycle/verdict outcomes were correct, representative widths had no overflow, and Chromium reported no page errors. Those checks do not include the recovery evolution. The updated page was not tested in an Alexa+ host.

## Closed-loop recovery evolution status

| Surface | Status | Evidence | Limitation |
|---|---|---|---|
| Bounded outcome interpretation | **LOCALLY VERIFIED** | Supported cancellation contract and unsupported task rejection tests | Only cancellation intents and deadline phrases are interpreted; no universal language compiler |
| Attention-event dedupe | **LOCALLY VERIFIED** | Deadline/evidence-derived severity and unchanged-condition suppression tests | Events are persisted; no Alexa delivery adapter or production notifications |
| Recovery authorization/execution | **LOCALLY VERIFIED** | Separate recovery confirmation, original-token rejection, owner/action/target binding, duplicate/concurrent rejection, receipt/evidence separation | Simulated provider only; a crash after `EXECUTING` can require operator recovery; no automatic replay |
| Recovery reverification | **LOCALLY VERIFIED** | Browser and lifecycle tests show claimed follow-up cannot self-certify; fresh read-back yields PASS or remains INCONCLUSIVE | Production worker/scheduler not implemented |
| Outcome violation | **LOCALLY VERIFIED** | Correlated simulated post-deadline charge produces FAIL/Not completed, URGENT event, and separately confirmed unsent draft | No bank or billing-account access; no actual refund request sent |
| Recovery and violation browser flow | **BROWSER VERIFIED LOCALLY** | Chromium Playwright regression exercises both flows, viewport overflow, proof disclosure, and scenario-only request bodies | Production recovery build not yet deployed/exercised |
| Prior public deployment baseline | **SIGNED-OUT VERIFIED** | Reconciled `e38bff72616faaa536bdccbf72419a26fdc6c77f` was exercised at `/demo/` | Does not cover current recovery changes |
| Current recovery deployment | **NOT VERIFIED** | Recovery changes are not yet deployed | Push to the existing project, then repeat signed-out judge-style checks |
| Live scheduler / proactive delivery | **NOT IMPLEMENTED / NOT VERIFIED** | No scheduler worker or Alexa notification adapter is active | EventBridge Scheduler/Lambda delivery and Alexa Proactive Events remain roadmap |
