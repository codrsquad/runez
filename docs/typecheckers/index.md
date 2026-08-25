# Type checkers

runez is not type-tight yet. It grew up before annotations were common, and it leans on patterns —
dynamically-built metaclasses, descriptors, deliberate monkey-patching of `logging` and `sys.stdout`
— that type checkers have genuinely different opinions about. That makes it an unusually good
specimen for a comparison: there is real, ambiguous material to disagree over, rather than a clean
codebase where everything agrees on zero.

So rather than pick a checker and start silencing it, we're running several and looking at what each
one actually says.

## What we're trying to learn

- **Where do they agree?** A finding every checker reports independently is very likely a real
  design problem, not a quirk of one engine's inference. That consensus set is what we intend to
  fix first.
- **Where do they disagree, and why?** A finding only one tool reports is the interesting case. It
  might be a rule the others don't implement, a difference in how far inference is pushed, or one
  tool being wrong. Each divergence has to be understood before it's worth acting on — the
  disagreements teach more about the code than the agreements do.
- **How much of what they report is design signal versus noise?** runez ships `py.typed`, so its
  annotations are a promise to users. An error that points at a loose signature is worth acting on;
  one that points at a convention the ecosystem doesn't actually follow is not.

We are explicitly *not* trying to reach zero on all of them, and not trying to crown a winner yet.

## Why the ignore markers are gone

The repo used to carry a handful of `# type: ignore[...]` comments. They have all been removed on
purpose, and nothing should add one back while this exploration is running.

They had to go because they made the comparison meaningless. Those markers use mypy's error codes,
and each checker honours that syntax differently — some suppressed all of them, some suppressed
none, and one silently ignored the bracketed code entirely. The same line was therefore invisible to
one tool and reported by another for reasons that had nothing to do with the code. Every checker now
sees the same source and gets the same chance to complain.

The second reason is that a suppression comment is a decision recorded in the wrong place. It
asserts "this is fine" without saying why, and it is written for one checker's vocabulary. Where a
finding really is acceptable, we would rather fix the signature so that every checker agrees, or
write down the reasoning here.

## The line-up

Seven checkers, chosen to cover distinct engines rather than distinct configurations — several
share a lineage, and seeing where relatives diverge is part of the point.

| Checker | Lineage | Notes |
| --- | --- | --- |
| mypy | the reference implementation | defines the semantics the ecosystem is written against |
| zuban | independent reimplementation of mypy's rules | reads the same config, so config is held constant and only the engine varies |
| pyright | Microsoft | the de-facto strict baseline, and what most editors run |
| basedpyright | fork of pyright | pyright's engine with much stricter defaults |
| pyrefly | Meta, successor to pyre | |
| ty | Astral | pre-1.0, expect churn |
| pytype | Google | infers types for unannotated code instead of trusting declarations |

This set will be trimmed once we know which ones are actually telling us different things.

## Running them

Each checker is its own tox environment named after it — `tox -e mypy`, `tox -e ty`, and so on.
They are not wired into CI and are not a gate; they are exploration tools for now. `tox.ini` and the
per-tool sections in `pyproject.toml` are the authority on how each is configured.

All of them are pointed at `src` and told to assume the minimum supported Python, so the comparison
is like-for-like. Two of them share configuration on purpose: zuban reads the `[tool.mypy]` section,
so it and mypy run the same declared rules on different engines.

Expect the counts to move as these tools release; several are young and one is pre-1.0. A raw count
says very little anyway — a checker reporting more is not thereby finding more, and the tools differ
in how aggressively they warn about merely-unannotated code as opposed to actual conflicts.

## Where the findings go

As each checker is worked through, it gets its own page here recording what it found and what that
turned out to mean. The cross-checker synthesis — the agreement and divergence sets, and the
recommendation — lands in a results page once there is something to synthesise. Nothing is written
up yet; this page is the intent.
