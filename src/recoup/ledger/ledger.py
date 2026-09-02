"""The ledger: the system of record. Phase 1.

NOT Razorpay. State transitions are the only way state changes.

    AT_RISK -> CONTACTED -> PROMISED -> PAID
                         -> DISPUTED -> HUMAN_QUEUE
                         -> EXHAUSTED -> WRITTEN_OFF
"""
