# Backend Route Split Plan

This inventory is a guardrail for reducing `backend/app.py` without changing runtime
behavior. It is intentionally conservative: route paths, response shapes, auth checks,
rate-limit buckets, database schema, frontend behavior, AI behavior, and SuperNova Core
semantics must stay unchanged during each extraction.

## Already Extracted

### Status / Health

- Module: `backend/status_routes.py`
- Paths: `GET /health`, `GET /supernova-status`, `GET /status`
- Dependencies kept in `app.py`: `get_db`, `DB_ENGINE_URL`, `CORS_CONFIG`, `_runtime`,
  `SUPER_NOVA_AVAILABLE`, `SUPER_NOVA_CORE_ROUTES`, `_build_status_payload`
- Models/tables: health probes use `SELECT 1`; `/status` uses aggregate reads through
  `_build_status_payload`
- Auth: public
- Frontend surfaces: health checks, deployment checks, public status consumers
- Existing tests: `test_status_routes_extraction.py`, `test_commons_rate_limits.py`,
  `test_public_federation_safety.py`
- Risk: low, already extracted
- Notes: keep these routes in the same middleware stack; rate-limit behavior remains
  owned by app middleware.

### Commons Rate Limiting

- Module: `backend/commons_rate_limits.py`
- Paths: middleware-only; no route paths
- Dependencies kept in `app.py`: FastAPI middleware registration, `jwt`, `get_settings`
- Models/tables: none; single-instance in-memory alpha buckets
- Auth: derives identity from bearer token where available, falls back to IP
- Frontend surfaces: all API routes indirectly
- Existing tests: `test_commons_rate_limits.py`
- Risk: low, already extracted
- Notes: Redis-backed counters are deferred; rollback switch remains
  `SUPERNOVA_RATE_LIMIT_ENABLED=false`.

### Messages

- Module: `backend/routers/messages.py`
- Paths: `GET /messages`, `POST /messages`
- Dependencies kept in `app.py`: `get_db`, `DirectMessageIn`, `_safe_user_key`,
  `_require_token_identity_match`, `_canonical_username_from_alias`,
  `_conversation_id`, `_ensure_direct_messages_table`, `_message_payload`,
  `_read_messages_store`, `_write_messages_store`
- Models/tables: `direct_messages`, `Harmonizer` for auth/user resolution where
  available; fallback `messages_store.json`
- Auth: bearer token required for current-user conversation reads and sends; username
  alias matching remains important after profile username changes
- Frontend surfaces: messages section/conversation list, message composer
- Existing tests: `test_messages_pagination.py`, `test_auth_bound_write_routes.py`,
  `test_message_routes_extraction.py`
- Risk: low-medium, already extracted
- Notes: route paths, response shapes, direct table behavior, fallback JSON store
  behavior, pagination, and auth semantics are intended to be unchanged.

## Route Groups Still In `backend/app.py`

### Auth / Profile / Session

- Paths:
  - `POST /users/register`
  - `POST /auth/login`
  - `GET /auth/social/profile`
  - `POST /auth/social/sync`
  - `GET /users/me`
  - `GET /profile/{username}`
  - `PATCH /profile/{username}`
  - imported login router: `POST /token`, `POST /login`, `POST /logout`
- Current helper dependencies: `_normalize_public_account_species`,
  `_hash_password_strict`, `_verify_password_with_legacy_upgrade`,
  `_create_wrapper_access_token`, `_public_user_payload`, `_auth_fields_for_user`,
  `_find_social_user`, `_sync_user_avatar_references`, `_profile_metadata`,
  `_profile_identity_payload`, `_require_token_identity_match`,
  `_optional_token_identity_match`, username alias helpers, avatar helpers
- Models/tables: `Harmonizer`, `username_aliases`, `profile_metadata`, proposal/comment
  rows for avatar/profile sync
