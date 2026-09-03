"""Shared visual language for the three Recoup dashboard views.

The chrome deliberately follows the Razorpay dashboard's design language --
deep-navy left rail, light-grey canvas, flat white cards, `#3395FF` as the only
accent, Inter with tabular figures for money -- so the tool reads as something
that belongs inside a payments console rather than a hackathon skin.

It stays *Recoup* branded. The mark is Recoup's, not Razorpay's: this is a tool
built for that console, and it should not imply it ships in it.
"""

# CSS declarations are kept one selector per line so the visual tokens stay
# scannable. Their natural width is occasionally longer than Python's limit.
# ruff: noqa: E501

from __future__ import annotations

import html
from decimal import ROUND_HALF_UP, Decimal

from dashboard.data import Scorecard
from recoup.domain.models import format_inr


def escape(value: object) -> str:
    """Escape artifact text before placing it in a small HTML component."""
    return html.escape(str(value), quote=True)


def percent(value: Decimal, places: str = "0.01") -> str:
    """Render a stored decimal percentage without converting through float."""
    return f"{value.quantize(Decimal(places), rounding=ROUND_HALF_UP):f}%"


def recovered(scorecard: Scorecard) -> str:
    """Render the exact integer-paise recovery value."""
    return format_inr(scorecard.recovered_paise)


def topbar(run_id: str, arm_label: str | None = None) -> str:
    """The console app bar: product lockup, breadcrumb, and the mode badge.

    The `Test mode` badge is not decoration. `RazorpayPaymentLinkClient` refuses
    any key that does not start with `rzp_test_`, so it is the literal truth
    about every Razorpay object this project can create.
    """
    crumb = f"Recovery runs / {escape(run_id)}"
    if arm_label:
        crumb += f" / {escape(arm_label)}"
    return f"""
    <div class="rzp-topbar">
      <div class="rzp-brand">
        <span class="rzp-mark">&#8599;</span>
        <span class="rzp-wordmark">Recoup</span>
      </div>
      <div class="rzp-crumb">{crumb}</div>
      <div class="rzp-topbar-right">
        <span class="rzp-mode">Test mode</span>
      </div>
    </div>
    """


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {
  --navy: #0c2451;
  --navy-deep: #02042b;
  --blue: #3395ff;
  --blue-dark: #1170e4;
  --blue-wash: #eef6ff;
  --ink: #0c2451;
  --body: #45536b;
  --muted: #7b8aa5;
  --paper: #f7f8fa;
  --card: #ffffff;
  --line: #e1e6ed;
  --line-soft: #eef1f6;
  --ok: #1e8e3e;
  --ok-wash: #e6f4ea;
  --warn: #b26b00;
  --warn-wash: #fff4e0;
  --danger: #e5233d;
  --danger-wash: #fde8eb;
}

html, body, .stApp, [data-testid="stSidebar"], button, input, select, textarea {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}
.stApp { background: var(--paper); color: var(--body); }
.block-container { max-width: 1340px; padding-top: 1.1rem; padding-bottom: 4rem; }
h1, h2, h3, h4 { color: var(--ink); font-weight: 600; letter-spacing: -0.015em; }
h2 { font-size: 1.15rem; margin-top: 1.9rem; }
a { color: var(--blue-dark); }

/* Money and counts line up in columns, the way a payments console does it. */
.metric-card .value, .story-card strong, .timeline-time, .timeline-meta,
div[data-testid="stDataFrame"], .rzp-stat b {
  font-variant-numeric: tabular-nums; font-feature-settings: "tnum" 1;
}

