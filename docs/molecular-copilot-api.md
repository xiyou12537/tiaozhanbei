# P1.3A Molecular Copilot API

`/api/assistant` is an authenticated, molecular-product-only assistant API. It
does not mount or depend on legacy `/api/chat` or legacy material-screening
knowledge.

## Safety boundary

- All model secrets are server environment variables. Client requests cannot
  configure a provider or submit a model key.
- The model receives JSON Schema definitions for the only supported tools:
  `platform_capabilities`, `select_task`,
  `get_current_user_result`, `draft_molecule_workflow`,
  `draft_molecular_study`, and `draft_molecular_bond_scan`.
- Tool reads are scoped to the authenticated user. JWTs are resolved by the
  API and are never passed to the model adapter.
- No HTTP, shell, SQL, or file tool exists.
- Every execution remains `logical_virtual_qpu`; `is_real_qpu` is always
  `false`.

## New-user guidance

The server-side Copilot policy starts with a plain-language answer, then tells
the user what they can do next; technical detail is added only when useful.
Copilot follows the user's primary language: Chinese messages, including safety
refusals, prompt-injection responses, missing-data notices, and unavailable-tool
notices, receive clear, natural Chinese. For a first-time user or a task-selection
request, Copilot recommends one task from the stated goal, explains the
recommendation, uses suitable defaults, and asks at most one genuinely necessary
follow-up question. For beginner Molecular Study guidance, the user supplies only the
molecule and genuinely necessary geometry; Copilot uses the recommended default
architecture set and does not require architecture, partition, connectivity, topology,
or routing choices. This newcomer rule does not remove professional users' ability to
discuss or adjust architecture, partition, connectivity, routing, active space, and
VQE parameters.

- **Molecule Workflow** calculates one fixed molecule's energy, quality status,
  and simulated execution result.
- **Molecular Study** compares engineering behavior for one molecular problem
  across partition, connectivity, and routing choices.
- **LiH Bond Scan** compares energy at discrete bond-length points to identify
  low-energy regions worth further review. It is not continuous geometry
  optimization and does not claim an exact equilibrium bond length.

Result explanations remain evidence-bound: `completed` means execution
finished, not automatically that scientific validation passed. `needs_review`,
`partial`, `failed`, and legacy results with missing fields are explicitly
called out. Copilot requests the existing compact `get_current_user_result`
summary before making a result-specific statement and says when data is absent;
it does not invent energy, minima, chemical-accuracy, FCI, SWAP,
communication, or deployment conclusions. Every response retains a concise
`logical_virtual_qpu`, `is_real_qpu=false`, non-real-QPU boundary.

### Controlled real-model acceptance budget

An isolated acceptance harness can share one process-local
`AssistantModelCallBudget` and wrap its real adapter with
`BudgetedAssistantModelAdapter`. The wrapper claims an atomic allowance before
each `AssistantModelAdapter.stream` turn, including a tool-result continuation;
multiple tool calls returned in one provider response still consume one request.
When the allowance is exhausted it returns the local
`assistant_model_request_budget_exhausted` error without calling the provider.
The counter is an explicit harness control, not an automatic retry, a credential
store, or a change to user-facing task confirmation.

## Lifecycle

1. `POST /api/assistant/sessions` creates a user-owned session.
2. `POST /api/assistant/sessions/{session_id}/messages/stream` accepts a
   plain user message. The server-side model orchestrator may select only a
   defined structured tool, validates its arguments, and enforces the
   configured per-message tool-call limit. Optional `ui_tool_name` and
   `ui_tool_arguments` are explicitly controlled UI shortcuts; they are not
   model tool calls and are never required for ordinary chat.
3. The SSE event contract is incremental: `tool_started`, `tool_completed`,
   one or more `message_delta`, `message_completed`, `error`, and terminal
   `done`. A model timeout or failure after a delta is represented by `error`
   then `done`; callers must not treat a completed message as token streaming.
   When a provider emits tool calls, the server always runs a continuation
   model turn after tool execution. Its context contains the provider's
   original `assistant.tool_calls` envelope followed by matching `tool`
   messages whose `tool_call_id` values are the same provider-issued IDs;
   internal audit execution IDs are never sent as provider tool-call IDs.
   Controlled `ui_tool_name` shortcuts instead contribute an ordinary
   assistant-context result, never an orphan `tool` message.
   Draft tools create only a `pending_confirmation` audit record.
4. The client repeats `confirmation_id`, `tool_name`, and
   `parameter_summary` to `POST /api/assistant/sessions/{session_id}/tool-confirmations`.
   The server validates user/session/tool/summary/expiry. A repeated valid
   confirmation returns the prior result and never creates a second task.
5. `GET /api/assistant/sessions/{session_id}` restores persisted messages and
   the controlled-tool audit.

## Model configuration

