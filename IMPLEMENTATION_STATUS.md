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
- [x] Next.js + Tailwind + @xyflow/react: dashboard, new analysis, evidence graph, diff viewer, tests, verifications, reports
- [x] Build + typecheck pass

## Phase 6b — Frontend Pages
- [x] Dashboard page with real data from API
- [x] Repositories list + new repository form
- [x] New analysis wizard (select repo, refs, options)
- [x] Analysis detail page with status, stage, summary
- [x] Evidence graph using @xyflow/react
- [x] Changed code viewer with diff highlighting
- [x] Test & coverage explorer
- [x] Verification details panel
- [x] Report download (JSON + Markdown)

## Phase 7 — Tests & docs
- [x] Unit + security tests pass (35 + 19 = 54 tests)
- [x] Docker-gated integration tests + E2E regression fixture (real reproduction) - 16 tests pass
- [x] README, deployment docs, final handoff
- [x] Genuine screenshots captured and embedded

## Completed Work Summary

### Fixes Applied
- Fixed frontend API proxy configuration (next.config.ts) to point to backend on port 8010
- Fixed pydantic-settings env_prefix (BS_) and env_file loading order
- Fixed git_service.ls_remote for local repositories (using git for-each-ref)
- Fixed job queue claim_next_job UUID handling for PostgreSQL RETURNING clause
- Restarted backend with correct environment variables

### Verified Functionality
- Backend API health endpoint: OK
- Repository creation (local path): OK
- Refs listing for local repos: OK
- Analysis creation and execution: OK
- Diff parsing and AST scope mapping: OK
- Baseline and modified test execution in Docker: OK
- Per-test coverage attribution: OK
- Hypothesis boundary + property verification: OK
- Evidence classification (PROVEN_FAILURE detected): OK
- Evidence graph generation: OK
- Frontend dashboard, repositories, new analysis, analysis detail pages: OK
- Frontend production build and typecheck: OK
- 70 backend tests passing
- 7 genuine screenshots captured

### Known Limitations
- Python-only analysis (no JS/TS/Go/Rust support)
- Single-worker job processing (horizontal scaling not implemented)
- Private Git repo authentication not supported
- No built-in auth UI (API key or external IdP required for production)
- Hypothesis strategies limited to int/float/bool/text/list inference
- Property language restricted to Python check(kwargs, outcome) functions

(End of file - total 85 lines)