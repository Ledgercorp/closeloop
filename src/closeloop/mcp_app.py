from __future__ import annotations

from mcp.server.apps import Apps, ResourceCsp


PROOF_CARD_URI = "ui://closeloop/proof-card.html"


PROOF_CARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CloseLoop proof</title>
  <style>
    :root {
      color-scheme: light dark;
      font-family: var(--font-sans, system-ui, sans-serif);
    }
    body {
      margin: 0;
      padding: 16px;
      background: var(--color-background-primary, Canvas);
      color: var(--color-text-primary, CanvasText);
    }
    main {
      border: 1px solid var(--color-border-primary, #8a8a8a);
      border-radius: var(--border-radius-md, 14px);
      padding: 16px;
      background: var(--color-background-secondary, Canvas);
    }
    h1 { margin: 0 0 6px; font-size: 1.1rem; }
    #task { margin: 0 0 16px; line-height: 1.4; }
    dl { display: grid; grid-template-columns: max-content 1fr; gap: 8px 12px; margin: 0; }
    dt { font-weight: 650; }
    dd { margin: 0; overflow-wrap: anywhere; }
    #outcome { font-weight: 750; }
    #outcome[data-state="Verified"] { color: #08783e; }
    #outcome[data-state="Not completed"] { color: #b3261e; }
    #outcome[data-state="Awaiting proof"] { color: #8a5a00; }
    #evidence { line-height: 1.4; }
  </style>
</head>
<body>
  <main aria-live="polite">
    <h1>CloseLoop proof</h1>
    <p id="task">Waiting for task data.</p>
    <dl>
      <dt>Execution</dt><dd id="execution">Not started</dd>
      <dt>Verification</dt><dd id="verification">Not started</dd>
      <dt>Outcome</dt><dd id="outcome">Pending</dd>
      <dt>Evidence</dt><dd id="evidence">No evidence received yet.</dd>
    </dl>
  </main>
  <script type="module">
    import {
      App,
      PostMessageTransport,
      applyDocumentTheme,
      applyHostFonts,
      applyHostStyleVariables
    } from "https://cdn.jsdelivr.net/npm/@modelcontextprotocol/ext-apps@1.7.5/+esm";

    const text = (id, value) => {
      document.getElementById(id).textContent = value ?? "Not available";
    };
    const label = (value) => String(value ?? "not_started").replaceAll("_", " ");
    const render = (data = {}) => {
      text("task", data.task ?? data.intent ?? "Task unavailable");
      text("execution", label(data.execution_status));
      text("verification", label(data.verification_status));
      const outcome = document.getElementById("outcome");
      outcome.textContent = data.consumer_state ?? "Pending";
      outcome.dataset.state = data.consumer_state ?? "";
      text("evidence", data.evidence_summary ?? data.explanation ?? "Evidence unavailable");
    };

    const app = new App({ name: "CloseLoop Proof Card", version: "0.4.0" });
    app.ontoolresult = (result) => render(result.structuredContent);
    app.onhostcontextchanged = (context) => {
      if (context.theme) applyDocumentTheme(context.theme);
      if (context.styles?.variables) applyHostStyleVariables(context.styles.variables);
      if (context.styles?.css?.fonts) applyHostFonts(context.styles.css.fonts);
    };
    app.onteardown = async () => ({});
    app.onerror = (error) => text("evidence", `Proof card unavailable: ${error.message}`);
    await app.connect(new PostMessageTransport(window.parent, window.parent));
  </script>
</body>
</html>
"""


def create_proof_card_extension() -> Apps:
    apps = Apps()
    apps.add_html_resource(
        PROOF_CARD_URI,
        PROOF_CARD_HTML,
        name="CloseLoop proof card",
        title="CloseLoop verification proof",
        description="Minimal read-only card for task, execution, verification, and evidence state.",
        csp=ResourceCsp(resource_domains=["https://cdn.jsdelivr.net"]),
        prefers_border=True,
    )
    return apps
