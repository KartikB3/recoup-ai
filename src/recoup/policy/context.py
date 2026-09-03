"""What a rule is handed, and what it is allowed to hand back. Phase 2.

A small module that exists to break a cycle: `policy.engine` imports the rule
list from `policy.rules`, and every rule module needs the context type and the
verdict constructors. Putting them here means neither imports the other.

The one thing to understand about `RuleContext`
-----------------------------------------------
It carries the `Invoice`, which carries **simulation ground truth** --
`payer_archetype`, `flags`, `provenance`, `spotlight`. The policy engine is
held to the same standard as the reasoner and **must not read any of them**.

That is not squeamishness. `Flag.DISPUTED` is set on all 18 records of the
DISPUTING archetype, but only 12 of those carry a `dispute_description` a
reader could actually see; the other 6 put the objection in prose and nowhere
else. A dispute rule keyed on the flag catches all 18 deterministically, scores
a perfect run, and quietly removes the only thing Phase 3 exists to
demonstrate. Keyed on the observable it catches 12, and the 6 it misses are the
honest measure of what a structured-field rule cannot do.

`tests/test_policy.py` greps this package for those four attribute names, and
for `model_dump`, which would smuggle the lot out in one call. The stronger
check is behavioural and lives in the same file: the agent arm's
false-intervention count must be greater than zero, because a zero means ground
truth leaked in somewhere a grep could not see.

WHAT A RULE MAY READ
    record.state, record.outstanding_paise, record.amount_paise,
    record.free_text, record.contact_ledger, record.payer_id, the dates,
    the proposal, the tick, and payer-level contact counts via the ledger.
WHAT A RULE MAY NOT READ
    record.payer_archetype, record.flags, record.provenance, record.spotlight.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeAlias

from recoup.domain.enums import Intervention, VerdictKind
from recoup.domain.models import Invoice, LLMProposal, Paise, PolicyVerdict, RuleSource, Tick
from recoup.ledger.clock import ticks_for_days
from recoup.ledger.ledger import CONTACT_WINDOW_TICKS, Ledger

#: How intrusive an intervention is, on the only axis the rule order cares
#: about: whether it puts a message in front of a payer, and how heavy that
#: message is.
#:
#: This table is what licenses the engine's single pass. The composition
#: invariant is that **a modification may only reduce contact intensity, never
#: raise it** -- so a rule that has already approved a proposal cannot be
#: violated by a downgrade applied after it, and no rule needs re-running.
#: WAIT, STOP and ESCALATE_HUMAN all sit at zero because none of them reaches
#: the payer; they differ in what they do to the record, which is the ledger's
#: business and not the contact rules'.
CONTACT_INTENSITY: dict[Intervention, int] = {
    Intervention.WAIT: 0,
    Intervention.STOP: 0,
    Intervention.ESCALATE_HUMAN: 0,
    Intervention.SOFT_REMINDER: 1,
    Intervention.PAYMENT_LINK: 2,
    Intervention.PHONE_FOLLOWUP: 3,
}


@dataclass(frozen=True)
class MerchantPolicy:
    """Business configuration. Not regulation, and never rendered as regulation.

    Every default here is a commercial judgement a merchant could reasonably
    set differently. `docs/POLICY-SOURCES.md` carries the table and the
    reasoning; ISS-009 carries the one that matters most, which is that no
    verified regulatory cap on retry attempts exists anywhere, so this project
    does not claim one.
    """

    max_contacts_per_payer: int = 4
    """Contacts to one payer, across ALL their invoices, per rolling window."""

    contact_window_ticks: int = CONTACT_WINDOW_TICKS
    """The rolling window. 30 virtual days."""

    min_contact_spacing_ticks: int = ticks_for_days(3)
    """72 virtual hours between contacts to the same payer, on any invoice."""

    max_links_per_invoice: int = 3
    """Payment links on one invoice before the engine downgrades to a reminder."""

    escalation_threshold_paise: Paise = 5_00_000_00
    """Rs 5,00,000. Above this, automation escalates rather than abandons."""

    link_budget: int | None = None
    """Global payment-link budget for the run. None disables the rule.

    Off by default and ON for live runs only. The 30-link cap is a Razorpay
    test-mode constraint (ISS-001); imposing it on a simulated batch would cap
    the agent at 30 links while the baseline, which bypasses this engine
    entirely, sent 225 -- and the metric table would be measuring a handicap
    rather than a strategy.
    """

    min_batch_group_invoices: int = 3
    """Minimum open invoices before one parent-level escalation is credible."""

    min_batch_group_payers: int = 3
    """Minimum distinct payers required for an account-level pattern."""


@dataclass(frozen=True)
class RuleContext:
    """Everything one rule may look at. See the module docstring for the limits."""

    record: Invoice
    original: Intervention
    """What the proposer asked for. Reported on every verdict."""

    current: Intervention
    """What the proposal has been reduced to so far. Rules judge THIS."""

    tick: Tick
    ledger: Ledger
    config: MerchantPolicy
    links_used: int
    """Payment links already spent in this run, across every record."""

    llm_proposal: LLMProposal | None = None

    def payer_contacts_in_window(self) -> int:
        """Contacts to this payer inside the rolling window, all invoices."""
        floor = max(0, self.tick - self.config.contact_window_ticks)
        return self.ledger.payer_contacts_since(self.record.payer_id, floor)

    def payer_contact_ticks(self) -> list[Tick]:
        """Every tick this payer was contacted on, ascending, all invoices."""
        return sorted(
            attempt.tick
            for other in self.ledger.records
            if other.payer_id == self.record.payer_id
            for attempt in other.contact_ledger.attempts
        )


RuleFn: TypeAlias = Callable[[RuleContext], PolicyVerdict | None]


@dataclass(frozen=True)
class Rule:
    """One rule: its id, and the pure function that decides whether it fires.

    `rule_id` travels onto the audit row and into the dashboard, so it is a
    wire format. Renaming one silently rewrites history.
    """

    rule_id: str
    check: RuleFn


def veto(
    ctx: RuleContext,
    source: RuleSource,
    explanation: str,
    *,
    defer_to_tick: Tick | None = None,
) -> PolicyVerdict:
    """Stop the proposal. Optionally say when it could be reconsidered.

    `defer_to_tick` is what makes a contact-window veto mean "not now" rather
    than "no". Without it the runner pushes the next review by the proposed
    intervention's usual interval -- a whole number of virtual days -- so a
    record blocked at 20:00 returns at 20:00 and stays blocked for the rest of
    the run. See ISS-025.
    """
    return PolicyVerdict(
        verdict=VerdictKind.VETOED,
        original=ctx.original,
        final=None,
        rule_source=source,
        explanation=explanation,
        defer_to_tick=defer_to_tick,
    )


def modify(
    ctx: RuleContext,
    final: Intervention,
    source: RuleSource,
    explanation: str,
) -> PolicyVerdict:
    """Reduce the proposal to something the rule can live with.

    Raises if the replacement is more intrusive than what it replaces. That is
    the composition invariant, enforced where it is easy to get wrong rather
    than only in a test: a modification that raised intensity could violate a
    rule that had already passed, and the engine's single pass would not catch
    it.
    """
    if CONTACT_INTENSITY[final] > CONTACT_INTENSITY[ctx.current]:
        raise ValueError(
            f"modification raises contact intensity: {ctx.current} -> {final}. "
            "Rules may only reduce."
        )
    return PolicyVerdict(
        verdict=VerdictKind.MODIFIED,
        original=ctx.original,
        final=final,
        rule_source=source,
        explanation=explanation,
    )
