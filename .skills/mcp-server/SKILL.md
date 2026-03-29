---
name: mcp-server
description: Design or refine an MCP server with clear tool contracts, health checks, and stable transport behavior.
keywords:
  - mcp
  - server
  - tool
  - transport
  - healthcheck
allowed-tools: "search_local_knowledge"
metadata:
  origin: anthropics-skills-inspired
  demo-fit: medium
---

# MCP Server

## Summary

Use this skill when the task involves exposing a tool through MCP and keeping the transport predictable for agent use.

## Steps

1. Define the tool schema around one clear user-facing action.
2. Add an explicit health endpoint before treating the server as production-ready.
3. Separate provider failures, transport failures, and parsing failures in logs.
4. Keep the tool response structured so the planner can consume it without brittle parsing.
