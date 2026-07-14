# Marsha AI Roadmap

## Purpose

This roadmap defines the planned development path for the Marsha AI platform and its first reference implementation, the Sponsorship Coordinator.

It separates completed work, active development, planned work, and future concepts so the project does not confuse implemented capabilities with ideas that have not yet been approved.

---

## Platform Direction

Marsha AI is being developed as a workflow-based artificial intelligence platform.

Its purpose is to support specialized AI employees that execute structured business processes through reusable platform services, domain-specific workflows, persistence, human review, and auditable records.

The Sponsorship Coordinator is the first reference implementation.

The immediate priority is not to build multiple AI employees at once. The immediate priority is to complete one usable, production-ready vertical product and establish the architectural patterns that future employees can reuse.

---

## Current Reference Implementation

### Marsha AI — Sponsorship Coordinator

The Sponsorship Coordinator supports organizations through the sponsorship lifecycle:

```text
Organization Setup
→ Initiative Definition
→ Asset Identification
→ Sponsor Strategy
→ Prospect Research
→ Outreach
→ Follow-Up
→ Opportunity Management
→ Relationship Development
```

---

## Completed Foundation

The following work is complete and validated.

### Engineering Foundation

* Git repository established
* feature-branch workflow established
* pull-request workflow established
* GitHub Actions validation established
* regression testing established
* engineering documentation established
* local project moved to the Marsha AI development workspace
* clean `main` baseline maintained

### Sponsorship Workflow Engine

* prospect records
* contact research
* decision-maker identification
* opportunity records
* opportunity stages
* outreach generation
* subject generation
* delivery-recipient management
* outreach-channel management
* test and live email paths
* message quality review
* follow-up generation
* follow-up regeneration
* follow-up quality review
* scheduling
* completion tracking
* activity notes

### Organization and Sponsorship Intelligence

* organization onboarding
* organization profile persistence
* organization analysis
* sponsorship asset recommendations
* sponsor-category recommendations
* research-priority generation
* sponsorship strategy generation
* Sponsorship Intelligence Engine
* AI Orchestrator
* structured intelligence validation
* sponsorship intelligence persistence
* automated persistence tests

### Quality Baseline

Current full regression baseline:

```text
70 passing tests
```

---

## Active Development

## Workspace AI Integration

The current feature is Workspace AI Integration.

### Objective

Bring AI-generated sponsorship intelligence directly into the application workspace so the user can generate, review, regenerate, save, and use strategic intelligence without leaving the workflow.

### Service-First Implementation

The first application service is:

```text
services/generate_sponsorship_intelligence.py
```

The service should:

* accept a workspace generation request
* load the organization profile
* load the active sponsorship initiative
* load relevant sponsorship assets
* retrieve existing intelligence records when required
* invoke the AI Orchestrator
* validate structured intelligence
* persist new intelligence
* return a UI-ready structured result
* remain independent of template rendering
* remain independent of Flask route concerns

### Planned Workspace Integration Package

* application service
* service result object
* error handling
* route integration
* workspace action
* loading and completion states
* intelligence display
* regeneration support
* persistence confirmation
* targeted service tests
* route tests
* template tests
* regression validation
* documentation updates

### Completion Criteria

Workspace AI Integration is complete when:

* intelligence can be generated from the workspace
* generated data is persisted
* existing records remain intact
* failures return controlled, actionable responses
* routes contain minimal business logic
* targeted tests pass
* the full regression suite passes
* documentation reflects the implemented behavior

---

## Next Production Milestones

### Workspace Intelligence Review

Planned capabilities:

* display current intelligence clearly
* distinguish generated, reviewed, and approved states
* allow users to inspect source context
* support controlled regeneration
* preserve prior versions where required
* record generation timestamps and status

### Sponsorship Initiative Workspace

Planned capabilities:

* initiative summary
* organization context
* sponsorship goals
* target audience
* event or campaign details
* asset summary
* strategic recommendations
* research priorities
* sponsor categories
* next recommended action

### Production Readiness

Planned work:

