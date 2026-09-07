# Final submission checklist

## Repository package

- [x] Public GitHub repository contains all source, setup, demo, tests, infrastructure, and docs.
- [x] Canonical Apache-2.0 text is stored in `LICENSE` and linked near the README opening.
- [x] README communicates the value proposition in under 10 seconds.
- [x] Exactly five MCP tools are documented; no verdict-write capability is claimed or exposed.
- [x] Alexa+, AWS, browser, security, provider, and deployment claims use explicit verification labels.
- [x] Build provenance distinguishes CloseLoop from prior CUF concepts/source.
- [x] Product feedback answers use, strengths, shortcomings, onboarding, and reuse intent.
- [x] Friction log contains only genuine reproduced issues and actionable recommendations.
- [x] Submission copy and judging-rubric map avoid unbuilt Bedrock/AgentCore/Strands claims.
- [x] Final focused checks, complete suite, diff review, and Governor review complete.
- [x] Package commit/push and signed-out repository/license verification complete.

## Video recording checklist

- [ ] Open `https://closeloop-zeta.vercel.app/demo/` in a fresh signed-out browser.
- [ ] Confirm the polished UI identifies the simulated provider and non-live Alexa+/AWS boundaries.
- [ ] Record the canonical request: “Alexa, cancel my subscription and make sure I won’t be charged again.”
- [ ] Show **Confirmation required** before any action.
- [ ] Show healthy **PASS → Verified** and expand execution/read-back/verifier provenance.
- [ ] Show false-success **FAIL → Not completed** with provider success and auto-renew still on together.
- [ ] Show outage **INCONCLUSIVE → Awaiting proof**.
- [ ] Show the implemented architecture and verification matrix briefly.
- [ ] Keep runtime below 180 seconds; target 2:50–2:55.
- [ ] Use English; remove notifications, personal data, tokens, local paths, and private tabs.
- [ ] Use no unauthorized music, footage, logos, or other copyrighted/trademarked assets.
- [ ] Export at a legible resolution and review the complete final file once.
- [ ] Upload publicly to YouTube or Vimeo and verify playback in a signed-out browser.

## Exact submission screenshots

Capture these from the signed-out public demo unless another source is specified:

1. **Hero / confirmation:** initial public demo state showing the task and “Confirmation required.”
2. **Primary result:** select Verified path, confirm, and capture “Verified” plus completed lifecycle.
3. **False-success proof:** select False success and expand proof so provider success, auto-renew on,
   and “Not completed” are visible together. This is the highest-value screenshot.
4. **Uncertainty proof:** select Evidence outage and capture “Awaiting proof.”
5. **Provenance detail:** Verified result expanded to show action receipt, independent read-back,
   deterministic verifier, timestamps, and identifiers.
6. **Implemented architecture:** README “How it works” diagram, without aspirational services.
7. **AWS proof:** `docs/aws-dynamodb.md` data/concurrency section plus the one-table
   `infra/aws/closeloop-dynamodb.json` resource. Caption it **Moto-simulated; not live AWS**.
8. **Test/security proof:** final terminal showing the complete passing count, plus the security
   report’s findings summary. Do not expose test signing keys.
9. **MCP discovery, if space allows:** five-tool Inspector output and MCP Apps resource metadata.
   Caption it **MCP integration verified locally; not a live Alexa+ client**.

## Devpost manual actions

1. Sign in to Devpost, join the hackathon, and confirm entrant/team eligibility. If entering as a
   team or organization, designate the authorized representative.
2. Choose primary track **Alexa+** and mini challenge **AWS Builder**. Select Open Source only if
   you also provide the required contribution URL, repository URL, GitHub username, and description.
3. Paste the reviewed fields from `docs/submission-copy.md`; replace every bracketed placeholder.
4. Add the public repository URL: `https://github.com/Ledgercorp/closeloop`.
5. In GitHub’s About panel, confirm the repository is public, Apache-2.0 is detected/visible, and the
   homepage points to the signed-out judge demo: `https://closeloop-zeta.vercel.app/demo/`.
6. Add the final public YouTube/Vimeo URL and confirm duration, English audio/captions, permissions,
   and signed-out playback.
7. Upload the strongest screenshots above. Do not label local cards as Alexa+ host screenshots.
8. Paste `docs/product-feedback.md` and the relevant `docs/friction-log.md` entries into the
   product-feedback/friction fields; include DynamoDB use for AWS Builder.
9. State plainly that the public browser demo calls an isolated server-side lifecycle/verifier with
   a deterministic simulated provider and demo-only confirmation, DynamoDB is Moto-simulated,
   Alexa+/MCP is locally integration verified, and live provider/Alexa+/AWS are not verified.
10. If live public execution is later required, provision shared storage, OAuth/account linking,
    and a trusted confirmation authority with production secrets. Never deploy the test or
    recording signer. Re-run anonymous `/`, `/health`, `/demo/`, and unauthenticated `/mcp` checks.
11. Review the submission preview in a signed-out browser. Test every repository, video, image, and
    optional demo link; remove inaccessible links.
12. Submit before **October 23, 2026 at 12:00 PM PDT** and save the final confirmation/receipt.

## Current external blockers

- A public video URL does not exist yet; recording/upload is a required manual action.
- No real Alexa+ client/add-on/Local Inspector/account-linking lifecycle has been exercised.
- The isolated server-backed judge demo is publicly verified; live provider-backed execution is not
  deployed.
- Safe public execution needs production shared storage, OAuth, and confirmation-authority
  configuration that is not present in this environment.
- Live AWS/DynamoDB remains unverified.

Do not resolve these blockers by weakening confirmation, authorization, storage, or evidence rules.
