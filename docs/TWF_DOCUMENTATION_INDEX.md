# TradingWorkFlow (TWF) — Documentation Index

## Status

**Authoritative documentation map for TWF**

Current architecture gate:

```text
TWF-0 ACCEPTED
GO_TWF1
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

---

## 3. Architecture Documents

### Master / Component
- `TWF_MASTER_PRODUCT_ARCHITECTURE.docx` — visual/reference
- `TWF_COMPONENT_ARCHITECTURE.docx` — visual/reference
- `TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md` — normative

### UX
- `TWF_UX_ARCHITECTURE.md` — normative
- `TWF_UX_ARCHITECTURE.docx` — reference

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

---

## 6. Acceptance / Readiness

### Gate template
`TWF_TWF0_ARCHITECTURE_ACCEPTANCE_AND_CODING_READINESS.md`

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

## 7. Current Phase

```text
TWF-0 — ACCEPTED / READY_TO_FREEZE
       ↓
TWF-1 — APPLICATION FOUNDATION / NEXT
```

Recommended repository action:

```text
commit acceptance/status updates
tag twf-0-architecture-baseline
begin TWF-1
```

---

## 8. TWF-1 Authorized Targets

```text
TWF-1.1 Frontend Shell
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
```

### Developer
```text
TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.md
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
