# CloseLoop judge demo and recording plan

## Recording boundaries

Record the public demo at `https://closeloop-zeta.vercel.app/demo/` in a clean, signed-out Chromium context. The recovery button is the recommended path. The demo runs CloseLoop server-side lifecycle and verifier code against isolated demo state. StreamBox, the billing observation, time advancement, and spoken Alexa interactions are simulated. No real cancellation or refund is performed. No live Alexa+, AWS service, or production scheduler is used.

The browser selects a bounded scenario only. It does not submit a verdict, evidence, owner, target, confirmation attestation, or result. The recovery utterance shown in the demo is simulated consent; the production confirmation authority has not been connected to Alexa+.

## Complete narration (2:45 target)

### 0:00–0:15 — The problem

**Narration:** “When an assistant says ‘done,’ what does that mean? A successful request only proves the action ran. It doesn’t prove the result we wanted happened.”

### 0:15–0:35 — Ask normally

**Narration:** “I ask Alexa to cancel StreamBox before Friday and make sure I don’t get charged again. CloseLoop keeps that responsibility attached to the request. The cancellation waits for my confirmation.”

### 0:35–0:55 — False success

**Narration:** “StreamBox says the cancellation was accepted. A normal assistant could stop here. CloseLoop checks the account separately: auto-renew is still on. The action succeeded. The outcome didn’t.”

### 0:55–1:15 — Keep the loop open

**Narration:** “CloseLoop leaves the same request open and keeps watching. Time moves toward the renewal in this simulation. Nothing needs me yet, so it stays quiet.”

### 1:15–1:38 — Attention and recovery

**Narration:** “As the deadline gets close, the request needs my attention. CloseLoop offers a support follow-up using the cancellation details already saved. That is a new action, so it asks again. ‘Handle it’ is simulated here; this confirmation is separate from the cancellation.”

### 1:38–1:58 — Reverify

**Narration:** “The follow-up is prepared. Its receipt does not prove anything changed. CloseLoop checks the account again. Auto-renew is now off, so the independent evidence—not the recovery action—closes the loop.”

### 1:58–2:17 — Outcome violation

**Narration:** “There’s another way reality can go wrong. A simulated nineteen-dollar-and-ninety-nine-cent renewal charge appears after cancellation. CloseLoop saves the charge with the original request and timeline. It can prepare a refund request, but it does not send one.”

### 2:17–2:32 — Open responsibility and proof

**Narration:** “Open Loops tells me what is still being handled and whether I need to act. The receipt gives me the plain answer first, with the evidence available underneath.”

### 2:32–2:45 — Why trust it

**Narration:** “Alexa, the provider, and recovery cannot mark their own work successful. CloseLoop checks reality independently, and says when it doesn’t know. Ask Alexa to handle it. CloseLoop checks what actually happened.”

## Shot list

| Time / duration | Page and state | Cursor action | Narration | Visible text / evidence | Transition |
|---|---|---|---|---|---|
| 0:00–0:15 · 15s | `/demo/`, initial signed-out view | Hold on headline and request; no click | Problem narration | “Ask Alexa to handle it. CloseLoop checks whether it actually happened”; StreamBox request; simulation disclosure | Cut to confirmation button |
| 0:15–0:35 · 20s | Waiting for confirmation | Point to request, then click **Confirm cancellation and follow the recommended recovery story** | Ask normally | Waiting confirmation; confirmation is required; browser starts one bounded scenario | Let timeline finish rendering |
| 0:35–0:55 · 20s | Recovery timeline | Point from **ACTION ACCEPTED** to **CLOSELOOP CHECKED** | False-success narration | “accepted”; “auto-renew is still on”; “Not resolved yet”; false-success card highlighted | Hold on contradiction |
| 0:55–1:15 · 20s | Same recovery timeline | Scroll only enough to show simulated time and attention entries | Keep loop open | **SIMULATED TIME**; **NEEDS YOUR ATTENTION**; renews tomorrow | Move to separate authorization |
| 1:15–1:38 · 23s | Recovery timeline | Point to “Handle it” and **NEW AUTHORIZATION**; do not click another action | Attention and recovery narration | New confirmation; follow-up details saved; cancellation was not repeated | Move down one entry |
| 1:38–1:58 · 20s | Reverification and receipt | Point to **INDEPENDENT RECHECK**, then receipt | Reverify narration | **Checking the account again**; auto-renew off; verified result; October 3 access end; proof disclosure | Open “Explore other outcomes” |
| 1:58–2:17 · 19s | Alternate outcome | Click **Explore other outcomes**, then the renewal-charge scenario | Outcome-violation narration | $19.99 simulated charge after cancellation; evidence timeline; refund request is a draft and nothing is sent | Return to recovery receipt or stay on violation proof |
| 2:17–2:32 · 15s | Responsibility summary and proof | Show “Closed with independent proof”; open **See proof** briefly | Open Loops narration | Consumer summary first; persisted receipt and evidence underneath | Close proof and move to trust explanation |
| 2:32–2:45 · 13s | Trust explanation, then technical page only if time | Point to “Why trust the result?”; optional quick cut to `/demo/index.html` | Trust narration | Separate evidence, unknown stays open, separate recovery confirmation; seven MCP tools and tests may appear as a title card | End on product tagline |

## Judge-visible proof checklist

- The request is waiting for confirmation before the demo starts.
- Provider acceptance and independent account state are shown as different facts.
- The false-success step remains unresolved.
- The deadline advances only as simulated time.
- Recovery is a separate action and displays a separate simulated authorization.
- The recovery receipt is followed by independent reverification.
- Verified is shown only when the independent read-back supports it.
- Outcome Violation uses correlated simulated billing evidence; the refund request remains unsent.
- Awaiting proof stays open if evidence is unavailable; Not completed is evidence-supported.
- Expanded proof is derived from the returned persisted resolution result.

Do not show developer credentials, private browser tabs, real customer data, or claim live integrations. Do not submit or upload a video as part of this repository task.
