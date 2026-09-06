# CloseLoop

**CloseLoop doesn’t trust an agent saying it finished. It independently checks the result before Alexa+ tells you the task is done.**

> Alexa+ can take action. CloseLoop makes sure “done” actually means done.

CloseLoop is a consumer-facing verified-resolution agent for consequential life-admin tasks. The
demo cancels a subscription, reads the resulting account state through a separate evidence path,
and lets deterministic code—not the agent or provider—produce one of three outcomes:

- `PASS` → **Verified**
- `FAIL` → **Not completed**
- `INCONCLUSIVE` → **Awaiting proof**

The memorable case is false success: the provider says cancellation worked, independent read-back
shows auto-renew is still on, and CloseLoop refuses to call the task done.

Primary track: **Alexa+** · Mini challenge: **AWS Builder** · License: [Apache-2.0](LICENSE)

**[Open the public judge demo](https://closeloop-zeta.vercel.app/demo/)** — a signed-out,
read-only deterministic demonstration of confirmation plus Verified, Not completed, and Awaiting
proof. It uses pre-generated results from the real CloseLoop lifecycle/verifier path and is
explicitly not a live Alexa+, provider, or AWS deployment.

## Run the deterministic demo

Prerequisites: Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --locked --extra test --no-editable
demo_dir=$(mktemp -d /tmp/closeloop-demo.XXXXXX)
PYTHONPATH=src uv run --no-editable python \
  scripts/build_proof_card_validation.py "$demo_dir"
cd "$demo_dir"
python3 -m http.server 8768 --bind 127.0.0.1
```

Open `http://127.0.0.1:8768/`. The recording index links to confirmation and all three outcomes.
Every terminal page is produced through the real in-process MCP server, lifecycle, repository,
provider adapter, independent read-back, deterministic verifier, and production proof-card code.
The provider and confirmation signer are explicitly local simulations; this is not a live Alexa+
client, real subscription provider, or live AWS environment.

The [sub-three-minute video script](docs/demo-script.md) gives the exact recording order and
narration.

## How it works

```text
MCP client (Alexa+ target)
       │  bearer-authenticated Streamable HTTP /mcp
       ▼
five closed-schema tools ── trusted, action-bound confirmation
       │
       ▼
execution plane ─────────── provider action receipt (claim only)
       │
       ▼
independent read-back ───── resulting account evidence
       │
       ▼
deterministic verifier ──── PASS / FAIL / INCONCLUSIVE
       │
       ├── SQL or DynamoDB authoritative lifecycle/evidence state
       └── Alexa-ready structured result + read-only MCP Apps proof card
```

The public MCP surface has exactly five tools:

- `start_resolution`
- `confirm_resolution_action`
- `get_resolution_status`
- `get_resolution_evidence`
- `list_open_resolutions`

There is no `set_verdict`, `mark_success`, `force_pass`, or equivalent capability. The executor’s
receipt is evidence, never the verdict. Consequential execution requires a signed, short-lived
`closeloop.confirmation/v1` attestation bound to the authenticated owner, exact resolution, and
canonical action digest. Replay, stale, tampered, cross-owner, and cross-resolution attestations
fail closed.

## Alexa+ integration

CloseLoop is a self-hosted MCP server using the official MCP Python SDK. `/mcp` uses stateless
Streamable HTTP and negotiates MCP `2025-11-25` plus the documented `2025-03-26` lifecycle example.
It provides closed conversation-ready schemas, bearer authentication, RFC 9728 protected-resource
metadata, safe errors, and a `ui://closeloop/proof-card.html` MCP Apps resource with meaningful
text fallback.

Verification level: **INTEGRATION VERIFIED locally**. Standard MCP Inspector and integration tests
proved initialization, five-tool discovery, schemas, authenticated calls, resources, and all three
outcomes. Alexa AI CLI/Local Inspector access, account linking, an Alexa-reachable public endpoint,
and live Alexa+ rendering were unavailable, so CloseLoop does not claim live Alexa+ verification.

## Why DynamoDB matters

When `CLOSELOOP_DYNAMODB_TABLE` is configured, DynamoDB is the authoritative lifecycle and evidence
store—not a decorative log. Owner-scoped keys, strongly consistent reads, and conditional writes
protect ordering, replay resistance, cross-instance concurrency, and immutable terminal outcomes.
The checked-in CloudFormation template creates one encrypted on-demand table with no running
compute.

Verification level: **SIMULATED** with boto3 and Moto. No live AWS table, IAM policy, or
CloudFormation deployment was exercised. See [AWS design and deployment notes](docs/aws-dynamodb.md).

## Run the service and tests

```bash
PYTHONPATH=src uv run --no-editable uvicorn main:app \
  --host 127.0.0.1 --port 8000
PYTHONPATH=src uv run --no-editable pytest -q
```

Health endpoints are `/` and `/health`; MCP is mounted at `/mcp`. Local development uses
`.closeloop/resolutions.db`. Production/serverless operation requires shared PostgreSQL or DynamoDB,
a bearer-token issuer, and a separate trusted confirmation authority. Missing production storage,
authentication, or confirmation configuration fails closed. Never deploy the test or recording
signing keys.

The final deployment package has **187 passing tests** (the Milestone 7 baseline was 183). Security is
**PARTIALLY ADVERSARIAL VERIFIED**:
109 focused adversarial/confirmation cases cover verdict manipulation, authorization isolation,
confirmation replay and tampering, lifecycle races, forged evidence, MCP abuse, UI injection,
information leakage, and failure behavior. Seven blocking findings were fixed. See the
[verification matrix](docs/verification-matrix.md) and [security report](docs/adversarial-security.md).

## Submission evidence

- [Submission-ready copy](docs/submission-copy.md)
- [Three-minute storyboard](docs/demo-script.md)
- [Judging rubric map](docs/judging-rubric-map.md)
- [Verification matrix](docs/verification-matrix.md)
- [Screenshot and submission checklist](docs/submission-checklist.md)
- [Product feedback](docs/product-feedback.md)
- [Friction log](docs/friction-log.md)
- [Build provenance](docs/build-provenance.md)
- [Trust model](docs/trust-model.md)

The repository and deterministic judge demo are publicly reachable. The canonical Vercel URL serves
`/`, `/health`, and `/demo/` without authentication; `/mcp` remains fail-closed behind bearer
authentication. The public demo is read-only and contains no production storage, OAuth,
confirmation-authority secret, test signer, live provider, live Alexa+, or live AWS configuration.

## Provenance and license

CloseLoop was built during the 2026 hackathon window. It draws on prior conceptual experience with
evidence-based PASS/FAIL/INCONCLUSIVE verification, but no source from the earlier CUF project was
copied. Details are in [build provenance](docs/build-provenance.md).

Licensed under [Apache License 2.0](LICENSE).
