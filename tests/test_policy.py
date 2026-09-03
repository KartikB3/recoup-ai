"""Policy rule, composition, provenance, and full-agent behavioural checks."""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from recoup.audit.replay import compare, replay
from recoup.domain.enums import (
    Intervention,
    MessageCategory,
    RuleKind,
    VerdictKind,
)
from recoup.domain.models import DraftedMessage, LLMProposal
from recoup.generator.generate import generate_batch
from recoup.ledger.ledger import Ledger
from recoup.metrics.compute import compute_arm_metrics
from recoup.policy.context import (
    CONTACT_INTENSITY,
    MerchantPolicy,
    Rule,
    RuleContext,
    modify,
    veto,
)
from recoup.policy.engine import PolicyEngine
from recoup.policy.rules import RULE_ORDER
from recoup.policy.sources import MERCHANT_POLICY
from recoup.reasoner.fallback import DeterministicFallback
from recoup.runner.batch import Proposal, RunResult, run_batch

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "src" / "recoup" / "policy" / "rules"


def _proposal(
    intervention: Intervention,
    category: MessageCategory | None = None,
) -> LLMProposal:
    drafted = None
    if category is not None:
        drafted = DraftedMessage(
            channel="EMAIL",
            category=category,
            subject="test",
            body="test body",
        )
    return LLMProposal(
        diagnosis="test",
        intervention=intervention,
        confidence=1.0,
        reasoning="test",
        drafted_message=drafted,
    )


def _ctx(
    intervention: Intervention,
    *,
    record=None,
    ledger: Ledger | None = None,
    tick: int = 0,
    config: MerchantPolicy | None = None,
    proposal: LLMProposal | None = None,
    suppressed: frozenset[str] = frozenset(),
    group_escalation_opened: bool = False,
) -> RuleContext:
    selected = record or generate_batch(42).records[0]
    selected_ledger = ledger or Ledger([selected])
    return RuleContext(
        record=selected,
        original=intervention,
        current=intervention,
        suppressed_invoices=suppressed,
        group_escalation_opened=group_escalation_opened,
        tick=tick,
        ledger=selected_ledger,
        config=config or MerchantPolicy(),
        links_used=0,
        llm_proposal=proposal,
    )


def _firing_contexts() -> dict[str, RuleContext]:
    batch = generate_batch(42)

    settled = batch.records[0].model_copy(deep=True)
    settled.recovered_paise = settled.amount_paise

    disputed = batch.records[1].model_copy(deep=True)
    disputed.free_text.dispute_description = "The supplied goods do not match the PO."

    frequency_record = batch.records[2].model_copy(deep=True)
    frequency_ledger = Ledger([frequency_record])
    for tick in (0, 12, 24, 36):
        frequency_ledger.record_action(frequency_record, Intervention.SOFT_REMINDER, tick)

    spacing_record = batch.records[3].model_copy(deep=True)
    spacing_ledger = Ledger([spacing_record])
    spacing_ledger.record_action(spacing_record, Intervention.SOFT_REMINDER, 0)

    capped = batch.records[4].model_copy(deep=True)
    capped.contact_ledger.payment_links_sent = 3

    return {
        "nothing-outstanding": _ctx(Intervention.SOFT_REMINDER, record=settled),
        "visible-dispute": _ctx(Intervention.SOFT_REMINDER, record=disputed),
        "batch-cluster-suppression": _ctx(
            Intervention.SOFT_REMINDER,
            suppressed=frozenset({batch.records[0].invoice_id}),
        ),
        "rbi-contact-hours": _ctx(Intervention.SOFT_REMINDER, tick=2),
        "trai-promotional-window": _ctx(
            Intervention.SOFT_REMINDER,
            tick=0,
            proposal=_proposal(Intervention.SOFT_REMINDER, MessageCategory.P),
        ),
        "trai-message-category": _ctx(
            Intervention.SOFT_REMINDER,
            tick=1,
            proposal=_proposal(Intervention.SOFT_REMINDER, MessageCategory.P),
        ),
        "payer-contact-frequency": _ctx(
            Intervention.SOFT_REMINDER,
            record=frequency_record,
            ledger=frequency_ledger,
            tick=40,
        ),
        "payer-contact-spacing": _ctx(
            Intervention.SOFT_REMINDER,
            record=spacing_record,
            ledger=spacing_ledger,
            tick=1,
        ),
        "invoice-link-cap": _ctx(Intervention.PAYMENT_LINK, record=capped),
        "link-budget": _ctx(
            Intervention.PAYMENT_LINK,
            config=MerchantPolicy(link_budget=0),
        ),
        "high-value-escalation": _ctx(
            Intervention.STOP,
            config=MerchantPolicy(escalation_threshold_paise=0),
        ),
    }


