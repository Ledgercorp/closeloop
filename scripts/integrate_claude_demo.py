"""Wire the supplied Claude Design bundle to CloseLoop's public demo API.

The transformation preserves the bundled visual/runtime assets and changes only
the demo data source, safe error state, and disclosure wording.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _replace_once(source: str, old: str, new: str, description: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"expected one {description}, found {source.count(old)}")
    return source.replace(old, new, 1)


MOBILE_LAYOUT_CSS = """  @media (max-width: 640px) {
    [role="group"][aria-label="Demo scenarios"] {
      left: 12px !important; right: 12px !important; max-width: none !important;
      transform: none !important; flex-wrap: nowrap !important;
      justify-content: flex-start !important; overflow-x: auto; scrollbar-width: none;
    }
    [role="group"][aria-label="Demo scenarios"] > * { flex: 0 0 auto; }
    [role="group"][aria-label="Demo scenarios"] > span:first-child { display: none; }
    [role="group"][aria-label="Demo scenarios"] > button {
      padding: 8px 10px !important; font-size: 0.72rem !important;
    }
    [aria-labelledby="lifecycle-heading"] ol { gap: 6px !important; }
    [aria-labelledby="lifecycle-heading"] ol li > span {
      font-size: 0.66rem !important; overflow-wrap: anywhere; hyphens: auto;
    }
  }
