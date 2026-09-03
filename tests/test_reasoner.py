"""Phase 3 structured reasoner, cache, fallback, and batch-insight checks."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from recoup.audit.replay import compare, replay
from recoup.domain.enums import Intervention, RuleKind, VerdictKind
from recoup.domain.models import LLMProposal, PromiseToPay
from recoup.generator.generate import generate_batch
from recoup.ledger.clock import virtual_date
from recoup.ledger.ledger import Ledger
from recoup.policy.engine import PolicyEngine
from recoup.reasoner.batch_insight import DeterministicBatchFallback
from recoup.reasoner.cache import ReasonerCache, sha256_canonical
from recoup.reasoner.client import (
    BATCH_EFFORT,
    BATCH_MAX_TOKENS,
    BATCH_TIMEOUT_SECONDS,
    DEFAULT_MAX_RETRIES,
    MODEL,
    RECORD_EFFORT,
    SERVER_FALLBACK_BETA,
    ClaudeReasoner,
)
from recoup.reasoner.prompts import BATCH_SYSTEM_PROMPT, RECORD_SYSTEM_PROMPT
from recoup.reasoner.schemas import BatchInsight
from recoup.runner.batch import run_batch, write_run

ROOT = Path(__file__).resolve().parents[1]


def _wait_proposal() -> LLMProposal:
    return LLMProposal(
        diagnosis="No contact is useful at this review.",
        intervention=Intervention.WAIT,
        confidence=0.8,
        reasoning="The payer's stated cycle supports waiting.",
    )


def _no_batch_pattern() -> BatchInsight:
    return BatchInsight(
        pattern_found=False,
        diagnosis="No aggregate pattern.",
        confidence=0.9,
        reasoning="No explicit parent group met the evidence threshold.",
    )


class _FakeMessages:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        output = (
            _no_batch_pattern() if kwargs["output_format"] is BatchInsight else _wait_proposal()
        )
        return SimpleNamespace(stop_reason="end_turn", parsed_output=output)


class _FakeClient:
    def __init__(self) -> None:
        self.messages = _FakeMessages()
        self.beta = SimpleNamespace(messages=self.messages)


def _snapshots() -> list[dict[str, Any]]:
    return [record.to_snapshot(virtual_date(0), 0) for record in generate_batch(42).records]


def test_reasoner_outputs_carry_no_money_or_date_number() -> None:
    """Confidence is the only model-authored number and cannot drive money/time."""
    assert {
        name for name, field in LLMProposal.model_fields.items() if field.annotation is float
    } == {"confidence"}
    assert {
        name for name, field in BatchInsight.model_fields.items() if field.annotation is float
    } == {"confidence"}
    forbidden = ("amount", "paise", "rupee", "date", "tick")
    for output_type in (LLMProposal, PromiseToPay, BatchInsight):
        assert not [
            name for name in output_type.model_fields if any(token in name for token in forbidden)
        ]


def test_prompts_name_the_closed_space_and_the_deterministic_boundary() -> None:
    for intervention in Intervention:
        assert intervention.value in RECORD_SYSTEM_PROMPT
    assert "final decision" in RECORD_SYSTEM_PROMPT
    assert "Never output, calculate" in RECORD_SYSTEM_PROMPT
    assert "deterministic merchant-policy" in BATCH_SYSTEM_PROMPT


def test_batch_schema_rejects_half_formed_or_duplicate_patterns() -> None:
    with pytest.raises(ValidationError):
        BatchInsight(
            pattern_found=False,
            diagnosis="bad",
            parent_group_id="invented",
            invoice_ids=[],
            confidence=0.5,
            reasoning="bad",
        )
    with pytest.raises(ValidationError):
        BatchInsight(
            pattern_found=True,
            diagnosis="bad",
            parent_group_id="group",
            invoice_ids=["one", "one"],
            confidence=0.5,
            reasoning="bad",
            suppression_recommended=True,
        )


def test_cache_key_is_canonical_and_contract_drift_is_a_miss(tmp_path: Path) -> None:
    cache = ReasonerCache(tmp_path)
    left = {"invoice_id": "one", "nested": {"b": 2, "a": 1}}
    right = {"nested": {"a": 1, "b": 2}, "invoice_id": "one"}
    assert sha256_canonical(left) == sha256_canonical(right)

    assert cache.put("records", left, _wait_proposal(), contract={"prompt": "v1"})
    hit = cache.get("records", right, contract={"prompt": "v1"}, output_type=LLMProposal)
    assert hit == _wait_proposal()
    assert cache.get("records", right, contract={"prompt": "v2"}, output_type=LLMProposal) is None
    assert cache.stats.hits == 1
    assert cache.stats.invalid_entries == 1


def test_cache_rejects_unsafe_namespace(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsafe cache namespace"):
        ReasonerCache(tmp_path).path_for("../outside", {"safe": True})


def test_model_request_uses_current_sdk_contract_and_snapshot_boundary(tmp_path: Path) -> None:
    client = _FakeClient()
    reasoner = ClaudeReasoner(api_key="test", cache_root=tmp_path, client=client)
    snapshot = _snapshots()[20]
    proposal = reasoner.propose(snapshot, 0)

    assert proposal.llm_proposal == _wait_proposal()
    request = client.messages.calls[0]
    assert request["model"] == MODEL
    assert request["thinking"] == {"type": "adaptive"}
    assert request["output_config"] == {"effort": RECORD_EFFORT}
    assert request["output_format"] is LLMProposal
    assert request["fallbacks"] == "default"
    assert request["betas"] == [SERVER_FALLBACK_BETA]
    assert request["system"][0]["cache_control"] == {"type": "ephemeral"}
    rendered = request["messages"][0]["content"]
    for forbidden in ("payer_archetype", '"flags"', '"provenance"', '"spotlight"'):
        assert forbidden not in rendered


def test_batch_request_uses_high_effort(tmp_path: Path) -> None:
    client = _FakeClient()
    reasoner = ClaudeReasoner(api_key="test", cache_root=tmp_path, client=client)
    assert not reasoner.analyze(_snapshots(), 0).pattern_found
    request = client.messages.calls[0]
    assert request["output_config"] == {"effort": BATCH_EFFORT}
    assert request["output_format"] is BatchInsight


def test_empty_key_never_constructs_client_or_caches_fallback(tmp_path: Path) -> None:
    def forbidden_factory(api_key: str, **_: object) -> Any:
        raise AssertionError(f"client constructed with {api_key!r}")

    reasoner = ClaudeReasoner(
        api_key="",
        cache_root=tmp_path,
        client_factory=forbidden_factory,
    )
    snapshot = _snapshots()[0]
    first = reasoner.propose(snapshot, 0)
    second = reasoner.propose(snapshot, 0)
    assert first == second
    assert reasoner.stats.fallbacks == 2
    assert reasoner.cache.stats.writes == 0
    assert reasoner.cache.stats.hits == 0
    assert not list(tmp_path.rglob("*.json"))


def test_stop_reason_is_checked_before_parsed_output(tmp_path: Path) -> None:
    class Refusal:
        stop_reason = "refusal"
        parsed_was_read = False

        @property
        def parsed_output(self) -> Any:
            self.parsed_was_read = True
            raise AssertionError("parsed output was read after a refusal")

    refusal = Refusal()
    client = _FakeClient()
    client.messages.parse = lambda **kwargs: refusal  # type: ignore[method-assign]
    reasoner = ClaudeReasoner(api_key="test", cache_root=tmp_path, client=client)
    result = reasoner.propose(_snapshots()[0], 0)
    assert result.llm_proposal is not None
    assert result.llm_proposal.diagnosis.startswith("Deterministic Phase 2 fallback")
    assert not refusal.parsed_was_read
    assert reasoner.stats.fallback_reasons == {"IncompleteModelResponse": 1}


def test_api_error_uses_deterministic_fallback(tmp_path: Path) -> None:
    client = _FakeClient()

    def fail(**kwargs: Any) -> Any:
        raise TimeoutError("simulated timeout")

    client.messages.parse = fail  # type: ignore[method-assign]
    reasoner = ClaudeReasoner(api_key="test", cache_root=tmp_path, client=client)
    proposal = reasoner.propose(_snapshots()[0], 0)
    assert proposal.llm_proposal is not None
    assert proposal.llm_proposal.diagnosis.startswith("Deterministic Phase 2 fallback")
    assert reasoner.stats.fallback_reasons == {"TimeoutError": 1}


def test_repeated_api_errors_open_a_run_local_circuit(tmp_path: Path) -> None:
    client = _FakeClient()
    attempts = 0

    def fail(**kwargs: Any) -> Any:
        nonlocal attempts
        attempts += 1
        raise ConnectionError("simulated outage")

    client.messages.parse = fail  # type: ignore[method-assign]
    reasoner = ClaudeReasoner(api_key="test", cache_root=tmp_path, client=client)
    for snapshot in _snapshots()[:5]:
        reasoner.propose(snapshot, 0)
    assert attempts == 3
    assert not reasoner.model_available
    assert reasoner.stats.fallbacks == 5
    assert reasoner.stats.fallback_reasons == {
        "ConnectionError": 3,
        "circuit-open": 2,
    }


def test_deterministic_batch_fallback_and_policy_find_the_seeded_group() -> None:
    batch = generate_batch(42)
    insight = DeterministicBatchFallback().analyze(_snapshots(), 0)
    assert insight.pattern_found
    assert insight.parent_group_id == batch.meta.parent_group_id
    assert insight.invoice_ids == sorted(batch.meta.cluster_invoice_ids)

    verdict = PolicyEngine().adjudicate_batch(insight, 0, Ledger(batch.records))
    assert verdict.verdict is VerdictKind.APPROVED
    assert verdict.suppression_approved
    assert verdict.final_intervention is Intervention.ESCALATE_HUMAN
    assert verdict.rule_source is not None
    assert verdict.rule_source.kind is RuleKind.MERCHANT
    assert verdict.rule_source.verified is None


def test_batch_policy_vetoes_hallucinated_or_partial_scope() -> None:
    batch = generate_batch(42)
    ledger = Ledger(batch.records)
    complete = DeterministicBatchFallback().analyze(_snapshots(), 0)
    hallucinated = complete.model_copy(
        update={"invoice_ids": [*complete.invoice_ids, "not-in-the-ledger"]}
    )
    assert PolicyEngine().adjudicate_batch(hallucinated, 0, ledger).verdict is VerdictKind.VETOED

    partial = complete.model_copy(update={"invoice_ids": complete.invoice_ids[:-1]})
    verdict = PolicyEngine().adjudicate_batch(partial, 0, ledger)
    assert verdict.verdict is VerdictKind.VETOED
    assert "complete open parent group" in verdict.explanation


def test_second_identical_run_is_entirely_disk_cached(tmp_path: Path) -> None:
    """Exercise every due record plus the aggregate call, not one toy lookup."""
    batch = generate_batch(42)
    first_client = _FakeClient()
    first = ClaudeReasoner(api_key="test", cache_root=tmp_path, client=first_client)
    first_result = run_batch(
        batch.records,
        first,
        seed=42,
        run_id="cache-first",
        horizon=1,
        policy=PolicyEngine(),
        batch_reasoner=first,
    )
    assert first.stats.api_calls > 120
    assert first.cache.stats.writes == first.stats.model_successes

    second_client = _FakeClient()
    second = ClaudeReasoner(api_key="test", cache_root=tmp_path, client=second_client)
    second_result = run_batch(
        batch.records,
        second,
        seed=42,
        run_id="cache-second",
        horizon=1,
        policy=PolicyEngine(),
        batch_reasoner=second,
    )
    assert second.stats.api_calls == 0
    assert second.cache.stats.lookups == second.cache.stats.hits
    assert second.cache.stats.hit_rate == 1.0
    assert not compare(first_result.records, second_result.records)
    assert not compare(
        second_result.records,
        replay(batch.records, second_result.log.rows).ledger.records,
    )


def test_batch_insight_is_persisted_beside_unchanged_audit(tmp_path: Path) -> None:
    batch = generate_batch(42)
    reasoner = ClaudeReasoner(api_key="", cache_root=tmp_path / "cache")
    result = run_batch(
        batch.records,
        reasoner,
        seed=42,
        run_id="batch-artifact",
        horizon=1,
        policy=PolicyEngine(),
        batch_reasoner=reasoner,
    )
    assert result.batch_insight is not None
    assert result.batch_insight.policy_verdict.suppression_approved
    assert not result.batch_insight.applied_to_ledger
    out = write_run(result, batch, tmp_path / "run")
    assert (out / "batch-insight.json").exists()
    assert not compare(result.records, replay(batch.records, result.log.rows).ledger.records)


def test_empty_key_phase3_path_does_not_import_anthropic() -> None:
    """Fresh interpreter proves wrapper + batch insight preserve the no-SDK floor."""
    script = """
