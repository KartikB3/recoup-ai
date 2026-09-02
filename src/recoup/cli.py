"""Recoup command-line surface.

Phase 0 defines the command contract; later phases fill in the implementations.
Every command here is referenced by a gate in docs/IMPLEMENTATION-PLAN.md, so
the signatures are the thing being frozen, not the bodies.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import typer

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Autonomous receivables recovery: the LLM proposes, the policy engine disposes.",
)

DEFAULT_SEED = 42
DEFAULT_TICKS = 112  # 1 tick = 6 virtual hours -> 28 virtual days


class Arm(StrEnum):
    """Which recovery strategy runs against the batch."""

    agent = "agent"
    baseline = "baseline"
    both = "both"


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


@app.command()
def generate(
    seed: int = typer.Option(DEFAULT_SEED, help="RNG seed. Same seed, byte-identical batch."),
    count: int = typer.Option(120, min=120, help="Number of records. Spec floor is 120."),
    out: Path = typer.Option(Path("data/batches"), help="Output directory."),
) -> None:
    """Generate a seeded, reproducible invoice batch. (Phase 1)"""
    _not_yet(1, "The generator")


@app.command()
def run(
    seed: int = typer.Option(DEFAULT_SEED, help="RNG seed. Both arms must share it."),
    arm: Arm = typer.Option(Arm.both, help="Which arm(s) to run."),
    ticks: int = typer.Option(DEFAULT_TICKS, help="Virtual ticks to advance."),
    executor: ExecutorMode = typer.Option(ExecutorMode.simulated, help="Execution mode."),
    live_budget: int = typer.Option(30, help="Payment-link budget. Test mode caps at 30."),
) -> None:
    """Run the batch end to end and write runs/<id>/. (Phase 2)

    This command is the Phase 2 gate: `recoup run --seed 42 --arm both` must
    produce a full metric table with no LLM involved.
    """
    _not_yet(2, "The batch runner")


@app.command()
def metrics(
    run_id: str = typer.Argument(..., help="Run id under runs/."),
    fmt: str = typer.Option("markdown", help="markdown | json"),
) -> None:
    """Render the baseline-vs-agent metric table for a run. (Phase 2)"""
    _not_yet(2, "Metric reporting")


@app.command()
def replay(
    run_id: str = typer.Argument(..., help="Run id under runs/."),
    invoice_id: str = typer.Option(None, help="Reconstruct one invoice; omit for all."),
) -> None:
    """Reconstruct invoice history from the audit log alone. (Phase 1)

    The acceptance test: replayed state must equal ledger state. If it does not,
    the log is wrong.
    """
    _not_yet(1, "Audit replay")


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
