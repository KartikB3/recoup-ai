"""The seeded generator. Phase 1.

The Phase 1 gate says `--seed 42` produces a byte-identical batch TWICE. The
word that matters is twice, and the trap is that calling `generate_batch`
twice in one interpreter shares a `PYTHONHASHSEED` and therefore proves nothing
about hash-order dependence -- which is the exact failure the sorted `flags`
serialiser exists to prevent. So the real check runs in subprocesses with
different hash seeds.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from recoup.cli import app
from recoup.domain.enums import Archetype, Flag
from recoup.generator.archetypes import BATCH_SIZE, CLUSTER_SIZE, PROFILES, total_records
from recoup.generator.generate import (
    apportion,
    generate_batch,
    load_batch,
    serialise,
    write_batch,
)

#: Emitted in a subprocess so each run gets its own `PYTHONHASHSEED`.
_DUMP = (
    "import sys;"
    "from recoup.generator.generate import generate_batch, serialise;"
    "sys.stdout.write(serialise(generate_batch(42)))"
)

PUBLISHED_SEED_42_SHA256 = "c903d91724d1c4566cb5c0a67ecf308eb6a0636772fe4a744a6b3f423188dd6f"


def _dump_with_hash_seed(hash_seed: str) -> str:
    """Serialise seed 42 in a fresh interpreter with a given PYTHONHASHSEED."""
    completed = subprocess.run(
        [sys.executable, "-c", _DUMP],
        capture_output=True,
        text=True,
        check=True,
        env={"PYTHONHASHSEED": hash_seed, "PATH": "", "SYSTEMROOT": ""},
    )
    return completed.stdout


def test_batch_size_matches_the_profile_table() -> None:
    """A profile table that does not sum to BATCH_SIZE silently truncates the batch."""
    assert total_records() == BATCH_SIZE
    assert BATCH_SIZE >= 120, "the spec floor is 120 records"


def test_apportionment_is_exact_at_the_default_size() -> None:
    """No largest-remainder rounding at 126; the table is the answer."""
    counts = apportion(BATCH_SIZE)
    assert counts == {a: p.count for a, p in PROFILES.items()}
    assert sum(counts.values()) == BATCH_SIZE


@pytest.mark.parametrize("count", [120, 126, 150, 200])
def test_apportionment_totals_hold_at_other_sizes(count: int) -> None:
    """`--count 150` must stay a legitimate batch, not a broken one."""
    counts = apportion(count)
    assert sum(counts.values()) == count
    assert all(v >= 0 for v in counts.values())


def test_same_seed_is_identical_in_process() -> None:
    """The cheap half of the gate."""
    assert serialise(generate_batch(42)) == serialise(generate_batch(42))


def test_different_seeds_differ() -> None:
    """A generator that ignores its seed would pass every determinism test."""
    assert serialise(generate_batch(42)) != serialise(generate_batch(43))


def test_byte_identical_across_processes_and_hash_seeds() -> None:
    """THE PHASE 1 GATE. Byte-identical in separate interpreters, different hash seeds.

    `Invoice.flags` is a `set`, and set iteration order varies with
    `PYTHONHASHSEED`. Without the sorted serialiser this test fails
    intermittently and only on someone else's machine, which is the worst
    possible way to find out.
    """
    first = _dump_with_hash_seed("0")
    second = _dump_with_hash_seed("1")
    third = _dump_with_hash_seed("12345")
    assert first == second == third
    assert first == serialise(generate_batch(42))


def test_round_trip_through_disk(tmp_path: Path) -> None:
    """Written and reloaded must equal what was generated."""
    batch = generate_batch(42)
    path, digest = write_batch(batch, tmp_path)
    assert path.exists()
    assert len(digest) == 64
    reloaded = load_batch(path)
    assert serialise(reloaded) == serialise(batch)


def test_written_file_has_no_carriage_returns(tmp_path: Path) -> None:
    """Windows must not turn the batch into a different file than Linux writes."""
    path, _ = write_batch(generate_batch(42), tmp_path)
    assert b"\r\n" not in path.read_bytes()


def test_documented_quickstart_reproduces_the_published_batch(tmp_path: Path) -> None:
    """The README command and published hash are one executable contract."""
    result = CliRunner().invoke(
        app,
        ["generate", "--seed", "42", "--count", "126", "--out", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    generated = tmp_path / "seed-42-n126.json"
    digest = hashlib.sha256(generated.read_bytes()).hexdigest()
    assert digest == PUBLISHED_SEED_42_SHA256
    assert f"sha256 {PUBLISHED_SEED_42_SHA256}" in result.output

    readme = Path("README.md").read_text(encoding="utf-8")
    assert "recoup generate --seed 42 --count 126" in readme


def test_all_amounts_are_positive_integers() -> None:
    """INVARIANT 1, on real data rather than on annotations."""
    for record in generate_batch(42).records:
        assert isinstance(record.amount_paise, int)
        assert record.amount_paise > 0
        # GST at 18% applied exactly: the value is a whole number of rupees
        # times 118, so it is always divisible by 2 with no fractional paise.
        assert record.amount_paise % 118 == 0


def test_due_dates_are_all_in_the_past() -> None:
    """Every record is an at-risk receivable at tick 0, or the batch is not a batch."""
    from recoup.domain.models import VIRTUAL_EPOCH

    for record in generate_batch(42).records:
        assert record.due_on < VIRTUAL_EPOCH
        assert record.issued_on < record.due_on


def test_the_cluster_is_one_group_of_nine() -> None:
    """The batch insight has nothing to find if the cluster is not intact."""
    batch = generate_batch(42)
    cluster = [r for r in batch.records if r.parent_group_id]
    assert len(cluster) == CLUSTER_SIZE
    assert len({r.parent_group_id for r in cluster}) == 1
    assert {r.invoice_id for r in cluster} == set(batch.meta.cluster_invoice_ids)


def test_cluster_members_all_go_quiet_in_one_week() -> None:
    """The co-occurrence IS the signal. Without it there is no batch-level insight."""
    batch = generate_batch(42)
    late, early = batch.meta.quiet_window
    for record in batch.records:
        if not record.parent_group_id:
            continue
        for reply in record.free_text.email_replies:
            assert late <= reply.received_on <= early, record.invoice_id


def test_cluster_records_do_not_repeat_each_others_templates() -> None:
    """Nine companies in one group must not send the same sentence twice.

    Those nine records are read side by side in the demo, so repetition there
    reads as a generator artifact rather than as texture.
    """
    batch = generate_batch(42)
    used: list[str] = []
    for record in batch.records:
        if record.parent_group_id:
            used.extend(record.provenance.template_ids)
    assert len(used) == len(set(used)), f"repeated cluster templates: {used}"


def test_paid_unreconciled_records_all_carry_the_flag() -> None:
    """These are the denominator for false interventions. A missing flag hides one."""
    records = [
        r for r in generate_batch(42).records if r.payer_archetype is Archetype.PAID_UNRECONCILED
    ]
    assert len(records) == PROFILES[Archetype.PAID_UNRECONCILED].count
    for record in records:
        assert Flag.ALREADY_PAID_UNRECONCILED in record.flags


def test_some_disputes_exist_only_in_prose() -> None:
    """The whole argument for the LLM, asserted.

    If every DISPUTING record also filed a structured `dispute_description`, a
    rule keyed on that field would match the agent exactly and the project
    would be a rules engine.
    """
    disputing = [r for r in generate_batch(42).records if r.payer_archetype is Archetype.DISPUTING]
    invisible = [r for r in disputing if r.free_text.dispute_description is None]
    assert invisible, "every dispute is visible in a structured field"
    assert len(invisible) >= 5, f"only {len(invisible)} prose-only disputes"
    for record in invisible:
        assert not record.free_text.is_empty, "a prose-only dispute with no prose"


def test_silence_is_represented() -> None:
    """A corpus where every record talks is a corpus that flatters the reasoner."""
    silent = [r for r in generate_batch(42).records if r.free_text.is_empty]
    assert len(silent) >= 10, f"only {len(silent)} records carry no free text"


def test_enough_records_sit_above_the_escalation_threshold() -> None:
    """A merchant rule with nothing to fire on is a rule nobody can see working."""
    from recoup.generator.archetypes import ESCALATION_REFERENCE_PAISE

    big = [r for r in generate_batch(42).records if r.amount_paise > ESCALATION_REFERENCE_PAISE]
    assert len(big) >= 5, f"only {len(big)} records above the escalation threshold"
