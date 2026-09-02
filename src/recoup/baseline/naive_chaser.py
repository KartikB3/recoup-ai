"""The baseline arm. Phase 2.

Contact every 3 days until paid or 5 attempts. Runs through the SAME runner, the
SAME ledger and the SAME seed, and bypasses the policy engine.

That bypass is the whole point: the baseline is what generates the false
interventions the agent avoids.
"""
