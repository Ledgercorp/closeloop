# CloseLoop

**CloseLoop lets you hand Alexa+ a consequential task and keeps responsibility for it until the real-world outcome can actually be verified.**

> Alexa+ can take the action. CloseLoop makes sure the outcome actually happened.

A provider receipt is a claim, not proof. CloseLoop preserves the request, confirmation, action claim, independent evidence, verification history, and follow-up schedule until the resolution has a justified outcome.

Subscription cancellation is the implemented workflow. Refunds, returns, warranty claims, service requests, and appointments are represented as future resolution types, not implemented integrations.

Deterministic code owns the evidence outcomes:

- `PASS` → **Verified**
- `FAIL` → **Not completed**
- `INCONCLUSIVE` → **Awaiting proof**

If StreamBox accepts cancellation while auto-renew is still on, the resolution remains open: “StreamBox accepted the cancellation request, but auto-renew is still on. I’m not marking this resolved yet.” A later session retrieves the same resolution and can recheck it.

Primary track: **Alexa+** · Mini challenge: **AWS Builder** · License: [Apache-2.0](LICENSE)

The checked-in demo runs at `http://127.0.0.1:8000/demo/`. The existing hosted URL is not updated or re-verified by this repository change. No live Alexa+, provider, or AWS verification is claimed.

## Run the server-backed demo locally

Prerequisites: Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --locked --extra test --no-editable
PYTHONPATH=src uv run --no-editable uvicorn main:app \
  --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/demo/`. The page starts at **Waiting for your confirmation**; no cancellation request is sent until you select **Confirm and play the resolution**. That runs `persistent_resolution`: accepted request, contradictory read-back, later-session retrieval, scheduled recheck, and final proof. The timeline shows the simulated next-check time. **See when proof is unavailable** exercises the outage path. `/demo/run` also offers `healthy`, `false_success`, `evidence_outage`, and `terminal_failure` scenarios.

The server uses temporary local SQLite and a deterministic simulated provider. Browser input can select a scenario only; it cannot supply an outcome, evidence, provider, owner, or confirmation attestation. Time advancement is a demo simulation, not a scheduler. This is not live Alexa+, a production provider, or AWS. See the [demo script](docs/demo-script.md) for the recording walkthrough.

## How it works

```text
Alexa+ / MCP client
        │ owner-authenticated resolution queries
        ▼
Persistent resolution record ─── request, confirmation, history, next check
        │
        ├── action plane ───────── provider receipt (claim only)
        ├── independent read-back ─ account evidence
        └── deterministic verifier ─ PASS / FAIL / INCONCLUSIVE

AWAITING_PROOF remains open → bounded follow-up read-back → terminal outcome
```

The seven MCP tools are `start_resolution`, `confirm_resolution_action`, `get_resolution_status`, `get_resolution_evidence`, `list_open_resolutions`, `list_recent_resolutions`, and `recheck_resolution`. The open list contains unresolved tasks only; the separate recent list contains terminal outcomes. Recheck repeats only independent observation, never the action. There is no `set_verdict`, `mark_success`, `force_pass`, or equivalent tool.

`AWAITING_PROOF` is nonterminal and has a four-check total limit including the initial read-back. Verified and not-completed records are immutable. Confirmation remains signed, short-lived, single-use, owner-bound, resolution-bound, action-digest-bound, and replay-resistant.

## Alexa+ integration

CloseLoop exposes an authenticated self-hosted MCP server over Streamable HTTP, with closed schemas, protected-resource metadata, safe errors, and a read-only MCP Apps proof card. Local MCP integration tests exercise tool discovery, authentication, owner scoping, resolution persistence, and bounded rechecks.

Alexa+ account linking, live device rendering, and live Amazon session testing have not been verified. Do not present this repository or its demo as a live Alexa+ deployment.

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

The reconciled suite has **235 passed, 0 failed, 1 skipped** (236 collected); its browser interaction regression was skipped because Playwright is unavailable here. Security is
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

The canonical Vercel URL had signed-out checks on a previous release; those results predate persistent resolutions and do not verify the current build. No production behavior check has been run against the persistent-resolution release. Locally, /demo/ is the persistent resolution simulation and /demo/run accepts only a bounded scenario selector. The production MCP endpoint remains bearer-authenticated. The demo uses isolated temporary state and a simulated provider; no live Alexa+, provider, AWS, production storage, OAuth, confirmation authority, or scheduler is claimed.

## Provenance and license

CloseLoop was built during the 2026 hackathon window. It draws on prior conceptual experience with
evidence-based PASS/FAIL/INCONCLUSIVE verification, but no source from the earlier CUF project was
copied. Details are in [build provenance](docs/build-provenance.md).

Licensed under [Apache License 2.0](LICENSE).
