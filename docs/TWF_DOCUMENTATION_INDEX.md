# TradingWorkFlow (TWF) — Documentation Index

## Status

**Authoritative documentation map for TWF**

Current architecture gate:

```text
TWF-0 ACCEPTED / FROZEN
GO_TWF1
Configuration v0.6 reconciled / GO_TWF1_5
TWF-1.5 IMPLEMENTED / pending independent review
```

---

## 1. Documentation Authority Model

```text
Vision / Intent
Architecture
Planning / Engineering
Acceptance / Closure
Implementation Records
```

Where both Markdown and DOCX versions exist:

```text
Markdown = normative repository source
DOCX     = polished visual/reference companion
```

Historical/accepted records remain historical unless an explicit later record supersedes them.
The [configuration review](TWF_CONFIGURATION_SETUP_ARCHITECTURE_REVIEW.md) records the
2026-09-25 clarification without reopening TWF-0. Current normative configuration is
Markdown v0.6; its supplied DOCX is retained unchanged as a **v0.5 reference snapshot**.
Other DOCX companions, including master/component diagrams, retain their TWF-0 content.
Read the updated normative Markdown for current realm/configuration/UX decisions.
Companions are not synchronized v0.6 deliverables.

---

## 2. Core Entry Documents

| Document | Role | Authority |
|---|---|---|
| [`README.md`](../README.md) | Human entry point and current-status dashboard | Navigation / status |
| `TWF_DOCUMENTATION_INDEX.md` | Canonical documentation map | Authoritative map |
| `TWF_HIGH_LEVEL_DISCUSSION_RECORD.md` | Initial product discussion and intent | Historical / contextual |
| `TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md` | Product purpose and high-level system design | Normative architecture |
| `TWF_DETAILED_ROADMAP.md` | Milestones, targets, sequencing | Normative planning |
| `TWF_TECHNOLOGY_DECISION_RECORD.md` | Technology baseline and open decisions | Decision record |
| `TWF_TWF0_ARCHITECTURE_ACCEPTANCE_REVIEW.md` | Formal TWF-0 architecture acceptance | Acceptance authority |
| `TWF_LOCAL_DEVELOPMENT_SETUP_LINUX.md` | Ubuntu/Linux local developer setup, validation, startup, shutdown, and troubleshooting | Developer operations / setup guide |

---

## 3. Architecture Documents

### Master / Component
- `TWF_MASTER_PRODUCT_ARCHITECTURE.docx` — visual/reference
- `TWF_COMPONENT_ARCHITECTURE.docx` — visual/reference
- `TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md` — normative

### UX
- [Responsive Trading Application Architecture](TWF_RESPONSIVE_TRADING_APPLICATION_ARCHITECTURE.md) — normative responsive application clarification
- `TWF_UX_ARCHITECTURE.md` — normative
- [UX Bucket Roadmap](TWF_UX_BUCKET_ROADMAP.md) — normative cross-cutting maturity plan v0.1; UX-B1 partial, UX-B2/B3 planned
- `TWF_UX_ARCHITECTURE.docx` — reference

### Configuration / Setup
- [Configuration, Setup, Capability, Entitlement and Pluggability Architecture](TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md) — sole normative configuration source, reconciled v0.6
- `TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.docx` — supplied v0.5 reference, unchanged
- [Configuration Architecture Review](TWF_CONFIGURATION_SETUP_ARCHITECTURE_REVIEW.md) — corpus, decisions, gaps, changes and TWF-1.5 readiness; does not duplicate normative design

### Data
- `TWF_DATA_ARCHITECTURE.md` — normative
- `TWF_DATA_ARCHITECTURE.docx` — reference

### Security / Authentication
- `TWF_SECURITY_AUTH_ARCHITECTURE.md` — normative
- `TWF_SECURITY_AUTH_ARCHITECTURE.docx` — reference

### Deployment
- `TWF_DEPLOYMENT_ARCHITECTURE.md` — normative
- `TWF_DEPLOYMENT_ARCHITECTURE.docx` — reference

---

## 4. Service / Integration Documents

| Document | Authority |
|---|---|
| `TWF_SERVICE_CONTRACT_ARCHITECTURE.md` | Normative |
| `TWF_SERVICE_CONTRACT_ARCHITECTURE.docx` | Reference |
| `TWF_SERVICE_INTEGRATION_ARCHITECTURE.md` | Normative |
| `TWF_TI_INTEGRATION_CONTRACT.md` | Architecture-stage normative |
| `TWF_TM_INTEGRATION_CONTRACT.md` | Provisional until clean TM public-surface reconciliation |

---

## 5. Planning / Engineering

- `TWF_DETAILED_ROADMAP.md`
- `TWF_TECHNOLOGY_DECISION_RECORD.md`
- `TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.md`
- `TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.docx`

### Developer operations

- [Ubuntu/Linux Local Development Setup](TWF_LOCAL_DEVELOPMENT_SETUP_LINUX.md)
  — setup, validation, native and Docker workflows, shutdown, and troubleshooting.

---

## 6. Acceptance / Readiness

### Gate template
`TWF_TWF0_ARCHITECTURE_ACCEPTANCE_AND_CODING_READINESS.md`

`TWF_TWF0_ARCHITECTURE_ACCEPTANCE_AND_CODING_READINESS.docx` — historical reference companion

Purpose:
- defines the criteria;
- remains the gate specification.

### Accepted review
`TWF_TWF0_ARCHITECTURE_ACCEPTANCE_REVIEW.md`

