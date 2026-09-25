# TradingWorkFlow (TWF) — Configuration, Setup, Capability, Entitlement & Pluggability Architecture

## Status

**Normative architecture — Version 0.6, reconciled for bounded TWF-1.5 planning on 2026-09-25**

Version 0.6 preserves the v0.5 design basis and supersedes its ambiguous realm, lifecycle, visibility and delivery rules. The [reconciliation review](TWF_CONFIGURATION_SETUP_ARCHITECTURE_REVIEW.md) records the changes and readiness decision. This is design acceptance, not evidence that these capabilities are implemented or a Git freeze. TWF-1.5 remains not started. The supplied DOCX remains a v0.5 reference; this Markdown is the sole current authority. The earlier v0.4 conceptual version is superseded. It consolidates the full configuration/settings/pluggability discussion into one normative design and adds the App Producer Side (APS), App Consumer Side (ACS), roles/privileges, subscription/entitlement model, capability lifecycle, effective-configuration resolution, platform administration, and SaaS operating model.

The commercial details of subscription plans (pricing, final plan names, quotas and exact feature bundles) remain TBD, but the **subscription architecture is intentionally included now** because it materially affects settings, capability exposure, roles, secrets, data design and future SaaS evolution.

---

## 1. Executive Summary

TWF configuration is not one flat “Settings” feature. It is a multi-plane system with explicit ownership and authority.

```text
                     TradingWorkFlow SaaS Platform
                                  │
                   APS / Platform Producer Realm
                                  │
                 COLD capability publication
                                  │
                    Capability Catalog
                                  │
                 Subscription / Entitlement
                                  │
                     ACS / Tenant Realm
                                  │
           Account Admin / Regular User / future roles
                                  │
                 HOT / WARM runtime settings
                                  │
          Presentation / User-Workflow / System-Integration
                                  │
            Account / User / Workspace / Workflow scopes
                                  │
                   Effective Runtime Configuration
```

The core rule is:

> **Every capability advertised by the currently deployed TWF release must already exist in the Platform Capability Catalog before subscribers need it. Subscription upgrades and subscriber settings must never require shutting down the application.**

True COLD changes belong to the APS/platform-owner plane and are delivered through platform deployment/operations. Subscriber-visible configuration is HOT or WARM only.

---

## 2. Core Architectural Dimensions

TWF configuration is described by several independent dimensions. They must not be conflated.

| Dimension | Question answered | Typical values |
|---|---|---|
| Realm | Which side of the product is acting? | APS / ACS |
| Principal kind | What kind of actor is this? | HUMAN / SERVICE |
| Account | Which ownership boundary is involved? | PLATFORM account / CONSUMER tenant |
| Environment and usage class | Where and for what purpose? | development/test/staging/production; STANDARD / DEMO |
| Role / privilege | What may this actor change? | Platform Owner, APS Admin, Developer, Account Admin, Regular User, etc. |
| Capability | What can this deployed platform do? | `llm.anthropic`, `broker.zerodha`, `ti.standard`, etc. |
| Entitlement | What may this ACS account use? | Plan grants, quotas, capability grants |
| Setting class | What kind of setting is this? | Presentation, User/Workflow, System/Integration |
| Mutability | How does a change take effect? | HOT, WARM; COLD only above subscriber runtime |
| Scope | Where does the value apply? | Platform default, Account, User, Workspace, Workflow |
| Profile | Which named reusable configuration instance? | “Primary LLM”, “Positional Scanner”, etc. |
| Secret ownership | Who supplies/owns the secret? | Platform, Account, User |
| Lifecycle and runtime state | Which independent gates pass? | Release/rollout, eligibility, configuration revision, selection, health, activation |

---

## 3. APS and ACS — Two First-Class Realms

### 3.1 APS — App Producer Side

APS contains the humans and service principals that build, operate, secure, maintain and govern TWF itself.

APS is **not** a premium subscriber account. It is a separate platform realm.

Representative APS responsibilities:

- platform ownership;
- release/deployment;
- capability publication;
- software development;
- service operations;
- database administration;
- security administration;
- support;
- audit/compliance;
- automated CI/CD, backup and monitoring services.

### 3.2 ACS — App Consumer Side

ACS contains subscribed customer accounts, their administrators and normal users who consume TWF functionality.

Representative ACS responsibilities:

- use entitled capabilities;
- configure personal/workspace profiles;
- choose active profiles;
- manage account-level settings where authorized;
- operate trader workflows;
- later manage users/teams within the account.

### 3.3 Security-realm invariant

APS and ACS are different security realms. A platform developer must not automatically gain customer-data access merely because they work on TWF, and an ACS administrator must never acquire platform-deployment privileges merely because the account has a high subscription tier.

Realm-qualified authentication contexts, session/token audiences, authorization policies and audit access must be distinct. They may share an identity provider only with explicit audience/session isolation; an ACS session cannot authenticate an APS operation. Realm switching requires an explicit authenticated context, never a UI parameter. Audit records retain both the real operator and target realm/account. APS operators receive operational telemetry through redacted interfaces, not implicit tenant read access. Separate deployments/identity providers are an operational choice, not required microservices.

TWF-1.4 currently supplies local human identity and sessions. It does not implement either realm's administration, account membership, RBAC, or support delegation. Personal settings may build on that accepted identity boundary; exposing APS or shared ACS functionality first requires the corresponding realm and ownership controls.

---

## 4. Principal and Account Classification

Use orthogonal fields rather than an expanding `ACC_TYPES` authorization enum:

| Concept | Values and meaning |
|---|---|
| Realm | APS or ACS, bound to authenticated context |
| Principal kind | HUMAN or SERVICE |
| Account kind | PLATFORM administrative account or CONSUMER tenant ownership boundary |
| Membership | Principal-to-account binding with explicit role/scope |
| Usage class | STANDARD or DEMO, independent of deployment environment |
| Environment | Development, test, staging or production |
| Subscription | Versioned grants/limits for the consumer account |

`APS_USER`, `APS_SERVICE`, `ACS_USER`, `APS_DEMO` and `ACS_DEMO` may be descriptive labels for combinations of these fields, never the source of permission. Demo is a restricted usage class, not a principal kind or synonym for a paid-plan trial. A service principal is never a human login. Future ACS automation requires its own account-bound machine policy; it is not implied by APS automation.

