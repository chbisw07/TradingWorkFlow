# TradingWorkFlow (TWF) Documentation

This repository contains the architecture, planning, integration, engineering, and acceptance documentation for **TradingWorkFlow (TWF)**.

TWF is the trader-facing web application that composes scanner, TradingIntelligence (TI), TradeMonitor (TM), LLMs, brokers, and other satellite services into one coherent workflow.

---

## Start Here

For a first reading, follow this order:

1. [High-Level Discussion Record](docs/TWF_HIGH_LEVEL_DISCUSSION_RECORD.md)
2. [Product Vision and System Architecture](docs/TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md)
3. [Documentation Index](docs/TWF_DOCUMENTATION_INDEX.md)
4. [Detailed Roadmap](docs/TWF_DETAILED_ROADMAP.md)
5. [Technology Decision Record](docs/TWF_TECHNOLOGY_DECISION_RECORD.md)

Then review the specialist architecture documents as needed.

---

## Architecture Overview

### Product / System Architecture

- `docs/TWF_MASTER_PRODUCT_ARCHITECTURE.docx`
- `docs/TWF_COMPONENT_ARCHITECTURE.docx`
- [TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md](docs/TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md)

### UX

- [TWF_UX_ARCHITECTURE.md](docs/TWF_UX_ARCHITECTURE.md)
- `docs/TWF_UX_ARCHITECTURE.docx`

### Data

- [TWF_DATA_ARCHITECTURE.md](docs/TWF_DATA_ARCHITECTURE.md)
- `docs/TWF_DATA_ARCHITECTURE.docx`

### Security / Authentication

- [TWF_SECURITY_AUTH_ARCHITECTURE.md](docs/TWF_SECURITY_AUTH_ARCHITECTURE.md)
- `docs/TWF_SECURITY_AUTH_ARCHITECTURE.docx`

### Deployment

- [TWF_DEPLOYMENT_ARCHITECTURE.md](docs/TWF_DEPLOYMENT_ARCHITECTURE.md)
- `docs/TWF_DEPLOYMENT_ARCHITECTURE.docx`

### Service / Integration

- [TWF_SERVICE_CONTRACT_ARCHITECTURE.md](docs/TWF_SERVICE_CONTRACT_ARCHITECTURE.md)
- `docs/TWF_SERVICE_CONTRACT_ARCHITECTURE.docx`
- [TWF_SERVICE_INTEGRATION_ARCHITECTURE.md](docs/TWF_SERVICE_INTEGRATION_ARCHITECTURE.md)
- [TWF_TI_INTEGRATION_CONTRACT.md](docs/TWF_TI_INTEGRATION_CONTRACT.md)
- [TWF_TM_INTEGRATION_CONTRACT.md](docs/TWF_TM_INTEGRATION_CONTRACT.md)

---

## Planning / Engineering

- [TWF_DETAILED_ROADMAP.md](docs/TWF_DETAILED_ROADMAP.md)
- [TWF_TECHNOLOGY_DECISION_RECORD.md](docs/TWF_TECHNOLOGY_DECISION_RECORD.md)
- [TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.md](docs/TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.md)
- `docs/TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.docx`

---

## Acceptance / Readiness

- [TWF_TWF0_ARCHITECTURE_ACCEPTANCE_AND_CODING_READINESS.md](docs/TWF_TWF0_ARCHITECTURE_ACCEPTANCE_AND_CODING_READINESS.md)
- `docs/TWF_TWF0_ARCHITECTURE_ACCEPTANCE_AND_CODING_READINESS.docx`

---

## Documentation Roles

The documentation set follows this rule:

```text
Markdown
    = authoritative repository-friendly architecture / planning record

DOCX
    = polished human-readable / diagram-oriented companion
```

Where both exist, the Markdown file should be treated as the normative source unless a later acceptance/decision record explicitly states otherwise.

---

## Current Project Phase

TWF is currently in the **TWF-0 architecture and pre-coding foundation phase**.

Coding should begin only after the TWF-0 acceptance/readiness review concludes that architecture is sufficiently complete.

Expected gate outcomes:

```text
GO_TWF1
HOLD_TWF0
ARCHITECTURAL_REWORK_REQUIRED
```

---

## Documentation Maintenance Rule

Whenever a milestone or target changes state:

1. update the relevant architecture/implementation record;
2. update the detailed roadmap if sequencing changes;
3. update the documentation index if files/authority change;
4. preserve earlier accepted/historical records rather than rewriting them;
5. keep current status distinguishable from historical status.

---

## Notes

The documentation set is expected to grow as TWF moves through implementation.

Future document families may include:

- milestone/target implementation records;
- acceptance reports;
- API/service contract versions;
- UX component specifications;
- data-model records;
- security decision records;
- deployment runbooks;
- production hardening records.
