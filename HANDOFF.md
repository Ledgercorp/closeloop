# CloseLoop Handoff

## Current phase

Milestone 7 is complete at **PARTIALLY ADVERSARIAL VERIFIED**. The prior untrusted
`{resolution_id, confirmed}`
boundary now requires a short-lived, signed `closeloop.confirmation/v1` attestation bound to the
authenticated owner, exact resolution and canonical action digest, affirmative decision, trusted
issuer/audience, issue/expiry times, and unique attestation ID. Verified provenance is consumed by
the conditional `AWAITING_CONFIRMATION -> EXECUTING` transition and preserved in SQLite or DynamoDB
history. Missing production configuration denies all confirmations; no signing secret or test
issuer is enabled by default.

The two former strict xfails for cross-resolution and stale confirmation are ordinary passing
tests in the focused runs so far. This remains local/integration verification plus Moto-simulated
DynamoDB—not live Alexa+, AWS, provider, production OAuth, or trusted human-confirmation issuance.
All focused regressions, the post-fix complete-suite checkpoint, and the CRITICAL-risk Governor
final review passed. Milestone 8, demo optimization, and submission packaging have not started.

## Implemented in Milestone 7

- Replaced the untrusted plain-confirmation boundary with a product-core
  `ConfirmationAttestationVerifier` abstraction and explicit `closeloop.confirmation/v1` contract.
  The production adapter requires dedicated issuer, audience, and 32-byte-or-stronger HMAC secret
  configuration; absent, partial, or weak configuration selects a deny-all verifier.
- Bound every accepted attestation to the authenticated bearer-token subject, exact resolution,
  `cancel_subscription` action, server-computed canonical action digest, literal affirmative
  decision, issue time, expiry, trusted issuer/audience, and bounded unique attestation ID. Tokens
  are capped at 4,096 bytes and fixed to HS256; malformed, unsigned, modified, stale, future,
  overlong, or mismatched claims receive one generic rejection.
- Persisted the verified contract version, issuer, attestation ID, issue/expiry times, action digest,
  and token SHA-256—not the compact token or signing secret—on the unique `EXECUTING` transition.
  SQL compares exact prior history application-side and atomically conditions owner, identifier,
  version, and state; DynamoDB additionally conditions exact prior history. Concurrent or repeated
  redemption for that bound resolution therefore has at most one winner across repository
  instances.
- Kept issuance outside the application core. Automated tests use a deterministic issuer under
  `tests/`; the proof-card validation builder uses a separately labeled local-only signer. Neither
  is a production default or evidence of Alexa+ issuance. A production authority must obtain the
  human decision independently rather than blindly sign agent-controlled fields.
- Changed the existing `confirm_resolution_action` schema minimally by requiring
  `confirmation_attestation`; the server still exposes exactly five MCP tools and no verdict-write
  capability. Status and evidence expose the canonical `action_digest` needed by a trusted host.
- Converted the two prior strict xfails for wrong-resolution and stale confirmation into passing
  adversarial tests. Added focused coverage for valid consumption, replay, expiry, future issue
  time, owner/resolution/action mismatch, tampering, unknown issuer, unsigned agent forgeries,
  missing/boolean-only confirmation, concurrent consumption, repository re-instantiation,
  corrupted persisted provenance, deny-all production configuration, and uncertain first writes.
- Made confirmation an exact JSON boolean, so strings and numbers such as `"true"`, `"yes"`, and
  `1` cannot cross the confirmation boundary or execute a provider action.
- Added explicit 2,000-character intent and 64-character resolution-ID limits at MCP and lifecycle
  boundaries before repository access.
- Added structural receipt and independent-evidence validation. Negative/string freshness,
  non-boolean fields, blank/noncanonical/invalid dates, malformed receipts, and adapter exceptions
  fail closed.
- Required a valid successful execution receipt as a necessary—but never sufficient—condition for
  PASS. A failed/malformed receipt followed by apparently positive read-back is INCONCLUSIVE;
  readable fresh evidence that auto-renew remains enabled is still FAIL.
- Normalized provider factory, execution, and read-back failures into safe evidence so an
  infrastructure or adapter failure never becomes VERIFIED.
- Hardened detailed proof-card results by recomputing the evidence verdict and requiring canonical
  provenance plus an ordered five-step lifecycle history. Contradictory, forged, reordered,
  malformed, or unknown results render `Proof unavailable`; hostile text remains escaped text.
- Exercised actual two-thread confirmation races against SQLite and Moto-backed DynamoDB. Exactly
  one conditional transition won and the provider executed once.
- Enforced monotonic lifecycle and provenance timestamps when decoding or persisting a record;
  reordered history and confirmation/execution/read-back/verifier time corruption fail closed.
- Added `docs/adversarial-security.md` with the A–K attack matrix, blocking findings/fixes,
  residual risks, verification scope, and live limitations.
- Updated package, HTTP app, MCP server, and proof-card versions to `0.7.0`.

## Milestone 7 verification evidence

