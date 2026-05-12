# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DeerFlow is an open-source **super agent harness** that orchestrates sub-agents, memory, and sandboxes — powered by extensible skills. Think of it as a framework for building and running capable AI agents, not just a chat app.

**Key high-level concepts**:

1. **Harness/App split** — The backend is two layers with a strict dependency direction. `deerflow-harness` (`packages/harness/deerflow/`) is the publishable agent framework; `app/` is the FastAPI Gateway + IM channels. **deerflow must never import from app.** This is enforced by CI (`tests/test_harness_boundary.py`).
2. **Lead agent + middleware chain** — A single lead agent runs per thread, wrapped in 18 middleware components (tool handling, memory, sandbox lifecycle, security, summarization, etc.). The chain is assembled in strict append order.
3. **Sandbox abstraction** — Abstract `Sandbox` interface (`execute_command`, `read_file`, `write_file`, `list_dir`) with local filesystem and Docker-based implementations. Agent sees virtual paths like `/mnt/user-data/{workspace,uploads,outputs}` mapped to physical `.deer-flow/` directories.
4. **Skills as a system** — Skills are directories with `SKILL.md` (YAML frontmatter). They can be injected into the agent system prompt, and their content is accessible to the agent at container-like paths.
5. **IM Channels** — Integration layer bridging Feishu, Slack, Telegram, DingTalk, Discord, WeChat to the LangGraph agent via `langgraph-sdk` HTTP client.

## Commands

### Root Level (full application)

```bash
make help         # List all commands
make check        # Check system requirements
make install      # Install all dependencies (frontend pnpm + backend uv sync + pre-commit)
make dev          # Start all services (Gateway + Frontend + Nginx) with hot-reloading
make start        # Start all services in production mode
make stop         # Stop all services
make dev-daemon   # Start dev services in background
make up           # Docker production build and start (localhost:2026)
make down         # Stop Docker production containers
make docker-start # Docker development mode
make doctor       # Check config and system requirements
make config       # Generate local config from example
```

### Backend Only (`cd backend`)

```bash
make install   # uv sync
make dev       # uvicorn app.gateway.app:app --reload (port 8001)
make gateway   # uvicorn app.gateway.app:app (port 8001, no reload)
make test      # Run all tests: uv run pytest tests/ -v
make lint      # ruff check + ruff format --check
make format    # ruff check --fix + ruff format
```

Run a single test file:
```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_client.py -v
```

### Frontend Only (`cd frontend`)

```bash
pnpm dev       # Dev server with Turbopack (localhost:3000)
pnpm build     # Production build
pnpm test      # Vitest unit tests
pnpm test:e2e  # Playwright E2E tests (Chromium)
pnpm check     # ESLint + TypeScript type check
pnpm lint      # ESLint only
pnpm typecheck # tsc --noEmit
```

Unit tests live under `tests/unit/` mirroring `src/` layout. E2E tests live under `tests/e2e/` and mock backend APIs.

### CI Workflows (`.github/workflows/`)

- `backend-unit-tests.yml` — Backend pytest suite
- `frontend-unit-tests.yml` — Frontend Vitest suite
- `e2e-tests.yml` — Playwright E2E tests
- `lint-check.yml` — Lint and formatting checks

## Architecture

### Service Layout

```
Port 2026 (nginx) → /api/langgraph/* → Gateway port 8001 (embedded LangGraph runtime, URL rewritten to /api/*)
                   → /api/*           → Gateway port 8001 (REST APIs)
                   → /*               → Frontend port 3000 (Next.js)
```

### Backend Packages

