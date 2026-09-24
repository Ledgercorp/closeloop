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
| Public demo backend | **PUBLIC DEMO END-TO-END VERIFIED** | Local API tests proved `/demo/` sends only an allowed scenario to `POST /demo/run`; server responses carry `server_generated: true`, real verifier identifiers, lifecycle timestamps, and verifier-generated PASS/FAIL/INCONCLUSIVE outcomes | Isolated temporary SQLite and deterministic simulated provider only; current browser bundle and hosted deployment were not exercised in this review |
| Public deployment | **VERIFIED** | Signed-out requests to `https://closeloop-zeta.vercel.app` returned 200 for `/`, `/health`, and `/demo/`; `/demo/run` returned all three server-generated outcomes; `/mcp` correctly returned 401; a fresh browser rendered Verified, Not completed, and Awaiting proof without SSO | No live provider, production storage/auth, Alexa+, or AWS; admission is per instance, not global rate limiting; Origin checks are browser control, not authentication |
| Live AWS | **NOT VERIFIED** | None claimed | Credentials, table, IAM, and CloudFormation execution unavailable |
| Live Alexa+ | **NOT VERIFIED** | None claimed | Partner tooling, onboarding, public endpoint, OAuth, confirmation authority, and host rendering unavailable |

## Final evidence counts

- Persistent-resolution evolution full suite (2026-09-24): **232 passed, 0 failed, 0 skipped**. The starting release baseline was **218 passed**.
- Focused MCP/Alexa contract and demo API suite: **46 passed, 0 failed, 0 skipped**.
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

The checked-in `/demo/` page now leads with the persistent-resolution story. The hosted Vercel deployment listed in the historical verification table was not redeployed or re-checked as part of this change; the prior result does not establish the revised UI or API is live there. Current verification is local. On 2026-09-24, a local browser run showed the initial confirmation gate, the full resolution timeline with simulated next-check time, and the evidence-outage path remaining open. The updated public page was not tested in an Alexa+ host.
