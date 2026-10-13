# VROS Security

Implements §17. Security for the user-submitted-URL crawler is Phase 1 scope; the broader review was slice 7.3 (§9 lists what it found and what changed).

## 1. Authentication and sessions

- **Invite-only team access.** There is no public sign-up. The first admin is created on the server with `python -m app.cli create-admin`. After that, admins invite teammates: each invite is bound to one email address, single-use, expires after 7 days, and carries the roles the teammate will get. A new invite to the same address replaces the pending one. The invite link puts the token in the URL fragment (`/invite#token=…`), which browsers never send to servers, so it does not appear in proxy or access logs. Until outreach email exists (Phase 3) the admin copies the link to the teammate. Admins can deactivate a user at any time, which ends all their sessions. VROS refuses to remove or deactivate the last active admin.
- Email + password. Passwords hashed with Argon2id (rehashed on login when parameters change); never logged. Policy: 12-256 characters, not trivially repetitive, not containing the email name, and **not in a known data breach** (slice 7.3): every new password (first admin, invite, password change) is checked against the Pwned Passwords range API by k-anonymity, so only the first 5 characters of its SHA-1 hash leave the server and the match is made locally. If the service cannot be reached the password is accepted and a warning logged. `VROS_BREACHED_PASSWORD_CHECK=false` switches it off.
- **Sessions are server-side.** The browser holds a random 256-bit token in an `HttpOnly`, `SameSite=Lax` cookie (`Secure` and `__Host-` prefixed over HTTPS); the database stores only its HMAC (keyed with `VROS_SECRET_KEY`). A session ends after 12 hours idle or 14 days in total (configurable), on logout, on deactivation, or when the user changes password (other sessions only). There are no JWTs, so revocation is immediate.
- **CSRF:** double-submit token. A second, readable cookie holds a random token that the frontend echoes in `X-CSRF-Token` on every state-changing request; the API rejects a mismatch. `SameSite=Lax` is a second layer.
- **Lockout:** after 5 consecutive wrong passwords the account is locked for 15 minutes (configurable). Every response to a failed sign-in is the same generic message, and an unknown email still costs a full hash, so attackers cannot tell which accounts exist. Every failure, including attempts during a lockout, is audited.
- **Rate limits** (slice 7.3, Redis, fixed windows): sign-in 20 attempts per client address per 10 minutes, so one address cannot spray passwords across many accounts; invite links 20 per address per 10 minutes; password changes 10 per person per hour; starting research 120 per person per hour; and any API request 1,200 per person per minute as a brake on runaway scripts. Over a limit the API answers 429 with `Retry-After`. If Redis is down requests are allowed and a warning logged. The client address is the one Caddy saw: uvicorn trusts `X-Forwarded-For` (`FORWARDED_ALLOW_IPS` in the API image; only Caddy and the frontend can reach the API, and Caddy replaces any value a client sends), so a forged header cannot dodge the limit.
- Optional TOTP later. No paid identity provider.

## 2. Authorisation (RBAC)

Roles: Admin, Founder/Management, Sales Manager, Salesperson, Researcher, Project Manager, Viewer. Permissions are rows (`permissions`, `role_permissions`), not code constants, and are enforced by a FastAPI dependency on every route. Default is deny.

Permissions by role, as the migrations seed them (reviewed in slice 7.4):

| Permission | Admin | Founder | Sales Mgr | Salesperson | Researcher | Project Mgr | Viewer |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `accounts.read`: see every account | ✓ | ✓ | ✓ | | ✓ | ✓ | ✓ |
| `accounts.read_own`: see own and unassigned accounts | ✓ | | | ✓ | | | |
| `records.write`: create and change records | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | |
| `research.run`: start research | ✓ | ✓ | ✓ | ✓ | ✓ | | |
| `prospects.review`: approve or reject prospects | ✓ | ✓ | ✓ | ✓ | | | |
| `accounts.merge`: merge duplicates | ✓ | ✓ | ✓ | | | | |
| `outreach.manage`: templates and sequences | ✓ | ✓ | ✓ | | | | |
| `reports.team`: team dashboards | ✓ | ✓ | ✓ | | | | |
| `audit.read`: audit log | ✓ | ✓ | ✓ | | | | |
| `config.manage`: ICP, scoring, catalogue, alert rules | ✓ | | | | | | |
| `users.manage`: invite and manage users | ✓ | | | | | | |

