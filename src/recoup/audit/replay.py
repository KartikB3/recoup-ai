"""Log replay. Phase 1.

ACCEPTANCE TEST: reconstruct(invoice_id, log) returns the final state of that
invoice from the log alone, with no other state, and it must equal the ledger
state. If the two ever diverge, the log is wrong. Runs over all 120 records in
CI.

Write this test before there is anything to replay.
"""
