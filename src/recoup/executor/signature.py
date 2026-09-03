"""Razorpay signature verification. Phase 4. The one place correctness is absolute.

Two different signatures, two different constructions, and getting either wrong
is the difference between a receiver and an open endpoint that credits invoices
on request.

**Webhook.** `X-Razorpay-Signature` is HMAC-SHA256 of the RAW REQUEST BODY under
the webhook secret, hex-encoded. Raw bytes, not a re-serialised parse: JSON
round-tripping reorders keys and respaces separators, and the resulting
signature check passes in a test that built the body itself and fails against
every real delivery. `webhook/app.py` reads `await request.body()` for exactly
this reason.

**Payment-link callback.** The browser is redirected back with query parameters
and the signature is HMAC-SHA256 of

    payment_link_id|payment_link_reference_id|payment_link_status|razorpay_payment_id

under the **API key secret** -- a different key from the webhook's, and a field
order that is not guessable. Both constructions here were read out of the
installed SDK (`razorpay/utility/utility.py`) rather than recalled, because the
SDK ships no type stubs and no in-repo reference (ISS-012).

Why this reimplements what the SDK already does
-----------------------------------------------
So that it can be tested against a fixture whose expected signature is computed
by hand rather than by the same helper under test -- a test that calls
`client.utility.verify_webhook_signature` to check `verify_webhook_signature`
asserts that the SDK agrees with itself. `tests/test_webhook.py` carries a
known secret, a known body and a literal hex digest, and this module has to
produce that digest. It is also the only way the receiver can verify without
constructing a `razorpay.Client`, which would require API credentials the
webhook process has no business holding.

Both functions compare with `hmac.compare_digest` and both return a bool. A
missing signature is a failure, never an exemption.
"""

from __future__ import annotations

import hmac
from collections.abc import Mapping
from hashlib import sha256

#: The field order Razorpay signs for a payment-link callback. Not alphabetical,
#: not the order they arrive in the query string. Read from the SDK.
CALLBACK_FIELDS = (
    "payment_link_id",
    "payment_link_reference_id",
    "payment_link_status",
    "razorpay_payment_id",
)


def expected_signature(payload: bytes, secret: str) -> str:
    """The hex HMAC-SHA256 Razorpay would send for this payload and secret."""
    return hmac.new(secret.encode("utf-8"), payload, sha256).hexdigest()


def verify_webhook_signature(body: bytes, signature: str, secret: str) -> bool:
    """Whether `signature` authenticates this exact request body.

    `body` is the bytes as received. Anything that has been through
    `json.loads` and back is a different document with a different signature.
    """
    if not signature or not secret:
        return False
    return hmac.compare_digest(expected_signature(body, secret), signature)


def verify_payment_link_callback(params: Mapping[str, str], key_secret: str) -> bool:
    """Whether a payment-link redirect really came from Razorpay.

    Signed with the API key secret, over the four fields in `CALLBACK_FIELDS`
    joined by `|`. A callback missing any of them is unverifiable and therefore
    unverified -- there is no partial credit here.
    """
    signature = params.get("razorpay_signature", "")
    if not signature or not key_secret:
        return False
    if any(field not in params for field in CALLBACK_FIELDS):
        return False
    message = "|".join(str(params[field]) for field in CALLBACK_FIELDS)
    return hmac.compare_digest(
        expected_signature(message.encode("utf-8"), key_secret),
        signature,
    )