import builtins
real_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == 'anthropic' or name.startswith('anthropic.'):
        raise AssertionError('LLM SDK reached the empty-key Phase 3 path')
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded
from recoup.generator.generate import generate_batch
from recoup.policy.engine import PolicyEngine
from recoup.reasoner.client import ClaudeReasoner
from recoup.runner.batch import run_batch
batch = generate_batch(42)
reasoner = ClaudeReasoner(api_key='')
result = run_batch(
    batch.records,
    reasoner,
    seed=42,
    run_id='phase3-no-key',
    horizon=1,
    policy=PolicyEngine(),
    batch_reasoner=reasoner,
)
assert len(result.records) == 126
assert result.batch_insight.policy_verdict.suppression_approved
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


def test_cache_only_never_calls_the_api_even_with_a_key(tmp_path: Path) -> None:
    """The demo/replay mode: a configured key must not make the run spend."""
    client = _FakeClient()
    reasoner = ClaudeReasoner(
        api_key="sk-ant-not-used",
        cache_root=tmp_path,
        client=client,
        cache_only=True,
    )
    snapshot = _snapshots()[0]
    reasoner.propose(snapshot, 0)
    reasoner.analyze(_snapshots(), 0)
    assert client.messages.calls == []
    assert reasoner.stats.api_calls == 0
    assert reasoner.stats.fallback_reasons == {"cache-only": 2}
    assert reasoner.cache.stats.writes == 0


