# CloseLoop

**Alexa+ can take action. CloseLoop verifies the outcome before it calls the job done.**

CloseLoop is a hackathon project for the Amazon Build, Ship, Shape 2026 Alexa+ track. It is a consumer-facing verified-resolution agent: the action plane can attempt consequential life-admin tasks, but it is structurally unable to declare success. A separate deterministic verification plane decides whether the requested real-world outcome is proven.

## Core semantics

- `PASS` → **Verified**
- `FAIL` → **Not completed**
- `INCONCLUSIVE` → **Awaiting proof**

The flagship demo is subscription cancellation. A simulated provider can report success while leaving auto-renew enabled; CloseLoop must detect that contradiction and refuse to call the task done.

## Hackathon targets

- Primary: **Alexa+**
- Mini-challenge: **AWS Builder**
- Demo: under 3 minutes, voice-first, with PASS / FAIL / INCONCLUSIVE fault injection

## Repository status

This repository contains the deterministic resolution core, fault-injection demo provider,
and a narrow MCP action lifecycle for subscription cancellation. The MCP service requires
explicit confirmation before execution, records the provider claim separately from an
independent read-back, and exposes only read access to the verifier's terminal result.

The provider remains a clearly labeled in-process demo simulation. Alexa+ client integration,
durable shared storage, and AWS orchestration are intentionally deferred beyond Milestone 2.

## Install and test

```bash
uv sync --extra test --no-editable
uv run --no-editable pytest -q
```

## Run the service

```bash
uv run --no-editable uvicorn main:app --host 127.0.0.1 --port 8000
```

The health endpoints remain at `/` and `/health`. The MCP service uses Streamable HTTP at
`/mcp` and supports the required `2025-11-25` protocol negotiation through the official MCP
Python SDK. For a non-local host, set `CLOSELOOP_ALLOWED_HOSTS`; set
`CLOSELOOP_ALLOWED_ORIGINS` when browser origins must be permitted. Both variables accept
comma-separated exact values. Vercel's `VERCEL_URL` is trusted automatically.

## Design rule

> Tool success is evidence. It is never the verdict.

The action plane does not expose any `set_verdict` capability. Only the independent verifier may produce the final outcome.
