# Repository Guidelines

Welcome to the **Issuu User Scraper** project! This document captures the
expectations for contributors and serves as a quick reference when making
changes.

## Repository Overview
- `main.py` contains the core scraping logic, download utilities, and helper
  functions.
- `tests/` holds the automated test suite. Additions and regressions should be
  covered by tests whenever possible.

## Coding Standards
- Follow standard Python style conventions (PEP 8) and include type hints for
  new or modified functions when practical.
- Prefer explicit imports over wildcard imports to keep dependencies obvious.
- Keep functions short and focused. Extract helpers if logic becomes complex.
- Avoid introducing try/except blocks around import statements.
- When modifying concurrent code, add comments or tests explaining assumptions
  about ordering, chunking, and progress reporting.

## Testing Expectations
- Run `pytest -q` before submitting changes. New functionality should include
  unit tests or integration tests demonstrating the expected behaviour.
- Tests should aim to reproduce real-world workflows. When mocking concurrency
  or I/O, instrument the mocks so the tests verify observable side effects
  (e.g., progress updates, scheduling order) rather than only verifying that a
  method was called.

## Git & Pull Requests
- Keep commits focused. Each commit should represent a logical change and have
  a descriptive message written in the imperative mood (e.g., "Improve progress
  reporting test").
- Ensure the working tree is clean and the test suite passes before committing.
- Pull request descriptions should summarize the key changes and list the tests
  that were executed (including the full command invocations).

## Documentation & Comments
- Update README.md or inline documentation when behaviour changes or new
  configuration steps are introduced.
- Use docstrings or explanatory comments when reasoning about tricky logic,
  concurrency, or error handling.

Thank you for contributing and keeping the test suite robust!
