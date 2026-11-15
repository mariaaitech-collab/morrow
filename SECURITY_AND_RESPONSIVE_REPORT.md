# Security and Responsive Review

**Review date:** 15 November 2026
**Branch:** `security-and-responsive-fixes`

## Executive summary

BrandAura is a React 18 / React Router 6 single-page frontend built with Vite and Tailwind CSS. The Python 3.13 backend uses FastAPI, Pydantic, SQLAlchemy 2 with SQLite for scheduled posts, and Firestore for users, activity, OAuth state, and responder data. APScheduler runs publishing and polling jobs. Social integrations include Meta, LinkedIn, Instagram, and TikTok; uploaded media is served from a public local `/uploads` directory.

The audit found an unauthenticated scheduled-post listing/deletion path in the baseline and two client-trusting billing routes that could grant paid entitlements without payment verification. The current working tree now requires ownership checks on scheduled posts, disables those simulated billing grants, binds social OAuth callbacks to single-use state, rejects mismatched video containers, and adds shared API protections. Existing local edits were present when this audit began and were preserved.

The app has useful responsive foundations: a mobile navigation drawer, fluid workspace columns, scrollable calendar grids, and mobile breakpoints across the shared styles. The drawer now traps keyboard focus and locks background scrolling. Contrast checks pass for all pairs in the project’s contrast script. This review did **not** visually inspect every page at each requested viewport: the browser access service was unavailable. Therefore the app is not certified as overflow-free at every breakpoint.

## Architecture and attack surface

- **Frontend:** React 18, React Router 6, Vite 6.4.6, Tailwind CSS 4, plain CSS/token files. Routes cover public marketing, auth, dashboard, creation, channels, scheduler/calendar, history, profile, responder, and admin pages.
- **Backend:** FastAPI 0.115, Uvicorn, Pydantic 2, Python-JOSE JWT, Passlib bcrypt, SQLAlchemy 2, APScheduler, Firebase Admin/Firestore, and multipart upload support.
- **Persistence:** Firestore is accessed server-side using Application Default Credentials. SQLite stores scheduled posts in `brandora.db`. Social access tokens are persisted in ignored `backend/connected_accounts.json`; uploaded media is kept under `backend/static/uploads` and served publicly.
- **Auth and integrations:** Bearer JWTs are returned to the browser and stored in `localStorage`. Facebook, Instagram, and LinkedIn use OAuth redirects; TikTok uses OAuth state plus PKCE. Webhooks accept platform events and use signature verification. Billing is manual through an admin activation route; no payment provider is configured.
- **Infrastructure/config:** `backend/.env.example` documents configuration; `.env` and local data files are ignored by Git. Firestore rules deny direct client reads and writes. CORS origins are configured from the environment or local app URL.

## Findings and changes

### Critical

No confirmed critical vulnerability was found in the tracked source during this pass. This is a code review, not a penetration test or proof that deployment credentials and cloud settings are safe.

### High

| Finding | Exploit / impact | Change and status |
|---|---|---|
| Client-declared payment success granted plans and tokens. `backend/routers/billing.py:111-125` | Any signed-in user could call `/subscribe` or `/success` and grant themselves paid access without a processor receipt. | Both legacy routes now return `501` until verified checkout exists. Manual activation remains restricted to `require_admin` at `backend/routers/billing.py:82`. |
| OAuth JWT was placed in the callback URL. `frontend/src/pages/Callback.jsx` (callback construction); prior backend handler accepted `access_token` in `backend/routers/social.py` | Browser history, proxy logs, and referrer handling could expose a bearer credential. | The frontend now forwards only OAuth `code` and `state`. Backend connect creates user-bound, single-use state and an HttpOnly callback cookie; the callback consumes and checks both at `backend/routers/social.py:408-442`. |
| Scheduled posts were listable/deletable without sufficient caller ownership checks. `backend/routers/schedule.py:271-285, 682-695` | A caller could enumerate other users’ queued content or delete another user’s pending post. | Listing requires authentication and filters by owner; deletion requires authentication and checks ownership, returning 404 for another user’s record. |
| Built-in JWT signing key could be used outside local development. `backend/config.py:25-35` | If deployed with the public default, an attacker who knows the source could forge sessions. | Startup now refuses the built-in key when `APP_BASE_URL` is not a loopback hostname. Set a unique random `SECRET_KEY` before deployment. |

