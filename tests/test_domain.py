"""The frozen contracts. Phase 1.

These test the invariants in CLAUDE.md that are checkable by introspection
rather than by behaviour. Several of them would be caught by a careful reviewer
and by nothing else, which is exactly why they are here: a reviewer reads a diff
once, and a test reads it on every commit.
"""

from __future__ import annotations

import inspect

import pytest
from pydantic import BaseModel

from recoup.domain import models as models_module
from recoup.domain.enums import Intervention
from recoup.domain.interventions import SPECS, spec
from recoup.domain.models import Invoice, format_inr
from recoup.generator.generate import generate_batch

#: INVARIANT 4. The closed intervention space, verbatim from CLAUDE.md.
EXPECTED_INTERVENTIONS = {
    "WAIT",
    "SOFT_REMINDER",
    "PAYMENT_LINK",
    "PHONE_FOLLOWUP",
    "ESCALATE_HUMAN",
    "STOP",
}

#: Ground truth. The simulation's answer key; the reasoner must never see it.
GROUND_TRUTH_FIELDS = {"payer_archetype", "flags", "provenance", "spotlight"}


def test_intervention_space_is_closed_and_exact() -> None:
    """INVARIANT 4. Nothing outside the six exists.

    Adding a seventh intervention is a decision with policy, cost and metric
    consequences, and it should fail this test loudly rather than appear.
    """
    assert {i.value for i in Intervention} == EXPECTED_INTERVENTIONS


def test_every_intervention_is_costed() -> None:
    """An intervention without a spec would silently cost nothing."""
    assert set(SPECS) == set(Intervention)
    for intervention in Intervention:
        assert spec(intervention) is SPECS[intervention]


def test_only_contact_interventions_have_a_channel() -> None:
    """A non-contact with a channel would put a message where none was sent."""
    for intervention in Intervention:
        details = spec(intervention)
        assert (details.channel is not None) == details.is_contact, intervention
        assert (details.contact_units > 0) == details.is_contact, intervention


def test_all_money_fields_are_integers() -> None:
    """INVARIANT 1. All money is `int` paise. Never float, never rupees.

    Checked by model introspection across every model in `domain.models`, so a
    future `amount: float` fails here rather than in a rounding bug six weeks
    later.
    """
    offenders: list[str] = []
    for _, obj in inspect.getmembers(models_module, inspect.isclass):
        if not issubclass(obj, BaseModel) or obj is BaseModel:
            continue
        for name, field in obj.model_fields.items():
            if "paise" not in name:
                continue
            annotation = str(field.annotation)
            if "float" in annotation or "Decimal" in annotation:
                offenders.append(f"{obj.__name__}.{name}: {annotation}")
    assert not offenders, offenders


def test_no_money_field_is_named_rupees() -> None:
    """Rupees are a presentation unit. A model field in rupees invites a bug."""
    offenders: list[str] = []
    for _, obj in inspect.getmembers(models_module, inspect.isclass):
        if not issubclass(obj, BaseModel) or obj is BaseModel:
            continue
        offenders.extend(
            f"{obj.__name__}.{name}" for name in obj.model_fields if name.endswith("_rupees")
        )
    assert not offenders, offenders


def test_snapshot_excludes_every_ground_truth_field() -> None:
    """The reasoner may not see the answer key.

    `to_snapshot` is the ONLY thing handed to a proposer. If a ground-truth
    field appears in it, the agent's performance stops meaning anything and a
    judge would be right to say so.
    """
    batch = generate_batch(42)
    record = batch.records[0]
    snapshot = record.to_snapshot(record.due_on, 0)
    leaked = GROUND_TRUTH_FIELDS & snapshot.keys()
    assert not leaked, f"snapshot leaks ground truth: {sorted(leaked)}"


def test_snapshot_does_not_leak_ground_truth_by_value() -> None:
    """A key rename would defeat the check above. Compare values too."""
    batch = generate_batch(42)
    for record in batch.records[:40]:
        snapshot = record.to_snapshot(record.due_on, 0)
        rendered = {str(v) for v in snapshot.values() if isinstance(v, str | int | bool)}
        assert record.payer_archetype.value not in rendered
        for flag in record.flags:
            assert str(flag) not in rendered
        for template_id in record.provenance.template_ids:
            assert template_id not in rendered


def test_snapshot_carries_the_free_text() -> None:
    """The converse failure: a snapshot with no prose makes the LLM pointless."""
    batch = generate_batch(42)
    with_text = [r for r in batch.records if not r.free_text.is_empty]
    assert len(with_text) > 100, f"only {len(with_text)} records carry free text"
    snapshot = with_text[0].to_snapshot(with_text[0].due_on, 0)
    assert snapshot["free_text"]


@pytest.mark.parametrize(
    ("paise", "expected"),
    [
        (0, "Rs 0.00"),
        (100, "Rs 1.00"),
        (123_456_789, "Rs 12,34,567.89"),
        (10_000_000, "Rs 1,00,000.00"),
        (-50_000, "-Rs 500.00"),
    ],
)
def test_indian_digit_grouping(paise: int, expected: str) -> None:
    """Presentation only, but it appears on the demo video."""
    assert format_inr(paise) == expected


def test_invoice_outstanding_never_goes_negative() -> None:
    """Overpayment must clamp, not produce a negative receivable."""
    record = generate_batch(42).records[0]
    record.recovered_paise = record.amount_paise * 2
    assert record.outstanding_paise == 0


def test_invoice_is_mutable_but_state_is_not_assigned_here() -> None:
    """Sanity: `Invoice` is a mutable model, which is why the ledger guard matters."""
    record = generate_batch(42).records[0]
    original = record.next_review_tick
    record.next_review_tick = original + 1
    assert record.next_review_tick == original + 1
    assert isinstance(record, Invoice)
