from __future__ import annotations

from pathlib import Path


def test_license_file_declares_source_available_evaluation_posture() -> None:
    license_text = Path("LICENSE").read_text(encoding="utf-8")

    assert "IX-BlackFox-WorldTwin Source-Available Evaluation License v1.0" in license_text
    assert "Copyright (c) 2026 Bryce Lovell. All rights reserved." in license_text
    assert "This license does not grant open-source rights." in license_text
    assert "Commercial Use" in license_text
    assert "Operational Use" in license_text
    assert "model-training use" in license_text
    assert "government operational use" in license_text


def test_license_file_preserves_evaluation_only_boundary() -> None:
    license_text = Path("LICENSE").read_text(encoding="utf-8")

    assert "limited internal review or testing of the unmodified Software" in license_text
    assert "production use" in license_text
    assert "derivative works" in license_text
    assert "separate written agreement is executed" in license_text
