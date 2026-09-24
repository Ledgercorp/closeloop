# Judging rubric map

This map uses only criterion names already recorded from the [official competition rules](https://amazonappdev2026.devpost.com/rules) and [official overview](https://amazonappdev2026.devpost.com/). It does not add criteria or assert bonus eligibility. Verify the live rules page before submission in case the organizer updates it.

| Official criterion / requirement (as recorded) | What a judge sees | Implementation evidence | Video moment | Supporting evidence and limitation |
|---|---|---|---|---|
| Alexa+ primary track | A normal Alexa-style request and CloseLoop’s outcome ownership story | Authenticated Streamable HTTP MCP server and Alexa+-designed flow | 0:15–0:35 | Seven-tool MCP and integration tests; no live Alexa+ account or device session |
| Runtime technology use | Product behavior backed by the CloseLoop lifecycle rather than a frontend verdict | MCP Python SDK, persistent resolution service, deterministic verifier | 0:35–1:58 | Full suite and public server-backed demo; public demo is an isolated simulation |
| Working demonstration | False success, recovery, separate authorization, independent recheck, receipt, and alternate failure/uncertainty paths | `/demo/` uses server-generated results, evidence, and lifecycle records | 0:35–2:32 | Signed-out Chromium production scenarios; simulated provider, billing, consent, and time |
| Public source and setup | Repository, license, setup steps, and public demo | Public GitHub repository, Apache-2.0 license, README | 2:32–2:45 / description | Source and demo are public; video still must be recorded and uploaded by the creator |
| Hackathon provenance | Clear separation of CloseLoop product work from prior concepts | Build provenance document and repository history | Optional brief end card | `docs/build-provenance.md`; no CUF source copied |
| Product feedback | Reproducible product/tooling observations and limitations | Feedback and friction logs | Not required in the 2:45 story | `docs/product-feedback.md` and `docs/friction-log.md`; entries remain historical, not fabricated |
| AWS Builder | A relevant, bounded AWS persistence design rather than decorative service claims | Optional DynamoDB repository and one-table template | Optional end card only if time | Moto-tested; no live AWS table, deployment, or runtime is claimed |
| Technical implementation | Separate action, evidence, verification, recovery, and confirmation authority | Seven closed-schema MCP tools; owner-scoped persistence; deterministic verifier; recovery state; adversarial coverage | 0:35–1:58 and 2:32–2:45 | `docs/architecture.md`, `docs/trust-model.md`, tests; no live identity provider or scheduler |
| Design | Consumer language first, highlighted false success, understandable responsibility, and expandable proof | Public demo first viewport, guided recovery, alternate outcomes, trust explanation, receipt | 0:00–2:32 | Signed-out mobile/desktop production checks; simulation disclosures remain visible |
| Potential impact | Prevents users from mistaking an accepted action for a completed real-world result | Persistent outcome tracking, quiet attention, safe recovery, evidence-backed receipts | 0:35–2:17 | Current executable workflow is simulated subscription cancellation, not broad provider coverage |
| Quality of idea | Memorable distinction between requested, executed, resolved, and recovered | False-success moment plus a separate recovery action and re-verification | 0:35–1:58 | API and browser tests show three outcomes and recovery; no outcome guarantee is claimed |

## Eligibility and bonus boundary

The AWS Builder mapping is an evidence-based description of the Moto-tested DynamoDB repository path. It is not a claim of live AWS use or automatic bonus eligibility. Do not claim any bonus unless the official current rules and submitted evidence establish it.

## Strongest judge moments

1. **0:35–0:55:** Provider acceptance is visibly contradicted by the independent read-back.
2. **1:15–1:58:** Recovery uses a separate authorization and is independently rechecked.
3. **1:58–2:17:** The post-cancellation charge is preserved as an outcome violation; the refund draft is not sent.
4. **2:17–2:45:** Consumer responsibility and trust explanation sit ahead of technical proof.
