# Marsha AI Architecture

# Engineering Philosophy

Marsha AI is engineered around durable business workflows rather than conversational exchanges.

Business logic belongs in reusable services.

AI should generate structured outputs that can be validated, persisted, reviewed, and reused.

Every architectural abstraction should exist because it solves a demonstrated problem rather than because it follows a trend.

## Purpose

This document defines the architectural boundaries of the Marsha AI platform and its first reference implementation, the Sponsorship Coordinator.

Its purpose is to keep platform capabilities, domain-specific behavior, application services, persistence, routes, and user-interface concerns separate enough to remain maintainable and reusable.

This document describes the intended architecture. It must remain aligned with the implemented codebase and should be updated whenever a meaningful architectural decision changes.

---

## Architectural Position

Marsha AI is a workflow-based artificial intelligence platform.

The Sponsorship Coordinator is the first domain application built on that platform.

The codebase currently contains both:

* shared Marsha AI foundations
* Sponsorship Coordinator-specific behavior

Those responsibilities may coexist in one repository while the product is still being established.

The architecture should evolve incrementally. Shared platform components should be extracted only when their reuse is demonstrated or their domain-independent responsibility is sufficiently clear.

---

## System Context

At a high level:

```text
User
  ↓
Workspace
  ↓
Flask Route
  ↓
Application Service
  ↓
AI Orchestrator
  ↓
Domain Intelligence Services
  ↓
Validation
  ↓
Persistence
  ↓
Structured Result
  ↓
Workspace UI
```

The route coordinates the HTTP request.

The application service coordinates the use case.

The AI Orchestrator coordinates the intelligence-generation workflow.

Domain intelligence services perform specialized analysis.

Validation ensures the generated result conforms to expected structures.

Persistence stores durable records.

The workspace presents the resulting state to the user.

---

## Primary Architectural Layers

## 1. Presentation Layer

The presentation layer includes:

* Jinja templates
* Bootstrap components
* forms
* workspace screens
* status messages
* user actions
* display formatting

Responsibilities:

* present application state
* collect user input
* submit valid requests
* display controlled success and error states
* avoid embedding business rules in templates

The presentation layer should not:

* call the AI provider directly
* query multiple domain models to assemble business workflows
* implement persistence logic
* determine sponsorship strategy
* perform complex validation
* contain orchestration logic

---

## 2. Route Layer

The route layer includes Flask endpoints and request handling.

Responsibilities:

* receive HTTP requests
* validate basic request shape
* identify the current record or workspace context
* call the appropriate application service
* interpret the service result
* redirect or render a template
* flash user-facing messages where appropriate

Routes should remain thin.

A route should not:

* coordinate multiple AI services directly
* contain substantial business logic
* construct complex domain intelligence
* perform manual transaction management across several operations
* duplicate logic used by another route
* contain provider-specific AI code

A route may perform lightweight concerns such as:

* parsing form fields
* converting identifiers
* selecting a redirect target
* applying authorization checks
* mapping a service result to a user-facing response

---

## 3. Application Service Layer

Application services represent complete application use cases.

Examples include:

```text
generate_sponsorship_intelligence
approve_sponsorship_intelligence
regenerate_sponsorship_intelligence
send_outreach_message
schedule_follow_up
complete_follow_up
```

Responsibilities:

* coordinate a complete use case
* load required domain records
* enforce workflow preconditions
* call the AI Orchestrator or other domain services
* validate returned results
* coordinate persistence
* return a structured result
* preserve transaction boundaries
* provide controlled error outcomes

Application services should not:

* render templates
* return Flask response objects
* depend on browser state
* contain HTML
* depend directly on form objects
* expose raw provider responses to routes

Application services should be testable independently from the UI.

---

## 4. AI Orchestration Layer

The AI Orchestrator coordinates multi-step intelligence generation.

Responsibilities:

* determine the required intelligence-generation sequence
* invoke domain intelligence services in the correct order
* pass structured context among services
* combine validated results
* return a complete intelligence package
* remain independent of Flask routes and templates

The Orchestrator should not:

* render UI
* commit database records unless persistence is explicitly part of its contract
* contain user-session logic
* depend on route-specific request objects
* expose unvalidated model output

The Orchestrator represents workflow coordination, not presentation or persistence.

---

## 5. Domain Intelligence Services

Domain intelligence services perform specialized business analysis.

Current examples include services responsible for:

* organization analysis
* sponsorship asset recommendations
* sponsor-category recommendations
* research-priority generation
* sponsorship strategy generation
* structured sponsorship intelligence generation

