---
name: Package Docker Delivery
description: Use this skill when the task needs a containerized handoff with a predictable startup command and runtime verification.
keywords:
  - docker
  - compose
  - container
  - deployment
  - handoff
  - runtime
tools:
  - search_local_knowledge
---

# Package Docker Delivery

## Summary

Use this skill when the task needs a containerized handoff with a predictable startup command and runtime verification.

## Steps

1. Define the runtime command and required environment variables before writing the Dockerfile.
2. Keep the image focused on runtime dependencies and expose a simple health path when possible.
3. Add a docker compose service that mirrors the expected local startup flow.
4. Document the required secrets and one smoke-test command in the README.