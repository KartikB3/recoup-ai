"""Frozen domain contracts. Phase 1. See IMPLEMENTATION-PLAN section 2.

Invoice, FreeText, EmailReply, PaymentEvent, ContactLedger, VirtualDate,
LLMProposal, DraftedMessage, PromiseToPay, PolicyVerdict, RuleSource, AuditRow.

INVARIANTS enforced here, not downstream:
  - All money is int paise. Never float. Never rupees.
  - All dates are virtual. No datetime.now() reachable from this module.
  - No numeric field on LLMProposal is ever used as money or as a date.
    The ledger resolves a promise phrase to a tick deterministically; the model
    only quotes the span it found.
"""