The default provider is disabled and returns stable
`assistant_model_unconfigured` (503). To use an OpenAI-compatible endpoint,
set server-side `MOLECULAR_ASSISTANT_MODEL_PROVIDER=openai_compatible`,
`MOLECULAR_ASSISTANT_MODEL_BASE_URL`, `MOLECULAR_ASSISTANT_MODEL_API_KEY`,
`MOLECULAR_ASSISTANT_MODEL_NAME`, and optionally
`MOLECULAR_ASSISTANT_MODEL_TIMEOUT_SECONDS`,
`MOLECULAR_ASSISTANT_MODEL_MAX_OUTPUT_TOKENS`, and
`MOLECULAR_ASSISTANT_MAX_TOOL_CALLS`,
`MOLECULAR_ASSISTANT_CONTEXT_MAX_MESSAGES`, and
`MOLECULAR_ASSISTANT_CONTEXT_MAX_INPUT_TOKENS`.

### Context window and deterministic input budget

`MOLECULAR_ASSISTANT_CONTEXT_MAX_MESSAGES` is an optional server-side integer
setting for the recent-message window. It defaults to `40`; invalid values fall
back to that default, and the effective range is `4` through `100` messages.
The model receives the most recent messages in chronological order. Session
restoration continues to return at most the most recent 40 persisted messages
in chronological order; no older message is deleted or overwritten.

`MOLECULAR_ASSISTANT_CONTEXT_MAX_INPUT_TOKENS` is an optional server-side
integer context allowance. It defaults to `12000`; invalid values fall back to
that default, and the effective range is `2048` through `65536`. It uses a
conservative deterministic estimate based on serialized UTF-8 byte length,
not provider billing-token accounting. The estimate includes the system prompt,
all six tool schemas, selected history, the current user message, current-turn
assistant tool-call envelopes and tool results, plus reserved
`max_output_tokens` space.

When the estimate exceeds the allowance, the server removes oldest complete
user-started turns first and keeps the newest context. It never cuts a message
string in the middle, never starts the selected history with an orphaned
assistant message, and never removes the current user message. Current-turn
`assistant.tool_calls` and their matching tool results are retained as one
atomic continuation sequence. If the system prompt, tool schemas, current
message, required continuation sequence, and output reserve cannot fit, the
SSE stream returns `assistant_context_too_large` followed by `done` without
calling the model provider.

`MOLECULAR_ASSISTANT_CONFIRMATION_RECOVERY_SECONDS` is an optional
server-side integer setting for concurrent confirmation recovery. It defaults
to `2`; invalid values fall back to that default, and the effective value is
bounded to `0` through `30` seconds. When two requests confirm the same draft,
the request that does not atomically claim the pending confirmation waits for
this short interval for the first executor to persist its confirmation result.
If the record is still `executing` when the interval ends, the existing
recovery path runs using the durable Assistant execution ID and the domain
idempotency ID. This setting is not the draft confirmation TTL: it does not
change `confirmation_expires_at`, and it does not disable user authorization,
parameter-summary matching, or idempotency validation. Setting it to `0`
disables only the short wait; safe recovery and idempotency protection remain
in effect.

Model timeouts and rate limits return stable `assistant_model_timeout` (504) and
`assistant_model_rate_limited` (429) errors.

### DeepSeek official API (non-thinking mode)

The explicit `deepseek` provider uses the official OpenAI-compatible endpoint
with the following server-side configuration. `deepseek-v4-flash` is the
recommended default; `deepseek-v4-pro` is also supported. The legacy
`deepseek-chat`, `deepseek-reasoner`, and unknown model names are rejected with
the stable `assistant_model_unsupported_model` configuration error.

```text
MOLECULAR_ASSISTANT_MODEL_PROVIDER=deepseek
MOLECULAR_ASSISTANT_MODEL_BASE_URL=https://api.deepseek.com
MOLECULAR_ASSISTANT_MODEL_NAME=deepseek-v4-flash
MOLECULAR_ASSISTANT_MODEL_API_KEY=<server-side-secret-placeholder>
```

When `provider=deepseek`, the base URL and model default to
`https://api.deepseek.com` and `deepseek-v4-flash`. Every request includes
`thinking={"type":"disabled"}`. The first version does not support DeepSeek
thinking mode and does not parse, store, display, or log `reasoning_content`.

The system prompt, user/assistant messages, permitted tool schemas, and compact
task-result summaries are sent to the configured third-party model service.
JWTs, API keys, full QASM, full routed execution plans, and VQE iteration
histories are not sent. The API key is read only from the server environment;
it is never accepted from clients, persisted, logged, returned, or exposed to
the frontend.

For an isolated local integration environment, set `LEGACY_DATABASE_URL` to a
separate file-backed SQLite URL before starting the backend. This changes only
the compatibility/product SQLite binding for that process; it does not run the
explicit Assistant migration.

## Persistence migration

`python -m backend.scripts.migrate_molecular_assistant` is an explicit,
backup-first, idempotent SQLite migration. It is not executed at application
startup and must not be run against production without release authorization.
Without those tables, Assistant endpoints return
`assistant_schema_not_ready` (503); `init_db()` never creates Assistant
tables. Confirmed Studies derive deterministic IDs from the durable Assistant
execution ID, so concurrent confirmations and recovery after a task was
created but before its audit result was committed resolve to the same Study.

Read-result tool context is a compact DTO only. It excludes QASM,
`routed_execution_plan`, VQE iteration history, and other bulky execution
artifacts; users retrieve full evidence through the existing task APIs.

`docs/openapi-p13.sha256` freezes the extended P1.3A contract. The P1.2
manifest remains unchanged as its historical release contract.
