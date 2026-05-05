# Cleanup Candidates Snapshot

Generated on 2026-04-26 from:

```powershell
python scripts/list_cleanup_candidates.py
```

This is a read-only inventory. It is not approval to delete anything from `master`. Any cleanup should happen on a separate branch, one candidate class at a time, with backend safety tests, FE7 lint/build, public protocol smoke, and protected-core zero diff.

## Completed Cleanup

- `super-nova-2177/backend/supernova_2177_ui_weighted/combined_repo.md` was removed in PR #9.
- It was a generated combined repository snapshot only.
- Reference search found no runtime imports or deployment references.
- Full checks passed before merge.
- Four tracked backup Python files were removed in PR #10 after reference checks and full safety checks.
- `super-nova-2177/frontend-nova` was deleted after launcher retirement and
  fresh reference checks found no active package, deployment, workflow, or
  runtime references.
- `super-nova-2177/frontend-professional` runnable local launcher support was
  retired; the source folder remains a cleanup candidate for a later
  single-target deletion PR.

## Legacy Or Experimental Frontend Trees

- `super-nova-2177/frontend-next`
- `super-nova-2177/frontend-professional`
- `super-nova-2177/frontend-social-six`
- `super-nova-2177/frontend-vite-3d`
- `super-nova-2177/frontend-vite-basic`

## Nested Backend Experiments

- `super-nova-2177/backend/supernova_2177_ui_weighted/backend/Dockerfile`
- `super-nova-2177/backend/supernova_2177_ui_weighted/backend/__init__.py`
- `super-nova-2177/backend/supernova_2177_ui_weighted/backend/app.py`
- `super-nova-2177/backend/supernova_2177_ui_weighted/backend/docker-compose.yml`
- `super-nova-2177/backend/supernova_2177_ui_weighted/backend/requirements.txt`

## Node Lockfiles Inside Backend Or Module Trees

- `super-nova-2177/backend/supernova_2177_ui_weighted/nova-web/package-lock.json`
- `super-nova-2177/backend/supernova_2177_ui_weighted/package-lock.json`

## Tracked Uploads

- `super-nova-2177/backend/uploads/1bb86e27e1c741b08274c4753f393777`
- `super-nova-2177/backend/uploads/380fa79e48e847f7a83acf32f7b424cb`
- `super-nova-2177/backend/uploads/4f7003858bbd41a89a17743a562543f0`

## Typo-Named Tracked Files

- `super-nova-2177/backend/supernova_2177_ui_weighted/transcendental_resonance_frontend/tr_pages/animate_gaussion.py`
- `super-nova-2177/frontend-next/content/proposal/content/LikesDeslikes.jsx`
- `super-nova-2177/frontend-social-seven/content/proposal/content/LikesDeslikes.jsx`
- `super-nova-2177/frontend-social-six/content/proposal/content/LikesDeslikes.jsx`
- `super-nova-2177/frontend-vite-3d/src/components/LikesDeslikes.tsx`
- `super-nova-2177/frontend-vite-basic/src/components/LikesDeslikes.tsx`

## Cleanup Rule

Review these on a separate cleanup branch before deleting or renaming anything.
