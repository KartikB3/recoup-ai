"""The policy engine. Phase 2. The core of the product.

Runs AFTER the reasoner. Approves, modifies, or vetoes. Rules run in a fixed,
documented order; the first veto wins; modifications compose. The order is part
of the spec, not an implementation detail, and it is written down in
docs/POLICY-SOURCES.md.

Every veto is logged AS A VETO and is visible in the UI.
"""
