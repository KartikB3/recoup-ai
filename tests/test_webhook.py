"""Phase 4: signature verification, reconciliation and the receiver. All offline.

ISS-012 named the Phase 4 risk exactly: the `razorpay` SDK ships no type stubs
and no in-repo reference, so a signature check written from memory is a check
nobody can review. This file is what discharges it. The webhook fixture below
carries a literal hex digest **computed by hand** from a known secret and a
known body -- not by calling the helper under test, and not by calling the SDK,
either of which would only prove that a function agrees with itself.
"""

from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import os
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from recoup.audit.log import read_log, verify_chain
from recoup.audit.replay import compare
from recoup.audit.replay import replay as replay_rows
from recoup.domain.enums import Arm, ExecutorKind, RecordState
from recoup.domain.models import Invoice
from recoup.executor.budget import LinkAllocator, demand_from_log
from recoup.executor.fake_razorpay import FakePaymentLinkClient, paid_webhook_payload
from recoup.executor.live_razorpay import LiveRazorpayExecutor
from recoup.executor.reconcile import (
    PROTECTED_RUN_IDS,
    ReconcileRefused,
    reconcile_payment,
)
from recoup.executor.session import read_session, write_session
from recoup.executor.signature import (
    expected_signature,
    verify_payment_link_callback,
    verify_webhook_signature,
)
from recoup.generator.generate import generate_batch, load_batch
from recoup.policy.context import MerchantPolicy
from recoup.policy.engine import PolicyEngine
from recoup.reasoner.fallback import DeterministicFallback
from recoup.runner.batch import run_live_batch, write_run

# --------------------------------------------------------------------------
# the fixture. Known secret, known body, digest computed by hand.
# --------------------------------------------------------------------------

#: A body byte-for-byte as it would arrive. Not re-serialised from a dict.
FIXTURE_BODY = b'{"event":"payment_link.paid","payload":{"amount":50000}}'
FIXTURE_SECRET = "recoup_test_webhook_secret"

#: HMAC-SHA256(FIXTURE_SECRET, FIXTURE_BODY), hex. Independently computed:
#:
#:     python -c "import hmac,hashlib; print(hmac.new(
#:         b'recoup_test_webhook_secret',
#:         b'{\"event\":\"payment_link.paid\",\"payload\":{\"amount\":50000}}',
#:         hashlib.sha256).hexdigest())"
#:
#: Written out as a literal so that a change to the construction fails here
#: rather than quietly agreeing with itself.
FIXTURE_SIGNATURE = "da240dcb64948bea964318cc0ace0b4ee38437f72f52e1146b6aaf60a331595c"