Responsibilities:

* accept structured inputs
* apply domain-specific reasoning
* invoke the configured AI provider when required
* validate expected output
* return typed or structured domain results
* remain reusable across application workflows

A domain intelligence service should have one primary responsibility.

It should not:

* query unrelated UI state
* render templates
* redirect users
* perform broad application orchestration
* silently persist unrelated records
* embed credentials or environment-specific secrets

---

## 6. Validation Layer

Generated AI output must not be treated as trustworthy merely because it is syntactically valid.

Validation responsibilities include:

* confirm required fields exist
* confirm field types
* normalize values
* reject malformed structures
* reject incomplete results where completion is required
* preserve controlled failure details
* prevent unvalidated provider output from reaching persistence or the UI

Validation may occur:

* inside a domain intelligence service
* in a dedicated schema or result object
* at the application-service boundary
* before persistence

The exact location depends on responsibility, but validation must be explicit.

---

## 7. Persistence Layer

The persistence layer includes:

* SQLAlchemy models
* repositories or persistence helpers where justified
* database transactions
* migration scripts
* durable intelligence records
* workflow state
* timestamps
* status fields
* audit-relevant metadata

Responsibilities:

* preserve business records
* maintain relationships among records
* commit valid state changes
* roll back failed operations
* support retrieval of current and historical state
* avoid accidental data loss

Persistence should not:

* generate AI content
* render templates
* determine workflow behavior
* hide destructive operations
* create new databases silently when an expected database is missing

SQLite is currently used for local development.

Production readiness will require a controlled PostgreSQL migration and verified backup and recovery procedures.

---

## 8. Domain Model Layer

The Sponsorship Coordinator domain includes connected records such as:

```text
Organization
→ Sponsorship Initiative
→ Sponsorship Asset
→ Sponsorship Intelligence
```

and:

```text
Sponsor Prospect
→ Contact
→ Opportunity
→ Outreach
→ Follow-Up
```

The Opportunity connects a sponsor relationship to a specific sponsorship initiative and, when applicable, to relevant sponsorship assets.

Domain models should represent durable business concepts rather than transient screen state.

Model fields should not be added solely because a template needs a temporary display value.

---

## 9. Infrastructure Layer

Infrastructure concerns include:

* OpenAI API integration
* SMTP delivery
* environment variables
* database configuration
* logging
* deployment configuration
* GitHub Actions
* external service adapters

Responsibilities:

* isolate external systems
* provide configured clients
* expose controlled interfaces
* keep credentials outside source control
* support test substitution or mocking where practical

Provider-specific implementation details should not spread through routes and domain logic.

---

## Platform Capabilities Versus Domain Capabilities

A central architectural rule is distinguishing Marsha AI platform capabilities from Sponsorship Coordinator domain capabilities.

## Marsha AI Platform Capabilities

Likely platform-level responsibilities include:

* AI provider abstraction
* AI Orchestrator patterns
* structured response validation
* generation audit metadata
* reusable application-service result objects
* human review and approval states
* shared workspace action patterns
* authentication
* authorization
* organization and account boundaries
* notifications
* document generation
* shared logging
* deployment configuration
* error handling conventions

These capabilities should become shared platform components only when reuse is demonstrated or their domain-independent nature is clear.

## Sponsorship Coordinator Capabilities

Domain-specific responsibilities include:

* sponsorship initiative analysis
* sponsorship asset recommendations
* sponsor-category recommendations
* sponsorship strategy
* sponsorship research priorities
* sponsor prospect research
* sponsorship outreach
* sponsorship follow-up
* sponsorship opportunity stages
* sponsorship relationship history

These responsibilities belong to the Sponsorship Coordinator even when they use shared platform services.

---

## Service Result Pattern

Application services should return structured results rather than raw tuples, Flask responses, or unhandled exceptions.

A service result may include:

```text
success
status
message
data
errors
warnings
record_id
created_at
```

The exact implementation may use:

* a dataclass
* a typed object
* a validated dictionary
* another explicit result type

The result should allow the route to make a simple decision without reimplementing business logic.

Example conceptual flow:

```text
result = generate_sponsorship_intelligence(...)

if result.success:
    redirect to workspace
else:
    display controlled error
```

The service result pattern should remain consistent across future Marsha AI workflows where practical.

---

## Workspace AI Integration Architecture

The first Workspace AI Integration service is:

```text
services/generate_sponsorship_intelligence.py
```

Its expected responsibilities are:

