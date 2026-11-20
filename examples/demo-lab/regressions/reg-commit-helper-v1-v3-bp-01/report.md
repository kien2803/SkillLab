# Regression report: `commit-helper` `v1` → `v3-bp`

- regression: `reg-commit-helper-v1-v3-bp-01` · experiment: `reg-commit-helper-v1-v3-bp-01` · created 2026-11-20T19:25:47+07:00
- model: `mock` · injection: `available` · harness: `standard-tools-v1` · rollouts/arm·task: 2
- suite: `default` (2 task(s))

> ⚠ **model is `mock` — results are simulated and do NOT represent real-world model performance.**

## Verdict: 🟡 INCONCLUSIVE

## Metrics overview

| metric | baseline | candidate | Δ |
|---|---|---|---|
| runs | 4 | 4 | — |
| error rate | 0% | 0% | +0.00 |
| success rate | 100% | 100% | +0.00 |
| rubric score | 1.00 | 1.00 | +0.00 |
| outcome variance | 0.00 | 0.00 | +0.00 |
| tokens/run | 390.00 | 373.00 | -4% |
| latency s/run | 0.00 | 0.00 | -8% |
| turns/run | 2.50 | 2.50 | +0% |
| activation recall | 0% | 0% | +0.00 |
| activation precision | — | — | — |
| false-activation | 0% | 0% | +0.00 |

## Per-task results

### `unrelated-refactor` (activation-negative) → — no change

| | baseline | candidate | Δ |
|---|---|---|---|
| runs | 2 (err 0) | 2 (err 0) | — |
| success | 100% | 100% | +0.00 |
| score | 1.00 | 1.00 | +0.00 |
| activated | 0% | 0% | +0.00 |
| tokens | 386.00 | 369.00 | -4% |
| latency s | 0.00 | 0.00 | -14% |
| turns | 2.00 | 2.00 | +0% |
| variance | 0.00 | 0.00 | +0.00 |

- baseline runs: `reg-commit-helper-v1-v3-bp-01--baseline--unrelated-refactor--r0`, `reg-commit-helper-v1-v3-bp-01--baseline--unrelated-refactor--r1`
- candidate runs: `reg-commit-helper-v1-v3-bp-01--candidate--unrelated-refactor--r0`, `reg-commit-helper-v1-v3-bp-01--candidate--unrelated-refactor--r1`
- ⚠ insufficient runs (n=2v2, min=3)

### `write-commit-msg` (activation-positive) → — no change

| | baseline | candidate | Δ |
|---|---|---|---|
| runs | 2 (err 0) | 2 (err 0) | — |
| success | 100% | 100% | +0.00 |
| score | 1.00 | 1.00 | +0.00 |
| activated | 0% | 0% | +0.00 |
| tokens | 394.00 | 377.00 | -4% |
| latency s | 0.00 | 0.00 | -2% |
| turns | 3.00 | 3.00 | +0% |
| variance | 0.00 | 0.00 | +0.00 |

- baseline runs: `reg-commit-helper-v1-v3-bp-01--baseline--write-commit-msg--r0`, `reg-commit-helper-v1-v3-bp-01--baseline--write-commit-msg--r1`
- candidate runs: `reg-commit-helper-v1-v3-bp-01--candidate--write-commit-msg--r0`, `reg-commit-helper-v1-v3-bp-01--candidate--write-commit-msg--r1`
- ⚠ insufficient runs (n=2v2, min=3)

## Reproduce

```
lab regression report reg-commit-helper-v1-v3-bp-01
lab report reg-commit-helper-v1-v3-bp-01
lab compare reg-commit-helper-v1-v3-bp-01
```