Authoritative starting state was clean `main` at
`4c6768c8c3a29fbd8bb82bef8c13cf17508c2c86`, aligned with `origin/main`. The pre-change complete
suite reproduced the Milestone 6 baseline at `72 passed`; the prior focused `15` UI, `12`
Alexa+/MCP, and `45` AWS/lifecycle results were reused under Usage Guardian.

The general adversarial file collects 78 reproducible cases and the focused confirmation-attestation
file collects 31. Before the original Milestone 7 fixes, 14 exploit variants demonstrated unsafe
execution, incorrect PASS, missing bounds, or an exception. Both former strict expected failures
are now ordinary passing cases. Current-diff validation commands:

```bash
uv lock --check
PYTHONPATH=src uv run --no-editable python -m compileall -q src scripts main.py
PYTHONPATH=src uv run --no-editable pytest -q tests/test_confirmation_attestation.py
PYTHONPATH=src uv run --no-editable pytest -q tests/test_adversarial_security.py
PYTHONPATH=src uv run --no-editable pytest -q \
  tests/test_aws_infrastructure.py tests/test_dynamodb_repository.py \
  tests/test_resolution_lifecycle.py tests/test_durable_repository.py \
  tests/test_cancellation_verifier.py
PYTHONPATH=src uv run --no-editable pytest -q \
  tests/test_alexa_integration.py tests/test_mcp_server.py
PYTHONPATH=src uv run --no-editable pytest -q tests/test_proof_card.py
PYTHONPATH=src uv run --no-editable pytest -q
```

Results before the single complete-suite checkpoint:

- dependency lock and compilation: passed (`62` packages resolved);
- focused confirmation-attestation suite: `31 passed`;
- focused adversarial/security suite: `78 passed`;
- focused AWS/lifecycle/verifier regression: `45 passed`;
- focused Alexa+/MCP regression: `12 passed`, with the pre-existing non-failing
  Starlette/anyio deprecation warning;
- focused proof-card/UI regression: `16 passed`;
- complete suite: `183 passed`, with the same pre-existing warning.

The bounded browser-security host is generated with:

```bash
validation_dir=$(mktemp -d /tmp/closeloop-m7-browser.XXXXXX)
PYTHONPATH=src uv run --no-editable python \
  scripts/build_proof_card_validation.py "$validation_dir"
cd "$validation_dir"
python3 -m http.server 8768 --bind 127.0.0.1
```

It validated one real healthy lifecycle result plus the contradictory read-back, forged provenance,
reordered history, malformed evidence, unknown state, and injected-text fixtures through the exact
production MCP App and official `AppBridge` / `PostMessageTransport` path. The healthy result
rendered `Verified`; all five malformed/forged/unknown results rendered neutral `Proof unavailable`;
the injected `<img>` and `<b>` strings appeared literally in the accessibility tree rather than as
markup. The no-result bridge-loading state remained `Waiting for proof`, not Verified. This is
**LOCAL UI/BROWSER VERIFIED** security behavior, not Alexa+ host verification.

The Development Governor classified the work CRITICAL because it crosses authorization,
mutation, persistence, and consumer trust boundaries. Its pre-implementation adversarial review
identified confirmation coercion, malformed evidence, failed-receipt PASS, and proof-card forgery
as blocking. Its final review rejected unconditional completion because the MCP call cannot prove
that a trusted user approved the selected resolution or that the confirmation is fresh. It also
found backend/card date drift and missing provenance chronology checks; both deterministic evidence
issues were fixed and regression-tested. Usage Guardian reused Milestone 1–6 evidence, used
fail-first targeted cases, bounded
the race/protocol/browser matrix, and ran the complete suite at the final checkpoint.
Its confirmation-attestation pre-implementation review accepted the product-core verifier and
conditional-consumption design with required refinements: version the contract, deny legacy
downgrades, persist full verified provenance, state the per-resolution replay scope precisely,
require complete no-default production configuration, and ensure an external issuer does not
blindly sign client fields. Those refinements are implemented. The final review found and blocked
commit on a PostgreSQL incompatibility in the first SQL replay predicate: PostgreSQL `json` has no
equality operator. The predicate was corrected to use application-side exact-history comparison
plus atomic owner/identifier/version/state guards, and a PostgreSQL-dialect compile regression was
added. Re-review found no remaining BLOCKING/HIGH implementation issue. Direct out-of-band database
mutation without a version update remains outside the repository trust boundary.

## Milestone 7 changed repository files

- `HANDOFF.md`
- `HACKATHON_REQUIREMENTS.md`
- `README.md`
- `docs/adversarial-security.md`
- `docs/architecture.md`
- `docs/friction-log.md`
- `docs/trust-model.md`
- `pyproject.toml`
- `scripts/build_proof_card_validation.py`
- `src/closeloop/alexa_contracts.py`
- `src/closeloop/confirmation.py`
- `src/closeloop/dynamodb_repository.py`
- `src/closeloop/http_app.py`
- `src/closeloop/lifecycle.py`
- `src/closeloop/mcp_app.py`
- `src/closeloop/mcp_server.py`
- `src/closeloop/repository_contract.py`
- `src/closeloop/repository.py`
- `src/closeloop/verifier.py`
- `tests/__init__.py`
- `tests/conftest.py`
- `tests/confirmation_support.py`
- `tests/test_alexa_integration.py`
- `tests/test_adversarial_security.py`
- `tests/test_confirmation_attestation.py`
- `tests/test_durable_repository.py`
- `tests/test_dynamodb_repository.py`
- `tests/test_mcp_server.py`
- `tests/test_proof_card.py`
- `tests/test_resolution_lifecycle.py`
- `uv.lock`

