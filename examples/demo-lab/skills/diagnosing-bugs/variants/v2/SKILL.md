---
name: diagnosing-bugs
description: Diagnosis loop for hard bugs and performance regressions. Use when the user says "diagnose"/"debug this", or reports something broken/throwing/failing/slow.
---

# Diagnosing Bugs

A discipline for hard bugs. Skip phases only when explicitly justified.

If the repo carries a glossary or module index, read it first to build a
mental model of the modules you're touching, and check ADRs in the area.

## Redact

This skill has you show commands, outputs and captured artifacts. **Redact
every secret first**: write `<REDACTED>` in its place. Build loops against
env vars, so the credential stays in the environment rather than in what
you show. Captured artifacts carry auth headers: quote only the lines that
carry the signal.

If the redacted output is not enough to diagnose the bug, say so and ask
the user.

## Phase 1: Build a feedback loop

**This is the skill.** Everything else is mechanical. If you have a
**tight** pass/fail signal for the bug — one that goes red on _this_ bug —
you will find the cause. Bisection, hypothesis-testing and instrumentation
all just consume it. Without one, no amount of staring at code will save
you.

Spend disproportionate effort here. **Be aggressive. Be creative. Refuse
to give up.**

Concrete example — a failing test at the seam reaching the bug:

```bash
pytest tests/test_checkout.py::test_total_includes_tax -x --lf
# red: expected 121.00, got 100.00 → a tight signal on THIS bug
```

Ways to construct one, roughly in order:

1. Failing test at whatever seam reaches the bug.
2. Curl / HTTP script against a running dev server.
3. CLI invocation with a fixture input, diffed against a known-good snapshot.
4. Headless browser script asserting on DOM/console/network.
5. Replay a captured trace in isolation.
6. Throwaway harness over a minimal system subset.
7. Property / fuzz loop over 1000 random inputs.
8. Bisection harness between two known states.
9. Differential loop: old vs new version, diff outputs.
10. Last resort: `scripts/hitl-loop.template.sh` drives a human through a
    structured loop.

Build the right feedback loop, and the bug is 90% fixed.

### When you genuinely cannot build a loop

Stop and say so explicitly. List what you tried. Ask the user for:
(a) access to whatever environment reproduces it, (b) a redacted captured
artifact (HAR file, log dump, core dump), or (c) permission to add
temporary production instrumentation. Do **not** proceed to hypothesise
without a loop.

## Phases 2–6

Read `resources/phases.md` for the full protocol: reproduce + minimise →
hypothesise (3–5 ranked, falsifiable, shown to the user) → instrument (one
variable at a time, tagged logs) → fix with a regression test at a correct
seam → cleanup.

Guidance on tightening loops — speed, determinism, raising the
reproduction rate of flaky bugs — lives in `resources/feedback-loops.md`.

Done means: the original repro no longer reproduces, the regression test
passes (or the absence of a correct seam is documented), all
`[DEBUG-...]` instrumentation is removed, and the confirmed hypothesis is
stated in the commit / PR message.