The same person can have separately authenticated APS and ACS contexts. Account ownership is distinct from a user identity and from an administrator role. Team/support functions normally use memberships and scoped grants, not new account types. TWF-1.5 must not equate `user_id` with `account_id` or infer membership from a role name.

---

## 5. APS Roles and Responsibilities

APS must use least privilege. “Developer” is not synonymous with “production super-admin.”

### 5.1 Role vocabulary and staged implementation

| APS role | Primary responsibility | Can grant roles? | Can publish COLD capability? | Can read ACS customer data by default? |
|---|---|---:|---:|---:|
| PLATFORM_OWNER | Ultimate product/platform authority | Yes, including APS_ADMIN | Yes | No blanket daily access; break-glass only where justified |
| APS_ADMIN | APS identity and delegated role administration | Only an owner-approved grant set | No | No |
| DEVELOPER | Build/maintain software | No | No direct production publication | No |
| RELEASE_OPERATOR | Execute approved releases/deployments | No | Executes owner-approved release | No |
| SERVICE_OPERATOR | Operate TWF services | No | No | Limited operational telemetry |
| DB_OPERATOR | Database maintenance | No | No | Data access limited by job and audit policy |
| SECURITY_ADMIN | Secrets/security/trust configuration | No | No | No ordinary business-data access |
| SUPPORT_OPERATOR | Diagnose customer incidents | No | No | Controlled support-access session only |
| AUDITOR | Read audit/security records | No | No | Read-only, scoped |

### 5.2 APS_ADMIN special rule

Per current product-owner intent:

> **APS_ADMIN is primarily an identity/role administration role. It grants or removes roles/privileges for other APS principals; it does not automatically inherit developer, deployment, database, security or support privileges.**

Only `PLATFORM_OWNER` can grant/revoke `PLATFORM_OWNER` or approve owner-level break-glass authority. APS_ADMIN cannot edit its own bindings, expand its grant set, or acquire operational authority indirectly by granting a cooperating principal a role it is not authorized to delegate. Owner approval defines allowed roles, recipients, scopes and expiry. Sensitive DB/security/release grants require separate approval; the grantor cannot approve its own elevation. The backend enforces these checks and audits denied as well as successful changes.

Owner authority is reserved for approval and recovery. Production break-glass requires strong reauthentication/MFA, a reason, narrow time-bound scope, durable audit and independent review. It is not blanket daily ACS data access. Bootstrap/recovery of the first owner is a controlled out-of-band operation, not public signup or an APS_ADMIN bypass. Exact tooling is deferred until APS production operations.

Three representative human identities — PLATFORM_OWNER, APS_ADMIN and DEVELOPER — are sufficient for an isolated architecture demonstration. They do not prove production operations segregation. DB_OPERATOR, SECURITY_ADMIN, SERVICE_OPERATOR, SUPPORT_OPERATOR and AUDITOR become implemented roles only as their operations appear; RELEASE_OPERATOR is a delegated release function. The v0.5 names DB_ADMIN and SUPPORT are superseded by DB_OPERATOR and SUPPORT_OPERATOR. No role framework or fixture account is required in TWF-1.5.

### 5.3 Platform owner and delegated execution

The TWF owner retains policy approval for true COLD capability publication. A delegated release operator may perform an approved deployment mechanically, but that does not transfer product-owner authority.

---

## 6. ACS Roles and Responsibilities

Initial ACS roles remain intentionally small.

| ACS role | Primary responsibility | Shared account settings | Personal settings | Platform capability install |
|---|---|---:|---:|---:|
| ACCOUNT_ADMIN | Manage account-level configuration and users later | Yes, within entitlement/policy | Yes | No |
| REGULAR_USER | Use TWF and configure own experience | No (except delegated future permissions) | Yes | No |

ACCOUNT_ADMIN and REGULAR_USER are sufficient initially. Both are account-bound; neither bypasses ownership, entitlement, secret-use permissions or TM authority. Future roles such as Analyst, Trader, Risk Manager, Read Only or Team Manager remain undefined until a use case requires them. Account ownership transfer and protection against removing the last administrator must be defined before shared account administration ships.

---

## 7. “Work / Admin Mode” Is a UI Context, Not Privilege Elevation

The concept of modes is useful ergonomically, but dangerous if it changes authority.

TWF may expose:

```text
Work mode
Administration mode
```

for users who already possess appropriate roles.

Rules:

- Switching UI mode does **not** grant a role.
- Backend authorization always evaluates principal realm, role, permission, scope and policy.
- A Regular User cannot enter an Admin view simply by toggling a switch.
- APS Admin may have a dedicated Administration workspace for role management.
- ACS Account Admin may have an Administration workspace for account configuration.
- Both realms may use Work/Administration navigation contexts, with persistent realm, account and acting-identity labels. APS Work means platform work, not access to an ACS trading account.
- Navigation mode is never sent as authorization evidence. Direct URLs and API calls receive the same backend checks. Switching accounts clears scoped client caches and unsaved context safely.
- Before administration is implemented, UX previews must say unavailable/preview and cannot pretend to mutate roles or entitlements.

---

## 8. Platform Bootstrap Plane

A small set of configuration must exist before TWF processes can start safely. These are not subscriber settings.

Examples:

- environment (`development/test/production`);
- database connection/bootstrap;
- platform security/session key material;
- secret-store bootstrap;
- trusted origins;
- base logging/observability configuration;
- minimum service-discovery/bootstrap configuration.

Ownership: APS platform/deployment side only.

These may be supplied through deployment manifests, environment variables and a secret manager. They should not appear as editable ordinary ACS Setup fields.

---

## 9. COLD Capability Architecture

### 9.1 Definition

COLD means a platform-owner capability change, for example:

- new TWF application release;
- new API capability;
- new provider/adapter implementation;
- new scanner integration type;
- new service protocol;
- core authentication/database infrastructure change.

### 9.2 Authority

COLD capability publication belongs to APS/platform ownership. Subscribers never install arbitrary platform code.