### Medium

| Finding | Exploit / impact | Change and status |
|---|---|---|
| Upload media type relied partly on filename/client MIME. `backend/routers/content.py:690-700, 734-735` | A crafted upload could be misclassified; malformed video bytes could be stored or passed to a publisher. | Images are decoded and normalized through Pillow. Video uploads now require a matching MP4/MOV `ftyp`, AVI `RIFF/AVI`, or WebM/MKV EBML signature before storage (`backend/media_rules.py:47-58`, `backend/routers/content.py:661-667`). |
| Global request limit is large and checks only `Content-Length`. `backend/security.py:94-120` | The 1.1 GiB cap is needed by current video-upload behavior, but chunked requests without that header are not bounded by this middleware. Large uploads are read into memory in `backend/routers/content.py:734`. | **Open risk:** replacing this with bounded streaming and per-route limits needs a streaming upload path to preserve large-video support. |
| JWT is stored in `localStorage`. `frontend/src/auth.js`, `frontend/src/api/axios.js`, `frontend/src/pages/Login.jsx`, `frontend/src/pages/Register.jsx` | Any successful script injection could steal the bearer token. | **Open design risk:** moving to HttpOnly cookies needs coordinated auth, CSRF, refresh, and deployment changes. No auth-strategy migration was made. |
| Social account tokens are stored in a local JSON file. `backend/routers/social.py:34-85` | Host or backup-file access can expose provider credentials. | File is Git-ignored and account records are owner-scoped in application logic. **Open deployment risk:** use restricted filesystem permissions and encrypted/managed secret storage for production. |
| Per-IP limiters are in-memory and per process. `backend/security.py:32-90` | Limits reset on restart and do not coordinate across multiple workers; key storage grows with distinct client IPs. | API-wide and auth-specific limits are active. **Open scaling risk:** use a shared limiter such as Redis and bound limiter-key retention before multi-worker deployment. |
| React Router advisories remain. `frontend/package.json` (`react-router-dom`) | npm reports two moderate advisories: backslash-based open redirect and SSR hydration constructor injection. The latter does not match this client-only app’s routing mode; all current navigation calls inspected were static internal destinations. | Vite and the CSS parser were updated to patched versions. Router 7 is the npm automatic fix and is a breaking major update, so Router 6 remains pending compatibility review. |
| Developer test override and local reset-token response are configuration-sensitive. `backend/deps.py:32-33, 123-156`; `backend/routers/auth.py:200, 325-329` | The fixed developer identity receives a token/unlimited override; localhost reset responses include a usable reset token. | Reset-token mode now checks the parsed hostname against loopback names only. **Open deployment action:** remove or explicitly gate the developer override before serving real users. |
| Webhook logs retain trimmed raw event payloads for 30 days. `backend/inbound_log.py:20-42` | Payloads may include user-generated content or platform identifiers. | Retention is bounded and logged entries expire; review whether the 30-day period and raw payload access match the product’s privacy policy. |
| Pydantic request models do not globally reject extra fields; validation is endpoint-specific. `backend/models.py` | Unexpected fields may be silently ignored, and there is no shared schema audit proving every route validates query/path/body inputs. Current handlers generally assign explicit fields, reducing mass assignment exposure. | **Open audit item:** add route-by-route validation coverage and `extra="forbid"` only after confirming clients do not rely on ignored fields. |

### Low / defense-in-depth