1. accept the workspace generation request
2. load the relevant organization
3. load the active sponsorship initiative
4. load related sponsorship assets
5. retrieve existing intelligence records when required
6. verify generation preconditions
7. call the existing AI Orchestrator
8. validate the complete intelligence result
9. persist a new intelligence record
10. return a structured UI-ready service result

It should not:

* render a template
* redirect the browser
* flash messages
* access `request.form` directly
* call individual intelligence workers from a route
* expose raw AI provider output
* overwrite existing intelligence without an explicit rule
* create an empty database when the configured database is missing

---

## Dependency Injection

Dependency injection should be used where it improves testability and control.

Useful injection points may include:

* AI Orchestrator
* AI provider client
* persistence function
* clock or timestamp provider
* email sender
* configuration object

Dependency injection should not be introduced merely to satisfy a pattern.

Use it when it enables:

* deterministic tests
* provider substitution
* controlled failure simulation
* separation of infrastructure from business logic

Default production dependencies may still be provided by the service.

---

## Error Handling

Errors should be translated at the correct boundary.

### Domain and AI Services

Should raise or return specific errors for:

* invalid input
* malformed AI output
* provider failure
* missing required context
* unsupported state

### Application Services

Should:

* catch expected domain and infrastructure errors
* roll back failed transactions
* return controlled service results
* preserve diagnostic detail for logs
* avoid exposing secrets or raw provider payloads to users

### Routes

Should:

* display a useful user-facing message
* preserve the workspace state
* avoid duplicating service error interpretation
* return an appropriate HTTP outcome where applicable

Unexpected errors should be logged and handled without corrupting persisted state.

---

## Transaction Boundaries

The application service should own the transaction boundary for a complete use case.

For intelligence generation:

```text
Load Context
→ Generate Intelligence
→ Validate Result
→ Persist Record
→ Commit
```

If validation or persistence fails:

```text
Rollback
→ Return Controlled Failure
```

The application should not commit partial intelligence records unless the workflow explicitly supports drafts or partial states.

---

## Testing Strategy

Testing should follow the architectural layers.

### Domain Service Tests

Test:

* input handling
* output structures
* validation
* provider failures
* edge cases

### Orchestrator Tests

Test:

* service call order
* context passing
* combined results
* partial failure behavior
* dependency substitution

### Application Service Tests

Test:

* record loading
* preconditions
* orchestration invocation
* persistence
* rollback behavior
* structured service results

### Route Tests

Test:

* endpoint access
* request handling
* service invocation
* redirects
* status messages
* authorization when implemented

### Template Tests

Test:

* required rendering paths
* workspace controls
* intelligence display
* safe handling of missing state

### Regression Tests

The full suite must run with:

```powershell
python -m pytest
```

The current baseline is:

```text
70 passing tests
```

A feature is not complete until targeted tests and the full regression suite pass.

---

## Data Safety

Data safety is a first-order architectural requirement.

Before database, schema, migration, or project-location changes:

* confirm Git status
* run the regression suite
* create a full project backup
* create a separate database backup
* verify backup size and location
* perform one controlled change
* verify database integrity
* rerun tests
* verify application behavior

Destructive migrations must not be run without an explicit migration and recovery plan.

The application must not silently replace a populated database with an empty one.

---

## Repository Strategy

The current repository contains the Marsha AI foundations and the Sponsorship Coordinator.

A repository split is not currently required.

Separate repositories may become appropriate when:

* components have independent release cycles
* platform code is consumed by multiple products
* access controls differ
* deployment boundaries differ
* repository size or ownership creates material friction

Until then, one repository reduces operational complexity.

---

## Architectural Decision Rules

Use these rules when evaluating new code:

1. Does this belong to the platform or the Sponsorship Coordinator?
2. Is this a route concern, service concern, orchestration concern, domain concern, persistence concern, or presentation concern?
3. Can the logic be tested without starting Flask?
4. Is AI output validated before persistence?
5. Is the transaction boundary explicit?
6. Does this abstraction solve a demonstrated problem?
7. Does the change preserve current behavior and data?
8. Does the implementation support the shortest safe path to a usable product?
9. Is documentation required?
10. Are targeted and regression tests included?

---

## Current Architectural Priority

The immediate architectural priority is not a broad platform refactor.

It is to complete Workspace AI Integration using the existing architecture and establish a production-quality application-service pattern.

The next implementation target is:

```text
services/generate_sponsorship_intelligence.py
```

That service will become the first concrete bridge among:

* the user workspace
* persisted sponsorship records
* the AI Orchestrator
* structured validation
* durable sponsorship intelligence