## Milestone 7 residual risks and next milestone

- The CloseLoop resource-server gap is closed locally: untrusted callers cannot create, modify,
  replay, or retarget a valid configured-authority attestation. Live Alexa+/authorization-server
  issuance is still unverified. Public Alexa+ documentation covers bearer authentication for
  user/write tools but does not document a per-action human-confirmation attestation, so CloseLoop
  does not claim Alexa+ currently emits this contract.
- Replay protection is single-use for the exact principal/resolution/action-bound resource, not a
  global JTI registry. Exact binding prevents cross-resource reuse and atomic history preservation
  prevents replacement on that resolution; a future multi-resource contract would need a global
  replay namespace.
- Pre-v1 persisted resolutions fail closed because they lack the explicit contract marker. There is
  no provisioned production store to migrate; a real upgrade with live data requires an intentional
  migration or retirement plan.
- A fully self-consistent malicious MCP host result cannot be distinguished by a read-only card
  without signed server evidence or a trusted host channel.
- The app bounds schema fields but relies on deployment-edge controls for raw request-body size.
- The proof-card module remains pinned to jsDelivr, leaving an external availability/supply-chain
  dependency.
- Alexa+ client/OAuth/device behavior, live AWS/IAM/DynamoDB races, a real provider/read-back system,
  network partitions, PostgreSQL parity, penetration/load tests, and formal assistive-technology
  testing remain unverified.

Stop here before Milestone 8. Commit and push only after the final current-diff suite and CRITICAL
Governor review pass without a blocking resource-server finding. Live Alexa+/host issuance remains
an external integration limitation, not a reason to fabricate verification or broaden this
milestone into demo polish, submission packaging, providers, or new product features.

## Historical Milestone 6 checkpoint

## Implemented in Milestone 6

- Replaced the minimal proof resource with a responsive consumer card that clearly separates the
  requested task, current outcome, lifecycle progress, rationale, evidence summary, provenance,
  technical identifiers, and state history.
- Preserved the exact deterministic mappings: `PASS -> Verified`, `FAIL -> Not completed`, and
  `INCONCLUSIVE -> Awaiting proof`. The presentation derives these states only from a consistent
  lifecycle/verdict/consumer-state/execution/verification tuple; contradictory or malformed input
  renders the neutral `Proof unavailable` state.
- Added explicit confirmation-required copy stating that no action has run, plus neutral executing
  and independent-checking presentation states. The progress label is `Independent check`, so FAIL
  and INCONCLUSIVE never visually overclaim independent verification.
- Added expandable, separately labeled execution claim, independent read-back, and deterministic
  verifier sections. Detailed provenance is populated by `get_resolution_evidence`; the immediate
  confirmation result remains a status response and does not pretend to include detailed evidence.
- Kept the app read-only. It consumes `result.structuredContent`, renders values with `textContent`,
  exposes no controls that call tools, and uses no storage, query-string, or verdict-override path.
- Added a single focused live region, native keyboard-operable `details` disclosures, textual and
  symbolic outcome cues, visible focus styling, forced-colors support, dark-mode support, safe
  timestamp fallbacks, overflow handling, and a compact layout below 560 px.
- Kept the stable `ui://closeloop/proof-card.html` MCP Apps resource, tool metadata linkage,
  `text/html;profile=mcp-app` type, pinned `@modelcontextprotocol/ext-apps@1.7.5` import, and
  jsDelivr-only resource CSP.
- Added a validation-only host builder. It obtains confirmation and all three terminal results
  through the real in-process MCP server, then sends those results into the unchanged production
  HTML through `AppBridge`. Script-context JSON escaping prevents card or result text from ending
  the host script. Synthetic contradictory and malformed fixtures are used only to test the
  presentation trust boundary; they are never presented as real lifecycle outcomes.
- Updated package, HTTP app, MCP server, and proof-card versions to `0.6.0`.

## Milestone 6 verification evidence

Authoritative starting state was clean `main` at
`5c77b99ac88ca4b82e87d28a4fe74e5f3bdf0324`, aligned with `origin/main`. The pre-change full suite
reproduced the Milestone 5 baseline at `57 passed`.

Final code and regression commands:

```bash
uv lock --check
PYTHONPATH=src uv run --no-editable python -m compileall -q src scripts main.py
PYTHONPATH=src uv run --no-editable pytest -q tests/test_proof_card.py
PYTHONPATH=src uv run --no-editable pytest -q \
  tests/test_alexa_integration.py tests/test_mcp_server.py
PYTHONPATH=src uv run --no-editable pytest -q \
  tests/test_aws_infrastructure.py tests/test_dynamodb_repository.py \
  tests/test_resolution_lifecycle.py tests/test_durable_repository.py \
  tests/test_cancellation_verifier.py
PYTHONPATH=src uv run --no-editable pytest -q
```

