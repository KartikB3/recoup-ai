"""Anthropic client wrapper. Phase 3.

claude-opus-5, adaptive thinking, output_config.effort = medium per record
(high for the batch insight), structured outputs via messages.parse(), prompt
caching on the frozen system prefix, server-side refusal fallbacks enabled, and
stop_reason checked before content is read.

Load the claude-api skill before editing this file. Do not write SDK calls from
memory.
"""
