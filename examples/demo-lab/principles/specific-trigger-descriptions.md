---
id: specific-trigger-descriptions
confidence: confirmed
evidence: [exp-trigger-wording]
scope: [skill-md, trigger, description]
status: promoted
lint:
  - field: description
    pattern: 'use when|if the user|when the user|e\.g\.|such as'
    negate: true
    severity: warn
    message: description lacks a concrete trigger condition
---
## Statement

Descriptions that name concrete trigger situations ("use when the user asks
to …") activate reliably; vague one-liners under-trigger.

## Conditions

- Verified on mock + keyword-overlap heuristic; re-verify per model class.

## Counter-evidence

None yet.
