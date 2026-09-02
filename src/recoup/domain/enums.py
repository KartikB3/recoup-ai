"""Closed enumerations. Phase 1.

RecordState     AT_RISK, CONTACTED, PROMISED, PAID, DISPUTED, HUMAN_QUEUE,
                EXHAUSTED, WRITTEN_OFF   (state machine, build spec section 2)
Intervention    WAIT, SOFT_REMINDER, PAYMENT_LINK, PHONE_FOLLOWUP,
                ESCALATE_HUMAN, STOP     (closed set, build spec section 4)
Flag            DISPUTED, ALREADY_PAID_UNRECONCILED, HARDSHIP_CLAIMED
Archetype       RELIABLE_BUT_SLOW, CHRONIC_LATE, DISPUTING, DISTRESSED,
                SILENT, PAID_UNRECONCILED
MessageCategory P, S, T, G   (TRAI header suffixes)
Arm             AGENT, BASELINE

INVARIANT: Intervention is closed. Nothing outside it exists in this codebase.
The reasoner structured-output schema uses it, so the model physically cannot
propose anything else.
"""