"""

# Presentation-only corrections for the generated document: language, title, and a
# narrow-viewport layout so the fixed scenario bar and stage labels never cover or
# overlap the outcome text. None of these touch data flow or verdict handling.
PRESENTATION_FIXES = (
    ("<html><head>", '<html lang="en"><head>', "document language attribute"),
    (
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n',
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>CloseLoop demo</title>\n",
        "document title",
    ),
    (
        "  summary::-webkit-details-marker { display: none; }\n",
        "  summary::-webkit-details-marker { display: none; }\n" + MOBILE_LAYOUT_CSS,
        "mobile layout rules",
    ),
)


def apply_presentation_fixes(template: str) -> str:
    for old, new, description in PRESENTATION_FIXES:
        template = _replace_once(template, old, new, description)
    return template


API_CLIENT = r'''const DEMO_API_PATH = "/demo/run";
const RESULT_SCHEMA = "closeloop.public-demo-result/v1";
const ALLOWED_SCENARIOS = new Set(["healthy", "false_success", "evidence_outage"]);
const TERMINAL_TUPLES = Object.freeze({
  PASS: ["Verified", "VERIFIED"],
  FAIL: ["Not completed", "NOT_COMPLETED"],
  INCONCLUSIVE: ["Awaiting proof", "AWAITING_PROOF"]
});

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function exactKeys(value, expected) {
  if (!isRecord(value)) return false;
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  return actual.length === wanted.length && actual.every((key, index) => key === wanted[index]);
}

function validTimestamp(value) {
  return typeof value === "string" && !Number.isNaN(Date.parse(value));
}

/* Validate the server contract without deriving a verdict from evidence. */
function parseDemoResponse(payload, requestedScenario) {
  if (!exactKeys(payload, [
    "schema_version", "server_generated", "scenario", "resolution", "execution_claim",
    "independent_read_back", "verification", "summary", "recommended_next_step", "disclosure"
  ])) return null;
  if (
    payload.schema_version !== RESULT_SCHEMA || payload.server_generated !== true ||
    payload.scenario !== requestedScenario || !ALLOWED_SCENARIOS.has(payload.scenario)
  ) return null;

  const resolution = payload.resolution;
  const claim = payload.execution_claim;
  const readback = payload.independent_read_back;
  const verification = payload.verification;
  const disclosure = payload.disclosure;
  if (!exactKeys(resolution, [
    "resolution_id", "action", "action_digest", "lifecycle_state", "requested_at",
    "confirmed_at", "executing_at", "verifying_at", "completed_at"
  ])) return null;
  if (!exactKeys(claim, [
    "source", "request_reference", "provider_reported_success", "message", "observed_at"
  ])) return null;
  if (!exactKeys(readback, [
    "source", "account_readable", "auto_renew", "effective_end_date",
    "freshness_seconds", "observed_at"
  ])) return null;
  if (!exactKeys(verification, [
    "verifier", "verdict", "consumer_state", "reason", "evaluated_at"
  ])) return null;
  if (!exactKeys(disclosure, [
    "provider", "confirmation", "live_alexa_plus", "live_aws", "production_action"
  ])) return null;

  const tuple = TERMINAL_TUPLES[verification.verdict];
  if (
    !tuple || verification.consumer_state !== tuple[0] || resolution.lifecycle_state !== tuple[1] ||
    resolution.action !== "cancel_subscription" ||
    typeof resolution.resolution_id !== "string" ||
    !/^[0-9a-f]{64}$/.test(resolution.action_digest) ||
    ![resolution.requested_at, resolution.confirmed_at, resolution.executing_at,
      resolution.verifying_at, resolution.completed_at, claim.observed_at,
      readback.observed_at, verification.evaluated_at].every(validTimestamp) ||
    claim.source !== "demo_provider.cancel_subscription" ||
    typeof claim.request_reference !== "string" ||
    typeof claim.provider_reported_success !== "boolean" || typeof claim.message !== "string" ||
    readback.source !== "demo_provider.read_cancellation_evidence" ||
    typeof readback.account_readable !== "boolean" ||
    (readback.auto_renew !== null && typeof readback.auto_renew !== "boolean") ||
    (readback.effective_end_date !== null && typeof readback.effective_end_date !== "string") ||
    (readback.freshness_seconds !== null && !Number.isInteger(readback.freshness_seconds)) ||
    verification.verifier !== "closeloop.verify_cancellation/v1" ||
    typeof verification.reason !== "string" || typeof payload.summary !== "string" ||
    typeof payload.recommended_next_step !== "string" ||
    disclosure.provider !== "deterministic simulated subscription provider" ||
    disclosure.confirmation !== "isolated public-demo confirmation; not a production trusted attestation" ||
    disclosure.live_alexa_plus !== false || disclosure.live_aws !== false ||
    disclosure.production_action !== false
  ) return null;

  return {
    resolutionId: resolution.resolution_id,
    digest: resolution.action_digest,
    times: {
      request: resolution.requested_at,
      confirmation: resolution.confirmed_at,
      executing: resolution.executing_at,
      verifying: resolution.verifying_at,
      outcome: resolution.completed_at
    },
    receipt: {
      requestId: claim.request_reference,
      providerReportedSuccess: claim.provider_reported_success,
      message: claim.message,
      observedAt: claim.observed_at
    },
    evidence: {
      accountReadable: readback.account_readable,
      autoRenew: readback.auto_renew,
      effectiveEndDate: readback.effective_end_date,
      freshnessSeconds: readback.freshness_seconds,
      observedAt: readback.observed_at
    },
    result: {
      verdict: verification.verdict,
      consumerState: verification.consumer_state,
      reason: verification.reason,
      evaluatedAt: verification.evaluated_at,
      summary: payload.summary,
      nextStep: payload.recommended_next_step
    }
  };
}

async function requestBackendResult(scenario, signal) {
  const response = await fetch(DEMO_API_PATH, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scenario }),
    credentials: "same-origin",
    cache: "no-store",
    signal
  });
  if (!response.ok) throw new Error("demo backend unavailable");
  const parsed = parseDemoResponse(await response.json(), scenario);
  if (!parsed) throw new Error("demo backend returned an invalid result");
  return parsed;
}

const SYMBOLS ='''


NEW_STATE = '''state = {
    scenario: "verified_path",
    phase: "confirm",
    resolutionId: null,
    digest: null,
    times: { request: null, confirmation: null, executing: null, verifying: null, outcome: null },
    receipt: null,
    evidence: null,
    result: null,
    error: null,
    resultIn: false
  };'''


NEW_CLEAR_RESET_CONFIRM = '''clear() {
    (this._timers || []).forEach(clearTimeout);
    this._timers = [];
    if (this._abortController) this._abortController.abort();
    this._abortController = null;
    this._active = false;
    this._requestSerial = (this._requestSerial || 0) + 1;
  }

  reset(scenario) {
    this.clear();
    this.setState({
      scenario: scenario || this.state.scenario,
      phase: "confirm",
      resolutionId: null,
      digest: null,
      times: { request: null, confirmation: null, executing: null, verifying: null, outcome: null },
      receipt: null, evidence: null, result: null, error: null, resultIn: false
    });
  }

  confirm() {
    if (this._active) return;
    const pace = Math.max(3, Number(this.props.paceSeconds ?? 6));
    const executeMs = pace * 1000 * 0.42;
    const verifyMs = pace * 1000 * 0.48;
    const scenario = MODES[this.state.scenario].providerMode;
    this.clear();
    this._active = true;
    const requestSerial = this._requestSerial;
    const controller = new AbortController();
    this._abortController = controller;

    this.setState({
      phase: "requesting",
      resolutionId: null,
      digest: null,
      times: { request: null, confirmation: null, executing: null, verifying: null, outcome: null },
      receipt: null,
      evidence: null,
      result: null,
      error: null,
      resultIn: false
    });

    const requestTimeout = setTimeout(() => controller.abort(), 7000);
    this._timers.push(requestTimeout);
    const backend = requestBackendResult(scenario, controller.signal)
      .then((data) => ({ ok: true, data }), () => ({ ok: false }))
      .finally(() => clearTimeout(requestTimeout));

    backend.then((response) => {
      if (requestSerial !== this._requestSerial) return;
      if (!response.ok) {
        this._active = false;
        this.setState({
          phase: "error", receipt: null, evidence: null, result: null,
          error: "The public demo backend did not return trustworthy proof.",
          resultIn: true
        });
        return;
      }
      const value = response.data;
      this.setState({
        phase: "executing",
        resolutionId: value.resolutionId,
        digest: value.digest,
        receipt: value.receipt,
        times: value.times
      });
      const executionTimer = setTimeout(() => {
        if (requestSerial !== this._requestSerial) return;
        this.setState({
          phase: "verifying",
          resolutionId: value.resolutionId,
          digest: value.digest,
          times: value.times,
          receipt: value.receipt,
          evidence: null,
          result: null,
          error: null
        });
        const verificationTimer = setTimeout(() => {
          if (requestSerial !== this._requestSerial) return;
          this._active = false;
          this.setState({
            phase: "terminal",
            resolutionId: value.resolutionId,
            digest: value.digest,
            times: value.times,
            receipt: value.receipt,
            evidence: value.evidence,
            result: value.result,
            error: null,
            resultIn: false
          });
          const revealTimer = setTimeout(() => {
            if (requestSerial === this._requestSerial) this.setState({ resultIn: true });
          }, 40);
          this._timers.push(revealTimer);
        }, verifyMs);
        this._timers.push(verificationTimer);
      }, executeMs);
      this._timers.push(executionTimer);
    });
  }'''


def integrate(source: str) -> str:
    match = re.search(
        r'(<script type="__bundler/template">\s*)(.*?)(\s*</script>)',
        source,
        flags=re.DOTALL,
    )
    if match is None:
        raise ValueError("Claude bundle template was not found")
    template = json.loads(match.group(2))

    template, count = re.subn(
        r"const MAX_EVIDENCE_AGE_SECONDS = 30;.*?const SYMBOLS =",
        API_CLIENT,
        template,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise ValueError("local provider/verifier block was not found exactly once")

    template, count = re.subn(
        r"state = \{\n    scenario: \"verified_path\",.*?\n  \};",
        NEW_STATE,
        template,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise ValueError("component state block was not found exactly once")

    template = _replace_once(
        template,
        "componentDidMount() {\n    this.setState({ times: { request: this.stamp(), confirmation: null, executing: null, verifying: null, outcome: null } });\n  }",
        "componentDidMount() {}",
        "local request timestamp initialization",
    )

    template, count = re.subn(
        r"clear\(\) \{.*?\n  confirm\(\) \{.*?\n  \}\n\n  clock\(iso\) \{",
        NEW_CLEAR_RESET_CONFIRM + "\n\n  clock(iso) {",
        template,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise ValueError("component lifecycle block was not found exactly once")

    template = _replace_once(
        template,
        "const { phase, times, receipt, evidence, result, resolutionId, scenario } = this.state;",
        "const { phase, times, receipt, evidence, result, error, resolutionId, scenario } = this.state;",
        "render state destructure",
    )
    template = _replace_once(
        template,
        'const idx = order.indexOf(phase);\n    const stageState = [',
        'const idx = order.indexOf(phase);\n    const stageState = phase === "requesting" ? [\n      "active", "pending", "pending", "pending", "pending"\n    ] : phase === "error" ? [\n      "complete", "pending", "pending", "pending", "pending"\n    ] : [',
        "requesting and error progress states",
    )
    template = _replace_once(
        template,
        "const terminalTone = result ? TONES[TONE_FOR[result.verdict]] : TONES.neutral;",
        "const terminalTone = error ? TONES.neutral : (result ? TONES[TONE_FOR[result.verdict]] : TONES.neutral);",
        "terminal tone",
    )
    template = _replace_once(
        template,
        'if (phase === "verifying") { stripText = "Execution returned a claim. CloseLoop is checking the account state itself."; }\n    if (result) {',
        'if (phase === "requesting") { stripText = "Requesting proof from the isolated demo backend. No execution or outcome is shown until the server returns a validated result."; }\n    if (phase === "verifying") { stripText = "Replaying the server-recorded independent verification step."; }\n    if (error) { stripIcon = "×"; stripText = "Server-side proof is unavailable. CloseLoop will not manufacture a successful outcome."; }\n    if (result) {',
        "neutral requesting and verification strips",
    )
    template = _replace_once(
        template,
        'const provenance = [];\n    provenance.push({',
        'const provenance = [];\n    if (resolutionId) provenance.push({',
        "resolution provenance guard",
    )
    template = _replace_once(
        template,
        '{ k: "Observed", v: this.full(times.verifying) }',
        '{ k: "Observed", v: this.full(receipt.observedAt) }',
        "execution observation time",
    )
    template = _replace_once(
        template,
        '{ k: "Observed", v: this.full(times.outcome) }',
        '{ k: "Observed", v: this.full(evidence.observedAt) }',
        "readback observation time",
    )
    template = _replace_once(
        template,
        '{ k: "Evaluated", v: this.full(times.outcome) },',
        '{ k: "Evaluated", v: this.full(result.evaluatedAt) },',
        "verification evaluation time",
    )
    template = _replace_once(
        template,
        'resolutionShort: "resolution " + resolutionId.slice(0, 8),\n      digestShort: this.state.digest.slice(0, 40) + "…",',
        'resolutionShort: resolutionId ? "resolution " + resolutionId.slice(0, 8) : "pending server run",\n      digestShort: this.state.digest ? this.state.digest.slice(0, 40) + "…" : "Assigned server-side after demo confirmation",',
        "pending server identifiers",
    )
    template = _replace_once(
        template,
        'isTerminal: phase === "terminal",',
        'isTerminal: phase === "terminal" || phase === "error",',
        "terminal error state",
    )
    template = _replace_once(
        template,
        'symbol: result ? SYMBOLS[result.verdict] : "·",\n      verdict: result ? result.verdict : "",\n      statusLabel: result ? result.consumerState : "",\n      plainLine: result ? PLAIN[result.verdict] : "",\n      verifierReason: result ? result.reason : "",\n      nextStep: result ? NEXT_STEP[result.verdict] : "",',
        'symbol: error ? "×" : (result ? SYMBOLS[result.verdict] : "·"),\n      verdict: result ? result.verdict : "",\n      statusLabel: error ? "Proof unavailable" : (result ? result.consumerState : ""),\n      plainLine: error ? "The demo backend did not return a trustworthy server result. CloseLoop will not claim completion." : (result ? result.summary : ""),\n      verifierReason: error || (result ? result.reason : ""),\n      nextStep: error ? "Retry the isolated demo run; no production action was performed." : (result ? result.nextStep : ""),',
        "server-derived terminal presentation",
    )
    template = _replace_once(
        template,
        'readbackTileStyle: tile(readbackKnown, readbackKnown && evidence.autoRenew === true ? "#f3ccc7" : "#d9e1dc"),',
        'readbackTileStyle: tile(readbackKnown, readbackKnown && evidence && evidence.autoRenew === true ? "#f3ccc7" : "#d9e1dc"),',
        "readback style guard",
    )
    template = _replace_once(
        template,
        "Confirmation is bound to this exact action. CloseLoop cannot execute without it.",
        "This button starts only an isolated public simulation. Production actions require a separately trusted, action-bound attestation.",
        "demo confirmation disclosure",
    )
    template = _replace_once(
        template,
        "No action has been performed yet. Execution begins only after explicit confirmation.",
        "No simulated action has been performed yet. The isolated run begins only after this demo confirmation.",
        "isolated confirmation copy",
    )
    template = _replace_once(
        template,
        ">Confirm cancellation</button>",
        ">Confirm demo cancellation</button>",
        "demo confirmation button",
    )
    template = _replace_once(
        template,
        'note: "Request arrives over the five-tool MCP surface."',
        'note: "This judge UI calls the isolated /demo/run API; production remains on the five-tool MCP surface."',
        "demo architecture disclosure",
    )
    template = _replace_once(
        template,
        'note: "Provider performs the action and returns a receipt."',
        'note: "The simulated provider mutates isolated demo state and returns a receipt."',
        "simulated execution disclosure",
    )
    template = _replace_once(
        template,
        'isRunning: phase === "executing" || phase === "verifying",\n      isTerminal: phase === "terminal" || phase === "error",\n      runningKicker: phase === "executing" ? "Executing" : "Verifying",\n      runningTitle: phase === "executing" ? "Confirmed — the action is running" : "Independently checking the result",\n      runningBody: phase === "executing"\n        ? "CloseLoop is executing the confirmed cancellation. No verdict exists yet, and nothing will be reported as done from this step alone."\n        : "The provider returned a receipt. CloseLoop is now reading the account state through a separate evidence path, because an execution claim is not proof.",',
        'isRunning: phase === "requesting" || phase === "executing" || phase === "verifying",\n      isTerminal: phase === "terminal" || phase === "error",\n      runningKicker: phase === "requesting" ? "Requesting server proof" : (phase === "executing" ? "Server-recorded execution" : "Server-recorded verification"),\n      runningTitle: phase === "requesting" ? "Waiting for the isolated demo backend" : (phase === "executing" ? "Replaying the confirmed demo action" : "Replaying independent verification"),\n      runningBody: phase === "requesting"\n        ? "No confirmation, execution claim, or verdict is displayed until CloseLoop returns a complete, validated server result."\n        : phase === "executing"\n          ? "The server returned complete proof. This presentation replays its recorded simulated execution step; the provider receipt is still only a claim."\n          : "This presentation now replays the server-recorded read-back and deterministic verification steps.",',
        "neutral requesting and server-recorded replay copy",
    )
    template = _replace_once(
        template,
        "using a simulated subscription provider and the deterministic verifier’s rules.",
        "using a simulated subscription provider and the real server-side deterministic verifier.",
        "footer verifier disclosure",
    )

    template = apply_presentation_fixes(template)

    for forbidden in ("function runProvider", "function verifyCancellation"):
        if forbidden in template:
            raise ValueError(f"local outcome logic remains: {forbidden}")
    if 'body: JSON.stringify({ scenario })' not in template:
        raise ValueError("backend-only scenario request was not installed")

    encoded_template = json.dumps(template, ensure_ascii=True).replace("<", "\\u003c")
    integrated = source[: match.start(2)] + encoded_template + source[match.end(2) :]
    return "\n".join(line.rstrip() for line in integrated.splitlines()) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_bundle", type=Path)
    parser.add_argument("output_bundle", type=Path)
    args = parser.parse_args()
    source = args.input_bundle.read_text(encoding="utf-8")
    integrated = integrate(source)
    args.output_bundle.parent.mkdir(parents=True, exist_ok=True)
    args.output_bundle.write_text(integrated, encoding="utf-8")


if __name__ == "__main__":
    main()
