"""Seeded outcome resolution. Phase 1.

P(pay), P(reply) and P(dispute), conditioned on archetype x intervention x
days-overdue. The same seed produces the same outcomes, so the baseline and
agent arms face an identical world. That is what makes the comparison in build
spec section 7a mean anything.

The key rule: what goes in the key, and what goes in the threshold
-----------------------------------------------------------------
Every draw is a uniform derived by hashing

    (seed, invoice_id, tick, channel)

and **nothing else**. Not the state, not the intervention, not how many times
the payer has been contacted. Those all differ between the two arms, and the
moment one of them enters the key the arms stop sharing a world: the agent
would face different luck from the baseline and the comparison would be
measuring the random number generator.

Everything conditional -- archetype, intervention potency, days overdue,
contact fatigue -- goes into the **threshold** the uniform is compared against.
Same dice, different odds. That is the whole design.

Three channels, drawn independently
-----------------------------------
``SPONTANEOUS``
    Drawn every tick for every non-terminal record, in both arms, whether or
    not anybody chased it. A payer on a 45-day cycle pays when their cycle comes
    round. Without this channel a record that is never contacted can never pay,
    WAIT and STOP become pure concessions, and the agent can never win by
    correctly declining to act -- which is precisely the behaviour this project
    exists to demonstrate. See the ledger docstring on why PAID is reachable
    from EXHAUSTED.

``RESPONSE``
    Drawn only on ticks where a contact was actually made. This is the lift (or
    the harm) that chasing produces on top of the spontaneous rate.

``PROMISE``
    Drawn when a promise falls due: honoured, or broken.

Because the channels are separate hashes, adding contact to a record does not
disturb its spontaneous draws. A record chased on tick 20 has exactly the
same spontaneous sequence as the same record left alone.

NO WALL CLOCK, and no floats in money. Amounts are integer paise throughout;
probabilities are floats and never touch a rupee value.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from recoup.domain.enums import Archetype, Intervention, OutcomeKind
from recoup.domain.interventions import spec
from recoup.domain.models import Invoice, OutcomeRecord, Tick
from recoup.ledger.clock import DEFAULT_HORIZON, virtual_date

#: Channel names. Part of the hash key, so these strings are a wire format:
#: changing one silently reshuffles every outcome in the project.
CHANNEL_SPONTANEOUS = "spontaneous"
CHANNEL_RESPONSE = "response"
CHANNEL_PROMISE = "promise"
CHANNEL_AMOUNT = "amount"

#: Days overdue at which the archetype table's quoted cumulative rates hold.
#: Records further past due pay more slowly; see `_overdue_multiplier`.
REFERENCE_DAYS_OVERDUE: int = 30

#: Floor on the overdue decay. Even very old paper retains some chance of
#: settling, and a zero here would make ageing records unrecoverable by
#: construction rather than by behaviour.
OVERDUE_FLOOR: float = 0.35

#: Contacts within the fatigue window after which further chasing is actively
#: counterproductive rather than merely useless.
FATIGUE_ONSET: int = 2

#: Per-contact multiplier applied to payment odds beyond `FATIGUE_ONSET`, and
#: the matching additive rise in complaint risk.
FATIGUE_PAY_DECAY: float = 0.82
FATIGUE_COMPLAINT_STEP: float = 0.035

#: Ceiling on the total mass of the response ladder. Below 1.0 on purpose: a
#: contact must always retain some chance of producing nothing at all, however
#: potent the intervention. A payer who is guaranteed to react is not a payer.
_MAX_RESPONSE_MASS: float = 0.95


def uniform(seed: int, invoice_id: str, tick: Tick, channel: str) -> float:
    """A reproducible uniform in [0, 1) for one record, tick and channel.

    blake2b rather than `hash()`: the stream must not depend on
    `PYTHONHASHSEED`, and must be identical on every machine that reruns the
    batch. The key deliberately excludes everything arm-dependent -- see the
    module docstring.
    """
    key = f"{seed}|{invoice_id}|{tick}|{channel}".encode()
    digest = hashlib.blake2b(key, digest_size=8).digest()
    return int.from_bytes(digest, "big") / 2.0**64


@dataclass(frozen=True)
class SpontaneousOdds:
    """How a payer behaves when nobody is chasing them.

    `cumulative_28d` is the probability the record settles on its own over a
    full 112-tick run at `REFERENCE_DAYS_OVERDUE`. Quoting the table in
    cumulative terms keeps it readable; `per_tick` does the conversion.
    """

    cumulative_28d: float
    partial_share: float
    """Share of spontaneous payments that arrive short of the full value."""

    def per_tick(self) -> float:
        """Per-tick hazard giving `cumulative_28d` over the default horizon."""
        return 1.0 - math.pow(1.0 - self.cumulative_28d, 1.0 / DEFAULT_HORIZON)


@dataclass(frozen=True)
class ResponseOdds:
    """What one contact produces, before intervention and fatigue adjustment.

    These are conditional on a contact having been made at this tick, and are
    read in the fixed field order below. Whatever mass is left over after
    intervention potency and fatigue have been applied is NO_RESPONSE; if the
    adjustments push the total past `_MAX_RESPONSE_MASS`, `resolve_response`
    rescales rather than letting the tail of the ladder be clipped.
    """

    paid_full: float
    paid_partial: float
    promised: float
    replied: float
    dispute_raised: float
    complaint: float

    def total(self) -> float:
        """Probability that anything at all comes back."""
        return (
            self.paid_full
            + self.paid_partial
            + self.promised
            + self.replied
            + self.dispute_raised
            + self.complaint
        )


@dataclass(frozen=True)
class BehaviourProfile:
    """One archetype's response to the world and to being chased."""

    spontaneous: SpontaneousOdds
    response: ResponseOdds
    promise_kept: float
    """Probability a promise, once made, is honoured when it falls due."""


