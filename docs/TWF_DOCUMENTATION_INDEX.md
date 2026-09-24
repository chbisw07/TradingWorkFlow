# TradingWorkFlow (TWF) — Documentation Index

## Status

**Authoritative documentation map for TWF**

This file identifies the purpose, authority, and relationship of the current TWF documentation corpus.

---

## 1. Documentation Authority Model

TWF documentation is organized into four broad classes:

```text
Vision / Intent
Architecture
Planning / Engineering
Acceptance / Closure
```

Where both Markdown and DOCX versions exist:

```text
Markdown = normative repository source
DOCX     = polished visual/reference companion
```

Historical/accepted records should remain immutable except for clearly marked corrections or superseding records.

---

## 2. Core Entry Documents

| Document | Role | Authority |
|---|---|---|
| [`README.md`](../README.md) | Human entry point and reading guide | Navigation |
| `TWF_DOCUMENTATION_INDEX.md` | Canonical documentation map | Authoritative map |
| `TWF_HIGH_LEVEL_DISCUSSION_RECORD.md` | Captures initial product discussion and intent | Historical / contextual |
| `TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md` | Product purpose, boundaries, high-level system design | Normative architecture |
| `TWF_DETAILED_ROADMAP.md` | Milestones, targets, sequencing | Normative planning |
| `TWF_TECHNOLOGY_DECISION_RECORD.md` | Proposed/accepted technology choices | Decision record |

---

## 3. Architecture Documents

### 3.1 Master / Component

| Document | Purpose | Authority |
|---|---|---|
| `TWF_MASTER_PRODUCT_ARCHITECTURE.docx` | Product-wide master block architecture | Visual/reference companion |
| `TWF_COMPONENT_ARCHITECTURE.docx` | Component-level system decomposition | Visual/reference companion |
| [TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md](TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md) | Normative high-level architecture | Normative |

### 3.2 UX

| Document | Purpose | Authority |
|---|---|---|
| [TWF_UX_ARCHITECTURE.md](TWF_UX_ARCHITECTURE.md) | Trader journeys, shell, panels, realtime UX, consoles | Normative |
| `TWF_UX_ARCHITECTURE.docx` | Visual UX architecture companion | Reference |

### 3.3 Data

| Document | Purpose | Authority |
|---|---|---|
| [TWF_DATA_ARCHITECTURE.md](TWF_DATA_ARCHITECTURE.md) | Persistence, ownership, SQLite→PostgreSQL portability | Normative |
| `TWF_DATA_ARCHITECTURE.docx` | Visual data architecture companion | Reference |

### 3.4 Security / Authentication

| Document | Purpose | Authority |
|---|---|---|
| [TWF_SECURITY_AUTH_ARCHITECTURE.md](TWF_SECURITY_AUTH_ARCHITECTURE.md) | Authentication, authorization, secrets, trust boundaries | Normative |
| `TWF_SECURITY_AUTH_ARCHITECTURE.docx` | Visual security architecture companion | Reference |

### 3.5 Deployment

| Document | Purpose | Authority |
|---|---|---|
| [TWF_DEPLOYMENT_ARCHITECTURE.md](TWF_DEPLOYMENT_ARCHITECTURE.md) | Development, integration and production deployment model | Normative |
| `TWF_DEPLOYMENT_ARCHITECTURE.docx` | Visual deployment companion | Reference |

---

## 4. Service / Integration Documents

| Document | Purpose | Authority |
|---|---|---|
| [TWF_SERVICE_CONTRACT_ARCHITECTURE.md](TWF_SERVICE_CONTRACT_ARCHITECTURE.md) | Common service contract principles | Normative |
| `TWF_SERVICE_CONTRACT_ARCHITECTURE.docx` | Visual service-contract companion | Reference |
| [TWF_SERVICE_INTEGRATION_ARCHITECTURE.md](TWF_SERVICE_INTEGRATION_ARCHITECTURE.md) | Local/remote adapter and service-integration model | Normative |
| [TWF_TI_INTEGRATION_CONTRACT.md](TWF_TI_INTEGRATION_CONTRACT.md) | TWF ↔ TI logical integration contract | Normative / architecture-stage |
| [TWF_TM_INTEGRATION_CONTRACT.md](TWF_TM_INTEGRATION_CONTRACT.md) | TWF ↔ TM integration contract | Provisional until TM public surface reconciliation |

Important:

`TWF_TM_INTEGRATION_CONTRACT.md` must not be treated as implementation-frozen until reconciled against a clean committed TM baseline.

---

## 5. Planning / Engineering Documents

| Document | Purpose | Authority |
|---|---|---|
| [TWF_DETAILED_ROADMAP.md](TWF_DETAILED_ROADMAP.md) | TWF-0…TWF-10 provisional milestone/target plan | Normative planning |
| [TWF_TECHNOLOGY_DECISION_RECORD.md](TWF_TECHNOLOGY_DECISION_RECORD.md) | Stack choices and still-open technology decisions | Decision record |
| [TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.md](TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.md) | Repository layout, quality gates, coding/documentation standards | Normative engineering |
| `TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.docx` | Human-readable engineering companion | Reference |