### 9.3 COLD does not mean customer downtime

Production should eventually use rolling or blue/green deployment. The term COLD is an authority/deployment lifecycle classification, not a promise of shutting down the SaaS platform.

---

## 10. Platform Capability Catalog

The Platform Capability Catalog is the authoritative list of capabilities the currently deployed TWF release can provide.

Example capability IDs:

```text
llm.openai
llm.anthropic
llm.google
scanner.basic
scanner.advanced
ti.standard
ti.advanced
tm.monitoring
broker.zerodha
broker.dhan
notifications.telegram
```

A capability definition may include:

- stable capability ID;
- feature family;
- provider/implementation identity;
- semantic version;
- required contract/API version;
- configuration schema;
- secret requirements;
- default settings;
- runtime mutability classification;
- health/test-connection capability;
- compatibility requirements;
- subscription-entitlement key;
- feature-flag/rollout state.

The catalog is APS-owned. These IDs are illustrative future capabilities, not claims that the current application implements them. Deployed release manifests register stable IDs before any usable capability is advertised. Runtime service discovery verifies the registered implementation; it cannot install code or grant entitlement.

Manifest contracts must include `requires[]`, `optional_dependencies[]` and `conflicts_with[]` now, even when empty. References name capability IDs and supported version/contract ranges. Registration rejects unknown required references and dependency cycles; activation rejects unsatisfied requirements and conflicts. Optional dependencies degrade explicitly and cannot silently select another provider. Eligibility must hold for every required dependency. A UI purchase never auto-grants a dependency.

Availability, rollout and health are separate observations, linked by release/revision. The publication workflow validates the catalog as a consistent set before exposure. Catalog read responses are filtered by disclosure policy; internal capabilities, endpoints and secret schemas are not leaked through public discovery.

---

## 11. Capability Lifecycle and Staged Rollout

The following are independent state dimensions, not one linear status enum:

| Dimension | Representative states or gates |
|---|---|
| Release presence | DEPLOYED, REGISTERED; absent implementation cannot be used |
| Compatibility | COMPATIBLE / INCOMPATIBLE against manifest, schema and contracts |
| Global policy | GLOBALLY_ENABLED / DISABLED; disabling does not uninstall code |
| Rollout | INTERNAL_ONLY → BETA → LIMITED_ROLLOUT → GENERAL_AVAILABILITY → DEPRECATED → RETIRED |
| Consumer eligibility | ENTITLED, ACCOUNT_ENABLED, USER_AUTHORIZED, each independently evaluated |
| Configuration | Validated revision and apply lifecycle from section 45 |
| Selection | Binding of a profile revision to the current permitted scope |
| Runtime | Health and confirmed activation of that revision |

Rollout cohorts are server-authorized and versioned, not client flags. An entitled account outside the rollout cohort cannot use the capability. Deprecation carries notice, supported versions and migration/sunset policy; retirement denies new use and preserves configuration/history subject to retention. Health failures do not erase entitlement, saved settings or selection.

Deploy and register first, validate compatibility/dependencies, test internally, admit selected beta accounts, then publish general availability under policy. Disable/rollback is possible without pretending the deployed code disappeared. Internal ACS testing uses isolated consumer fixtures, not APS superuser access to customers.

---

## 12. Subscription and Entitlement Architecture

Subscription is now included architecturally because it influences capability visibility, settings, quotas and administration. **Commercial plan contents remain TBD.**

### 12.1 Separation rule

```text
Subscription / entitlement = WHAT an ACS account may use
Role / privilege           = WHAT an actor may change
```

A PRO subscriber is not automatically an Account Admin. An APS developer is not a subscriber at all.

### 12.2 Core concepts

Recommended future model:

```text
PlanDefinition
PlanVersion
EntitlementDefinition
PlanEntitlement
UsageQuota
AccountSubscription
AccountEntitlement (effective/materialized if needed)
```

Plan versions are immutable once activated. Amendments create new versions with explicit effective times and migration/grandfathering policy, preserving historical customer rights.

### 12.3 Plan contents are capability references

Avoid business code such as:

```text
if plan == PRO: show Claude
```

Prefer:

```text
account_has_entitlement(account, "llm.anthropic")
```

Plan definitions grant capabilities/quotas; implementation logic lives elsewhere.

### 12.4 Upgrade behavior

A subscription upgrade changes entitlements dynamically. It does not redeploy or restart TWF.

```text
Plan change
→ entitlements recomputed
→ newly entitled capability becomes eligible within rollout/policy
→ Account Admin/User configures profile
→ profile revision is validated, applied and runtime activation confirmed
```

---

## 13. Subscriber Runtime Mutability — HOT and WARM

After platform capability publication and subscription gating, ACS runtime configuration is classified as HOT or WARM only.

| Mutability | Meaning | Examples |
|---|---|---|
| HOT | Applies immediately without reconnect/restart | Theme, density, profile label, watchlist default, safe scanner filters, notification preference |
| WARM | Requires controlled reconnect/rebind/reinitialization, but TWF stays running | Change TI/TM endpoint, rebind LLM credentials, activate another broker connection, reload provider config |
| COLD | Platform deployment/capability publication; not subscriber runtime configuration | New provider adapter implementation, new TWF release, new core API capability |

Mutability belongs to the setting/action descriptor, not the page it appears on. Profile selection can be WARM when it changes a connection or provider. Workflow defaults affect new work unless the contract explicitly allows changing an existing workflow. HOT means effective after a successful authorized apply, not an unvalidated optimistic UI write.

---

## 14. Setting Classes — the Original Three-Dimension Model

### 14.1 Presentation

Examples:

- theme;
- font/size/weight;
- density;
- visual layout preferences;
- table/chart appearance;
- color/accessibility preferences.

Usually HOT and user-scoped.

### 14.2 User / Workflow

Examples:

- default watchlist;
- default horizon;
- workspace behavior;
- active LLM/scanner profile;
- notifications;
- panel visibility;
- confirmation preferences;
- workflow defaults.

Usually HOT; provider/profile activation may be WARM. May exist at user/workspace/workflow scope. Confirmation preferences cannot disable mandatory trader approval or TM checks.

### 14.3 System / Integration

