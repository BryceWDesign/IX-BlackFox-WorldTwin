from __future__ import annotations

from datetime import UTC, datetime

import pytest

import ix_blackfox_worldtwin as worldtwin


def _created_at() -> datetime:
    return datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _simulation(delta: float = 3.0) -> worldtwin.SimulationResult:
    return worldtwin.run_deterministic_simulation(
        scenario=worldtwin.build_thermal_drift_scenario(),
        rules=(
            worldtwin.create_simulation_rule(
                target="temperature",
                delta_per_step=delta,
                unit="F",
                description="Simple deterministic thermal drift.",
                minimum=-40.0,
                maximum=220.0,
            ),
            worldtwin.create_simulation_rule(
                target="risk_score",
                delta_per_step=0.10,
                unit="score",
                description="Simple deterministic risk accumulation.",
                initial_value=0.0,
                minimum=0.0,
                maximum=1.0,
                clamp_to_bounds=True,
            ),
        ),
        config=worldtwin.SimulationConfig(
            step_count=5,
            step_seconds=60,
            created_at=_created_at(),
        ),
    )


def _receipt(delta: float = 3.0) -> worldtwin.PredictionReceipt:
    simulation = _simulation(delta=delta)
    confidence = worldtwin.create_confidence_assessment(
        target_id=simulation.simulation_id,
        confidence=0.80,
        rationale="Simulation is deterministic and scenario-bounded.",
        created_at=_created_at(),
        assessor="worldtwin-confidence-gate",
    )
    prediction = worldtwin.create_prediction_result(
        simulation=simulation,
        created_at=_created_at(),
        created_by="worldtwin-prediction-gate",
        confidence_assessment=confidence,
    )
    return worldtwin.create_prediction_receipt(
        prediction=prediction,
        created_at=_created_at(),
        created_by="worldtwin-receipt-gate",
    )


def test_receipt_chain_creates_genesis_entry_and_validates() -> None:
    receipt = _receipt()
    chain = worldtwin.create_receipt_chain(
        receipts=(receipt,),
        created_at=_created_at(),
        created_by="worldtwin-chain-gate",
        notes=("initial chain",),
    )

    assert chain.chain_id.startswith("receipt-chain-")
    assert chain.schema_version == worldtwin.RECEIPT_CHAIN_SCHEMA_VERSION
    assert chain.tail.previous_entry_hash == worldtwin.GENESIS_PREVIOUS_ENTRY_HASH
    assert chain.head.sequence_number == 1
    assert chain.receipt_ids() == (receipt.receipt_id,)
    assert chain.notes == ("initial chain",)

    validation = worldtwin.validate_receipt_chain(
        chain=chain,
        receipts=(receipt,),
        checked_at=_created_at(),
        checked_by="worldtwin-chain-gate",
    )

    assert validation.status is worldtwin.ReceiptChainValidationStatus.PASS
    assert validation.passed is True
    assert validation.issues == ()


def test_receipt_chain_append_preserves_continuity() -> None:
    first_receipt = _receipt(delta=3.0)
    second_receipt = _receipt(delta=4.0)
    chain = worldtwin.create_receipt_chain(
        receipts=(first_receipt,),
        created_at=_created_at(),
        created_by="worldtwin-chain-gate",
    )
    appended = worldtwin.append_receipt_to_chain(
        chain=chain,
        receipt=second_receipt,
        created_at=_created_at(),
        created_by="worldtwin-chain-gate",
    )

    assert appended.receipt_ids() == (first_receipt.receipt_id, second_receipt.receipt_id)
    assert appended.entries[1].sequence_number == 2
    assert appended.entries[1].previous_entry_hash == appended.entries[0].entry_hash

    validation = worldtwin.validate_receipt_chain(
        chain=appended,
        receipts=(first_receipt, second_receipt),
        checked_at=_created_at(),
        checked_by="worldtwin-chain-gate",
    )

    assert validation.passed is True


