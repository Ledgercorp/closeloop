from __future__ import annotations

import asyncio
import json

from scripts.build_proof_card_validation import (
    VALIDATION_CONFIRMATION_SECRET,
    _build,
)


def test_submission_demo_builds_real_canonical_outcomes_and_recording_index(tmp_path):
    asyncio.run(_build(tmp_path))

    manifest = json.loads((tmp_path / "demo-results.json").read_text(encoding="utf-8"))
    index = (tmp_path / "index.html").read_text(encoding="utf-8")

    assert manifest["cases"] == {
        "evidence_outage": {
            "consumer_state": "Awaiting proof",
            "lifecycle_state": "AWAITING_PROOF",
            "verdict": "INCONCLUSIVE",
        },
        "false_success": {
            "consumer_state": "Not completed",
            "lifecycle_state": "NOT_COMPLETED",
            "verdict": "FAIL",
        },
        "healthy": {
            "consumer_state": "Verified",
            "lifecycle_state": "VERIFIED",
            "verdict": "PASS",
        },
    }
    assert manifest["live_alexa_plus"] is False
    assert manifest["live_aws"] is False
    assert "Local demonstration" in index
    for path in (
        "confirmation.html",
        "healthy.html",
        "false_success.html",
        "evidence_outage.html",
    ):
        assert f'href="{path}"' in index
        assert (tmp_path / path).is_file()


def test_submission_demo_does_not_export_local_signing_secret(tmp_path):
    asyncio.run(_build(tmp_path))

    generated_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in tmp_path.iterdir()
        if path.suffix in {".html", ".json"}
    )

    assert VALIDATION_CONFIRMATION_SECRET not in generated_text
    assert "live_alexa_plus\": true" not in generated_text
    assert "live_aws\": true" not in generated_text
