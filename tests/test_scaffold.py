"""Phase 0 scaffold tests.

These do not test behaviour — there is none yet. They test that the skeleton the
later phases depend on actually holds together, and they fail loudly if someone
moves a module the plan references.
"""

from __future__ import annotations

import importlib
import pkgutil
import subprocess
import tomllib
from collections.abc import Sequence
from pathlib import Path

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
    # Phase 4 additions. The plan named the four above; these are the modules
    # the live slice turned out to need, and they are pinned here for the same
    # reason: five gates reference these paths by name.
    "recoup.executor.fake_razorpay",
    "recoup.executor.session",
    "recoup.executor.signature",
    "recoup.executor.reconcile",
    "recoup.audit.log",
    "recoup.audit.replay",
    "recoup.baseline.naive_chaser",
    "recoup.metrics.compute",
    "recoup.metrics.report",
    "recoup.runner.batch",
]

# Commands the plan's gates invoke by name.
PLANNED_COMMANDS = [
    "generate",
    "run",
    "metrics",
    "replay",
    "dashboard",
    "check-razorpay",
    "webhook",
    "reconcile",
]


@pytest.mark.parametrize("module", PLANNED_MODULES)
def test_planned_module_imports(module: str) -> None:
    """Every module the plan references exists and imports cleanly."""
    assert importlib.import_module(module) is not None


def test_every_module_has_a_docstring() -> None:
    """A stub without a docstring is an empty file nobody can navigate.

    Covers package __init__ files as well as leaf modules - an undocumented
    package is exactly the one a later phase fills in blind.
    """
    packages = [f"recoup.{m.name}" for m in pkgutil.iter_modules(recoup.__path__) if m.ispkg] + [
        "recoup.policy.rules"
    ]
    undocumented = [
        name
        for name in PLANNED_MODULES + packages
        if not (importlib.import_module(name).__doc__ or "").strip()
    ]
    assert not undocumented, f"missing docstrings: {undocumented}"


def test_planned_subpackages_still_exist() -> None:
    """The layout is frozen in Phase 0: later phases ADD, they do not move or rename.

    Deliberately a subset check, not equality. A phase that legitimately adds a
    subpackage should not fail CI at 11pm on Day 5; a phase that renames one
    should fail immediately, because five gates reference these paths by name.
    """
    required = {
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
    assert required <= found, f"layout drift - subpackages missing or renamed: {required - found}"


@pytest.mark.parametrize("command", PLANNED_COMMANDS)
def test_command_is_registered(command: str) -> None:
    """Each gate command exists and has help text."""
    result = runner.invoke(app, [command, "--help"])
    assert result.exit_code == 0, result.output


def test_dashboard_command_launches_streamlit_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI passes a local runs root and never starts another Recoup subsystem."""
    seen: list[Sequence[str]] = []

    def fake_run(command: Sequence[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        assert check is True
        seen.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = runner.invoke(app, ["dashboard", "seed42", "--port", "8765"])

    assert result.exit_code == 0, result.output
    assert "offline dashboard" in result.output
    assert len(seen) == 1
    command = list(seen[0])
    assert command[1:4] == ["-m", "streamlit", "run"]
    assert command[command.index("--server.port") + 1] == "8765"
    assert command[command.index("--run-id") + 1] == "seed42"
    assert Path(command[command.index("--runs-root") + 1]) == Path.cwd() / "runs"
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    wheel_packages = project["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert "dashboard" in wheel_packages


def test_default_seed_count_and_tick_count_match_the_plan() -> None:
    """Published defaults are seed 42, 126 records, and a 28-day horizon."""
    from recoup.cli import DEFAULT_COUNT, DEFAULT_SEED, DEFAULT_TICKS
    from recoup.generator.archetypes import BATCH_SIZE

    assert DEFAULT_SEED == 42
    assert DEFAULT_COUNT == BATCH_SIZE == 126
    assert DEFAULT_TICKS == 112
    assert DEFAULT_TICKS * 6 == 28 * 24
