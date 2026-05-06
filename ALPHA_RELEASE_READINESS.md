# Alpha Release Readiness

Use this as the fast go/no-go bundle before promoting SN-2 to a public alpha or
demo candidate. It does not replace the fuller `ALPHA_QA_CHECKLIST.md`; it
collects the release-critical gates in one place.

Do not mark the candidate release-ready until manual browser smoke evidence is
recorded. Automated checks prove the app can build and the public surfaces can
boot; they do not prove the human-clicked product flows passed.

## Candidate Evidence To Record

- Candidate commit SHA:
- Release branch or tag:
- FE7 URL:
- Backend API URL:
- MCP health/connector URL, if in scope:
- Previous known-good rollback target:
- Manual QA owner and date:
- Known accepted exceptions:

## Required Automated Gates

Run these before release:

| Gate | Command / evidence | Release posture |
| --- | --- | --- |
| FE7 lint | `npm run lint` from `super-nova-2177/frontend-social-seven` | Required before release |
| FE7 build | `npm run build` from `super-nova-2177/frontend-social-seven` | Required before release |
| Mocked FE7 E2E | `PLAYWRIGHT_PORT=<free-port> npm run test:e2e` | Required before release, advisory as branch protection |
| Real-backend public E2E | `PLAYWRIGHT_REAL_BACKEND=1 NEXT_PUBLIC_API_URL=<backend> npm run test:e2e:real` | Required before release when a local/staging backend is reachable |
| Backend compile | `.venv` Python `-m py_compile super-nova-2177/backend/app.py` | Required before release |
| Alpha docs/static tests | `python -m unittest backend.tests.test_alpha_readiness_docs` | Required when readiness docs change |
| Local safe check | `python scripts/check_safe.py --local-only` | Required before release |
| Full safe check | `python scripts/check_safe.py` | Required when live public network smoke is available |
| Protected core zero-diff | `git diff --exit-code HEAD -- super-nova-2177/backend/supernova_2177_ui_weighted/supernovacore.py super-nova-2177/frontend-vite-basic/supernovacore.py` | Required before release |

If the full safe check cannot run because live network access is unavailable,
record the exact reason and run it as soon as the network path is available.

## Manual Browser Smoke Gate

Manual smoke is a release gate. Use
`ALPHA_MANUAL_SMOKE_EVIDENCE_SHEET.md` or a dated copy of
`ALPHA_SMOKE_SIGNOFF_TEMPLATE.md`.

Rows stay `NOT RUN` until a human actually clicks through the browser flow.
Automated E2E, backend probes, or screenshots from older candidates do not
convert manual rows to `PASS`.

Minimum release-critical manual flows:

- Signed-out public feed/profile/proposal reads.
- Sign up, sign in, reload, and sign out.
- Create a post or proposal.
- Comment, reply where practical, and vote.
- Follow, unfollow, open messages, and send/reload a message.
- Upload an image and confirm it renders after refresh.
- Create an AI delegate through AI Genesis.
- Generate AI review, AI comment, and AI post drafts.
- Approve and cancel AI drafts, confirming nothing publishes before approval.
- Mobile feed, composer, AI modal, delegate picker, and account modal sanity.

## Branch Protection Readiness

Branch protection remains manual until it is explicitly enabled in GitHub
settings. Do not claim it is enabled from repository docs alone.

First required checks to enable:

- `Backend local deterministic checks`
- `FE7 local deterministic checks`

Keep live/network smoke and Playwright E2E advisory for branch protection until
the workflows are stable enough to avoid noisy blocking failures.

## Deployment And Media Preflight

Before promoting a deployment, complete `DEPLOYMENT_MEDIA_PREFLIGHT.md`.

Release-critical points:

- FE7 deploy root is `super-nova-2177/frontend-social-seven`.
- Backend entrypoint remains `super-nova-2177/backend/app.py` plus the root
  compatibility `app.py` where the platform expects it.
- `NEXT_PUBLIC_API_URL` points to the intended backend API origin.
- `DATABASE_URL` points at the intended data store.
- `UPLOADS_DIR` or durable media storage is preserved across deploys.
- Uploaded image bytes are runtime state, not git state.
- Old missing upload files cannot be reconstructed unless bytes are restored
  from source files, backups, or durable storage.
- Sample `/proposals` image URLs before and after deploy.

## Rollback Gate

Before release, record:

- The git commit/tag to redeploy for FE7.
- The backend deploy/version to restore.
- The database backup or restore point.
- The upload/media storage backup or source of truth.
- The env var snapshot owner/location.

If media breaks after deploy, roll back code first, then restore upload bytes to
the expected storage path. Restore database state only if the deploy changed
data unexpectedly.

## No-Go Conditions

Do not release if any of these are true:

- Protected core has an unexpected diff.
- Public signup exposes AI as a standalone account species.
- AI drafts publish without explicit approve/cancel.
- Raw provider/API keys are requested or stored in the browser.
- `NEXT_PUBLIC_API_URL` points at the wrong backend.
- Fresh uploaded images fail after refresh in the target environment.
- Manual smoke has release-critical `FAIL` rows without an accepted exception.
