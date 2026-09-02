"""Batch-level insight. Phase 3; wired to the dashboard in Phase 6.

Build spec section 7b: the one decision the per-record path structurally cannot
produce. Detects the parent-group cluster and returns a suppression
recommendation, which the policy engine still has to approve.

Without this, a judge can correctly say a lookup table would have done the job.
"""
