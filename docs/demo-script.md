# CloseLoop three-minute video plan

Target runtime: **2:50–2:55**. Hard stop: **2:59**.

The recording uses the public judge demo at `https://closeloop-zeta.vercel.app/demo/`. Its three
outcomes come from the deployed server: the real CloseLoop lifecycle, deterministic demo provider,
independent read-back, and verifier, returned to the browser as presentation-safe evidence. Keep the
visible “Verified demo experience — not live Alexa+ rendering” badge and the footer disclosure in
frame. The provider and demo confirmation are simulations; do not describe the footage as a live
Alexa+ client, live provider, or live AWS environment.

## Recording setup

Open `https://closeloop-zeta.vercel.app/demo/` in a fresh signed-out browser window at a common
desktop size. If the public site is unreachable, run the same server locally and open
`http://127.0.0.1:8000/demo/` instead:

```bash
uv sync --locked --extra test --no-editable
PYTHONPATH=src uv run --no-editable uvicorn main:app \
  --host 127.0.0.1 --port 8000
```

Before recording, run each scenario once from the **Demo scenario** bar and verify:

- initial state → Confirmation required before anything runs
- **Verified path** → Verified
- **False success** → Not completed
- **Evidence outage** → Awaiting proof

For each terminal result, expand **View proof and provenance** once. Do not show test signing keys,
tokens, local filesystem paths, private browser tabs, or third-party music/footage.

## Storyboard and narration

### 0:00–0:20 — The problem

**Visual:** Start on the demo page in its confirmation state. Cut quickly to a prepared
false-success **Not completed** result, then back to the confirmation state.

**Narration:** “Agents are getting good at taking action—but a tool saying ‘success’ is not proof
that the real-world outcome happened. A cancellation can return success while auto-renew is still
on. For consequential tasks, that gap costs people money.”

### 0:20–0:45 — The product

**Visual:** Keep the headline and the three outcome tiles visible. Show the canonical request as an
on-screen caption:

> Alexa, cancel my subscription and make sure I won’t be charged again.

Scroll to **Confirmation required before anything runs**.

**Narration:** “CloseLoop is a verified-resolution layer for Alexa+. It requires trusted,
action-bound confirmation, keeps execution separate from judgment, and only says the task is done
when independent evidence proves it. Before confirmation, no mutation has run.”

### 0:45–1:35 — Healthy path

**Visual:** With **Verified path** selected, press **Confirm demo cancellation**. Let the lifecycle
run to **Verified**. Expand proof and provenance. Point to the execution claim, independent
read-back, and deterministic verifier.

**Narration:** “Here the confirmed cancellation executes. The provider returns a receipt—but
CloseLoop treats that as a claim, not a verdict. It separately reads the account state. Auto-renew
is off, the effective end date is present, and the evidence is fresh. Deterministic code evaluates
those facts and returns PASS. The customer sees Verified, with the proof and provenance available
on demand.”

### 1:35–2:05 — False-success path

**Visual:** Select **False success** and confirm. Let it run to **Not completed**. Hold both the
successful execution claim and the contradictory auto-renew read-back on screen.

**Narration:** “This is the trust moment. The provider again claims success, but independent
read-back says auto-renew is still enabled. CloseLoop does not let the executor grade its own work.
The verifier returns FAIL, and the customer sees Not completed instead of a false promise.”

### 2:05–2:25 — Evidence outage

**Visual:** Select **Evidence outage** and confirm. Let it run to **Awaiting proof** and briefly
expand proof and provenance.

**Narration:** “When read-back is unavailable, CloseLoop refuses to guess. It returns
INCONCLUSIVE—Awaiting proof—so infrastructure failure can never become fake success.”

### 2:25–2:45 — Architecture and integrations

**Visual:** Show the implemented architecture diagram in the README, then the verification matrix.

**Narration:** “CloseLoop is a five-tool Streamable HTTP MCP server compatible with the Alexa+
protocol requirement. The action plane cannot write verdicts. A trusted confirmation boundary
binds approval to the exact action. DynamoDB can be the authoritative, owner-scoped evidence store,
using consistent reads and conditional writes for replay protection and immutable outcomes.”

**On-screen labels:** “Alexa+/MCP: integration verified locally” and “DynamoDB: Moto-simulated; not
live AWS.”

### 2:45–2:59 — Close

**Visual:** Return to the three outcome tiles, ending on **Verified**.

**Narration:** “Agents are getting better at taking action. CloseLoop makes completion trustworthy.
It only tells you it’s done when there’s evidence.”

## Recording acceptance

- Total exported duration is below 180 seconds.
- The video is in English and publicly visible on YouTube or Vimeo.
- The first 10 seconds communicate independent verification.
- All three canonical outcomes are legible.
- The false-success contradiction receives the longest non-happy-path emphasis.
- Simulation and verification-level labels remain visible and truthful.
- The video contains no unauthorized trademarks, music, footage, credentials, or personal data.
- The final public URL works in a signed-out browser.
