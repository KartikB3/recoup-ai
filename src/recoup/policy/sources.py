"""Rule provenance. Phase 2.

Every rule carries a RuleSource: kind (REGULATORY or MERCHANT), title, date,
url, and verified: bool.

`verified` is load-bearing. It is the mechanism that stops an unverified
citation reaching the video: an unverified rule renders with a visible chip in
the dashboard. Merchant policy is labelled merchant policy and is never dressed
up as regulatory. See docs/ISSUES.md, ISS-006 through ISS-009.
"""