def test_a_partially_seeded_cache_cannot_bill_for_the_uncached_rest(tmp_path: Path) -> None:
    """The seeding hazard: N cached entries must not authorise 472-N live calls."""
    snapshots = _snapshots()[:4]
    seeding = ClaudeReasoner(cache_root=tmp_path, client=_FakeClient())
    seeding.propose(snapshots[0], 0)
    assert seeding.cache.stats.writes == 1

    client = _FakeClient()
    guarded = ClaudeReasoner(
        api_key="sk-ant-not-used",
        cache_root=tmp_path,
        client=client,
        cache_only=True,
    )
    for snapshot in snapshots:
        guarded.propose(snapshot, 0)
    assert guarded.cache.stats.hits == 1
    assert client.messages.calls == []
    assert guarded.stats.fallback_reasons == {"cache-only": 3}


def test_max_api_calls_is_a_hard_ceiling_on_spend(tmp_path: Path) -> None:
    client = _FakeClient()
    reasoner = ClaudeReasoner(
        api_key="sk-ant-not-used",
        cache_root=tmp_path,
        client=client,
        max_api_calls=2,
    )
    for snapshot in _snapshots()[:5]:
        reasoner.propose(snapshot, 0)
    assert len(client.messages.calls) == 2
    assert reasoner.stats.api_calls == 2
    assert reasoner.stats.fallback_reasons == {"call-budget-spent": 3}


