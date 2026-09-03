"""Anthropic structured-output proposer with cache and deterministic fallback.

The SDK import is lazy and occurs only after a truthy API key and a disk-cache
miss.  The empty-key CI path therefore does not merely avoid a network call; it
does not import the LLM SDK at all.  Successful model output is cached, while
API errors, truncation, refusals, parse failures, and missing credentials all
fall back to the deterministic components.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from recoup.domain.enums import Arm
from recoup.domain.models import LLMProposal, Tick
from recoup.reasoner.batch_insight import DeterministicBatchFallback
from recoup.reasoner.cache import DEFAULT_CACHE_ROOT, ReasonerCache
from recoup.reasoner.fallback import DeterministicFallback
from recoup.reasoner.prompts import (
    BATCH_PROMPT_VERSION,
    BATCH_SYSTEM_PROMPT,
    RECORD_PROMPT_VERSION,
    RECORD_SYSTEM_PROMPT,
    batch_user_prompt,
    cached_system_block,
    record_user_prompt,
)
from recoup.reasoner.schemas import (
    BatchInsight,
    batch_insight_json_schema,
    proposal_json_schema,
)
from recoup.runner.batch import Proposal

MODEL = "claude-opus-5"
SERVER_FALLBACK_BETA = "server-side-fallback-2026-07-01"
RECORD_EFFORT = "medium"
BATCH_EFFORT = "high"
RECORD_MAX_TOKENS = 4096
# Adaptive thinking bills against max_tokens, and the batch call reasons over
# the whole ~58k-token opening book at high effort.  8192 truncated it into an
# IncompleteModelResponse: the call is paid for and nothing is cached.
BATCH_MAX_TOKENS = 32768
DEFAULT_TIMEOUT_SECONDS = 60.0
# The same call is non-streaming, so it must not race the record timeout.
BATCH_TIMEOUT_SECONDS = 600.0
DEFAULT_FAILURE_LIMIT = 3
# The SDK default is 2, so one flaky call bills three times.  The circuit
# breaker below is the intended failure control, not the retry budget.
DEFAULT_MAX_RETRIES = 1

ClientFactory = Callable[..., Any]
ParsedOutput = TypeVar("ParsedOutput", LLMProposal, BatchInsight)


class IncompleteModelResponse(RuntimeError):
    """The API returned a response whose stop reason is unsafe to consume."""


@dataclass
class ReasonerStats:
    """Model/fallback counters kept separate from the disk-cache counters."""

    api_calls: int = 0
    model_successes: int = 0
    fallbacks: int = 0
    fallback_reasons: dict[str, int] = field(default_factory=dict)

    def record_fallback(self, reason: str) -> None:
        self.fallbacks += 1
        self.fallback_reasons[reason] = self.fallback_reasons.get(reason, 0) + 1


def _anthropic_client(api_key: str, *, max_retries: int = DEFAULT_MAX_RETRIES) -> Any:
    """Import the SDK only on the live model path."""
    import anthropic

    return anthropic.Anthropic(api_key=api_key, max_retries=max_retries)


class ClaudeReasoner:
    """Satisfy both the per-record and aggregate snapshot-only protocols."""

    name = "claude-opus-5-structured"
    arm = Arm.AGENT

    def __init__(
        self,
        *,
        api_key: str | None = None,
        cache_root: Path = DEFAULT_CACHE_ROOT,
        client: Any | None = None,
        client_factory: ClientFactory = _anthropic_client,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        batch_timeout_seconds: float = BATCH_TIMEOUT_SECONDS,
        failure_limit: int = DEFAULT_FAILURE_LIMIT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        cache_only: bool = False,
        max_api_calls: int | None = None,
    ) -> None:
        if failure_limit < 1:
            raise ValueError("failure_limit must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")
        if max_api_calls is not None and max_api_calls < 0:
            raise ValueError("max_api_calls must not be negative")
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "") if api_key is None else api_key
        self.cache = ReasonerCache(cache_root)
        self.stats = ReasonerStats()
        self._client = client
        self._client_factory = client_factory
        self._timeout_seconds = timeout_seconds
        self._batch_timeout_seconds = batch_timeout_seconds
        self._failure_limit = failure_limit
        self._max_retries = max_retries
        self._cache_only = cache_only
        self._max_api_calls = max_api_calls
        self._consecutive_failures = 0
        self._circuit_open = False
        self._record_fallback = DeterministicFallback()
        self._batch_fallback = DeterministicBatchFallback()

    @property
    def model_available(self) -> bool:
        """A supplied test client or a truthy key permits the model path.

        ``cache_only`` and ``max_api_calls`` are spend guards: a partially
        seeded cache would otherwise let one ordinary run bill for every
        record it has no entry for.
        """
        if self._cache_only or self._circuit_open or self._call_budget_spent:
            return False
        return self._client is not None or bool(self.api_key)

    @property
    def _call_budget_spent(self) -> bool:
        return self._max_api_calls is not None and self.stats.api_calls >= self._max_api_calls

    def propose(self, snapshot: dict[str, Any], tick: Tick) -> Proposal:
        """Return cached/model output, or the exact Phase 2 fallback proposal."""
        contract = self._record_contract()
        cached = self.cache.get(
            "records",
            snapshot,
            contract=contract,
            output_type=LLMProposal,
        )
        if cached is not None:
            return Proposal(intervention=cached.intervention, llm_proposal=cached)

        if not self.model_available:
            self.stats.record_fallback(self._unavailable_reason())
            return self._record_fallback.propose(snapshot, tick)

        try:
            output = self._parse(
                output_type=LLMProposal,
                effort=RECORD_EFFORT,
                max_tokens=RECORD_MAX_TOKENS,
                system_prompt=RECORD_SYSTEM_PROMPT,
                user_prompt=record_user_prompt(snapshot),
                timeout=self._timeout_seconds,
            )
        except Exception as exc:
            self._record_api_failure(exc)
            return self._record_fallback.propose(snapshot, tick)

        self.cache.put("records", snapshot, output, contract=contract)
        return Proposal(intervention=output.intervention, llm_proposal=output)

    def analyze(self, snapshots: list[dict[str, Any]], tick: Tick) -> BatchInsight:
        """Run the one aggregate call at high effort with the same safety net."""
        ordered = sorted(snapshots, key=lambda item: str(item["invoice_id"]))
        contract = self._batch_contract()
        cached = self.cache.get(
            "batch",
            ordered,
            contract=contract,
            output_type=BatchInsight,
        )
        if cached is not None:
            return cached

        if not self.model_available:
            self.stats.record_fallback(self._unavailable_reason())
            return self._batch_fallback.analyze(ordered, tick)

        try:
            output = self._parse(
                output_type=BatchInsight,
                effort=BATCH_EFFORT,
                max_tokens=BATCH_MAX_TOKENS,
                system_prompt=BATCH_SYSTEM_PROMPT,
                user_prompt=batch_user_prompt(ordered),
                timeout=self._batch_timeout_seconds,
            )
        except Exception as exc:
            self._record_api_failure(exc)
            return self._batch_fallback.analyze(ordered, tick)

        self.cache.put("batch", ordered, output, contract=contract)
        return output

    def _parse(
        self,
        *,
        output_type: type[ParsedOutput],
        effort: str,
        max_tokens: int,
        system_prompt: str,
        user_prompt: str,
        timeout: float,
    ) -> ParsedOutput:
        """Make one verified SDK call and inspect stop_reason before output."""
        client = self._get_client()
        self.stats.api_calls += 1
        response = client.beta.messages.parse(
            model=MODEL,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            system=cached_system_block(system_prompt),
            messages=[{"role": "user", "content": user_prompt}],
            output_format=output_type,
            fallbacks="default",
            betas=[SERVER_FALLBACK_BETA],
            timeout=timeout,
        )
        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason != "end_turn":
            raise IncompleteModelResponse(f"model stopped with {stop_reason!r}")
        parsed = getattr(response, "parsed_output", None)
        if parsed is None:
            raise IncompleteModelResponse("model returned no parsed output")
        validated = output_type.model_validate(parsed)
        self._consecutive_failures = 0
        self.stats.model_successes += 1
        return validated

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = self._client_factory(self.api_key, max_retries=self._max_retries)
        return self._client

    def _record_api_failure(self, exc: Exception) -> None:
        """Fall back and open a run-local circuit after repeated failures."""
        self._consecutive_failures += 1
        self.stats.record_fallback(type(exc).__name__)
        if self._consecutive_failures >= self._failure_limit:
            self._circuit_open = True

    def _unavailable_reason(self) -> str:
        if self._cache_only:
            return "cache-only"
        if self._circuit_open:
            return "circuit-open"
        if self._call_budget_spent:
            return "call-budget-spent"
        return "missing-api-key"

    @staticmethod
    def _record_contract() -> dict[str, Any]:
        return {
            "model": MODEL,
            "effort": RECORD_EFFORT,
            "max_tokens": RECORD_MAX_TOKENS,
            "prompt_version": RECORD_PROMPT_VERSION,
            "system_prompt": RECORD_SYSTEM_PROMPT,
            "schema": proposal_json_schema(),
            "server_fallback_beta": SERVER_FALLBACK_BETA,
        }

    @staticmethod
    def _batch_contract() -> dict[str, Any]:
        return {
            "model": MODEL,
            "effort": BATCH_EFFORT,
            "max_tokens": BATCH_MAX_TOKENS,
            "prompt_version": BATCH_PROMPT_VERSION,
            "system_prompt": BATCH_SYSTEM_PROMPT,
            "schema": batch_insight_json_schema(),
            "server_fallback_beta": SERVER_FALLBACK_BETA,
        }


ReasonerClient = ClaudeReasoner
