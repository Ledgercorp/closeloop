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

## Final rules verification — 2026-09-06

The [official rules](https://amazonappdev2026.devpost.com/rules),
[hackathon overview](https://amazonappdev2026.devpost.com/), and
[resources](https://amazonappdev2026.devpost.com/resources) were checked again for Milestone 8.
Current submission requirements that materially affect CloseLoop are:

- Submission deadline: **October 23, 2026 at 12:00 PM PDT**.
- Alexa+ accepts a working self-hosted MCP server using Streamable HTTP and MCP `2025-11-25` or
  later. The repository must actually import/call the required runtime technology, not merely name
  it in documentation, and the video must show the project functioning.
- The public GitHub repository must include all source, assets, and instructions plus a detectable
  open-source license visible at the top/About area. The abbreviated Apache notice was replaced by
  canonical Apache-2.0 text for final submission.
- The public English demonstration video must be under three minutes, hosted on YouTube or Vimeo,
  and avoid third-party trademarks/copyrighted material without permission. Judges need not watch
  beyond three minutes and may judge solely from the text, images, and video.
- If prior work existed, the submission must explain significant work completed during the
  submission window. CloseLoop’s CUF conceptual provenance remains explicitly disclosed.
- Product feedback must identify each tool/API/SDK used, what worked, what needs work, onboarding
  experience, and whether the entrant would use it again.
- AWS Builder requires the submission to name the AWS service and explain its use. DynamoDB’s
  authoritative lifecycle/evidence responsibility is documented; it is not presented as live AWS.
- Optional friction entries must include the attempted task, expected/actual behavior, severity,
  workaround, and actionable recommendation. Genuine entries may contribute up to a 10% bonus.

The code/runtime hook is locally integration verified through the official MCP SDK and Inspector,
but no Alexa+ client/add-on/Local Inspector connected. The recording must therefore show the real
local MCP lifecycle and preserve its simulation labels. A live Alexa+ claim, public deployment
claim, or video URL remains prohibited until independently verified.

## Alexa+ / MCP implementation target
The project should use the hackathon-supported Alexa+/MCP path rather than a fake wrapper.

Engineering target:
- self-hosted MCP service
- Streamable HTTP transport
- MCP specification/version compatible with the hackathon's currently stated requirement (2025-11-25 or newer unless official rules are updated)
- tools designed around a user-facing Alexa+ action lifecycle

If official documentation changes, update this file and implementation together. Do not silently ship a transport/version that is no longer eligible.

## Alexa+ MCP Toolkit requirements verified for Milestone 4

The following requirements were re-verified against the official Alexa+ Builder documentation on
2026-09-05. These Alexa+-specific sources, rather than the Amazon Devices Vega/Fire OS context,
govern this milestone:

- [MCP QuickStart](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html)
- [MCP Toolkit Overview](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-overview.html)
- [MCP Client and App Lifecycle](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-client-lifecycle.html)
- [Tools, Schema, and Data Design](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-addon-tools-schema-data-design.html)
- [Authentication](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-authentication.html)
- [Account Linking](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-account-linking.html)
- [Test MCP Add-ons](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-test-add-ons.html)
- [Local Inspector](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-local-inspector.html)
- [Alexa AI CLI](https://developer.amazon.com/docs/alexaplus/add-ons/alexa-ai-cli-reference.html)

Verified requirements and differences from the Milestone 3 assumptions:

- Alexa+ for Builders explicitly supports MCP `2025-11-25` over Streamable HTTP. The client
  lifecycle page still shows a `2025-03-26` initialize example, so CloseLoop must negotiate both
  through the MCP SDK rather than hard-code one client version.
- The MCP endpoint must be remotely reachable over HTTPS. A local server may be exposed through a
  tunnel during development; a Vercel deployment protected by Vercel SSO is not Alexa-reachable.
- Alexa+ requires unauthenticated discovery to return HTTP 401 without a `WWW-Authenticate` header.
  The MCP server must publish RFC 9728 protected-resource metadata, and the authorization server
  must publish OAuth authorization-server metadata.
- Protected discovery uses service-level client credentials. User-specific tools and write actions
  require OAuth 2.1 Authorization Code with PKCE S256, the canonical MCP `resource` parameter,
  bearer tokens only in the `Authorization` header, and refresh-token issuance. Dynamic Client
  Registration, Client ID Metadata Documents, OpenID Connect, step-up authorization, and a
  `WWW-Authenticate` challenge are not currently supported by the Alexa+ MCP Toolkit.
- CloseLoop's Milestone 3 HS256 verifier is only a resource-server boundary. It is not an OAuth
  authorization server and does not by itself satisfy Alexa+ account linking or service-level
  discovery. Do not treat locally minted test JWTs as Alexa+ credentials.
- Re-review on 2026-09-06 confirmed that Alexa+ account linking authenticates user-specific/write
  requests with authorization-code + PKCE S256 bearer tokens, but the public pages do not specify a
  per-action human-confirmation attestation. CloseLoop therefore verifies a separate short-lived,
  action-bound attestation from a configured trusted authorization/host boundary. This is a
  CloseLoop security contract, not a claim that Alexa+ currently emits that token.
- Tool names, descriptions, input schemas, and output schemas are promises to Alexa. Each tool must
  map to one meaningful customer intent, every parameter must be used, errors must always return
  useful data, and declared and returned output fields must remain synchronized.
- Alexa+ composes spoken and visual responses from MCP data. CloseLoop must return complete text and
  structured data; it must not script Alexa's words.
- MCP Apps are supported through `_meta.ui.resourceUri` pointing to a `ui://` resource served as
  `text/html;profile=mcp-app`. UI-enabled tools still require a meaningful text/data fallback.
- The documented server-side latency target is under 500 ms round trip.
- Isolated validation uses standard MCP Inspector operations (`initialize`, `tools/list`, valid and
  invalid `tools/call`, repeat/idempotency checks, and trace export). The Alexa+ Local Inspector can
  perform data-layer checks without a UI and visual checks for `ui://` resources. End-to-end web
  simulator or physical-device testing requires an add-on deployed to the development stage.
- The Alexa AI CLI and Local Inspector require Node.js 24+. Alexa+ MCP Toolkit access is currently
  limited to selected partners. The official CLI, inspector, and Add-on Agent Skill are distributed
  through private AWS CodeArtifact/CodeCommit access granted to approved partners.
- An add-on manifest requires US distribution, an HTTPS MCP endpoint, store descriptions and
  example phrases, public privacy-policy and terms URLs, six light icon sizes, and at least one
  600x900 carousel image. Alexa+ refreshes tool/resource registration only when the add-on is
  redeployed.

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

## AWS Builder requirements verified for Milestone 5

The following requirements were re-verified against current official sources on 2026-09-05:

- [Official hackathon rules](https://amazonappdev2026.devpost.com/rules)
- [Official hackathon resources](https://amazonappdev2026.devpost.com/resources)
- [DynamoDB item operations and conditional writes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/WorkingWithItems.html)
- [DynamoDB optimistic version control](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/BestPractices_ImplementingVersionControl.html)
- [DynamoDB on-demand capacity](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/on-demand-capacity-mode.html)
- [DynamoDB core key design](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.CoreComponents.html)
- [DynamoDB Query API](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_Query.html)
- [DynamoDB encryption](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/encryption.usagenotes.html)
- [DynamoDB constraints](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Constraints.html)
- [DynamoDB least-privilege policy guidance](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/using-identity-based-policies.html)
- [CloudFormation DynamoDB table reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-dynamodb-table.html)
- [AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agents-tools-runtime.html)
- [AgentCore Policy concepts](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-core-concepts.html)
- [Strands tool model](https://strandsagents.com/docs/user-guide/concepts/tools/)
- [EventBridge overview](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-what-is.html)

Verified findings:

- The AWS Builder mini-challenge accepts a primary-track entry that incorporates AWS services and
  documents the integrations. The rules list Bedrock, AgentCore, Strands, Kiro Crew, SageMaker,
  and other services as examples, not mandatory components.
- Stage 1 checks for reasonable SDK/API use. Stage 2 weights technical implementation, design,
  potential impact, and idea quality equally. The judging examples contrast a basic storage or
  single-model call with a creative multi-service pipeline, but do not require unnecessary
  services. CloseLoop therefore optimizes for a genuine product responsibility rather than raw
  service count.
- The submission must describe which AWS services were used and how. A factual friction log can
  earn a bonus under the current rules.
- DynamoDB is meaningful here because it becomes the authoritative shared state and evidence
  boundary. Conditional writes atomically enforce optimistic versions and allowed predecessor
  states, while owner partition keys and strongly consistent table reads preserve isolation.
- A composite `owner_id` partition key plus `resolution_id` sort key identifies each record and
  supports owner-scoped queries. Query filtering occurs after reads and query pages can return a
  `LastEvaluatedKey`, so the implementation paginates all owner records, removes terminal records,
  sorts by `created_at`, and then applies the API limit.
- DynamoDB's maximum item size is 400 KB. CloseLoop uses a conservative 350 KiB serialized bound
  and fails safely before a write when a record is too large.
- `PAY_PER_REQUEST` is AWS's recommended mode for most variable/serverless workloads. It avoids
  provisioned idle throughput, but request and storage charges can still apply; the project does
  not call it unconditionally free.
- DynamoDB encrypts data at rest and in transit. The template explicitly enables server-side
  encryption, uses one Region, and adds no global table, stream, secondary index, or running
  compute.
- AgentCore can host MCP/agent workloads and AgentCore Policy can govern Gateway calls. Strands
  offers model-driven tool orchestration, while EventBridge routes asynchronous events. None adds
  a current product capability to CloseLoop's already hosted, synchronous five-tool lifecycle.
  Bedrock, AgentCore, Strands, Lambda, Step Functions, and EventBridge are therefore intentionally
  excluded from Milestone 5 rather than added for optics.

Milestone 5 implements one optional `DynamoDbResolutionRepository` plus a CloudFormation table
template. When selected, DynamoDB is the system of record—not a duplicate audit copy—for complete
resolution state, confirmation, execution claim, independent evidence, verifier result,
timestamps, owner identity, state history, and optimistic version. The runtime identity needs only
table-scoped `dynamodb:GetItem`, `dynamodb:PutItem`, and `dynamodb:Query`.

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