- Auth requirements: mixed public signup/login; bearer token required for `/users/me`
  and profile mutation; public `species=ai` is forbidden
- Frontend surfaces: Account modal, profile edit page, social auth sync, header/session
  state, profile pages
- Existing tests: `test_auth_bound_write_routes.py`,
  `test_public_federation_safety.py`, `test_secret_key_hardening.py`
- Missing tests before extraction: direct profile-update alias regression after username
  change; social auth duplicate-email/candidate suffix test; legacy login-router parity
  test if moved alongside wrapper auth
- Risk: high
- Recommended module: `routers/auth_profile.py`
- Extraction notes: do not combine with public federation profile exports. Preserve the
  public-account species guard and username alias behavior first.

### Proposals / Posts

- Paths:
  - `GET /proposals`
  - `POST /proposals`
  - `GET /proposals/{pid}`
  - `PATCH /proposals/{pid}`
  - `DELETE /proposals/{pid}`
  - `DELETE /proposals`
  - `GET /proposals/{pid}/tally-weighted`
  - `POST /decide/{pid}`
  - `GET /decisions`
  - `POST /runs`
  - `GET /runs`
- Current helper dependencies: `_require_token_identity_match`,
  `_proposal_governance_payload`, `_proposal_payload`, `_proposal_media_payload`,
  `_proposal_collab_payload`, `_ensure_proposal_read_indexes`,
  `_ensure_comment_thread_columns`, `_comment_payload`, `_comment_vote_summary`,
  `_uploads_url`, upload validation helpers, mention notification helpers,
  weighted vote helpers from SuperNova runtime
- Models/tables: `Proposal`, `ProposalVote`, `Comment`, `Decision`, `Run`,
  `ProposalCollab`, `Notification`, harmonizer rows for authors/collabs
- Auth requirements: public reads; bearer token required for create/update/delete and
  identity-bound author writes; AI-authored posts are approval-routed elsewhere
- Frontend surfaces: feed cards, post detail, create composer, profile posts,
  collaboration UI, AI action modal refreshes
- Existing tests: `test_proposal_write_auth_routes.py`,
  `test_proposal_embedded_caps.py`, `test_proposal_mention_notifications.py`,
  `test_proposal_collab_*`, `test_read_pagination_baseline.py`,
  `test_connector_action_proposal_model.py`
- Missing tests before extraction: create proposal with all media variants; bulk delete
  protected by confirmation; proposal update/delete after username alias change; frontend
  refresh contract for AI-approved posts
- Risk: high
- Recommended module: `routers/proposals.py`
- Extraction notes: extract late. This surface is central and intertwined with uploads,
  comments, votes, collabs, mentions, and AI action publication.

### Comments / Comment Votes / Mentions

- Paths:
  - `GET /comments`
  - `POST /comments`
  - `PATCH /comments/{comment_id}`
  - `DELETE /comments/{comment_id}`
  - `POST /comments/{comment_id}/votes`
  - `DELETE /comments/{comment_id}/votes`
  - connector read facade: `GET /connector/proposals/{proposal_id}/comments`
- Current helper dependencies: `_ensure_comments_read_indexes`,
  `_ensure_comment_thread_columns`, `_ensure_comment_votes_table`,
  `_comment_payload`, `_comment_public_context`, `_comment_vote_summary`,
  `_require_token_identity_match`, `_optional_token_identity_match`,
  mention parsing/notification helpers, `_safe_user_key`, username alias helpers
- Models/tables: `Comment`, `Proposal`, `Harmonizer`, `Notification`,
  `comment_votes`, possible raw SQL fallback tables
- Auth requirements: public reads; bearer token required for create/edit/delete and vote
  writes; delete must remain author-bound or authorized by preserved rules
- Frontend surfaces: comments list, reply rows, comment action row, AI comment approval
  refresh, notification mentions