Results:

- dependency lock check: passed (`62` packages resolved);
- source, validation script, and Vercel entrypoint compilation: passed;
- focused proof-card/UI suite: `15 passed`;
- focused Alexa+/MCP regression suite: `12 passed`, with the pre-existing non-failing
  Starlette/anyio deprecation warning;
- focused AWS/lifecycle/verifier regression suite: `45 passed`;
- complete suite: `72 passed`, with the same pre-existing warning.

Browser fixture generation and local host commands:

```bash
validation_dir=$(mktemp -d /tmp/closeloop-proof-card-final.XXXXXX)
PYTHONPATH=src uv run --no-editable python \
  scripts/build_proof_card_validation.py "$validation_dir"
cd "$validation_dir"
python3 -m http.server 8767 --bind 127.0.0.1
```

The Codex in-app browser opened `confirmation.html`, `healthy.html`, `false_success.html`,
`evidence_outage.html`, `contradictory.html`, `missing_status_booleans.html`, and
`wrong_status_booleans.html`. Browser accessibility inspection verified respectively
`Confirmation required`, `Verified`, `Not completed`, `Awaiting proof`, and neutral
`Proof unavailable` outputs. The three terminal pages came from real MCP
`start_resolution -> confirm_resolution_action -> get_resolution_evidence` lifecycles and the
real deterministic verifier. The two malformed-status and one contradictory fixtures correctly
failed closed.

The healthy page was also verified at the default desktop viewport and at `390x844`. The narrow
layout stacked lifecycle progress vertically without horizontal loss. Keyboard `Tab` focused
`View evidence and provenance`, and `Return` expanded it; the accessibility tree exposed the
execution claim, independent read-back, deterministic verifier, labels, values, and timestamps.
No new console error occurred on the repaired validation pages. This establishes **LOCAL
UI/BROWSER VERIFIED** rendering and MCP Apps bridge integration. It is not a formal WCAG audit and
does not establish Alexa+ rendering compatibility because the Alexa+ Local Inspector/client remains
unavailable.

The Development Governor classified this consumer trust presentation as HIGH risk. Its
pre-continuation review required canonical tuple validation, neutral confirmation/progress wording,
script-safe host embedding, status/evidence shape discrimination, executed fail-closed fixtures,
keyboard/accessibility inspection, and all three real lifecycle outcomes. The final implementation
incorporates those requirements without changing backend trust boundaries.

## Milestone 6 changed repository files

- `HANDOFF.md`
- `docs/friction-log.md`
- `pyproject.toml`
- `scripts/build_proof_card_validation.py`
- `src/closeloop/http_app.py`
- `src/closeloop/mcp_app.py`
- `src/closeloop/mcp_server.py`
- `tests/test_proof_card.py`
- `uv.lock`

## Milestone 6 limitations and next milestone

- Live Alexa+ add-on onboarding, Local Inspector, simulator/device rendering, public HTTPS hosting,
  and production OAuth account linking remain blocked for the reasons recorded in Milestone 4.
- The proof card has a pinned jsDelivr runtime dependency allowed by its resource CSP. A future
  production hardening pass should evaluate bundling the runtime.
- The executing and verifying views are supported by the closed status contract, but the current
  synchronous demo lifecycle normally advances through them within one confirmed tool call; the
  browser proof therefore concentrates on the externally observable confirmation and terminal
  evidence states.
- Accessibility was checked through browser semantics, keyboard operation, responsive rendering,
  forced-colors CSS, and non-color labels/symbols, not through a formal assistive-technology audit.

Stop here before Milestone 7. The next milestone should follow its own explicit authority and may
cover the deferred adversarial/security pass, final demo optimization, and submission packaging.
Do not combine that work into this completed Milestone 6 checkpoint.

## Implemented in Milestone 5

- Added `DynamoDbResolutionRepository` as an optional backend selected by a nonblank
  `CLOSELOOP_DYNAMODB_TABLE`. An explicit DynamoDB selection takes precedence over SQL URLs; a
  blank explicit value fails closed.
- Used `owner_id` as the partition key and `resolution_id` as the sort key. Runtime code never
  creates infrastructure.
- Preserved owner indistinguishability with composite-key `GetItem` calls and owner-partitioned
  `Query` calls, both using `ConsistentRead=True`.
- Made each transition one atomic conditional `PutItem` requiring the complete key, expected
  numeric version, and an allowed stored predecessor state. A post-failure consistent read only
  classifies the failure; it never authorizes a retry or overwrite.
- Kept terminal states out of every allowed predecessor set, so persisted terminal outcomes remain
  immutable. Record/version mismatches also fail before a write.
- Extracted one shared SQL/DynamoDB codec and invariant validator. Persisted terminal state,
  verdict, consumer state, execution claim, and independent evidence must all agree; malformed or
  contradictory records fail as unavailable storage.
