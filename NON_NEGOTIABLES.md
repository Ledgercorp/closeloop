# CloseLoop Non-Negotiables

These constraints are architectural, product, and hackathon-critical. Do not weaken them to make implementation easier.

## Product boundary
- CloseLoop is not a generic assistant.
- CloseLoop is not CUF renamed.
- CloseLoop is a consumer-facing Alexa+ completion product for consequential actions.
- The core promise is: do not tell the user a consequential task is done unless independent evidence supports that claim.

## Trust and verdict integrity
- The planning/conversational agent cannot set the final verdict.
- The execution provider cannot set the final verdict.
- Alexa+ cannot override the verifier.
- External callers cannot directly write PASS / FAIL / INCONCLUSIVE.
- There must be no `set_verdict`, `mark_success`, `force_pass`, or equivalent control path.
- Execution receipts/claims are evidence inputs only.
- Independent read-back evidence must be evaluated separately from the execution claim.
- Deterministic logic, not an LLM judgment, produces PASS / FAIL / INCONCLUSIVE.

## Outcome semantics
Internal semantics remain:
- PASS
- FAIL
- INCONCLUSIVE

User-facing semantics remain:
- PASS -> Verified
- FAIL -> Not completed
- INCONCLUSIVE -> Awaiting proof

Do not collapse INCONCLUSIVE into PASS or FAIL.

## Confirmation and safety
- Consequential mutations require explicit user confirmation before execution.
- Reads/status checks must not silently mutate state.
- Invalid state transitions must fail closed.
- A partial or timed-out execution is not success.
- Missing evidence is not success.

## Hackathon constraints
- Maintain clear provenance between pre-existing work and work built during the hackathon window.
- Do not misrepresent CUF as hackathon-created work.
- Keep the repository public and submission-ready.
- Preserve the Apache-2.0 license unless rules require a compatible change.
- Maintain the friction log as Amazon/AWS/Alexa integration work proceeds.
- Optimize for judge comprehension and a sub-3-minute demo, not maximum feature count.

## Engineering discipline
- Keep tests deterministic.
- Do not fabricate integrations or successful results.
- Do not add dead/demo-only code that bypasses real paths without labeling it clearly as simulation.
- Do not break the deployable FastAPI/Vercel baseline while building MCP support.
- Update `HANDOFF.md` at every milestone boundary.
