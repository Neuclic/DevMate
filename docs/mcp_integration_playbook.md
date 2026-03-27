# MCP Integration Playbook

This playbook describes the preferred pattern for adding or extending MCP tools in DevMate.

## Tool Design

- Name tools after the user-facing action, such as `search_web`.
- Return structured data that can be transformed into concise planning context.
- Separate transport errors from provider errors so retries stay predictable.

## Runtime Integration

- Run a lightweight health check before high-value MCP calls.
- Treat MCP lookup as optional context, not as a hard dependency for every prompt.
- Log when the runtime chooses to skip or downgrade web search.

## Testing

- Unit test response parsing separately from network transport.
- Add one end-to-end smoke path that proves the client and server agree on the tool contract.
- Keep the MCP server transport on Streamable HTTP to match the project requirement.