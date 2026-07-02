---
name: python-backend-standards
description: Python 后端工程规范与代码审查准则。Use when building, refactoring, or reviewing Python backend services, especially Flask/FastAPI/Django-style projects, API-Service-Repository layered architecture, Model/Schema separation, configuration, logging, exception handling, database migrations, tests, security, async jobs, and backend maintainability work.
---

# Python Backend Standards

Use this skill to implement or review Python backend code with engineering-first constraints.

## Core Posture

Prefer maintainable system structure over quick feature patches.

Keep code layered, testable, observable, and recoverable. Avoid script-style backend development unless the repository is explicitly a script/tooling project.

## Layering Rules

Use the repository's existing architecture first. When adding new backend code, preserve these responsibilities:

- API / Controller: receive request, validate or parse input, call service, return response.
- Service: own business logic, process orchestration, policy decisions, and external service coordination.
- Repository / CRUD / DAO: own SQL, ORM queries, persistence details, and transaction boundaries when local patterns put transactions there.
- Model: represent database tables and ORM state.
- Schema / DTO: represent request payloads, response payloads, validation, and serialization.
- Core / Config: centralize settings, logging, security helpers, and shared infrastructure.

Do not let API handlers directly manipulate database state unless the existing codebase intentionally has no repository layer and the change is too small to justify introducing one.

## Hard Constraints

Check for these before editing or approving code:

- API layer must not contain meaningful business logic.
- Service layer should not depend on Flask/FastAPI request or response objects.
- Service code should be unit-testable without a live web server.
- SQL and ORM query logic should be centralized in repository, CRUD, or data-access modules when that pattern exists.
- Do not return ORM models directly from public APIs unless the existing framework explicitly serializes them safely.
- Do not use schema or DTO objects as database models.
- Do not hardcode database URLs, API keys, tokens, credentials, or environment-specific config.
- Do not use `print` for backend diagnostics; use the project logger.
- Do not introduce global mutable state for request-specific or task-specific data unless the repository already has a controlled runtime registry.
- Do not swallow exceptions silently.
- Do not replace useful error summaries with unstructured tracebacks in user-visible fields.

## Implementation Workflow

1. Inspect the local architecture before choosing a pattern.
2. Identify which layer owns the requested behavior.
3. Keep the API layer thin.
4. Put reusable business decisions in services.
5. Put persistence details in repository, CRUD, or data-access modules when present.
6. Keep models and schemas separate.
7. Add or update focused tests for service logic, edge cases, and error paths.
8. Run the narrowest relevant test command first, then broaden if the change touches shared behavior.

## API Layer Guidance

API handlers should:

- Parse request data.
- Invoke schema validation or equivalent local validation.
- Call one service function or method.
- Convert service results into the existing response format.

Avoid:

- Complex branching.
- SQL or ORM calls.
- Long loops.
- Cross-resource orchestration.
- Framework-specific objects leaking into service APIs.

## Service Layer Guidance

Services should:

- Own core business logic.
- Coordinate repositories, external clients, queues, and domain helpers.
- Expose plain Python interfaces that are easy to unit test.
- Accept explicit dependencies where the project already uses dependency injection.

Services should not:

- Read directly from Flask `request`.
- Return Flask `Response` objects.
- Depend on route decorators or web middleware.
- Hide database or network failures without preserving enough context for recovery.

## Repository / CRUD Guidance

Repositories should:

- Encapsulate SQL or ORM queries.
- Expose intention-revealing methods.
- Keep query filters close to the database instead of post-filtering large in-memory collections.
- Preserve transaction patterns already used in the repository.

Avoid scattering ORM query logic through routes and services.

## Model / Schema Separation

Use models for persistence and schemas or DTOs for boundaries.

When returning API data:

- Convert models into response schemas or dictionaries using existing serializers.
- Avoid leaking internal fields, secrets, relationship internals, or lazy-loading surprises.
- Keep request schemas separate from response schemas when semantics differ.

## Configuration

Use the project's config manager or settings layer.

Do not add new direct environment-variable reads in business code when a central config system exists.

Sensitive values must stay out of source code, logs, templates, test fixtures, and generated artifacts.

## Logging

Use the existing logging module or project logger.

Good backend logs include:

- Event or action name.
- Relevant entity IDs.
- Status or outcome.
- Error class and message when failing.
- Enough context to debug without exposing secrets.

Do not log tokens, API keys, passwords, cookies, authorization headers, private sheet URLs, or raw user secrets.

## Exception Handling

Prefer typed or domain exceptions for expected business failures.

When re-raising inside an `except` block, use bare `raise` to preserve traceback.

When wrapping exceptions, preserve the original cause:

```python
raise BusinessException("User not found") from exc
```

Use centralized error handling where the framework supports it.

## Testing

Prioritize service-level tests because they validate business behavior without the web stack.

Cover:

- Core success path.
- Boundary inputs.
- Expected business errors.
- External dependency failures.
- Database-free or network-free unit tests where practical.
- API tests separately from business tests.

Use mocks or fakes for network, Redis, queues, external APIs, and databases when the test's goal is business behavior.

## Database Changes

Use the repository's migration mechanism when available.

Do not manually mutate schema in application code unless the project already has startup schema repair logic and the change explicitly belongs there.

For queries over many records, push time windows, statuses, and ownership filters into SQL or ORM filters.

## REST and Endpoint Design

Prefer resource-oriented routes:

```text
GET    /resources
POST   /resources
GET    /resources/{id}
PUT    /resources/{id}
DELETE /resources/{id}
```

Use plural resource names and consistent casing conventions from the existing app.

## Async, Concurrency, and Long-Running Work

For IO-heavy operations, prefer async clients or background tasks if the project architecture supports them.

For CPU-heavy or long-running jobs, prefer task queues or workers instead of blocking request threads.

When modifying long-running task systems, explicitly check:

- Thread or task lifecycle.
- Cancellation behavior.
- Retry and recovery behavior.
- Database state versus in-memory state.
- Resource occupancy and release.
- Logging and user-visible error summaries.

## Security Checklist

Before finishing backend changes, check:

- Authentication required unless endpoint is intentionally public.
- Authorization checks match the resource owner or role model.
- Sensitive fields are not returned by default.
- Secrets are not logged.
- User input is validated before use.
- SQL or ORM access is parameterized through safe APIs.
- File paths and uploads are constrained if relevant.

## Review Checklist

When reviewing Python backend code, report issues in this order:

1. Layering violations that create hidden coupling.
2. Data corruption, transaction, or persistence risks.
3. Security or secret-handling problems.
4. Error handling that breaks recovery or debuggability.
5. Missing tests for core logic, edge cases, or failures.
6. Maintainability issues such as oversized functions or mixed responsibilities.
