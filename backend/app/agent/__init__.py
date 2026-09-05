"""Agent layer.

Three modules, deliberately separated by trust level:

  tools.py        deterministic capabilities — anything an agent may do
  guardrails.py   deterministic checks — what an agent may NOT conclude
  budget.py       hard limits — how much an agent may spend
  orchestrator.py the only place an LLM is in the loop

Nothing here decides credit policy. The agent proposes and analyses; the
metric layer computes; the guardrails veto; a human approves.
"""
