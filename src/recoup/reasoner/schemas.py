"""Reasoner output schema. Phase 3.

Pydantic -> JSON Schema -> output_config.format, read back with
client.messages.parse(). Using the Intervention enum in the schema is what makes
an out-of-space proposal physically impossible rather than merely discouraged.
"""
