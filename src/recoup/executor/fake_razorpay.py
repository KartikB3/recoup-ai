"""A Razorpay payment-link client that never touches the network. Phase 4.

Everything in the live slice except the final verification is developed and
tested against this: the allocator, the executor, the audit rows, the session
index, the webhook and the reconciliation. Those tests then run in CI, offline,
forever, and they cost none of the 30 test-mode links (ISS-001).

The response shape is the real one
----------------------------------
Field for field, including the fields Recoup does not read. That is the whole
value of a fake: if it returned `{"id": ...}` it would prove only that the code
can read a dict it invented. `_read_link` on the live executor validates the
same boundary either way, and `notify`, `reminder_enable` and `notes` come back
echoed exactly as the API echoes them -- so a test can assert that nothing was
notified, which is a property that matters and would otherwise be untested
until a real payer's inbox proved it.

Ids are deterministic, derived from the reference id, so a fake run is
reproducible and its audit rows are stable across machines. Real ids are opaque
and random; nothing in the system relies on their shape beyond the `plink_`
prefix that `_read_link` checks for.
"""

from __future__ import annotations

import hashlib
from typing import Any

#: Razorpay ids are 14 characters after the prefix.
_ID_CHARS = 14


def _deterministic_id(prefix: str, seed: str) -> str:
    """A stable, correctly-shaped fake id for a given input."""
    digest = hashlib.blake2b(seed.encode("utf-8"), digest_size=16).hexdigest()
    return f"{prefix}{digest[:_ID_CHARS]}"


class FakePaymentLinkClient:
    """Satisfies `PaymentLinkClient`. Records every call instead of making one."""

    def __init__(self, *, fail_with: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.created: list[dict[str, Any]] = []
        self._fail_with = fail_with

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Return the entity Razorpay would return, without asking Razorpay.

        `fail_with` makes the API-failure path testable: the runner must log a
        row that does not claim a contact was made, and that behaviour needs a
        test as much as the happy path does.
        """
        self.calls.append(data)
        if self._fail_with is not None:
            raise self._fail_with

        reference = str(data.get("reference_id") or "")
        link_id = _deterministic_id("plink_", reference)
        entity: dict[str, Any] = {
            "accept_partial": False,
            "amount": data["amount"],
            "amount_paid": 0,
            "cancelled_at": 0,
            "created_at": 0,
            "currency": data.get("currency", "INR"),
            "customer": {},
            "description": data.get("description", ""),
            "expire_by": 0,
            "expired_at": 0,
            "first_min_partial_amount": 0,
            "id": link_id,
            "notes": dict(data.get("notes", {})),
            "notify": dict(data.get("notify", {})),
            "payments": None,
            "reference_id": reference,
            "reminder_enable": bool(data.get("reminder_enable", False)),
            "reminders": [],
            "short_url": f"https://rzp.io/i/{link_id[-10:]}",
            "status": "created",
            "updated_at": 0,
            "upi_link": False,
            "user_id": "",
        }
        if "callback_url" in data:
            entity["callback_url"] = data["callback_url"]
            entity["callback_method"] = data.get("callback_method", "get")
        self.created.append(entity)
        return entity


def paid_webhook_payload(
    entity: dict[str, Any],
    *,
    payment_id: str | None = None,
    amount_paise: int | None = None,
) -> dict[str, Any]:
    """Build the `payment_link.paid` event Razorpay sends for a created link.

    Lives here rather than in the tests because the webhook handler, the
    reconciliation and the replay-a-saved-payload CLI all need the same shape,
    and a payload invented three times is a payload that agrees with itself and
    nothing else.
    """
    paid = entity["amount"] if amount_paise is None else amount_paise
    payment = _deterministic_id("pay_", payment_id or entity["id"])
    return {
        "entity": "event",
        "account_id": "acc_TESTACCOUNT00",
        "event": "payment_link.paid",
        "contains": ["payment_link", "payment"],
        "payload": {
            "payment_link": {
                "entity": {
                    **entity,
                    "amount_paid": paid,
                    "status": "paid",
                }
            },
            "payment": {
                "entity": {
                    "id": payment,
                    "entity": "payment",
                    "amount": paid,
                    "currency": entity.get("currency", "INR"),
                    "status": "captured",
                    "method": "card",
                    "captured": True,
                    "notes": dict(entity.get("notes", {})),
                }
            },
        },
        "created_at": 0,
    }
