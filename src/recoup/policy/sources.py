"""Rule provenance. Phase 2.

Every rule carries a `RuleSource`: kind (REGULATORY or MERCHANT), title, date,
url, and `verified: bool`.

`verified` is load-bearing. It is the mechanism that stops an unverified
citation reaching the video: an unverified rule renders with a visible chip in
the dashboard. Merchant policy is labelled merchant policy and is never dressed
up as regulatory. See docs/ISSUES.md, ISS-006 through ISS-009.

What "verified" means in this file
----------------------------------
Every source below marked `verified=True` was read **at the issuing body's own
site**, in the gazette notification or circular itself, during Phase 2. Not a
vendor blog, not a summary, not from memory. The exact clause each rule rests
on is quoted in `docs/POLICY-SOURCES.md` next to the URL it was read from.

One of the claims this project started with did not survive that reading, and
the corrected version is what ships. `TRAI_TIME_BANDS` was carried in
`docs/POLICY-SOURCES.md` as "promotional-category messages only 10:00-21:00
IST", sourced from a vendor blog. TCCCPR contains no such blanket prohibition.
What it contains is a customer **preference** register with nine time bands, of
which four are default-OFF for every subscriber whether or not they ever
registered a preference -- and the complement of those four happens to be
10:00-21:00. The window is real, the number is right, and the reason is
completely different: it is a default preference, not a ban, and it binds only
promotional communication. See ISS-024.

That distinction is not pedantry. A payments panel contains people who know
this regulation, and "we cite the default preference bands" survives being
asked a follow-up question in a way that "it is illegal to send at 21:30" does
not.

Scope caveats are carried in the data, not in a comment
--------------------------------------------------------
`RuleSource.scope_caveat` exists because the RBI contact-hour rule is the most
useful rule in this engine and is also, read strictly, about something else --
lending recovery by regulated entities, not merchant receivables. The caveat
travels with the citation into the dashboard so that the honest version is the
one on screen, not a footnote somebody has to go looking for.
"""

from __future__ import annotations

from recoup.domain.enums import RuleKind
from recoup.domain.models import RuleSource

# ---------------------------------------------------------------------------
# Regulatory. Every one of these was read at the issuing body in Phase 2.
# ---------------------------------------------------------------------------

#: RBI/2022-23/108, 12 August 2022. The clause, verbatim: regulated entities
#: must ensure their agents do not resort to "persistently calling the borrower
#: and/ or calling the borrower before 8:00 a.m. and after 7:00 p.m. for
#: recovery of overdue loans".
#:
#: Read at rbi.org.in on 2026-09-02. The circular number is quoted here because
#: it was verified at source; `docs/POLICY-SOURCES.md` explains why the
#: E-mandate framework (ISS-006) gets title-and-date only instead.
RBI_CONTACT_HOURS = RuleSource(
    kind=RuleKind.REGULATORY,
    title=(
        "RBI, Outsourcing of Financial Services - Responsibilities of "
        "regulated entities employing Recovery Agents"
    ),
    cited_date="2022-08-12",
    url="https://www.rbi.org.in/scripts/NotificationUser.aspx?Id=12378&Mode=0",
    verified=True,
    scope_caveat=(
        "Binds banks, NBFCs, All-India Financial Institutions, co-operative banks and "
        "ARCs recovering OVERDUE LOANS. A merchant chasing its own trade receivables is "
        "not a regulated entity under this circular. Recoup adopts the 08:00-19:00 window "
        "as a standard, and does not claim it is legally bound by it."
    ),
)