Subscriber-visible integration configuration, for example:

- LLM provider profile;
- TI/TM service profile;
- scanner provider setup;
- broker connection;
- notification provider;
- timeouts/fallbacks.

Usually HOT or WARM. Account-level values often require Account Admin authority.

Platform bootstrap/deployment configuration is **not** ordinary ACS System/Integration settings.

---

## 15. Setting Scopes and Precedence

Canonical scopes are PLATFORM, ACCOUNT, USER, WORKSPACE and WORKFLOW. PLATFORM provides defaults or locks, under APS authority. ACS scopes are:

```text
ACCOUNT
USER
WORKSPACE
WORKFLOW
```

Platform defaults and plan/policy constraints exist above ACS scopes.

Where overrides are allowed, precedence may be:

```text
Workflow override
    > Workspace
    > User
    > Account
    > Platform default
```

However, a setting definition must explicitly declare which scopes are legal. Example:

| Setting | Allowed scopes |
|---|---|
| Theme | User, Workspace |
| Active LLM profile | User, Workspace, optionally Workflow |
| Account Anthropic credential | Account only |
| Production DB | Platform bootstrap only; not ACS setting |

The descriptor declares legal scopes and which lower scopes can override each value. A platform/account constraint is not a default that a user can overwrite. Resolution must first prove workspace/workflow ownership and their account relationship. A missing override means inherit; reset removes the override, while an explicit null is legal only if the schema permits it. Collection merge versus replacement must be declared per descriptor; default to replacement. Unsupported scopes are rejected, not silently flattened.

---

## 16. Effective Configuration Resolution

Stored desired values, resolved effective values, and applied runtime revisions are separate.

1. Bind the authenticated realm, actor, owner/account and resource context; authorize reading or editing before disclosing values.
2. Load the versioned descriptor and allowed scopes; reject unknown keys/scopes. Resolve permitted precedence and provenance, including inherited defaults.
3. Evaluate deployed/registered capability, compatibility, dependencies, rollout, entitlement, account enablement and permission for the intended operation.
4. Enforce platform/account locks, limits and schema/cross-field constraints. Reject invalid input; any declared normalization must be visible to the caller.
5. Validate secret-reference ownership/use permission and availability where required. Obtain runtime health/connection observations separately with their timestamps.
6. Produce an effective candidate, validation/eligibility reasons and source revisions. Apply according to HOT/WARM policy, then report the actual applied revision and runtime state.

For example, a user timeout of 120 seconds under a platform maximum of 60 seconds is rejected unless the descriptor explicitly defines and reports normalization. Failed eligibility must not overwrite stored desired values or silently switch provider.

Read, configure, enable and use permissions are distinct. An administrator may repair a disabled profile without being permitted to execute its workflow. Health can block activation while leaving an effective candidate and saved selection inspectable. Recheck current policy/revisions before apply and at consequential action boundaries; a previously displayed effective value is not a reusable authorization grant.

The future Explain Effective Setting response reports the winning scope, inherited/overridden sources, descriptor/configuration/policy/entitlement revisions, applied revision, observation time and safe reason codes. It uses the same resolver and ownership checks. It never returns secrets, credentials, hidden internal capabilities, other tenants' values, or sensitive raw endpoints. TWF-1.5 implements explanations only for its non-secret settings.

---

## 17. Profiles

Profiles are named reusable configuration instances.

Examples:

```text
LLM profile      "Primary Trading Reasoner"
Scanner profile  "Intraday Momentum"
TI profile       "Positional Equity"
Broker profile   "Zerodha Primary"
Workspace profile "Day Trading"
```

Architecture should not hard-limit stored profiles to 3–5. The UI may limit pinned/favorite profiles for ergonomics.

Profile metadata should include at least:

- profile ID;
- feature/capability ID;
- owner/scope;
- schema version;
- state;
- settings values;
- secret references;
- created/updated timestamps;
- compatibility metadata;
- optimistic revision and lifecycle metadata, separate from runtime health.

The model supports create, edit, clone, activate, deactivate and reset, with export/import deferred. Cloning copies non-secret values and revalidates scope; references may be reused only with explicit same-owner permission, otherwise the clone requires a new secret binding. Reset removes an override or restores a descriptor default, not factory-resetting an account. Activation binds a validated profile revision atomically; deactivation does not delete it. Only one primary LLM binding per applicable context is normal. Delete must reject or explicitly detach active references and preserve required audit history.

## 18. Profile and Runtime State

Use section 11 for platform/account gates and section 45 for configuration changes. A profile may contain a saved DRAFT revision while an older APPLIED revision remains selected. Validation results are tied to exact schema, value and reference revisions; editing invalidates validation.

Selection is a durable scope binding. Runtime state separately reports pending, active, degraded, unavailable or blocked, with the applied revision and a reason. If health later fails, keep the selection visible as selected/degraded instead of implying it was deleted or successfully switched elsewhere. An inactive profile is retained configuration with no active binding, not a missing entitlement.

---

## 19. Configured vs Enabled vs Active

These are distinct concepts.

Example:

```text
OpenAI profile:
    CONFIGURED = yes
    ENABLED = yes
    ACTIVE = yes

Claude profile:
    CONFIGURED = yes
    ENABLED = yes
    ACTIVE = no
```

The settings architecture must preserve these distinctions across LLMs, scanners, brokers and other pluggable services.

---

## 20. Secrets Architecture

Secrets are not ordinary settings.

Profiles/settings contain `secret_ref`, not raw secrets.

Secret ownership classes:

```text
PLATFORM_MANAGED
ACCOUNT_MANAGED
USER_MANAGED
```

Examples:

- TWF-provided LLM entitlement → platform-managed provider credential;
- enterprise customer BYOK → account-managed credential;
- personal user key, if later supported → user-managed credential.

Production integration secrets require a secret manager/vault before those integrations ship. The configuration DB stores metadata/reference only. Resolution checks both owner scope and permission to use the reference; possession of a reference string grants no access. A platform-managed credential never becomes readable by ACS users.

