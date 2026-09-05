# CloseLoop Handoff

## Current phase

Milestone 3 is complete. The Milestone 2 action lifecycle now uses a durable, owner-scoped SQL
repository with a bearer-token authorization boundary. The deterministic verification core and
all prior lifecycle semantics remain intact.

The official Amazon Devices Builder Tools MCP context is initialized for later Amazon-specific
work, but no Milestone 4, Alexa+ integration, AWS orchestration, final UI, additional provider
category, or live deployment work was started.

## Implemented in Milestone 3

- Replaced process-local resolution storage with a SQLAlchemy repository supporting file-backed
  SQLite for local development and PostgreSQL through `psycopg` for shared serverless storage.
- Persisted resolution/owner identifiers, intent, provider mode, lifecycle state and history,
  optimistic version, confirmation time, execution receipt and observation time, independent
  read-back and observation time, verifier result and evaluation time, and terminal outcome.
- Preserved the exact lifecycle and terminal mapping:
  `REQUESTED -> AWAITING_CONFIRMATION -> EXECUTING -> VERIFYING`, followed by
  `PASS -> VERIFIED`, `FAIL -> NOT_COMPLETED`, or
  `INCONCLUSIVE -> AWAITING_PROOF`.
- Added version-checked conditional transitions so concurrent instances cannot both advance the
  same confirmation. Stale writers fail before provider execution.
- Enforced repository-level invariants: execution requires persisted confirmation, verification
  requires persisted execution evidence, terminal state requires the complete independent
  verifier chain, illegal lifecycle jumps fail, and an existing terminal row cannot be changed.
- Added an HTTP authorization boundary using issuer- and audience-bound HS256 JWTs. The owner key
  is a SHA-256 digest of validated `iss` and `sub`; no tool accepts a caller-provided principal.
- Scoped every lookup, confirmation, evidence fetch, and open-resolution query to the owner key.
  Missing and unauthorized resolution IDs intentionally return the same error.
- Required the `closeloop:resolutions` scope and preserved DNS-rebinding host/origin protections.
- Kept exactly the five strict MCP tools:
  - `start_resolution`
  - `confirm_resolution_action`
  - `get_resolution_status`
  - `get_resolution_evidence`
  - `list_open_resolutions`
- Preserved `/`, `/health`, and Streamable HTTP `/mcp`. The complete MCP ASGI app is mounted so
  its authentication middleware remains in the request path.
- Updated the package and MCP/FastAPI version to `0.3.0` and locked the new SQL/JWT dependencies.

There is no `set_verdict`, `mark_success`, `force_pass`, or equivalent write method. Provider
execution claims remain evidence only. Only `verify_cancellation` produces `PASS`, `FAIL`, or
`INCONCLUSIVE`, and the repository validates the resulting terminal/evidence correspondence.

## Amazon Devices Builder Tools initialization

The exact requested initializer was run from the repository root:

```bash
npx -y @amazon-devices/amazon-devices-buildertools-mcp@latest init-context
```

Interactive choices were Codex, update `/Users/colbyweiss/.codex/config.toml`, use the repository
root for the context file, and opt out of a project identifier. The initializer reported MCP
package version `1.0.10` and wrote:

- repository `AGENTS.md`, subsequently amended only with a CloseLoop authority/scope preamble;
- repository `.adbt-config.json` containing the private/opt-out identifier;
- an enabled `amazon-devices-buildertools-mcp` `npx` stanza in the global Codex config;
- 12 Amazon Devices Vega skills plus the Amazon Developers community
  `vega-multi-tv-migration` skill under `/Users/colbyweiss/.agents/skills`.

Every installed file was inventoried. The files are text/JSON templates, their JSON files parse,
no installed file is executable, and the 12 packaged skills share the same license. The skill
corpus is Vega/Fire OS-focused and contains no Alexa+-specific guidance. No generated React
Native/Vega architecture, dependency, or template was copied into CloseLoop. The initializer
printed npm deprecation warnings for transitive CLI packages; it did not add npm dependencies or
a `package.json` to this repository.

The generated context requires an explicit Vega/Fire OS platform for documentation requests.
CloseLoop has not selected either platform, so no platform was invented and no Amazon Devices MCP
documentation call was made in this session. `HACKATHON_REQUIREMENTS.md` records the future
official-documentation and submission-evidence gate; the existing CloseLoop constraints remain
higher authority.

## Baseline reproduced before changes

The authoritative starting point was a clean `main` branch at `2810fd0` with `HEAD`, `main`, and
`origin/main` aligned:

```bash
git status --short
git log -5 --oneline --decorate
uv lock --check
uv sync --locked --extra test --no-editable
uv run --no-editable pytest -q
```

Result before Milestone 3 changes: `19 passed`, with one non-failing Starlette/anyio deprecation
warning. That run reproduced the Milestone 2 baseline, including:

