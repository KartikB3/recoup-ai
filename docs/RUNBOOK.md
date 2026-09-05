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

### 6 · Exercise the signed path without spending a link (if the dashboard offers it)

If the webhook UI has a test-send, or a redelivery on an earlier event, use it.
Read the response you get back, because the two failure shapes mean different
things:

- **401 `signature verification failed`** — the secret in `.env` and the secret
  in the dashboard disagree. Fix it before step 8.
- **A refusal that names the payment link** — signature verification *passed*
  and reconciliation could not find a session for that link id. Expected for a
  synthetic payload, and it is the result you want here.

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

Expect three rows: two `payable`, one `settled`. The `settled` one is a record
the simulation already closed — **do not pay that link**, the receiver will
correctly refuse it (ISS-039).

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

Open the `short_url` of a row printed as **`payable`**. Pay on the mock page
with a test card — the page lists them; `4111 1111 1111 1111` with any future
expiry and any CVV is the standard success card.

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
