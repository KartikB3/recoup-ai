"""Seeded batch generator. Phase 1.

Reproducible: the same seed produces byte-identical output. Emits to
data/batches/.

Owns the deliberate cluster event: nine invoices sharing one parent_group_id,
all going silent in the same week, whose free text HINTS at a procurement
freeze without naming it. The LLM must infer it, or the batch-level insight in
build spec section 7b is worthless.
"""
