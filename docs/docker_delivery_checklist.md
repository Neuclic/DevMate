# Docker Delivery Checklist

Use this checklist when packaging DevMate or a generated project for handoff.

## Container Expectations

- The image should start with one command and avoid interactive setup.
- The container should include only the runtime dependencies required by the app.
- `docker compose up` should be the main verification command.

## Delivery Notes

- Mount writable directories when the app needs to persist vector indexes or caches.
- Expose health endpoints so other services can detect readiness.
- Keep secrets outside the committed repository and inject them at runtime.

## Verification

- Run one smoke test inside the container after the app starts.
- Confirm that logs show configuration source, server URL, and retrieval mode.
- Document the required environment variables in the README.