# TradingWorkFlow (TWF) — TWF-0 Architecture Acceptance and Coding Readiness Gate

## Status
**Formal pre-coding review template — NOT YET ACCEPTED**

## 1. Purpose
Provide an explicit gate between TWF architecture/planning and implementation.

Coding should begin only when the foundational architecture is coherent enough that TWF-1 scaffolding will not immediately require major redesign.

## 2. TWF-0 Required Architecture Set
The following should exist and be reviewed:

### Product / System
- TWF_HIGH_LEVEL_DISCUSSION_RECORD.md
- TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md
- TWF_MASTER_PRODUCT_ARCHITECTURE.docx companion
- TWF_COMPONENT_ARCHITECTURE.docx companion

### Planning / Technology
- TWF_DETAILED_ROADMAP.md
- TWF_TECHNOLOGY_DECISION_RECORD.md
- TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.md

### Integration
- TWF_SERVICE_INTEGRATION_ARCHITECTURE.md
- TWF_SERVICE_CONTRACT_ARCHITECTURE.md
- TWF_TI_INTEGRATION_CONTRACT.md
- TWF_TM_INTEGRATION_CONTRACT.md

### UX / Data / Security / Deployment
- TWF_UX_ARCHITECTURE.md
- TWF_DATA_ARCHITECTURE.md
- TWF_SECURITY_AUTH_ARCHITECTURE.md
- TWF_DEPLOYMENT_ARCHITECTURE.md

## 3. Gate A — Product Clarity
Must be YES:
- product purpose clear
- miniature-system boundary clear
- goals/non-goals clear
- trader journey defined
- TWF vs TI/TM/scanner responsibility clear

## 4. Gate B — Component Architecture
Must be YES:
- frontend/backend boundary clear
- service boundaries clear
- local/remote adapter pattern defined
- persistence ownership clear
- realtime responsibilities clear
- LLM role clear

## 5. Gate C — Service Integration
Must be YES:
- TI consumption model defined
- TM consumption model defined provisionally
- scanner model defined
- common version/error/correlation rules defined
- browser-to-TWF-to-service path defined

TM real adapter coding may remain blocked until TM public-surface reconciliation is complete; that should not block TWF synthetic miniature coding.

## 6. Gate D — Data Architecture
Must be YES:
- SQLite → PostgreSQL path defined
- DB abstraction/repository strategy defined
- user/workspace ownership defined
- external authority boundaries defined
- migration policy defined
- audit/correlation strategy defined

## 7. Gate E — Security
Must be YES:
- authentication vs trading authority distinction clear
- session/security direction defined
- secrets boundary defined
- service-auth direction defined
- LLM output treated as untrusted
- multi-user isolation principle defined

Exact auth vendor may remain TBD for TWF-1 if the architecture supports replacement.

## 8. Gate F — UX
Must be YES:
- application shell defined
- primary workflow defined
- degraded/stale states defined
- console pattern defined
- responsive priorities defined
- critical authority states visually distinct

## 9. Gate G — Deployment
Must be YES:
- local development topology defined
- integrated topology defined
- production-cloud topology defined
- Docker-first policy defined
- PostgreSQL production direction defined
- scale path avoids premature Kubernetes

## 10. Gate H — Engineering Process
Must be YES:
- repo structure proposed
- testing strategy defined
- CI gates defined
- docs authority defined
- milestone/target process defined
- Git/freeze discipline defined

## 11. Allowed TBDs at Coding Start
The following may remain open if clearly isolated:
- exact UI component library
- exact chart library
- exact auth provider
- exact background job framework
- Redis adoption timing
- cloud provider
- billing provider
- final TM real adapter details while TM repo is unsettled

These TBDs must not invalidate TWF-1 foundation contracts.

## 12. Disallowed Unknowns at Coding Start
Do NOT start if unclear:
- who owns trading authority
- who owns broker truth
- whether browser talks directly to broker
- how user ownership works
- whether SQLite-specific logic may leak into domain
- whether satellite services are embedded or contract-driven
- whether TWF is single-user-only by design
- whether LLM provider is hard-wired

## 13. TWF-1 Coding Authorization Scope
Once accepted, TWF-1 may implement only the application foundation:
```text
web shell
API shell
database foundation
user/login foundation
settings foundation
service registry/client foundation
synthetic adapters
```
Do not jump directly to live broker execution.

## 14. TWF-1 Minimum Completion Definition
A user should be able to:
1. start TWF;
2. log in;
3. enter a workspace;
4. persist basic settings/workspace data;
5. see configured services and health;
6. interact with synthetic service adapters;
7. navigate the application shell.

## 15. Architecture Acceptance Status Template
```text
TWF0_PRODUCT_VISION_ACCEPTED = NO
TWF0_MASTER_ARCHITECTURE_ACCEPTED = NO
TWF0_COMPONENT_ARCHITECTURE_ACCEPTED = NO
TWF0_TECH_STACK_ACCEPTED = NO
TWF0_UX_ARCHITECTURE_ACCEPTED = NO
TWF0_DATA_ARCHITECTURE_ACCEPTED = NO
TWF0_SECURITY_ARCHITECTURE_ACCEPTED = NO
TWF0_SERVICE_CONTRACT_ARCHITECTURE_ACCEPTED = NO
TWF0_DEPLOYMENT_ARCHITECTURE_ACCEPTED = NO
TWF0_ENGINEERING_STANDARDS_ACCEPTED = NO
TWF0_ROADMAP_ACCEPTED = NO
READY_TO_IMPLEMENT_TWF1 = NO
```

## 16. Final Review Outcome
Use exactly one:
```text
GO_TWF1
HOLD_TWF0
ARCHITECTURAL_REWORK_REQUIRED
```

## 17. Current Preliminary Assessment
Based on current documentation work, TWF-0 is approaching coding readiness but should undergo one explicit architecture review before `READY_TO_IMPLEMENT_TWF1` becomes YES.

Do not treat creation of this document itself as acceptance.