References track version/status and permit rotation, expiry and revocation. Rotation is a privileged operation with WARM rebind where needed; revoked/expired references block new use. Connection tests use authorized server-side credentials, bounded timeouts and sanitized results, never returning secrets to the browser. Broker secrets stay behind TM's broker boundary; a TWF broker profile may reference a TM-managed connection, not import raw broker credentials.

Endpoint connection tests also require an environment-specific destination policy before they ship: allow approved protocols/hosts, reject credential-bearing URLs, constrain redirects and block cloud metadata or unintended internal destinations. Local adapters may use explicitly approved local endpoints; a user-supplied URL is never permission for arbitrary server-side network access.

Exports exclude secret values and by default secret references/identifying metadata. Import cannot recreate secret ownership or rights; it requires validation and rebinding. Exact vault provider and credential entry UI remain deferred.

---

## 21. Plugin / Provider Manifest

A capability provider should expose a versioned manifest rather than require hard-coded UI logic for every provider.

Conceptual fields:

```text
plugin/capability identity
version
feature family
capabilities
configuration schema
secret schema
defaults
validation rules
health check
connection test
runtime mutability
compatibility requirements
requires / optional_dependencies / conflicts_with
rollout and entitlement references
configuration schema migration policy
exposed features
```

TWF should prefer explicit registration over arbitrary runtime code discovery.

---

## 22. Capability-Driven Settings UI

Visibility, configurability, usability and activation are different decisions.

| Decision | Rule |
|---|---|
| Discover | Disclosure policy may show a sanitized public catalog card even without entitlement, with a truthful unavailable/upgrade explanation |
| Configure or repair | Appropriate ownership/permission, schema and policy; disabling use does not hide the controls needed to fix or re-enable it |
| Enable for account | Account authority plus current entitlement, rollout and policy |
| Use | All operation-specific eligibility gates in section 38 |
| Active | Selected revision successfully applied and runtime confirmed |

Internal-only capabilities remain hidden outside authorized cohorts. An upgrade card is not an editable credential form or a promise that undeployed code is ready. UI labels distinguish not deployed, not entitled, disabled, invalid, applying and degraded. Backend checks govern every operation even if the caller bypasses the UI.

---

## 23. Hierarchical Setup Center UX

The user’s original matrix model is adopted as the **underlying hierarchy**, while the visible UI should use progressive drill-down rather than a spreadsheet matrix.

Example:

```text
Setup
  ↓
LLM
  ↓
Providers
  ↓
Anthropic
  ↓
Profiles
  ↓
Claude Trading
```

Recommended visible layout:

```text
left:    major settings feature
middle:  selected sub-feature
main:    form/details
```

Additional depth should use tabs, breadcrumbs, expandable tree nodes or contextual lists. Avoid showing more than ~3 navigation depths simultaneously.

---

## 24. Basic, Administration and Advanced Surfaces

### Regular Setup

- Appearance
- Workspace
- LLM
- Scanner
- Broker
- Notifications
- Profiles

### ACS Administration (Account Admin only)

- Users (later)
- Enabled capabilities
- Shared profiles
- Connections
- Account secrets
- Account defaults
- Subscription/entitlement visibility

### APS Platform Administration

- Capability Catalog
- Deployments/releases
- Plugin/adapter releases
- Platform services
- Platform policy
- Platform secrets
- Database/operations
- Security
- Support tooling
- Audit

Do not merge all three into one flat Settings page.

---

## 25. APS Workflows and Administration

### 25.1 Publish a new capability

```text
Platform Owner approves capability/release
→ Developer builds implementation
→ Release Operator deploys approved release
→ compatibility/health checks
→ capability registered
→ internal/beta enablement
→ subscription plan entitlement can reference it
```

### 25.2 Assign APS roles

```text
Platform Owner creates/grants APS_ADMIN
→ owner defines delegated grant set, scopes and approval policy
→ APS_ADMIN manages only permitted other principals/bindings
→ backend prevents direct/indirect self-elevation and audits the result
```

### 25.3 Support access to ACS account

Support should not silently impersonate a customer. Future design should use a controlled support-access session with:

- target account;
- operator;
- reason/ticket;
- time limit;
- scope/read-write permission;
- audit trail;
- customer consent/approval reference under an explicit policy.

Support access is denied until consent or a separately approved emergency basis is recorded. Exact customer-consent UX is deferred, not authorization to omit consent policy. Sessions expire and can be revoked early; every access records both operator and target account. Read-only is the default; writes require additional explicit scope/approval. No shared customer password, silent impersonation or support grant of TM/broker authority is allowed.

---

## 26. ACS Workflows

### 26.1 Subscription upgrade

```text
Account changes plan
→ entitlement set changes
→ new capabilities become visible
→ Account Admin may enable them
→ user creates/configures profile
→ user activates capability
```

No restart or deployment occurs.

### 26.2 Account Admin enables a capability

```text
Capability is platform-available + entitled
→ Account Admin enables for account
→ shared configuration/secret established if needed
→ validation/test connection
→ capability becomes available to authorized users
```

### 26.3 Regular user configures profile

```text
User opens Setup
→ selects available feature/provider
→ creates personal profile
→ validates profile
→ activates within allowed scope
```

---

## 27. Demo Usage Class

DEMO is an orthogonal usage class within APS or ACS, not a third realm or a subscription trial. Demonstrations use isolated accounts/data, synthetic or explicitly approved sandbox adapters, and no production-changing privileges or production secrets. Test traffic and audit/provenance remain marked synthetic.

A commercial trial may eventually be STANDARD with restricted entitlements under a separate live-use policy; it must not silently promote a demo fixture to production authority. Demo-to-standard migration, if offered, requires explicit ownership and policy validation and new secret bindings. Demo quotas/retention are product policy, not a role.

---

## 28. Service Principals

APS includes non-human identities such as:

- CI/CD pipeline;
- migration worker;
- backup service;
- monitoring agent;
- billing worker;
- scheduler.

Service principals require narrow permissions, machine-authentication and auditability. They must not share human credentials. Use workload identity or short-lived credentials where available, bind audience/environment/task, rotate/revoke credentials and record the initiating job/release. Migration and backup principals may require tightly scoped data-plane rights approved independently of ordinary APS membership. No machine identity receives PLATFORM_OWNER for convenience. A scheduler acting for an ACS workflow must revalidate that account's policy; APS machine identity never bypasses consumer authorization.