- Existing tests: `test_comment_auth_routes.py`, `test_comment_mention_notifications.py`,
  `test_comments_pagination.py`, `test_delete_with_mentions.py`,
  `test_connector_action_inbox_cancel.py`
- Missing tests before extraction: reply-to-reply AI comment attachment contract;
  comment delete after username alias change; comment action refresh without full page
  reload
- Risk: high
- Recommended module: `routers/comments.py`
- Extraction notes: keep comments near proposal serialization until embedded comment
  payloads and AI-approved comments have stronger regression coverage.

### Votes / System Votes

- Paths:
  - imported votes router: `POST /votes`, `DELETE /votes`, `GET /votes`
  - `GET /system-vote`
  - `GET /system-vote/config`
  - `POST /system-vote`
  - `DELETE /system-vote`
- Current helper dependencies: `votes_router.py` already contains direct vote helpers;
  system vote helpers include `_ensure_system_votes_table`, `_species_for_username`,
  `_require_token_identity_match`, `_enforce_system_vote_deadline`, tally helpers
- Models/tables: `ProposalVote`, `Harmonizer`, `system_votes`
- Auth requirements: bearer token required for vote writes and system vote writes;
  public reads for tallies/config
- Frontend surfaces: post card support/oppose controls, system vote card, AI review
  approval result display
- Existing tests: `test_votes_router_auth.py`, `test_system_vote_auth_deadline.py`,
  `test_connector_vote_approval.py`, `test_public_federation_safety.py`
- Missing tests before extraction: username alias behavior in `votes_router.py`; AI
  delegate vote attribution after approve route moves; system vote delete admin posture
- Risk: medium-high
- Recommended module: `routers/system_votes.py` for system votes; leave
  `votes_router.py` as-is until alias parity is added
- Extraction notes: do not change vote math or species weighting in a route split PR.

### AI Delegates / AI Actors / AI Actions

- Paths:
  - `GET /ai/delegates`
  - `POST /ai/delegates/persona-draft`
  - `POST /ai/delegates`
  - `PATCH /ai/delegates/{delegate_id}`
  - `DELETE /ai/delegates/{delegate_id}`
  - `GET /ai-actors/{username}`
  - `GET /proposals/{proposal_id}/system-ai-review`
  - `GET /proposals/{proposal_id}/ai-review-ledger`
  - `GET /connector/actions`
  - `POST /connector/actions/{action_id}/cancel`
  - `POST /connector/actions/draft-vote`
  - `POST /connector/actions/draft-ai-review`
  - `POST /connector/actions/draft-ai-delegate-review`
  - `POST /connector/actions/draft-ai-delegate-comment`
  - `POST /connector/actions/draft-ai-delegate-post`
  - `POST /connector/actions/{action_id}/approve-vote`
  - `POST /connector/actions/{action_id}/approve-ai-review`
  - `POST /connector/actions/{action_id}/approve-ai-comment`
  - `POST /connector/actions/{action_id}/approve-ai-post`
  - `POST /connector/actions/draft-comment`
  - `POST /connector/actions/draft-proposal`
  - `POST /connector/actions/draft-collab-request`
- Current helper dependencies: AI generation helpers, `_ensure_ai_actors_table`,
  `_ai_delegate_payload`, `_ai_delegate_actor_metadata`, `_ai_delegate_action_metadata`,
  `_build_ai_actor_context`, `_ai_persona_hash`, `_generate_with_openai_or_fallback`,
  `_connector_*` helpers, proposal/comment/vote creation helpers, public connector
  serialization, custody/status guards
- Models/tables: `ai_actors`, `connector_action_proposals`, `Proposal`, `Comment`,
  `ProposalVote`, `Harmonizer`, `ProposalCollab`
- Auth requirements: custodian bearer token required for delegate creation/update and
  draft/approval actions; public reads for AI profiles and ledgers; normal delete route
  intentionally refuses
