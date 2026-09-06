"""Build browser fixtures from real CloseLoop MCP results.

The generated pages are validation hosts, not an alternate product UI. Each host
loads the exact production MCP App HTML and delivers a real tool result through
the official AppBridge/PostMessageTransport lifecycle.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from mcp import Client

from closeloop.lifecycle import ResolutionService
from closeloop.mcp_app import PROOF_CARD_HTML
from closeloop.mcp_server import create_mcp_server
from closeloop.repository import SqlResolutionRepository


OWNER = "proof-card-browser-validation"
INTENT = "Cancel my subscription and make sure I will not be charged again."


def _script_json(value: object) -> str:
    """Serialize data safely inside an HTML script element."""

    return json.dumps(value, ensure_ascii=True, separators=(",", ":")).replace(
        "<", "\\u003c"
    )


def _host_html(name: str, structured_content: dict[str, object]) -> str:
    tool_result = {
        "content": [{"type": "text", "text": f"CloseLoop validation result: {name}"}],
        "structuredContent": structured_content,
        "isError": False,
    }
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CloseLoop proof-card validation — {name}</title>
  <style>
    html, body {{ margin: 0; min-height: 100%; background: #eef3f2; }}
    iframe {{ display: block; width: 100%; min-height: 1050px; border: 0; }}
  </style>
</head>
<body>
  <iframe id="app" title="CloseLoop proof card" sandbox="allow-scripts"></iframe>
  <script type="module">
    import {{ AppBridge, PostMessageTransport }} from
      "https://cdn.jsdelivr.net/npm/@modelcontextprotocol/ext-apps@1.7.5/app-bridge/+esm";

    const iframe = document.querySelector("#app");
    const bridge = new AppBridge(
      null,
      {{ name: "CloseLoop validation host", version: "1.0.0" }},
      {{ openLinks: {{}}, serverTools: {{}}, logging: {{}} }},
      {{ hostContext: {{
        theme: "light",
        platform: "web",
        locale: "en-US",
        timeZone: "America/New_York",
        containerDimensions: {{ width: 760, maxHeight: 1050 }}
      }} }}
    );
    bridge.oninitialized = async () => {{
      await bridge.sendToolInput({{ arguments: {{ fixture: {_script_json(name)} }} }});
      await bridge.sendToolResult({_script_json(tool_result)});
      requestAnimationFrame(() => requestAnimationFrame(() => {{
        document.documentElement.dataset.ready = "true";
      }}));
    }};
    const connection = bridge.connect(
      new PostMessageTransport(iframe.contentWindow, iframe.contentWindow)
    );
    iframe.srcdoc = {_script_json(PROOF_CARD_HTML)};
    await connection;
  </script>
</body>
</html>
"""


async def _real_results(database_path: Path) -> dict[str, dict[str, object]]:
    repository = SqlResolutionRepository(f"sqlite+pysqlite:///{database_path}")
    server = create_mcp_server(
        ResolutionService(repository), principal_resolver=lambda: OWNER
    )
    results: dict[str, dict[str, object]] = {}
    async with Client(server) as client:
        confirmation = await client.call_tool(
            "start_resolution", {"intent": INTENT, "provider_mode": "healthy"}
        )
        results["confirmation"] = confirmation.structured_content

        for mode in ("healthy", "false_success", "evidence_outage"):
            started = await client.call_tool(
                "start_resolution", {"intent": INTENT, "provider_mode": mode}
            )
            resolution_id = started.structured_content["resolution_id"]
            await client.call_tool(
                "confirm_resolution_action",
                {"resolution_id": resolution_id, "confirmed": True},
            )
            evidence = await client.call_tool(
                "get_resolution_evidence", {"resolution_id": resolution_id}
            )
            results[mode] = evidence.structured_content

        contradictory = dict(results["healthy"])
        contradictory["consumer_state"] = "Not completed"
        results["contradictory"] = contradictory

        missing_status_booleans = dict(confirmation.structured_content)
        missing_status_booleans.pop("is_terminal")
        missing_status_booleans.pop("confirmation_required")
        results["missing_status_booleans"] = missing_status_booleans

        wrong_status_booleans = dict(confirmation.structured_content)
        wrong_status_booleans["is_terminal"] = "false"
        wrong_status_booleans["confirmation_required"] = "true"
        results["wrong_status_booleans"] = wrong_status_booleans
    return results


async def _build(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    results = await _real_results(output_dir / "validation.db")
    for name, structured_content in results.items():
        (output_dir / f"{name}.html").write_text(
            _host_html(name, structured_content), encoding="utf-8"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    asyncio.run(_build(args.output_dir.resolve()))


if __name__ == "__main__":
    main()
