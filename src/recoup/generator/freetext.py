"""The free-text corpus: loading, filtering, and slot rendering. Phase 1.

The corpus lives in `generator/corpus/*.yaml` and is the single
highest-leverage artifact in the build. Without it every record carries only
amounts and dates, `if days_overdue > 30` reproduces the agent exactly, and the
project is a rules engine with an API bill.

What a template is
------------------
A template declares the free-text surface it writes to (`kind`), which pool it
belongs to (`GENERAL` or `CLUSTER`), which archetypes it is plausible for, the
signals it carries, and a body with `{slot}` placeholders. Slots are filled
from ordered lists by a seeded RNG, so 48 templates yield roughly eight
thousand distinct renderings.

The rule the corpus is built around
-----------------------------------
**A template body must not contain its own signal's vocabulary.** "We dispute
this invoice" is a regex; "the GRN quantity does not tally with your challan so
the lot is held at gate" is a reasoning task. The CLUSTER pool goes further and
bans a specific word list outright -- see `BANNED_IN_CLUSTER` and
`tests/test_corpus.py`, which fails the build if any of them appears.

Determinism
-----------
Files are read in sorted filename order and templates keep their file order, so
the corpus presents the same sequence on every machine. Nothing here touches a
set, a dict ordering, or `hash()`.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from importlib import resources
from typing import Any

import yaml

from recoup.domain.enums import Archetype, FreeTextKind, SignalKind

#: Words that must never appear in a CLUSTER-pool template. Naming the cause
#: turns the batch-level insight (build spec section 7b) into a keyword search
#: and destroys the only claim in the project that the LLM does something a
#: lookup table cannot.
BANNED_IN_CLUSTER: tuple[str, ...] = (
    "freeze",
    "frozen",
    "procurement",
    "payment hold",
    "on hold",
    "suspended",
    "moratorium",
    "stopped payment",
    "blocked payment",
)

#: Slot names the generator supplies. A template may reference these without
#: declaring them under `slots`.
RESERVED_SLOTS: frozenset[str] = frozenset(
    {
        "invoice_no",
        "payer_name",
        "contact_name",
        "contact_role",
        "city",
        "merchant_short",
        "merchant_legal",
        "amount_rupees",
        "days_overdue",
    }
)

_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


@dataclass(frozen=True)
class Template:
    """One corpus template with its slot vocabulary and its ground-truth tags."""

    id: str
    kind: FreeTextKind
    pool: str
    signals: tuple[SignalKind, ...]
    archetypes: tuple[Archetype, ...]
    weight: int
    text: str
    slots: dict[str, tuple[str, ...]]
    subjects: tuple[str, ...] = ()
    strength: str | None = None

    def placeholders(self) -> set[str]:
        """Every `{slot}` referenced by the body or by any subject line."""
        found = set(_PLACEHOLDER.findall(self.text))
        for subject in self.subjects:
            found |= set(_PLACEHOLDER.findall(subject))
        return found


@dataclass(frozen=True)
class Rendering:
    """A template with its slots filled. Carries provenance for the seed docs."""

    template_id: str
    signals: tuple[SignalKind, ...]
    strength: str | None
    subject: str | None
    body: str


def _normalise(text: str) -> str:
    """Tidy the seams left by slot substitution, without touching line structure."""
    lines = [re.sub(r"[ \t]{2,}", " ", line).rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def _load_file(name: str, raw: str) -> list[Template]:
    """Parse one corpus YAML file into templates."""
    data: dict[str, Any] = yaml.safe_load(raw)
    if "templates" not in data:
        return []
    kind = FreeTextKind(data["kind"])
    pool = str(data.get("pool", "GENERAL"))
    templates: list[Template] = []
    for entry in data["templates"]:
        templates.append(
            Template(
                id=str(entry["id"]),
                kind=kind,
                pool=pool,
                signals=tuple(SignalKind(s) for s in entry.get("signals", [])),
                archetypes=tuple(Archetype(a) for a in entry.get("archetypes", [])),
                weight=int(entry.get("weight", 1)),
                text=str(entry["text"]),
                slots={k: tuple(str(x) for x in v) for k, v in entry.get("slots", {}).items()},
                subjects=tuple(str(s) for s in entry.get("subject", [])),
                strength=entry.get("strength"),
            )
        )
    if not templates:
        raise ValueError(f"{name}: declares a kind but contains no templates")
    return templates


class Corpus:
    """Every template, loaded once, queryable by kind, pool and archetype."""

    def __init__(self, templates: list[Template]) -> None:
        self.templates = templates

    @classmethod
    def load(cls) -> Corpus:
        """Read `generator/corpus/*.yaml` in sorted filename order."""
        package = resources.files("recoup.generator") / "corpus"
        templates: list[Template] = []
        for entry in sorted(package.iterdir(), key=lambda p: p.name):
            if not entry.name.endswith(".yaml"):
                continue
            templates.extend(_load_file(entry.name, entry.read_text(encoding="utf-8")))
        if not templates:
            raise RuntimeError("corpus is empty: generator/corpus/*.yaml did not load")
        return cls(templates)

    def select(
        self,
        kind: FreeTextKind,
        archetype: Archetype,
        *,
        pool: str = "GENERAL",
        strength: str | None = None,
    ) -> list[Template]:
        """Candidate templates, expanded by weight so a weight of 3 is 3x likely.

        Returns a list rather than a weighted sample so that the caller's RNG
        does a single `choice` and the draw stays reproducible.
        """
        out: list[Template] = []
        for template in self.templates:
            if template.kind is not kind or template.pool != pool:
                continue
            if template.archetypes and archetype not in template.archetypes:
                continue
            if strength is not None and template.strength != strength:
                continue
            out.extend([template] * template.weight)
        return out

    def by_id(self, template_id: str) -> Template:
        """One template by id. Used to pin the spotlight record's free text."""
        for template in self.templates:
            if template.id == template_id:
                return template
        raise KeyError(template_id)

    def render(self, template: Template, rng: random.Random, reserved: dict[str, str]) -> Rendering:
        """Fill a template's slots. See the module-level `render`."""
        return render(template, rng, reserved)

    def render_by_id(
        self, template_id: str, rng: random.Random, reserved: dict[str, str]
    ) -> Rendering:
        """Render a specific template. Used to pin the spotlight record."""
        return render(self.by_id(template_id), rng, reserved)


def render(template: Template, rng: random.Random, reserved: dict[str, str]) -> Rendering:
    """Fill a template's slots from `rng` and the generator-supplied values.

    Raises on an undeclared placeholder rather than emitting a literal `{slot}`
    into the corpus. A malformed template should fail the build, not ship into
    the batch and get read out on a demo video.
    """
    values: dict[str, str] = dict(reserved)
    for name in sorted(template.slots):
        values[name] = rng.choice(template.slots[name])

    missing = template.placeholders() - values.keys()
    if missing:
        raise KeyError(f"{template.id}: undeclared placeholders {sorted(missing)}")

    subject = (
        _normalise(rng.choice(template.subjects).format(**values)) if template.subjects else None
    )
    return Rendering(
        template_id=template.id,
        signals=template.signals,
        strength=template.strength,
        subject=subject,
        body=_normalise(template.text.format(**values)),
    )
