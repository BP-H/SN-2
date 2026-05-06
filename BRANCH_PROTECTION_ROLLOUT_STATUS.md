# Branch Protection Rollout Status

This file records the current enforcement posture so SuperNova does not jump from manual safety checks to strict branch rules too quickly.

## Current Status

| Area | Status | Notes |
| --- | --- | --- |
| Manual local checks | Active | `python scripts/check_safe.py --local-only` is available. |
| Public protocol smoke | Active | Daily/manual GitHub Action exists and live smoke passes when deployment is healthy. |
| Local safe-check workflow | Active, manual-only | `.github/workflows/local-safe-pr-gates.yml` is available for PRs, but not required as a blocking branch rule yet. |
| FE7 lint/build | Covered by workflow and manual runs | Workflow job `FE7 local deterministic checks`; manual fallback is `npm run lint` and `npm run build` in `super-nova-2177/frontend-social-seven`. |
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

These jobs cover focused backend deterministic tests, FE7 lint/build, the local
safe check, and protected core zero-diff. Keep live/network smoke checks advisory
for now because they depend on deployment and public network availability.

## Alpha Release Readiness Note

As of the alpha readiness bundle, branch protection is still not verified as
enabled in GitHub settings. Treat this document as rollout instructions only
until someone manually confirms the repository settings.

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