---

## 6. Acceptance / Readiness Documents

| Document | Purpose | Authority |
|---|---|---|
| [TWF_TWF0_ARCHITECTURE_ACCEPTANCE_AND_CODING_READINESS.md](TWF_TWF0_ARCHITECTURE_ACCEPTANCE_AND_CODING_READINESS.md) | Formal pre-coding architecture readiness gate | Acceptance authority |
| `TWF_TWF0_ARCHITECTURE_ACCEPTANCE_AND_CODING_READINESS.docx` | Visual/human-readable companion | Reference |

TWF-0 should eventually conclude exactly one:

```text
GO_TWF1
HOLD_TWF0
ARCHITECTURAL_REWORK_REQUIRED
```

---

## 7. Current Document Inventory

Current known files:

```text
README.md
docs/
├── TWF_DOCUMENTATION_INDEX.md
├── TWF_COMPONENT_ARCHITECTURE.docx
├── TWF_DATA_ARCHITECTURE.docx
├── TWF_DATA_ARCHITECTURE.md
├── TWF_DEPLOYMENT_ARCHITECTURE.docx
├── TWF_DEPLOYMENT_ARCHITECTURE.md
├── TWF_DETAILED_ROADMAP.md
├── TWF_HIGH_LEVEL_DISCUSSION_RECORD.md
├── TWF_MASTER_PRODUCT_ARCHITECTURE.docx
├── TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md
├── TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.docx
├── TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.md
├── TWF_SECURITY_AUTH_ARCHITECTURE.docx
├── TWF_SECURITY_AUTH_ARCHITECTURE.md
├── TWF_SERVICE_CONTRACT_ARCHITECTURE.docx
├── TWF_SERVICE_CONTRACT_ARCHITECTURE.md
├── TWF_SERVICE_INTEGRATION_ARCHITECTURE.md
├── TWF_TECHNOLOGY_DECISION_RECORD.md
├── TWF_TI_INTEGRATION_CONTRACT.md
├── TWF_TM_INTEGRATION_CONTRACT.md
├── TWF_TWF0_ARCHITECTURE_ACCEPTANCE_AND_CODING_READINESS.docx
├── TWF_TWF0_ARCHITECTURE_ACCEPTANCE_AND_CODING_READINESS.md
├── TWF_UX_ARCHITECTURE.docx
└── TWF_UX_ARCHITECTURE.md
```

---

## 8. Recommended Reading Paths

### Product Owner / Trader View

```text
../README.md
→ TWF_HIGH_LEVEL_DISCUSSION_RECORD.md
→ TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md
→ TWF_UX_ARCHITECTURE.md
→ TWF_DETAILED_ROADMAP.md
```

### Architect View

```text
TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md
→ TWF_MASTER_PRODUCT_ARCHITECTURE.docx
→ TWF_COMPONENT_ARCHITECTURE.docx
→ TWF_SERVICE_CONTRACT_ARCHITECTURE.md
→ TWF_DATA_ARCHITECTURE.md
→ TWF_SECURITY_AUTH_ARCHITECTURE.md
→ TWF_DEPLOYMENT_ARCHITECTURE.md
```

### Developer View

```text
TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.md
→ TWF_TECHNOLOGY_DECISION_RECORD.md
→ TWF_SERVICE_INTEGRATION_ARCHITECTURE.md
→ TWF_TI_INTEGRATION_CONTRACT.md
→ TWF_TM_INTEGRATION_CONTRACT.md
→ TWF_DETAILED_ROADMAP.md
```

### Pre-Coding Review

```text
All normative architecture docs
→ TWF_TWF0_ARCHITECTURE_ACCEPTANCE_AND_CODING_READINESS.md
```

---

## 9. Authority / Supersession Rules

1. Historical discussion records remain historical.
2. Architecture records define intended structure.
3. Decision records freeze technology/policy choices when explicitly accepted.
4. Roadmap defines current intended sequence.
5. Acceptance records determine whether a bounded milestone is allowed to advance.
6. Implementation records, when added later, document what was actually built.
7. Later accepted records may supersede earlier proposed designs, but earlier historical records should not be silently rewritten.

---

## 10. Documentation Maintenance

When new documents are added:

1. add them to this index;
2. assign purpose and authority;
3. add them to the root [`README.md`](../README.md) when useful to readers;
4. preserve naming consistency;
5. avoid duplicate competing architecture documents;
6. explicitly mark provisional vs accepted status.

---

## 11. Current Phase

Current phase:

```text
TWF-0 — Product / Architecture Foundation
```

Current intent:

```text
complete architecture review
→ run TWF-0 readiness gate
→ GO_TWF1 or HOLD
```

No implementation milestone should be treated as started merely because architecture documents exist.
