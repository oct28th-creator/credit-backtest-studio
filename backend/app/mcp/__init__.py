"""MCP server exposing the platform's tool layer.

The tool registry is already self-describing with JSON Schema, so this is a
thin adapter rather than a second implementation: an external agent (Claude
Code, Cowork) gets exactly the tools the in-app orchestrator has, with the
same budgets and the same guardrails. There is no privileged back door for
outside callers.
"""
