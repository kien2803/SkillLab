# Regression report: `commit-helper` `v1` → `v2-bad`

- regression: `reg-commit-helper-v1-v2-bad-01` · experiment: `reg-commit-helper-v1-v2-bad-01` · created 2026-11-18T21:06:28+07:00
- model: `mock` · injection: `available` · harness: `standard-tools-v1` · rollouts/arm·task: 3
- suite: `default` (2 task(s))

> ⚠ **model is `mock` — results are simulated and do NOT represent real-world model performance.**

## Verdict: 🔴 REGRESSED

| category | tasks |
|---|---|
| activation | 1 |

## Metrics overview

| metric | baseline | candidate | Δ |
|---|---|---|---|
| runs | 6 | 6 | — |
| error rate | 0% | 0% | +0.00 |
| success rate | 100% | 100% | +0.00 |
| rubric score | 1.00 | 1.00 | +0.00 |
| outcome variance | 0.00 | 0.00 | +0.00 |
| tokens/run | 206.50 | 178.50 | -14% |
| latency s/run | 0.00 | 0.00 | -25% |
| turns/run | 3.00 | 2.00 | -33% |
| activation recall | 100% | 0% | -1.00 |
| activation precision | 100% | — | — |
| false-activation | 0% | 0% | +0.00 |

## Per-task results

### `unrelated-refactor` (activation-negative) → — no change

| | baseline | candidate | Δ |
|---|---|---|---|
| runs | 3 (err 0) | 3 (err 0) | — |
| success | 100% | 100% | +0.00 |
| score | 1.00 | 1.00 | +0.00 |
| activated | 0% | 0% | +0.00 |
| tokens | 202.00 | 174.00 | -14% |
| latency s | 0.00 | 0.00 | -16% |
| turns | 2.00 | 2.00 | +0% |
| variance | 0.00 | 0.00 | +0.00 |

- baseline runs: `reg-commit-helper-v1-v2-bad-01--baseline--unrelated-refactor--r0`, `reg-commit-helper-v1-v2-bad-01--baseline--unrelated-refactor--r1`, `reg-commit-helper-v1-v2-bad-01--baseline--unrelated-refactor--r2`
- candidate runs: `reg-commit-helper-v1-v2-bad-01--candidate--unrelated-refactor--r0`, `reg-commit-helper-v1-v2-bad-01--candidate--unrelated-refactor--r1`, `reg-commit-helper-v1-v2-bad-01--candidate--unrelated-refactor--r2`

### `write-commit-msg` (activation-positive) → 🔴 activation

| | baseline | candidate | Δ |
|---|---|---|---|
| runs | 3 (err 0) | 3 (err 0) | — |
| success | 100% | 100% | +0.00 |
| score | 1.00 | 1.00 | +0.00 |
| activated | 100% | 0% | -1.00 |
| tokens | 211.00 | 183.00 | -13% |
| latency s | 0.00 | 0.00 | -32% |
| turns | 4.00 | 2.00 | -50% |
| variance | 0.00 | 0.00 | +0.00 |

- baseline runs: `reg-commit-helper-v1-v2-bad-01--baseline--write-commit-msg--r0`, `reg-commit-helper-v1-v2-bad-01--baseline--write-commit-msg--r1`, `reg-commit-helper-v1-v2-bad-01--baseline--write-commit-msg--r2`
- candidate runs: `reg-commit-helper-v1-v2-bad-01--candidate--write-commit-msg--r0`, `reg-commit-helper-v1-v2-bad-01--candidate--write-commit-msg--r1`, `reg-commit-helper-v1-v2-bad-01--candidate--write-commit-msg--r2`

## Reproduce

```
lab regression report reg-commit-helper-v1-v2-bad-01
lab report reg-commit-helper-v1-v2-bad-01
lab compare reg-commit-helper-v1-v2-bad-01
```
