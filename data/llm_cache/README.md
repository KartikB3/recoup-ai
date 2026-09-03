# Committed reasoner cache

Successful structured model outputs are stored below `records/` and `batch/`,
keyed by the SHA-256 of their canonical input. These files are committed on
purpose so an identical demo run can use validated model output with the API
unavailable.

Deterministic fallback output is never written here. Each entry also records a
contract hash over the prompt, schema, model, and effort, so stale entries are
cache misses rather than silently reused answers.
