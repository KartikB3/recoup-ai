"""Phase 4: the live slice, tested entirely offline.

Everything here runs against `FakePaymentLinkClient` and a temporary runs
directory. No network, no credentials, no test-mode links consumed (ISS-001),
which is what lets these run in CI on every push forever.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from recoup.audit.log import read_log, verify_chain
from recoup.domain.enums import Arm, ExecutorKind, Intervention, RecordState
from recoup.domain.interventions import spec
from recoup.executor.base import Executor
from recoup.executor.budget import LinkAllocator, LinkRequest, demand_from_log
from recoup.executor.fake_razorpay import FakePaymentLinkClient, paid_webhook_payload
from recoup.executor.live_razorpay import (
    MIN_LINK_PAISE,
    LiveRazorpayExecutor,
    RazorpayPaymentLinkClient,
    link_payload,
    reference_id,
)
from recoup.executor.session import find_link, read_session, write_session
from recoup.executor.simulated import SimulatedExecutor
from recoup.generator.generate import generate_batch
from recoup.policy.context import MerchantPolicy
from recoup.policy.engine import PolicyEngine
from recoup.reasoner.client import ClaudeReasoner
from recoup.reasoner.fallback import DeterministicFallback
from recoup.runner.batch import (
    LiveRunDivergence,
    NoPayableLink,
    assert_same_decisions,
    run_batch,
    run_live_batch,
    write_run,
)

#: States a real payment can no longer land on. See ISS-039.
TERMINAL = (RecordState.PAID, RecordState.WRITTEN_OFF)


# --------------------------------------------------------------------------
# the protocol change: LIVE must mean "a Razorpay object exists for this row"
# --------------------------------------------------------------------------


def test_simulated_executor_satisfies_the_protocol_and_never_claims_live() -> None:
    """The four-arm comparison rests on nothing in it having touched anything."""
    executor = SimulatedExecutor("run")
    assert isinstance(executor, Executor)
    record = generate_batch(42).records[0]
    for intervention in Intervention:
        result = executor.perform(record, intervention, 0)
        assert result.kind is ExecutorKind.SIMULATED
        if spec(intervention).api_units:
            assert result.external_ref == f"sim_link_run_{record.invoice_id}_0"
        else:
            assert result.external_ref is None


def test_only_payment_links_can_ever_be_live() -> None:
    """Recoup sends no email, SMS or voice, so those rows are never LIVE.

    The reason `ExecutionResult` carries the kind per action: a class-level
    LIVE stamp would mark every reminder in a live run as real.
    """
    record = generate_batch(42).records[0]
    executor = _live_executor(FakePaymentLinkClient(), [_request(record.invoice_id)], capacity=5)
    for intervention in (Intervention.SOFT_REMINDER, Intervention.PHONE_FOLLOWUP):
        result = executor.perform(record, intervention, 0)
        assert result.kind is ExecutorKind.SIMULATED
        assert "no live counterpart" in result.detail
    assert executor.perform(record, Intervention.PAYMENT_LINK, 0).kind is ExecutorKind.LIVE


# --------------------------------------------------------------------------
# allocation
# --------------------------------------------------------------------------


def _request(invoice_id: str, *, tick: int = 0, outstanding: int = 1_000_00) -> LinkRequest:
    return LinkRequest(invoice_id=invoice_id, tick=tick, outstanding_paise=outstanding)


def test_the_budget_goes_to_the_largest_requests_not_the_earliest() -> None:
    """The whole point of ISS-001: allocate the scarcity, do not take the first N."""
    demand = [
        _request("SMALL-EARLY", tick=0, outstanding=1_000_00),
        _request("BIG-LATE", tick=90, outstanding=90_000_00),
        _request("MID-MID", tick=40, outstanding=40_000_00),
    ]
    allocator = LinkAllocator(demand, capacity=2)
    assert [a.invoice_id for a in allocator.shortlist] == ["BIG-LATE", "MID-MID"]
    assert allocator.permits("BIG-LATE")
    assert not allocator.permits("SMALL-EARLY")


def test_only_the_first_link_on_a_record_is_funded() -> None:
    """A second link to one payer is worth less than a first to another."""
    allocator = LinkAllocator([_request("A", tick=0), _request("A", tick=20)], capacity=3)
    assert allocator.spend("A") is True
    assert allocator.spend("A") is False
    assert "already holds a real link" in allocator.refusal_reason("A")
    assert allocator.remaining == 2


def test_a_failed_call_does_not_burn_budget() -> None:
    """`may_spend` is separate from `spend` precisely so this holds."""
    record = generate_batch(42).records[0]
    client = FakePaymentLinkClient(fail_with=RuntimeError("gateway is unwell"))
    executor = _live_executor(client, [_request(record.invoice_id)], capacity=1)
    result = executor.perform(record, Intervention.PAYMENT_LINK, 0)
    assert result.kind is ExecutorKind.SIMULATED
    assert "failed" in result.detail
    assert executor.allocator.remaining == 1
    assert executor.failures and "RuntimeError" in executor.failures[0]
    assert executor.session.links == []


def test_capacity_zero_grants_nothing_and_raises_on_negative() -> None:
    allocator = LinkAllocator([_request("A")], capacity=0)
    assert allocator.shortlist == ()
    assert allocator.spend("A") is False
    with pytest.raises(ValueError):
        LinkAllocator([], capacity=-1)


def test_demand_is_read_from_executed_link_rows_only() -> None:
    """Vetoed and downgraded proposals never executed, so they are not demand."""
    result = _agent_run("demand")
    demand = demand_from_log(result.log.rows)
    executed_links = [
        row
        for row in result.log.rows
        if row.action
        and row.action.executed
        and row.action.intervention is Intervention.PAYMENT_LINK
    ]
    assert len(demand) == len(executed_links) > 0
    assert all(request.outstanding_paise > 0 for request in demand)


@pytest.mark.parametrize(
    ("proposer_name", "expected_top_three_requesting"),
    [("tiered", 0), ("ladder", 1)],
)
def test_an_intake_shortlist_would_waste_the_budget(
    proposer_name: str, expected_top_three_requesting: int
) -> None:
    """The measured failure that shaped the design, pinned so it cannot drift.

    Shortlisting the biggest invoices at intake reserves the budget for records
    that never ask for a link: under the cost-tiered agent none of the top three
    ever does, and under the Phase 2 ladder only one of them does. These two
    numbers are quoted in `executor.budget`'s docstring.
    """
    batch = generate_batch(42)
    biggest = {
        record.invoice_id for record in sorted(batch.records, key=lambda r: -r.amount_paise)[:3]
    }

    if proposer_name == "tiered":
        reasoner = ClaudeReasoner(cache_only=True)
        result = run_batch(
            batch.records,
            reasoner,
            seed=42,
            run_id="waste",
            horizon=112,
            policy=PolicyEngine(MerchantPolicy(link_budget=None)),
            batch_reasoner=reasoner,
        )
    else:
        result = _agent_run("waste")

    demand = demand_from_log(result.log.rows)
    requesters = {request.invoice_id for request in demand}
    assert len(biggest & requesters) == expected_top_three_requesting
    # Revealed demand, by contrast, fills every unit it is given.
    assert len(LinkAllocator(demand, capacity=3).shortlist) == 3


# --------------------------------------------------------------------------
# the two-pass live run
# --------------------------------------------------------------------------


def _agent_run(run_id: str) -> Any:
    return run_batch(
        generate_batch(42).records,
        DeterministicFallback(),
        seed=42,
        run_id=run_id,
        horizon=112,
        policy=PolicyEngine(MerchantPolicy(link_budget=None)),
    )


def _live_executor(
    client: FakePaymentLinkClient,
    demand: list[LinkRequest],
    *,
    capacity: int,
    run_id: str = "run",
) -> LiveRazorpayExecutor:
    return LiveRazorpayExecutor(
        client,
        LinkAllocator(demand, capacity),
        run_id=run_id,
        arm=Arm.AGENT,
        key_id="rzp_test_offline",
    )


def _live_run(run_id: str, capacity: int) -> tuple[Any, FakePaymentLinkClient]:
    client = FakePaymentLinkClient()
    executors: list[LiveRazorpayExecutor] = []

    def build(allocator: LinkAllocator) -> LiveRazorpayExecutor:
        executor = LiveRazorpayExecutor(
            client,
            allocator,
            run_id=run_id,
            arm=Arm.AGENT,
            key_id="rzp_test_offline",
            callback_url="https://example.invalid/razorpay/callback",
        )
        executors.append(executor)
        return executor

    outcome = run_live_batch(
        generate_batch(42).records,
        DeterministicFallback(),
        seed=42,
        run_id=run_id,
        capacity=capacity,
        executor_factory=build,
        policy_factory=lambda: PolicyEngine(MerchantPolicy(link_budget=None)),
        horizon=112,
    )
    return (outcome, executors[-1]), client


def test_a_live_run_makes_exactly_the_decisions_the_dry_run_made() -> None:
    """The claim the allocation rests on, asserted rather than assumed."""
    (outcome, executor), client = _live_run("livepass", 3)
    assert_same_decisions(outcome.dry, outcome.live)
    assert len(client.calls) == 3
    assert len(executor.session.links) == 3

    live_rows = [
        row
        for row in outcome.live.log.rows
        if row.action and row.action.executor is ExecutorKind.LIVE
    ]
    assert len(live_rows) == 3
    assert all(
        row.action and row.action.intervention is Intervention.PAYMENT_LINK for row in live_rows
    )
    # Everything else in the run is untouched by having gone live.
    assert outcome.live.contacts == outcome.dry.contacts
    assert outcome.live.recovered_paise == outcome.dry.recovered_paise


def test_the_funded_links_are_the_most_valuable_requests() -> None:
    (outcome, executor), _client = _live_run("livevalue", 3)
    demand = {r.invoice_id: r.outstanding_paise for r in demand_from_log(outcome.dry.log.rows)}
    funded = {link.invoice_id for link in executor.session.links}
    cheapest_funded = min(demand[i] for i in funded)
    unfunded = [v for k, v in demand.items() if k not in funded]
    assert cheapest_funded >= max(unfunded), "a cheaper request was funded over a dearer one"


def test_divergent_passes_are_refused() -> None:
    """If the two passes ever disagreed, the allocation would describe a fiction."""
    left = _agent_run("same")
    right = _agent_run("same")
    assert_same_decisions(left, right)  # same inputs, so identical
    right.log.append(
        kind=right.log.rows[-1].kind,
        tick=999,
        record_id="ASH-2026-0001",
    )
    with pytest.raises(LiveRunDivergence):
        assert_same_decisions(left, right)


# --------------------------------------------------------------------------
# the request Razorpay actually receives
# --------------------------------------------------------------------------


def test_nothing_is_ever_notified_and_no_customer_is_sent() -> None:
    """The payer names are generated. A notification would reach a stranger."""
    record = generate_batch(42).records[0]
    payload = link_payload(record, 12, run_id="run", callback_url="https://x.invalid/cb")
    assert payload["notify"] == {"sms": False, "email": False}
    assert payload["reminder_enable"] is False
    assert "customer" not in payload
    assert payload["amount"] == record.outstanding_paise
    assert payload["currency"] == "INR"
    assert payload["callback_method"] == "get"
    assert payload["notes"] == {
        "recoup_invoice_id": record.invoice_id,
        "recoup_run_id": "run",
        "recoup_tick": "12",
    }


def test_the_reference_id_is_stable_unique_and_short_enough() -> None:
    """Razorpay caps it at 40 characters and requires account-wide uniqueness."""
    first = reference_id("run-a", "ASH-2026-0001", 12)
    assert first == reference_id("run-a", "ASH-2026-0001", 12)
    assert first != reference_id("run-b", "ASH-2026-0001", 12)
    assert first != reference_id("run-a", "ASH-2026-0001", 13)
    assert len(first) <= 40


def test_a_link_below_one_rupee_is_never_attempted() -> None:
    record = (
        generate_batch(42)
        .records[0]
        .model_copy(update={"recovered_paise": generate_batch(42).records[0].amount_paise - 1})
    )
    assert record.outstanding_paise < MIN_LINK_PAISE
    executor = _live_executor(FakePaymentLinkClient(), [_request(record.invoice_id)], capacity=1)
    result = executor.perform(record, Intervention.PAYMENT_LINK, 0)
    assert result.kind is ExecutorKind.SIMULATED
    assert "one-rupee minimum" in result.detail


def test_a_response_without_a_usable_id_degrades_rather_than_lying() -> None:
    class Broken:
        def create(self, data: dict[str, Any]) -> dict[str, Any]:
            return {"status": "created"}  # no id

    record = generate_batch(42).records[0]
    executor = LiveRazorpayExecutor(
        Broken(),
        LinkAllocator([_request(record.invoice_id)], 1),
        run_id="run",
        arm=Arm.AGENT,
        key_id="rzp_test_offline",
    )
    result = executor.perform(record, Intervention.PAYMENT_LINK, 0)
    assert result.kind is ExecutorKind.SIMULATED
    assert result.external_ref is None
    assert executor.session.links == []


def test_a_live_key_is_refused_before_a_client_exists() -> None:
    """Recoup never touches live mode. Not a warning; a refusal."""
    with pytest.raises(ValueError, match="not a test key"):
        RazorpayPaymentLinkClient("rzp_live_something", "secret")
    with pytest.raises(ValueError, match="must both be set"):
        RazorpayPaymentLinkClient("", "")


# --------------------------------------------------------------------------
# the session index
# --------------------------------------------------------------------------


def test_a_session_round_trips_and_is_findable_by_payment_link_id(tmp_path: Path) -> None:
    (_outcome, executor), _client = _live_run("session", 2)
    arm_dir = tmp_path / "runs" / "session" / "agent"
    write_session(executor.session, arm_dir)

    restored = read_session(arm_dir)
    assert restored is not None
    assert restored.model_dump() == executor.session.model_dump()

    target = executor.session.links[0]
    located = find_link(tmp_path / "runs", target.payment_link_id)
    assert located is not None
    found_dir, _session, link = located
    assert found_dir == arm_dir
    assert link.invoice_id == target.invoice_id
    assert find_link(tmp_path / "runs", "plink_nothingatall") is None
    assert read_session(tmp_path / "runs" / "absent") is None


# --------------------------------------------------------------------------
# ground truth: the allocator is held to the policy engine's standard
# --------------------------------------------------------------------------


def test_the_executor_package_never_reads_simulation_ground_truth() -> None:
    """`tests/test_policy.py` greps the policy package. Same standard here.

    Allocating by `payer_archetype` would be allocating by the answer key.
    """
    answer_key = ("payer_archetype", "flags", "provenance", "spotlight")
    # A bulk dump would smuggle the whole answer key out in one call, so it is
    # banned in the modules that DECIDE. `reconcile` and `session` are
    # persistence -- they serialise run artifacts and Razorpay ids, which is
    # exactly what `runner.write_run` already does.
    deciding = {"base.py", "budget.py", "live_razorpay.py", "simulated.py"}
    package = Path(__file__).resolve().parent.parent / "src" / "recoup" / "executor"
    offenders = []
    for path in sorted(package.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        # Docstrings name these attributes precisely to say they are not read.
        code = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith(("#", "*", '"'))
        )
        banned = (*answer_key, "model_dump") if path.name in deciding else answer_key
        offenders += [f"{path.name}: {name}" for name in banned if f".{name}" in code]
    assert not offenders, f"executor reads simulation ground truth: {offenders}"


# --------------------------------------------------------------------------
# the fake client is a faithful stand-in
# --------------------------------------------------------------------------


def test_the_fake_returns_the_shape_the_real_api_returns() -> None:
    """A fake that returns `{"id": ...}` proves only that we can read our own dict."""
    record = generate_batch(42).records[0]
    client = FakePaymentLinkClient()
    entity = client.create(link_payload(record, 0, run_id="run"))
    for field in (
        "accept_partial",
        "amount",
        "amount_paid",
        "currency",
        "description",
        "id",
        "notes",
        "notify",
        "reference_id",
        "reminder_enable",
        "short_url",
        "status",
        "upi_link",
    ):
        assert field in entity, f"the real payment-link entity carries {field}"
    assert entity["id"].startswith("plink_")
    assert entity["status"] == "created"
    assert entity["notify"] == {"sms": False, "email": False}
    assert client.create(link_payload(record, 0, run_id="run"))["id"] == entity["id"]


def test_the_paid_payload_matches_the_link_it_settles() -> None:
    record = generate_batch(42).records[0]
    entity = FakePaymentLinkClient().create(link_payload(record, 0, run_id="run"))
    event = paid_webhook_payload(entity)
    assert event["event"] == "payment_link.paid"
    link = event["payload"]["payment_link"]["entity"]
    payment = event["payload"]["payment"]["entity"]
    assert link["id"] == entity["id"]
    assert link["status"] == "paid"
    assert payment["amount"] == entity["amount"] == record.outstanding_paise
    assert payment["id"].startswith("pay_")


# --------------------------------------------------------------------------
# a complete live run, written to disk, still replays
# --------------------------------------------------------------------------


def test_a_live_run_writes_a_replayable_run_directory(tmp_path: Path) -> None:
    (outcome, executor), _client = _live_run("ondisk", 2)
    arm_dir = tmp_path / "ondisk" / "agent"
    write_run(outcome.live, generate_batch(42), arm_dir)
    write_session(executor.session, arm_dir)

    rows = read_log(arm_dir / "audit.jsonl")
    verify_chain(rows)
    live_refs = [
        row.action.external_ref
        for row in rows
        if row.action and row.action.executor is ExecutorKind.LIVE
    ]
    assert len(live_refs) == 2
    assert all(ref and ref.startswith("plink_") for ref in live_refs)

    stored = json.loads((arm_dir / "final.json").read_text(encoding="utf-8"))
    assert len(stored) == 126
    assert any(item["state"] == RecordState.PAID.value for item in stored)


# --------------------------------------------------------------------------
# the pre-flight refusal: never spend a capped, irrecoverable resource blind
# --------------------------------------------------------------------------


def _live_run_with(run_id: str, capacity: int, horizon: int, *, require_payable: bool) -> Any:
    client = FakePaymentLinkClient()
    executors: list[LiveRazorpayExecutor] = []

    def build(allocator: LinkAllocator) -> LiveRazorpayExecutor:
        executor = LiveRazorpayExecutor(
            client,
            allocator,
            run_id=run_id,
            arm=Arm.AGENT,
            key_id="rzp_test_offline",
        )
        executors.append(executor)
        return executor

    outcome = run_live_batch(
        generate_batch(42).records,
        DeterministicFallback(),
        seed=42,
        run_id=run_id,
        capacity=capacity,
        executor_factory=build,
        policy_factory=lambda: PolicyEngine(MerchantPolicy(link_budget=None)),
        horizon=horizon,
        require_payable=require_payable,
    )
    return outcome, client


def test_a_spending_run_refuses_before_creating_unpayable_links() -> None:
    """The default horizon settles every funded record, so it must not spend.

    `--ticks` defaults to 112, and at 112 the simulated payer has closed all
    three funded receivables by the time anyone could pay one. Without this
    check a `--confirm` run would create three real links, consume three of a
    capped and irrecoverable 30, and only then report that none was payable.
    """
    with pytest.raises(NoPayableLink) as raised:
        _live_run_with("preflight", 3, 112, require_payable=True)
    assert "shorter --ticks" in str(raised.value)
    assert raised.value.horizon == 112


def test_the_refusal_happens_before_any_link_is_created() -> None:
    """A refusal after the spend would be worthless. Assert the ordering."""
    client = FakePaymentLinkClient()

    def build(allocator: LinkAllocator) -> LiveRazorpayExecutor:
        return LiveRazorpayExecutor(
            client, allocator, run_id="order", arm=Arm.AGENT, key_id="rzp_test_offline"
        )

    with pytest.raises(NoPayableLink):
        run_live_batch(
            generate_batch(42).records,
            DeterministicFallback(),
            seed=42,
            run_id="order",
            capacity=3,
            executor_factory=build,
            policy_factory=lambda: PolicyEngine(MerchantPolicy(link_budget=None)),
            horizon=112,
            require_payable=True,
        )
    assert client.calls == [], "links were created before the run refused to spend"


def test_a_short_horizon_leaves_links_payable_and_is_allowed() -> None:
    """24 ticks closes the book while two of the three funded records are open."""
    outcome, client = _live_run_with("payable", 3, 24, require_payable=True)
    closing = {record.invoice_id: record.state for record in outcome.live.ledger.records}
    funded = [allocation.invoice_id for allocation in outcome.allocator.shortlist]
    payable = [invoice_id for invoice_id in funded if closing[invoice_id] not in TERMINAL]
    assert len(client.calls) == 3
    assert len(payable) == 2


def test_a_rehearsal_is_never_refused() -> None:
    """Costing nothing, it stays useful on any horizon -- it shows the allocation."""
    outcome, client = _live_run_with("rehearse", 3, 112, require_payable=False)
    assert len(client.calls) == 3
    assert len(outcome.allocator.shortlist) == 3
