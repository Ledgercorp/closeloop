# Milestone 2 Acceptance Tests

Milestone 2 is not complete until all existing tests and all tests below pass.

## Baseline preservation
1. Existing verifier tests still pass.
2. Claimed success with contradictory evidence still produces FAIL / Not completed.
3. Missing independent evidence still produces INCONCLUSIVE / Awaiting proof.
4. Vercel/FastAPI entrypoint remains valid.

## Lifecycle
5. `start_resolution` creates a resolution in a non-terminal state.
6. Consequential actions enter an explicit confirmation-required state before execution.
7. `confirm_resolution_action` is required before mutation.
8. Invalid state transitions are rejected.
9. Repeated reads of status/evidence do not mutate state.

## Verification integrity
10. Execution-provider success claims never directly create VERIFIED.
11. Successful execution + independent read-back confirming target state => PASS / Verified.
12. Claimed success + independent read-back contradicting target state => FAIL / Not completed.
13. Action possibly executed + insufficient independent evidence => INCONCLUSIVE / Awaiting proof.
14. No public API/MCP method allows the caller to directly write PASS / FAIL / INCONCLUSIVE.
15. No caller can override a terminal verifier result by passing a field such as `verdict`, `success`, `status`, or equivalent.

## MCP surface
16. `start_resolution` is registered and callable.
17. `confirm_resolution_action` is registered and callable.
18. `get_resolution_status` is registered and callable.
19. `get_resolution_evidence` is registered and callable.
20. `list_open_resolutions` is registered and callable.
21. No `set_verdict`, `mark_success`, `force_pass`, or equivalent tool is registered.
22. MCP transport/version matches the hackathon requirements in `HACKATHON_REQUIREMENTS.md`.

## Evidence quality
23. Evidence records distinguish execution claim from independent read-back.
24. Evidence includes enough provenance/timestamps/identifiers to explain how a result was reached.
25. User-facing output can explain why a task is Verified, Not completed, or Awaiting proof without exposing internal implementation noise.

## Stop condition
When all 25 checks pass, update `HANDOFF.md` with exact evidence and stop before Milestone 3.
