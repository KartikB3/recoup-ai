"""Recoup command-line surface.

Phase 0 defines the command contract; later phases fill in the implementations.
Every command here is referenced by a gate in docs/IMPLEMENTATION-PLAN.md, so
the signatures are the thing being frozen, not the bodies.
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path

import typer

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Autonomous receivables recovery: the LLM proposes, the policy engine disposes.",
)

DEFAULT_SEED = 42
DEFAULT_COUNT = 126
DEFAULT_TICKS = 112  # 1 tick = 6 virtual hours -> 28 virtual days


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
) -> None:
    """Run the batch end to end and write runs/<id>/. (Phases 2-3)

    A cached structured reasoner drives the agent when a key is configured;
    missing/empty credentials and any model failure preserve the exact
    deterministic Phase 2 fallback.
    """
    from dotenv import load_dotenv

    from recoup.baseline.naive_chaser import NaiveChaser, PolicyNaiveChaser
    from recoup.domain.enums import Arm as DomainArm
    from recoup.generator.generate import generate_batch
    from recoup.metrics.compute import compute_metrics
    from recoup.metrics.report import write_reports
    from recoup.policy.context import MerchantPolicy
    from recoup.policy.engine import PolicyEngine
    from recoup.reasoner.client import ClaudeReasoner
    from recoup.runner.batch import AlwaysWait, PolicyGate, Proposer, run_batch, write_run

    if executor is ExecutorMode.live:
        typer.secho(
            "Live execution lands in Phase 4; Phase 2 only permits the deterministic "
            "simulated executor.",
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
    run_id = f"seed{seed}" if ticks == DEFAULT_TICKS else f"seed{seed}-t{ticks}"
    run_dir = Path("runs") / run_id
    metric_inputs = {}
    agent_reasoner = (
        ClaudeReasoner(cache_only=cache_only, max_api_calls=max_api_calls)
        if DomainArm.AGENT in selected
        else None
    )

    for domain_arm in selected:
        proposer: Proposer
        policy: PolicyGate | None
        batch_reasoner = None
        if domain_arm is DomainArm.AGENT:
            assert agent_reasoner is not None
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

        result = run_batch(
            batch.records,
            proposer,
            seed=seed,
            run_id=run_id,
            horizon=ticks,
            policy=policy,
            batch_reasoner=batch_reasoner,
        )
        arm_dir = run_dir / domain_arm.value.lower()
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
    if live_budget != 30:
        typer.echo("live_budget is reserved for Phase 4 and was not applied to this simulation")


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
def dashboard(
    run_id: str = typer.Argument(None, help="Run id to open. Defaults to the latest."),
    port: int = typer.Option(8501),
) -> None:
    """Launch the Streamlit dashboard. (Phase 5)"""
    _not_yet(5, "The dashboard")


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