def test_every_documented_rule_can_fire_directly() -> None:
    """A dormant batch path is not an excuse for an unexercised rule."""
    contexts = _firing_contexts()
    assert set(contexts) == {rule.rule_id for rule in RULE_ORDER}
    for rule in RULE_ORDER:
        verdict = rule.check(contexts[rule.rule_id])
        assert verdict is not None, rule.rule_id


def test_dormant_regulatory_and_budget_rules_are_exercised() -> None:
    """The three known zero-count rules still have discriminating unit checks."""
    contexts = _firing_contexts()
    for rule_id in (
        "trai-promotional-window",
        "trai-message-category",
        "link-budget",
    ):
        rule = next(item for item in RULE_ORDER if item.rule_id == rule_id)
        verdict = rule.check(contexts[rule_id])
        assert verdict is not None
        assert verdict.rule_source is not None
        if verdict.rule_source.kind is RuleKind.REGULATORY:
            assert verdict.rule_source.verified is True
        else:
            assert verdict.rule_source.verified is None


def test_merchant_source_verification_is_not_applicable() -> None:
    """A merchant policy must never inherit a regulatory verification badge."""
    assert MERCHANT_POLICY.kind is RuleKind.MERCHANT
    assert MERCHANT_POLICY.verified is None


def test_default_escalation_threshold_matches_the_seed_contract() -> None:
    """Prevent Indian digit grouping from silently changing Rs 5 lakh to Rs 50 lakh."""
    from recoup.generator.archetypes import ESCALATION_REFERENCE_PAISE

    assert MerchantPolicy().escalation_threshold_paise == ESCALATION_REFERENCE_PAISE


def test_a_modification_never_raises_contact_intensity() -> None:
    """The invariant that makes one-pass composition valid, over every rule."""
    contexts = _firing_contexts()
    for rule in RULE_ORDER:
        ctx = contexts[rule.rule_id]
        verdict = rule.check(ctx)
        assert verdict is not None
        if verdict.verdict is VerdictKind.MODIFIED:
            assert verdict.final is not None
            assert CONTACT_INTENSITY[verdict.final] <= CONTACT_INTENSITY[ctx.current]


def test_all_deferrals_move_strictly_forward() -> None:
    contexts = _firing_contexts()
    for rule_id in (
        "rbi-contact-hours",
        "trai-promotional-window",
        "payer-contact-frequency",
        "payer-contact-spacing",
    ):
        rule = next(item for item in RULE_ORDER if item.rule_id == rule_id)
        verdict = rule.check(contexts[rule_id])
        assert verdict is not None
        assert verdict.defer_to_tick is not None
        assert verdict.defer_to_tick > contexts[rule_id].tick


def test_engine_composes_modifications_and_keeps_the_first_reason() -> None:
    record = generate_batch(42).records[0]
    ledger = Ledger([record])

    first = Rule(
        "first-reduction",
        lambda ctx: modify(ctx, Intervention.SOFT_REMINDER, MERCHANT_POLICY, "first"),
    )
    second = Rule(
        "second-reduction",
        lambda ctx: modify(ctx, Intervention.WAIT, MERCHANT_POLICY, "second"),
    )
    engine = PolicyEngine(rules=(first, second))
    verdict = engine.adjudicate(record, Proposal(Intervention.PAYMENT_LINK), 0, ledger)

    assert verdict.verdict is VerdictKind.MODIFIED
    assert verdict.rule_id == "first-reduction"
    assert verdict.explanation == "first"
    assert verdict.final is Intervention.WAIT


