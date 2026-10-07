# Coach AI

Personal multisport coach, with a later commercial path. Python/FastAPI backend,
React/TypeScript frontend. Run commands from the repository root.

- Read README.md, docs/architecture.md and docs/backlog.md before implementation.
- Keep real user data, credentials, tokens and exports out of git. No personal medical
  history in fixtures, example profiles or prompts checked into this public repository.
- This milestone is loopback-only and single-user. Do not expose a listener to the LAN
  or internet until LOCAL-02 is implemented and verified.
- Preserve user ownership in queries and records. Never treat missing health data as zero.
- Never log auth callback URLs, tokens, passwords or provider error bodies.
- Garmin is a replaceable unofficial adapter. Do not bypass MFA or access controls.
- ChatGPT uses official authorization and public Responses endpoints only. No paid API
  fallback without explicit user configuration. Preserve terminal streaming validation.
- Do not claim an integration is validated with real accounts based on mocked tests.
- RAG, Excel import and workout logging are backlog work, not implemented features.
- Match each ticket to acceptance checks; avoid unrelated changes.

Checks: `ruff check backend`, `ruff format --check backend`, `pytest backend/tests`,
`npm --prefix frontend run build` (activate .venv first).
