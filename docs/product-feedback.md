# Product feedback

This is submission-ready feedback for tools actually used or attempted. Detailed reproducible
issues and recommendations are in the [friction log](friction-log.md).

## Alexa+ MCP Toolkit documentation and developer tooling

- **Used for:** designing the self-hosted MCP transport, schemas, protected-resource discovery,
  account-linking boundary, conversational outputs, MCP Apps resource, and validation plan.
- **Worked well:** the documentation clearly identifies Streamable HTTP, MCP `2025-11-25`, strict
  tool/data design, PKCE-based account linking, and Local Inspector responsibilities.
- **Needs work:** the Alexa AI CLI, Local Inspector, package registry, and Add-on Agent Skill are
  selected-partner resources. Public setup paths did not expose an entitlement preflight, and the
  public authentication guidance does not define a per-action human-confirmation attestation for
  consequential tools.
- **Onboarding:** documentation-level onboarding was useful; tooling onboarding stopped before
  installation because this host lacks partner registry/CodeCommit credentials and Node.js 24+.
  No Alexa+ add-on, client session, or account link was created.
- **Would use again:** **Yes**, if partner access and a single supported bootstrap are available.
  The MCP model fits CloseLoop well, but live host behavior still needs verification.

## MCP Python SDK, MCP Inspector, and MCP Apps

- **Used for:** the five-tool server, stateless Streamable HTTP `/mcp`, strict schemas, tool
  discovery/calls, `ui://` proof-card resource, and local AppBridge rendering.
- **Worked well:** the SDK kept the service small and produced machine-readable input/output
  contracts. Inspector proved protocol discovery and calls; AppBridge let the exact production card
  consume structured results without creating a second verdict path.
- **Needs work:** SDK default auth behavior differed from Alexa+ discovery guidance; Inspector
  required a newer Node patch than this host provided; safe nested `srcdoc` hosting required
  manual script-context escaping; the MCP Apps runtime currently depends on a pinned CDN module.
- **Onboarding:** server setup was direct. Auth-discovery alignment and a browser-validation host
  required the most iteration.
- **Would use again:** **Yes**. The open protocol and schema tooling are strong foundations; a
  credential-free official MCP Apps renderer would make host compatibility much easier to prove.

## Amazon DynamoDB, boto3, and CloudFormation

- **Used for:** an optional authoritative, owner-scoped store for the complete resolution
  lifecycle, confirmation provenance, evidence, verifier result, timestamps, and optimistic
  version. CloudFormation defines one encrypted on-demand table.
- **Worked well:** strongly consistent reads and one conditional `PutItem` align naturally with
  owner isolation, lifecycle ordering, replay resistance, and immutable terminal outcomes.
- **Needs work:** Query limit/filter/pagination ordering and conditional-failure classification
  require careful cross-reading. DynamoDB Local also requires a separate Java 17 or Docker runtime.
- **Onboarding:** boto3 with Moto was straightforward. This host had no AWS CLI, credentials,
  usable Java runtime, or Docker, so live and official-local validation were unavailable.
- **Would use again:** **Yes** for this low-contention shared-state boundary, after live IAM/table
  validation and production recovery/backup design.

## Amazon Devices Builder Tools

- **Used for:** initializing Amazon developer context, inventorying available tools, and checking
  whether the package supplied Alexa+-specific authority.
- **Worked well:** initialization detected Codex, installed the context, and exposed a clear tool
  inventory.
- **Needs work:** the installed content is Vega/Fire OS-oriented and requires a device-OS platform
  choice even for an Alexa+-only repository. That can make package availability look like Alexa+
  compliance when it is not.
- **Onboarding:** setup completed, but CloseLoop intentionally selected neither Vega nor Fire OS,
  so no device-specific workflow was applied.
- **Would use again:** **Yes** for an actual Fire OS/Vega project. For Alexa+, it needs explicit
  Alexa+-specific documentation or a clear handoff to the MCP Toolkit.

## Vercel deployment integration

- **Used for:** the observed production build of the FastAPI entry point from GitHub at commit
  `173f85bf107a4ee6986c62434b17ae2b8fa2ba25`.
- **Worked well:** that observed commit received a successful Vercel deployment status.
- **Needs work:** the canonical project hostname returns `DEPLOYMENT_NOT_FOUND`, while generated
  deployment URLs redirect anonymous users to Vercel SSO. A successful build status therefore did
  not mean the MCP endpoint was judge- or Alexa-reachable.
- **Onboarding:** the observed Git-linked build completed, but anonymous access and required
  production storage/auth/confirmation configuration were not established.
- **Would use again:** **Yes**, with deployment protection configured deliberately and all
  fail-closed production dependencies provisioned first.

## Overall

CloseLoop would use the Alexa+ MCP and DynamoDB paths again. The strongest improvement would be one
public onboarding command that validates partner entitlement, Node/tool versions, OAuth discovery,
public endpoint reachability, Local Inspector access, and consequential-action confirmation
support before a developer invests in integration work.
