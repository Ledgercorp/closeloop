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

This repository currently contains the deterministic resolution core, fault-injection demo provider, tests, build provenance, judging map, friction log, and architecture plan. Alexa+ MCP and AWS AgentCore integrations are intentionally the next milestone.

## Run the current core

```bash
python -m pytest -q
```

## Design rule

> Tool success is evidence. It is never the verdict.

The action plane does not expose any `set_verdict` capability. Only the independent verifier may produce the final outcome.
