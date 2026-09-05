# Amazon Build, Ship, Shape 2026 — CloseLoop Requirements

This file translates the current hackathon requirements into engineering constraints for CloseLoop. Re-verify against the official rules before final submission if the rules change.

## Target track
Primary: Alexa+

Target stackable mini-prize: AWS Builder, where the AWS integration is substantive and documented.

## Submission constraints to preserve
- Public GitHub repository.
- Open-source license visible in the repository.
- Working demonstration.
- Public demo video under 3 minutes.
- Clear documentation of what was built during the hackathon window versus pre-existing concepts/components.
- Product feedback/friction notes for Amazon/AWS/Alexa tooling used.

## Alexa+ / MCP implementation target
The project should use the hackathon-supported Alexa+/MCP path rather than a fake wrapper.

Engineering target:
- self-hosted MCP service
- Streamable HTTP transport
- MCP specification/version compatible with the hackathon's currently stated requirement (2025-11-25 or newer unless official rules are updated)
- tools designed around a user-facing Alexa+ action lifecycle

If official documentation changes, update this file and implementation together. Do not silently ship a transport/version that is no longer eligible.

## Official Amazon Builder Tools context

The official Amazon Devices Builder Tools MCP context was initialized on 2026-09-05 with:

```bash
npx -y @amazon-devices/amazon-devices-buildertools-mcp@latest init-context
```

The initializer reported MCP package version `1.0.10` and context-document version `4.0.0`. It
installed a Codex MCP configuration plus Vega/Fire OS skills. The installed material is scoped to
Amazon Devices applications and does not itself verify Alexa+ hackathon eligibility, Alexa+ API
behavior, or submission compliance.

CloseLoop has not selected Vega or Fire OS, so `.adbt-config.json` intentionally contains only the
private/opt-out project identifier and no platform declaration. Do not infer a platform or import
the generated React Native/Vega templates or dependencies into the Python MCP service.

Before any later Alexa+ implementation or final submission:

- use the official Builder Tools MCP documentation tools with an explicit supported platform
  decision where the tool requires one;
- call `list_documents` with `documentType="WORKFLOW"` before using Builder Tools for an Amazon
  implementation, setup, configuration, test, build, deployment, or submission task, then follow
  any applicable official workflow before consulting knowledge-base documents;
- verify the then-current Alexa+, Amazon Devices API, MCP transport/version, and submission rules;
- record document identifiers, dates, and any resulting requirement changes here or in the
  friction log;
- treat an unavailable or non-applicable Builder Tools result as an evidence gap, not as proof of
  compliance.

## Required MCP surface for Milestone 2
- `start_resolution`
- `confirm_resolution_action`
- `get_resolution_status`
- `get_resolution_evidence`
- `list_open_resolutions`

Forbidden:
- `set_verdict`
- `mark_success`
- `force_pass`
- any equivalent direct verdict-write capability

## AWS Builder strategy
AWS usage must be meaningful, not decorative.

Planned candidates for later milestones include:
- Amazon Bedrock for planning/reasoning where appropriate
- Strands SDK for orchestration where appropriate
- AgentCore Gateway / Policy / related AgentCore services where they materially improve execution, identity, policy, or observability

Important: no model or orchestration layer may replace the deterministic verifier as the final source of truth.

## Judging optimization
Every feature should improve at least one of these dimensions:
- technical implementation
- design / user experience
- potential impact / usefulness
- idea quality / novelty

Do not add features solely because they are technically interesting if they weaken the 3-minute demo.

## Friction log
Record integration friction as it happens, including:
- service/API used
- task attempted
- expected behavior
- actual behavior
- error/confusion
- workaround
- concrete product-improvement suggestion

Keep this in the existing friction-log documentation and make it submission-ready.

## Provenance
CloseLoop may take advantage of prior expertise and reusable patterns, but the repository must truthfully identify what was created or substantially extended during the hackathon period.

CUF must not be represented as newly created for this hackathon.
