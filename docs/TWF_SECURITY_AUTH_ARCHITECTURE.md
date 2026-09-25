# TradingWorkFlow (TWF) — Security and Authentication Architecture

## Status
**TWF-0 accepted security baseline, with configuration realm clarification dated 2026-09-25**

## 1. Purpose
Define the security model for a cloud-hosted, multi-user trading workflow application integrating TI, TM, scanners, LLM providers, brokers, and future subscription services.

## 2. Security North Star
> A user-facing convenience or integration feature must never silently weaken identity, authority, broker security, or auditability.

## 3. Distinct Security Concepts
Keep separate:
```text
User Authentication
Application Authorization
Service Authentication
Trading Authority
Broker Authorization
Subscription Entitlement
```

These are different concerns.

## 4. Trust Zones
```text
Browser
  ↓
TWF Web / API
  ↓
TWF trusted application zone
  ├── Database
  ├── TI service
  ├── TM service
  ├── Scanner service
  ├── LLM provider
  └── Notification/Billing services

TM
  ↓
Broker boundary
```

Broker secrets should remain within the broker/TM trust boundary whenever possible.

## 5. User Authentication
Production must support secure user login.

Requirements:
- passwordless or password-based provider to be selected;
- MFA-capable future path;
- secure session management;
- logout/revocation;
- brute-force/rate-limit protections;
- email/account verification as needed.

TWF-1.4 implements local password authentication with server-owned revocable sessions. Production IdP/federation, MFA and recovery remain later decisions; see the [historical login implementation](TWF_TWF1_4_USER_LOGIN_FOUNDATION.md).

## 6. Session Strategy
Prefer secure server-managed session or short-lived token architecture appropriate to Next.js + FastAPI.

Requirements:
- HttpOnly cookies where applicable;
- Secure/SameSite flags in production;
- CSRF protection where needed;
- rotation/expiry;
- no sensitive tokens in localStorage by default.

## 7. Application Authorization
Every user-owned object must be authorization-checked:
- workspace;
- watchlist;
- candidate;
- settings;
- service configuration;
- workflow;
- history.

Do not rely on frontend hiding controls.

## 8. Roles
Use realm-qualified roles from [configuration architecture v0.6](TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md). APS starts with representative PLATFORM_OWNER, APS_ADMIN and DEVELOPER identities; operational roles are decomposed when needed. ACS starts with ACCOUNT_ADMIN and REGULAR_USER, each bound to an account. These are design commitments, not roles implemented by TWF-1.4. Generic USER/ADMIN must not imply cross-realm authority.

Trading authority should not simply equal an application role.

## 9. Trading Authority
Trading authority belongs to TM/policy/trader workflow, not ordinary TWF authorization.

Example:
```text
TWF user authenticated
    ≠
allowed to execute trade

TWF role = REGULAR_USER
    ≠
TM risk/authority approved
```

UI must show these states separately.

## 10. Broker Authorization
Prefer TWF never sees raw broker credentials.

Architecture:
```text
TWF
  ↓
TM
  ↓
Broker adapter / broker secret store
```

If TWF must initiate broker connection/setup later, secrets should flow through dedicated secure paths and secret management.

## 11. Service Authentication
Remote TI/TM/scanner services should authenticate TWF.

Potential future options:
- mTLS;
- signed service tokens;
- OAuth2 client credentials;
- cloud-native service identity.

Exact mechanism depends on deployment.

## 12. LLM Provider Security
Provider API keys:
- server-side only;
- never embedded in browser;
- secret-manager backed in production;
- scoped where provider permits;
- usage/audit visibility.

User-provided provider keys, if supported later, require separate encrypted-secret design.

## 13. Secret Management
Development:
- `.env` / local secret files excluded from Git.

Production:
- cloud secret manager / vault.

Never store:
- passwords;
- API keys;
- broker tokens;
- LLM keys
as plaintext ordinary settings records.

## 14. Transport Security
Production:
- HTTPS everywhere;
- secure WebSocket;
- TLS for service-to-service;
- HSTS where appropriate.

No production plaintext HTTP for sensitive paths.

## 15. CSRF / XSS / Injection
Controls:
- secure cookie/session design;
- CSRF protection when cookie auth is used;
- framework output escaping;
- content security policy;
- input validation;
- parameterized SQL/ORM;
- avoid rendering untrusted HTML from LLM/service output.

## 16. LLM Output Safety Boundary
Treat LLM output as untrusted content.

It may:
- contain malformed markup;
- hallucinate actions;
- include unsafe links/text.

LLM output must not directly execute privileged commands.

Any action must pass through typed workflow contracts and authority checks.

## 17. Command / Console Security
Web console command input, if later enabled:
- capability-scoped;
- authenticated;
- authorized;
- audited;
- never arbitrary shell by default;
- no command path may bypass TM authority.

Read-only console is the safe initial default.

