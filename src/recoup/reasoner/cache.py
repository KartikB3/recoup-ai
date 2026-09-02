"""Disk cache keyed by SHA-256 of the canonical input snapshot. Phase 3.

Lives at data/llm_cache/ and is COMMITTED. That is not an oversight: it is what
makes runs reproducible and what makes the demo work with the API down. If this
ever becomes an untracked directory, the offline gate passes locally and fails
on a fresh clone.
"""