```
backend/
├── packages/harness/           # deerflow-harness (publishable agent framework)
│   └── deerflow/
│       ├── agents/             # Lead agent factory, middleware chain, ThreadState, memory
│       │   ├── lead_agent/     # make_lead_agent(), system prompt templating
│       │   ├── middlewares/    # 18 middleware components in strict order
│       │   ├── memory/         # Async memory extraction, debounce queue, file storage
│       │   └── thread_state.py # ThreadState extending AgentState
│       ├── sandbox/            # Sandbox interface + LocalSandboxProvider + tools
│       ├── subagents/          # Subagent delegation (general-purpose, bash agents)
│       ├── tools/              # Tool loading, built-in tools (present_files, ask_clarification, view_image, setup_agent, update_agent)
│       ├── mcp/                # MCP client integration (MultiServerMCPClient, OAuth, caching)
│       ├── models/             # Model factory with thinking/vision suppor + vLLM provider
│       ├── skills/             # Skills discovery, loading, parsing
│       ├── config/             # Configuration models for all subsystems
│       ├── community/          # Community tools (tavily, jina, firecrawl, image_search, aio_sandbox)
│       ├── guardrails/         # Pluggable guardrail middleware (AllowlistProvider, OAP)
│       ├── reflection/         # Dynamic module loading (resolve_variable, resolve_class)
│       └── client.py           # DeerFlowClient - in-process access without HTTP
├── app/                       # Application layer (import: app.*)
│   ├── gateway/               # FastAPI app, routers, auth, middleware
│   │   ├── routers/           # models, mcp, memory, skills, uploads, threads, artifacts, agents, feedback, runs, suggestions, channels, auth
│   │   └── auth/              # Authentication (local provider, JWT, credential file)
│   └── channels/              # IM platform integrations (Feishu, Slack, Telegram, DingTalk, Discord, WeChat)
└── tests/                     # ~140 test files
```

### Configuration

Two files in project root:

- **`config.yaml`** (from `config.example.yaml`) — LLM models, tools, sandbox, skills, memory, subagents, summarization, channels, auth, etc. Config values starting with `$` resolve as env vars.
- **`extensions_config.json`** — MCP servers and skill enable states. Can be updated at runtime via Gateway API.

### The Middleware Chain (Lead Agent)

Assembled in strict append order in `packages/harness/deerflow/agents/lead_agent/agent.py`:

1. ThreadData → 2. Uploads → 3. Sandbox → 4. DanglingToolCall → 5. LLMErrorHandling → 6. Guardrail → 7. SandboxAudit → 8. ToolErrorHandling → 9. Summarization → 10. TodoList → 11. TokenUsage → 12. Title → 13. Memory → 14. ViewImage → 15. DeferredToolFilter → 16. SubagentLimit → 17. LoopDetection → 18. Clarification

### Memory System

Per-user isolated file-based memory at `{base_dir}/users/{user_id}/memory.json`. Async pipeline: MemoryMiddleware queues conversations → debounce timer → background LLM call extracts facts/context → atomic file write. Facts are injected into system prompt on next interaction.

### IM Channel Message Flow

Channel impl → `MessageBus.publish_inbound()` → `ChannelManager._dispatch_loop()` → create/find thread via langgraph-sdk → `runs.stream()` or `runs.wait()` → `MessageBus.publish_outbound()` → channel replies.

## Important Development Rules

1. **Harness → App import firewall**: `packages/harness/deerflow/` must never import from `app.*`. Enforced by CI.
2. **Tests required**: Every feature or bug fix must include tests. Follow `tests/test_<feature>.py` naming.
3. **No hardcoded secrets in config.yaml**: Use `$ENV_VAR` syntax for API keys.
4. **Configuration upgrade**: When changing `config.example.yaml` schema, bump `config_version` field.

## Key Utilities

- `resolve_variable("module.path:VariableName")` — Dynamic import from dotted path
- `resolve_class(path, BaseClass)` — Dynamic class import with validation
- `get_effective_user_id()` — Resolves user ID from runtime context (falls back to `"default"` in no-auth mode)
- `cn()` — Tailwind class merging utility (frontend)

## Development

- Python 3.12+, Node.js 22+, pnpm 10.26.2+
- Backend uses `uv` for dependency management (workspace with `packages/harness`)
- Frontend uses `pnpm` with workspace support
- Ruff for Python linting/formatting (line length: 240)
- ESLint for frontend, Vitest for unit tests, Playwright for E2E
- Pre-commit hooks installed via `make install`
