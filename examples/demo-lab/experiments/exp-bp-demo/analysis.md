# Report: exp-bp-demo

**Hypothesis:** commit messages inconsistent

- model: `mock` · injection: `available` · rollouts/arm: 3
- runs found: 6

## Arms

| arm | n | err | incomplete | activation | false-act | act@turn | rubric | success | tokens | load-cost | turns | variance |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| control | 3 | 0 | 3 | 0% | — | — | — | — | 396.00 | — | 3.00 | — |
| treatment | 3 | 0 | 3 | 0% | — | — | — | — | 419.00 | — | 3.00 | — |

## Skill usage

- `control` **code-review**: offered 3 run(s), activated 3
- `control` **commit-helper**: offered 3 run(s), activated 0
- `control` **diagnosing-bugs**: offered 3 run(s), activated 0
- `control` **grill-with-docs**: offered 3 run(s), activated 0
- `treatment` **code-review**: offered 3 run(s), activated 3
- `treatment` **commit-helper**: offered 3 run(s), activated 0
- `treatment` **demo-skill**: offered 3 run(s), activated 0
- `treatment` **diagnosing-bugs**: offered 3 run(s), activated 0
- `treatment` **grill-with-docs**: offered 3 run(s), activated 0

## Warnings

- arm `control` has 3 run(s) but no rubric scores — outcome data insufficient (missing rubric or all runs errored)
- arm `treatment` has 3 run(s) but no rubric scores — outcome data insufficient (missing rubric or all runs errored)

## Runs

- `exp-bp-demo--control--write-a-commit-message--r0` ⚠ eval=error
- `exp-bp-demo--control--write-a-commit-message--r1` ⚠ eval=error
- `exp-bp-demo--control--write-a-commit-message--r2` ⚠ eval=error
- `exp-bp-demo--treatment--write-a-commit-message--r0` ⚠ eval=error
- `exp-bp-demo--treatment--write-a-commit-message--r1` ⚠ eval=error
- `exp-bp-demo--treatment--write-a-commit-message--r2` ⚠ eval=error