#: The behaviour table. Every number here is a modelling choice, not a measured
#: quantity, and docs/SEED-DISTRIBUTION.md says so in those words. What matters
#: for the demonstration is the ORDERING between archetypes, which is the part
#: a reader can sanity-check:
#:
#:   * RELIABLE_BUT_SLOW pays on its own with high probability and barely
#:     responds to chasing. Contacting them spends budget and buys nothing.
#:     This is the population the agent wins on by choosing WAIT.
#:   * CHRONIC_LATE is the opposite: chasing genuinely works, which is why the
#:     naive baseline is not a straw man and scores respectably.
#:   * DISPUTING converts contact into a formal dispute. Chasing them is
#:     actively harmful and creates human-queue work.
#:   * DISTRESSED pays LESS when pressed and complains more. Pressure is
#:     counterproductive; time and a human do better.
#:   * SILENT mostly does not answer, so contact is close to a pure cost.
#:   * PAID_UNRECONCILED settles almost immediately on its own, because the
#:     money already left the payer. Every contact to one is a false
#:     intervention, and the metric table counts it as one.
PROFILES: dict[Archetype, BehaviourProfile] = {
    Archetype.RELIABLE_BUT_SLOW: BehaviourProfile(
        spontaneous=SpontaneousOdds(cumulative_28d=0.85, partial_share=0.04),
        response=ResponseOdds(
            paid_full=0.030,
            paid_partial=0.010,
            promised=0.150,
            replied=0.300,
            dispute_raised=0.005,
            complaint=0.020,
        ),
        promise_kept=0.88,
    ),
    Archetype.CHRONIC_LATE: BehaviourProfile(
        spontaneous=SpontaneousOdds(cumulative_28d=0.42, partial_share=0.18),
        response=ResponseOdds(
            paid_full=0.110,
            paid_partial=0.070,
            promised=0.240,
            replied=0.220,
            dispute_raised=0.020,
            complaint=0.030,
        ),
        promise_kept=0.58,
    ),
    Archetype.DISPUTING: BehaviourProfile(
        spontaneous=SpontaneousOdds(cumulative_28d=0.10, partial_share=0.45),
        response=ResponseOdds(
            paid_full=0.015,
            paid_partial=0.030,
            promised=0.050,
            replied=0.180,
            dispute_raised=0.260,
            complaint=0.045,
        ),
        promise_kept=0.40,
    ),
    Archetype.DISTRESSED: BehaviourProfile(
        spontaneous=SpontaneousOdds(cumulative_28d=0.16, partial_share=0.55),
        response=ResponseOdds(
            paid_full=0.020,
            paid_partial=0.055,
            promised=0.170,
            replied=0.230,
            dispute_raised=0.020,
            complaint=0.090,
        ),
        promise_kept=0.34,
    ),
    Archetype.SILENT: BehaviourProfile(
        spontaneous=SpontaneousOdds(cumulative_28d=0.30, partial_share=0.20),
        response=ResponseOdds(
            paid_full=0.030,
            paid_partial=0.020,
            promised=0.045,
            replied=0.070,
            dispute_raised=0.010,
            complaint=0.020,
        ),
        promise_kept=0.45,
    ),
    Archetype.PAID_UNRECONCILED: BehaviourProfile(
        spontaneous=SpontaneousOdds(cumulative_28d=0.95, partial_share=0.02),
        response=ResponseOdds(
            paid_full=0.040,
            paid_partial=0.005,
            promised=0.030,
            replied=0.420,
            dispute_raised=0.030,
            complaint=0.070,
        ),
        promise_kept=0.80,
    ),
}


