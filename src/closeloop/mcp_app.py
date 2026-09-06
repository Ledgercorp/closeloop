from __future__ import annotations

import json

from mcp.server.apps import Apps, ResourceCsp


PROOF_CARD_URI = "ui://closeloop/proof-card.html"

PROOF_CARD_OUTCOME_RULES = {
    "PASS": {
        "consumerState": "Verified",
        "lifecycleState": "VERIFIED",
        "tone": "verified",
        "symbol": "✓",
        "support": "The action completed and the resulting state was independently verified.",
    },
    "FAIL": {
        "consumerState": "Not completed",
        "lifecycleState": "NOT_COMPLETED",
        "tone": "failed",
        "symbol": "!",
        "support": "The attempted action did not produce the required resulting state.",
    },
    "INCONCLUSIVE": {
        "consumerState": "Awaiting proof",
        "lifecycleState": "AWAITING_PROOF",
        "tone": "awaiting",
        "symbol": "?",
        "support": "CloseLoop cannot prove completion yet.",
    },
}


_PROOF_CARD_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CloseLoop resolution proof</title>
  <style>
    :root {
      color-scheme: light dark;
      font-family: var(--font-sans, Inter, ui-sans-serif, system-ui, -apple-system, sans-serif);
      --ink: var(--color-text-primary, #14211b);
      --muted: var(--color-text-secondary, #58645e);
      --surface: var(--color-background-primary, #ffffff);
      --surface-soft: var(--color-background-secondary, #f4f7f5);
      --line: var(--color-border-primary, #d9e1dc);
      --brand: #146c4b;
      --verified: #08783e;
      --verified-bg: #e7f6ed;
      --failed: #a7342d;
      --failed-bg: #fff0ee;
      --awaiting: #825800;
      --awaiting-bg: #fff5d9;
      --neutral: #4c5b54;
      --neutral-bg: #edf1ef;
      background: var(--surface-soft);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-width: 0;
      padding: clamp(12px, 3vw, 28px);
      background:
        radial-gradient(circle at top left, color-mix(in srgb, var(--brand) 11%, transparent), transparent 42%),
        var(--surface-soft);
      color: var(--ink);
    }

    main {
      width: min(100%, 760px);
      margin: 0 auto;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: clamp(18px, 3vw, 28px);
      background: var(--surface);
      box-shadow: 0 18px 54px rgba(21, 49, 36, 0.12);
    }

    .card-head,
    .content,
    .trust-note { padding-inline: clamp(18px, 4vw, 40px); }

    .card-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding-block: 18px;
      border-bottom: 1px solid var(--line);
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 0.94rem;
      font-weight: 760;
      letter-spacing: -0.01em;
    }

    .loop-mark {
      display: grid;
      width: 30px;
      height: 30px;
      place-items: center;
      border: 2px solid var(--brand);
      border-radius: 50%;
      color: var(--brand);
      font-size: 1rem;
      line-height: 1;
    }

    .environment {
      color: var(--muted);
      font-size: 0.76rem;
      font-weight: 680;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .content { padding-block: clamp(24px, 5vw, 42px); }

    .eyebrow {
      margin: 0 0 10px;
      color: var(--muted);
      font-size: 0.75rem;
      font-weight: 760;
      letter-spacing: 0.11em;
      text-transform: uppercase;
    }

    .task {
      max-width: 640px;
      margin: 0;
      font-size: clamp(1.16rem, 3.2vw, 1.65rem);
      font-weight: 650;
      letter-spacing: -0.025em;
      line-height: 1.28;
      overflow-wrap: anywhere;
    }

    .outcome {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr);
      gap: 14px;
      align-items: center;
      margin-top: 26px;
      padding: clamp(16px, 3vw, 22px);
      border: 1px solid var(--line);
      border-radius: 18px;
      background: var(--neutral-bg);
    }

    .outcome-mark {
      display: grid;
      width: 48px;
      height: 48px;
      place-items: center;
      border: 2px solid currentColor;
      border-radius: 50%;
      color: var(--neutral);
      font-size: 1.35rem;
      font-weight: 820;
    }

    .outcome h1 {
      margin: 0;
      font-size: clamp(1.42rem, 4vw, 2rem);
      letter-spacing: -0.035em;
      line-height: 1.05;
    }

    .outcome p { margin: 6px 0 0; color: var(--muted); line-height: 1.45; }

    main[data-tone="verified"] .outcome { background: var(--verified-bg); }
    main[data-tone="verified"] .outcome-mark { color: var(--verified); }
    main[data-tone="failed"] .outcome { background: var(--failed-bg); }
    main[data-tone="failed"] .outcome-mark { color: var(--failed); }
    main[data-tone="awaiting"] .outcome { background: var(--awaiting-bg); }
    main[data-tone="awaiting"] .outcome-mark { color: var(--awaiting); }

    .timestamp {
      display: block;
      margin-top: 10px;
      color: var(--muted);
      font-size: 0.78rem;
    }

    .confirmation {
      margin-top: 18px;
      padding: 14px 16px;
      border: 1px solid color-mix(in srgb, var(--awaiting) 35%, var(--line));
      border-radius: 14px;
      background: var(--awaiting-bg);
      color: #604300;
      font-weight: 650;
      line-height: 1.45;
    }

    .confirmation[hidden] { display: none; }

    .progress-label,
    .section-label {
      margin: 30px 0 12px;
      color: var(--muted);
      font-size: 0.74rem;
      font-weight: 760;
      letter-spacing: 0.1em;
      text-transform: uppercase;
    }

    .progress {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
      margin: 0;
      padding: 0;
      list-style: none;
    }

    .progress li {
      position: relative;
      min-width: 0;
      padding-top: 18px;
      color: var(--muted);
      font-size: 0.76rem;
      font-weight: 650;
      line-height: 1.3;
    }

    .progress li::before {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 5px;
      border-radius: 999px;
      background: var(--line);
      content: "";
    }

    .progress li[data-step="complete"] { color: var(--ink); }
    .progress li[data-step="complete"]::before { background: var(--brand); }
    .progress li[data-step="active"] { color: var(--ink); }
    .progress li[data-step="active"]::before {
      background: linear-gradient(90deg, var(--brand) 50%, var(--line) 50%);
    }

    .reason,
    .evidence-summary {
      margin: 0;
      color: var(--ink);
      font-size: 0.98rem;
      line-height: 1.55;
    }

    .evidence-summary {
      margin-top: 10px;
      padding: 16px;
      border-left: 4px solid var(--brand);
      border-radius: 4px 12px 12px 4px;
      background: var(--surface-soft);
    }

    details {
      margin-top: 14px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: var(--surface);
    }

    summary {
      padding: 15px 16px;
      cursor: pointer;
      font-weight: 720;
      list-style-position: inside;
    }

    summary:hover { background: var(--surface-soft); }
    summary:focus-visible {
      outline: 3px solid color-mix(in srgb, var(--brand) 55%, white);
      outline-offset: 3px;
    }

    .details-body {
      display: grid;
      gap: 12px;
      padding: 0 14px 14px;
    }

    .evidence-item {
      min-width: 0;
      padding: 15px;
      border-radius: 12px;
      background: var(--surface-soft);
    }

    .evidence-item[hidden],
    .detail-row[hidden],
    details[hidden] { display: none; }

    .evidence-item h2 {
      margin: 0;
      font-size: 0.96rem;
      letter-spacing: -0.01em;
    }

    .source {
      margin: 4px 0 12px;
      color: var(--muted);
      font-size: 0.76rem;
      overflow-wrap: anywhere;
    }

    dl {
      display: grid;
      grid-template-columns: minmax(110px, auto) minmax(0, 1fr);
      gap: 8px 14px;
      margin: 0;
      font-size: 0.84rem;
      line-height: 1.4;
    }

    dt { color: var(--muted); }
    dd { margin: 0; font-weight: 620; overflow-wrap: anywhere; }
    .detail-row { display: contents; }

    .history {
      display: grid;
      gap: 8px;
      margin: 0;
      padding: 0;
      list-style: none;
    }

    .history li {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      color: var(--muted);
      font-size: 0.8rem;
    }

    .history strong { color: var(--ink); font-weight: 650; }

    .trust-note {
      display: flex;
      gap: 10px;
      align-items: flex-start;
      margin: 0;
      padding-block: 18px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 0.78rem;
      line-height: 1.45;
    }

    .trust-note strong { color: var(--ink); }

    @media (max-width: 560px) {
      body { padding: 0; background: var(--surface); }
      main { border: 0; border-radius: 0; box-shadow: none; }
      .card-head { align-items: flex-start; }
      .environment { max-width: 120px; text-align: right; }
      .progress { grid-template-columns: 1fr; gap: 6px; }
      .progress li { min-height: 28px; padding: 4px 0 4px 24px; }
      .progress li::before { width: 8px; height: 100%; }
      .progress li[data-step="active"]::before {
        background: linear-gradient(180deg, var(--brand) 50%, var(--line) 50%);
      }
      dl { grid-template-columns: 1fr; gap: 3px; }
      dd { margin-bottom: 8px; }
      .detail-row { display: block; }
      .history li { display: grid; gap: 2px; }
    }

    @media (prefers-color-scheme: dark) {
      :root {
        --ink: var(--color-text-primary, #eef5f1);
        --muted: var(--color-text-secondary, #b5c2bb);
        --surface: var(--color-background-primary, #111a16);
        --surface-soft: var(--color-background-secondary, #19231e);
        --line: var(--color-border-primary, #35433b);
        --brand: #6ed3a5;
        --verified: #79dca8;
        --verified-bg: #123323;
        --failed: #ffaaa2;
        --failed-bg: #3a1e1c;
        --awaiting: #f4c963;
        --awaiting-bg: #332a12;
        --neutral: #c0cbc5;
        --neutral-bg: #222d27;
      }
      .confirmation { color: #f7d77f; }
      main { box-shadow: none; }
    }

    @media (forced-colors: active) {
      .outcome,
      .confirmation,
      .evidence-summary { border: 2px solid CanvasText; }
      .progress li::before { forced-color-adjust: none; }
      .outcome-mark { color: CanvasText !important; }
    }
  </style>
</head>
<body>
  <main id="proof-card" data-tone="neutral" aria-labelledby="outcome-title">
    <header class="card-head">
      <div class="brand"><span class="loop-mark" aria-hidden="true">↻</span>CloseLoop</div>
      <div class="environment" id="environment">Resolution proof</div>
    </header>

    <div class="content">
      <p class="eyebrow">Your request</p>
      <p class="task" id="task">Waiting for task data.</p>

      <section class="outcome" id="outcome-region" role="status" aria-live="polite" aria-atomic="true">
        <span class="outcome-mark" id="outcome-mark" aria-hidden="true">·</span>
        <div>
          <h1 id="outcome-title">Waiting for proof</h1>
          <p id="outcome-support">CloseLoop will show a result only after it validates the resolution data.</p>
          <time class="timestamp" id="outcome-time" hidden></time>
        </div>
      </section>

      <p class="confirmation" id="confirmation" hidden>
        Confirmation required — no action has run. CloseLoop will not continue until the customer explicitly confirms.
      </p>

      <p class="progress-label" id="progress-label">Resolution progress</p>
      <ol class="progress" aria-labelledby="progress-label">
        <li id="step-request">Request received</li>
        <li id="step-confirmation">Confirmation</li>
        <li id="step-execution">Action executed</li>
        <li id="step-verification">Independent check</li>
      </ol>

      <p class="section-label">Why this result</p>
      <p class="reason" id="reason">No resolution result has been received yet.</p>
      <p class="evidence-summary" id="evidence-summary">No execution or verification evidence is available.</p>

      <details id="evidence-details" hidden>
        <summary>View evidence and provenance</summary>
        <div class="details-body">
          <article class="evidence-item" id="execution-evidence" hidden>
            <h2>Execution claim</h2>
            <p class="source" id="execution-source"></p>
            <dl>
              <div class="detail-row" id="execution-reference-row"><dt>Request reference</dt><dd id="execution-reference"></dd></div>
              <div class="detail-row" id="execution-report-row"><dt>Provider reported</dt><dd id="execution-report"></dd></div>
              <div class="detail-row" id="execution-message-row"><dt>Claim</dt><dd id="execution-message"></dd></div>
              <div class="detail-row" id="execution-time-row"><dt>Observed</dt><dd><time id="execution-time"></time></dd></div>
            </dl>
          </article>

          <article class="evidence-item" id="readback-evidence" hidden>
            <h2>Independent read-back</h2>
            <p class="source" id="readback-source"></p>
            <dl>
              <div class="detail-row" id="readback-readable-row"><dt>Account state</dt><dd id="readback-readable"></dd></div>
              <div class="detail-row" id="readback-renew-row"><dt>Auto-renew</dt><dd id="readback-renew"></dd></div>
              <div class="detail-row" id="readback-end-row"><dt>Effective end</dt><dd id="readback-end"></dd></div>
              <div class="detail-row" id="readback-freshness-row"><dt>Evidence age</dt><dd id="readback-freshness"></dd></div>
              <div class="detail-row" id="readback-time-row"><dt>Observed</dt><dd><time id="readback-time"></time></dd></div>
            </dl>
          </article>

          <article class="evidence-item" id="verifier-evidence" hidden>
            <h2>Deterministic verifier</h2>
            <p class="source" id="verifier-source"></p>
            <dl>
              <div class="detail-row" id="verifier-verdict-row"><dt>Internal verdict</dt><dd id="verifier-verdict"></dd></div>
              <div class="detail-row" id="verifier-reason-row"><dt>Evaluation</dt><dd id="verifier-reason"></dd></div>
              <div class="detail-row" id="verifier-time-row"><dt>Evaluated</dt><dd><time id="verifier-time"></time></dd></div>
            </dl>
          </article>
        </div>
      </details>

      <details id="technical-details">
        <summary>Technical details</summary>
        <div class="details-body">
          <dl>
            <div class="detail-row" id="resolution-id-row"><dt>Resolution ID</dt><dd id="resolution-id">Not available</dd></div>
            <div class="detail-row" id="lifecycle-row"><dt>Lifecycle state</dt><dd id="lifecycle-state">Not available</dd></div>
            <div class="detail-row" id="provider-row"><dt>Provider mode</dt><dd id="provider-mode">Not available</dd></div>
          </dl>
          <ol class="history" id="state-history" aria-label="Resolution state history"></ol>
        </div>
      </details>
    </div>

    <p class="trust-note">
      <span aria-hidden="true">◇</span>
      <span><strong>How CloseLoop decides:</strong> execution claims are evidence, never the verdict. Independent read-back is evaluated by deterministic rules.</span>
    </p>
  </main>

  <script id="outcome-rules" type="application/json">__OUTCOME_RULES__</script>
  <script type="module">
    import {
      App,
      PostMessageTransport,
      applyDocumentTheme,
      applyHostFonts,
      applyHostStyleVariables
    } from "https://cdn.jsdelivr.net/npm/@modelcontextprotocol/ext-apps@1.7.5/+esm";

    const rules = Object.freeze(JSON.parse(document.getElementById("outcome-rules").textContent));
    const terminalStates = new Set(Object.values(rules).map((rule) => rule.lifecycleState));
    const byId = (id) => document.getElementById(id);
    const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
    const hasOwn = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
    const label = (value) => String(value ?? "not available").replaceAll("_", " ").toLowerCase();

    const consistentValue = (first, second) => {
      const hasFirst = first !== undefined && first !== null;
      const hasSecond = second !== undefined && second !== null;
      if (hasFirst && hasSecond && first !== second) return { valid: false, value: null };
      return { valid: true, value: hasFirst ? first : (hasSecond ? second : null) };
    };

    const invalidView = (reason = "This result could not be validated for display. Check the resolution again.") => ({
      valid: false,
      tone: "neutral",
      symbol: "×",
      outcome: "Proof unavailable",
      support: reason,
      phase: "invalid"
    });

    const deriveView = (data) => {
      if (!isObject(data)) return invalidView();
      const evidenceShape = hasOwn(data, "state_history") || hasOwn(data, "execution_claim") ||
        hasOwn(data, "independent_read_back") || hasOwn(data, "verification");
      const statusShape = hasOwn(data, "is_terminal") || hasOwn(data, "confirmation_required");
      if (evidenceShape === statusShape) return invalidView();
      if (
        statusShape &&
        (typeof data.is_terminal !== "boolean" || typeof data.confirmation_required !== "boolean")
      ) return invalidView();
      if (
        evidenceShape &&
        (!Array.isArray(data.state_history) || !hasOwn(data, "execution_claim") ||
          !hasOwn(data, "independent_read_back") || !hasOwn(data, "verification"))
      ) return invalidView();
      const nested = data.verification === undefined || data.verification === null
        ? null
        : (isObject(data.verification) ? data.verification : false);
      if (nested === false) return invalidView();

      const verdictPair = consistentValue(data.verdict, nested?.verdict);
      const consumerPair = consistentValue(data.consumer_state, nested?.consumer_state);
      if (!verdictPair.valid || !consumerPair.valid) return invalidView();

      const verdict = verdictPair.value;
      const consumerState = consumerPair.value;
      const lifecycle = data.lifecycle_state;
      const execution = data.execution_status;
      const verification = data.verification_status;
      const isTerminal = data.is_terminal;
      const confirmationRequired = data.confirmation_required;
      const terminalSignal = verdict !== null || consumerState !== null || terminalStates.has(lifecycle);

      if (terminalSignal) {
        const rule = rules[verdict];
        if (
          !rule || lifecycle !== rule.lifecycleState || consumerState !== rule.consumerState ||
          verification !== verdict || execution !== "completed" ||
          (statusShape && (isTerminal !== true || confirmationRequired !== false))
        ) return invalidView();
        return {
          valid: true,
          tone: rule.tone,
          symbol: rule.symbol,
          outcome: rule.consumerState,
          support: rule.support,
          phase: "terminal"
        };
      }

      if (nested !== null || isTerminal === true) return invalidView();
      const hasExecutionEvidence = data.execution_claim !== undefined && data.execution_claim !== null;
      const hasReadBack = data.independent_read_back !== undefined && data.independent_read_back !== null;

      if (lifecycle === "AWAITING_CONFIRMATION") {
        if (
          execution !== "not_started" || verification !== "not_started" ||
          confirmationRequired === false || hasExecutionEvidence || hasReadBack
        ) return invalidView();
        return {
          valid: true,
          tone: "awaiting",
          symbol: "!",
          outcome: "Confirmation required",
          support: "No action has run. Explicit confirmation is required before CloseLoop can continue.",
          phase: "confirmation"
        };
      }

      if (lifecycle === "EXECUTING") {
        if (
          execution !== "in_progress" || verification !== "not_started" ||
          confirmationRequired === true || hasExecutionEvidence || hasReadBack
        ) return invalidView();
        return {
          valid: true,
          tone: "neutral",
          symbol: "→",
          outcome: "Action in progress",
          support: "The confirmed action is running. CloseLoop has not evaluated the result yet.",
          phase: "executing"
        };
      }

      if (lifecycle === "VERIFYING") {
        if (
          execution !== "completed" || verification !== "in_progress" ||
          confirmationRequired === true || hasReadBack
        ) return invalidView();
        return {
          valid: true,
          tone: "neutral",
          symbol: "…",
          outcome: "Checking the result",
          support: "The action was attempted. CloseLoop is independently checking the resulting state.",
          phase: "verifying"
        };
      }

      return invalidView();
    };

    const setText = (id, value, fallback = "Not available") => {
      byId(id).textContent = value === undefined || value === null || value === "" ? fallback : String(value);
    };

    const setTimestamp = (id, value) => {
      const element = byId(id);
      if (typeof value !== "string" || Number.isNaN(Date.parse(value))) {
        element.hidden = true;
        element.removeAttribute("datetime");
        element.removeAttribute("title");
        element.textContent = "";
        return false;
      }
      const parsed = new Date(value);
      element.hidden = false;
      element.dateTime = value;
      element.title = value;
      element.textContent = new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short"
      }).format(parsed);
      return true;
    };

    const setRow = (rowId, valueId, value, formatter = String) => {
      const present = value !== undefined && value !== null && value !== "";
      byId(rowId).hidden = !present;
      if (present) setText(valueId, formatter(value));
      return present;
    };

    const renderProgress = (phase) => {
      const phases = {
        confirmation: ["complete", "active", "upcoming", "upcoming"],
        executing: ["complete", "complete", "active", "upcoming"],
        verifying: ["complete", "complete", "complete", "active"],
        terminal: ["complete", "complete", "complete", "complete"],
        invalid: ["complete", "upcoming", "upcoming", "upcoming"]
      };
      ["step-request", "step-confirmation", "step-execution", "step-verification"]
        .forEach((id, index) => {
          const element = byId(id);
          const step = (phases[phase] ?? phases.invalid)[index];
          element.dataset.step = step;
          if (step === "active") element.setAttribute("aria-current", "step");
          else element.removeAttribute("aria-current");
        });
    };

    const renderEvidence = (data) => {
      const execution = isObject(data.execution_claim) ? data.execution_claim : null;
      const readBack = isObject(data.independent_read_back) ? data.independent_read_back : null;
      const verifier = isObject(data.verification) ? data.verification : null;
      const hasEvidence = execution !== null || readBack !== null || verifier !== null;
      byId("evidence-details").hidden = !hasEvidence;

      byId("execution-evidence").hidden = execution === null;
      if (execution) {
        setText("execution-source", execution.source, "Source unavailable");
        setRow("execution-reference-row", "execution-reference", execution.request_id);
        setRow(
          "execution-report-row",
          "execution-report",
          execution.provider_reported_success,
          (value) => value === true ? "Success claimed" : "Success not claimed"
        );
        setRow("execution-message-row", "execution-message", execution.message);
        const hasTime = setTimestamp("execution-time", execution.observed_at);
        byId("execution-time-row").hidden = !hasTime;
      }

      byId("readback-evidence").hidden = readBack === null;
      if (readBack) {
        setText("readback-source", readBack.source, "Source unavailable");
        setRow(
          "readback-readable-row",
          "readback-readable",
          readBack.account_readable,
          (value) => value === true ? "Readable" : "Unavailable"
        );
        setRow(
          "readback-renew-row",
          "readback-renew",
          readBack.auto_renew,
          (value) => value === true ? "Enabled" : "Disabled"
        );
        setRow("readback-end-row", "readback-end", readBack.effective_end_date);
        setRow(
          "readback-freshness-row",
          "readback-freshness",
          readBack.freshness_seconds,
          (value) => `${value} seconds`
        );
        const hasTime = setTimestamp("readback-time", readBack.observed_at);
        byId("readback-time-row").hidden = !hasTime;
      }

      byId("verifier-evidence").hidden = verifier === null;
      if (verifier) {
        setText("verifier-source", verifier.verifier, "Verifier unavailable");
        setRow("verifier-verdict-row", "verifier-verdict", verifier.verdict);
        setRow("verifier-reason-row", "verifier-reason", verifier.reason);
        const hasTime = setTimestamp("verifier-time", verifier.evaluated_at);
        byId("verifier-time-row").hidden = !hasTime;
      }
    };

    const renderHistory = (history) => {
      const list = byId("state-history");
      list.replaceChildren();
      if (!Array.isArray(history)) return;
      history.forEach((transition) => {
        if (!isObject(transition) || typeof transition.state !== "string") return;
        const item = document.createElement("li");
        const state = document.createElement("strong");
        const time = document.createElement("time");
        state.textContent = label(transition.state);
        if (typeof transition.occurred_at === "string" && !Number.isNaN(Date.parse(transition.occurred_at))) {
          time.dateTime = transition.occurred_at;
          time.title = transition.occurred_at;
          time.textContent = new Intl.DateTimeFormat(undefined, {
            dateStyle: "medium",
            timeStyle: "short"
          }).format(new Date(transition.occurred_at));
        } else {
          time.textContent = "Time unavailable";
        }
        item.append(state, time);
        list.append(item);
      });
    };

    const render = (data) => {
      const payload = isObject(data) ? data : {};
      const view = deriveView(data);
      const card = byId("proof-card");
      card.dataset.tone = view.tone;
      setText("task", payload.task ?? payload.intent, "Task unavailable");
      setText("outcome-mark", view.symbol);
      setText("outcome-title", view.outcome);
      setText("outcome-support", view.support);
      byId("confirmation").hidden = view.phase !== "confirmation";
      renderProgress(view.phase);

      const safeReason = view.valid
        ? (payload.explanation ?? payload.verification?.reason ?? payload.evidence_summary)
        : "CloseLoop did not accept this data as a trustworthy completion result.";
      setText("reason", safeReason, "No verified explanation is available.");
      setText(
        "evidence-summary",
        view.valid ? payload.evidence_summary : null,
        view.valid
          ? "Detailed provenance is available when the evidence view is opened."
          : "No terminal claim is shown because the result contract is inconsistent."
      );

      const relevantTime = payload.verification?.evaluated_at
        ?? payload.independent_read_back?.observed_at
        ?? payload.confirmed_at
        ?? payload.updated_at
        ?? payload.created_at;
      setTimestamp("outcome-time", relevantTime);
      setText(
        "environment",
        payload.execution_environment === "demo_simulation" ? "Demo simulation" : "Resolution proof"
      );
      setText("resolution-id", payload.resolution_id);
      setText("lifecycle-state", label(payload.lifecycle_state));
      setText("provider-mode", label(payload.provider_mode));
      renderEvidence(view.valid ? payload : {});
      renderHistory(view.valid ? payload.state_history : []);
    };

    const app = new App({ name: "CloseLoop Proof Card", version: "0.6.0" }, {});
    app.ontoolresult = (result) => render(result.structuredContent);
    app.onhostcontextchanged = (context) => {
      if (context.theme) applyDocumentTheme(context.theme);
      if (context.styles?.variables) applyHostStyleVariables(context.styles.variables);
      if (context.styles?.css?.fonts) applyHostFonts(context.styles.css.fonts);
    };
    app.ontoolcancelled = () => render(null);
    app.onteardown = async () => ({});
    app.onerror = () => render(null);
    await app.connect(new PostMessageTransport(window.parent, window.parent));
  </script>
</body>
</html>
"""


PROOF_CARD_HTML = _PROOF_CARD_TEMPLATE.replace(
    "__OUTCOME_RULES__",
    json.dumps(PROOF_CARD_OUTCOME_RULES, ensure_ascii=False, separators=(",", ":")),
)


def create_proof_card_extension() -> Apps:
    apps = Apps()
    apps.add_html_resource(
        PROOF_CARD_URI,
        PROOF_CARD_HTML,
        name="CloseLoop proof card",
        title="CloseLoop resolution proof",
        description=(
            "Read-only consumer proof for confirmation, execution, independent verification, "
            "terminal outcome, and expandable evidence provenance."
        ),
        csp=ResourceCsp(resource_domains=["https://cdn.jsdelivr.net"]),
        prefers_border=True,
    )
    return apps
