# Judging rubric map

Verified against the [official rules](https://amazonappdev2026.devpost.com/rules) and
[hackathon overview](https://amazonappdev2026.devpost.com/) on 2026-09-06. Judges may rely only on
the description, images, and video, so each claim below has a visible demo moment and repository
artifact.

## Stage 1 eligibility

| Requirement | CloseLoop evidence | Repository/demo proof | Strength | Limitation |
|---|---|---|---|---|
| Alexa+ primary track | Self-hosted MCP server using Streamable HTTP and MCP 2025-11-25 | `src/closeloop/mcp_server.py`; `tests/test_alexa_integration.py`; 2:25 video | Strong local integration | No live Alexa+ client, add-on, Local Inspector, or account linking |
| Runtime technology use | Official MCP Python SDK is imported and executes the five-tool lifecycle | `pyproject.toml`; `src/closeloop/mcp_server.py`; public server-backed demo | Strong local integration plus public deterministic demo | Public demo is isolated simulation; live MCP actions remain authenticated and are not publicly exercised |
| Working demonstration | Confirmation plus PASS/FAIL/INCONCLUSIVE are generated through the deployed real lifecycle/provider/read-back/verifier path | `src/closeloop/public_demo_api.py`; `/demo/`; 0:20–2:25 video | Strong, public, and reproducible | Demo provider and confirmation are labeled simulations |
| Public source and setup | Public GitHub repository, canonical Apache-2.0, quick-start commands | `README.md`; `LICENSE` | Strong; anonymous access and GitHub license detection verified | Public video remains a manual submission step |
| Hackathon provenance | New CloseLoop code is separated from prior CUF concepts | `docs/build-provenance.md`; README provenance | Explicit | Prior conceptual experience is disclosed, not claimed as new |
| Product feedback | Actual tooling attempts, successes, limits, and recommendations | `docs/product-feedback.md`; `docs/friction-log.md` | Detailed and reproducible | Some Alexa+/AWS tooling was inaccessible |
| AWS Builder | DynamoDB is the optional authoritative repository, not a decorative call | `src/closeloop/dynamodb_repository.py`; `infra/aws/closeloop-dynamodb.json`; 2:25 video | Meaningful architecture | Moto-simulated; no live AWS deployment |

## Stage 2 criteria

| Criterion | CloseLoop evidence | Exact proof | Strength | Limitation |
|---|---|---|---|---|
| Technical implementation | Five closed-schema MCP tools; bearer-derived ownership; trusted confirmation; separate receipt/read-back; deterministic verdict; SQL/DynamoDB invariants; read-only MCP App | `docs/architecture.md`, `docs/trust-model.md`, 214-test suite, 0:45–2:45 video | Very strong: cross-layer contracts and adversarial evidence | Live Alexa+, AWS, provider, and PostgreSQL remain unverified |
| Design | Voice-first Ask → Confirm → Act → Verify → Explain; three plain-language outcomes; expandable proof without developer-log clutter | Production proof card; public judge UI; 0:20–2:25 video | Strong, coherent consumer story | Not Alexa+ host rendering; local proof-card plus public judge UI verified |
| Potential impact | Prevents false completion for financial life-admin actions; preserves uncertainty rather than hiding it | False-success moment at 1:35; problem/solution copy | Specific, credible need with broad future applicability | Current executable provider covers subscription cancellation only |
| Quality of idea | Separates executor from verdict authority and makes contradiction/uncertainty first-class; uses stateful MCP Apps rather than a Q&A wrapper | False-success evidence; deterministic verifier; proof card; security report | Distinct and memorable | Not a live multi-service provider workflow |

## AWS Builder positioning

DynamoDB owns a real product responsibility: authoritative owner-scoped lifecycle and evidence
state across server instances. Strongly consistent reads prevent stale evidence from being treated
as current. Conditional writes enforce expected version, allowed transition, confirmation
consumption, and immutable terminal outcomes. The project deliberately excludes decorative
Bedrock, AgentCore, Strands, Lambda, Step Functions, and EventBridge calls that would not improve
the synchronous demo.

## Highest-value judging moments

1. **First 10 seconds:** “A tool saying success is not proof.”
2. **0:45:** execution claim and independent evidence visibly separated.
3. **1:35:** provider says success while CloseLoop says Not completed.
4. **2:05:** evidence outage becomes Awaiting proof, never invented certainty.
5. **2:25:** five-tool MCP, deterministic verifier, trusted confirmation, and meaningful DynamoDB.

## Submission risk

The source package and signed-out deterministic Vercel demo are ready for an Alexa+ self-hosted-MCP
entry, but live Alexa+ host behavior is not verified. The public browser calls an isolated deployed
CloseLoop lifecycle/provider/read-back/verifier path and retains its simulation labels. A real Alexa+
client/add-on connection would strengthen eligibility evidence but must not be claimed until
actually exercised.
