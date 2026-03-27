# Internal Backend Guidelines

This note captures the baseline backend conventions used by DevMate generated services.

## Service Layout

- Prefer `src/<package_name>/main.py` as the application entry point.
- Keep framework setup, route registration, and configuration loading in separate modules when the project grows beyond a single file.
- Use environment-aware configuration loaders instead of hardcoded secrets.

## API Design

- Use clear request and response models.
- Add health endpoints early for local verification and container checks.
- Keep external provider integrations behind adapters so they can be mocked in tests.

## Testing

- Add unit tests for configuration parsing and provider clients.
- Add one integration-style test for the runtime path that joins retrieval and planning.
- Log provider failures with enough detail to debug retries and fallback behavior.