def test_batch_call_gets_thinking_headroom_and_its_own_timeout(tmp_path: Path) -> None:
    """High effort over the whole book must not truncate into a paid-for error."""
    client = _FakeClient()
    reasoner = ClaudeReasoner(api_key="sk-ant-not-used", cache_root=tmp_path, client=client)
    reasoner.propose(_snapshots()[0], 0)
    reasoner.analyze(_snapshots(), 0)
    record_call, batch_call = client.messages.calls
    assert batch_call["max_tokens"] == BATCH_MAX_TOKENS >= 32768
    assert batch_call["max_tokens"] > record_call["max_tokens"]
    assert batch_call["timeout"] == BATCH_TIMEOUT_SECONDS > record_call["timeout"]


def test_default_client_caps_sdk_retries_below_the_sdk_default(tmp_path: Path) -> None:
    """The SDK default of 2 bills three times for one flaky call."""
    assert DEFAULT_MAX_RETRIES < 2
    seen: dict[str, Any] = {}

    def recording_factory(api_key: str, **kwargs: Any) -> Any:
        seen.update(kwargs)
        return _FakeClient()

    reasoner = ClaudeReasoner(
        api_key="sk-ant-not-used",
        cache_root=tmp_path,
        client_factory=recording_factory,
    )
    reasoner.propose(_snapshots()[0], 0)
    assert seen == {"max_retries": DEFAULT_MAX_RETRIES}