**Seeing is not changing (slice 7.4).** Most routes that create or change records (people, activities, tasks, deals, projects, documents and so on) are open to anyone who can see the account. Until 7.4 that meant a Viewer could change them. Now a change (any method but GET) that a person may make only because of `accounts.read` or `accounts.read_own` also needs `records.write`, which every role but Viewer has; the API answers 403 "Your role can view records but not change them". The rule lives in one place (`require_permission` in `app/auth/deps.py`), so a new route gets it without doing anything. Routes that change only the person's own things are marked `personal`: watching an account and their saved views. The app labels a read-only person "View only" and hides what the API would refuse them: every control that adds, edits, moves, completes, uploads, removes or sends is left out (`useCanChange` in `frontend/lib/hooks.ts`), forms such as a deal's or a project's details show their fields disabled, and the Mailbox tab is gone. Watching, saved views, notifications and their own password stay. Hiding is a convenience; the API rule above is what enforces it. `e2e/phase7-viewer.spec.ts` signs in as an invited Viewer and checks each screen.

**Every route is tested (slice 7.4).** `tests/integration/test_access_control.py` reads every route from the app's own OpenAPI schema and checks that each one refuses a stranger (401) and a signed-in person with no role (403), that every change refuses a Viewer (403), and that every route scoped to an account answers for someone else's account exactly as for one that does not exist. The routes that are meant to be different are listed in that file by name: public (health, sign-in, invite links), open to anyone signed in (their own session, password and notifications; the team list, services and reference projects every screen needs; which providers are on) and personal. A new route fails the test until it either refuses these people or is added to a list on purpose.

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
- XSS: React escaping by default; crawled text is **untrusted** and always rendered as text. No `dangerouslySetInnerHTML` on crawled content. Content-Security-Policy on every page (slice 7.3, set by Caddy): everything from the site's own origin only, no outside scripts, frames, objects or form targets, no `eval`, and no framing of VROS. Scripts and styles allow `'unsafe-inline'` because Next.js inlines its hydration data; see §9.
- CSRF: see §1 (double-submit token plus `SameSite=Lax`).
- Prompt injection: crawled content is data. It is passed to models inside delimited blocks, the model has no tools and no authority, and output is schema-validated and grounded (AI_SPEC.md §3). A page that says "ignore previous instructions" cannot change a score or action.
- Rate limiting on sign-in, invites, password changes, research and the API as a whole (§1).
- File handling: size and type limits, generated storage keys, no user-controlled paths.
- Production refuses to start with missing or default secrets (ARCHITECTURE.md §9). TLS everywhere via Caddy with HSTS.
- Secrets in environment or a secrets manager; `.env` is git-ignored; stored mailbox passwords are encrypted at rest (Fernet, with a key derived from `VROS_SECRET_KEY` by HKDF) and never returned by the API; changing the secret key means each person reconnects their mailbox (slice 3.4).
- Dependencies are pinned (`uv.lock`, `package-lock.json`) and CI audits them on every pull request: `pip-audit` for Python and `npm audit` for the production npm dependencies; a known high-severity vulnerability fails the build.
- Secure headers (Caddy): HSTS, `nosniff`, `X-Frame-Options: DENY`, a strict referrer policy, a permissions policy denying camera, microphone, location, payment and USB, `Cross-Origin-Opener-Policy` and `Cross-Origin-Resource-Policy: same-origin`, and the CSP above. API responses add `Content-Security-Policy: default-src 'none'` and `Cache-Control: no-store`.

### Imports and exports

- **CSV import:**
  - The browser sends the file's text in a JSON body. No file is stored on disk, and the server never executes or evaluates it.
  - Limits are enforced: 2 MB, 5,000 rows, 50 columns, 2,000 characters per cell.
  - Rows are only data until a person starts research. Research then goes through the same SSRF-safe fetcher and URL validation as any other run.
- **Export:**
  - It includes only the accounts the user may see.
  - CSV cells starting with `=`, `+`, `-`, `@`, tab or carriage return are prefixed with `'` so spreadsheets do not run them as formulas.
  - Every export is audited (`accounts.exported`, with format and count).

### Uploaded documents (slice 4.4)

- Only PDF, Word, Excel and PowerPoint (`.docx`, `.xlsx`, `.pptx`), PNG, JPEG, WebP, plain text, Markdown and CSV are accepted. The type is decided from the file's own bytes (signatures, the parts inside an Office ZIP, UTF-8 for text) and must match the file's extension; HTML, SVG, scripts, programs and macro-enabled Office files are refused.
- The size limit (`VROS_DOCUMENT_MAX_BYTES`, 10 MB) is enforced while the body is read, and Caddy limits request bodies to 10MB as well.
- Files are stored under the SHA-256 of their bytes, never under a name a person typed; the hash is checked again on every download, so a file changed on disk is not served.
- Downloads are always attachments with the recorded type, `X-Content-Type-Options: nosniff`, a sandboxing `Content-Security-Policy` and `Cache-Control: no-store`. VROS never renders an uploaded file.
- A document is visible only to people who can see its account. Removing one hides it and is audited; the bytes stay in storage and the nightly backup (`ops/backup/backup.sh` archives `storage/documents`).

