# Report: exp-trigger-wording

**Hypothesis:** v1 (concrete trigger examples) activates on positive tasks and stays quiet on negative ones; v2 (vague description) misbehaves

- model: `mock` · injection: `available` · rollouts/arm: 3
- runs found: 24

## Arms

| arm | n | err | activation | false-act | rubric | success | tokens | turns | variance |
|---|---|---|---|---|---|---|---|---|---|
| control | 8 | 0 | 0% | 0% | — | 100% | 171.00 | 2.00 | — |
| good-desc | 8 | 0 | 100% | 0% | — | 100% | 206.50 | 3.00 | — |
| bad-desc | 8 | 0 | 0% | 0% | — | 100% | 178.50 | 2.00 | — |

## Skill usage

- `good-desc` **commit-helper**: offered 8 run(s), activated 4 · read: resources/style.md
- `bad-desc` **commit-helper**: offered 8 run(s), activated 0

## Suggested insights *(review before recording)*

- `good-desc` vs `control`: activation +100% — trigger wording may matter

Record with: `lab insight new "<statement>" --evidence exp-trigger-wording`

## Runs

- `exp-trigger-wording--bad-desc--unrelated-refactor--r0`
- `exp-trigger-wording--bad-desc--unrelated-refactor--r0--b2`
- `exp-trigger-wording--bad-desc--unrelated-refactor--r1`
- `exp-trigger-wording--bad-desc--unrelated-refactor--r2`
- `exp-trigger-wording--bad-desc--write-commit-msg--r0`
- `exp-trigger-wording--bad-desc--write-commit-msg--r0--b2`
- `exp-trigger-wording--bad-desc--write-commit-msg--r1`
- `exp-trigger-wording--bad-desc--write-commit-msg--r2`
- `exp-trigger-wording--control--unrelated-refactor--r0`
- `exp-trigger-wording--control--unrelated-refactor--r0--b2`
- `exp-trigger-wording--control--unrelated-refactor--r1`
- `exp-trigger-wording--control--unrelated-refactor--r2`
- `exp-trigger-wording--control--write-commit-msg--r0`
- `exp-trigger-wording--control--write-commit-msg--r0--b2`
- `exp-trigger-wording--control--write-commit-msg--r1`
- `exp-trigger-wording--control--write-commit-msg--r2`
- `exp-trigger-wording--good-desc--unrelated-refactor--r0`
- `exp-trigger-wording--good-desc--unrelated-refactor--r0--b2`
- `exp-trigger-wording--good-desc--unrelated-refactor--r1`
- `exp-trigger-wording--good-desc--unrelated-refactor--r2`
- `exp-trigger-wording--good-desc--write-commit-msg--r0`
- `exp-trigger-wording--good-desc--write-commit-msg--r0--b2`
- `exp-trigger-wording--good-desc--write-commit-msg--r1`
- `exp-trigger-wording--good-desc--write-commit-msg--r2`
