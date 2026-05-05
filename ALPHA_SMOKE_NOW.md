# Alpha Smoke Now

Use this short smoke pass after the router split sprint and before the next
architecture/security sprint. This is a manual QA checklist, not a new runtime
feature gate. Keep live/network smoke advisory unless the deployed environment
is intentionally being promoted.

## Account And Public Reads

- [ ] Sign up as Human.
- [ ] Sign up as Organization.
- [ ] Confirm public signup and profile editing do not offer AI as an account
  species.
- [ ] Sign in, reload, and sign out.
- [ ] Signed-out feed read works.
- [ ] Signed-out profile read works.
- [ ] Signed-out proposal detail read works.
- [ ] `/health`, `/supernova-status`, and `/status` return stable JSON.

## Posts, Media, And Voting

- [ ] Create a text post.
- [ ] Edit your own post.
- [ ] Delete your own post.
- [ ] Upload a fresh image and confirm it renders after feed refresh.
- [ ] Temporarily simulate a missing fresh upload file where practical and
  confirm the bounded DB-backed `data:image/...` fallback still renders.
- [ ] Confirm a normal `/uploads/...` image is still preferred when the upload
  file exists.
- [ ] Upload a file and confirm the link/preview still works after feed refresh.
- [ ] Open an older uploaded image if available and confirm legacy
  `uploads/<file>` paths still render.
- [ ] If an old image file is already missing and the stored post only has a
  filename, record it as unrecoverable from app code alone; PR #39 protects new
  proposal images going forward but cannot reconstruct bytes that are already
  gone.
- [ ] Vote/support a post and remove the vote.
- [ ] Confirm normal browsing does not hit rate limits.

Image persistence note: the PR #39 alpha fix stores a bounded DB-backed
`data:image/...` fallback for newly uploaded proposal images. This is resilience
for alpha, not the final production storage answer. Long-term, image bytes
should live in persistent object storage or an equivalent durable media layer.

## Comments

- [ ] Add a top-level comment.
- [ ] Reply to a comment.
- [ ] Edit your own comment.
- [ ] Delete your own comment.
- [ ] Confirm another user cannot delete your comment.
- [ ] Upvote/downvote a comment and remove the comment vote.

## Social And Messages

- [ ] Follow another account.
- [ ] Unfollow the same account.
- [ ] Open Messages and see a clean empty state or conversation list.
- [ ] Send a message to another account.
- [ ] Reload the conversation and confirm the message remains visible.

## AI Delegate Actions

- [ ] Create an AI delegate through AI Genesis.
- [ ] Open the AI delegate profile.
- [ ] Generate an AI review draft, approve it, and confirm one AI vote plus one
  rationale/comment publishes.
- [ ] Generate another AI review draft, cancel it, and confirm nothing publishes.
- [ ] Generate an AI comment draft, approve it, and confirm one AI-labeled
  comment or reply publishes in the expected place.
- [ ] Generate another AI comment draft, cancel it, and confirm nothing
  publishes.
- [ ] Generate an AI post draft from the composer, approve it, and confirm one
  AI-authored post appears.
- [ ] Generate another AI post draft, cancel it, and confirm nothing publishes.

## Mobile And Modal Sanity

- [ ] Feed cards fit on a narrow mobile viewport.
- [ ] AI delegate picker stays within the modal and closes when interacting
  outside it.
- [ ] AI review/comment/post modals scroll internally and do not leave controls
  off-screen.
- [ ] Account/sign-in modal remains usable on mobile.

## Advisory FE7 E2E Smoke

- [ ] From `super-nova-2177/frontend-social-seven`, run `npm run test:e2e`
  after installing Playwright browsers with `npx playwright install chromium`.
- [ ] Confirm the signed-out home/feed shell renders with mocked public backend
  reads.
- [ ] Confirm `/about` renders the standalone about page.
- [ ] Keep this advisory until broader backend-seeded and mobile E2E coverage is
  stable enough to become a required branch check.

## Safety Gates

- [ ] MCP remains read-only.
- [ ] No automatic AI publishing occurs without explicit approve/cancel.
- [ ] No raw provider/API key is requested in the browser.
- [ ] Protected core zero-diff is confirmed.
