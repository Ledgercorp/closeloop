# Codex First Mission — Milestone 2

## Mission
Implement the real CloseLoop MCP action lifecycle around the existing deterministic verification core.

Do not redesign CloseLoop. Do not broaden scope. Do not weaken the trust boundary.

## Before changing code
1. Read:
   - `HANDOFF.md`
   - `NON_NEGOTIABLES.md`
   - `ACCEPTANCE_TESTS.md`
   - `HACKATHON_REQUIREMENTS.md`
   - `DEMO_SPEC.md`
   - `docs/architecture.md`
   - `docs/trust-model.md`
2. Inspect git status and recent commits.
3. Run the existing test suite.
4. Verify the Vercel/FastAPI baseline remains understandable and reproducible.
5. Confirm the false-success and insufficient-evidence cases still behave correctly.

## Implement
Build an MCP service that exposes:
- `start_resolution`
- `confirm_resolution_action`
- `get_resolution_status`
- `get_resolution_evidence`
- `list_open_resolutions`

Use a deterministic lifecycle such as:

`REQUESTED -> AWAITING_CONFIRMATION -> EXECUTING -> VERIFYING -> VERIFIED`

with terminal alternatives:

`NOT_COMPLETED`

`AWAITING_PROOF`

The exact internal enum names may differ, but transitions must be explicit and tested.

## Required behavior
- Consequential execution must require explicit confirmation before mutation.
- Execution success claims must never directly produce VERIFIED.
- Independent evidence collection must drive verification.
- The verifier must be deterministic.
- PASS / FAIL / INCONCLUSIVE semantics must remain intact internally.
- User-facing language should map cleanly to:
  - PASS -> Verified
  - FAIL -> Not completed
  - INCONCLUSIVE -> Awaiting proof
- There must be no API/MCP method that lets an agent set the verdict.
- MCP transport/version must match the current Amazon hackathon requirements documented in `HACKATHON_REQUIREMENTS.md`.

## Tests required
At minimum add tests proving:
- start creates a non-terminal resolution
- unconfirmed consequential action cannot execute
- confirmed action can progress to verification
- claimed success + contradictory evidence => FAIL / Not completed
- successful execution + successful read-back => PASS / Verified
- missing/insufficient independent evidence => INCONCLUSIVE / Awaiting proof
- caller cannot directly set or override verdict
- repeated status/evidence reads do not mutate outcome
- invalid state transitions are rejected

## Definition of done
Milestone 2 is done only when:
- all existing tests pass
- all new Milestone 2 tests pass
- MCP tools are callable in the supported transport
- Vercel baseline is not broken
- trust boundaries remain intact
- docs are updated with exact commands and evidence

Then stop. Do not proceed to Milestone 3 automatically.
