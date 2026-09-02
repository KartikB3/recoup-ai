"""Deterministic fallback. Phase 3.

For when the API errors, times out, or refuses. Assume it is down while the
video is being recorded.

GATE: the full batch must complete with ANTHROPIC_API_KEY empty OR unset.
Branch on falsy-or-missing, not on `"ANTHROPIC_API_KEY" not in os.environ` -
an empty value still outranks every other credential source rather than
falling through, so CI runs the stricter empty-string case.
"""
