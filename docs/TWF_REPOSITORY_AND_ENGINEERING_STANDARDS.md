# TradingWorkFlow (TWF) — Repository and Engineering Standards

## Status
**Accepted TWF-0 engineering baseline, extended for configuration and UX planning on 2026-09-25**

## 1. Purpose
Define repository structure, coding standards, documentation discipline, testing gates, Git practices, and artifact conventions before implementation begins.

## 2. Repository Philosophy
TWF is a separate repository from TI, TM, and scanners.
Keep product integration through contracts/adapters rather than cross-repo source imports except explicitly versioned packages.

## 3. Proposed Repository Layout
```text
TradingWorkFlow/
├── README.md
├── docs/
├── apps/
│   ├── web/          # Next.js / React / TypeScript
│   └── api/          # FastAPI / Python
├── packages/
│   └── contracts/    # only if shared/generated contracts justify it
├── tests/
├── scripts/
├── deploy/
├── .github/
└── pyproject/package configs
```
Exact layout may be adjusted during TWF-1 scaffolding.

## 4. Backend Standards
- Python 3.12+
- type hints required for public code
- Ruff
- mypy
- pytest
- Pydantic/FastAPI validation
- no hidden global mutable state
- explicit dependency/configuration injection where useful

## 5. Frontend Standards
- TypeScript strict mode
- React functional components
- Next.js application conventions
- ESLint
- Prettier
- component/interaction tests
- Playwright E2E
- no business authority logic hidden solely in browser code

## 6. Domain Separation
Backend layers should conceptually separate:
```text
API / transport
Application / workflow
Domain contracts/state
Infrastructure / persistence/adapters
```
Avoid overengineering strict DDD where simple code is clearer, but keep dependencies pointing inward.

## 7. Configuration
Configuration should be explicit and environment-aware.
Separate:
- non-secret app config
- service endpoints
- user preferences
- secrets
- authority/risk configuration

Secrets never committed.

## 8. Documentation Structure
Initial authoritative docs:
- high-level discussion record
- product/system architecture
- detailed roadmap
- technology decision record
- master/component/deployment architecture
- UX architecture
- data architecture
- security/auth architecture
- service contract architecture
- repository/engineering standards
- TWF-0 acceptance/readiness

Later add target implementation/acceptance records.

## 9. Documentation Authority
Markdown is normative for repository architecture/status.
DOCX is a human-readable/visual companion.
If they diverge, Markdown governs unless explicitly stated otherwise.

## 10. Decision Records
Material architecture/technology changes should have explicit decision records.
Do not rewrite historical accepted decisions; supersede them with a new record.

## 11. Milestone Records
Each milestone/target should have:
- scope
- implementation record
- tests
- acceptance criteria
- closure/readiness result
- README/roadmap update

## 12. README Dashboard
README should maintain a hierarchical project tree showing:
- completed milestones
- current target
- blocked work
- next work
- enough sub-phase detail to preserve architectural memory

Do not collapse historical detail after completion.

## 13. Git Practices
Recommended:
- `main` remains stable
- bounded commits
- clear commit messages
- no generated secrets/artifacts committed accidentally
- tags for major accepted/frozen baselines
- working tree clean before major architecture/acceptance tasks

## 14. Branch Strategy
Initial small-team approach may use short-lived feature branches or direct main with disciplined bounded commits.
Before multi-contributor production, adopt PR-based protected main.

## 15. Commit Message Style
Suggested prefixes:
- `docs:`
- `feat:`
- `fix:`
- `refactor:`
- `test:`
- `build:`
- `chore:`

Milestone commits may use explicit TWF target naming.

## 16. Backend Test Pyramid
- unit tests
- repository/persistence tests
- API tests
- service contract tests
- integration tests
- E2E miniature workflow tests

## 17. Frontend Tests
- component tests
- accessibility-focused checks
- interaction tests
- state/error/degraded-mode tests
- Playwright E2E

