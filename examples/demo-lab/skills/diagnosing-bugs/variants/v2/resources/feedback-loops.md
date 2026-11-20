# Tightening the feedback loop

Treat the loop as a product. Once you have _a_ loop, **tighten** it:

- Can I make it faster? (Cache setup, skip unrelated init, narrow the test
  scope.)
- Can I make the signal sharper? (Assert on the specific symptom, not
  "didn't crash".)
- Can I make it more deterministic? (Pin time, seed RNG, isolate
  filesystem, freeze network.)

A 30-second flaky loop is barely better than no loop; a 2-second
deterministic one is a debugging superpower.

A loop that is red-capable must be:

- **Red-capable**: drives the actual bug code path and asserts the
  **user's exact symptom** — not "runs without erroring".
- **Deterministic**: same verdict every run (flaky bugs: a pinned, high
  reproduction rate, see below).
- **Fast**: seconds, not minutes.
- **Agent-runnable**: unattended; a human enters only via
  `scripts/hitl-loop.template.sh`.

## Non-deterministic bugs

The goal is not a clean repro but a **higher reproduction rate**. Loop the
trigger 100×, parallelise, add stress, narrow timing windows, inject
sleeps. A 50%-flake bug is debuggable; 1% is not — keep raising the rate
until it's debuggable.

If you catch yourself reading code to build a theory before a red-capable
command exists, **stop**: jumping straight to a hypothesis is the exact
failure this skill prevents.
