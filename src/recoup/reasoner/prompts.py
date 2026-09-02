"""Prompt construction. Phase 3.

The frozen system prefix goes FIRST so that it caches; volatile per-record
content goes after the last cache breakpoint. The system prompt carries the
intervention space, the policy rules (so that proposals are plausible), and the
hard constraint that the model never outputs a rupee amount, a date
calculation, or a final decision.
"""