- `CORS_ORIGINS` now rejects `*` because credentials are enabled (`backend/config.py:61-67`). CORS still allows all methods and headers for the explicitly allowed origins (`backend/main.py:101-108`); narrow these if the API’s method/header inventory is stable.
- Security headers are added to API responses (`backend/security.py:126-150`): `nosniff`, frame denial, referrer and permissions policies, restrictive API CSP, COOP/CORP, and HSTS on HTTPS requests. The frontend host must independently set its own CSP/HSTS and HTTPS redirect policy.
- Rate limits cover login, signup, password-reset requests and submissions, plus a global per-IP limit (`backend/security.py:44-90`). Passwords use Passlib bcrypt; password reset tokens are hashed in Firestore and redeemed transactionally (`backend/routers/auth.py:202-204, 340-390`).
- Firestore rules deny direct client database access (`firestore.rules`). SQLite access uses SQLAlchemy ORM and fixed migration statements; no dynamic SQL injection sink was identified in the reviewed routes.
- No `dangerouslySetInnerHTML`, direct `innerHTML` assignment, or `javascript:` URL sink was found in `frontend/src` during the search pass. React text rendering is used for user-facing values.
- No `.env` file was tracked by Git; only `backend/.env.example` was tracked. A pattern scan of tracked non-env source found no credential literal that was confirmed as a live secret. This does not inspect Git history, cloud secrets, ignored local files, or credentials previously shared elsewhere.

## Responsive and accessibility review

### Changes made

- `frontend/src/components/WorkspaceShell.jsx`: mobile drawer now moves focus inside when opened, traps Tab/Shift+Tab, closes on Escape, restores prior focus, locks body scrolling, exposes dialog semantics, and reports mobile `aria-expanded` accurately.
- `frontend/scripts/check-contrast.mjs`: computes the sidebar hover overlay and active color using the values used by the stylesheet; the contrast check now completes instead of throwing on missing derived colors.
- `frontend/src/index.css` already declares global `border-box`, a viewport meta tag exists in `frontend/index.html`, and shared styles set `min-width: 0` and `overflow-x: hidden` in the app shell.

### Page/component coverage from static review

- **Public landing/about/privacy/terms:** shared `frontend/src/index.css` includes mobile breakpoints; the landing page has separate responsive navigation. Visual overflow at 320–480 px remains unverified.
- **Login/register/forgot/reset/callback:** auth layouts share the responsive auth styles and minimum-width form treatment; no visual device pass was possible.
- **Dashboard/create/channels/profile/history/admin:** use the shared workspace shell and common page/card tokens. The shared shell collapses the sidebar for tablet/mobile.
- **Scheduler/calendar:** dense week and month boards use internal horizontal-scroll containers at narrow widths; this is intentional component scrolling, not proof that every page has zero horizontal overflow.
- **AI responder:** `frontend/src/components/responder/responder.css` stacks multi-column forms and training layouts at 640/1100 px and includes reduced-motion overrides.
- **Dialogs, crop modal, notifications, language selector, and pricing modal:** component styles exist, but bounded-position and keyboard behavior were not exhaustively inspected at every viewport.

### Responsive verification still required

The requested 320, 375, 390, 480, 768, 1024, 1440, and 1920 px visual checks could not be run because the browser access host was unavailable. Do not treat the static review as a 100% responsive certification. Run a browser QA pass for horizontal overflow, focus order, overlay bounds, minimum 44 px targets, and mobile input sizing on every route before release.

## Defense layers present after this pass

- JWT signature and expiry validation with bcrypt password hashing.
- Login, signup, password-reset, and global per-IP rate limits.
- Authenticated scheduled-post read/delete with database-level ownership filtering.
- User-bound, single-use OAuth state for social connect callbacks; TikTok retains PKCE and its cookie-bound state flow.
- No unsigned client-side payment grant; paid access stays behind admin activation until verified payment integration exists.
- Image decode/re-encode and video container signature checking.
- Explicit credentialed CORS origin list with wildcard rejection.
- API security headers and request-body `Content-Length` cap.
- Firestore deny-by-default client rules and expiring reset/OAuth state documents.
- `.env` and local token/database artifacts ignored by Git.

## Files changed or added by this audit

- Backend hardening: `backend/config.py`, `backend/main.py`, `backend/security.py`, `backend/routers/auth.py`, `backend/routers/schedule.py`, `backend/routers/social.py`, `backend/routers/content.py`, `backend/routers/billing.py`, `backend/media_rules.py`.
- Frontend responsive/accessibility and checks: `frontend/src/components/WorkspaceShell.jsx`, `frontend/src/pages/Callback.jsx`, `frontend/scripts/check-contrast.mjs`.
- Dependency updates: `frontend/package.json`, `frontend/package-lock.json`.
- Report: `SECURITY_AND_RESPONSIVE_REPORT.md`.

