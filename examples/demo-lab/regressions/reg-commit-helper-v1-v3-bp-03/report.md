# Regression report: `commit-helper` `v1` → `v3-bp`

- regression: `reg-commit-helper-v1-v3-bp-03` · experiment: `reg-commit-helper-v1-v3-bp-03` · created 2026-11-22T12:38:18+07:00
- model: `anthropic/claude-haiku-4-5` · injection: `available` · harness: `standard-tools-v1` · rollouts/arm·task: 1
- suite: `default` (4 task(s))

## Verdict: 🟡 INCONCLUSIVE

## Metrics overview

| metric | baseline | candidate | Δ |
|---|---|---|---|
| runs | 4 | 4 | — |
| error rate | 100% | 100% | +0.00 |
| success rate | — | — | — |
| rubric score | — | — | — |
| outcome variance | 0.00 | 0.00 | +0.00 |
| tokens/run | — | — | — |
| latency s/run | — | — | — |
| turns/run | — | — | — |
| activation recall | — | — | — |
| activation precision | — | — | — |
| false-activation | — | — | — |

## Per-task results

### `unrelated-refactor` (activation-negative) → — no change

| | baseline | candidate | Δ |
|---|---|---|---|
| runs | 1 (err 1) | 1 (err 1) | — |
| success | — | — | — |
| score | — | — | — |
| activated | — | — | — |
| tokens | — | — | — |
| latency s | — | — | — |
| turns | — | — | — |
| variance | 0.00 | 0.00 | +0.00 |

- baseline runs: `reg-commit-helper-v1-v3-bp-03--baseline--unrelated-refactor--r0`
- candidate runs: `reg-commit-helper-v1-v3-bp-03--candidate--unrelated-refactor--r0`
- ⚠ insufficient runs (n=1v1, min=3)
- ⚠ no final evaluations on one/both sides — outcome comparison impossible
- baseline evidence: reg-commit-helper-v1-v3-bp-03--baseline--unrelated-refactor--r0: run error — AuthenticationError: litellm.AuthenticationError: Missing Anthropic API Key - A call is being made to anthropic but no key is set either in the environment variables or via params. Please set `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` in your environment vars, or configure workload identity federation via `ANTHROPIC_FEDERATION_RULE_ID`, `ANTHROPIC_ORGANIZATION_ID`, `ANTHROPIC_SERVICE_ACCOUNT_ID` and `ANTHROPIC_IDENTITY_TOKEN_FILE` (or `ANTHROPIC_IDENTITY_TOKEN`)
- candidate evidence: reg-commit-helper-v1-v3-bp-03--candidate--unrelated-refactor--r0: run error — AuthenticationError: litellm.AuthenticationError: Missing Anthropic API Key - A call is being made to anthropic but no key is set either in the environment variables or via params. Please set `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` in your environment vars, or configure workload identity federation via `ANTHROPIC_FEDERATION_RULE_ID`, `ANTHROPIC_ORGANIZATION_ID`, `ANTHROPIC_SERVICE_ACCOUNT_ID` and `ANTHROPIC_IDENTITY_TOKEN_FILE` (or `ANTHROPIC_IDENTITY_TOKEN`)

### `write-a-commit-message` (activation-positive) → — no change

| | baseline | candidate | Δ |
|---|---|---|---|
| runs | 1 (err 1) | 1 (err 1) | — |
| success | — | — | — |
| score | — | — | — |
| activated | — | — | — |
| tokens | — | — | — |
| latency s | — | — | — |
| turns | — | — | — |
| variance | 0.00 | 0.00 | +0.00 |

- baseline runs: `reg-commit-helper-v1-v3-bp-03--baseline--write-a-commit-message--r0`
- candidate runs: `reg-commit-helper-v1-v3-bp-03--candidate--write-a-commit-message--r0`
- ⚠ insufficient runs (n=1v1, min=3)
- ⚠ no final evaluations on one/both sides — outcome comparison impossible
- baseline evidence: reg-commit-helper-v1-v3-bp-03--baseline--write-a-commit-message--r0: run error — AuthenticationError: litellm.AuthenticationError: Missing Anthropic API Key - A call is being made to anthropic but no key is set either in the environment variables or via params. Please set `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` in your environment vars, or configure workload identity federation via `ANTHROPIC_FEDERATION_RULE_ID`, `ANTHROPIC_ORGANIZATION_ID`, `ANTHROPIC_SERVICE_ACCOUNT_ID` and `ANTHROPIC_IDENTITY_TOKEN_FILE` (or `ANTHROPIC_IDENTITY_TOKEN`)
- candidate evidence: reg-commit-helper-v1-v3-bp-03--candidate--write-a-commit-message--r0: run error — AuthenticationError: litellm.AuthenticationError: Missing Anthropic API Key - A call is being made to anthropic but no key is set either in the environment variables or via params. Please set `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` in your environment vars, or configure workload identity federation via `ANTHROPIC_FEDERATION_RULE_ID`, `ANTHROPIC_ORGANIZATION_ID`, `ANTHROPIC_SERVICE_ACCOUNT_ID` and `ANTHROPIC_IDENTITY_TOKEN_FILE` (or `ANTHROPIC_IDENTITY_TOKEN`)