## 18. Contract Tests
Every satellite adapter must have a contract suite.
Real and synthetic adapters should satisfy the same logical semantics where applicable.

## 19. CI Minimum Gates
Before merge/release:
Backend:
- compile/package
- Ruff
- mypy
- pytest

Frontend:
- typecheck
- ESLint
- tests
- production build

Repository:
- docs/link checks
- migration checks
- `git diff --check` equivalent

## 20. Security Gates
At minimum:
- dependency scan
- secret scan
- authz tests
- no plaintext credentials
- safe logging review

## 21. Database Migration Standards
- every schema change through Alembic
- migration tests
- production migration notes for destructive changes
- no manual schema drift

## 22. API Evolution
- version contracts explicitly
- breaking changes require compatibility plan
- generated clients refreshed deterministically
- do not rely on undocumented response fields

## 23. Logging
Use structured logs.
Include:
- request ID
- workflow ID
- service
- operation
- duration
- status

Redact secrets and sensitive data.

## 24. Error Handling
Use typed/domain errors internally and stable API errors externally.
Do not leak raw stack traces in production responses.

## 25. Dependency Discipline
Avoid unnecessary frameworks.
Add dependencies only with clear ownership/use case.
Pin/version according to ecosystem best practice and security needs.

## 26. Code Review Checklist
Review:
- ownership boundaries
- authority leakage
- user scoping
- error/degraded state
- idempotency
- provenance/correlation
- tests
- docs
- migration impact
- security

## 27. Codex / ChatGPT Workflow
ChatGPT web:
- architecture
- planning
- document creation
- review
- acceptance reasoning

Codex:
- bounded implementation
- tests
- mechanical repo updates

Prefer prompts with explicit scope/non-goals to conserve quota and prevent drift.

## 28. Artifact Exchange
During early development, ZIP exchange of changed files is acceptable.
Always preserve paths relative to repository root and include a changed-file inventory.

## 29. Definition of Done for a Target
A target is not done merely because code compiles.
Require:
- implementation complete
- tests pass
- docs updated
- acceptance criteria met
- no known blocker hidden
- Git save/freeze decision explicit

## 30. Engineering Invariants
1. Architecture before major coding.
2. Historical decisions remain auditable.
3. Contracts before coupling.
4. Tests accompany behavior.
5. Database migrations are explicit.
6. Authority/security logic is server-side and governed.
7. README/roadmap remain current.
8. No milestone closure without acceptance evidence.

## 31. Configuration and UX Delivery Rules

The [configuration architecture v0.6](TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md) is the sole normative configuration design. The [reconciliation review](TWF_CONFIGURATION_SETUP_ARCHITECTURE_REVIEW.md) records decisions/findings; the [UX Bucket Roadmap](TWF_UX_BUCKET_ROADMAP.md) tracks UX maturity, without duplicating configuration rules or replacing functional milestones. Acceptance records describe their historical review; current README/index status must distinguish implemented, accepted, planned and unverified behavior.

Synthetic Scanner/TI/TM/LLM adapters are an explicit standard: deterministic fixtures behind the same versioned logical contracts, visible synthetic provenance, no live credentials/network effects, and shared success/failure/stale/denial/compatibility tests. Add cross-user/tenant and realm isolation, stale revision, failed apply/rollback, secret redaction and entitlement-change tests when the relevant functionality ships. Test meaning and authority boundaries, not merely counts.

Typed setting schemas, descriptor changes, configuration migrations and API revisions require compatibility notes and regression cases. Do not silently reinterpret saved profiles when upgrading providers. Concurrent editing uses expected revisions from the first mutable records. Runtime scope remains bounded by each milestone's prompt.

DOCX references may lag the normative Markdown if their version/status is explicitly recorded in the index. This task retains historical companions, including supplied configuration v0.5; they must not be presented as the v0.6 authority. Regeneration should use the normative source and rendered-page QA when supported tooling is available.
