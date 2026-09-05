# CloseLoop Handoff

## Current phase

Milestone 2 is complete. Milestones 0 and 1 remain intact, and the canonical
subscription-cancellation demo now has a production-shaped MCP action lifecycle around the
existing deterministic verification core.

No Milestone 3, final UI, full Alexa integration, AWS orchestration, or additional provider
category work was started.

## Implemented in Milestone 2

- explicit lifecycle transitions:
  `REQUESTED -> AWAITING_CONFIRMATION -> EXECUTING -> VERIFYING -> terminal`;
- terminal states that preserve the required mapping:
  `PASS -> VERIFIED`, `FAIL -> NOT_COMPLETED`, and
  `INCONCLUSIVE -> AWAITING_PROOF`;
- confirmation-gated execution: starting a consequential resolution performs no provider
  mutation, and `confirmed=true` is required before execution;
- separate execution-claim, independent-read-back, and verifier evidence records with source,
  identifier, and UTC timestamp provenance;
- a locked process-local resolution repository that rejects duplicate/invalid transitions;
- exactly five MCP tools:
  - `start_resolution`
  - `confirm_resolution_action`
  - `get_resolution_status`
  - `get_resolution_evidence`
  - `list_open_resolutions`
- strict MCP input schemas that reject undeclared fields before handler execution, including
  attempted `verdict`, `success`, or `status` overrides;
- Streamable HTTP at `/mcp`, with a test proving negotiation of MCP `2025-11-25` and tool calls;
- DNS-rebinding defenses with exact host/origin allowlists, automatic `VERCEL_URL` support,
  and configurable `CLOSELOOP_ALLOWED_HOSTS` / `CLOSELOOP_ALLOWED_ORIGINS`;
- FastAPI/Vercel health routes preserved at `/` and `/health`;
- locked Python dependencies and an installable `src` package at version `0.2.0`.

There is no `set_verdict`, `mark_success`, `force_pass`, or equivalent MCP/API method. Only
`verify_cancellation` produces `PASS`, `FAIL`, or `INCONCLUSIVE`; the lifecycle maps that
immutable result to its user-facing terminal state.

## Baseline reproduced before changes

The host `python3` is 3.9.6, below the repository's Python 3.11 requirement, and initially had
no pytest module. The first command therefore failed before test collection:

```bash
python3 -m pytest -q
```

An isolated Python 3.11.16 environment was then created and the original suite was run:

```bash
uv venv --python /Users/colbyweiss/.local/bin/python3.11 .venv
uv pip install --python .venv/bin/python -e . pytest httpx
.venv/bin/python -m pytest -q
```

Result before code changes: `4 passed`.

The original deterministic core was also exercised directly. Results:

```text
healthy: PASS / Verified
false_success: FAIL / Not completed
evidence_outage: INCONCLUSIVE / Awaiting proof
```

The original `main:app` returned HTTP 200 from both `/` and `/health` through FastAPI's test
client before changes.

## Final verification evidence

Commands run against the final Milestone 2 diff:

```bash
uv lock --check
uv sync --locked --extra test --no-editable
uv run --no-editable python -m compileall -q src main.py
uv run --no-editable pytest -q -vv tests/test_resolution_lifecycle.py tests/test_mcp_server.py
uv run --no-editable pytest -q
git diff --check
```

Results:

- dependency resolution/lock check: passed (`39` packages resolved, `36` checked);
- source and Vercel entrypoint compilation: passed;
- Milestone 2 focused suite: `15 passed`;
- full suite: `19 passed`;
- diff whitespace check: passed;
- one non-failing upstream warning remains: Starlette's test client uses the deprecated
  `anyio.abc.BlockingPortal` alias.

Verification level: **INTEGRATION VERIFIED** locally. The supported MCP protocol was exercised
through the ASGI Streamable HTTP endpoint; no remote deployment or Alexa client was live-tested.

## Acceptance results

All 25 checks in `ACCEPTANCE_TESTS.md` pass:

1. Existing verifier suite passes in the full 19-test run.
2. False success remains `FAIL / Not completed`.
3. Missing independent evidence remains `INCONCLUSIVE / Awaiting proof`.
4. `main:app`, `/`, and `/health` remain valid.
5. Start returns a non-terminal resolution.
6. Consequential start returns `AWAITING_CONFIRMATION`.
7. Missing/false confirmation rejects execution and leaves provider mutation count at zero.
8. Repeated confirmation rejects an invalid terminal transition.
9. Repeated status/evidence reads return identical state and evidence.
10. A provider success claim alone never produces `VERIFIED`.
11. Successful execution plus confirming read-back produces `PASS / Verified`.
12. Claimed success plus contradictory read-back produces `FAIL / Not completed`.
13. Possibly executed action plus unavailable read-back produces
    `INCONCLUSIVE / Awaiting proof`.
14. The public MCP surface contains no verdict-write method.
15. Extra `verdict`, `success`, and `status` fields are rejected before execution.
16. `start_resolution` is registered and called through MCP.
17. `confirm_resolution_action` is registered and called through MCP.
18. `get_resolution_status` is registered and called through MCP.
19. `get_resolution_evidence` is registered and called through MCP.
20. `list_open_resolutions` is registered and called through MCP.
21. No forbidden or equivalent verdict-write tool is registered.
22. Streamable HTTP negotiates protocol version `2025-11-25` at `/mcp`.
23. Execution claim and independent read-back have distinct evidence types and sources.
24. Evidence includes resolution/request identifiers, UTC timestamps, sources, and verifier ID.
25. Status/evidence exposes plain-language state and reason for all three outcomes.

## Changed files

- `.gitignore`
- `HANDOFF.md`
- `README.md`
- `apps/mcp-server/README.md`
- `docs/architecture.md`
- `docs/trust-model.md`
- `main.py`
- `pyproject.toml`
- `src/closeloop/__init__.py`
- `src/closeloop/http_app.py`
- `src/closeloop/lifecycle.py`
- `src/closeloop/mcp_server.py`
- `tests/test_mcp_server.py`
- `tests/test_resolution_lifecycle.py`
- `uv.lock`

## Known limitations / blockers

There are no blockers to the Milestone 2 acceptance criteria. Remaining limitations are stated
explicitly rather than represented as completed work:

- resolution state is process-local and is not durable across restarts or Vercel instances;
- the cancellation provider is the labeled first-party demo simulation, not a live provider;
- remote authentication/PKCE, Alexa+ client integration, and AWS orchestration are not present;
- Vercel remained locally importable/testable but was not deployed or production-tested in this
  milestone;
- on this macOS host, Python skips hidden editable-install `.pth` files, so documented `uv`
  commands use `--no-editable` for deterministic local imports.

## Next recommended step

Stop here. After owner approval to begin Milestone 3, first define and test a durable,
cross-instance resolution repository plus its authorization boundary so confirmation state and
terminal evidence survive process restarts. Do not add Alexa/AWS orchestration before that state
contract preserves the Milestone 2 trust invariants.