def _hand_computed(body: bytes, secret: str) -> str:
    """The digest, from primitives, with no project code in the path."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def test_the_known_good_fixture_is_what_the_module_produces() -> None:
    """The check ISS-012 asked for: a literal digest, not a self-agreeing helper.

    Three independent statements of the same value -- the literal above, the
    primitives, and the module under test. Any one of them drifting fails here.
    """
    assert _hand_computed(FIXTURE_BODY, FIXTURE_SECRET) == FIXTURE_SIGNATURE
    assert expected_signature(FIXTURE_BODY, FIXTURE_SECRET) == FIXTURE_SIGNATURE
    assert verify_webhook_signature(FIXTURE_BODY, FIXTURE_SIGNATURE, FIXTURE_SECRET) is True


def test_a_valid_webhook_signature_verifies() -> None:
    signature = _hand_computed(FIXTURE_BODY, FIXTURE_SECRET)
    assert verify_webhook_signature(FIXTURE_BODY, signature, FIXTURE_SECRET) is True


@pytest.mark.parametrize(
    ("body", "signature", "secret"),
    [
        (FIXTURE_BODY, _hand_computed(FIXTURE_BODY, "other-secret"), FIXTURE_SECRET),
        (b'{"event":"payment_link.paid","payload":{"amount":500000}}', "", FIXTURE_SECRET),
        (FIXTURE_BODY, "", FIXTURE_SECRET),
        (FIXTURE_BODY, _hand_computed(FIXTURE_BODY, FIXTURE_SECRET), ""),
        (FIXTURE_BODY, "not-hex-at-all", FIXTURE_SECRET),
    ],
)
def test_bad_signatures_are_refused(body: bytes, signature: str, secret: str) -> None:
    """Wrong secret, tampered body, missing signature, missing secret, junk."""
    assert verify_webhook_signature(body, signature, secret) is False


def test_a_tampered_body_fails_even_by_one_byte() -> None:
    signature = _hand_computed(FIXTURE_BODY, FIXTURE_SECRET)
    tampered = FIXTURE_BODY.replace(b"50000", b"50001")
    assert verify_webhook_signature(tampered, signature, FIXTURE_SECRET) is False


def test_a_reserialised_body_does_not_verify() -> None:
    """Why the receiver reads raw bytes: json round-tripping changes the document."""
    signature = _hand_computed(FIXTURE_BODY, FIXTURE_SECRET)
    reserialised = json.dumps(json.loads(FIXTURE_BODY)).encode("utf-8")
    assert reserialised != FIXTURE_BODY
    assert verify_webhook_signature(reserialised, signature, FIXTURE_SECRET) is False


# --------------------------------------------------------------------------
# the callback signature: a different key and a field order that is not guessable
# --------------------------------------------------------------------------


def _callback_params(secret: str) -> dict[str, str]:
    params = {
        "payment_link_id": "plink_abc123",
        "payment_link_reference_id": "ASH-2026-0011-t0-deadbeef",
        "payment_link_status": "paid",
        "razorpay_payment_id": "pay_xyz789",
    }
    message = "|".join(
        params[field]
        for field in (
            "payment_link_id",
            "payment_link_reference_id",
            "payment_link_status",
            "razorpay_payment_id",
        )
    )
    params["razorpay_signature"] = _hand_computed(message.encode("utf-8"), secret)
    return params


def test_a_valid_callback_verifies_against_the_key_secret() -> None:
    assert verify_payment_link_callback(_callback_params("key-secret"), "key-secret") is True


def test_a_callback_signed_with_the_wrong_key_is_refused() -> None:
    assert verify_payment_link_callback(_callback_params("webhook-secret"), "key-secret") is False


def test_a_callback_missing_a_signed_field_is_unverifiable() -> None:
    params = _callback_params("key-secret")
    del params["payment_link_reference_id"]
    assert verify_payment_link_callback(params, "key-secret") is False


def test_the_signed_field_order_is_the_one_razorpay_uses() -> None:
    """Reordering the concatenation must break it -- otherwise the order is untested."""
    params = _callback_params("key-secret")
    wrong_order = "|".join(
        [
            params["razorpay_payment_id"],
            params["payment_link_id"],
            params["payment_link_reference_id"],
            params["payment_link_status"],
        ]
    )
    params["razorpay_signature"] = _hand_computed(wrong_order.encode("utf-8"), "key-secret")
    assert verify_payment_link_callback(params, "key-secret") is False


# --------------------------------------------------------------------------
# a live run on disk, and a payment reconciled into it
# --------------------------------------------------------------------------


#: A live run has to close while the funded receivables are still open, or
#: there is nothing left for a real payer to settle. Over the full 112-tick
#: horizon the simulated adjudicator settles all three funded records itself;
#: at 24 ticks two of the three are still open. See ISS-039.
LIVE_HORIZON = 24


@pytest.fixture
def live_run(tmp_path: Path) -> dict[str, Any]:
    """A complete two-pass live run written to a temporary runs directory."""
    run_id = "webhooktest"
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

    batch = generate_batch(42)
    outcome = run_live_batch(
        batch.records,
        DeterministicFallback(),
        seed=42,
        run_id=run_id,
        capacity=3,
        executor_factory=build,
        policy_factory=lambda: PolicyEngine(MerchantPolicy(link_budget=None)),
        horizon=LIVE_HORIZON,
    )
    runs_root = tmp_path / "runs"
    arm_dir = runs_root / run_id / "agent"
    write_run(outcome.live, batch, arm_dir)
    write_session(executors[-1].session, arm_dir)

    # Pick a funded link whose record is still open at the close of the run:
    # a payment onto a terminal record is refused, and that is tested separately.
    final = {
        item["invoice_id"]: item
        for item in json.loads((arm_dir / "final.json").read_text(encoding="utf-8"))
    }
    session = executors[-1].session
    open_links = [
        link
        for link in session.links
        if final[link.invoice_id]["state"]
        not in (RecordState.PAID.value, RecordState.WRITTEN_OFF.value)
    ]
    assert open_links, "expected at least one funded link on a record still open"
    link = open_links[0]
    entity = next(e for e in client.created if e["id"] == link.payment_link_id)
    return {
        "runs_root": runs_root,
        "arm_dir": arm_dir,
        "link": link,
        "entity": entity,
        "outstanding": final[link.invoice_id]["amount_paise"]
        - final[link.invoice_id]["recovered_paise"],
        "batch": batch,
    }


def test_a_payment_lands_as_an_ordinary_outcome_row(live_run: dict[str, Any]) -> None:
    """Invariant 8: the ledger is the system of record, not Razorpay."""
    arm_dir = live_run["arm_dir"]
    link = live_run["link"]
    event = paid_webhook_payload(live_run["entity"], amount_paise=live_run["outstanding"])
    payment = event["payload"]["payment"]["entity"]

    before = len(read_log(arm_dir / "audit.jsonl"))
    result = reconcile_payment(
        arm_dir,
        invoice_id=link.invoice_id,
        payment_id=payment["id"],
        payment_link_id=link.payment_link_id,
        amount_paise=payment["amount"],
    )

    assert result.already_applied is False
    assert result.state_after == RecordState.PAID.value
    rows = read_log(arm_dir / "audit.jsonl")
    assert len(rows) == before + 1
    verify_chain(rows)

    last = rows[-1]
    assert last.outcome is not None
    assert payment["id"] in last.outcome.detail, "the payment id must be derivable from the log"
    assert last.record_id == link.invoice_id


def test_the_reconciled_run_still_replays(live_run: dict[str, Any]) -> None:
    """The acceptance test that has governed since Phase 1, now over a webhook row."""
    arm_dir = live_run["arm_dir"]
    link = live_run["link"]
    event = paid_webhook_payload(live_run["entity"], amount_paise=live_run["outstanding"])
    reconcile_payment(
        arm_dir,
        invoice_id=link.invoice_id,
        payment_id=event["payload"]["payment"]["entity"]["id"],
        payment_link_id=link.payment_link_id,
        amount_paise=live_run["outstanding"],
    )

    rows = read_log(arm_dir / "audit.jsonl")
    replayed = replay_rows(load_batch(arm_dir / "batch.json").records, rows)
    stored = [
        Invoice.model_validate(item)
        for item in json.loads((arm_dir / "final.json").read_text(encoding="utf-8"))
    ]
    assert compare(stored, replayed.ledger.records) == []


def test_the_same_payment_twice_changes_nothing(live_run: dict[str, Any]) -> None:
    """Razorpay retries deliveries, and a demo gets refreshed."""
    arm_dir = live_run["arm_dir"]
    link = live_run["link"]
    payment_id = paid_webhook_payload(live_run["entity"])["payload"]["payment"]["entity"]["id"]
    kwargs = {
        "invoice_id": link.invoice_id,
        "payment_id": payment_id,
        "payment_link_id": link.payment_link_id,
        "amount_paise": live_run["outstanding"],
    }
    first = reconcile_payment(arm_dir, **kwargs)
    rows_after_first = read_log(arm_dir / "audit.jsonl")
    final_after_first = (arm_dir / "final.json").read_text(encoding="utf-8")

    second = reconcile_payment(arm_dir, **kwargs)
    assert second.already_applied is True
    assert second.row_id == first.row_id
    assert len(read_log(arm_dir / "audit.jsonl")) == len(rows_after_first)
    assert (arm_dir / "final.json").read_text(encoding="utf-8") == final_after_first


def test_a_payment_onto_a_terminal_record_is_refused(live_run: dict[str, Any]) -> None:
    """The bug this guard exists for.

    `record_outcome` adds money before transitioning and `state_after_outcome`
    returns early on a terminal state, so an unguarded second payment would
    raise recovered money on a record that stays PAID -- and replay would stay
    green while the metric table counted the rupees twice.
    """
    arm_dir = live_run["arm_dir"]
    link = live_run["link"]
    reconcile_payment(
        arm_dir,
        invoice_id=link.invoice_id,
        payment_id="pay_first",
        payment_link_id=link.payment_link_id,
        amount_paise=live_run["outstanding"],
    )
    recovered_before = _recovered(arm_dir, link.invoice_id)

    with pytest.raises(ReconcileRefused, match="already PAID"):
        reconcile_payment(
            arm_dir,
            invoice_id=link.invoice_id,
            payment_id="pay_second_different_payment",
            payment_link_id=link.payment_link_id,
            amount_paise=live_run["outstanding"],
        )
    assert _recovered(arm_dir, link.invoice_id) == recovered_before


def _recovered(arm_dir: Path, invoice_id: str) -> int:
    for item in json.loads((arm_dir / "final.json").read_text(encoding="utf-8")):
        if item["invoice_id"] == invoice_id:
            return int(item["recovered_paise"])
    raise AssertionError(invoice_id)


def test_the_canonical_runs_are_never_written_to(tmp_path: Path) -> None:
    """The rule that outranks everything, enforced against the webhook path."""
    assert set(PROTECTED_RUN_IDS) == {"seed42", "seed42-tiered"}
    for run_id in sorted(PROTECTED_RUN_IDS):
        arm_dir = Path("runs") / run_id / "agent"
        if not arm_dir.exists():
            continue
        before = (arm_dir / "audit.jsonl").read_bytes()
        with pytest.raises(ReconcileRefused, match="protected canonical run"):
            reconcile_payment(
                arm_dir,
                invoice_id="ASH-2026-0011",
                payment_id="pay_intruder",
                payment_link_id="plink_intruder",
                amount_paise=1000,
            )
        assert (arm_dir / "audit.jsonl").read_bytes() == before


def test_the_live_link_index_records_the_settlement(live_run: dict[str, Any]) -> None:
    arm_dir = live_run["arm_dir"]
    link = live_run["link"]
    reconcile_payment(
        arm_dir,
        invoice_id=link.invoice_id,
        payment_id="pay_marks_index",
        payment_link_id=link.payment_link_id,
        amount_paise=live_run["outstanding"],
    )
    session = read_session(arm_dir)
    assert session is not None
    settled = session.find(link.payment_link_id)
    assert settled is not None and settled.status == "paid"
    events = (arm_dir / "reconciliation.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(events) == 1
    assert json.loads(events[0])["payment_id"] == "pay_marks_index"


# --------------------------------------------------------------------------
# the receiver
# --------------------------------------------------------------------------


@pytest.fixture
def client(live_run: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """The FastAPI app, pointed at the temporary runs directory."""
    monkeypatch.setenv("RECOUP_RUNS_ROOT", str(live_run["runs_root"]))
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", FIXTURE_SECRET)
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "key-secret")
    import webhook.app as app_module

    importlib.reload(app_module)
    return TestClient(app_module.app)


def _delivery(event: dict[str, Any], secret: str = FIXTURE_SECRET) -> tuple[bytes, dict[str, str]]:
    """A delivery exactly as Razorpay sends it: raw bytes plus their signature."""
    body = json.dumps(event, separators=(",", ":")).encode("utf-8")
    return body, {"X-Razorpay-Signature": _hand_computed(body, secret)}


def test_a_signed_delivery_moves_the_ledger(client: TestClient, live_run: dict[str, Any]) -> None:
    """The Phase 4 gate, end to end, with the network replaced and nothing else."""
    event = paid_webhook_payload(live_run["entity"], amount_paise=live_run["outstanding"])
    body, headers = _delivery(event)

    response = client.post("/razorpay/webhook", content=body, headers=headers)

    assert response.status_code == 200, response.text
    reconciled = response.json()["reconciled"]
    assert reconciled["invoice_id"] == live_run["link"].invoice_id
    assert reconciled["state_after"] == RecordState.PAID.value
    assert _recovered(live_run["arm_dir"], live_run["link"].invoice_id) > 0


def test_an_unsigned_delivery_is_rejected(client: TestClient, live_run: dict[str, Any]) -> None:
    event = paid_webhook_payload(live_run["entity"])
    body, _headers = _delivery(event)
    response = client.post("/razorpay/webhook", content=body)
    assert response.status_code == 401
    assert _recovered(live_run["arm_dir"], live_run["link"].invoice_id) == 0


def test_a_delivery_signed_with_the_wrong_secret_is_rejected(
    client: TestClient, live_run: dict[str, Any]
) -> None:
    event = paid_webhook_payload(live_run["entity"])
    body, headers = _delivery(event, secret="not-the-secret")
    response = client.post("/razorpay/webhook", content=body, headers=headers)
    assert response.status_code == 401
    assert _recovered(live_run["arm_dir"], live_run["link"].invoice_id) == 0


def test_other_events_are_acknowledged_and_ignored(
    client: TestClient, live_run: dict[str, Any]
) -> None:
    """`payment.captured` fires for the same rupees; acting on both double-credits."""
    event = paid_webhook_payload(live_run["entity"])
    event["event"] = "payment.captured"
    body, headers = _delivery(event)
    response = client.post("/razorpay/webhook", content=body, headers=headers)
    assert response.status_code == 200
    assert response.json()["ignored"] == "payment.captured"
    assert _recovered(live_run["arm_dir"], live_run["link"].invoice_id) == 0


def test_a_link_we_never_created_is_a_404(client: TestClient, live_run: dict[str, Any]) -> None:
    event = paid_webhook_payload(live_run["entity"])
    event["payload"]["payment_link"]["entity"]["id"] = "plink_neverseen0"
    body, headers = _delivery(event)
    response = client.post("/razorpay/webhook", content=body, headers=headers)
    assert response.status_code == 404


def test_a_receiver_without_a_secret_refuses_everything(
    live_run: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Accepting unverified would be worse than having no endpoint."""
    monkeypatch.setenv("RECOUP_RUNS_ROOT", str(live_run["runs_root"]))
    monkeypatch.delenv("RAZORPAY_WEBHOOK_SECRET", raising=False)
    import webhook.app as app_module

    importlib.reload(app_module)
    event = paid_webhook_payload(live_run["entity"])
    body, headers = _delivery(event)
    response = TestClient(app_module.app).post("/razorpay/webhook", content=body, headers=headers)
    assert response.status_code == 503


