# Phases 2–6

## Phase 2: Reproduce + minimise

Run the loop. Watch it go red as the bug appears.

Confirm:

- [ ] The loop produces the failure mode the **user** described, not a
      different failure that happens to be nearby. Wrong bug = wrong fix.
- [ ] The failure is reproducible across multiple runs (or, for
      non-deterministic bugs, at a high enough rate to debug against).
- [ ] You have captured the exact symptom (error message, wrong output,
      slow timing) so later phases can verify the fix addresses it.

### Minimise

Once it's red, shrink the repro to the **smallest scenario that still goes
red**. Cut inputs, callers, config, data and steps **one at a time**,
re-running the loop after each cut, and keep only what's load-bearing for
the failure.

Why bother: a minimal repro shrinks the hypothesis space in Phase 3 and
becomes the clean regression test in Phase 5.

Done when **every remaining element is load-bearing**: removing any one
makes the loop go green. Do not proceed until you have reproduced **and**
minimised.

## Phase 3: Hypothesise

Generate **3–5 ranked hypotheses** before testing any of them.
Single-hypothesis generation anchors on the first plausible idea.

Each hypothesis must be **falsifiable**: state the prediction it makes.

> Format: "If <X> is the cause, then <changing Y> will make the bug
> disappear / <changing Z> will make it worse."

If you cannot state the prediction, the hypothesis is a vibe: discard or
sharpen it.

**Show the ranked list to the user before testing.** They often have
domain knowledge that re-ranks instantly, or know hypotheses already ruled
out. Cheap checkpoint; don't block on it — proceed with your ranking if
the user is AFK.

## Phase 4: Instrument

Each probe must map to a specific prediction from Phase 3. **Change one
variable at a time.**

Tool preference:

1. **Debugger / REPL inspection** if the env supports it. One breakpoint
   beats ten logs.
2. **Targeted logs** at the boundaries that distinguish hypotheses.
3. Never "log everything and grep".

**Tag every debug log** with a unique prefix, e.g. `[DEBUG-a4f2]`. Cleanup
becomes a single grep. Untagged logs survive; tagged logs die.

**Perf branch.** For performance regressions, logs are usually wrong.
Instead: establish a baseline measurement (timing harness, profiler, query
plan), then bisect. Measure first, fix second.

## Phase 5: Fix + regression test

Write the regression test **before the fix**, but only if there is a
**correct seam** for it — a place where the test exercises the **real bug
pattern** as it occurs at the call site. If the only seam is too shallow,
a regression test there gives false confidence.

**If no correct seam exists, that itself is the finding.** Note it: the
codebase architecture is preventing the bug from being locked down.

If a correct seam exists:

1. Turn the minimised repro into a failing test at that seam.
2. Watch it fail. If you forced the red by mutating code or a fixture,
   `diff` against a pristine copy to prove the mutation landed.
3. Apply the fix.
4. Watch it pass.
5. Re-run the Phase 1 feedback loop against the original (un-minimised)
   scenario.

## Phase 6: Cleanup

Required before declaring done:

- [ ] Original repro no longer reproduces (re-run the Phase 1 loop)
- [ ] Regression test passes (or absence of seam is documented)
- [ ] All `[DEBUG-...]` instrumentation removed (`grep` the prefix)
- [ ] Throwaway prototypes deleted (or moved to a clearly-marked debug
      location)
- [ ] The confirmed hypothesis is stated in the commit / PR message, so
      the next debugger learns
