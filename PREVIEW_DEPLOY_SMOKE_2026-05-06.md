# Preview Deploy Smoke - 2026-05-06

This note prepares the actual alpha preview deploy smoke after PR #72. It is a
deploy-readiness checklist and verification record only. It does not change
runtime behavior, branch settings, deployment settings, environment variables,
database state, uploads, or SN-1 branches.

## Branch Protection Verification

- Repository: `BP-H/SN-2`
- Branch checked: `master`
- Verification method: public GitHub branch metadata
- Verification result on 2026-05-06: `protected: false`
- Required status checks enforcement: `off`
- Required checks visible on the branch metadata: none

The owner is manually enabling branch protection/rulesets. This workspace did
not verify that protection is enabled yet, so branch protection remains an owner
next action.

The required checks to enable remain:

- `Backend local deterministic checks`
- `FE7 local deterministic checks`

## Preview URL Status

Preview/deploy URL: `NOT PROVIDED`

No preview URL was present in the prompt, environment, or active release docs
checked for this pass. Safe GET-only checks against a preview deployment were
therefore not run. This does not block the local release gates, but the owner
must deploy a preview and paste the URL/results next.

## Preview Deploy Configuration

Before preview deploy:

1. Set the FE7 deploy root to `super-nova-2177/frontend-social-seven`.
2. Keep the backend pointed at `super-nova-2177/backend/app.py`, plus root
   compatibility `super-nova-2177/app.py` if the deployment platform expects it.
3. Verify `NEXT_PUBLIC_API_URL` points to the intended backend API origin.
4. Verify `DATABASE_URL` points to the intended database.
5. Verify `UPLOADS_DIR` or durable media storage points to the intended media
   storage.
6. Do not run DB reset, seed, drop, truncate, migration reset, upload cleanup,
   env changes, or SN-1 sync during preview deploy smoke.

## Data Snapshot Plan

Before deploy or preview promotion:

```powershell
python scripts/public_data_snapshot.py <backend-url>
```

After deploy or preview promotion:

```powershell
python scripts/public_data_snapshot.py <backend-url>
```

Compare:

- endpoint status for `/health`, `/supernova-status`, and
  `/proposals?filter=latest&limit=30`
- proposal sample count
- proposal IDs and titles
- sampled media URLs
- `/uploads/...` URLs that should still resolve when bytes exist
- `data:image/...` URLs, which must remain data URLs and must not be prefixed
  with the backend origin

## Browser Smoke Plan

Run quick human browser smoke after preview deploy. Do not mark rows `PASS`
unless the flow was actually clicked in a browser.

Release-critical rows:

- signed-out feed renders
- create post/proposal
- comment
- vote/support
- upload image and refresh feed/detail
- existing image display where bytes exist
- AI delegate create
- AI review draft approve/cancel
- AI comment draft approve/cancel
- AI post draft approve/cancel
- mobile feed/composer/AI modal sanity

Fix only explicit `FAIL` or `BLOCKED` rows with evidence.

## Manual Smoke Status

Manual browser smoke remains owner-reported but not fully itemized. No detailed
manual rows were changed to `PASS` in this pass.

No detailed manual rows were changed to `PASS`.

## SN-1 And Data Safety

SN-1 sync was not performed.

Future SN-1 sync remains later only and non-default-branch-first. Git does not
carry DB rows, posts, comments, votes, messages, or uploaded image bytes.
Protect `DATABASE_URL`, `UPLOADS_DIR` or durable media storage, and
`NEXT_PUBLIC_API_URL` before any deploy or branch sync.

Git does not carry DB rows or uploaded image bytes.

## Recommendation

Proceed with owner-side branch protection setup and preview deployment. After a
preview URL exists, run safe GET-only checks, before/after public data snapshots,
and the quick browser smoke rows above. Controlled alpha/preview remains `GO`
only with the known caveat that branch protection was not yet verified enabled
from this workspace.

## Rollback

This note is docs/static-test only. Revert this PR to remove it. If a future
preview deploy breaks media, roll back code first, restore upload bytes second,
and restore DB only if data changed unexpectedly.