- Added a conservative 350 KiB record bound below DynamoDB's 400 KB item limit.
- Paginated complete owner partitions, removed terminal records, sorted open records by
  `created_at`, and only then applied the existing result limit. This preserves SQL behavior while
  documenting owner-history read cost.
- Translated AWS credential, region, endpoint, authorization, throttling, missing-table,
  validation, and internal SDK failures into the safe storage-unavailable contract.
- Added `infra/aws/closeloop-dynamodb.json`: one `PAY_PER_REQUEST`, server-side-encrypted,
  single-region DynamoDB table with no stream, index, provisioned capacity, or running compute.
- Added deployment, least-privilege IAM, cost, cleanup, and recovery guidance in
  `docs/aws-dynamodb.md`.
- Kept exactly five MCP tools. There is still no verdict-write capability, and no AWS or cloud
  response can calculate or override `PASS`, `FAIL`, or `INCONCLUSIVE`.
- Updated application/package/proof-card versions to `0.5.0`.

## Why the AWS integration is meaningful

DynamoDB is not a mirrored log or hackathon-only call. When configured, it is the repository used
for every lifecycle read and write and supplies the shared serverless durability/concurrency
boundary CloseLoop previously lacked outside PostgreSQL. Conditional writes directly enforce
confirmation ordering, optimistic concurrency, and terminal immutability across runtime instances.

Current hackathon rules list AWS services as examples rather than mandating a specific stack.
Bedrock/AgentCore/Strands and event/compute orchestration were intentionally excluded because the
current lifecycle is synchronous and already has an MCP host, authentication boundary, and
deterministic verifier. Adding another agent or control plane would not create a current consumer
capability and could weaken the trust story.

## Milestone 5 environment, provisioning, and cleanup

Detected environment:

- AWS CLI: **not installed**.
- CloudFormation linter: **not installed**; no credentialed AWS-native validator was available.
- AWS profiles/credentials and `AWS_*` variables: **absent**.
- Docker: **not installed**.
- Java command exists, but no usable JRE is installed; DynamoDB Local 2.6+ requires Java 17+.
- boto3: `1.43.89`; Moto: `5.2.3`.
- Live AWS resources created: **none**.
- Resource identifiers: **none**.

The unexecuted production deployment procedure is:

```bash
aws cloudformation deploy \
  --stack-name closeloop-m5 \
  --template-file infra/aws/closeloop-dynamodb.json \
  --parameter-overrides TableName=closeloop-resolutions \
  --region us-east-1
export CLOSELOOP_DYNAMODB_TABLE=closeloop-resolutions
export AWS_REGION=us-east-1
```

The runtime identity needs only table-scoped `dynamodb:GetItem`, `dynamodb:PutItem`, and
`dynamodb:Query`. Credentials must come from the standard AWS SDK chain and must never be committed.

Cleanup for a future deployed stack:

```bash
aws cloudformation delete-stack --stack-name closeloop-m5 --region us-east-1
aws cloudformation wait stack-delete-complete --stack-name closeloop-m5 --region us-east-1
```

The checked-in stack deletes its table during stack deletion. It uses on-demand capacity and has
no running compute, but DynamoDB request and storage charges vary by Region and usage; it is not
represented as unconditionally free. AWS managed KMS charges may also apply to the explicitly
enabled server-side encryption. This run incurred no AWS cost because it created no AWS
resources.

## Milestone 5 verification evidence

Authoritative starting state:

```bash
git status --short
git rev-parse HEAD
git rev-parse origin/main
uv lock --check
uv sync --locked --extra test --no-editable
PYTHONPATH=src uv run --no-editable pytest -q
```

Results before changes: clean `main`; `HEAD` and `origin/main` both
`f475f948370e19e9f93634439c074c6eb034cdf1`; dependency checks passed; `35 passed` with the one
pre-existing Starlette/anyio deprecation warning.

Final commands against the Milestone 5 diff:

```bash
uv lock --check
uv sync --locked --extra test --no-editable
PYTHONPATH=src uv run --no-editable python -m compileall -q src main.py
PYTHONPATH=src uv run --no-editable pytest -q \
  tests/test_dynamodb_repository.py tests/test_aws_infrastructure.py
PYTHONPATH=src uv run --no-editable pytest -q \
  tests/test_alexa_integration.py tests/test_mcp_server.py tests/test_resolution_lifecycle.py
PYTHONPATH=src uv run --no-editable pytest -q
python3 -m json.tool infra/aws/closeloop-dynamodb.json >/dev/null
git diff --check
```

Results:

- locked dependency resolution/sync: passed (`62` packages resolved; `57` checked);
- source/Vercel entrypoint compilation: passed;
- focused AWS repository/infrastructure suite: `22 passed`;
- focused Alexa+/MCP/lifecycle regression suite: `22 passed`;
- complete suite: `57 passed`;
- CloudFormation JSON syntax and diff whitespace checks: passed;
- AWS-native validation: unavailable because neither the AWS CLI nor `cfn-lint` is installed and
  no AWS credentials are configured; this is not claimed as passed;
