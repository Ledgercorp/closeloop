"""Build browser fixtures from real CloseLoop MCP results.

The generated pages are validation hosts, not an alternate product UI. Each host
loads the exact production MCP App HTML and delivers a real tool result through
the official AppBridge/PostMessageTransport lifecycle.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import jwt
from mcp import Client

from closeloop.confirmation import (
    CONFIRMATION_CONTRACT_VERSION,
    HmacJwtConfirmationAttestationVerifier,
)
from closeloop.lifecycle import ResolutionService
from closeloop.mcp_app import PROOF_CARD_HTML
from closeloop.mcp_server import create_mcp_server
from closeloop.repository import SqlResolutionRepository


OWNER = "proof-card-browser-validation"
INTENT = "Cancel my subscription and make sure I will not be charged again."
VALIDATION_CONFIRMATION_SECRET = "local-validation-only-confirmation-secret-32-bytes"
VALIDATION_CONFIRMATION_ISSUER = "https://confirmation.validation.local"
VALIDATION_CONFIRMATION_AUDIENCE = "https://closeloop.validation/confirmation"


def _validation_attestation(status: dict[str, object]) -> str:
    """Mint only a clearly labeled local browser-validation attestation."""

    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "iss": VALIDATION_CONFIRMATION_ISSUER,
            "aud": VALIDATION_CONFIRMATION_AUDIENCE,
            "confirmation_contract": CONFIRMATION_CONTRACT_VERSION,
            "sub": OWNER,
            "resolution_id": status["resolution_id"],
            "action": status["action"],
            "action_digest": status["action_digest"],
            "confirmed": True,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=60)).timestamp()),
            "jti": str(uuid4()),
        },
        VALIDATION_CONFIRMATION_SECRET,
        algorithm="HS256",
    )


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
    confirmation_verifier = HmacJwtConfirmationAttestationVerifier(
        secret=VALIDATION_CONFIRMATION_SECRET,
        issuer=VALIDATION_CONFIRMATION_ISSUER,
        audience=VALIDATION_CONFIRMATION_AUDIENCE,
    )
    server = create_mcp_server(
        ResolutionService(repository, confirmation_verifier=confirmation_verifier),
        principal_resolver=lambda: OWNER,
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
                {
                    "resolution_id": resolution_id,
                    "confirmed": True,
                    "confirmation_attestation": _validation_attestation(
                        started.structured_content
                    ),
                },
            )
            evidence = await client.call_tool(
                "get_resolution_evidence", {"resolution_id": resolution_id}
            )
            results[mode] = evidence.structured_content

        contradictory = dict(results["healthy"])
        contradictory["consumer_state"] = "Not completed"
        results["contradictory"] = contradictory

        contradictory_readback = deepcopy(results["healthy"])
        contradictory_readback["independent_read_back"]["auto_renew"] = True
        results["contradictory_readback"] = contradictory_readback

        forged_provenance = deepcopy(results["healthy"])
        forged_provenance["verification"]["verifier"] = "attacker.force_pass"
        results["forged_provenance"] = forged_provenance

        reordered_history = deepcopy(results["healthy"])
        reordered_history["state_history"][2:4] = reversed(
            reordered_history["state_history"][2:4]
        )
        results["reordered_history"] = reordered_history

        malformed_evidence = deepcopy(results["healthy"])
        malformed_evidence["independent_read_back"]["freshness_seconds"] = "0"
        results["malformed_evidence"] = malformed_evidence

        injected_text = deepcopy(results["healthy"])
        injected_text["task"] = '<img src=x onerror="document.body.dataset.pwned=true">'
        injected_text["execution_claim"]["message"] = "</script><script>alert(1)</script>"
        injected_text["verification"]["reason"] = "<b>literal evidence text</b>"
        results["injected_text"] = injected_text

        missing_status_booleans = dict(confirmation.structured_content)
        missing_status_booleans.pop("is_terminal")
        missing_status_booleans.pop("confirmation_required")
        results["missing_status_booleans"] = missing_status_booleans

        wrong_status_booleans = dict(confirmation.structured_content)
        wrong_status_booleans["is_terminal"] = "false"
        wrong_status_booleans["confirmation_required"] = "true"
        results["wrong_status_booleans"] = wrong_status_booleans

        results["unknown_state"] = {
            "task": "Unknown result",
            "lifecycle_state": "FORCED_VERIFIED",
            "is_terminal": True,
            "confirmation_required": False,
            "execution_status": "completed",
            "verification_status": "PASS",
            "consumer_state": "Verified",
            "verdict": "PASS",
        }
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