### `write-a-commit-message-for-stage` (activation-positive) → — no change

| | baseline | candidate | Δ |
|---|---|---|---|
| runs | 1 (err 1) | 1 (err 1) | — |
| success | — | — | — |
| score | — | — | — |
| activated | — | — | — |
| tokens | — | — | — |
| latency s | — | — | — |
| turns | — | — | — |
| variance | 0.00 | 0.00 | +0.00 |

- baseline runs: `reg-commit-helper-v1-v3-bp-03--baseline--write-a-commit-message-for-stage--r0`
- candidate runs: `reg-commit-helper-v1-v3-bp-03--candidate--write-a-commit-message-for-stage--r0`
- ⚠ insufficient runs (n=1v1, min=3)
- ⚠ no final evaluations on one/both sides — outcome comparison impossible
- baseline evidence: reg-commit-helper-v1-v3-bp-03--baseline--write-a-commit-message-for-stage--r0: run error — AuthenticationError: litellm.AuthenticationError: Missing Anthropic API Key - A call is being made to anthropic but no key is set either in the environment variables or via params. Please set `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` in your environment vars, or configure workload identity federation via `ANTHROPIC_FEDERATION_RULE_ID`, `ANTHROPIC_ORGANIZATION_ID`, `ANTHROPIC_SERVICE_ACCOUNT_ID` and `ANTHROPIC_IDENTITY_TOKEN_FILE` (or `ANTHROPIC_IDENTITY_TOKEN`)
- candidate evidence: reg-commit-helper-v1-v3-bp-03--candidate--write-a-commit-message-for-stage--r0: run error — AuthenticationError: litellm.AuthenticationError: Missing Anthropic API Key - A call is being made to anthropic but no key is set either in the environment variables or via params. Please set `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` in your environment vars, or configure workload identity federation via `ANTHROPIC_FEDERATION_RULE_ID`, `ANTHROPIC_ORGANIZATION_ID`, `ANTHROPIC_SERVICE_ACCOUNT_ID` and `ANTHROPIC_IDENTITY_TOKEN_FILE` (or `ANTHROPIC_IDENTITY_TOKEN`)

### `write-commit-msg` (activation-positive) → — no change

| | baseline | candidate | Δ |
|---|---|---|---|
| runs | 1 (err 1) | 1 (err 1) | — |
| success | — | — | — |
| score | — | — | — |
| activated | — | — | — |
| tokens | — | — | — |
| latency s | — | — | — |
| turns | — | — | — |
| variance | 0.00 | 0.00 | +0.00 |

- baseline runs: `reg-commit-helper-v1-v3-bp-03--baseline--write-commit-msg--r0`
- candidate runs: `reg-commit-helper-v1-v3-bp-03--candidate--write-commit-msg--r0`
- ⚠ insufficient runs (n=1v1, min=3)
- ⚠ no final evaluations on one/both sides — outcome comparison impossible
- baseline evidence: reg-commit-helper-v1-v3-bp-03--baseline--write-commit-msg--r0: run error — AuthenticationError: litellm.AuthenticationError: Missing Anthropic API Key - A call is being made to anthropic but no key is set either in the environment variables or via params. Please set `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` in your environment vars, or configure workload identity federation via `ANTHROPIC_FEDERATION_RULE_ID`, `ANTHROPIC_ORGANIZATION_ID`, `ANTHROPIC_SERVICE_ACCOUNT_ID` and `ANTHROPIC_IDENTITY_TOKEN_FILE` (or `ANTHROPIC_IDENTITY_TOKEN`)
- candidate evidence: reg-commit-helper-v1-v3-bp-03--candidate--write-commit-msg--r0: run error — AuthenticationError: litellm.AuthenticationError: Missing Anthropic API Key - A call is being made to anthropic but no key is set either in the environment variables or via params. Please set `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` in your environment vars, or configure workload identity federation via `ANTHROPIC_FEDERATION_RULE_ID`, `ANTHROPIC_ORGANIZATION_ID`, `ANTHROPIC_SERVICE_ACCOUNT_ID` and `ANTHROPIC_IDENTITY_TOKEN_FILE` (or `ANTHROPIC_IDENTITY_TOKEN`)

## Reproduce

```
lab regression report reg-commit-helper-v1-v3-bp-03
lab report reg-commit-helper-v1-v3-bp-03
lab compare reg-commit-helper-v1-v3-bp-03
```