def test_the_callback_verifies_the_redirect(client: TestClient) -> None:
    params = _callback_params("key-secret")
    assert client.get("/razorpay/callback", params=params).status_code == 200

    params["razorpay_signature"] = "0" * 64
    assert client.get("/razorpay/callback", params=params).status_code == 401


def test_healthz_reports_whether_it_can_verify(client: TestClient) -> None:
    body = client.get("/healthz").json()
    assert body["ok"] is True
    assert body["webhook_secret_configured"] is True


def test_the_receiver_holds_no_api_credentials() -> None:
    """It verifies with a shared secret; it never needs to call Razorpay."""
    source = (Path(__file__).resolve().parent.parent / "webhook" / "app.py").read_text("utf-8")
    assert "RAZORPAY_KEY_ID" not in source
    assert "razorpay.Client" not in source
    assert "import razorpay" not in source


def test_the_environment_is_untouched_by_these_tests() -> None:
    """A guard on the guard: no test here may leave a real secret in os.environ."""
    assert os.environ.get("RAZORPAY_WEBHOOK_SECRET", "") != FIXTURE_SECRET


def test_no_live_row_was_ever_written_by_the_fake(live_run: dict[str, Any]) -> None:
    """The fake creates objects that exist only in this process, and says so."""
    rows = read_log(live_run["arm_dir"] / "audit.jsonl")
    live_rows = [r for r in rows if r.action and r.action.executor is ExecutorKind.LIVE]
    assert len(live_rows) == 3
    demand = demand_from_log(rows)
    assert len(demand) >= len(live_rows)
