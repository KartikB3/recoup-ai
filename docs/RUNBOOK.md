# Runbook — the live round trip, then the video

The last two P0 items (ROADMAP #21 and #15). Both need a browser, so both are
manual. Everything below is ordered by **what is still free**: nothing spends a
capped Razorpay link until step 8.

**Budget:** 1 of 30 test-mode Payment Links consumed (ISS-001). The take spends
3, leaving 26 for retries. There is no reason to be stingy — but there is also
no reason to re-run: only **one** of the three links has to be paid to get
`CONTACTED → PAID`. The other two are footage for the allocation beat.

---

## Part A · The live round trip

### Where the configuration actually stands

| | |
|---|---|
| `RAZORPAY_KEY_ID` / `_SECRET` | ✅ set, test key |
| `RAZORPAY_WEBHOOK_SECRET` | ❌ empty — step 5 |
| `RAZORPAY_CALLBACK_BASE_URL` | ❌ still the `.invalid` placeholder — step 5 |
| `cloudflared` / `ngrok` | ❌ neither installed — step 1 |

`ANTHROPIC_API_KEY` is empty and should stay that way. `--cache-only` reads the
committed cache regardless of whether a key is set (ISS-043) and takes the
deterministic fallback on a miss, so the run cannot bill anything.

### 1 · Install a tunnel

```powershell
winget install Cloudflare.cloudflared
```

Quick tunnels need no Cloudflare account. Restart the shell afterwards so the
new `cloudflared` is on `PATH`.

### 2 · Start the receiver (terminal 1)

```bash
uv run recoup webhook
```

It will print a yellow warning that `RAZORPAY_WEBHOOK_SECRET` is not set. **That
warning is not authoritative** — it is emitted by the CLI before uvicorn imports
`webhook/app.py`, which is where `.env` is actually loaded. Step 3 is the check
that counts.

### 3 · Start the tunnel (terminal 2) and prove the inbound path

```bash
cloudflared tunnel --url http://localhost:8000
```

Note the `https://<random-words>.trycloudflare.com` host it prints. Then, from a
third terminal:

```bash
curl https://<host>/healthz
```

Expect `{"ok":true,"runs_root":"runs","webhook_secret_configured":false}`. If
that does not come back, nothing downstream can work and you have found it for
zero links.

> **Do not restart the tunnel after step 5.** A quick-tunnel hostname changes on
> every start, and it lives in *two* places — `.env` and the Razorpay dashboard.
> The `--confirm` preflight catches an unset or `.invalid` callback URL, but a
> **stale-but-well-formed** one sails straight through: the links get created
> and the delivery simply never arrives. If you must restart, update both places
> and re-check `/healthz`.

### 4 · Create the webhook in the Razorpay dashboard

Test mode → Account & Settings → Webhooks → Add New Webhook.

- **URL:** `https://<host>/razorpay/webhook`
- **Secret:** choose one; you will paste it into `.env` next
- **Active event:** `payment_link.paid` — and only that one. `payment.captured`
  also fires for the same payment and the receiver ignores it by design.

### 5 · Fill in `.env`, then restart terminal 1

```
RAZORPAY_WEBHOOK_SECRET=<the secret you just chose>
RAZORPAY_CALLBACK_BASE_URL=https://<host>
```

`webhook/app.py` loads `.env` at import, so the running receiver will not pick
this up. Stop it, start it again, and re-check:

```bash
curl https://<host>/healthz     # webhook_secret_configured must now be true
```

### 6 · Prove the signed path end to end, without Razorpay and without a link

Do not wait for a real event to test this. The webhook UI has no dependable
test-send, and its delivery log has nothing to redeliver until step 8 has
already spent the links — which is exactly backwards. Sign a payload yourself
instead: `verify_webhook_signature` is a hex HMAC-SHA256 over the raw body with
the shared secret, so the receiver cannot tell your probe from Razorpay's.

Save this as `probe.py` **outside the repo** and run it with the tunnel host:

```python
import hashlib, hmac, json, sys, urllib.request
from dotenv import dotenv_values

# Read the secret from .env rather than the command line, so it stays out of
# shell history and off camera.
secret = dotenv_values(".env")["RAZORPAY_WEBHOOK_SECRET"]
body = json.dumps({
    "event": "payment_link.paid",
    "created_at": 0,
    "payload": {
        "payment_link": {"entity": {"id": "plink_probe_not_a_real_link"}},
        "payment": {"entity": {"id": "pay_probe", "amount": 1}},
    },
}).encode()
req = urllib.request.Request(
    sys.argv[1].rstrip("/") + "/razorpay/webhook",
    data=body,
    headers={
        "Content-Type": "application/json",
        "X-Razorpay-Signature": hmac.new(
            secret.encode(), body, hashlib.sha256
        ).hexdigest(),
    },
)
try:
    with urllib.request.urlopen(req) as r:
        print(r.status, r.read().decode())
except urllib.error.HTTPError as e:
    print(e.code, e.read().decode())
```

```bash
uv run python probe.py https://<host>
```

Two outcomes, and they mean opposite things:

- **`404 no run under runs created payment link plink_probe_not_a_real_link`** —
  this is the **pass**. Signature verification succeeded and reconciliation
  correctly refused a link no run created. Tunnel, secret and signature path are
  all proved.
- **`401 signature verification failed`** — the secret in `.env` and the secret
  in the dashboard disagree, or terminal 1 was not restarted after step 5. Fix
  it before step 8.
- **`503`** — the receiver has no secret at all. Step 5 did not take.

Both responses above were confirmed against this receiver offline; they are the
literal strings it returns.

### 7 · Rehearse once more, now that the callback URL is real

```bash
uv run recoup run --seed 42 --arm agent --ticks 16 --cache-only \
                  --executor live --live-budget 3 --run-id live-rehearsal-2
```

The earlier rehearsals ran with the placeholder callback, so this is the first
one that exercises real `callback_url` construction. Costs nothing. Confirm:

```bash
python -c "import json;print(json.load(open('runs/live-rehearsal-2/agent/summary.json'))['live_mode'])"
# rehearsal
```

Expect three rows — `ASH-2026-0011` and `ASH-2026-0035` marked **`payable`**,
`ASH-2026-0051` marked `settled`. That allocation was confirmed with a
real-shaped callback base set, so a working tunnel URL does not change it; only
the `plink_` ids differ between runs, because the fake derives them from the
run id. **Do not pay the `settled` link** — the simulation already closed that
record and the receiver will correctly refuse the delivery (ISS-039).

### 8 · The take

```bash
uv run recoup run --seed 42 --arm agent --ticks 16 --cache-only \
                  --executor live --live-budget 3 --run-id live-demo --confirm
```

Three real objects. The preflight runs **before** anything is created and
refuses outright if the callback base is missing or a placeholder, or if no
funded record would still be open at the horizon.

`--run-id` must be fresh on every attempt: link reference ids are deterministic
in `(run_id, invoice_id, tick)` and unique per Razorpay account, so a re-run of
`live-demo` is rejected by the API rather than by us.

### 9 · Pay one, watch it land

Open the `short_url` of a row printed as **`payable`** — never the `settled`
one. Pay on the mock page with a card from Razorpay's own test-card list, which
the checkout page surfaces. Take the number from there rather than from memory:
a declined card mid-beat is expensive here in a way it is nowhere else, and the
link is spent either way.

Two things then happen, and only one of them moves the ledger:

- the browser lands on `/razorpay/callback`, which verifies the four-field
  signature and renders a banner. **This is cosmetic.**
- the signed `payment_link.paid` webhook arrives at terminal 1 and reconciles.
  **This is the one that counts.**

### 10 · Prove it

```bash
uv run recoup replay live-demo/agent
python -c "import json;print(json.load(open('runs/live-demo/agent/summary.json'))['live_mode'])"
# confirmed
```

The record should be `PAID`, and the outcome should be a *new appended row*, not
an edit.

### If the tunnel dies after the links exist

Do not re-run — the links are already spent. Copy the delivery payload out of
the Razorpay dashboard's webhook delivery log into a file and apply it offline:

```bash
uv run recoup reconcile payload.json
```

Same reconciliation, no network. Worth confirming *before* step 8 that your
dashboard actually exposes a failed delivery's request body, since that is what
makes this escape hatch viable.

---

## Part B · The video

Narration, beat order and the re-verify commands are in
[`VIDEO-SCRIPT.md`](VIDEO-SCRIPT.md). This is only the shooting order, which is
**not** the same thing.

### The one rule

**The live round trip is the only one-shot beat.** Every other beat reads from
committed artifacts and is reproducible on demand. So do not attempt a single
continuous take — record in pieces and cut them together.

### Shooting order

1. **The live beat first**, while the tunnel is verified and terminal 1 is
   confirmed receiving. This is Part A steps 8–10 with the recorder already
   rolling. Keep rolling through the replay.
2. **The dashboard beats** (0:00–3:00) — portfolio summary, the payer timeline
   on `ASH-2026-0012`, the veto dot and the rule provenance card. No time
   pressure, re-take freely.
3. **The stopping beat** (3:00–3:40) — run selector to `seed42-t224`.
4. **The closing limitations beat** (4:20–5:00).
5. Assemble in script order.

### Pre-flight

```bash
uv run recoup run --seed 42 --arm all --no-model
uv run recoup run --seed 42 --arm all --cache-only --run-id seed42-tiered
uv run recoup run --seed 42 --arm all --no-model --ticks 224 --run-id seed42-t224
uv run recoup dashboard
```

Browser at 100% zoom, window 1440 wide (the dashboard caps at 1340). Type
`--arm all`, never `--arm both` (OBS-007).

### Keep off camera

- `.env`, in any editor or `cat`
- `check-razorpay` output — it prints the key id
- the Razorpay dashboard's API Keys page
- the webhook secret field

### The beat that is only true after Part A

The 3:40 narration says a real Razorpay Payment Link was created and paid. If
you shoot before the confirmed run, hold that beat back. Until step 8 has
actually happened the honest phrasing everywhere is **"built and verified
offline"**.

---

## Part C · After the confirmed run, before submitting

- [ ] `docs/ISSUES.md` **ISS-001** running total: 1 → 4 of 30. It is the only
      running total in the project.
- [ ] `README.md` — the *Status:* paragraph under **Running the live loop**
      flips from "has not been recorded yet" to what actually happened.
- [ ] `docs/SUBMISSION.md` — the "do not claim a real payment has been
      reconciled" note under *Notes for whoever fills the form* is removed, and
      field 4 gets the video URL.
- [ ] Commit `runs/live-demo/` — it is the evidence, and it will be the only run
      artifact in the repository whose `summary.json` says
      `live_mode: confirmed`.
- [ ] `docs/ROADMAP.md` — #21 and #15 move to done; P1 #5 closes with them.
- [ ] `docs/BUILD-LOG.md` — the round trip is Phase 4's outstanding gate
      evidence.
- [ ] **Last, after every other doc edit:** re-check the entry count quoted at
      the end of `docs/SUBMISSION.md` field 5 against
      `grep -c "^### ISS-" docs/ISSUES.md` minus one (ISS-012 carries a second
      header for its Phase 4 resolution). The live run will add at least one
      entry, and that sentence is in the graded field.