- existing Starlette/anyio deprecation warning: unchanged and non-failing.

AWS verification level: **SIMULATED**. Moto proves the boto3 repository's request and lifecycle
contract locally, including restart/re-instantiation, all three outcomes, owner isolation,
confirmation, provenance, terminal immutability, stale writers, pagination/order, consistent-read
flags, conditional expressions, corrupt records, deterministic re-evaluation of stored terminal
evidence, size limits, environment selection, and AWS error translation. It does not prove IAM,
CloudFormation deployment, service availability, latency, regional behavior, or live DynamoDB
semantics in an AWS account.

The Development Governor classified the change as HIGH/CRITICAL because it crosses persistence,
authorization, and serverless failure boundaries. Its pre-implementation architecture review
approved the single-service design with conditional-write/consistent-read constraints. Its final
review blocked completion after reproducing a corrupt stored `PASS` whose changed evidence was not
re-evaluated. The shared terminal validator now calls the deterministic verifier and requires the
entire stored result to match; four DynamoDB corruption cases plus a direct shared-codec regression
test prove the correction. The reviewer found no other blocking issue.

## Milestone 5 operational limitations

- No live DynamoDB table or CloudFormation API was exercised, so AWS-native validation remains a
  live-environment blocker rather than a completed claim.
- Open-list queries paginate an owner's full history to preserve created-time ordering and strong
  consistency. This is correct for the bounded demo but should be revisited for large histories.
- The template intentionally omits point-in-time recovery for minimal demo cost. Production should
  evaluate backup retention, alarms, and recovery objectives.
- A conditional save before execution prevents stale instances from both starting an action, but
  CloseLoop does not claim exactly-once completion. A crash after provider execution can leave a
  truthful `EXECUTING` or `VERIFYING` record requiring later reconciliation.
- Live Alexa+ onboarding blockers from Milestone 4 remain unchanged: partner tooling access,
  supported Node, console authentication, public HTTPS hosting, and external OAuth 2.1 account
  linking.

## Milestone 5 changed repository files

- `HACKATHON_REQUIREMENTS.md`
- `HANDOFF.md`
- `README.md`
- `apps/mcp-server/README.md`
- `docs/architecture.md`
- `docs/aws-dynamodb.md`
- `docs/build-provenance.md`
- `docs/friction-log.md`
- `docs/product-feedback.md`
- `docs/trust-model.md`
- `infra/aws/closeloop-dynamodb.json`
- `pyproject.toml`
- `src/closeloop/__init__.py`
- `src/closeloop/dynamodb_repository.py`
- `src/closeloop/http_app.py`
- `src/closeloop/mcp_app.py`
- `src/closeloop/mcp_server.py`
- `src/closeloop/repository.py`
- `src/closeloop/repository_contract.py`
- `tests/test_aws_infrastructure.py`
- `tests/test_dynamodb_repository.py`
- `uv.lock`

## Next recommended milestone

Stop here before Milestone 6. After explicit approval and AWS credentials, deploy the checked-in
stack in one Region, attach the documented least-privilege runtime policy, run the same lifecycle
against the live table, validate CloudFormation, record cost/latency evidence, then delete the
stack unless it is needed for a public demo deployment. Milestone 6 should also address the
previously planned scope on its own authority; do not combine final UI, adversarial testing, demo
optimization, or submission packaging into this completed milestone.

## Implemented in Milestone 4

- Kept exactly the existing five MCP tools and added no verdict-write capability.
- Added strict Pydantic output contracts. Tool discovery now declares closed input and output
  schemas, bounded input values, and intent-oriented descriptions for Alexa's planner.
- Added self-contained turn-oriented fields for task, execution status, verification status,
  evidence summary, consumer state, and safe next step. The MCP SDK emits both structured content
  and a meaningful generated text fallback; CloseLoop does not script Alexa's spoken response.
- Translated expected domain rejections into actionable, safe MCP tool errors. Missing and
  unauthorized resolution IDs remain indistinguishable; unexpected implementation/contract errors
  still fail as unexpected server errors rather than being disguised as user mistakes.
- Preserved `PASS -> Verified`, `FAIL -> Not completed`, and
  `INCONCLUSIVE -> Awaiting proof`. Provider success remains evidence only.
- Verified MCP `2025-11-25` and the Alexa lifecycle example's `2025-03-26` initialize negotiation
  over authenticated stateless Streamable HTTP `/mcp`.
- Added the root `/.well-known/oauth-protected-resource` alias documented by Alexa+ while
  preserving the MCP SDK's `/.well-known/oauth-protected-resource/mcp` endpoint.
- Adapted only unauthenticated `/mcp` 401 responses to omit `WWW-Authenticate`, as required by the
  Alexa+ QuickStart. Insufficient-scope 403 challenges and successful authenticated calls remain
  unchanged.
- Added a minimal read-only MCP Apps resource at `ui://closeloop/proof-card.html`, linked from the
  four lifecycle/detail tools. It renders task, execution, verification, evidence, and the three
  required consumer states. The open-resolution list remains a data-only tool.
