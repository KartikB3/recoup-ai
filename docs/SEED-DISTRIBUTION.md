# Seed Distribution

> Phase 1 deliverable. Write this while the numbers are fresh, not afterwards.

Documents exactly what `recoup generate --seed 42` produces, so that the batch is
reproducible by anyone and auditable by a judge.

## To fill in during Phase 1

- Total record count and the seed used
- Archetype mix: count and share per archetype
- Amount distribution (paise): min / median / p90 / max, and the shape
- Days-overdue distribution
- Flag incidence: DISPUTED, ALREADY_PAID_UNRECONCILED, HARDSHIP_CLAIMED
- Free-text coverage: how many records carry payer notes, email replies, dispute text
- The free-text corpus: template count, slot variation, and a few verbatim samples
- **The cluster event**: which parent group, which 9 invoices, what week they go
  silent, and what the free text hints at without naming
- Reproducibility check: the command, and the hash of the emitted batch file
