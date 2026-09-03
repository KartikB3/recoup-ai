"""The audit log and the replay acceptance test. Phase 1.

THE GATE: reconstruct the run from the batch file and the log alone, with no
other state, and it must equal what the ledger holds. Over all 126 records and
112 ticks, for every arm.

The comparison deliberately covers more than `RecordState`. `recovered_paise`,
the contact ledger, `next_review_tick` and the promise fields are what the
Phase 2 metric table reads, and a replay that checked only state would go green
while recovered money silently diverged -- the failure most likely to embarrass
this project in front of a judge.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

from recoup.audit.log import (
    GENESIS_HASH,
    AuditLog,
    ChainBroken,
    read_log,
    row_hash,
    verify_chain,
)
from recoup.audit.replay import compare, reconstruct, replay
from recoup.baseline.naive_chaser import NaiveChaser
from recoup.domain.enums import Arm, RowKind
from recoup.generator.generate import generate_batch
from recoup.runner.batch import AlwaysWait, RunResult, run_batch, summarise, write_run

ARMS = ["always-wait", "naive-chaser"]


def _proposer(name: str) -> AlwaysWait | NaiveChaser:
    return AlwaysWait() if name == "always-wait" else NaiveChaser()


def _run(name: str) -> RunResult:
    """One full 126-record, 112-tick run of an arm."""
    return run_batch(
        generate_batch(42).records,
        _proposer(name),
        seed=42,
        run_id=f"test-{name}",
    )


@pytest.fixture(scope="module", params=ARMS)
def result(request: pytest.FixtureRequest) -> RunResult:
    """A completed run, built once per arm."""
    return _run(str(request.param))


# ---------------------------------------------------------------------------
# the log itself
# ---------------------------------------------------------------------------


#: Public `AuditLog` methods that do not mutate the row sequence. A new helper
#: must be classified here deliberately, which is the point: the equality check
#: below is a tripwire, and the thing it protects is that `append` stays the
#: only way a row comes into existence.
#:
#: `resume` is a CONSTRUCTOR, classified here after being weighed against the
#: invariant rather than waved through. It builds a log around rows already
#: written, verifying the chain first, so that the Phase 4 webhook can add a
#: payment outcome to the run that earned it. It changes no row it is given --
#: the new outcome still arrives through `append`, as invariant 5 has always
#: said outcomes do.
NON_MUTATING_LOG_METHODS: frozenset[str] = frozenset({"write", "resume"})


def test_the_log_has_no_writer_other_than_append() -> None:
    """INVARIANT 5. Nothing but `append` can change the row sequence.

    `write` flushes to disk and adds nothing. Everything else on the public
    surface must be a read, and a future `rows_for` or `by_tick` belongs in
    `NON_MUTATING_LOG_METHODS` rather than quietly widening this assertion --
    an `update` or `amend` slipping in unnoticed is exactly the failure the
    invariant exists to prevent.
    """
    public = {
        name
        for name in dir(AuditLog)
        if not name.startswith("_") and callable(getattr(AuditLog, name, None))
    }
    assert public - NON_MUTATING_LOG_METHODS == {"append"}, public


def test_rows_property_hands_back_a_copy() -> None:
    """A caller mutating the returned list must not touch the log."""
    log = AuditLog("r", Arm.AGENT)
    log.append(kind=RowKind.INTAKE, tick=0, record_id="X")
    borrowed = log.rows
    borrowed.clear()
    assert len(log) == 1


def test_the_chain_starts_at_genesis_and_links(result: RunResult) -> None:
    """Every row carries the hash of the row before it."""
    rows = result.log.rows
    assert rows[0].prev_row_hash == GENESIS_HASH
    for previous, current in itertools.pairwise(rows):
        assert current.prev_row_hash == row_hash(previous)
    verify_chain(rows)


def test_editing_a_row_breaks_the_chain(result: RunResult) -> None:
    """Tamper evidence. An accidental hand-edit must be caught, not believed."""
    rows = result.log.rows
    target = next(i for i, r in enumerate(rows) if r.kind is RowKind.OUTCOME)
    rows[target] = rows[target].model_copy(update={"tick": rows[target].tick + 1})
    with pytest.raises(ChainBroken) as caught:
        verify_chain(rows)
    assert caught.value.row_id == target + 1


def test_dropping_a_row_breaks_the_chain(result: RunResult) -> None:
    """A hash chain that only checks hashes still admits a file with a gap."""
    rows = result.log.rows
    del rows[5]
    with pytest.raises(ChainBroken):
        verify_chain(rows)


def test_outcomes_arrive_as_new_rows_never_as_updates(result: RunResult) -> None:
    """Row ids are dense and monotonic; nothing is rewritten in place."""
    rows = result.log.rows
    assert [r.row_id for r in rows] == list(range(len(rows)))
    kinds = {r.kind for r in rows}
    assert RowKind.INTAKE in kinds


def test_every_record_gets_an_intake_row(result: RunResult) -> None:
    """A reader of the log alone must see the opening position of the whole book."""
    intake = [r for r in result.log.rows if r.kind is RowKind.INTAKE]
    assert len(intake) == len(result.ledger.records)
    assert {r.record_id for r in intake} == {r.invoice_id for r in result.ledger.records}
    for row in intake:
        assert row.input_snapshot is not None


def test_decision_rows_carry_the_snapshot_that_produced_them(result: RunResult) -> None:
    """Without it the log cannot answer "why did it do that", which is the point."""
    decisions = [r for r in result.log.rows if r.kind is RowKind.DECISION]
    for row in decisions:
        assert row.input_snapshot is not None
        assert row.action is not None


# ---------------------------------------------------------------------------
# the acceptance test
# ---------------------------------------------------------------------------


def test_replay_reproduces_the_run_exactly(result: RunResult) -> None:
    """THE PHASE 1 GATE, over all 126 records and 112 ticks.

    Rebuilt from a PRISTINE batch plus the log. Nothing is carried over from
    the run's own objects, so a passing comparison means the log really is
    sufficient rather than that two references point at one list.
    """
    rebuilt = replay(generate_batch(42).records, result.log.rows)

    differences = compare(result.ledger.records, rebuilt.ledger.records)
    assert not differences, differences[:10]
    assert rebuilt.rows_applied == len(result.log.rows)
    assert len(rebuilt.ledger.records) == 126


def test_replay_reproduces_the_money_and_the_contacts(result: RunResult) -> None:
    """State alone is not enough; these are what the metric table reads."""
    rebuilt = replay(generate_batch(42).records, result.log.rows)

    assert sum(r.recovered_paise for r in rebuilt.ledger.records) == result.recovered_paise
    assert rebuilt.contacts == result.contacts
    assert rebuilt.api_units == result.api_units
    live_attempts = sum(r.contact_ledger.count for r in result.ledger.records)
    rebuilt_attempts = sum(r.contact_ledger.count for r in rebuilt.ledger.records)
    assert live_attempts == rebuilt_attempts


def test_replay_detects_a_divergence_when_one_is_introduced(result: RunResult) -> None:
    """A test that cannot fail proves nothing. Break it on purpose.

    If `compare` returned an empty list unconditionally, every assertion above
    would still pass.
    """
    rebuilt = replay(generate_batch(42).records, result.log.rows)
    rebuilt.ledger.records[0].recovered_paise += 1
    differences = compare(result.ledger.records, rebuilt.ledger.records)
    assert differences
    assert differences[0].field_name == "recovered_paise"


def test_write_offs_are_rows_in_the_log_not_an_implied_side_effect(result: RunResult) -> None:
    """Replay must reconstruct the closing position with no finalisation step.

    An earlier version wrote records off inside `Ledger.finalise`, outside the
    log entirely, and replay reproduced them only by running a copy of the same
    logic afterwards. That passed, and proved nothing: a replay that re-derives
    the answer is not a check. It also failed the moment the horizon had to be
    guessed from the rows -- `recoup replay` inferred 101 where the run had
    used 112, and every write-off came back with the wrong `resolved_tick`.
    """
    from recoup.domain.enums import OutcomeKind, RecordState

    rows = result.log.rows
    write_offs = [
        r for r in rows if r.outcome is not None and r.outcome.kind is OutcomeKind.WRITTEN_OFF
    ]
    live = [r for r in result.ledger.records if r.state is RecordState.WRITTEN_OFF]
    assert len(write_offs) == len(live) == result.written_off

    # No finalisation call anywhere in this test: the rows carry it.
    rebuilt = replay(generate_batch(42).records, rows)
    assert not compare(result.ledger.records, rebuilt.ledger.records)
    for record in rebuilt.ledger.records:
        if record.state is RecordState.WRITTEN_OFF:
            assert record.resolved_tick == result.horizon


def test_reconstruct_one_invoice_from_the_log_alone(result: RunResult) -> None:
    """The signature the module docstring names."""
    for record in result.ledger.records[:25]:
        state = reconstruct(record.invoice_id, generate_batch(42).records, result.log.rows)
        assert state is record.state, record.invoice_id


def test_a_run_is_reproducible_end_to_end() -> None:
    """The same seed and arm produce the same log, row for row."""
    first = _run("naive-chaser")
    second = _run("naive-chaser")
    assert len(first.log) == len(second.log)
    assert row_hash(first.log.rows[-1]) == row_hash(second.log.rows[-1])
    assert summarise(first) == summarise(second)


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------


def test_log_round_trips_through_jsonl(result: RunResult, tmp_path: Path) -> None:
    """What is written must read back as the same rows, and still verify."""
    path = result.log.write(tmp_path / "audit.jsonl")
    reloaded = read_log(path)
    assert len(reloaded) == len(result.log)
    verify_chain(reloaded)
    assert reloaded == result.log.rows


def test_written_log_has_no_carriage_returns(result: RunResult, tmp_path: Path) -> None:
    """The log is compared byte for byte; Windows must not rewrite it."""
    path = result.log.write(tmp_path / "audit.jsonl")
    assert b"\r\n" not in path.read_bytes()


def test_a_corrupt_line_names_its_position(tmp_path: Path) -> None:
    """A malformed log must say where it broke, not raise from inside pydantic."""
    path = tmp_path / "audit.jsonl"
    path.write_text('{"not": "a row"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"audit\.jsonl:1"):
        read_log(path)


def test_write_run_produces_a_replayable_artifact(tmp_path: Path) -> None:
    """The four files `recoup replay` needs, and a replay that uses them.

    `final.json` is what makes this a test rather than an exercise: without a
    stored closing position, replaying a log can only be checked against
    itself.
    """
    batch = generate_batch(42)
    result = run_batch(batch.records, NaiveChaser(), seed=42, run_id="artifact-test")
    out = write_run(result, batch, tmp_path / "artifact-test")

    for name in ("batch.json", "audit.jsonl", "final.json", "summary.json"):
        assert (out / name).exists(), name

    # The stored opening batch must be the generator's own bytes, not a second
    # serialisation of the same object. docs/SEED-DISTRIBUTION.md publishes a
    # SHA-256 of `serialise()` output as *the* batch hash, and a reader who
    # hashes this file and compares is entitled to a match.
    from recoup.generator.generate import serialise

    assert (out / "batch.json").read_text(encoding="utf-8") == serialise(generate_batch(42))

    from recoup.domain.models import Invoice
    from recoup.generator.generate import load_batch

    rows = read_log(out / "audit.jsonl")
    rebuilt = replay(load_batch(out / "batch.json").records, rows)
    stored = [
        Invoice.model_validate(row)
        for row in json.loads((out / "final.json").read_text(encoding="utf-8"))
    ]
    assert not compare(stored, rebuilt.ledger.records)


# ---------------------------------------------------------------------------
# the arms differ in the way they are supposed to
# ---------------------------------------------------------------------------


def test_doing_nothing_still_recovers_money() -> None:
    """WAIT is not a forfeit. Without this the whole comparison is rigged.

    Most of this book settles on its own cycle. If spontaneous payment rode the
    response channel, a record nobody contacted could never pay and the agent
    could never win by correctly declining to act.
    """
    result = _run("always-wait")
    assert result.contacts == 0
    assert result.recovered_paise > 0
    assert result.recovered_paise / result.billed_paise > 0.30


def test_chasing_recovers_more_but_costs_contacts_and_complaints() -> None:
    """The baseline is not a straw man: it genuinely beats doing nothing.

    And it pays for that in contacts and in human-queue items, which is the
    trade the agent arm has to improve on in Phase 2 rather than merely win.
    """
    idle = _run("always-wait")
    chaser = _run("naive-chaser")

    assert chaser.recovered_paise > idle.recovered_paise
    assert chaser.contacts > 200

    idle_states = summarise(idle)["states"]
    chaser_states = summarise(chaser)["states"]
    assert chaser_states.get("HUMAN_QUEUE", 0) > idle_states.get("HUMAN_QUEUE", 0)


def test_both_arms_face_the_same_world() -> None:
    """Same seed, same spontaneous draws. The arms differ only in what they did.

    If the adjudicator's hash key ever picked up an arm-dependent term, the two
    arms would face different luck and the comparison would be measuring the
    random number generator.
    """
    from recoup.ledger.adjudicator import uniform

    for record_id in ("ASH-2026-0001", "ASH-2026-0050", "ASH-2026-0126"):
        for tick in (0, 37, 111):
            assert uniform(42, record_id, tick, "spontaneous") == uniform(
                42, record_id, tick, "spontaneous"
            )
            assert uniform(42, record_id, tick, "spontaneous") != uniform(
                42, record_id, tick, "response"
            )
