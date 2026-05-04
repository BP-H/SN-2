# Changelog

## Unreleased
- Tightened AI delegate action modal discoverability: mini Genesis remains available with zero delegates and a compact create-another affordance is visible when delegates already exist.
- Reduced AI action modal weight by moving model, generation, and hash metadata into collapsed details while keeping approve/cancel publication controls unchanged.
- Added alpha-stage commons-safe rate limits for auth, uploads, AI generation, writes, messages, and public reads. Limits are generous, species-neutral, environment-configurable circuit breakers for spam, brute force, upload abuse, and runaway automation; they are not monetization or participation throttles.
- Added friendly HTTP 429 JSON responses with `Retry-After` and `X-SuperNova-RateLimit-Bucket` headers.

## v5.1.0-prep
- Registered RFCs 101–106 with summaries.
- Added 3D viewer docs and render stub.
- Introduced quotes auto-post cron stub.
- Added federation outbox and CLI stub.
- Implemented seasonal quest toggle and milestone CLI.
- Created moderation helpers for profanity and consent.
- Added resonance music stub and summary route.
- Standardized Streamlit default port to **8888**.
- Added `?healthz=1` query parameter for UI health checks.
- Removed legacy monkey patch for `/healthz`.
- Added simulation event form with InfluenceGraph preview.
- Added moderation page with real-time flag updates.