- Frontend surfaces: AI Genesis, AI profile, AI delegate modal, AI Actions inbox,
  proposal card Ask AI, comment AI, composer AI, AssistantOrb
- Existing tests: `test_ai_delegate_management.py`,
  `test_ai_actor_system_review.py`, `test_connector_action_draft_routes.py`,
  `test_connector_ai_review_actions.py`, `test_connector_vote_approval.py`,
  `test_connector_action_inbox_cancel.py`
- Missing tests before extraction: AI modal create-delegate mini-flow server contract;
  media context included in AI comment/review generation; approved AI post/comment
  immediate refresh contract; provider metadata secret non-exposure across all action
  payloads after route split
- Risk: high
- Recommended module: `routers/ai_actions.py` plus `routers/ai_delegates.py` after
  additional tests
- Extraction notes: split after messages/uploads/follows. Keep official AI-authored
  content server-generated and approval-required.

### Follows / Social Graph

- Paths:
  - `GET /social-users`
  - `GET /social-graph`
  - `GET /follows`
  - `GET /follows/status`
  - `POST /follows`
  - `DELETE /follows`
- Current helper dependencies: `_follow_counts`, `_read_follows_store`,
  `_write_follows_store`, `_ensure_follows_table`, `_social_avatar`,
  `_require_token_identity_match`, `_optional_token_identity_match`, username alias
  helpers, social graph proposal/comment aggregation
- Models/tables: `follows`, `Harmonizer`, `Proposal`, fallback `follows_store.json`
- Auth requirements: public social read lists; bearer token required for follow/unfollow
  writes
- Frontend surfaces: profile follow button/counts, social constellation/graph,
  messaging user picker
- Existing tests: `test_follow_auth_routes.py`
- Missing tests before extraction: social graph shape stability; fallback JSON store
  parity; username alias behavior for follow status after rename
- Risk: medium
- Recommended module: `routers/social_graph.py`
- Extraction notes: good after messages/uploads, but keep profile counts compatibility in
  mind.

### Uploads / Media

- Paths:
  - `POST /upload-image`
  - `POST /upload-file`
  - static mount: `/uploads`
- Current helper dependencies: upload size limit helpers, `_upload_matches`,
  `_save_upload`, `_uploads_url`, media extension/content-type allowlists,
  `UPLOADS_DIR`, FastAPI `UploadFile`
- Models/tables: none for direct upload endpoints; proposal create stores returned URLs
  later
- Auth requirements: upload endpoints currently rely on route-level behavior/rate
  limits; verify whether bearer auth should remain unchanged before any move
- Frontend surfaces: composer media upload, avatar/profile image upload, AI/media post
  flows
- Existing tests: `test_upload_size_limits.py`
- Missing tests before extraction: auth/no-auth posture snapshot; image/video/file
  content-type matrix; static `/uploads` cache/no-store expectations
- Risk: low-medium
- Recommended module: `routers/uploads.py`
- Extraction notes: recommended second extraction candidate because upload limits are
  already covered and the route surface is compact. Do not move static mount if that
  changes app startup behavior.

### Public Federation / Export Routes

- Paths:
  - `GET /.well-known/supernova`
  - `GET /.well-known/supernova.json`
  - `GET /.well-known/webfinger`
  - `GET /domain-verification/preview`
  - `GET /actors/{username}`
  - `GET /actors/{username}/outbox`
  - `GET /api/users/{username}/portable-profile`
  - `GET /u/{username}/export.json`
  - connector read facade: `GET /connector/supernova`,
    `GET /connector/supernova/spec`, `GET /connector/proposals`,
    `GET /connector/proposals/{proposal_id}`,
    `GET /connector/proposals/{proposal_id}/votes`,
    `GET /connector/profiles/{username}`
- Current helper dependencies: `_normalize_preview_domain`,
  `_normalize_preview_username`, `_profile_exists`, `_profile_identity_payload`,
  `_connector_*` public serialization helpers, `PUBLIC_BASE_URL`,
  `PUBLIC_FEDERATION_CACHE_HEADERS`, proposal/profile reads