## 18. Audit Requirements
Audit:
- login/logout;
- settings affecting service configuration;
- LLM/provider changes;
- broker connection changes;
- candidate → TM handoff;
- trader approval/rejection;
- authority-changing actions;
- adoption;
- execution requests;
- admin actions.

Audit records should include actor, time, workflow/correlation ID, and action result.

## 19. Multi-User Isolation
Every request must resolve authenticated user/account context.

Rules:
- repository queries scoped by owner/tenant;
- service results not cached across users without safe keying;
- realtime channels authorized per user/workspace;
- no IDOR-style direct access by guessable IDs.

## 20. Subscription Entitlements
The entitlement architecture is defined now; commercial plans and billing remain later scope. Versioned capability grants control what an account may use; roles control which actors may configure/use it.

Examples:
- number of scanners;
- advanced TI services;
- retention;
- concurrent workflows.

Subscription must never grant broker execution rights automatically.

## 21. API Security
- schema validation;
- request size limits;
- rate limits where appropriate;
- idempotency keys for sensitive commands;
- explicit error handling;
- no stack traces to users in production.

## 22. Realtime Security
WebSocket/SSE:
- authenticated connection;
- authorized topics;
- revalidation on reconnect;
- no cross-user broadcast leakage;
- bounded message size/rate;
- stale connection cleanup.

## 23. File / Export Security
If exports/uploads are added:
- type/size validation;
- no executable upload by default;
- user ownership;
- safe filenames;
- malware scanning if threat profile justifies later.

## 24. Logging Security
Do not log:
- passwords;
- bearer tokens;
- broker secrets;
- LLM API keys;
- full sensitive payloads unnecessarily.

Use structured redaction.

## 25. Threat Scenarios
At minimum consider:
- stolen session;
- cross-user object access;
- compromised browser;
- malicious LLM output;
- service impersonation;
- replayed trade approval;
- duplicate execution request;
- leaked broker token;
- stale risk approval;
- forged realtime event;
- privilege escalation;
- vulnerable dependency.

## 26. Security Development Lifecycle
For each milestone:
- threat review;
- dependency scan;
- authz tests;
- secret scan;
- secure-default review;
- audit coverage review.

Production hardening later adds penetration testing and operational monitoring.

## 27. Initial Authentication Recommendation
TWF-1.4 has selected the bounded local password/session implementation. Keep its authentication boundary replaceable; evaluate production identity options before the deployment that needs them.

Preferred architecture:
```text
Browser
  ↓
TWF authentication/session layer
  ↓
FastAPI user context
  ↓
authorization policies
```

Evaluate:
- Auth.js-compatible pattern;
- dedicated IdP;
- self-hosted auth library/service;
- managed auth provider.

Decision criteria:
- multi-user SaaS readiness;
- FastAPI compatibility;
- security maturity;
- cost;
- account recovery;
- MFA;
- vendor lock-in.

## 28. Security Invariants
1. Authentication != trading authority.
2. TWF authorization != broker authorization.
3. LLM output is untrusted.
4. Secrets never belong in browser bundles.
5. Broker secrets stay behind TM/broker boundary when possible.
6. Every user-owned resource is server-authorized.
7. Remote services authenticate.
8. Sensitive actions are auditable/idempotent.
9. Subscription entitlement never equals trading authority.
10. Security failures fail closed for authority-changing actions.

## 29. Realm and Configuration Security Clarification

Follow [configuration architecture v0.6](TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md) sections 3–7, 20, 25, 28 and 45–49. APS and ACS require distinct authenticated contexts/audiences and scoped authorization/audit. Shared IdP or infrastructure never makes an APS actor an ACS superuser. Work/Admin is navigation only. HUMAN/SERVICE principal kind, account ownership, DEMO usage class, subscription and role remain orthogonal.

APS_ADMIN grants only an owner-approved delegation set and cannot change its own authority or bypass separate approval through another principal. PLATFORM_OWNER is a governed recovery/approval identity; production break-glass requires reauthentication/MFA, reason, bounded scope/time and independent audit review. Developers receive no default customer-data access. Support requires a named operator, target account, approved basis/consent, reason, expiry, explicit read/write scope and revocation; no silent impersonation. Service principals use narrow audience/environment/task grants and dedicated machine credentials.

Settings read, edit, enable, apply and use are separately authorized. Entitlement or a UI mode never grants a role, secret access or TM authority. Secret references must be owner-checked; production integration secrets require a vault before activation. Profile cloning/import/export cannot transfer credentials or rights. Cross-user/tenant tests, stale revision conflicts, revoked-grant behavior, redacted explain/audit responses and failed-apply cleanup are acceptance requirements when each feature ships.

These additions do not expand TWF-1.5 into a realm/RBAC implementation. It uses authenticated personal ownership from TWF-1.4; shared-account and APS exposure require their own security gate first.
