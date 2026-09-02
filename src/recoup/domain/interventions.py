"""Intervention cost model. Phase 1. See build spec section 4.

Each intervention carries its cost in contact-budget units and API-budget units.
WAIT and STOP cost nothing and are still first-class decisions that get logged.
That is what makes this an agent with judgement rather than a dunning cron job.
"""