- Models/tables: `Harmonizer`, `Proposal`, `ProposalVote`, `Comment`, profile metadata
- Auth requirements: public read-only; must not introduce writes or private data leaks
- Frontend surfaces: public profile/export links, connector consumers, federation
  discovery, docs
- Existing tests: `test_public_federation_safety.py`,
  `test_public_gpt_connector_facade.py`
- Missing tests before extraction: exact route path cache headers for each public export;
  connector read facade response key snapshots
- Risk: medium-high
- Recommended module: `routers/public_federation.py`
- Extraction notes: behavior is read-only but public/security-sensitive. Move after
  stronger cache/header snapshots.

### Core Gateway / Runtime Status

- Paths:
  - mounted SuperNova Core app under `/core` when available
  - `GET /universe/info`
  - `GET /universe`
  - `GET /network-analysis/`
  - `GET /supernova-menu`
- Current helper dependencies: SuperNova runtime loader/settings, `_build_network_payload`,
  `_build_supernova_menu_payload`, `_build_status_payload`, CORS/status helpers, proposal
  aggregation
- Models/tables: runtime settings, `Harmonizer`, `Proposal`, `ProposalVote`, `Comment`,
  optional SuperNova Core models
- Auth requirements: public reads
- Frontend surfaces: legacy dashboard/system views, status/menu widgets
- Existing tests: `test_status_routes_extraction.py`,
  `test_public_federation_safety.py` partially
- Missing tests before extraction: `/universe/info`, `/universe`, `/network-analysis/`,
  and `/supernova-menu` response-shape snapshots
- Risk: medium
- Recommended module: `routers/system_runtime.py`
- Extraction notes: do not touch `supernovacore.py` or the `/core` mount. Keep any
  entangled startup/runtime helpers in `app.py` until route snapshots exist.

### Misc / Debug / Dev-Only Routes

- Paths:
  - `GET /debug-supernova`
  - `GET /debug/search-test`
  - `GET /notifications`
  - `GET /users/{username}/karma`
- Current helper dependencies: production environment guard, SuperNova runtime payload,
  proposal search helpers, notification serialization, karma fields
- Models/tables: `Proposal`, `Notification`, `Harmonizer`
- Auth requirements: debug routes are hidden in explicit production environments;
  notification and karma reads currently follow existing route behavior
- Frontend surfaces: development diagnostics, notification UI, profile karma display
- Existing tests: `test_debug_supernova_hardening.py`
- Missing tests before extraction: notification route auth/privacy expectation; karma
  response-shape snapshot
- Risk: medium
- Recommended module: `routers/misc_readonly.py` or split debug into
  `routers/debug_routes.py`
- Extraction notes: move only after clarifying notification privacy posture.

## Recommended Next Extraction Order To Evaluate

1. `routers/uploads.py` - compact route set, upload limits already tested; keep static
   mount behavior unchanged.
2. `routers/social_graph.py` - follows/social graph is moderately bounded, but profile
   counts and fallback JSON parity need snapshots.
3. `routers/ai_delegates.py` / `routers/ai_actions.py` - important and test-covered,
   but high risk because it publishes AI-authored content after approval.
4. `routers/proposals.py`, `routers/comments.py`, and vote/system-vote routes last -
   central, intertwined, and easiest to regress.

## Extraction Checklist For Future PRs

- Move one route group per PR.
- Keep route paths, methods, status codes, response fields, auth rules, rate-limit bucket
  selection, and cache headers unchanged.
- Add a static test proving the route group moved to the intended module.
- Add or preserve response-shape tests for public routes and write-auth tests for
  protected routes.
- Run focused route tests plus `test_commons_rate_limits.py` and protected core zero-diff.
- Do not combine route movement with frontend, schema, AI behavior, or product changes.
