# Marsha AI — Sponsorship Coordinator

> **Current Development Stage:** Workspace AI Integration
> **Reference Implementation:** Sponsorship Coordinator
> **Regression Status:** 70 automated tests passing

Marsha AI is a workflow-based artificial intelligence platform designed to execute structured business processes through specialized AI employees.

The Sponsorship Coordinator is the first reference implementation built on the Marsha AI platform. It helps nonprofit organizations and sponsorship-driven businesses plan sponsorship initiatives, identify sponsorship assets, generate strategic intelligence, research prospective sponsors, manage outreach, coordinate follow-up, and maintain sponsorship opportunities through a structured workspace.

This application is not intended to function as a general-purpose chatbot.

It is an AI-assisted operating system for sponsorship work.

---

## Platform Vision

Marsha AI is being developed as a reusable platform for specialized AI employees that complete business workflows rather than simply answer isolated questions.

The platform is intended to provide shared capabilities such as:

* AI intelligence generation
* AI orchestration
* workflow execution
* structured persistence
* human review and approval
* workspace integration
* document generation
* reusable application services
* auditable business records

The Sponsorship Coordinator serves as the first production reference implementation for these platform capabilities.

Future Marsha AI employees may include:

* Client Intake & Delivery Coordinator
* Proposal Coordinator
* Grant Coordinator
* Marketing Coordinator
* additional workflow-specific AI employees

---

## Sponsorship Coordinator

The Sponsorship Coordinator supports the sponsorship lifecycle from organizational preparation through opportunity management.

Its intended workflow is:

1. Organization onboarding
2. Organization profile development
3. Sponsorship initiative definition
4. Sponsorship asset identification
5. Sponsor-category recommendation
6. Sponsorship strategy development
7. Prospect research
8. Decision-maker identification
9. Outreach generation
10. Message quality review
11. Delivery and activity recording
12. Follow-up generation and scheduling
13. Opportunity pipeline management
14. Long-term sponsorship relationship development

---

## Current System Status

The following foundational packages are complete:

* Sponsorship workflow engine
* Organization onboarding
* Organization analysis
* Sponsorship asset analysis
* Sponsor-category recommendations
* Research-priority generation
* Sponsorship strategy generation
* Sponsorship Intelligence Engine
* AI Orchestrator
* Sponsorship intelligence persistence
* Contact research workflow
* Opportunity pipeline
* Outreach generation
* Message Quality Review Worker
* Test and live email delivery paths
* Follow-up generation and regeneration
* Follow-up quality review
* Follow-up scheduling and completion
* Automated regression testing
* GitHub Actions validation
* Engineering documentation

Current development is focused on:

> **Workspace AI Integration**

The objective is to make generated sponsorship intelligence directly accessible, reviewable, regenerable, and persistent within the user workspace.

---

## Architecture

The application follows a service-oriented architecture with separation among:

* Flask routes
* application services
* AI intelligence services
* AI orchestration
* persistence
* SQLAlchemy models
* templates
* tests
* engineering documentation

Business logic should not be placed directly in Flask routes when it can be represented as a reusable and testable service.

AI model calls should remain behind defined service and orchestration boundaries.

See:

```text
docs/ENGINEERING_GUIDE.md
```

for the formal platform and application boundaries.

---

## Major Capabilities

### Organization Intelligence

* Organization onboarding
* Organization profile capture
* Mission and audience analysis
* Organizational-strength analysis
* Sponsorship-readiness analysis
* Research-priority generation

### Sponsorship Intelligence

* Sponsorship asset recommendations
* Sponsor-category recommendations
* Sponsorship strategy generation
* Coordinated intelligence generation
* Structured output validation
* Intelligence persistence
* Historical intelligence records

### Prospect Research

* Contact Research Worker
* Decision-maker identification
* Email-route support
* Phone-route support
* Contact-form support
* Research confidence and source tracking

### Outreach

* AI-generated outreach
* Subject-line generation
* Message Quality Review Worker
* Test email delivery
* Live email delivery
* Delivery-recipient management
* Outreach-channel management

### Follow-Up

* Follow-up generation
* Follow-up regeneration
* AI quality review
* Test follow-up delivery
* Live follow-up delivery
* Automatic scheduling
* Manual completion
* Follow-up history

### Opportunity Pipeline