def test_engine_returns_the_first_veto_even_after_a_modification() -> None:
    record = generate_batch(42).records[0]
    ledger = Ledger([record])
    reduction = Rule(
        "reduction",
        lambda ctx: modify(ctx, Intervention.SOFT_REMINDER, MERCHANT_POLICY, "reduce"),
    )
    stop = Rule("veto", lambda ctx: veto(ctx, MERCHANT_POLICY, "stop"))
    never = Rule("never", lambda ctx: pytest.fail("rule order did not stop at the veto"))
    verdict = PolicyEngine(rules=(reduction, stop, never)).adjudicate(
        record, Proposal(Intervention.PAYMENT_LINK), 0, ledger
    )
    assert verdict.verdict is VerdictKind.VETOED
    assert verdict.rule_id == "veto"


def test_rule_order_matches_the_documented_table() -> None:
    text = (ROOT / "docs" / "POLICY-SOURCES.md").read_text(encoding="utf-8")
    documented = re.findall(r"^\| \d+ \| `([^`]+)`", text, flags=re.MULTILINE)
    assert documented == [rule.rule_id for rule in RULE_ORDER]


def test_policy_rule_source_never_reads_simulation_ground_truth() -> None:
    """AST catches aliases and spacing that a text grep would miss."""
    forbidden = {"payer_archetype", "flags", "provenance", "spotlight", "model_dump"}
    offenders: list[str] = []
    for path in sorted(RULES.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in forbidden:
                offenders.append(f"{path.name}:{node.lineno}:{node.attr}")
    assert not offenders, offenders


@pytest.fixture(scope="module")
def agent_result() -> RunResult:
    batch = generate_batch(42)
    return run_batch(
        batch.records,
        DeterministicFallback(),
        seed=42,
        run_id="test-agent",
        policy=PolicyEngine(),
    )


def test_agent_run_exercises_rbi_rule_and_preserves_replay(agent_result: RunResult) -> None:
    rbi_rows = [row for row in agent_result.log.rows if row.policy_rule == "rbi-contact-hours"]
    assert rbi_rows
    assert all(row.policy_verdict is not None for row in rbi_rows)
    assert all(
        row.policy_verdict.defer_to_tick > row.tick for row in rbi_rows if row.policy_verdict
    )

    rebuilt = replay(generate_batch(42).records, agent_result.log.rows)
    assert not compare(agent_result.records, rebuilt.ledger.records)


def test_agent_false_interventions_stay_nonzero(agent_result: RunResult) -> None:
    """Zero would mean the held-out ground truth leaked into policy."""
    metrics = compute_arm_metrics(agent_result.records, agent_result.log.rows)
    assert metrics.false_interventions > 0


def test_phase2_agent_execution_does_not_import_an_llm_sdk() -> None:
    """Exercise a fresh interpreter so module caching cannot hide the import."""
    script = """
import builtins
real_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == 'anthropic' or name.startswith('anthropic.'):
        raise AssertionError('LLM SDK reached the Phase 2 execution path')
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded
from recoup.generator.generate import generate_batch
from recoup.policy.engine import PolicyEngine
from recoup.reasoner.fallback import DeterministicFallback
from recoup.runner.batch import run_batch
batch = generate_batch(42)
result = run_batch(
    batch.records,
    DeterministicFallback(),
    seed=42,
    run_id='no-llm',
    policy=PolicyEngine(),
)
assert len(result.records) == 126
"""
    env = dict(os.environ)
    env["ANTHROPIC_API_KEY"] = ""
    env["PYTHONPATH"] = str(ROOT / "src")
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
