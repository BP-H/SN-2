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
- [ ] Upload a file and confirm the link/preview still works after feed refresh.
- [ ] Open an older uploaded image if available and confirm legacy
  `uploads/<file>` paths still render.
- [ ] Vote/support a post and remove the vote.
- [ ] Confirm normal browsing does not hit rate limits.

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

## Safety Gates

- [ ] MCP remains read-only.
- [ ] No automatic AI publishing occurs without explicit approve/cancel.
- [ ] No raw provider/API key is requested in the browser.
- [ ] Protected core zero-diff is confirmed.
