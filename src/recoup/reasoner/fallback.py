"""Deterministic fallback. Phase 3.

For when the API errors, times out, or refuses. Assume it is down while the
video is being recorded.

GATE: the full batch must complete with ANTHROPIC_API_KEY unset.
"""