* PostgreSQL migration
* production configuration
* secure secret handling
* authentication review
* authorization review
* database migration strategy
* structured application logging
* error monitoring
* email safety controls
* production deployment
* backup and recovery procedure
* privacy review
* pilot data-isolation review

### Pilot Program

Planned pilot scope:

* recruit 3–5 nonprofit or sponsorship-driven organizations
* onboard each pilot organization
* observe real workflow usage
* document points of confusion
* measure time saved
* identify missing workflow steps
* review AI output quality
* validate pricing assumptions
* prioritize only launch-critical improvements

---

## Launch Milestone

The first production release should provide a complete and usable Sponsorship Coordinator workflow.

Launch readiness requires:

* stable onboarding
* stable workspace
* persistent sponsorship intelligence
* usable prospect research
* reviewed outreach
* follow-up management
* opportunity pipeline
* production database
* secure deployment
* customer data separation
* documented operating process
* pilot validation
* acceptable regression coverage

The launch target should not be delayed for speculative platform features that are not required by the Sponsorship Coordinator customer workflow.

---

## Platform Extraction Strategy

Shared Marsha AI platform capabilities should be extracted only when the Sponsorship Coordinator proves that they are reusable.

Likely shared capabilities include:

* AI Orchestrator
* model-provider configuration
* structured AI response validation
* generation audit records
* application-service result patterns
* workspace action patterns
* human review and approval states
* reusable document generation
* authentication
* authorization
* account and organization boundaries
* notifications
* shared deployment configuration

The project should avoid premature extraction.

A component should become a platform service when:

1. it is used by more than one domain workflow, or
2. its domain-independent responsibility is already clear, and
3. extracting it reduces duplication or risk without slowing delivery materially.

---

## Planned AI Employees

These are planned product directions, not active builds.

### Client Intake & Delivery Coordinator

Proposed workflow:

```text
Inquiry
→ Qualification
→ Discovery
→ Scope Definition
→ Missing-Information Collection
→ Proposal Preparation
→ Approval
→ Agreement and Payment Readiness
→ Onboarding
→ Kickoff Preparation
→ Delivery Milestones
→ Client Follow-Up
```

Strategic purpose:

Demonstrate that the Marsha AI architecture can support a revenue-producing service-delivery workflow beyond sponsorship management.

### Proposal Coordinator

Potential responsibilities:

* opportunity intake
* requirement analysis
* proposal structure
* missing-information detection
* draft generation
* review coordination
* version control
* submission readiness

### Grant Coordinator

Potential responsibilities:

* grant-opportunity tracking
* eligibility review
* requirement extraction
* document collection
* application planning
* draft coordination
* deadline management
* submission readiness
* reporting obligations

### Marketing Coordinator

Potential responsibilities:

* campaign planning
* audience definition
* content workflow
* campaign assets
* publishing schedule
* performance review
* follow-up actions

No additional AI employee should enter active development until the Sponsorship Coordinator reaches a defined production or pilot milestone.

---

## Deferred Work

The following items are intentionally deferred unless they become necessary for launch:

* broad multi-tenant platform redesign
* mobile application
* separate microservices
* event-driven infrastructure
* complex plugin architecture
* generalized workflow builder
* marketplace
* customer-created AI employees
* extensive theming
* advanced analytics
* native desktop application
* repository splitting
* speculative abstractions

Deferred does not mean rejected. It means the work is not currently justified by the shortest safe path to a usable and sellable product.

---

## Decision Rules

Development priorities should follow these rules:

1. Protect customer and development data.
2. Preserve passing behavior unless a deliberate migration is approved.
3. Complete active vertical features before opening new workstreams.
4. Prefer services over route-level business logic.
5. Prefer reusable patterns over duplication when reuse is demonstrated.
6. Do not generalize prematurely.
7. Build for the immediate customer workflow first.
8. Treat testing and documentation as part of feature completion.
9. Separate completed work from planned work.
10. Prioritize production readiness over feature volume.

---

## Current Next Action

The next implementation step is:

```text
Build services/generate_sponsorship_intelligence.py
```

This work begins after the Marsha AI platform identity documentation package is reviewed, tested, committed, pushed, merged, and the documentation branch is deleted.