---

## 29. Authorization Model

Conceptually:

```text
Principal
├── principal_kind
├── realm
├── account/tenant context where applicable
├── role bindings
└── permissions/scopes
```

Recommended policy direction:

- role-based baseline (RBAC);
- scope/context constraints;
- policy checks for sensitive actions;
- least privilege;
- no universal daily-use super-admin.

A break-glass owner mechanism may exist later but must be explicitly elevated and audited.

---

## 30. Subscription Model — Architectural Commitments, Commercial TBDs

The architecture commits now to:

- versioned plan definitions;
- capability-based entitlements;
- quota/limit hooks;
- dynamic entitlement changes without restart;
- account-level subscription identity;
- role/entitlement separation;
- plan changes being auditable;
- future grandfathering/migration support through plan versions.

Deferred commercial design:

- final plan names;
- pricing;
- exact capability bundles;
- billing provider;
- trial duration;
- usage overage policy;
- promotions/coupons;
- enterprise contracts.

---

## 31. Proposed Component Model

Core conceptual components:

```text
CapabilityRegistry
CapabilityPolicy
EntitlementService
AuthorizationService
ConfigurationService
ProfileService
SecretReferenceService
EffectiveConfigurationResolver
CapabilityHealthService
AuditJournal
SetupCenter UI
PlatformAdministration UI
AccountAdministration UI
```

These are logical responsibilities, not necessarily separate deployable microservices.

---

## 32. Proposed Data Concepts

TWF-1.5 should anticipate, but not necessarily implement all of:

```text
Principal / Account / AccountMembership
CapabilityDefinition
CapabilityRelease / Version
PlatformCapabilityState
FeatureFlag / RolloutRule
PlanDefinition
PlanVersion
EntitlementDefinition
PlanEntitlement
UsageQuota
AccountSubscription
AccountCapability
Role
Permission
RoleBinding
SettingDefinition
SettingValue
Profile
ProfileBinding
SecretReference
ActivationBinding
CapabilityHealth
ConfigurationChange / AuditEvent
```

Avoid a generic untyped key/value settings table as the only foundation.

---

## 33. Settings Resolution Contract

A `SettingDefinition` or equivalent descriptor should be able to declare:

- stable setting key;
- setting class;
- value/schema type;
- allowed scopes;
- default value;
- HOT/WARM mutability;
- minimum authority/permission;
- required capability;
- entitlement requirement hook;
- validation constraints;
- platform min/max constraints;
- secret/non-secret classification;
- restart/reconnect semantics;
- schema version;
- audit sensitivity.

---

## 34. TWF-1.5 Minimum Foundation Guidance

TWF-1.5 remains a representative settings foundation. Its implementation prompt must name the finite setting keys, schemas, defaults, permitted scopes and UI surfaces before coding.

1. Typed descriptors for Presentation and safe User/Workflow preferences, with class, schema version, legal scopes, mutability, authority and capability hooks. Unknown keys/scopes are rejected.
2. Authenticated user-owned persistence on the accepted TWF-1.4 identity. No inferred account membership or automatic admin role. PLATFORM defaults may be read-only; shared ACCOUNT and workflow-owned settings remain deferred unless their ownership foundation receives a separate bounded design.
3. Effective resolution and redacted source/default explanation for implemented scopes. Workspace scope requires a real authorized ownership relation; metadata alone does not justify a workspace CRUD subsystem here.
4. A small typed non-secret personal profile foundation, with revision checking, validation and explicit apply/reset behavior. Do not build a universal form engine or production integration profile catalog.
5. Capability/entitlement interfaces with an explicit finite foundation allowlist and deny-by-default unknown capabilities. No implicit allow-all substitute for billing. Future capability IDs stay illustrative until implemented and registered.
6. A secret-reference contract that rejects raw secret values; no credential entry, vault implementation, live connection tests or endpoint execution in this target.
7. Setup Center foundation, accessible validation/save/failure states, protected API paths and change/audit metadata. HOT apply can complete in one transaction; WARM is metadata/contracts until a real adapter exists.
8. Optimistic revisions from the first mutable settings/profile record, explicit transactions/migrations, cross-user negative tests and failure rollback tests.

Theme migration must preserve the accepted TWF-1.1A browser-local pre-paint behavior. The implementation design must specify user preference versus device fallback, logout/user-switch behavior and restoration timing; a previous user's preference cannot be represented as the next user's saved value. Do not silently rewrite accepted auth or theme behavior as part of settings.

Full APS/ACS administration, accounts/teams, billing, production secret storage, arbitrary plugin loading, real satellite integrations and UX-B2/B3 screens remain outside this target. Representative role fixtures are architecture demonstrations, not mandatory TWF-1.5 seed accounts. The [UX bucket plan](TWF_UX_BUCKET_ROADMAP.md) tracks partial foundation progress without declaring all UX-B1 complete.

---

## 35. Representative Initial Accounts for Architecture Validation

For early development/demo purposes, architecture should support representative identities such as:

```text
APS owner account     → the current product owner
APS developer account → developer role, no owner/admin privilege
APS admin account     → role administration only
ACS demo account      → safe consumer demonstration
ACS regular account   → normal settings/workflow use
```

These are development fixtures / representative roles, not hard-coded production accounts.

---

## 36. Roles vs Modes vs Account Types — Summary

| Concept | Example | What it controls |
|---|---|---|
| Realm | APS / ACS | Which security/administration world the principal belongs to |
| Principal kind | HUMAN / SERVICE | Human or machine authentication |
| Account kind | PLATFORM / CONSUMER | Administrative or tenant ownership boundary |
| Usage class | STANDARD / DEMO | Restricted usage policy, independent of environment |
| Role | APS_ADMIN, DEVELOPER, ACCOUNT_ADMIN, REGULAR_USER | Permissions/authority |
| UI mode | Work / Administration | Navigation/context only; never grants privilege |
| Subscription | Plan/version | ACS capability entitlement |
| Mutability | HOT / WARM / COLD | How a configuration/capability change takes effect |
| Setting class | Presentation / User-Workflow / System-Integration | Functional category of runtime setting |
| Scope | Account/User/Workspace/Workflow | Where runtime value applies |

