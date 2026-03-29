# Deepagents Migration Plan

## Goal

Migrate DevMate's execution layer from the current custom LangChain planning/generation flow to `deepagents`, while preserving the existing API and UI. The migration is focused on closing the delivery gap around direct codebase operations:

- real file editing and writing
- multi-file changes
- file deletion
- command/script execution
- clearer LangSmith traces for filesystem actions
- official-style `.skills/` consumption through `deepagents`

## Scope

Keep:
- Web API and current frontend UI
- MCP + Tavily search
- local RAG knowledge base
- session persistence
- Docker deployment
- LangSmith configuration

Replace or converge:
- `planning_agent.py`
- `project_generator.py`
- runtime execution path in `agent_runtime.py`
- current custom skill consumption path in the main agent flow

## Phases

### Phase 1: Minimal deepagents runtime

- add `deepagents_runtime.py`
- connect model configuration
- use deepagents filesystem backend
- expose a unified `handle_prompt()` entry
- keep classic runtime available and make API swappable

Acceptance:
- `/api/chat` can switch to `deepagents`
- the agent can write real files
- LangSmith trace shows deepagents-driven execution

### Phase 2: Plug in MCP and RAG

- wrap `search_web` as a deepagents tool
- wrap `search_knowledge_base` as a deepagents tool
- refine the system prompt so the agent uses search only when needed

Acceptance:
- a single task can mix search and file operations
- trace shows both search and filesystem activity

### Phase 3: Move skills consumption to deepagents

- point deepagents at `.skills/`
- reduce reliance on the current custom runtime skill search path
- keep frontend skill upload, but change backend consumption to deepagents-first

Acceptance:
- the agent can load and use `.skills/<name>/SKILL.md` through deepagents

### Phase 4: Add delete and command execution

- add explicit `delete_file` support
- add explicit `run_command` support
- expose these actions more clearly in trace and UI

Acceptance:
- the agent can edit, delete, and execute within the workspace
- the UI can show those actions clearly while the task is running

## Current Progress

- [x] Define migration target and boundaries
- [x] Research deepagents official capabilities
- [x] Add deepagents dependency to the project
- [x] Land the first `deepagents` runtime skeleton
- [x] Allow `/api/chat` and `/api/chat/stream` to switch runtime mode
- [x] Verify minimal deepagents end-to-end execution
- [x] Connect MCP web search and local RAG into the deepagents runtime
- [x] Surface deepagents file/search activity into streaming UI events
- [x] Add explicit `delete_file` support
- [x] Add explicit `run_command` support
- [x] Switch skill consumption to deepagents-native skill sources
- [ ] Expose richer runtime/action detail in the frontend UI
- [ ] Validate file deletion and command execution with a real interactive flow

## Next Focus

1. Deepagents-native skills loading and verification
2. clearer UI rendering for runtime/tool activity
3. end-to-end proof that edit/delete/run-command all work through the same agent path