* Sponsor prospect records
* Contact records
* Opportunity records
* Opportunity stages
* Follow-up dates
* activity notes
* delivery records
* sponsorship relationship history

---

## Technology Stack

* Python
* Flask
* SQLAlchemy
* SQLite for local development
* Bootstrap
* OpenAI API
* Gmail SMTP
* Pytest
* Git
* GitHub
* GitHub Actions

A production database and deployment configuration will be established as part of production-readiness work.

---

## Repository Structure

The repository currently contains the Sponsorship Coordinator reference implementation and shared Marsha AI foundations.

```text
MarshaAI/
├── .github/
├── docs/
├── instance/
├── services/
├── static/
├── templates/
├── tests/
├── app.py
├── README.md
├── ROADMAP.md
├── requirements.txt
└── .env.example
```

The architecture will continue to evolve incrementally as additional Marsha AI platform boundaries become necessary.

The codebase should not be reorganized speculatively. Structural changes must be justified by an active feature or an identified architectural constraint.

---

## Local Installation

Clone the repository:

```bash
git clone https://github.com/MarshaKDesigns-Dev/sponsorship-coordinator-mvp.git
cd sponsorship-coordinator-mvp
```

Create a virtual environment:

```bash
python -m venv venv
```

Activate it on Windows:

```powershell
.\venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

---

## Environment Configuration

Copy:

```text
.env.example
```

to:

```text
.env
```

Configure the required environment variables, including:

* OpenAI API credentials
* Gmail SMTP credentials
* sender information
* `TEST_MODE`
* `TEST_EMAIL`
* application secrets
* database configuration, when applicable

Never commit `.env` or production credentials to Git.

---

## Run the Application

With the virtual environment activated:

```powershell
python app.py
```

Default local address:

```text
http://127.0.0.1:5000
```

---

## Run the Test Suite

Use Python to invoke Pytest so the repository root is included correctly in the import path:

```powershell
python -m pytest
```

Current regression baseline:

```text
70 passed
```

The regression count may increase as new functionality is added. A feature is not considered complete until its targeted tests and the full regression suite pass.

---

## Engineering Workflow

All development follows this workflow:

```text
Feature Branch
→ Build
→ Compile
→ Targeted Tests
→ Full Regression
→ Documentation
→ Commit
→ Push
→ Pull Request
→ Merge
→ Delete Branch
```

Engineering rules:

* Do not commit feature work directly to `main`.
* Keep routes thin.
* Place reusable business logic in services.
* Keep AI calls behind testable boundaries.
* Use dependency injection where it materially improves testability.
* Build complete vertical feature packages whenever practical.
* Preserve backward compatibility unless a deliberate migration is approved.
* Do not alter production or user data without a verified backup and migration plan.
* Update documentation when architecture or workflow behavior changes.
* Run the full regression suite before committing and before merging.

---

## Documentation

Primary project documentation includes:

```text
README.md
ROADMAP.md
docs/ENGINEERING_GUIDE.md
docs/CHANGELOG.md
docs/MILESTONES.md
```

Documentation should distinguish clearly among:

* completed capabilities
* active development
* planned work
* architectural proposals
* ideas that have not been approved for implementation

---

## Product Principles

Marsha AI is being built according to the following principles:

* AI should support a defined business workflow.
* Software should adapt to the operating needs of the business.
* Human review should remain available at consequential decision points.
* AI output should be structured, reviewable, and persistent.
* Business records should not disappear when an AI interaction ends.
* Shared platform capabilities should be reusable across AI employees.
* Domain-specific behavior should remain distinguishable from platform behavior.
* New abstractions should be introduced only when they solve a demonstrated problem.
* The shortest safe path to a usable and sellable product takes priority over speculative complexity.

---

## Roadmap

The active roadmap is maintained in:

```text
ROADMAP.md
```

The current development package is:

```text
Workspace AI Integration
```

The first planned application service is:

```text
services/generate_sponsorship_intelligence.py
```

This service will coordinate loading workspace data, invoking the existing AI Orchestrator, validating its structured results, persisting generated intelligence, and returning a UI-ready response without placing business logic in Flask routes.

---

## Ownership

Marsha AI and the Sponsorship Coordinator are products of Marsha K Designs.

Copyright © Marsha K Designs.

All rights reserved.