## 5. Audit

Append-only `audit_log` records user, time, object, action, old value, new value, source and reason for: research approval/rejection, score or config changes, owner changes, stage changes, user and role changes, and imports. Database triggers block `UPDATE`/`DELETE` on audit rows.

## 6. Data protection and compliance

- Data minimisation: store only business contact information that is public and attributable. Each contact stores source URL and collection date (§16).
- Lawful basis note (B2B legitimate interest, UK GDPR / PECR) is recorded for contact data; a deletion/suppression path exists from Phase 1 (`suppressions`) so a person or domain can be removed and never re-added.
- No scraping of LinkedIn and no stored LinkedIn credentials or cookies (§12A).
- Outreach controls (opt-out, suppression, send caps, CAN-SPAM footer) arrive with Phase 3 per §12B and are listed in `ROADMAP.md`.
- Backups (slice 7.2): off-site copies are encrypted with age to a public key whose private half is kept offline by the owner, so the server and the storage provider cannot read them; the upload is refused when no key is set. Local copies are kept 14 days and off-site copies 30. A weekly drill proves the latest dump restores. Restores need the private key, which is copied to the server only for the restore and deleted after.

## 7. Logging and privacy

Structured logs carry request and run IDs, not passwords, tokens or full page bodies. Evidence text is stored in the database, not logs.

Metrics (slice 7.1) are counts only: labels are HTTP methods, route templates, status codes, task names and states, never names, emails, URLs or IDs. `/metrics` answers only internal hostnames (a request under the public hostname gets 404) and Caddy never forwards it. Prometheus and Grafana listen on 127.0.0.1 only; Grafana has sign-up and anonymous access off and will not start with its default password.

## 8. Review checklist (every PR touching these areas)

New route has a permission check · new fetch path uses the safe `Fetcher` · new rendering of crawled text is escaped · new table has FK, indexes and audit where needed · new config is validated.

## 9. Security review (slice 7.3)

Each section above was compared with the code. What was found, and what was done:

| # | Finding | Severity | Outcome |
| --- | --- | --- | --- |
| 1 | §4 promised rate limiting on API and auth endpoints; only the per-account lockout existed. One address could spray passwords across every account, and anyone could lock a colleague out on purpose (the lockout still does that, but now only 20 tries per address per 10 minutes) | High | Fixed: Redis rate limits (§1) |
| 2 | Reported in 7.3 as "behind Caddy every request appeared to come from Caddy". **Corrected in 7.5:** that was wrong. The API image already set `FORWARDED_ALLOW_IPS="*"`, so uvicorn already used the address Caddy forwarded; the extra flag added in 7.3 was redundant and was removed. What 7.3 did verify still stands: through Caddy a forged `X-Forwarded-For` is ignored and the real address is used | None | No change needed |
| 3 | §4 promised a strict CSP; the app sent none (only document downloads had one) | Medium | Fixed: CSP and cross-origin headers in Caddy; 11 pages, navigation and writes checked with zero violations |
| 4 | §4 promised automated vulnerability checks in CI; CI ran `npm ci --no-audit` and no Python audit | Medium | Fixed: `pip-audit` and `npm audit` in CI. At the review: Python 0 known vulnerabilities, production npm 0 |
| 5 | No breached-password check (tracked since Phase 1) | Medium | Fixed: k-anonymity range check (§1) |
| 6 | The dev-only lint toolchain (`eslint-config-next` → `fast-glob` → `micromatch` → `braces` 3.0.3) has a high-severity advisory (GHSA-vfj7-8cjw-p6xm, stack exhaustion from crafted glob patterns) with no fixed release | Low | Accepted: never shipped in the image and only ever given our own lint patterns; CI audits production dependencies. Revisit when `braces` publishes a fix |
| 7 | The CSP allows `'unsafe-inline'` scripts: Next.js inlines hydration data, and nonces would force every page to render per request | Low | Accepted: all other script sources are blocked, `eval` is not allowed, and crawled or user text is always rendered as text, never as HTML |

Checked and unchanged: sessions (server-side, HMAC-stored tokens, idle and absolute expiry, revoked on logout, deactivation and password change), CSRF (double-submit plus `SameSite=Lax`), the SSRF guard and its tests (§3), uploads (§4: type from bytes, size enforced while reading, hash-named storage, attachment-only downloads), secrets (production refuses defaults; mailbox passwords encrypted), metrics and backups exposure (§6, §7).
