"""AI layer: Amazon Bedrock via the Strands Agents SDK.

* ``model``: builds the Bedrock model provider from settings (nothing hardcoded).
* ``untrusted``: prepares retrieved AWS data so the model treats it as data, never instructions.
* ``prompts``: the system prompt and its non-negotiable rules.
* ``report``: turns collected evidence into a validated, evidence-cited report.
"""
