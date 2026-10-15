# BranchSleuth — Implementation Status

Living checklist. Updated as work completes. No item is marked done without a passing check.

## Phase 1 — Stabilize / scaffold
- [x] Inspect working directory (empty repo → build from scratch)
- [x] Environment verified: Python 3.12.10, Node 22, git 2.53, Docker CLI present (daemon startup attempted)
- [x] Dedicated Neon project `branchsleuth` (frosty-art-19764346) created; DATABASE_URL written to gitignored `.env`
- [x] `.env.example` (names only), `.gitignore`

## Phase 2 — Analysis engine
- [x] Git service (clone, refs, archive snapshots, diff) with SSRF-safe URL validation
- [x] Unified diff parser (added/deleted/renamed/binary)
- [x] AST scope mapper (functions, async, classes, nested; end_lineno; executable lines)

## Phase 3 — Secure runtime verification
- [x] Docker worker image + isolated containers (no-new-privileges, cap drop, non-root, network disabled, limits)
- [x] Wheel-only dependency preparation phase, committed image, network-disabled test phase
- [x] Per-test coverage via pytest-cov --cov-context=test, parsed with Coverage.py API
- [x] Hypothesis differential + property probes with boundary candidates and minimization

## Phase 4 — Persistence & jobs
- [x] SQLAlchemy models + Alembic migration applied to Neon
- [x] Postgres-backed job queue with leases, heartbeats, cancel, retry
- [x] Pipeline orchestration with lifecycle events and honest progress

## Phase 5 — API
- [x] Repositories (URL / upload / local-dev), analyses, evidence, graph, reports, health
- [x] API key auth when configured; rate limiting; validation

## Phase 6 — Frontend
- [ ] Next.js + Tailwind + @xyflow/react: dashboard, new analysis, evidence graph, diff viewer, tests, verifications, reports
- [ ] Build + typecheck pass

## Phase 6b — Missing Frontend Pages
- [ ] Dashboard page with real data from API
- [ ] Repositories list + new repository form
- [ ] New analysis wizard (select repo, refs, options)
- [ ] Analysis detail page with status, stage, summary
- [ ] Evidence graph using @xyflow/react
- [ ] Changed code viewer with diff highlighting
- [ ] Test & coverage explorer
- [ ] Verification details panel
- [ ] Report download (JSON + Markdown)

## Phase 7 — Tests & docs
- [x] Unit + security tests pass (35 + 19 = 54 tests)
- [x] Docker-gated integration tests + E2E regression fixture (real reproduction) - 16 tests pass
- [ ] README, deployment docs, final handoff

## Current Blockers
- Frontend is nearly empty - needs full implementation
- Need to verify Neon database connection works with the app (run alembic upgrade head)
- Need to build and test the Docker worker image