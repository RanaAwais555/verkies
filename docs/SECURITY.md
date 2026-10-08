# VROS Security

Implements §17. Security for the user-submitted-URL crawler is Phase 1 scope; broader hardening and review are Phase 7.

## 1. Authentication and sessions

- **Invite-only team access.** There is no public sign-up. The first admin is created from the command line on the server; after that, admins invite teammates by email-bound, single-use, expiring invite links and can deactivate users at any time (deactivation revokes their sessions).
- Email + password. Passwords hashed with Argon2id; never logged. Minimum length 12, checked against a breached-password list held locally.
- Short-lived access tokens plus rotating refresh tokens in `HttpOnly`, `Secure`, `SameSite=Lax` cookies. Server-side session records so sessions can be revoked.
- Login rate limiting and lockout backoff. Optional TOTP later.
- No paid identity provider.

## 2. Authorisation (RBAC)

Roles: Admin, Founder/Management, Sales Manager, Salesperson, Researcher, Project Manager, Viewer. Permissions are rows (`permissions`, `role_permissions`), not code constants, and are enforced by a FastAPI dependency on every route. Default is deny.

Phase 1 defaults:

| Capability | Admin | Founder | Sales Mgr | Salesperson | Researcher | Project Mgr | Viewer |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Start research | ✓ | ✓ | ✓ | ✓ | ✓ | | |
| Approve / reject prospect | ✓ | ✓ | ✓ | ✓ | | | |
| View accounts and leads | ✓ | ✓ | ✓ | ✓ (own + unassigned) | ✓ | ✓ (clients) | ✓ (permitted) |
| Edit ICP, scoring, catalogue | ✓ | | | | | | |
| View audit log | ✓ | ✓ | ✓ | | | | |
| Manage users | ✓ | | | | | | |

## 3. Crawler and SSRF protection

Users submit URLs and the server fetches them, so this is the highest-risk surface.

1. Allow only `http` and `https`; reject credentials in the URL; limit ports to 80/443 by default.
2. Resolve DNS **before** connecting. Reject loopback, private (RFC 1918), link-local (including `169.254.169.254` cloud metadata), CGNAT, multicast, unspecified and IPv6 equivalents (ULA, link-local, IPv4-mapped).
3. **Pin the connection to the validated IP** (custom resolver/transport) so a second DNS lookup cannot rebind to an internal address.
4. Re-validate every redirect hop with the same rules; cap hops at 5.
5. Cap bytes, time and decompressed size (zip-bomb guard); validate content type.
6. Playwright runs in a throwaway context with downloads, permissions, file URLs and non-HTTP schemes disabled, and the same request-interception IP check applied to every sub-request. The worker has no credentials or internal network routes it does not need; the Compose network isolates it from the database admin interface.
7. Never follow `file:`, `ftp:`, `gopher:` or similar.
8. Respect robots.txt. Never bypass CAPTCHAs, authentication, paywalls or anti-bot measures (§17).

Tests cover each rule, including a rebinding fake resolver and redirect-to-internal.

## 4. Application security

- Input validation with Pydantic on every request; typed responses.
- SQL injection: SQLAlchemy parameterised queries only; no string-built SQL.
- XSS: React escaping by default; crawled text is **untrusted** and always rendered as text. No `dangerouslySetInnerHTML` on crawled content. Strict CSP.
- CSRF: cookie auth with `SameSite` plus a CSRF token on mutating requests.
- Prompt injection: crawled content is data. It is passed to models inside delimited blocks, the model has no tools and no authority, and output is schema-validated and grounded (AI_SPEC.md §3). A page that says "ignore previous instructions" cannot change a score or action.
- Rate limiting on API and auth endpoints (Redis).
- File handling: size and type limits, generated storage keys, no user-controlled paths.
- Production refuses to start with missing or default secrets (ARCHITECTURE.md §9). TLS everywhere via Caddy with HSTS.
- Secrets in environment or a secrets manager; `.env` is git-ignored; encrypted-at-rest for stored provider credentials (Phase 3 mailboxes).
- Dependency pinning and automated vulnerability checks in CI.
- Secure headers on API and frontend.

## 5. Audit

Append-only `audit_log` records user, time, object, action, old value, new value, source and reason for: research approval/rejection, score or config changes, owner changes, stage changes, user and role changes, and imports. Database triggers block `UPDATE`/`DELETE` on audit rows.

## 6. Data protection and compliance

- Data minimisation: store only business contact information that is public and attributable. Each contact stores source URL and collection date (§16).
- Lawful basis note (B2B legitimate interest, UK GDPR / PECR) is recorded for contact data; a deletion/suppression path exists from Phase 1 (`suppressions`) so a person or domain can be removed and never re-added.
- No scraping of LinkedIn and no stored LinkedIn credentials or cookies (§12A).
- Outreach controls (opt-out, suppression, send caps, CAN-SPAM footer) arrive with Phase 3 per §12B and are listed in `ROADMAP.md`.
- Backups, retention and disaster recovery: Phase 7.

## 7. Logging and privacy

Structured logs carry request and run IDs, not passwords, tokens or full page bodies. Evidence text is stored in the database, not logs.

## 8. Review checklist (every PR touching these areas)

New route has a permission check · new fetch path uses the safe `Fetcher` · new rendering of crawled text is escaped · new table has FK, indexes and audit where needed · new config is validated.
