# VROS Security

Implements §17. Security for the user-submitted-URL crawler is Phase 1 scope; broader hardening and review are Phase 7.

## 1. Authentication and sessions

- **Invite-only team access.** There is no public sign-up. The first admin is created on the server with `python -m app.cli create-admin`. After that, admins invite teammates: each invite is bound to one email address, single-use, expires after 7 days, and carries the roles the teammate will get. A new invite to the same address replaces the pending one. The invite link puts the token in the URL fragment (`/invite#token=…`), which browsers never send to servers, so it does not appear in proxy or access logs. Until outreach email exists (Phase 3) the admin copies the link to the teammate. Admins can deactivate a user at any time, which ends all their sessions. VROS refuses to remove or deactivate the last active admin.
- Email + password. Passwords hashed with Argon2id (rehashed on login when parameters change); never logged. Policy: 12-256 characters, not trivially repetitive, not containing the email name. A breached-password check is not implemented; it would need either a bundled list or an outside service and is tracked for Phase 7.
- **Sessions are server-side.** The browser holds a random 256-bit token in an `HttpOnly`, `SameSite=Lax` cookie (`Secure` and `__Host-` prefixed over HTTPS); the database stores only its HMAC (keyed with `VROS_SECRET_KEY`). A session ends after 12 hours idle or 14 days in total (configurable), on logout, on deactivation, or when the user changes password (other sessions only). There are no JWTs, so revocation is immediate.
- **CSRF:** double-submit token. A second, readable cookie holds a random token that the frontend echoes in `X-CSRF-Token` on every state-changing request; the API rejects a mismatch. `SameSite=Lax` is a second layer.
- **Lockout:** after 5 consecutive wrong passwords the account is locked for 15 minutes (configurable). Every response to a failed sign-in is the same generic message, and an unknown email still costs a full hash, so attackers cannot tell which accounts exist. Every failure, including attempts during a lockout, is audited.
- Optional TOTP later. No paid identity provider.

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

As implemented (slice 1.6):
- **Accounts:** `accounts.read` sees every account. `accounts.read_own` (Salesperson) sees accounts it owns or that have no owner, with their tasks, opportunities and timeline. Another person's account answers 404, not 403, so its existence is not revealed.
- **Research runs:** reviewers (`prospects.review`) and `accounts.read` see every run, because the review queue holds everyone's research. Only the person who started a run, or someone with `accounts.read`, may cancel or retry it.
- **Approval:** a reviewer can only attach research to an account they can see.
- **Known limit:** a possible-duplicate warning names the matching accounts even when the reviewer cannot open them. This lets the reviewer avoid creating a duplicate.

## 3. Crawler and SSRF protection

Users submit URLs and the server fetches them, so this is the highest-risk surface.

1. Allow only `http` and `https`; reject credentials in the URL; limit ports to 80/443 by default.
2. Resolve DNS **before** connecting. Reject loopback, private (RFC 1918), link-local (including `169.254.169.254` cloud metadata), CGNAT, multicast, unspecified and IPv6 equivalents (ULA, link-local, IPv4-mapped).
3. **Pin the connection to the validated IP** (custom resolver/transport) so a second DNS lookup cannot rebind to an internal address.
4. Re-validate every redirect hop with the same rules; cap hops at 5.
5. Cap bytes, time and decompressed size (zip-bomb guard); validate content type.
6. **Chromium never touches the network itself.** Every request a rendered page makes is intercepted: non-GET requests, images, media, fonts and WebSockets are refused, and everything else is fetched by the same guarded fetcher (rules 1-5) and handed back to the browser. Chromium is also launched against a dead proxy (`127.0.0.1:9`), so a request that escaped interception fails instead of reaching the network; this backstop caught a real gap during development (Chromium does not re-route the target of a redirect it is handed), which is now handled by serving the final page directly. Service workers and downloads are blocked, background networking is disabled, and subrequests and bytes are capped per page. Playwright is installed only in the worker image.
7. Never follow `file:`, `ftp:`, `gopher:` or similar.
8. Respect robots.txt. Never bypass CAPTCHAs, authentication, paywalls or anti-bot measures (§17).

9. Error responses (4xx/5xx) are recorded by status only; their bodies are never downloaded. `Set-Cookie` headers from crawled sites are never stored.
10. `VROS_FETCH_PRIVATE_ALLOWLIST` (CIDRs the fetcher may reach) and `VROS_FETCH_HOST_OVERRIDES` (fixed DNS answers, `host=address`) exist for tests and local development only. Production refuses to start if either is set. An overridden answer still passes the address policy, so it reaches a private address only together with the allowlist.

Tests cover each rule: every private, loopback, link-local, CGNAT, multicast, reserved and IPv4-mapped/6to4 range; mixed public/private DNS answers; DNS rebinding (the second answer is never used); redirects to internal addresses; redirect loops; size limits measured after decompression (zip bombs); slow-drip servers (hard per-request deadline); a real TLS server proving pinning still verifies the certificate hostname; and a hostile page whose JavaScript tries to reach cloud metadata, POST data and open a WebSocket.

## 4. Application security

- Input validation with Pydantic on every request; typed responses.
- SQL injection: SQLAlchemy parameterised queries only; no string-built SQL.
- XSS: React escaping by default; crawled text is **untrusted** and always rendered as text. No `dangerouslySetInnerHTML` on crawled content. Strict CSP.
- CSRF: see §1 (double-submit token plus `SameSite=Lax`).
- Prompt injection: crawled content is data. It is passed to models inside delimited blocks, the model has no tools and no authority, and output is schema-validated and grounded (AI_SPEC.md §3). A page that says "ignore previous instructions" cannot change a score or action.
- Rate limiting on API and auth endpoints (Redis).
- File handling: size and type limits, generated storage keys, no user-controlled paths.
- Production refuses to start with missing or default secrets (ARCHITECTURE.md §9). TLS everywhere via Caddy with HSTS.
- Secrets in environment or a secrets manager; `.env` is git-ignored; encrypted-at-rest for stored provider credentials (Phase 3 mailboxes).
- Dependency pinning and automated vulnerability checks in CI.
- Secure headers on API and frontend.

### Imports and exports

- **CSV import:**
  - The browser sends the file's text in a JSON body. No file is stored on disk, and the server never executes or evaluates it.
  - Limits are enforced: 2 MB, 5,000 rows, 50 columns, 2,000 characters per cell.
  - Rows are only data until a person starts research. Research then goes through the same SSRF-safe fetcher and URL validation as any other run.
- **Export:**
  - It includes only the accounts the user may see.
  - CSV cells starting with `=`, `+`, `-`, `@`, tab or carriage return are prefixed with `'` so spreadsheets do not run them as formulas.
  - Every export is audited (`accounts.exported`, with format and count).

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