Several backend files above already had uncommitted edits when this audit began. Those edits were preserved and reviewed; unrelated untracked image assets, scripts, and Firebase configuration files were not staged or modified.

## Action required

1. Set a unique random `SECRET_KEY` in `backend/.env` before deploying. Never reuse the sample placeholder.
2. Populate the URLs and origins: `APP_BASE_URL`, `API_BASE_URL`, `FRONTEND_URL`, `PUBLIC_BACKEND_URL`, `CORS_ORIGINS`, and the registered OAuth redirect URIs (`FACEBOOK_REDIRECT_URI`, `LINKEDIN_REDIRECT_URI`, `INSTAGRAM_REDIRECT_URI`, `TIKTOK_REDIRECT_URI`).
3. Configure provider credentials only for integrations in use: `FACEBOOK_CLIENT_ID`, `FACEBOOK_CLIENT_SECRET`, `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`, `INSTAGRAM_CLIENT_ID`, `INSTAGRAM_CLIENT_SECRET`, `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `IMAGE_API_KEY`, `GEMINI_API_KEY`, `TAVILY_API_KEY`, and SMTP credentials (`SMTP_USER`/`SMTP_PASS` or aliases). Keep them server-side.
4. Configure Firestore Application Default Credentials and verify the target project, database, rules, indexes, and TTL policies in the hosting account. The sample project identifier is configuration, not a credential.
5. Set real webhook secrets/tokens (`META_WEBHOOK_VERIFY_TOKEN`, `META_APP_SECRET`, `INSTAGRAM_APP_SECRET`) and keep `WEBHOOK_REQUIRE_SIGNATURE=true` outside local tests.
6. Remove or environment-gate the hard-coded developer entitlement override in `backend/deps.py` before production. Confirm the admin account value in `ADMIN_EMAIL` and reconcile the separate contact email in `frontend/src/components/PricingModal.jsx`.
7. Configure HTTPS termination and frontend-host security headers at the reverse proxy/static host. Confirm `X-Forwarded-Proto` is only supplied by a trusted proxy.
8. Decide whether to plan a React Router 7 compatibility migration. Current `npm audit` reports two moderate React Router advisories; upgrading via the automatic fix changes the major version.
9. Schedule a visual viewport pass and a real Firestore-backed smoke test before release. Rotate credentials if any were ever committed in earlier Git history or shared outside the repository; this review did not inspect cloud credential stores or every historical commit.

## Verification and run instructions

### Checks run

- `npm.cmd run build` — passed with a warning that the main JavaScript chunk is about 882 kB minified.
- `npm.cmd run check:contrast` — passed; all checked text/background pairs meet 4.5:1.
- `python -m compileall -q backend` using the project virtual environment — passed.
- Frontend dependency audit — high severity Axios/follow-redirects findings and Vite/CSS parser advisories were fixed. Full audit now reports **two moderate React Router findings**; the available fix requires Router 7.
- Backend dependency audit — `pip-audit` was not installed in the existing virtual environment and could not be installed in this environment; Python package advisories remain unverified.
- Local HTTP smoke checks — frontend `/` returned 200; backend `/api/health` and `/docs` returned 200 after restart. Login, OAuth, payment, and full CRUD journeys were not exercised against real provider/Firestore accounts.
- No TypeScript checker or linter script is defined in `frontend/package.json`; the frontend is JavaScript. No test script was defined.

### Start locally (PowerShell)

```powershell
Copy-Item backend/.env.example backend/.env
# Fill the local-only configuration values in backend/.env.
Set-Location backend
..\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
Set-Location frontend
npm.cmd install
npm.cmd run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173` for the frontend and `http://127.0.0.1:8000/docs` for the API docs. For production verification, run `npm.cmd run build`, `npm.cmd run check:contrast`, `npm.cmd audit`, and install/run `pip-audit -r backend/requirements.txt` in a controlled environment.