#: TCCCPR 2018 (6 of 2018), 19 July 2018, Schedule III. The customer preference
#: register carries nine time bands. Note-1 to the time-band table: bands
#: (i) 00:00-06:00, (ii) 06:00-08:00, (iii) 08:00-10:00 and (ix) 21:00-24:00
#: "shall be default OFF for all customers irrespective of the status of
#: registration of customer ... unless customer has registered its
#: preference(s) and switched ON".
#:
#: The complement of the four default-OFF bands is 10:00-21:00, which is where
#: the widely repeated figure comes from. Read at trai.gov.in on 2026-09-02.
TRAI_TIME_BANDS = RuleSource(
    kind=RuleKind.REGULATORY,
    title=(
        "TRAI, Telecom Commercial Communications Customer Preference "
        "Regulations, 2018 - Schedule III time bands"
    ),
    cited_date="2018-07-19",
    url="https://www.trai.gov.in/sites/default/files/2024-09/RegulationUcc19072018.pdf",
    verified=True,
    scope_caveat=(
        "A default customer PREFERENCE, not a blanket prohibition, and it binds only "
        "promotional communication. Service, transactional and government messages are "
        "explicitly outside the BLOCK PROMO option. Recoup sends no promotional traffic, "
        "so this rule is wired and tested but does not fire on the seeded batch."
    ),
)

#: TCCCPR (Second Amendment) Regulations, 2025 (1 of 2025), 12 February 2025.
#: Verbatim: the Access Provider "should suffix '-P', '-S', '-T', and '-G' to
#: Header structure for promotional, service, transactional, and government"
#: communications.
#:
#: The same amendment defines a Transactional Message as one sent "in response
#: to Customer initiated transaction within thirty minutes of the transaction",
#: which is the clause that settles a design question this project had already
#: answered by reasoning: a payment link chasing an overdue bill is merchant-
#: initiated and days late, so it is a Service message and never -T. See the
#: `correct_category` table in `domain/interventions.py`.
TRAI_MESSAGE_CATEGORY = RuleSource(
    kind=RuleKind.REGULATORY,
    title=(
        "TRAI, Telecom Commercial Communications Customer Preference "
        "(Second Amendment) Regulations, 2025 - header category suffixes"
    ),
    cited_date="2025-02-12",
    url="https://www.trai.gov.in/sites/default/files/2025-02/Regulation_12022025.pdf",
    verified=True,
    scope_caveat=(
        "Recoup does not send SMS through a DLT-registered header in this build, so the "
        "classification is checked rather than transmitted. The rule catches a proposal "
        "that would carry the wrong category if it were sent."
    ),
)

# ---------------------------------------------------------------------------
# Merchant policy. No citation, and none claimed.
# ---------------------------------------------------------------------------
#
# These are business configuration. They are the majority of what actually
# fires on the seeded batch, and labelling them honestly is the point: a
# merchant frequency cap dressed up as a regulation would be the single most
# damaging thing this project could put on screen. ISS-009 is the worked
# example -- there is no verified regulatory cap on retry attempts anywhere,
# so Recoup does not claim one.

MERCHANT_POLICY = RuleSource(
    kind=RuleKind.MERCHANT,
    title="Recoup merchant collections policy (configurable)",
    cited_date=None,
    url=None,
    verified=True,
    scope_caveat=None,
)

#: Every source in the project, by the name rules refer to it by. The dashboard
#: renders from this, and `tests/test_policy.py` asserts that every rule's
#: source is one of these -- so a rule cannot invent a citation inline.
ALL_SOURCES: dict[str, RuleSource] = {
    "RBI_CONTACT_HOURS": RBI_CONTACT_HOURS,
    "TRAI_TIME_BANDS": TRAI_TIME_BANDS,
    "TRAI_MESSAGE_CATEGORY": TRAI_MESSAGE_CATEGORY,
    "MERCHANT_POLICY": MERCHANT_POLICY,
}


def unverified() -> list[RuleSource]:
    """Every source not confirmed at the issuing body. Renders with a chip.

    Empty as of Phase 2: the two P0 citations were verified and the P1
    e-mandate rules were not written, because the mandate lane did not ship.
    The function exists anyway -- the dashboard needs a truthful answer to
    "what is unverified here?", and an empty list is a truthful answer that a
    hardcoded "none" is not.
    """
    return [source for source in ALL_SOURCES.values() if not source.verified]
