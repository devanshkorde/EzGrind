# EzGrind — Standing Rules

## Stack
Flask + PostgreSQL (psycopg2, hosted on Neon) + vanilla JS. No frameworks, no
build step, no TypeScript, no
Tailwind, no React. Keep it that way unless I explicitly say otherwise.

## Working rules
- Explain the plan before implementing. Wait for my approval.
- Change one concern at a time. Never mix a refactor with a feature.
- Never modify a file you have not read in this session.
- After every change, state: what changed, why, and what could break because of it.
- Never delete or rewrite user data. Schema changes go in numbered migration
  files, never as edits to existing migrations.
- No silent failures. Every fetch gets a .catch(). Every DB call gets error
  handling. Every 4xx/5xx returns JSON, never an HTML error page.
- If a file or behaviour is unclear, ask me. Do not assume.
- Keep functions under ~40 lines. Name things for what they mean, not what they are.
- Comments explain WHY, never WHAT.

## Design tokens (use CSS variables, never hardcoded hex)
```css
--bg: #080808;
--bg-2: #121212;
--surface: #1A1A1A;
--gold: #C9A84C;
--gold-2: #D7B414;
--text: #F5F5F5;
--text-muted: #9A9A9A;
--radius: 16px;
```
Dark theme only. Desktop-first, must work down to 360px.

## API contract
All endpoints under /api. All responses JSON. Success: 2xx with a data payload.
Error: 4xx/5xx with `{"error": {"code": "...", "message": "..."}}`.
Auth failures are always 401 with that shape.
