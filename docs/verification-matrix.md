# Final verification matrix

Labels describe evidence actually established; they are not interchangeable.

| Surface | Status | Evidence | Limitation |
|---|---|---|---|
| Deterministic verifier | **VERIFIED** | Unit, lifecycle, persistence, and adversarial tests cover PASS/FAIL/INCONCLUSIVE and malformed evidence | Current executable predicate is subscription cancellation only |
| Lifecycle and immutable outcomes | **VERIFIED** | State-order, stale-write, race, replay, terminal-corruption, and restart tests | Crash recovery from truthful EXECUTING/VERIFYING is not implemented |
| Confirmation trust | **INTEGRATION VERIFIED** | Production verifier contract exercised with signed test attestations; freshness, tamper, owner/action binding, and atomic consumption tested | No live Alexa+/authorization-server confirmation issuer |
| Authentication and authorization | **INTEGRATION VERIFIED** | Authenticated ASGI/MCP calls test issuer/audience/scope, bearer-derived owner, and cross-principal isolation | Local tokens only; no live OAuth account linking |
| SQL persistence | **INTEGRATION VERIFIED** | SQLite cross-instance/restart/race tests and PostgreSQL-dialect predicate compilation | No live PostgreSQL server |
| DynamoDB persistence | **SIMULATED** | boto3 repository exercised through Moto with consistent-read and conditional-write contract assertions | No live AWS table, IAM, regional behavior, or CloudFormation API |
| MCP protocol | **INTEGRATION VERIFIED** | Standard MCP Inspector plus tests cover Streamable HTTP, 2025-11-25/2025-03-26, strict calls, and safe errors | Inspector ran on an unsupported older Node patch with successful commands |
| Alexa+ integration | **INTEGRATION VERIFIED** | Server implements documented self-hosted MCP contracts, schemas, protected-resource metadata, and conversational results | No Alexa AI CLI, add-on, Local Inspector, simulator, device, account link, or live client |
| MCP Apps resource | **INTEGRATION VERIFIED** | Resource discovery/read, metadata linkage, MIME profile, AppBridge result delivery, and text fallback tested | Not rendered by an Alexa+ host; CDN runtime dependency remains |
| Proof-card browser UI | **LOCAL UI/BROWSER VERIFIED** | Real lifecycle cards rendered for confirmation and all three outcomes locally; the polished public browser UI also rendered all three server-returned outcomes signed out at `https://closeloop-zeta.vercel.app/demo/` | Not rendered by an Alexa+ host; not a formal assistive-technology/WCAG audit |
| Adversarial/security | **PARTIALLY ADVERSARIAL VERIFIED** | 31 confirmation plus 78 general adversarial cases; seven blocking findings fixed; Governor final review | No formal penetration, load/DoS, live identity, live cloud, or network-partition testing |
| Demo provider | **SIMULATED** | Deterministic healthy, false-success, and evidence-outage modes traverse the real adapter/lifecycle/verifier path | No real subscription account or third-party provider |
| Public repository | **VERIFIED** | Anonymous GitHub and raw-content requests returned 200; GitHub detects Apache-2.0 and the public license matches canonical bytes | Submission video remains a separate manual publication step |
| Public demo backend | **PUBLIC DEMO END-TO-END VERIFIED** | Signed-out browser and direct API tests proved `/demo/` sends only an allowed scenario to `POST /demo/run`; deployed server responses carried `server_generated: true`, real verifier identifiers, lifecycle timestamps, and PASS/FAIL/INCONCLUSIVE evidence; the UI rendered all three outcomes | Isolated temporary state and deterministic simulated provider only; not a production action or trusted production confirmation |
| Public deployment | **VERIFIED** | Signed-out requests to `https://closeloop-zeta.vercel.app` returned 200 for `/`, `/health`, and `/demo/`; `/demo/run` returned all three server-generated outcomes; `/mcp` correctly returned 401; a fresh browser rendered Verified, Not completed, and Awaiting proof without SSO | No live provider, production storage/auth, Alexa+, or AWS; admission is per instance, not global rate limiting; Origin checks are browser control, not authentication |
| Live AWS | **NOT VERIFIED** | None claimed | Credentials, table, IAM, and CloudFormation execution unavailable |
| Live Alexa+ | **NOT VERIFIED** | None claimed | Partner tooling, onboarding, public endpoint, OAuth, confirmation authority, and host rendering unavailable |

## Final evidence counts

- Final release-QA complete suite: **216 passed** (server-backed demo package: 214;
  pre-integration deployment baseline: 187; Milestone 7 baseline: 183).
- Public demo API/browser/security: **29 passed**; existing MCP/demo cases: **12 passed**; combined
  focused checkpoint: **41 passed**.
- Confirmation-attestation suite: **31 passed**.
- General adversarial/security suite: **78 passed**.
- AWS/lifecycle/verifier regression: **46 passed**.
- Alexa+/MCP regression: **12 passed**.
- Proof-card/UI regression: **16 passed**.
- Submission demo package: **2 passed**.
