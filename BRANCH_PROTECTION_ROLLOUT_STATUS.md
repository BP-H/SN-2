# Branch Protection Rollout Status

This file records the current enforcement posture so SuperNova does not jump from manual safety checks to strict branch rules too quickly.

## Current Status

| Area | Status | Notes |
| --- | --- | --- |
| Manual local checks | Active | `python scripts/check_safe.py --local-only` is available. |
| Public protocol smoke | Active | Daily/manual GitHub Action exists and live smoke passes when deployment is healthy. |
| Local safe-check workflow | Active, PR-only | `.github/workflows/local-safe-pr-gates.yml` exposes the two candidate required checks on PRs, but they are not required as blocking branch rules until manually enabled in GitHub settings. |
| Backend deterministic gates | Covered by workflow and manual runs | Workflow job `Backend local deterministic checks` runs backend compile, alpha readiness docs tests, focused backend tests, local safe check, and protected core zero-diff. |
| FE7 lint/build | Covered by workflow and manual runs | Workflow job `FE7 local deterministic checks` runs `npm ci`, `npm run lint`, and `npm run build` in `super-nova-2177/frontend-social-seven`. |
| Protected core diff check | Active locally | `scripts/check_safe.py` checks protected core zero diff. |
| CODEOWNERS | Syntax validated through PR #8; auto-review inconclusive | PR #8 touched a CODEOWNERS-protected docs file and merged cleanly. Auto-review behavior remains inconclusive because the PR author was also the repo owner/CODEOWNER. |
| Required checks | Not enabled | No workflow is required as a blocking branch rule yet. |
| Strict branch protection | Not enabled | Wait until workflows are stable and CODEOWNERS behavior is confirmed. |

## Candidate Required Checks

When branch protection is enabled manually in GitHub settings, start with these
required status checks from `.github/workflows/local-safe-pr-gates.yml`:

- `Backend local deterministic checks`
- `FE7 local deterministic checks`

Manual GitHub settings for the first protected-branch rollout:

- Enable `Require status checks to pass before merging`.
- Enable `Require branches to be up to date before merging`.
- Select only `Backend local deterministic checks` and `FE7 local deterministic
  checks` as required checks at first.
- Leave live/network smoke checks advisory and unrequired until deployment
  dependencies are stable enough to be a blocking gate.

These jobs cover backend compile, alpha readiness docs tests, focused backend
deterministic tests, FE7 lint/build, the local safe check, and protected core
zero-diff. Keep live/network smoke checks advisory for branch protection for
now. Mocked Playwright and real-backend Playwright also remain release
evidence, but not required PR blockers.

## Alpha Release Readiness Note

As of the alpha readiness bundle, branch protection is still not verified as
enabled in GitHub settings. Treat this document as rollout instructions only
until someone manually confirms the repository settings.

## 2026-05-06 Verification

The owner asked to protect the branch during the alpha preview gate pass. The
workflow/check names are present and branch-protection-ready:

- `Backend local deterministic checks`
- `FE7 local deterministic checks`

Public GitHub branch metadata for `BP-H/SN-2` `master` reported
`protected: false` and required status check enforcement `off` on 2026-05-06.
This workspace could not enable branch protection directly because `gh` is not
installed, no GitHub token is present in the environment, and the available
GitHub connector tools do not expose branch protection or repository ruleset
mutation. The remaining action is still manual GitHub settings setup with the
two checks above.

For an alpha release, the two checks above are the only recommended required
branch checks. Mocked Playwright, real-backend Playwright, full live/network
smoke, and deployment smoke should remain release evidence and advisory checks,
not required branch-protection gates yet.

Rollback for an accidentally over-strict setup: remove the required checks in
GitHub branch protection settings. Local emergency runtime rollback for alpha
rate-limit problems remains `SUPERNOVA_RATE_LIMIT_ENABLED=false`.

## Next Validation Steps

Do these without changing runtime behavior:

1. Use a future PR from a different contributor or bot to confirm CODEOWNERS auto-review requests.
2. Confirm public protocol smoke and local safe-check workflows can still be run manually.
3. Enable only the two candidate required checks above after they are stable
   across several PRs.

## Do Not Enable Yet

Do not enable required branch rules for:

- Strict deployment checks.
- Auth enforcement.
- Database migrations.
- Real domain verification.
- Webmention intake.
- ActivityPub inbox writes.
- Execution-intent pipelines.

Those systems are not mature enough to become branch-protection gates.

## Cleanup Rule

Cleanup must stay branch-tested. The cleanup snapshot is an inventory, not deletion approval.