def test_receipt_chain_rejects_duplicate_receipts() -> None:
    receipt = _receipt()

    with pytest.raises(ValueError, match="receipt chain contains duplicate receipt ids"):
        worldtwin.create_receipt_chain(
            receipts=(receipt, receipt),
            created_at=_created_at(),
            created_by="worldtwin-chain-gate",
        )


def test_receipt_chain_rejects_appending_existing_receipt() -> None:
    receipt = _receipt()
    chain = worldtwin.create_receipt_chain(
        receipts=(receipt,),
        created_at=_created_at(),
        created_by="worldtwin-chain-gate",
    )

    with pytest.raises(ValueError, match=f"receipt already exists in chain: {receipt.receipt_id}"):
        worldtwin.append_receipt_to_chain(
            chain=chain,
            receipt=receipt,
            created_at=_created_at(),
            created_by="worldtwin-chain-gate",
        )


def test_receipt_chain_validation_detects_missing_receipt() -> None:
    receipt = _receipt()
    chain = worldtwin.create_receipt_chain(
        receipts=(receipt,),
        created_at=_created_at(),
        created_by="worldtwin-chain-gate",
    )

    validation = worldtwin.validate_receipt_chain(
        chain=chain,
        receipts=(_receipt(delta=4.0),),
        checked_at=_created_at(),
        checked_by="worldtwin-chain-gate",
    )

    assert validation.status is worldtwin.ReceiptChainValidationStatus.FAIL
    assert validation.passed is False
    assert validation.issues == (
        f"entry {chain.entries[0].entry_id} references missing receipt {receipt.receipt_id}",
    )


def test_receipt_chain_validation_detects_tampered_entry_hash() -> None:
    receipt = _receipt()
    chain = worldtwin.create_receipt_chain(
        receipts=(receipt,),
        created_at=_created_at(),
        created_by="worldtwin-chain-gate",
    )
    tampered_entry = worldtwin.ReceiptChainEntry(
        entry_id=chain.entries[0].entry_id,
        sequence_number=chain.entries[0].sequence_number,
        receipt_id=chain.entries[0].receipt_id,
        receipt_fingerprint=chain.entries[0].receipt_fingerprint,
        previous_entry_hash=chain.entries[0].previous_entry_hash,
        entry_hash="tampered-entry-hash",
        created_at=chain.entries[0].created_at,
        created_by=chain.entries[0].created_by,
    )
    tampered_chain = worldtwin.ReceiptChain(
        chain_id=chain.chain_id,
        entries=(tampered_entry,),
        created_at=chain.created_at,
        created_by=chain.created_by,
    )

    validation = worldtwin.validate_receipt_chain(
        chain=tampered_chain,
        receipts=(receipt,),
        checked_at=_created_at(),
        checked_by="worldtwin-chain-gate",
    )

    assert validation.status is worldtwin.ReceiptChainValidationStatus.FAIL
    assert validation.issues == (
        f"entry {tampered_entry.entry_id} has invalid entry_hash",
    )


def test_receipt_chain_fingerprint_is_replay_stable() -> None:
    first = worldtwin.create_receipt_chain(
        receipts=(_receipt(),),
        created_at=_created_at(),
        created_by="worldtwin-chain-gate",
        notes=("b", "a"),
    )
    second = worldtwin.create_receipt_chain(
        receipts=(_receipt(),),
        created_at=_created_at(),
        created_by="worldtwin-chain-gate",
        notes=("a", "b"),
    )

    assert first.chain_id == second.chain_id
    assert first.fingerprint() == second.fingerprint()


def test_receipt_chain_validation_rejects_status_mismatch_when_constructed_directly() -> None:
    with pytest.raises(
        ValueError,
        match="receipt-chain validation status must match issue state",
    ):
        worldtwin.ReceiptChainValidationResult(
            chain_id="receipt-chain-manual",
            status=worldtwin.ReceiptChainValidationStatus.PASS,
            checked_at=_created_at(),
            checked_by="worldtwin-chain-gate",
            issues=("issue-a",),
        )