- healthy evidence: `PASS / Verified`;
- provider false-success plus contradictory read-back: `FAIL / Not completed`;
- unavailable independent read-back: `INCONCLUSIVE / Awaiting proof`;
- HTTP 200 with the expected JSON at both `/` and `/health`.

## Final verification evidence

Commands run against the final Milestone 3 diff:

```bash
uv lock --check
uv sync --locked --extra test --no-editable
uv run --no-editable python -m compileall -q src main.py
uv run --no-editable pytest -q tests/test_durable_repository.py tests/test_resolution_lifecycle.py tests/test_mcp_server.py
uv run --no-editable pytest -q
git diff --check
```

Results:

- dependency lock check passed (`44` packages resolved);
- locked environment sync passed (`39` packages checked);
- source and Vercel entrypoint compilation passed;
- focused durability/lifecycle/MCP suite: `25 passed`;
- full suite, including every prior test: `29 passed`;
- diff whitespace check passed;
- one non-failing upstream warning remains: Starlette's test client uses the deprecated
  `anyio.abc.BlockingPortal` alias.

Verification level: **INTEGRATION VERIFIED locally**. SQLite files simulated process/repository
re-instantiation, and the MCP authorization boundary was exercised through the ASGI Streamable
HTTP endpoint. PostgreSQL compatibility is implemented through SQLAlchemy/psycopg but was not
tested against a live database or Vercel deployment.

## Milestone 3 acceptance results

1. All prior 19 tests remain green in the final 29-test run.
2. Resolution state and all evidence survive repository and service re-instantiation.
3. Healthy, false-success, and evidence-outage outcomes persist respectively as
   `PASS / Verified`, `FAIL / Not completed`, and `INCONCLUSIVE / Awaiting proof`.
4. Terminal rows reject later writes at the repository boundary.
5. Stale cross-instance writers reject with an optimistic-concurrency error.
6. Direct illegal lifecycle jumps are rejected.
7. Repository writes cannot enter `EXECUTING` without persisted explicit confirmation.
8. A second principal cannot read, confirm, fetch evidence for, or list the first principal's
   resolution, both through the service/repository and through authenticated MCP HTTP calls.
9. Missing bearer authentication returns HTTP 401; a valid token lacking the required scope
   returns HTTP 403.
10. Strict MCP schemas still reject undeclared verdict/status/success fields before execution,
    and the public surface remains exactly five tools with no verdict-write method.
11. The FastAPI root and health routes remain HTTP 200 with their prior response contracts.
12. A serverless environment without a shared database URL fails closed instead of using
    ephemeral filesystem state.

## Changed repository files

- `.adbt-config.json`
- `.gitignore`
- `AGENTS.md`
- `HACKATHON_REQUIREMENTS.md`
- `HANDOFF.md`
- `README.md`
- `apps/mcp-server/README.md`
- `docs/architecture.md`
- `docs/trust-model.md`
- `pyproject.toml`
- `src/closeloop/__init__.py`
- `src/closeloop/auth.py`
- `src/closeloop/http_app.py`
- `src/closeloop/lifecycle.py`
- `src/closeloop/mcp_server.py`
- `src/closeloop/repository.py`
- `tests/test_durable_repository.py`
- `tests/test_mcp_server.py`
- `tests/test_resolution_lifecycle.py`
- `uv.lock`

## Known limitations / blockers

There are no blockers to the requested Milestone 3 acceptance boundary. Remaining limitations are
explicit:

- No live Vercel deployment or PostgreSQL service was exercised. Cross-instance behavior was
  verified locally by constructing independent repositories/services over the same SQLite file.
- Schema creation is idempotent through SQLAlchemy `create_all`; versioned production migrations
  are not yet implemented.
- CloseLoop is a JWT resource server in this milestone. It does not mint tokens, provide OAuth
  authorization flows, or implement PKCE. The deployment must provide an external issuer and a
  secret of at least 32 bytes.
- A process failure after the action enters `EXECUTING` or `VERIFYING` leaves a truthful persisted
  in-progress state. Automatic recovery/reconciliation is not implemented, preventing unsafe
  blind re-execution but requiring a later recovery design.
- The cancellation provider remains the labeled first-party demo simulation; no live provider,
  Alexa+, or AWS path was tested.
- The newly configured Amazon Devices MCP will be available to newly started Codex sessions; its
  installed context currently supplies Vega/Fire OS guidance, not Alexa+ compliance evidence.
- On this macOS host, Python skips hidden editable-install `.pth` files, so the documented `uv`
  commands use `--no-editable` for deterministic local imports.

## Next recommended step

Stop here. After explicit approval to begin Milestone 4, first use the official Amazon Devices
Builder Tools documentation context where applicable to re-verify then-current Alexa+/MCP and
submission constraints. Then add production schema migrations and an idempotent
recovery/reconciliation path for persisted `EXECUTING` and `VERIFYING` records before Alexa+, AWS
orchestration, final UI, or broader provider work.