/* ---------- left rail ---------- */
[data-testid="stSidebar"] { background: var(--navy); border-right: 1px solid var(--navy-deep); }
[data-testid="stSidebar"] * { color: #e8edf6; }
[data-testid="stSidebar"] h1 { color: #ffffff; font-size: 1.15rem; font-weight: 600; letter-spacing: -.01em; }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: #93a4c4; font-size: .74rem; }
[data-testid="stSidebar"] label { color: #b9c6dd !important; font-size: .74rem; font-weight: 500; text-transform: uppercase; letter-spacing: .07em; }
[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,.12); }
[data-testid="stSidebar"] [data-baseweb="select"] > div {
  background: rgba(255,255,255,.07); border-color: rgba(255,255,255,.16); border-radius: 4px; color: #fff;
}
[data-testid="stSidebar"] [data-baseweb="select"] * { color: #ffffff; }
[data-testid="stSidebar"] [role="radiogroup"] { gap: .1rem; }
[data-testid="stSidebar"] [role="radiogroup"] label {
  text-transform: none; letter-spacing: 0; font-size: .88rem; font-weight: 500;
  padding: .42rem .55rem; border-radius: 4px; color: #dbe4f2 !important;
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover { background: rgba(255,255,255,.06); }

/* ---------- app bar ---------- */
.rzp-topbar {
  display: flex; align-items: center; gap: 1rem; background: var(--card);
  border: 1px solid var(--line); border-radius: 6px; padding: .62rem .9rem; margin-bottom: 1.1rem;
}
.rzp-brand { display: flex; align-items: center; gap: .5rem; }
.rzp-mark {
  width: 26px; height: 26px; border-radius: 6px; background: var(--blue); color: #fff;
  display: inline-flex; align-items: center; justify-content: center; font-size: .95rem; font-weight: 700;
}
.rzp-wordmark { color: var(--ink); font-weight: 700; font-size: 1rem; letter-spacing: -.02em; }
.rzp-crumb { color: var(--muted); font-size: .82rem; border-left: 1px solid var(--line); padding-left: 1rem; }
.rzp-topbar-right { margin-left: auto; }
.rzp-mode {
  background: var(--warn-wash); color: var(--warn); border: 1px solid #f3d9a8;
  border-radius: 4px; padding: .22rem .55rem; font-size: .72rem; font-weight: 600; letter-spacing: .02em;
}

/* ---------- page header ---------- */
.recoup-kicker {
  color: var(--muted); font-size: .7rem; font-weight: 600; letter-spacing: .1em;
  text-transform: uppercase; margin-bottom: .5rem;
}
.recoup-hero {
  background: var(--card); border: 1px solid var(--line); border-radius: 6px;
  padding: 1.5rem 1.6rem; margin-bottom: 1.1rem;
}
.recoup-hero h1 { color: var(--ink); font-size: clamp(1.5rem, 2.4vw, 2rem); margin: 0; font-weight: 600; line-height: 1.2; }
.recoup-hero p { color: var(--body); max-width: 760px; font-size: .92rem; line-height: 1.6; margin: .6rem 0 0; }

/* ---------- pills ---------- */
.offline-pill, .source-pill {
  display: inline-flex; align-items: center; gap: .4rem; border-radius: 4px;
  padding: .24rem .55rem; font-size: .72rem; font-weight: 600;
}
.offline-pill { background: var(--ok-wash); color: var(--ok); border: 1px solid #bfe3ca; margin-bottom: .9rem; }
.offline-pill:before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--ok); }

/* ---------- metric cards ---------- */
.metric-card {
  background: var(--card); border: 1px solid var(--line); border-radius: 6px;
  padding: .95rem 1rem; min-height: 148px;
}
.metric-card.model { border-color: #bcdcff; background: var(--blue-wash); }
.metric-card .label { color: var(--muted); font-size: .7rem; text-transform: uppercase; letter-spacing: .08em; font-weight: 600; }
.metric-card .value { color: var(--ink); font-size: 1.7rem; font-weight: 700; letter-spacing: -.03em; margin: .3rem 0 .15rem; }
.metric-card.model .value { color: var(--blue-dark); }
.metric-card .sub { color: var(--body); font-size: .78rem; line-height: 1.5; }

.story-card {
  background: var(--card); border: 1px solid var(--line); border-radius: 6px;
  padding: 1rem 1.05rem; min-height: 150px;
}
.story-card strong { display: block; font-size: 1.5rem; font-weight: 700; letter-spacing: -.03em; color: var(--blue-dark); }
.story-card p { color: var(--body); margin: .4rem 0 0; font-size: .84rem; line-height: 1.55; }
.section-intro { color: var(--body); max-width: 830px; margin-top: -.3rem; font-size: .9rem; }

/* ---------- activity timeline ---------- */
.timeline { margin: 1.1rem 0 2rem; }
.timeline-row { display: grid; grid-template-columns: 138px 22px 1fr; gap: .55rem; min-height: 104px; }
.timeline-time { text-align: right; padding: .2rem .55rem 0 0; color: var(--muted); font-size: .73rem; line-height: 1.5; }
.timeline-time strong { color: var(--ink); display: block; font-weight: 600; }
.timeline-rail { position: relative; }
.timeline-rail:before { content: ""; position: absolute; left: 10px; top: 20px; bottom: -8px; width: 2px; background: var(--line); }
.timeline-row:last-child .timeline-rail:before { display: none; }
.timeline-dot {
  position: absolute; top: 5px; left: 3px; width: 15px; height: 15px; border-radius: 50%;
  background: var(--blue); border: 3px solid var(--paper); box-shadow: 0 0 0 1px var(--blue);
}
.timeline-dot.wait { background: #f5a623; box-shadow: 0 0 0 1px #f5a623; }
.timeline-dot.veto { background: var(--danger); box-shadow: 0 0 0 1px var(--danger); }
.timeline-dot.outcome { background: var(--ok); box-shadow: 0 0 0 1px var(--ok); }
.timeline-body {
  background: var(--card); border: 1px solid var(--line); border-radius: 6px;
  padding: .8rem .95rem; margin-bottom: .75rem;
}
.timeline-eyebrow { color: var(--blue-dark); font-weight: 600; letter-spacing: .08em; font-size: .66rem; text-transform: uppercase; }
.timeline-eyebrow.veto { color: var(--danger); }
.timeline-eyebrow.wait { color: var(--warn); }
.timeline-title { font-weight: 600; color: var(--ink); margin: .2rem 0 .35rem; font-size: .95rem; }
.timeline-copy { color: var(--body); font-size: .84rem; line-height: 1.55; }
.timeline-meta { color: var(--muted); font-size: .71rem; margin-top: .5rem; }

/* ---------- rule provenance ---------- */
.source-card {
  background: var(--blue-wash); border: 1px solid #d3e7ff; border-left: 3px solid var(--blue);
  border-radius: 4px; padding: .9rem 1rem; margin: .6rem 0;
}
.source-card.unverified { background: var(--danger-wash); border-color: #f6ccd4; border-left-color: var(--danger); }
.source-card.merchant { background: #f4f6f9; border-color: var(--line); border-left-color: var(--muted); }
.source-card h4 { margin: 0 0 .3rem; color: var(--ink); font-size: .92rem; }
.source-card p { color: var(--body); font-size: .8rem; line-height: 1.5; margin: .4rem 0; }
.source-pill.verified { background: var(--ok-wash); color: var(--ok); border: 1px solid #bfe3ca; }
.source-pill.unverified { background: #fff; color: var(--danger); border: 1px solid #f6ccd4; }
.source-pill.merchant { background: #fff; color: var(--body); border: 1px solid var(--line); }

.artifact-note {
  background: var(--card); border: 1px solid var(--line); border-left: 3px solid var(--muted);
  border-radius: 4px; padding: .75rem .95rem; color: var(--body); font-size: .8rem; line-height: 1.55;
}

/* ---------- data tables and inputs ---------- */
div[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 6px; }
div[data-testid="stDataFrame"] * { font-size: .82rem; }
.stTextInput input, .stNumberInput input, [data-baseweb="select"] > div {
  border-radius: 4px !important; border-color: var(--line) !important;
}
.stTextInput input:focus, [data-baseweb="select"] > div:focus-within {
  border-color: var(--blue) !important; box-shadow: 0 0 0 3px rgba(51,149,255,.16) !important;
}
.stButton button {
  background: var(--blue); color: #fff; border: 0; border-radius: 4px;
  font-weight: 600; font-size: .85rem; padding: .42rem 1rem;
}
.stButton button:hover { background: var(--blue-dark); color: #fff; }
[data-testid="stExpander"] { border: 1px solid var(--line); border-radius: 6px; background: var(--card); }
code { background: var(--line-soft); color: var(--ink); border-radius: 3px; padding: .08rem .3rem; font-size: .84em; }

@media (max-width: 760px) {
  .timeline-row { grid-template-columns: 1fr; gap: .2rem; }
  .timeline-time { text-align: left; }
  .timeline-rail { display: none; }
  .recoup-hero { padding: 1.1rem; }
  .rzp-crumb { display: none; }
}
</style>
"""
