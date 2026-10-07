# Coach AI

Personal multisport coach, with a later commercial path. Python/FastAPI backend,
React/TypeScript frontend. Run commands from the repository root.

- Read README.md, docs/architecture.md and docs/backlog.md before implementation.
- Keep real user data, credentials, tokens and exports out of git. No personal medical
  history in fixtures, example profiles or prompts checked into this public repository.
- Single-user only. Production requires HTTPS ingress, an exact public origin, a strong
  environment access key and persistent storage. Use coach.server for Railway; one replica
  and one worker. Do not assume local ChatGPT OAuth is supported on the hosted app.
- Preserve user ownership in queries and records. Never treat missing health data as zero.
- Never log auth callback URLs, tokens, passwords or provider error bodies.
- Garmin is a replaceable unofficial adapter. Do not bypass MFA or access controls.
- ChatGPT uses official authorization and public Responses endpoints only. No paid API
  fallback without explicit user configuration. Preserve terminal streaming validation.
- Do not claim an integration is validated with real accounts based on mocked tests.
- Vector RAG, conversation imports, Excel import and workout logging remain backlog work.
  Editable memory, derived summaries and owner-scoped lexical retrieval are implemented.
- Match each ticket to acceptance checks; avoid unrelated changes.

Checks: `ruff check backend`, `ruff format --check backend`, `pytest backend/tests`,
`npm --prefix frontend run build` (activate .venv first).
