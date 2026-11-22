# Regression report: `commit-helper` `v1` → `v3-bp`

- regression: `reg-commit-helper-v1-v3-bp-02` · experiment: `reg-commit-helper-v1-v3-bp-02` · created 2026-11-22T12:37:30+07:00
- model: `anthropic/claude-sonnet-4-5` · injection: `available` · harness: `standard-tools-v1` · rollouts/arm·task: 1
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

- baseline runs: `reg-commit-helper-v1-v3-bp-02--baseline--unrelated-refactor--r0`
- candidate runs: `reg-commit-helper-v1-v3-bp-02--candidate--unrelated-refactor--r0`
- ⚠ insufficient runs (n=1v1, min=3)
- ⚠ no final evaluations on one/both sides — outcome comparison impossible
- baseline evidence: reg-commit-helper-v1-v3-bp-02--baseline--unrelated-refactor--r0: run error — UnsupportedParamsError: litellm.UnsupportedParamsError: anthropic does not support parameters: ['seed'], for model=claude-sonnet-4-5. To drop these, set `litellm.drop_params=True` or for proxy:

`litellm_settings:
 drop_params: true`
. 
 If you want to use these params dynamically send allowed_openai_params=['seed'] in your request.
- candidate evidence: reg-commit-helper-v1-v3-bp-02--candidate--unrelated-refactor--r0: run error — UnsupportedParamsError: litellm.UnsupportedParamsError: anthropic does not support parameters: ['seed'], for model=claude-sonnet-4-5. To drop these, set `litellm.drop_params=True` or for proxy:

`litellm_settings:
 drop_params: true`
. 
 If you want to use these params dynamically send allowed_openai_params=['seed'] in your request.

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

- baseline runs: `reg-commit-helper-v1-v3-bp-02--baseline--write-a-commit-message--r0`
- candidate runs: `reg-commit-helper-v1-v3-bp-02--candidate--write-a-commit-message--r0`
- ⚠ insufficient runs (n=1v1, min=3)
- ⚠ no final evaluations on one/both sides — outcome comparison impossible
- baseline evidence: reg-commit-helper-v1-v3-bp-02--baseline--write-a-commit-message--r0: run error — UnsupportedParamsError: litellm.UnsupportedParamsError: anthropic does not support parameters: ['seed'], for model=claude-sonnet-4-5. To drop these, set `litellm.drop_params=True` or for proxy:

`litellm_settings:
 drop_params: true`
. 
 If you want to use these params dynamically send allowed_openai_params=['seed'] in your request.
- candidate evidence: reg-commit-helper-v1-v3-bp-02--candidate--write-a-commit-message--r0: run error — UnsupportedParamsError: litellm.UnsupportedParamsError: anthropic does not support parameters: ['seed'], for model=claude-sonnet-4-5. To drop these, set `litellm.drop_params=True` or for proxy:

`litellm_settings:
 drop_params: true`
. 
 If you want to use these params dynamically send allowed_openai_params=['seed'] in your request.

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

- baseline runs: `reg-commit-helper-v1-v3-bp-02--baseline--write-a-commit-message-for-stage--r0`
- candidate runs: `reg-commit-helper-v1-v3-bp-02--candidate--write-a-commit-message-for-stage--r0`
- ⚠ insufficient runs (n=1v1, min=3)
- ⚠ no final evaluations on one/both sides — outcome comparison impossible
- baseline evidence: reg-commit-helper-v1-v3-bp-02--baseline--write-a-commit-message-for-stage--r0: run error — UnsupportedParamsError: litellm.UnsupportedParamsError: anthropic does not support parameters: ['seed'], for model=claude-sonnet-4-5. To drop these, set `litellm.drop_params=True` or for proxy:

`litellm_settings:
 drop_params: true`
. 
 If you want to use these params dynamically send allowed_openai_params=['seed'] in your request.
- candidate evidence: reg-commit-helper-v1-v3-bp-02--candidate--write-a-commit-message-for-stage--r0: run error — UnsupportedParamsError: litellm.UnsupportedParamsError: anthropic does not support parameters: ['seed'], for model=claude-sonnet-4-5. To drop these, set `litellm.drop_params=True` or for proxy:

`litellm_settings:
 drop_params: true`
. 
 If you want to use these params dynamically send allowed_openai_params=['seed'] in your request.

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

- baseline runs: `reg-commit-helper-v1-v3-bp-02--baseline--write-commit-msg--r0`
- candidate runs: `reg-commit-helper-v1-v3-bp-02--candidate--write-commit-msg--r0`
- ⚠ insufficient runs (n=1v1, min=3)
- ⚠ no final evaluations on one/both sides — outcome comparison impossible
- baseline evidence: reg-commit-helper-v1-v3-bp-02--baseline--write-commit-msg--r0: run error — UnsupportedParamsError: litellm.UnsupportedParamsError: anthropic does not support parameters: ['seed'], for model=claude-sonnet-4-5. To drop these, set `litellm.drop_params=True` or for proxy:

`litellm_settings:
 drop_params: true`
. 
 If you want to use these params dynamically send allowed_openai_params=['seed'] in your request.
- candidate evidence: reg-commit-helper-v1-v3-bp-02--candidate--write-commit-msg--r0: run error — UnsupportedParamsError: litellm.UnsupportedParamsError: anthropic does not support parameters: ['seed'], for model=claude-sonnet-4-5. To drop these, set `litellm.drop_params=True` or for proxy:

`litellm_settings:
 drop_params: true`
. 
 If you want to use these params dynamically send allowed_openai_params=['seed'] in your request.

## Reproduce

```
lab regression report reg-commit-helper-v1-v3-bp-02
lab report reg-commit-helper-v1-v3-bp-02
lab compare reg-commit-helper-v1-v3-bp-02
```
