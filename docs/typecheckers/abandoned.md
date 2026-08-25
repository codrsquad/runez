# Abandoned candidates

Checkers that were tried and dropped, with the reason. Kept so the same evaluation isn't repeated
from scratch later — and so a revisit starts from what was actually observed rather than from
reputation.

## pytype

Google's checker. Its distinguishing idea is genuinely appealing for a library like this one: it
*infers* types for unannotated code instead of only trusting declarations, which should be an
advantage on a partly-annotated codebase. In practice it was dropped almost immediately.

**It can't survey a codebase that isn't already clean.** pytype analyses modules in dependency
order and stops at the first one that fails; everything downstream of a failed module is then
unreachable, so the run ends with "cannot make progress". `--keep-going` does not rescue this — it
keeps going *within* a module, not past a broken one. Every finding it produced came from a single
early module, and the large majority of the source tree was never looked at. That makes it useless
for the survey we're doing, which is precisely a survey of code with existing errors.

**It found nothing the others missed.** Every one of its findings was independently reported by two
other checkers in the line-up. The interesting one — an `Optional` dereference in a code path whose
own comment says failing is intentional — is real, but it is not pytype's to claim.

**It lags.** The release we ran was roughly a year old, its supported Python range trails the
versions this project targets, and it needed its own pinned interpreter in tox to run at all.

**It's slow.** Wall-clock was two orders of magnitude off the Rust-based checkers on the same
source, which matters when the workflow is "change something, re-run everything, compare".

Worth revisiting only if it picks up active development again. The inference-first approach is
still the most genuinely different idea in the field, and if it could survey a dirty codebase it
would earn its slot back.