- Updated package, FastAPI, MCP server, and proof-card versions to `0.4.0`.

## Alexa+ tooling, authentication, and onboarding evidence

Preflight and access checks:

```bash
command -v alexa-ai
command -v addon-local-inspector
node --version
npm --version
aws --version
npm config get @alexa-ai:registry
npm view @alexa-ai/cli version
npm view @alexa-ai/addon-local-inspector version
```

Results:

- Alexa AI CLI: **not installed; version unavailable**.
- Alexa+ Local Inspector: **not installed**.
- Host Node.js: `v22.14.0`; npm: `10.9.2`. Official Alexa+ tooling requires Node.js 24+.
- AWS CLI/profile, Alexa credentials, and Alexa private npm registry configuration: **absent**.
- Both private Alexa packages return npm `E404` from the public registry.
- The official Add-on Agent Skill was not locally installed and its private CodeCommit source was
  inaccessible without partner credentials.
- The Alexa developer console redirected to Amazon Sign-In; no credentials were entered and CLI
  authentication was not possible.
- Add-on status: **not created / not onboarded / not deployed**.
- Manifest/config files created: **none**. Fabricating an undeployable add-on manifest would not
  prove onboarding.
- Account linking status: **not configured**. Milestone 3 HS256 JWT verification is only a
  resource-server boundary and is not OAuth 2.1 Authorization Code + PKCE or protected discovery.
- Endpoint status: the repository homepage deployment returns `DEPLOYMENT_NOT_FOUND`; the known
  successful Vercel deployment redirects to Vercel SSO and is not Alexa-reachable.

The official Amazon Devices Builder Tools MCP was natively available in this Codex session, but it
was not used for Milestone 4 implementation or compliance claims. Its installed documentation is
Vega/Fire OS-specific; no device OS platform was selected.

## Official MCP Inspector evidence

Standard MCP Inspector `2.5.0` was the strongest accessible official validation path. It launched
on Node `22.14.0` with an engine warning because it declares Node `>=22.19.0`, but the exercised CLI
operations completed successfully against a local authenticated server. Representative exact
commands were:

```bash
npx -y @modelcontextprotocol/inspector@2.5.0 --cli --help
npx -y @modelcontextprotocol/inspector@2.5.0 --cli http://127.0.0.1:8000/mcp \
  --header "Authorization: Bearer <ephemeral local test JWT>" \
  --format json --method tools/list --strict
npx -y @modelcontextprotocol/inspector@2.5.0 --cli http://127.0.0.1:8000/mcp \
  --header "Authorization: Bearer <ephemeral local test JWT>" \
  --format json --method resources/list
npx -y @modelcontextprotocol/inspector@2.5.0 --cli http://127.0.0.1:8000/mcp \
  --header "Authorization: Bearer <ephemeral local test JWT>" \
  --format json --method resources/read --uri ui://closeloop/proof-card.html
npx -y @modelcontextprotocol/inspector@2.5.0 --cli http://127.0.0.1:8000/mcp \
  --header "Authorization: Bearer <ephemeral local test JWT>" \
  --format json --method tools/call --tool-name start_resolution \
  --tool-args-json '{"intent":"Cancel my subscription and make sure I will not be charged again.","provider_mode":"healthy"}'
npx -y @modelcontextprotocol/inspector@2.5.0 --cli http://127.0.0.1:8000/mcp \
  --header "Authorization: Bearer <ephemeral local test JWT>" \
  --format json --method tools/call --tool-name confirm_resolution_action \
  --tool-args-json '{"resolution_id":"<returned resolution_id>","confirmed":true}'
npx -y @modelcontextprotocol/inspector@2.5.0 --cli http://127.0.0.1:8000/mcp \
  --header "Authorization: Bearer <ephemeral local test JWT>" \
  --format json --method tools/call --tool-name get_resolution_evidence \
  --tool-args-json '{"resolution_id":"<returned resolution_id>"}'
npx -y @modelcontextprotocol/inspector@2.5.0 --cli http://127.0.0.1:8000/mcp \
  --header "Authorization: Bearer <ephemeral local test JWT>" \
  --format json --method tools/call --tool-name get_resolution_status \
  --tool-args-json '{"resolution_id":"missing"}'
```

Inspector evidence:

- strict `tools/list` exited 0 and discovered exactly the five expected tools;
- `resources/list` and `resources/read` exited 0 and returned the proof card as
  `text/html;profile=mcp-app`;
- `tools/call start_resolution`, `confirm_resolution_action`, and
  `get_resolution_evidence` exited 0 through authenticated Streamable HTTP;
- the completed Inspector lifecycle returned `PASS / Verified` and separate execution-claim,
  independent-read-back, and deterministic-verifier evidence;
- the invalid status call returned the safe actionable "Resolution is unavailable" tool result;
  Inspector exited 5 because the MCP result deliberately set `isError: true`;
- Inspector tool-call metadata plus `resources/list`/`resources/read` resolved the tool/resource
  link, CSP, border preference, and MIME type. No app host rendered or executed the card.

