# ADR 0003 — Better Auth with session cookies; FastAPI verifies sessions

- Status: accepted (2026-10-30)

## Context
Users are a lab team of 5–30. Login is email + password with admin invites; there is no SSO for
now. FastAPI must authorize every request, including long-lived SSE streams.

## Decision
- **Better Auth 1.7** runs inside the Next.js app (`/api/auth/*`) and owns the `auth` schema in
  Postgres:
  - email/password with a strong hash (argon2id) and its built-in rate limiting;
  - the admin plugin (create, ban and offboard users);
  - the organization plugin (single-use, expiring, email-bound invitations; lab roles).
- **Sessions are httpOnly, SameSite=Lax cookies.** We don't use JWTs: the browser's native
  `EventSource` sends cookies, and revocation is immediate.
- **FastAPI checks each request's cookie** by calling Better Auth's `get-session` endpoint over
  the internal network, caching the result for at most 60 s. State-changing requests also check
  the `Origin` header (CSRF).
- Project roles (`owner`, `researcher`, `viewer`) live in our own `project_members` table and are
  enforced by FastAPI, then re-checked in Temporal Update validators.
- **Bootstrap and offboarding:**
  - The first admin is created from a CLI command, never through a public sign-up.
  - Invite links can be copied when SMTP isn't configured; dev uses Mailpit.
  - Offboarding deletes the user's sessions and their provisioned OpenRouter key.

## Consequences
- The API depends on the `web` service for authentication (both run on one host).
- Alembic must exclude the `auth` schema; Better Auth's own migrations manage it.

## Alternatives considered
- **FastAPI-native JWT auth**: we would hand-build invites, password reset and rate limiting.
- **Keycloak / Authentik**: heavier. Adopt only if university SSO (Entra ID / SAML) becomes a
  requirement.
- **Auth.js**: security fixes only since it joined Better Auth. **Clerk**: hosted only.
