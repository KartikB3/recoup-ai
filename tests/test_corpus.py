"""The free-text corpus. Phase 1.

These tests read TEMPLATE SOURCE, not rendered output. That distinction is the
whole value of the file: a banned word sitting in a slot value that seed 42
happens never to draw would sail through any check that only inspects a
generated batch, and would then surface on somebody else's seed -- or on the
demo video.

The corpus is the highest-leverage artifact in the build (CLAUDE.md). If it
degrades, the project quietly becomes a rules engine with an API bill, and
nothing else in the test suite would notice.
"""

from __future__ import annotations

import random

import pytest

from recoup.domain.enums import Archetype, FreeTextKind
from recoup.generator.freetext import (
    BANNED_IN_CLUSTER,
    RESERVED_SLOTS,
    Corpus,
    Template,
    render,
)

#: A filled-in value for every reserved slot, so `render` can be exercised on
#: templates the current seed does not happen to select.
DUMMY_RESERVED: dict[str, str] = {
    "invoice_no": "ASH-2026-0001",
    "payer_name": "Example Traders Pvt Ltd",
    "contact_name": "A. Contact",
    "contact_role": "Manager - Accounts",
    "city": "Pune",
    "merchant_short": "Ashwatth",
    "merchant_legal": "Ashwatth Industrial Supplies Pvt Ltd",
    "amount_rupees": "1,23,456",
    "days_overdue": "31",
}


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    """The corpus, loaded once."""
    return Corpus.load()


def _slot_text(template: Template) -> str:
    """Every word a template could ever emit: body, subjects and all slot values."""
    parts = [template.text, *template.subjects]
    for values in template.slots.values():
        parts.extend(values)
    return "\n".join(parts).lower()


def test_corpus_is_large_enough_to_matter(corpus: Corpus) -> None:
    """CLAUDE.md asks for 25-30 templates. Fewer than that and the text is wallpaper."""
    assert len(corpus.templates) >= 30, f"only {len(corpus.templates)} templates"


def test_every_kind_is_populated(corpus: Corpus) -> None:
    """A free-text surface with no templates would silently emit nothing."""
    for kind in FreeTextKind:
        assert [t for t in corpus.templates if t.kind is kind], f"no templates for {kind}"


def test_template_ids_are_unique(corpus: Corpus) -> None:
    """Ids are how provenance is recorded, so a duplicate corrupts the seed docs."""
    ids = [t.id for t in corpus.templates]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("word", BANNED_IN_CLUSTER)
def test_cluster_pool_never_names_the_cause(corpus: Corpus, word: str) -> None:
    """No banned word anywhere in the CLUSTER pool -- body, subject OR slot value.

    Naming the centralisation turns the batch-level insight (build spec 7b)
    into a keyword search and destroys the only claim in this project that the
    LLM does something a lookup table cannot.
    """
    offenders = [t.id for t in corpus.templates if t.pool == "CLUSTER" and word in _slot_text(t)]
    assert not offenders, f"banned word {word!r} appears in {offenders}"


def test_every_template_renders(corpus: Corpus) -> None:
    """Render all of them once. A malformed template must fail the build, not the demo.

    `render` raises on an undeclared placeholder rather than emitting a literal
    `{slot}`. Without this test that guard only ever runs on the templates the
    current seed happens to draw.
    """
    rng = random.Random("corpus-render-check")
    for template in corpus.templates:
        rendering = render(template, rng, DUMMY_RESERVED)
        assert rendering.body.strip(), f"{template.id} rendered empty"
        assert "{" not in rendering.body, f"{template.id} left an unfilled slot"
        if template.subjects:
            assert rendering.subject
            assert "{" not in rendering.subject


def test_templates_only_reference_declared_or_reserved_slots(corpus: Corpus) -> None:
    """Placeholders must resolve from the template's own slots or the reserved set."""
    for template in corpus.templates:
        unknown = template.placeholders() - RESERVED_SLOTS - set(template.slots)
        assert not unknown, f"{template.id} references {sorted(unknown)}"


def test_no_slot_list_is_empty(corpus: Corpus) -> None:
    """An empty slot list makes `rng.choice` raise deep inside generation."""
    for template in corpus.templates:
        for name, values in template.slots.items():
            assert values, f"{template.id}.{name} has no values"


def test_the_batch_insight_cannot_be_read_off_a_single_record() -> None:
    """At most two of the nine cluster records may carry a STRONG hint.

    This replaces an earlier test that tried to catch signal leakage
    generically, by flagging any template containing the words of its own
    signal tag. That heuristic was noise: it fired on `PN-09-tds` for saying
    "TDS deduction" and on `ER-03-already-remitted` for saying the payer had
    already paid -- both of which are exactly what those payers would write,
    and both of which are only readable in PROSE, which is the entire point.
    A note is not disqualified by being clear; it is disqualified by putting
    the answer in a structured field, and none of them do.

    What genuinely has to hold is narrower and is asserted here plus in
    `test_cluster_pool_never_names_the_cause`: no cluster record may let a
    reader skip the cross-record reasoning. Two STRONG hints out of nine means
    the other seven have to be connected by co-occurrence -- one parent group,
    one quiet week -- rather than by reading the loudest note twice.
    """
    from recoup.generator.archetypes import CLUSTER_HINT_PLAN, CLUSTER_SIZE

    assert len(CLUSTER_HINT_PLAN) == CLUSTER_SIZE
    strong = [s for s in CLUSTER_HINT_PLAN if s == "STRONG"]
    silent = [s for s in CLUSTER_HINT_PLAN if s == "NONE"]
    assert len(strong) <= 2, f"{len(strong)} strong hints makes the insight a lookup"
    assert silent, "at least one cluster record must say nothing at all"


def test_cluster_hints_are_graded(corpus: Corpus) -> None:
    """The CLUSTER pool must offer all three strengths, with enough of each.

    Nine cluster records draw from these bands and must not be forced to repeat
    a template: two records need STRONG, three need MEDIUM, two need WEAK. If a
    band is thinner than its demand, the generator's `_without` fallback fires
    and two of the nine read as copy-paste -- which is precisely the passage a
    judge looks at hardest.
    """
    for kind in (FreeTextKind.PAYER_NOTE, FreeTextKind.EMAIL_REPLY):
        pool = [t for t in corpus.templates if t.pool == "CLUSTER" and t.kind is kind]
        by_strength = {
            s: [t.id for t in pool if t.strength == s] for s in ("STRONG", "MEDIUM", "WEAK")
        }
        assert len(by_strength["STRONG"]) >= 2, f"{kind}: {by_strength}"
        assert len(by_strength["MEDIUM"]) >= 3, f"{kind}: {by_strength}"
        assert len(by_strength["WEAK"]) >= 2, f"{kind}: {by_strength}"


def test_general_pool_covers_every_archetype(corpus: Corpus) -> None:
    """Every archetype must have notes and emails available, or its records go mute."""
    for archetype in Archetype:
        for kind in (FreeTextKind.PAYER_NOTE, FreeTextKind.EMAIL_REPLY):
            assert corpus.select(kind, archetype), f"no {kind} for {archetype}"


def test_slot_variation_produces_thousands_of_renderings(corpus: Corpus) -> None:
    """Combinatorial breadth, not just template count.

    48 templates that each render one way would be 48 pieces of text across 126
    records. The slot lists are what stop the batch reading as a form letter.
    """
    total = 0
    for template in corpus.templates:
        variants = 1
        for values in template.slots.values():
            variants *= len(values)
        if template.subjects:
            variants *= len(template.subjects)
        total += variants
    assert total >= 5000, f"only {total} distinct renderings"