#: How each intervention scales the response odds. Applied to the threshold,
#: never to the key.
#:
#: A payment link removes the friction between intent and payment, so it lifts
#: the paying branches hardest. A phone call gets a human talking -- more
#: promises and replies, but also the most intrusive channel and so the highest
#: annoyance. A soft reminder is the neutral reference.
@dataclass(frozen=True)
class InterventionPotency:
    """Multipliers on the response odds for one intervention."""

    pay: float
    promise: float
    reply: float
    dispute: float
    complaint: float


POTENCY: dict[Intervention, InterventionPotency] = {
    Intervention.SOFT_REMINDER: InterventionPotency(
        pay=1.00, promise=1.00, reply=1.00, dispute=1.00, complaint=1.00
    ),
    Intervention.PAYMENT_LINK: InterventionPotency(
        pay=1.65, promise=0.85, reply=0.90, dispute=1.05, complaint=1.15
    ),
    Intervention.PHONE_FOLLOWUP: InterventionPotency(
        pay=1.20, promise=1.70, reply=1.45, dispute=1.30, complaint=1.60
    ),
}


def _overdue_multiplier(days_overdue: int) -> float:
    """Older paper settles more slowly. Bounded below by `OVERDUE_FLOOR`.

    Halves roughly every 90 days past the reference point, which is a modelling
    choice chosen to be visible over a 28-day run without dominating it.
    """
    if days_overdue <= REFERENCE_DAYS_OVERDUE:
        return 1.0
    excess = days_overdue - REFERENCE_DAYS_OVERDUE
    return max(OVERDUE_FLOOR, math.pow(0.5, excess / 90.0))


def _fatigue(recent_contacts: int) -> tuple[float, float]:
    """Cost of having already chased this payer. (pay multiplier, complaint add).

    Nothing happens for the first `FATIGUE_ONSET` contacts: a couple of
    reminders is normal commercial practice. Past that, each further contact
    lowers the odds of payment and raises the odds of a complaint. This is the
    mechanism by which the naive every-N-days baseline damages its own book,
    and it is the reason contact count belongs in the threshold rather than in
    the key -- the two arms must be able to differ here.
    """
    excess = max(0, recent_contacts - FATIGUE_ONSET)
    if excess == 0:
        return 1.0, 0.0
    return FATIGUE_PAY_DECAY**excess, FATIGUE_COMPLAINT_STEP * excess


def days_overdue(record: Invoice, tick: Tick) -> int:
    """Days past due at a tick. Virtual time only."""
    return (virtual_date(tick) - record.due_on).days