The proof card imports `@modelcontextprotocol/ext-apps@1.7.5` from a pinned jsDelivr URL and declares
that origin in its CSP. The resource contract and the card's `structuredContent` handler source are
integration/static verified, but the handler was not executed and the card was not visually
rendered by Alexa+ or the unavailable Alexa+ Local Inspector. A later production pass should bundle
the client to remove the runtime CDN dependency.

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

Post-initialization verification commands:

```bash
npx -y @amazon-devices/amazon-devices-buildertools-mcp@latest check-status
npx -y @amazon-devices/amazon-devices-buildertools-mcp@latest exec --list
```

`check-status` detected Codex, context document v4.0 at the repository `AGENTS.md`, and a configured
MCP entry in `/Users/colbyweiss/.codex/config.toml`; Codex was the one fully configured agent. The
read-only tool inventory launched successfully and returned nine tools. The MCP server is therefore
configured and launchable. Because this Codex task began before the global configuration changed,
native MCP tools require a newly started Codex session; the CLI inventory was used for the current
process. The official inventory also requires `list_documents(documentType="WORKFLOW")` before
future Amazon implementation/setup/test/build/deploy/submit workflows, which is now recorded in
`HACKATHON_REQUIREMENTS.md`.

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

## Milestone 3 final verification evidence

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

## Milestone 3 changed repository files

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

## Milestone 4 changed repository files

- `HACKATHON_REQUIREMENTS.md`
- `HANDOFF.md`
- `README.md`
- `apps/mcp-server/README.md`
- `docs/architecture.md`
- `docs/friction-log.md`
- `docs/trust-model.md`
- `pyproject.toml`
- `src/closeloop/alexa_contracts.py`
- `src/closeloop/http_app.py`
- `src/closeloop/lifecycle.py`
- `src/closeloop/mcp_app.py`
- `src/closeloop/mcp_server.py`
- `tests/test_alexa_integration.py`
- `tests/test_mcp_server.py`
- `uv.lock`

## Milestone 4 final verification evidence

Commands against the final Milestone 4 diff:

```bash
uv lock --check
uv sync --locked --extra test --no-editable
PYTHONPATH=src uv run --no-editable python -m compileall -q src main.py
PYTHONPATH=src uv run --no-editable pytest -q tests/test_alexa_integration.py tests/test_mcp_server.py tests/test_resolution_lifecycle.py
PYTHONPATH=src uv run --no-editable pytest -q
git diff --check
```

Results:

- dependency lock check and locked environment sync passed;
- source and Vercel entrypoint compilation passed;
- focused Alexa+/MCP/lifecycle suite: `22 passed`;
- full suite, preserving the prior 29-test baseline: `35 passed`;
- diff whitespace check passed;
- the one non-failing upstream Starlette/anyio deprecation warning remains.

Verification level: **INTEGRATION VERIFIED locally**. This covers MCP protocol negotiation,
authenticated Streamable HTTP lifecycle, exact tool discovery and strict schemas, MCP Apps resource
discovery/read, and all three deterministic verdict/consumer-state mappings. It does not cover an
Alexa+ client, Alexa+ Local Inspector, web simulator, physical device, public deployment, external
OAuth authorization server, or live PostgreSQL.

## Milestone 4 known limitations / blockers (historical)

There are no blockers to the local Milestone 4 integration boundary. Live Alexa+ onboarding and
verification remain blocked by:

- selected-partner access to the private Alexa AI CLI, Local Inspector, and Add-on Agent Skill;
- Node.js 24+ for Alexa's official tools (and Node `>=22.19.0` for a supported Inspector 2.5.0
  runtime; the current host is `22.14.0`);
- authenticated Alexa developer-console access;
- a public Alexa-reachable HTTPS deployment;
- an OAuth 2.1 authorization server supporting the Alexa+ account-linking and protected-discovery
  requirements.

Additional limitations are explicit:

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
- The proof card has a pinned runtime CDN dependency and was not visually rendered by an Alexa+
  host. Only its MCP Apps metadata, resource, structured input path, and text fallback are verified.
- The cancellation provider remains the labeled first-party demo simulation; no live provider,
  Alexa+ client, or AWS path was tested.
- The Amazon Devices MCP is natively available, but its context supplies Vega/Fire OS guidance,
  not Alexa+ compliance evidence. No device OS platform was selected.
- On this macOS host, Python skips hidden editable-install `.pth` files, so the documented `uv`
  commands use `--no-editable` for deterministic local imports.

## Milestone 4 next recommended step (superseded by Milestone 5)

Stop here before Milestone 5. After explicit approval, first obtain Alexa+ selected-partner access,
upgrade Node.js, configure/authenticate the Alexa AI CLI, provide a public HTTPS deployment and
compatible external OAuth authorization server, then create/deploy the real add-on and validate it
with the Alexa+ Local Inspector and web simulator. Production schema migrations and idempotent
recovery for persisted `EXECUTING`/`VERIFYING` states remain important operational hardening. Do not
begin AWS Builder integration or final visual polish until that next milestone is approved.