---

## 37. Authority and Responsibility Matrix

| Action | Platform Owner | APS Admin | Developer | Release/Ops | ACS Account Admin | ACS Regular |
|---|---:|---:|---:|---:|---:|---:|
| Approve new COLD capability | Yes | No | No | No | No | No |
| Assign APS roles | Yes | Yes (bounded) | No | No | No | No |
| Develop feature | Optional | No | Yes | No | No | No |
| Execute approved release | Optional | No | No | Yes | No | No |
| Change platform bootstrap | Yes/delegated | No | No | Role-dependent | No | No |
| Enable entitled ACS capability | No | No | No | No | Yes | No |
| Configure shared account profile | No | No | No | No | Yes | No |
| Configure personal profile | No | No | No | No | Yes | Yes |
| Change appearance/workspace | No | No | No | No | Yes | Yes |
| Install arbitrary plugin code | Owner-approved APS process only | No | No | Mechanical approved deployment only | No | No |

---

## 38. Feature Usability and Activation

For the requested operation, evaluate:

```text
Usable = DeployedAndRegistered
    AND Compatible AND DependenciesSatisfied AND NoConflicts
    AND GloballyEnabled AND RolloutPermitted
    AND Entitled AND AccountEnabled AND ActorAuthorized
    AND ConfigurationValid AND RequiredSecretsAvailable
    AND RuntimeHealthAcceptable

Active = Usable AND SelectedForCurrentScope
    AND ApplySucceededForSelectedRevision AND RuntimeActivationConfirmed
```

Health acceptability is contract-specific: degraded read-only display may be usable with a warning, while an authority-changing action fails closed. Selection persists when Usable becomes false; report selected/blocked or selected/degraded with the last applied revision. Never interpret a checkbox as confirmation of runtime activation. For in-flight work, section 46 governs entitlement loss; TM remains the authority for existing broker exposure.

---

## 39. Auditability

Audit at least:

- capability publication/disablement;
- platform role assignment;
- account capability enable/disable;
- subscription/entitlement change;
- account/user settings changes;
- profile creation/activation;
- secret-reference changes (never secret values);
- support-access sessions;
- administrative mode entry where sensitive;
- configuration validation failures.

Each implemented sensitive change must capture actor, realm/context where implemented, scope, target, revisions, safe before/after metadata, timestamp, outcome and correlation ID; reason/ticket applies to governed operations. Reserved future realms or roles must not be fabricated in current audit records.

---

## 40. Security Invariants

1. APS and ACS are distinct security realms.
2. Subscription tier never grants APS privileges.
3. Premium/PRO never implies Account Admin.
4. UI mode never elevates backend permission.
5. Developer does not automatically mean production access.
6. APS Admin administers roles; it is not an all-powerful platform operator.
7. True COLD capability publication remains platform-owner controlled.
8. Subscriber-visible changes never require application restart.
9. Secrets are separate from ordinary settings.
10. Support/customer access is controlled and audited, not silent impersonation.
11. Demo accounts cannot accidentally reach live trading authority.
12. Service principals use machine identities, not human credentials.

---

## 41. Operational Invariants

1. Everything advertised by the deployed release already exists in the Platform Capability Catalog.
2. Capability rollout can be staged with feature flags/enablement without redeployment after the capability is already present.
3. Subscription changes apply dynamically.
4. HOT applies immediately.
5. WARM performs bounded reconnect/rebind without TWF shutdown.
6. COLD changes are handled by platform deployment and should use zero/minimal-downtime release techniques.
7. The capability catalog, entitlement, authorization and configuration decisions remain independently observable/auditable.

---

## 42. Reviewed Architecture Decisions

- One authoritative configuration/capability architecture document.
- APS/ACS realm separation.
- COLD is platform-owner capability/deployment authority.
- Subscriber runtime has HOT/WARM only.
- Capability Catalog precedes subscription/entitlement.
- Subscription controls ACS capability entitlement, not authority.
- APS/ACS roles control privileges independently of subscription.
- UI Work/Admin modes are presentation contexts, not privilege escalation.
- Three setting classes remain: Presentation, User/Workflow, System/Integration.
- Scopes: Platform defaults, Account, User, Workspace, Workflow, only as allowed by each descriptor.
- Profiles are first-class reusable configuration objects.
- Secrets use references and explicit ownership classes.
- Settings UI is hierarchical and capability-driven.
- Effective configuration is resolved through precedence, policy, entitlement, authorization, validation and health.
- Plan/subscription architecture is included now; commercial details are deferred.

---

## 43. TBDs for Later Design

- final commercial plan names/pricing;
- exact plan capability bundles and quotas;
- billing provider;
- detailed ACS role taxonomy beyond Admin/Regular;
- detailed APS developer/operations role granularity;
- exact break-glass tooling, subject to the mandatory controls in section 5;
- customer-consent UX and emergency approval mechanics, subject to section 25;
- exact secret-manager implementation;
- dynamic remote capability registration policy;
- schema-driven form engine implementation;
- configuration export/import policy;
- profile sharing/templates;
- plan grandfathering/migration UX;
- feature-flag provider vs native implementation;
- admin-console routing/deployment boundary.

---

## 44. Next Engineering Gate

The [architecture review](TWF_CONFIGURATION_SETUP_ARCHITECTURE_REVIEW.md) records `GO_TWF1_5` for a bounded implementation plan under section 34. TWF-1.5 is not implemented by this reconciliation. Produce its finite settings/profile contract and acceptance cases before coding; preserve the accepted authentication, theme and database foundations. Each later feature must satisfy the applicable gates below before exposure.

---

## 45. Configuration Lifecycle and Concurrent Editing

Each change has an immutable identity, owner scope, expected base revision, descriptor/schema version, actor and safe audit metadata. Lifecycle:

```text
DRAFT → VALIDATED → APPLYING → APPLIED
                       ↓
                     FAILED → ROLLED_BACK (only after restoration is confirmed)
```