@dataclass(frozen=True)
class Adjudicator:
    """Resolves what the world does back. Deterministic in the run seed.

    Holds no mutable state: every answer is a pure function of the seed, the
    record, the tick and the channel. Two arms sharing a seed therefore share a
    world, which is the precondition for the comparison meaning anything.
    """

    seed: int

    # -- spontaneous ---------------------------------------------------------

    def resolve_spontaneous(self, record: Invoice, tick: Tick) -> OutcomeRecord | None:
        """Did this record settle on its own this tick? Called for EVERY record.

        Independent of anything either arm did. A record nobody has touched
        draws exactly the same sequence as one being chased weekly.
        """
        profile = PROFILES[record.payer_archetype]
        threshold = profile.spontaneous.per_tick() * _overdue_multiplier(days_overdue(record, tick))
        draw = uniform(self.seed, record.invoice_id, tick, CHANNEL_SPONTANEOUS)
        if draw >= threshold:
            return None

        outstanding = record.amount_paise - record.recovered_paise
        if outstanding <= 0:
            return None

        # Reuse the draw's position within the threshold to decide full versus
        # partial, rather than spending a second hash on it.
        position = draw / threshold if threshold > 0 else 1.0
        if position < profile.spontaneous.partial_share:
            return OutcomeRecord(
                kind=OutcomeKind.PAID_PARTIAL,
                amount_paise=self._partial_amount(record, tick, outstanding),
                detail="settled in part on the payer's own cycle",
            )
        return OutcomeRecord(
            kind=OutcomeKind.PAID_FULL,
            amount_paise=outstanding,
            detail="settled on the payer's own cycle, unprompted",
        )

    # -- response ------------------------------------------------------------

    def resolve_response(
        self,
        record: Invoice,
        tick: Tick,
        intervention: Intervention,
        *,
        recent_contacts: int,
    ) -> OutcomeRecord:
        """What came back from one contact. Never returns None: silence is an outcome.

        `recent_contacts` counts contacts to this PAYER inside the fatigue
        window, across all their invoices, and is supplied by the ledger. It
        enters the threshold, never the key.
        """
        details = spec(intervention)
        if not details.is_contact:
            raise ValueError(f"{intervention} makes no contact and has no response to resolve")

        profile = PROFILES[record.payer_archetype]
        odds = profile.response
        potency = POTENCY[intervention]
        decay = _overdue_multiplier(days_overdue(record, tick))
        pay_fatigue, complaint_add = _fatigue(recent_contacts)

        # Ordered so that the ladder is stable: adding a branch later must not
        # reshuffle the ones above it.
        ladder: list[tuple[OutcomeKind, float]] = [
            (OutcomeKind.PAID_FULL, odds.paid_full * potency.pay * decay * pay_fatigue),
            (OutcomeKind.PAID_PARTIAL, odds.paid_partial * potency.pay * decay * pay_fatigue),
            (OutcomeKind.PROMISED, odds.promised * potency.promise * pay_fatigue),
            (OutcomeKind.REPLIED, odds.replied * potency.reply),
            (OutcomeKind.DISPUTE_RAISED, odds.dispute_raised * potency.dispute),
            (OutcomeKind.COMPLAINT, odds.complaint * potency.complaint + complaint_add),
        ]

        # A phone call to an already-fatigued payer can push the branch masses
        # past 1.0. Left alone that silently truncates the tail of the ladder --
        # COMPLAINT, the branch fatigue is supposed to be RAISING, would be the
        # one that gets clipped, and NO_RESPONSE would become unreachable.
        # Rescale instead, so the shape is preserved and silence stays possible.
        mass = sum(probability for _, probability in ladder)
        if mass > _MAX_RESPONSE_MASS:
            scale = _MAX_RESPONSE_MASS / mass
            ladder = [(kind, probability * scale) for kind, probability in ladder]

        draw = uniform(self.seed, record.invoice_id, tick, CHANNEL_RESPONSE)
        cursor = 0.0
        for kind, probability in ladder:
            cursor += probability
            if draw < cursor:
                return self._response_outcome(record, tick, kind, intervention)
        return OutcomeRecord(kind=OutcomeKind.NO_RESPONSE, detail="no reply to the approach")

    def _response_outcome(
        self,
        record: Invoice,
        tick: Tick,
        kind: OutcomeKind,
        intervention: Intervention,
    ) -> OutcomeRecord:
        """Attach money and a human-readable detail to a resolved response."""
        outstanding = max(0, record.amount_paise - record.recovered_paise)
        match kind:
            case OutcomeKind.PAID_FULL:
                return OutcomeRecord(
                    kind=kind,
                    amount_paise=outstanding,
                    detail=f"settled in full after {intervention.value}",
                )
            case OutcomeKind.PAID_PARTIAL:
                return OutcomeRecord(
                    kind=kind,
                    amount_paise=self._partial_amount(record, tick, outstanding),
                    detail=f"part payment after {intervention.value}",
                )
            case OutcomeKind.PROMISED:
                return OutcomeRecord(kind=kind, detail=self._promise_phrase(record, tick))
            case OutcomeKind.DISPUTE_RAISED:
                return OutcomeRecord(
                    kind=kind,
                    detail="the standing objection was filed as a formal dispute",
                )
            case OutcomeKind.COMPLAINT:
                return OutcomeRecord(
                    kind=kind,
                    detail="the payer complained about the frequency of contact",
                )
            case _:
                return OutcomeRecord(kind=kind, detail="acknowledged, nothing committed")

    # -- promises ------------------------------------------------------------

    def resolve_promise(self, record: Invoice, tick: Tick) -> OutcomeRecord | None:
        """Honoured or broken, on the tick a promise falls due.

        Returns None when there is no promise, or it is not due yet. A promise
        whose phrase did not resolve to a tick has no due date and is never
        adjudicated here -- see `clock.resolve_promise_phrase`.
        """
        if record.promise_due_tick is None or tick < record.promise_due_tick:
            return None

        profile = PROFILES[record.payer_archetype]
        kept = profile.promise_kept * _overdue_multiplier(days_overdue(record, tick))
        draw = uniform(self.seed, record.invoice_id, tick, CHANNEL_PROMISE)
        if draw < kept:
            outstanding = max(0, record.amount_paise - record.recovered_paise)
            return OutcomeRecord(
                kind=OutcomeKind.PAID_FULL,
                amount_paise=outstanding,
                detail=f"honoured the commitment: {record.promise_phrase}",
            )
        return OutcomeRecord(
            kind=OutcomeKind.PROMISE_BROKEN,
            detail=f"the commitment passed unmet: {record.promise_phrase}",
        )

    # -- helpers -------------------------------------------------------------

    def _partial_amount(self, record: Invoice, tick: Tick, outstanding: int) -> int:
        """A part payment, in integer paise. Between a third and 85% of the balance.

        Integer arithmetic throughout: the fraction is chosen as whole percent
        so no float ever reaches a money value.
        """
        draw = uniform(self.seed, record.invoice_id, tick, CHANNEL_AMOUNT)
        percent = 33 + int(draw * 52)
        return max(1, outstanding * percent // 100)

    def _promise_phrase(self, record: Invoice, tick: Tick) -> str:
        """The words the payer used. Deliberately vague for the vaguer archetypes.

        The reasoner will later be asked to extract a phrase like this and quote
        it; the clock, not the model, turns it into a date. Some of these
        resolve to no date at all, which is the point.
        """
        draw = uniform(self.seed, record.invoice_id, tick, CHANNEL_AMOUNT)
        vague = (
            "we will release it in due course",
            "after the festival break",
            "once the current review concludes",
            "shortly",
        )
        firm = (
            "in the next payment run, on the 25th",
            "by Friday",
            "within 7 working days",
            "before month end",
            "next week",
        )
        pool = vague if record.payer_archetype in _VAGUE_PROMISERS else firm
        return pool[int(draw * len(pool)) % len(pool)]


#: Archetypes whose promises tend not to name a date. Their commitments
#: therefore resolve to no due tick, and the caller must not treat them as a
#: reason to suppress contact. See `clock.resolve_promise_phrase`.
_VAGUE_PROMISERS: frozenset[Archetype] = frozenset(
    {Archetype.DISPUTING, Archetype.DISTRESSED, Archetype.SILENT}
)
