# GitHub Actions versions

**Policy: pin third-party actions to version tags, never to commit SHAs.**

Several action authors — `astral-sh/setup-uv` among them — now tell you in their README to write
the dependency as a full 40-character commit SHA with the version in a trailing comment:

```yaml
- uses: astral-sh/setup-uv@<40-hex-sha>  # v10.0.1
```

That advice comes from GitHub's own supply-chain hardening guidance. A mutable tag can be moved by
whoever controls the action's repo, so a compromised or coerced maintainer can change what `@v10`
means without you touching anything. A SHA can't be moved, so it removes that class of attack.

We don't do it here, on purpose.

## Why not

The threat it defends against is real but the cost lands somewhere it doesn't pay off for this
repo:

- **Nothing worth stealing is in reach.** The test and lint workflows check out public source and
  run public tools. There are no secrets in the environment for a hostile action to exfiltrate.
- **Release doesn't hold a credential either.** Publishing uses PyPI trusted publishing over OIDC,
  so there's no long-lived API token sitting in repo secrets to steal. The blast radius of a
  compromised action is "publish a bad artifact", which pinning a SHA on `setup-uv` wouldn't
  prevent anyway — that would take compromising the publish action itself.
- **SHAs make the workflows unreadable and un-reviewable by hand.** Every bump becomes an opaque
  hex diff, and the version lives in a comment that nothing verifies, so it silently goes wrong.
  Keeping that honest realistically requires Dependabot or similar, which is a whole mechanism to
  maintain for a repo this size.

Pinning to a tag keeps the diff meaningful: you can see at a glance which version each job runs,
and a bump reviews itself.

This is a judgment call about *this* repo, not a claim that the advice is wrong. Reconsider it if
the workflows ever gain real secrets, or start running on untrusted input such as forked-PR code
with write permissions.

## How the tags are written

Keep whatever granularity each action already uses rather than unifying them:

- **`actions/*`** — the moving major tag (`@v7`). These are maintained by GitHub, keep their
  majors stable, and picking up patches automatically is the point.
- **`astral-sh/setup-uv`** — an exact release tag (`@v10.0.1`). It moves fast and has had
  behavioural changes within a major, so we take those deliberately.
- **`pypa/gh-action-pypi-publish`** — the `release/v1` branch ref that PyPA's own documentation
  prescribes. It already tracks the latest v1, so there is nothing to bump.

## Bumping

Check the action's latest release, edit the tag in `.github/workflows/`, done — no SHA lookup, no
comment to keep in sync. Bump all the workflows together so the same action isn't running at two
versions across jobs.

The related but separate problem — CI breaking because a *tool* installed by tox updated itself —
is covered in [code quality](./code-quality.md).
