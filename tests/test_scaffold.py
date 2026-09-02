"""Phase 0 scaffold tests.

These do not test behaviour — there is none yet. They test that the skeleton the
later phases depend on actually holds together, and they fail loudly if someone
moves a module the plan references.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest
from typer.testing import CliRunner

import recoup
from recoup.cli import app

runner = CliRunner()

# Every module docs/IMPLEMENTATION-PLAN.md section 1 promises will exist.
PLANNED_MODULES = [
    "recoup.domain.enums",
    "recoup.domain.models",
    "recoup.domain.interventions",
    "recoup.generator.archetypes",
    "recoup.generator.generate",
    "recoup.ledger.clock",
    "recoup.ledger.ledger",
    "recoup.ledger.adjudicator",
    "recoup.policy.engine",
    "recoup.policy.sources",
    "recoup.reasoner.client",
    "recoup.reasoner.schemas",
    "recoup.reasoner.prompts",
    "recoup.reasoner.cache",
    "recoup.reasoner.fallback",
    "recoup.reasoner.batch_insight",
    "recoup.executor.base",
    "recoup.executor.simulated",
    "recoup.executor.live_razorpay",
    "recoup.executor.budget",
    "recoup.audit.log",
    "recoup.audit.replay",
    "recoup.baseline.naive_chaser",
    "recoup.metrics.compute",
    "recoup.metrics.report",
    "recoup.runner.batch",
]

# Commands the plan's gates invoke by name.
PLANNED_COMMANDS = ["generate", "run", "metrics", "replay", "dashboard", "check-razorpay"]


@pytest.mark.parametrize("module", PLANNED_MODULES)
def test_planned_module_imports(module: str) -> None:
    """Every module the plan references exists and imports cleanly."""
    assert importlib.import_module(module) is not None


def test_every_module_has_a_docstring() -> None:
    """A stub without a docstring is an empty file nobody can navigate."""
    undocumented = [
        name
        for name in PLANNED_MODULES
        if not (importlib.import_module(name).__doc__ or "").strip()
    ]
    assert not undocumented, f"missing docstrings: {undocumented}"


def test_no_unexpected_top_level_subpackages() -> None:
    """The layout is frozen in Phase 0. Later phases fill files in, not move them."""
    expected = {
        "domain",
        "generator",
        "ledger",
        "policy",
        "reasoner",
        "executor",
        "audit",
        "baseline",
        "metrics",
        "runner",
    }
    found = {m.name for m in pkgutil.iter_modules(recoup.__path__) if m.ispkg}
    assert found == expected, (
        f"layout drift: unexpected={found - expected}, missing={expected - found}"
    )


@pytest.mark.parametrize("command", PLANNED_COMMANDS)
def test_command_is_registered(command: str) -> None:
    """Each gate command exists and has help text."""
    result = runner.invoke(app, [command, "--help"])
    assert result.exit_code == 0, result.output


def test_unimplemented_commands_fail_loudly() -> None:
    """A not-yet-built command must exit non-zero and point at the plan.

    Silently succeeding with no output is how a phase gets marked done by
    accident.
    """
    result = runner.invoke(app, ["generate", "--seed", "42"])
    assert result.exit_code == 1
    assert "Phase 1" in result.output
    assert "IMPLEMENTATION-PLAN" in result.output


def test_default_seed_and_tick_count_match_the_plan() -> None:
    """1 tick = 6 virtual hours; 112 ticks = 28 virtual days. Seed 42 everywhere."""
    from recoup.cli import DEFAULT_SEED, DEFAULT_TICKS

    assert DEFAULT_SEED == 42
    assert DEFAULT_TICKS == 112
    assert DEFAULT_TICKS * 6 == 28 * 24
