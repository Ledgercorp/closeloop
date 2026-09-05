# CloseLoop Handoff

## Product definition
CloseLoop is an Alexa+ action-completion system that carries consequential tasks through execution, independently verifies the resulting state, and only tells the user they are done when there is evidence.

CloseLoop is intentionally distinct from CUF. CUF is broader verification infrastructure. CloseLoop is a consumer-facing Alexa+ completion product with a concrete action lifecycle, confirmation UX, evidence collection, and outcome communication.

## Current state
Milestone 0 and Milestone 1 are complete.

Implemented:
- deterministic verification core
- PASS / FAIL / INCONCLUSIVE semantics
- false-success rejection
- insufficient-evidence handling
- demo provider/tests
- Vercel-compatible FastAPI entrypoint
- architecture/trust-model/judging docs
- Apache-2.0 license

The repository is deployed through Vercel and is intended to remain deployable throughout development.

## Canonical winning demo
Primary scenario: subscription cancellation.

User intent:
> Alexa, cancel my subscription and make sure I will not be charged again.

Required demo outcomes:
1. Verified — cancellation succeeded and independent read-back proves auto-renew is off.
2. Not completed — execution/provider claims success but independent read-back proves the subscription is still active or auto-renew remains on.
3. Awaiting proof — the action may have been performed, but independent evidence is not yet available.

The product must make these distinctions obvious to a non-technical judge in seconds.

## Trust boundaries
The system has three separate planes:

1. Planning / conversational plane
   - Alexa+ or an agent interprets user intent.
   - May plan steps.
   - Must not determine final completion status.

2. Execution plane
   - Performs the requested action.
   - Produces an action receipt/claim.
   - Its own success claim is evidence only.

3. Verification plane
   - Independently reads resulting state.
   - Applies deterministic rules.
   - Produces PASS / FAIL / INCONCLUSIVE.

No agent, model, execution provider, Alexa surface, or external caller may override the verdict.

## Exact next milestone
Milestone 2: implement a production-quality MCP action lifecycle around the existing deterministic verifier.

Required tools:
- `start_resolution`
- `confirm_resolution_action`
- `get_resolution_status`
- `get_resolution_evidence`
- `list_open_resolutions`

Forbidden tools / capabilities:
- `set_verdict`
- `mark_success`
- any path that lets an agent or execution provider directly set PASS / FAIL / INCONCLUSIVE

## Milestone 2 stop condition
Stop after Milestone 2 acceptance criteria pass.

Do not begin:
- final UI polish
- full Alexa production integration
- AgentCore/Bedrock orchestration beyond what Milestone 2 strictly needs
- additional provider categories
- broad product redesign

Update this file with exact commands, test evidence, known blockers, changed files, and the next recommended milestone before stopping.