Purpose:
- applies the gate;
- records `GO_TWF1`;
- authorizes bounded TWF-1 coding.

Authority:

```text
TWF_TWF0_ARCHITECTURE_ACCEPTANCE_REVIEW.md
    supersedes the template's NOT YET ACCEPTED status
    without rewriting the historical template.
```

---

### Configuration reconciliation checkpoint

[Configuration Architecture Review](TWF_CONFIGURATION_SETUP_ARCHITECTURE_REVIEW.md)
records `GO_TWF1_5` under configuration v0.6. This accepts the bounded next-target
architecture; it does not claim SaaS administration, billing or UX bucket completion.

## 7. Current Phase

```text
TWF-0 — ACCEPTED / FROZEN (twf-0-architecture-baseline)
       ↓
TWF-1 — APPLICATION FOUNDATION / IN_PROGRESS
├── TWF-1.0 — REPOSITORY SCAFFOLD / ACCEPTED
├── TWF-1.1 — FRONTEND SHELL / ACCEPTED (twf-1.1-frontend-shell)
├── TWF-1.1A — THEME SWITCHING / ACCEPTED (twf-1.1a-theme-switching)
├── TWF-1.2 — BACKEND SHELL / ACCEPTED (twf-1.2-backend-shell)
├── TWF-1.3 — DATABASE FOUNDATION / ACCEPTED
├── TWF-1.4 — USER / LOGIN FOUNDATION / ACCEPTED AFTER BOUNDED FIXES (ba9bb8b)
├── Configuration reconciliation — REVIEWED v0.6 / GO_TWF1_5
├── TWF-1.5 — SETTINGS FOUNDATION / IMPLEMENTED / pending independent review
└── TWF-1.6 — SERVICE CLIENT FOUNDATION / PENDING

UX workstream (parallel to functional milestones)
├── UX-B1 — FOUNDATIONAL COMPLETE UX / PARTIAL
├── UX-B2 — OPERATIONALLY USEFUL TRADING UX / PLANNED
└── UX-B3 — ARCHITECTURE-COMPLETE UX / PLANNED
```

Implementation records:

- [TWF-1.0 Repository / Project Scaffold](TWF_TWF1_0_REPOSITORY_PROJECT_SCAFFOLD.md)
  — authoritative bounded implementation record, developer commands, inventory,
  and validation evidence for the accepted historical scaffold.
- [TWF-1.1 Frontend Shell](TWF_TWF1_1_FRONTEND_SHELL.md)
  — historical implementation evidence for the accepted shell baseline.
- [TWF-1.1A Theme Switching Foundation](TWF_TWF1_1A_THEME_SWITCHING_FOUNDATION.md)
  — historical implementation evidence for the accepted theme foundation.
- [TWF-1.2 Backend Shell](TWF_TWF1_2_BACKEND_SHELL.md)
  — historical implementation evidence for the accepted backend shell.
- [TWF-1.3 Database Foundation](TWF_TWF1_3_DATABASE_FOUNDATION.md)
  — historical implementation evidence for the accepted database foundation.
- [TWF-1.4 User / Login Foundation](TWF_TWF1_4_USER_LOGIN_FOUNDATION.md)
  — historical identity, credential, session, login UI, CSRF and migration evidence.
  Its pending-re-review wording predates the accepted `ba9bb8b` commit; current status
  is recorded here and in README without rewriting that implementation history.
- [TWF-1.5 Settings Foundation](TWF_TWF1_5_SETTINGS_FOUNDATION.md)
  — implemented personal preferences, validated profiles, revision checks and Setup UI;
  pending independent review. Next functional target after acceptance/freeze: TWF-1.6.

---

## 8. TWF-1 Authorized Targets

```text
TWF-1.0 Repository / Project Scaffold
TWF-1.1 Frontend Shell
TWF-1.1A Theme Switching Foundation
TWF-1.2 Backend Shell
TWF-1.3 Database Foundation
TWF-1.4 User / Login Foundation
TWF-1.5 Settings Foundation
TWF-1.6 Service Client Foundation
```

Later milestones remain separately gated.

---

## 9. Recommended Reading Paths

### Product / Trader
```text
../README.md
→ TWF_HIGH_LEVEL_DISCUSSION_RECORD.md
→ TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md
→ TWF_UX_ARCHITECTURE.md
→ TWF_DETAILED_ROADMAP.md
```

### Architect
```text
TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md
→ master/component DOCX companions
→ TWF_SERVICE_CONTRACT_ARCHITECTURE.md
→ TWF_DATA_ARCHITECTURE.md
→ TWF_SECURITY_AUTH_ARCHITECTURE.md
→ TWF_DEPLOYMENT_ARCHITECTURE.md
→ TWF_TWF0_ARCHITECTURE_ACCEPTANCE_REVIEW.md
→ TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md
→ TWF_UX_BUCKET_ROADMAP.md
→ TWF_CONFIGURATION_SETUP_ARCHITECTURE_REVIEW.md
```

### Developer
```text
TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.md
→ TWF_LOCAL_DEVELOPMENT_SETUP_LINUX.md
→ TWF_TECHNOLOGY_DECISION_RECORD.md
→ TWF_SERVICE_INTEGRATION_ARCHITECTURE.md
→ TWF_DETAILED_ROADMAP.md
→ TWF_TWF0_ARCHITECTURE_ACCEPTANCE_REVIEW.md
```

---

## 10. Maintenance Rules

When new documents are added:

1. add them here;
2. state purpose and authority;
3. update root README when current status changes;
4. preserve prior acceptance/history;
5. avoid duplicate competing normative documents.
