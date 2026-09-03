"""Razorpay webhook receiver. Phase 4. FastAPI, single file, deliberately thin.

Run it behind a tunnel:

    recoup webhook --port 8000
    cloudflared tunnel --url http://localhost:8000

then point a Razorpay dashboard webhook at `<tunnel>/razorpay/webhook` for the
`payment_link.paid` event, and set `RAZORPAY_WEBHOOK_SECRET` to the secret you
chose there.

Kept out of the dashboard process on purpose (IMPLEMENTATION-PLAN section 0),
and kept thin on purpose: everything with a rule in it -- signature
verification, the ledger reconciliation, the protected-run refusal -- lives in
`recoup.executor.signature` and `recoup.executor.reconcile`, which are inside
`src/` where mypy strict and the test suite reach. This file is transport.

Three endpoints:

  POST /razorpay/webhook   the asynchronous half. Verifies, reconciles, replies.
  GET  /razorpay/callback  the synchronous half. Where the payer's browser is
                           returned to after paying; verifies the redirect
                           signature and renders the result. It does NOT
                           reconcile -- a browser redirect is not a payment
                           confirmation, it is a user's browser making a claim,
                           and the webhook is the authenticated channel.
  GET  /healthz            is the tunnel up.

Status codes are the honest ones. A bad signature is 401. A payment for a link
this installation never created is 404. A payment the ledger refuses -- onto a
terminal record, or into a protected run -- is 409 with the reason, because
returning 200 to something that did not happen is how a demo silently lies.
"""

from __future__ import annotations

import html
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse

# `src/` is on the path when installed (`uv sync` installs the package), and
# this makes the receiver runnable straight from a checkout as well.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from recoup.executor.reconcile import (
    ReconcileRefused,
    reconcile_payment,
)
from recoup.executor.session import find_link
from recoup.executor.signature import (
    verify_payment_link_callback,
    verify_webhook_signature,
)

load_dotenv()

#: Where live-link session files are looked up. One env var so a demo can point
#: the receiver at a scratch runs directory without editing code.
RUNS_ROOT = Path(os.environ.get("RECOUP_RUNS_ROOT", "runs"))

#: The only event this receiver acts on. `payment.captured` also fires for the
#: same rupees and acting on both would double-credit the invoice.
HANDLED_EVENT = "payment_link.paid"

app = FastAPI(
    title="Recoup webhook receiver",
    description="Reconciles Razorpay test-mode payment events into the Recoup ledger.",
)


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    """Liveness, and whether this process is actually able to verify anything."""
    return {
        "ok": True,
        "runs_root": str(RUNS_ROOT),
        "webhook_secret_configured": bool(os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")),
    }


@app.post("/razorpay/webhook")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(default=""),
) -> JSONResponse:
    """Verify, then reconcile one `payment_link.paid` event into the ledger."""
    secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")
    if not secret:
        # Refuse rather than accept unverified. An endpoint that credits
        # invoices on unauthenticated request is worse than no endpoint.
        return JSONResponse(
            status_code=503,
            content={"error": "RAZORPAY_WEBHOOK_SECRET is not set; nothing can be verified"},
        )

    # RAW bytes. A re-serialised parse has a different signature. See
    # `recoup.executor.signature`.
    body = await request.body()
    if not verify_webhook_signature(body, x_razorpay_signature, secret):
        return JSONResponse(status_code=401, content={"error": "signature verification failed"})

    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"error": "body is not JSON"})

    name = event.get("event", "")
    if name != HANDLED_EVENT:
        return JSONResponse(
            status_code=200,
            content={"ignored": name, "reason": f"only {HANDLED_EVENT} is acted on"},
        )

    payload = event.get("payload", {})
    link_entity = payload.get("payment_link", {}).get("entity", {})
    payment_entity = payload.get("payment", {}).get("entity", {})
    payment_link_id = str(link_entity.get("id", ""))
    payment_id = str(payment_entity.get("id", ""))
    amount_paise = int(payment_entity.get("amount") or link_entity.get("amount_paid") or 0)

    located = find_link(RUNS_ROOT, payment_link_id)
    if located is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"no run under {RUNS_ROOT} created payment link {payment_link_id}"},
        )
    arm_dir, _session, link = located

    try:
        result = reconcile_payment(
            arm_dir,
            invoice_id=link.invoice_id,
            payment_id=payment_id,
            payment_link_id=payment_link_id,
            amount_paise=amount_paise,
            received_at=str(event.get("created_at", "")),
        )
    except ReconcileRefused as exc:
        return JSONResponse(status_code=409, content={"error": str(exc)})

    return JSONResponse(status_code=200, content={"reconciled": result.as_dict()})


@app.get("/razorpay/callback")
def razorpay_callback(request: Request) -> HTMLResponse:
    """The synchronous half: where the payer's browser lands after paying.

    Verified with the API key secret over the four-field construction Razorpay
    signs (`recoup.executor.signature`). Verification is the whole point of the
    endpoint -- the ledger is moved by the webhook, not by whatever a browser
    arrives claiming.
    """
    params = dict(request.query_params)
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "")
    verified = verify_payment_link_callback(params, key_secret)
    # Escaped: these are query parameters, so they are attacker-controlled text
    # being written into a page. The stakes are low on a demo callback and the
    # habit is not optional.
    status = html.escape(params.get("payment_link_status", "unknown"))
    payment_id = html.escape(params.get("razorpay_payment_id", ""))
    banner = "signature verified" if verified else "SIGNATURE NOT VERIFIED"
    return HTMLResponse(
        status_code=200 if verified else 401,
        content=(
            "<!doctype html><meta charset='utf-8'>"
            "<title>Recoup - payment callback</title>"
            "<body style='font-family:system-ui;max-width:40rem;margin:4rem auto'>"
            f"<h1>Payment {status}</h1>"
            f"<p><strong>{banner}</strong></p>"
            f"<p>Razorpay payment id: <code>{payment_id}</code></p>"
            "<p>The ledger is moved by the verified webhook, not by this redirect. "
            "This page confirms the round trip closed in the browser.</p>"
            "</body>"
        ),
    )
