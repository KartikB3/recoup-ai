"""Recoup command-line surface.

Phase 0 defines the command contract; later phases fill in the implementations.
Every command here is referenced by a gate in docs/IMPLEMENTATION-PLAN.md, so
the signatures are the thing being frozen, not the bodies.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    # Type-only. Every command imports what it needs inside its own body so
    # that `recoup --help` does not pay for pydantic, pandas and the rest.
    from recoup.executor.budget import LinkAllocator
    from recoup.generator.generate import Batch
    from recoup.runner.batch import BatchReasoner, Proposer, RunResult

#: A run id becomes a directory name, so it may not traverse or escape `runs/`.
_SAFE_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Autonomous receivables recovery: the LLM proposes, the policy engine disposes.",
)

DEFAULT_SEED = 42
DEFAULT_COUNT = 126
DEFAULT_TICKS = 112  # 1 tick = 6 virtual hours -> 28 virtual days

#: Committed JSON artifacts end with one newline, like every other run file.
NEWLINE = "\n"


class Arm(StrEnum):
    """Which recovery strategy runs against the batch."""

    agent = "agent"
    baseline = "baseline"
    policy_baseline = "policy-baseline"
    control = "control"
    both = "both"
    all = "all"


class ExecutorMode(StrEnum):
    """Where interventions actually land."""

    simulated = "simulated"
    live = "live"


def _not_yet(phase: int, what: str) -> None:
    """Fail loudly and usefully for a command whose phase has not landed yet."""
    typer.secho(
        f"{what} lands in Phase {phase}. See docs/IMPLEMENTATION-PLAN.md and docs/ROADMAP.md.",
        fg=typer.colors.YELLOW,
        err=True,
    )
    raise typer.Exit(code=1)


def _canonical(value: object) -> str:
    """Canonical JSON for a committed artifact. Same serialiser as the run files."""
    from recoup.domain.models import canonical_json

    return canonical_json(value)


def _console_safe(text: str) -> str:
    """Keep UTF-8 artifacts rich while remaining printable on CP-1252 Windows."""
    return text.replace("₹", "Rs")


@app.command()
def generate(
    seed: int = typer.Option(DEFAULT_SEED, help="RNG seed. Same seed, byte-identical batch."),
    count: int = typer.Option(
        DEFAULT_COUNT, min=120, help="Number of records. Published seed-42 book is 126."
    ),
    out: Path = typer.Option(Path("data/batches"), help="Output directory."),
) -> None:
    """Generate a seeded, reproducible invoice batch. (Phase 1)"""
    from recoup.generator.generate import generate_batch, write_batch

    batch = generate_batch(seed=seed, count=count)
    path, digest = write_batch(batch, out)
    typer.secho(f"wrote {len(batch.records)} records to {path}", fg=typer.colors.GREEN)
    typer.echo(f"sha256 {digest}")
    typer.echo(
        f"cluster {batch.meta.parent_group_id}: "
        f"{len(batch.meta.cluster_invoice_ids)} records, "
        f"quiet {batch.meta.quiet_window[0]} to {batch.meta.quiet_window[1]}"
    )
    typer.echo(f"spotlight {batch.meta.spotlight_invoice_id}")


def _run_live_agent_arm(
    batch: Batch,
    proposer: Proposer,
    *,
    batch_reasoner: BatchReasoner | None,
    seed: int,
    run_id: str,
    ticks: int,
    capacity: int,
    arm_dir: Path,
    confirm: bool,
) -> RunResult:
    """Drive the two-pass live agent arm and report where the budget went.

    Without `--confirm` the second pass runs against the fake client. That is
    not a stub of the live path -- it IS the live path, with one object swapped
    at the boundary, so the allocation, the session index, the audit rows and
    the reconciliation are all exercised for free before a single one of the 30
    test-mode links (ISS-001) is spent.
    """
    import os

    from recoup.domain.enums import Arm as DomainArm
    from recoup.executor.fake_razorpay import FakePaymentLinkClient
    from recoup.executor.live_razorpay import (
        LiveRazorpayExecutor,
        PaymentLinkClient,
        RazorpayPaymentLinkClient,
    )
    from recoup.executor.session import write_session
    from recoup.ledger.ledger import is_terminal
    from recoup.policy.context import MerchantPolicy
    from recoup.policy.engine import PolicyEngine
    from recoup.runner.batch import NoPayableLink, run_live_batch

    key_id = os.environ.get("RAZORPAY_KEY_ID", "")
    callback_base = os.environ.get("RAZORPAY_CALLBACK_BASE_URL", "").rstrip("/")
    callback_url = f"{callback_base}/razorpay/callback" if callback_base else None

    client: PaymentLinkClient
    if confirm:
        # Checked before a link exists. `.invalid` is the reserved never-resolves
        # TLD that `.env.example` ships as a placeholder, so an unconfigured
        # tunnel would either have the create rejected or send the payer's
        # browser to a dead host after paying -- and the links are gone either
        # way. Refusing costs nothing; discovering it costs three of thirty.
        if not callback_base or ".invalid" in callback_base:
            typer.secho(
                "RAZORPAY_CALLBACK_BASE_URL is "
                f"{'not set' if not callback_base else 'still the placeholder'}, so the payer "
                "would be redirected nowhere after paying. Start a tunnel "
                "(cloudflared tunnel --url http://localhost:8000) and set it to that URL "
                "before spending real links.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)
        try:
            real = RazorpayPaymentLinkClient(key_id, os.environ.get("RAZORPAY_KEY_SECRET", ""))
        except ValueError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from exc
        client = real
        typer.secho(
            f"LIVE mode on {key_id}: up to {capacity} real test-mode payment links may be "
            "created, once the pre-flight checks pass.",
            fg=typer.colors.YELLOW,
        )
    else:
        client = FakePaymentLinkClient()
        key_id = key_id or "rzp_test_rehearsal"
        typer.secho(
            f"live path REHEARSAL against the fake client; up to {capacity} links would be "
            "created. Re-run with --confirm to make them real.",
            fg=typer.colors.CYAN,
        )

    executors: list[LiveRazorpayExecutor] = []

    def build(allocator: LinkAllocator) -> LiveRazorpayExecutor:
        executor = LiveRazorpayExecutor(
            client,
            allocator,
            run_id=run_id,
            arm=DomainArm.AGENT,
            key_id=key_id,
            callback_url=callback_url,
        )
        executors.append(executor)
        return executor

    try:
        outcome = run_live_batch(
            batch.records,
            proposer,
            seed=seed,
            run_id=run_id,
            capacity=capacity,
            executor_factory=build,
            policy_factory=lambda: PolicyEngine(MerchantPolicy(link_budget=None)),
            horizon=ticks,
            batch_reasoner=batch_reasoner,
            # Only a spending run refuses. A rehearsal is still worth running on
            # a long horizon -- it shows the allocation -- and costs nothing.
            require_payable=confirm,
            # The audit rows of a rehearsal and a confirmed run are
            # indistinguishable by construction (OBS-012), so the marker that
            # says whether these `plink_` ids exist at Razorpay has to be
            # written by the run itself, at the moment it knows.
            live_mode="confirmed" if confirm else "rehearsal",
        )
    except NoPayableLink as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        typer.secho("no links were created.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    executor = executors[-1]
    arm_dir.mkdir(parents=True, exist_ok=True)
    write_session(executor.session, arm_dir)
    (arm_dir / "link-allocation.json").write_text(
        _canonical(outcome.allocator.report()) + NEWLINE, encoding="utf-8", newline=""
    )

    granted = len(executor.session.links)
    typer.secho(
        f"live links: {granted} created of a {capacity} budget, "
        f"allocated across {outcome.allocator.demand_size} records that requested one.",
        fg=typer.colors.GREEN,
    )

    # Which of them a human can actually settle. A record the simulated payer
    # already resolved is closed, and a webhook for it is refused -- correctly,
    # because the rupees are already in the ledger. Over a full 112-tick
    # horizon that is ALL of them; the round trip needs a run that closes while
    # the funded receivables are still open. See ISS-039.
    closing = {record.invoice_id: record.state for record in outcome.live.ledger.records}
    payable = [link for link in executor.session.links if not is_terminal(closing[link.invoice_id])]
    for link in executor.session.links:
        state = closing[link.invoice_id]
        mark = "payable " if not is_terminal(state) else "settled  "
        typer.echo(
            f"  {mark} {link.invoice_id}  tick {link.tick}  closed {state}  "
            f"{link.payment_link_id}  {link.short_url}"
        )
    if not payable and granted:
        typer.secho(
            "none of these links is payable: every funded record was resolved inside the run, "
            f"so a webhook for any of them is refused. Re-run with a shorter --ticks "
            f"(the current run is {ticks}) to close the book while they are still open.",
            fg=typer.colors.YELLOW,
        )
    for failure in executor.failures:
        typer.secho(f"  live call FAILED, row logged as simulated: {failure}", fg=typer.colors.RED)
    if executor.failures and not granted:
        # `reference_id` is deterministic in (run_id, invoice_id, tick) and
        # Razorpay requires it unique per account, so re-running a spending
        # attempt under a run id that already reached the API collides on every
        # create. No budget is burned -- a unit is committed only once an object
        # exists -- but the retry produces nothing until the id changes.
        typer.secho(
            "every live call failed. If this run id has been confirmed before, its "
            "reference ids already exist at Razorpay: retry with a fresh --run-id.",
            fg=typer.colors.RED,
        )
    if confirm and granted:
        typer.secho(
            f"{granted} unit(s) of the 30-link test-mode budget consumed. "
            "Update the running total in docs/ISSUES.md ISS-001.",
            fg=typer.colors.YELLOW,
        )
    return outcome.live


@app.command()
def run(
    seed: int = typer.Option(DEFAULT_SEED, help="RNG seed. Both arms must share it."),
    arm: Arm = typer.Option(Arm.both, help="Which arm(s) to run."),
    ticks: int = typer.Option(DEFAULT_TICKS, help="Virtual ticks to advance."),
    executor: ExecutorMode = typer.Option(ExecutorMode.simulated, help="Execution mode."),
    live_budget: int = typer.Option(30, help="Payment-link budget. Test mode caps at 30."),
    cache_only: bool = typer.Option(
        False,
        "--cache-only",
        help="Never call the API. Cache misses take the deterministic fallback.",
    ),
    max_api_calls: int | None = typer.Option(
        None, help="Hard ceiling on model calls this run. Spend guard; unset means no ceiling."
    ),
    no_model: bool = typer.Option(
        False,
        "--no-model",
        help="Deterministic fallback only: no cache reads, no API calls. Reproduces runs/seed42.",
    ),
    run_id: str | None = typer.Option(
        None, help="Override the run directory name. Use it to avoid overwriting canonical runs."
    ),
    confirm: bool = typer.Option(
        False,
        "--confirm",
        help="With --executor live, create REAL payment links. Without it, live mode "
        "rehearses the whole path against the fake client and spends nothing.",
    ),
) -> None:
    """Run the batch end to end and write runs/<id>/. (Phases 2-4)

    A cached structured reasoner drives the agent when a key is configured;
    missing/empty credentials and any model failure preserve the exact
    deterministic Phase 2 fallback.

    `--executor live` puts the agent arm's most valuable payment links through
    the real Razorpay test-mode API. It runs the arm twice: once simulated, to
    reveal which records actually ask for a link, and once for real, spending
    the capped budget on the largest of those requests (ISS-001). Without
    `--confirm` the second pass uses the fake client, which exercises every
    line of the live path and costs nothing.
    """
    from dotenv import load_dotenv

    from recoup.baseline.naive_chaser import NaiveChaser, PolicyNaiveChaser
    from recoup.domain.enums import Arm as DomainArm
    from recoup.generator.generate import generate_batch
    from recoup.metrics.compute import compute_metrics
    from recoup.metrics.report import write_reports
    from recoup.policy.context import MerchantPolicy
    from recoup.policy.engine import PolicyEngine
    from recoup.reasoner.batch_insight import DeterministicBatchFallback
    from recoup.reasoner.client import ClaudeReasoner
    from recoup.reasoner.fallback import DeterministicFallback
    from recoup.runner.batch import (
        AlwaysWait,
        PolicyGate,
        run_batch,
        write_run,
    )

    live = executor is ExecutorMode.live
    if live and arm not in (Arm.agent, Arm.both, Arm.all):
        typer.secho(
            f"--executor live applies to the agent arm; {arm.value} has no live half.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    if live and run_id is None:
        # A live run rewrites its directory and creates real objects. It does
        # not get to default onto the canonical run id.
        typer.secho(
            "--executor live requires an explicit --run-id so no canonical run is overwritten.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    selected: tuple[DomainArm, ...]
    if arm is Arm.agent:
        selected = (DomainArm.AGENT,)
    elif arm is Arm.baseline:
        selected = (DomainArm.BASELINE,)
    elif arm is Arm.policy_baseline:
        selected = (DomainArm.POLICY_BASELINE,)
    elif arm is Arm.control:
        selected = (DomainArm.CONTROL,)
    else:
        # `both` remains the documented gate spelling, but now means the full
        # comparison: control, naive, naive + policy, and agent. `all` says that
        # explicitly; `both` remains compatible with the documented gate command.
        selected = (
            DomainArm.CONTROL,
            DomainArm.BASELINE,
            DomainArm.POLICY_BASELINE,
            DomainArm.AGENT,
        )

    # An explicitly empty process variable is not overridden by .env. That is
    # the stricter CI gate and prevents SDK credential fall-through.
    load_dotenv(dotenv_path=Path(".env"), override=False)

    batch = generate_batch(seed)
    if run_id is None:
        run_id = f"seed{seed}" if ticks == DEFAULT_TICKS else f"seed{seed}-t{ticks}"
    elif not _SAFE_RUN_ID.fullmatch(run_id):
        typer.secho(f"unsafe run id: {run_id!r}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    run_dir = Path("runs") / run_id
    metric_inputs = {}
    # `--no-model` bypasses the reasoner entirely rather than pointing it at an
    # empty cache. A committed cache is read whether or not a key is set, so
    # once real entries exist the no-key run stops being the deterministic run
    # the canonical artifacts describe (ISS-043). Using the fallback components
    # directly is the only spelling that cannot read a cache, cannot call the
    # API, and is obviously the thing that produced `runs/seed42/`.
    agent_reasoner = (
        ClaudeReasoner(cache_only=cache_only, max_api_calls=max_api_calls)
        if DomainArm.AGENT in selected and not no_model
        else None
    )

    for domain_arm in selected:
        proposer: Proposer
        policy: PolicyGate | None
        batch_reasoner: BatchReasoner | None = None
        if domain_arm is DomainArm.AGENT:
            if agent_reasoner is None:
                proposer = DeterministicFallback()
                batch_reasoner = DeterministicBatchFallback()
            else:
                proposer = agent_reasoner
                batch_reasoner = agent_reasoner
            # A fresh engine owns per-run link-budget state. The simulated
            # comparison leaves the Phase 4 live budget disabled.
            policy = PolicyEngine(MerchantPolicy(link_budget=None))
        elif domain_arm is DomainArm.BASELINE:
            proposer = NaiveChaser()
            policy = None
        elif domain_arm is DomainArm.POLICY_BASELINE:
            proposer = PolicyNaiveChaser()
            policy = PolicyEngine(MerchantPolicy(link_budget=None))
        else:
            proposer = AlwaysWait()
            policy = None

        arm_dir = run_dir / domain_arm.value.lower()
        if live and domain_arm is DomainArm.AGENT:
            result = _run_live_agent_arm(
                batch,
                proposer,
                batch_reasoner=batch_reasoner,
                seed=seed,
                run_id=run_id,
                ticks=ticks,
                capacity=live_budget,
                arm_dir=arm_dir,
                confirm=confirm,
            )
        else:
            result = run_batch(
                batch.records,
                proposer,
                seed=seed,
                run_id=run_id,
                horizon=ticks,
                policy=policy,
                batch_reasoner=batch_reasoner,
            )
        write_run(result, batch, arm_dir)
        metric_inputs[domain_arm] = (result.records, result.log.rows)
        typer.echo(
            f"{domain_arm.value.lower()}: recovered {result.recovered_paise} paise, "
            f"contacts {result.contacts}, vetoes {result.vetoed}"
        )

    if agent_reasoner is not None:
        cache = agent_reasoner.cache.stats
        typer.echo(
            "reasoner: "
            f"cache {cache.hits}/{cache.lookups} ({cache.hit_rate:.1%}), "
            f"model calls {agent_reasoner.stats.api_calls}, "
            f"fallbacks {agent_reasoner.stats.fallbacks}"
        )
        reasons = agent_reasoner.stats.fallback_reasons
        if reasons:
            detail = ", ".join(f"{name} {count}" for name, count in sorted(reasons.items()))
            typer.echo(f"reasoner fallback reasons: {detail}")

    report = compute_metrics(metric_inputs)
    _, markdown_path = write_reports(report, run_dir)
    typer.secho(f"wrote {markdown_path}", fg=typer.colors.GREEN)
    typer.echo(_console_safe(markdown_path.read_text(encoding="utf-8")))
    if not live and live_budget != 30:
        typer.echo("--live-budget applies to --executor live only; this run was simulated")


@app.command()
def metrics(
    run_id: str = typer.Argument(..., help="Run id under runs/."),
    fmt: str = typer.Option("markdown", help="markdown | json"),
) -> None:
    """Recompute the four-arm metric table from stored artifacts. (Phase 2)"""
    from recoup.audit.log import read_log, verify_chain
    from recoup.domain.models import Invoice
    from recoup.metrics.compute import REPORT_ARM_ORDER, compute_metrics
    from recoup.metrics.report import render_json, render_markdown, write_reports

    run_dir = Path("runs") / run_id
    metric_inputs = {}
    for domain_arm in REPORT_ARM_ORDER:
        arm_dir = run_dir / domain_arm.value.lower()
        final_path = arm_dir / "final.json"
        log_path = arm_dir / "audit.jsonl"
        if not final_path.exists() or not log_path.exists():
            continue
        rows = read_log(log_path)
        verify_chain(rows)
        records = [
            Invoice.model_validate(item)
            for item in json.loads(final_path.read_text(encoding="utf-8"))
        ]
        metric_inputs[domain_arm] = (records, rows)

    if not metric_inputs:
        typer.secho(f"no arm artifacts found under {run_dir}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    report = compute_metrics(metric_inputs)
    write_reports(report, run_dir)
    if fmt == "markdown":
        typer.echo(_console_safe(render_markdown(report)))
    elif fmt == "json":
        typer.echo(render_json(report))
    else:
        typer.secho("--fmt must be markdown or json", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command()
def replay(
    run_id: str = typer.Argument(..., help="Run id under runs/."),
    invoice_id: str = typer.Option(None, help="Reconstruct one invoice; omit for all."),
) -> None:
    """Reconstruct invoice history from the audit log alone. (Phase 1)

    The acceptance test: replayed state must equal ledger state. If it does not,
    the log is wrong.
    """
    from recoup.audit.log import read_log
    from recoup.audit.replay import compare
    from recoup.audit.replay import replay as replay_rows
    from recoup.domain.models import Invoice
    from recoup.generator.generate import load_batch

    run_dir = Path("runs") / run_id
    log_path = run_dir / "audit.jsonl"
    batch_path = run_dir / "batch.json"
    final_path = run_dir / "final.json"
    for required in (log_path, batch_path, final_path):
        if not required.exists():
            typer.secho(f"missing {required}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

    rows = read_log(log_path)

    # Reconstruct from the OPENING batch and the log, and nothing else. There
    # is no finalisation step: the run's write-offs are rows in the log like
    # everything else, so nothing here needs to know the horizon.
    result = replay_rows(load_batch(batch_path).records, rows)

    if invoice_id:
        record = result.ledger.get(invoice_id)
        typer.echo(f"{invoice_id}: {record.state} recovered={record.recovered_paise} paise")
        return

    # Compare against the CLOSING position the run itself stored. This is the
    # acceptance test: the log has to reproduce a state it was not handed.
    stored = [Invoice.model_validate(row) for row in json.loads(final_path.read_text("utf-8"))]
    differences = compare(stored, result.ledger.records)

    typer.echo(f"{len(rows)} rows, chain verified, {len(result.ledger.records)} records")
    if differences:
        for difference in differences[:10]:
            typer.secho(str(difference), fg=typer.colors.RED, err=True)
        typer.secho(f"{len(differences)} divergences", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.secho("replay matches the ledger", fg=typer.colors.GREEN)


@app.command()
def webhook(
    port: int = typer.Option(8000, help="Port to serve on. Expose it with a tunnel."),
    host: str = typer.Option("127.0.0.1", help="Bind address. Localhost; the tunnel reaches in."),
    runs_root: Path = typer.Option(Path("runs"), help="Where live-link sessions are looked up."),
) -> None:
    """Serve the Razorpay webhook receiver. (Phase 4)

    Pair it with a tunnel and point a dashboard webhook at
    `<tunnel>/razorpay/webhook` for `payment_link.paid`:

        recoup webhook
        cloudflared tunnel --url http://localhost:8000
    """
    import os

    import uvicorn

    os.environ["RECOUP_RUNS_ROOT"] = str(runs_root)
    if not os.environ.get("RAZORPAY_WEBHOOK_SECRET", ""):
        # Serve anyway -- the endpoint refuses every request with 503 and says
        # why, which is a better thing to discover now than mid-recording.
        typer.secho(
            "RAZORPAY_WEBHOOK_SECRET is not set. The receiver will refuse every delivery "
            "until it is: set it to the secret you chose in the Razorpay dashboard.",
            fg=typer.colors.YELLOW,
            err=True,
        )
    typer.secho(f"webhook receiver on http://{host}:{port}", fg=typer.colors.GREEN)
    uvicorn.run("webhook.app:app", host=host, port=port, log_level="info")


@app.command()
def reconcile(
    payload: Path = typer.Argument(..., help="A saved Razorpay webhook payload, as JSON."),
    runs_root: Path = typer.Option(Path("runs"), help="Where live-link sessions are looked up."),
) -> None:
    """Apply a saved `payment_link.paid` payload to the ledger. (Phase 4)

    The offline half of the webhook, and the reason the receiver needs no
    network to be exercised: the same reconciliation, driven from a payload on
    disk. Use it to replay a delivery that arrived while the tunnel was down,
    or to rehearse the round trip without spending a link.
    """
    from recoup.executor.reconcile import ReconcileRefused, reconcile_payment
    from recoup.executor.session import find_link

    event = json.loads(payload.read_text(encoding="utf-8"))
    body = event.get("payload", {})
    link_entity = body.get("payment_link", {}).get("entity", {})
    payment_entity = body.get("payment", {}).get("entity", {})
    payment_link_id = str(link_entity.get("id", ""))

    located = find_link(runs_root, payment_link_id)
    if located is None:
        typer.secho(
            f"no run under {runs_root} created payment link {payment_link_id!r}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    arm_dir, _session, link = located

    try:
        result = reconcile_payment(
            arm_dir,
            invoice_id=link.invoice_id,
            payment_id=str(payment_entity.get("id", "")),
            payment_link_id=payment_link_id,
            amount_paise=int(payment_entity.get("amount") or link_entity.get("amount_paid") or 0),
            received_at=str(event.get("created_at", "")),
        )
    except ReconcileRefused as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    verb = "already applied" if result.already_applied else "reconciled"
    typer.secho(
        f"{verb}: {result.invoice_id} {result.state_before} -> {result.state_after}, "
        f"{result.amount_paise} paise, audit row {result.row_id}",
        fg=typer.colors.GREEN,
    )
    # Replay is keyed by run AND arm, because each arm has its own log. The
    # run-root metric table is derived from final.json and audit.jsonl, so it
    # is stale until recomputed -- and it is what the dashboard and the video
    # read.
    typer.echo(
        f"verify with: recoup replay {result.run_id}/{arm_dir.name} "
        f"&& recoup metrics {result.run_id}"
    )


@app.command()
def dashboard(
    run_id: str = typer.Argument(
        None, help="Run id to open. Defaults to canonical seed42 when present, else latest."
    ),
    port: int = typer.Option(8501),
) -> None:
    """Launch the offline Streamlit dashboard. (Phase 5)"""
    if run_id is not None and _SAFE_RUN_ID.fullmatch(run_id) is None:
        typer.secho(
            "Run id must be 1-64 letters, numbers, dots, underscores or hyphens.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)
    if not 1 <= port <= 65535:
        typer.secho("Port must be between 1 and 65535.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    import dashboard as dashboard_package

    package_file = dashboard_package.__file__
    script = Path(package_file).resolve().parent / "app.py" if package_file else Path()
    if not script.is_file():
        typer.secho(f"Dashboard entry point not found: {script}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    runs_root = (Path.cwd() / "runs").resolve()
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(script),
        "--server.port",
        str(port),
        "--",
        "--runs-root",
        str(runs_root),
    ]
    if run_id is not None:
        command.extend(("--run-id", run_id))
    typer.secho(
        f"opening offline dashboard from {runs_root} on http://localhost:{port}",
        fg=typer.colors.GREEN,
    )
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        raise typer.Exit(code=exc.returncode) from exc


@app.command("check-razorpay")
def check_razorpay(
    amount_paise: int = typer.Option(10000, help="Link amount in paise. Default is Rs 100."),
) -> None:
    """Smoke-test Razorpay test-mode credentials. (Phase 0)

    Creates one Standard Payment Link and prints its short_url. Confirms the keys
    work before Phase 4 depends on them, and burns exactly one unit of the
    30-link test-mode budget (ISS-001).
    """
    import os

    import razorpay
    from dotenv import load_dotenv

    load_dotenv()
    key_id = os.environ.get("RAZORPAY_KEY_ID", "")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "")

    if not key_id or not key_secret:
        typer.secho(
            "RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set. Copy .env.example to .env.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    if not key_id.startswith("rzp_test_"):
        typer.secho(
            f"Refusing to run: key id {key_id!r} is not a test key. "
            "Recoup never touches live mode.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    client = razorpay.Client(auth=(key_id, key_secret))
    link = client.payment_link.create(
        {
            "amount": amount_paise,
            "currency": "INR",
            "description": "Recoup Phase 0 connectivity check",
            "reminder_enable": False,
        }
    )
    typer.secho("Razorpay test mode reachable.", fg=typer.colors.GREEN)
    typer.echo(f"  id:        {link['id']}")
    typer.echo(f"  short_url: {link['short_url']}")
    typer.echo("\nOne unit of the 30-link test-mode budget has been used (ISS-001).")


if __name__ == "__main__":
    app()


class SeedSelection(StrEnum):
    """Which tick-0 records a seeding pass is allowed to pay for."""

    high_info = "high-info"
    already_paid = "already-paid"
    disputed_prose = "disputed-prose"
    hardship = "hardship"


@app.command("seed-cache")
def seed_cache(
    select: SeedSelection = typer.Option(
        SeedSelection.high_info, help="Which held-out slice to seed at tick 0."
    ),
    seed: int = typer.Option(DEFAULT_SEED, help="RNG seed. Must match the run being seeded."),
    confirm: bool = typer.Option(
        False, "--confirm", help="Actually call the API. Without this the pass is a dry run."
    ),
    max_calls: int | None = typer.Option(
        None, help="Hard ceiling on calls. Defaults to the number of uncached targets."
    ),
    cost_per_call: float = typer.Option(
        0.021, help="USD per record call, for the projection only. Measure it, do not trust it."
    ),
) -> None:
    """Seed the model cache for a named slice of tick-0 records. Dry run by default.

    Selection uses the held-out flags, which is legitimate: choosing an
    evaluation set is not the same as showing the model the answer. The
    snapshot handed to the reasoner is the ordinary one and still excludes
    `payer_archetype`, `flags`, `provenance` and `spotlight`.

    Records already in the cache are skipped, so a repeated pass costs nothing.
    """
    from dotenv import load_dotenv

    from recoup.domain.enums import CONTACT_INTERVENTIONS, Flag
    from recoup.generator.generate import generate_batch
    from recoup.ledger.clock import virtual_date
    from recoup.reasoner.client import ClaudeReasoner
    from recoup.reasoner.fallback import DeterministicFallback

    load_dotenv(dotenv_path=Path(".env"), override=False)

    wanted = {
        SeedSelection.already_paid: {Flag.ALREADY_PAID_UNRECONCILED},
        SeedSelection.disputed_prose: {Flag.DISPUTED},
        SeedSelection.hardship: {Flag.HARDSHIP_CLAIMED},
        SeedSelection.high_info: {
            Flag.ALREADY_PAID_UNRECONCILED,
            Flag.DISPUTED,
            Flag.HARDSHIP_CLAIMED,
        },
    }[select]

    ladder = DeterministicFallback()
    as_of = virtual_date(0)
    targets: list[tuple[str, dict[str, object]]] = []
    for record in generate_batch(seed).records:
        if not (set(record.flags) & wanted):
            continue
        if record.outstanding_paise <= 0:
            continue  # never reviewed, so a cache entry could never be hit
        snapshot = record.to_snapshot(as_of, 0)
        free_text = record.free_text
        if free_text.is_empty:
            continue  # no prose means nothing the ladder cannot already see
        if record.state.value == "DISPUTED" or free_text.dispute_description:
            continue  # a structured tell the policy engine already acts on
        if ladder.propose(snapshot, 0).intervention not in CONTACT_INTERVENTIONS:
            continue  # the ladder does no harm here, so there is nothing to beat
        targets.append((record.invoice_id, snapshot))

    reasoner = ClaudeReasoner()
    pending = [
        (invoice_id, snapshot)
        for invoice_id, snapshot in targets
        if not reasoner.cache.path_for("records", snapshot).exists()
    ]
    ceiling = len(pending) if max_calls is None else min(max_calls, len(pending))

    typer.echo(f"selection      {select.value}")
    typer.echo(f"targets        {len(targets)}")
    typer.echo(f"already cached {len(targets) - len(pending)}")
    typer.echo(f"calls to make  {ceiling}")
    typer.secho(f"projected cost ${ceiling * cost_per_call:.2f}", fg=typer.colors.YELLOW)
    for invoice_id, _ in pending[:ceiling]:
        typer.echo(f"  would call {invoice_id}")

    if not confirm:
        typer.secho("\ndry run. re-run with --confirm to spend.", fg=typer.colors.CYAN)
        raise typer.Exit(code=0)
    if not reasoner.api_key:
        typer.secho("no ANTHROPIC_API_KEY configured; nothing to do.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    # The ceiling is enforced inside the reasoner too, so a bug in the loop
    # above cannot turn into unbounded spend.
    reasoner = ClaudeReasoner(max_api_calls=ceiling)
    for invoice_id, snapshot in pending[:ceiling]:
        proposal = reasoner.propose(snapshot, 0)
        intervention = proposal.llm_proposal.intervention if proposal.llm_proposal else None
        typer.echo(f"  {invoice_id}: {intervention}")

    typer.secho(
        f"\ncalls {reasoner.stats.api_calls}, cached {reasoner.cache.stats.writes}, "
        f"fallbacks {reasoner.stats.fallbacks}",
        fg=typer.colors.GREEN,
    )
