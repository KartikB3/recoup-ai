"""One module per policy rule. Each is a pure function returning a verdict or None.

Rules run in a fixed, documented order (see docs/POLICY-SOURCES.md); the first
veto wins. Every rule carries a RuleSource, and a regulatory source that is not
verified at the issuing body renders with a warning and stays out of the demo."""
