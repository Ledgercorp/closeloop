# CloseLoop Handoff

## Current phase

Milestone 5 is complete at **SIMULATED AWS verification**. CloseLoop now has an optional Amazon
DynamoDB repository that becomes the authoritative store for owner-scoped resolution state,
confirmation, evidence provenance, lifecycle history, optimistic version, and immutable terminal
outcome. The implementation uses boto3 against a single-region, on-demand table defined by
CloudFormation. All prior MCP, Alexa+ compatibility, and deterministic verdict semantics remain
intact.

No live AWS resource was provisioned. This host has no AWS CLI, profile, or AWS credential
environment, and it lacks the Java 17 or Docker runtime required for official DynamoDB Local.
Integration was therefore exercised with Moto and is accurately labeled **SIMULATED**, not live or
AWS-native integration verified. No Bedrock, AgentCore, Strands, Lambda, Step Functions,
EventBridge, model, or cloud-agent path was added. Final UI polish, adversarial testing, demo
optimization, submission packaging, and Milestone 6 work were not started.

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