An edit creates a new revision and invalidates prior validation. Apply checks current authority, eligibility, schema and referenced revisions again. HOT changes may atomically validate, save and apply; no asynchronous framework is required for a theme or preference. WARM changes preserve the last known applied revision, stage/rebind the candidate, perform a bounded check and promote only after success. UI reports desired versus applied revision and progress/failure honestly.

Use optimistic concurrency (`revision` or an ETag with a conditional write). A stale writer receives a conflict/precondition error and the permitted current revision; no last-write-wins overwrite of shared or multi-tab edits. Reset, clone, activation bindings and deletes also enforce revisions/ownership. Retry uses a change/idempotency identity so it cannot apply twice.

Rollback is a governed compensating operation: record a new event restoring a known compatible revision, not deletion of history. If a secret is revoked or an external side effect cannot be undone, remain FAILED/degraded with explicit recovery instructions; never claim ROLLED_BACK without proof. Rollback cannot restore revoked permission or undo a broker action. Durable retry/recovery for WARM changes is required before those adapters ship, not a worker framework in TWF-1.5.

## 46. Entitlement and Account Lifecycle

Upgrades, downgrades, trial expiry, payment failure, grant revocation and temporary suspension are versioned policy inputs, not plan-name conditionals. A policy defines effective time, any commercial grace interval and limits; unrecognized or expired grants deny new gated use. Payment events are reconciled idempotently against the current subscription version before they change grants. Pricing and grace durations are deferred until billing is implemented.

Entitlement loss normally retains owned settings/profiles inactive, under retention policy. It denies new activations and new gated actions; read/repair/export access is separately authorized. Restoration requires fresh schema, dependency, secret and permission validation and explicit safe activation, never automatic restart of a previously running trade workflow. Reduced quotas block new allocations rather than deleting arbitrary existing profiles.

Running work records capability, configuration and entitlement revisions. Recheck at new consequential actions and authorization renewals. Pause/cancel optional queued analysis safely on loss of eligibility. Never abandon TM monitoring, cancel broker exposure, liquidate a position or invent a trading action because a plan changed. Existing exposure follows TM's governed safety/monitoring policy with an explicit handoff and audit; any limited safety access must be defined before live integration. A workflow snapshot is provenance, not permanent authorization.

Before distributed entitlement caching, define maximum staleness, invalidation and outage policy per operation. Cache keys include realm, account, principal/permission context and policy/entitlement revisions. Revocation invalidates authorization caches and long-lived channels; high-consequence actions require current authoritative checks and fail closed when freshness cannot be established. Bounded stale data may be displayed with an as-of label, never used as a stale permission grant.

Suspension disables new gated work and sessions/grants as policy requires while preserving governed safety operations and audit. Account deletion is a separate authenticated, authorized lifecycle with grace/legal-hold/retention policy, secret revocation, reference cleanup and deletion evidence. Subscription cancellation alone must not delete tenant data. Exact periods require product/legal decisions before production onboarding/deletion.

## 47. Ownership and Isolation Gates

An ACS account is the tenant boundary; principals join through explicit memberships. Account ownership, membership and ACCOUNT_ADMIN are distinct, with verified transfer and last-admin protection before shared administration. No request may choose an account merely by posting its ID. Queries, unique constraints, references, exports, background jobs and realtime topics must enforce ownership; caches must not leak across tenant, user or realm.

TWF-1.5 may persist strictly personal `user_id` settings without implementing accounts. Future migration must explicitly map existing owners to verified memberships/accounts, preserve IDs and provenance, detect ambiguous mappings, and test cross-tenant denial before enabling sharing. Never backfill every user into one implicit production tenant or equate user IDs with account IDs. New shared resources must have a verified account owner before creation.

Audit is append-oriented, access-controlled and separated by realm/target; include actor, delegation, scope, revisions, outcome and correlation, with redacted diffs. Define retention/deletion categories before production, including audits, profiles, exports, support records and backups. Retained configuration after downgrade is not a promise of indefinite storage. Secrets and sensitive endpoints must not appear in ordinary audit diffs or explain responses.

## 48. Schema and Provider Evolution

Version capability implementations, API contracts, configuration schemas and profile revisions independently. Provider upgrades declare supported old schemas and tested forward transformations; preserve original revisions, preview validation failures and require revalidation before activation. Unknown future schemas are rejected explicitly. Profile imports are untrusted, bounded data with ownership checks and no executable payloads.

Registration checks dependency cycles, version ranges and conflicts. Rollout of a replacement must account for dependent capabilities and rollback compatibility. Deprecation/retirement includes notice, replacement guidance, retained inactive profiles and a policy for running work; no silent provider substitution or provenance change. A migration must not silently widen permission or copy secret values.

API additions should be backward compatible; breaking changes need an explicit version/adapter and migration plan. Before mixed-version deployments, verify database expand/contract migrations, config-schema compatibility and rollback across both releases. Failed compatibility gates prevent advertisement of the new capability.

## 49. Configuration and Platform Operations

Configuration is persistent desired state. Deploy, restart, migrate, restore, rotate a secret, invalidate a cache and upgrade a plugin are operations with separate command contracts, authorization, approval, idempotency, progress and audit. An operations screen may link to settings, but a settings PATCH must not execute arbitrary infrastructure commands.

COLD changes are APS-approved releases/bootstrap changes. Rolling or blue/green deployment is the production direction, not a current availability guarantee; it requires capacity, session continuity, schema compatibility, safe draining and rollback evidence. No Kubernetes requirement is introduced. WARM changes may temporarily interrupt a particular connection while TWF stays available; UX must show this honestly.

The accepted `/ready` remains application-initialization-only. Capability health, DB probes and integration readiness are separate observations until a separately reviewed operational contract changes this endpoint.

## 50. UX and Delivery References

[UX Bucket Roadmap](TWF_UX_BUCKET_ROADMAP.md) defines UX-B1/B2/B3 as a cross-cutting maturity workstream. [Detailed Roadmap](TWF_DETAILED_ROADMAP.md) retains functional TWF-0 through TWF-10 sequencing. Synthetic Scanner/TI/TM/LLM adapters must satisfy versioned logical contracts, expose synthetic provenance and never grant live authority. Configuration schemas describe supported functionality; they do not authorize ahead-of-milestone implementation.
