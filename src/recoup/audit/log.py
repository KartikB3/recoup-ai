"""Append-only audit log, JSONL. Phase 1.

One row per decision, never updated. Outcomes arrive as new rows.

Fields: tick, record_id, input_snapshot, llm_proposal, policy_verdict,
policy_rule, action, outcome, plus run_id, arm, row_id, prev_row_hash.
"""
