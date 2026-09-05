# Software Requirements Specification (SRS)
# BrandAura — AI-Powered Social Media Management, Analytics & Content Generation Suite

**Prepared by:** Meveryx — Product & Architecture
**Document Version:** 1.0
**Status:** Approved for Development Baseline
**Date:** 31 August 2026

---

## Table of Contents

1. [Introduction](#1-introduction)
   - 1.1 Purpose
   - 1.2 Document Conventions
   - 1.3 Intended Audience and Reading Suggestions
   - 1.4 Product Scope
   - 1.5 References
2. [Overall Description](#2-overall-description)
   - 2.1 Product Perspective
   - 2.2 Product Functions
   - 2.3 User Classes and Characteristics
   - 2.4 Operating Environment
   - 2.5 Design and Implementation Constraints
   - 2.6 User Documentation
   - 2.7 Assumptions and Dependencies
3. [Specific Requirements](#3-specific-requirements)
   - 3.1 External Interface Requirements
   - 3.2 Functional Requirements
   - 3.3 Non-Functional Requirements
   - 3.4 System Architecture & Tech Stack
   - 3.5 User Roles & Use Cases
4. [Appendix and Index](#4-appendix-and-index)
   - A. Glossary
   - B. Analysis Models
   - C. Current Implementation Status & Known Gaps
   - D. Change History

---

# 1. Introduction

## 1.1 Purpose

This Software Requirements Specification (SRS) document defines the functional and non-functional requirements for **BrandAura**, an AI-powered Social Media Management, Analytics, and Content Generation suite developed by **Meveryx**. The document is intended to serve as the authoritative reference for architecture, development, quality assurance, and maintenance activities.

The product is delivered as a **single-page web application** with a **RESTful API backend**. It enables creators, marketers, and enterprises to generate on-brand visual and textual content, plan campaigns on a content calendar, publish directly to social platforms, and analyze performance from one unified workspace.

## 1.2 Document Conventions

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **MAY**, and **OPTIONAL** in this document are to be interpreted as described in RFC 2119 (https://www.ietf.org/rfc/rfc2119.txt).

Type styles used in this document:

| Style | Meaning |
|-------|---------|
| `monospace` | Code, identifiers, file paths, API endpoints, environment variables |
| **Bold** | Emphasis on a functional or non-functional requirement |
| *Italic* | Notes, examples, or non-normative explanation |

Unique requirement identifiers follow the pattern **FR-** (functional), **NFR-** (non-functional), **EIR-** (external interface), **UC-** (use case). Identifiers are tabulated in [Appendix B](#b-analysis-models).

## 1.3 Intended Audience and Reading Suggestions

| Audience | Reading Emphasis |
|----------|------------------|
| Product Management | Sections 1, 2, and 3.2 |
| Software Architects & Lead Developers | Sections 2.4, 2.5, 3.1, 3.4 |
| Frontend & Backend Engineers | All of Section 3 |
| QA / Test Engineers | All of Section 3 (traceable identifiers) |
| DevOps / SRE | Sections 2.4, 3.3 (NFR), 3.4 |
| Operations & Support | Section 2.3, 3.2 (FR), Appendix C |

## 1.4 Product Scope

**BrandAura** is a cloud-based, multilingual, artificial-intelligence-driven software suite that consolidates four core capabilities into a single product:

1. **AI Content & Image Studio** — tailored text generation and media generation.
2. **Cross-Platform Publisher** — OAuth-based account connection and direct publishing to Facebook, Instagram, and LinkedIn.
3. **Smart Strategy Panel** — competitor analysis and market-demand generation using live web search.
4. **Brand Kits & History** — persistent brand configuration and a full post/activity history module.

The product is monetized through a **free-trial → Pro subscription** model (`$29/mo`), administered manually by Meveryx staff (no automated payment processor in the current baseline; see [FR-BIL](#fr-bil) and [Appendix C](#c-current-implementation-status--known-gaps)).

A key distinguishing value proposition is that BrandAura **generates**, **plans**, and **publishes** automatically — from a single natural-language prompt — and is available in a large set of human languages with Right-to-Left (RTL) support.

## 1.5 References

The following documents and standards are referenced throughout this SRS:

1. **IEEE 830-1998** — IEEE Recommended Practice for Software Requirements Specifications.
2. **RFC 2119** — Key words for use in RFCs to Indicate Requirement Levels.
3. **Meta Graph API v18.0** — Facebook and Instagram publishing endpoints.
4. **LinkedIn Marketing API (v2)** — `ugcPosts`, `assets` register/upload endpoints.
5. **Open Graph Protocol** — `og:meta` tags for social sharing.
6. **Google Search Central** — Structured data (`JSON-LD`), `sitemap.xml` and `robots.txt` guidelines.
7. **Core Web Vitals** — LCP, INP, CLS performance metrics.
8. Project codebase: `frontend/`, `backend/` (living baseline referenced in [Appendix C](#c-current-implementation-status--known-gaps)).

---

# 2. Overall Description

## 2.1 Product Perspective

BrandAura is a new, self-contained product family owned by Meveryx. It is composed of two deployable components:

- **Frontend** — a React (Vite) single-page application (SPA).
- **Backend** — a FastAPI REST service with asynchronous I/O, acting as the single source of truth and orchestrating all third-party integrations.

BrandAura depends on the following external systems (see [3.1 External Interface Requirements](#31-external-interface-requirements)):

- Google Gemini (text generation)
- Pollinations.ai (image generation)
- Tavily Search (live web search for competitor/market analysis)
- Meta Graph API (Facebook + Instagram OAuth and publishing)
- LinkedIn API (OAuth and publishing)
- Cloudinary (media hosting/transformation)
- SMTP e-mail (password reset and notifications)
- MongoDB & SQLite (persistence)

Architecturally, the frontend communicates exclusively with the backend over HTTP(S) JSON (`/api/*`) and never holds third-party credentials directly; all OAuth and publishing orchestration occurs server-side.

## 2.2 Product Functions

The high-level product functions are:

- **F1 — Account & Authentication:** registration, login, JWT-based authenticated sessions, password reset (e-mail or development link), and role-based access (user / admin).
- **F2 — Social Account Management:** connect, disconnect, and enumerate Facebook, Instagram, and LinkedIn accounts via OAuth.
- **F3 — AI Content Generation:** generate tailored text captions, post copy, and competitive analyses.
- **F4 — AI Image Generation:** generate media assets from prompts.
- **F5 — Publishing:** direct (synchronous) publishing and queued/automated publishing to connected platforms.
- **F6 — Content Calendar & Scheduling:** create/edit/delete single and recurring posts, bulk queueing, and calendar notes/reminders.
- **F7 — Smart Strategy Panel:** live competitor analysis and viral strategy generation.
- **F8 — Brand Kits:** persistent custom brand settings used to tailor generated content.
- **F9 — History Module:** searchable activity and post history.
- **F10 — Subscription & Billing:** trial lifecycle, Pro activation, and paywall enforcement.
- **F11 — Multilingual & RTL:** full translation of the interface and RTL layout support.
- **F12 — Search Engine Optimization:** dynamic metadata, structured data, and crawler control.

## 2.3 User Classes and Characteristics

| User Class | Characteristics | Privileges |
|------------|-----------------|------------|
| **Visitor** | Unauthenticated; browses public marketing pages (landing, about, privacy, terms). | Read-only public pages. |
| **Registered User (Free Trial)** | Authenticated; has a 30-day trial. | Full feature access while trial is active; otherwise paywalled (HTTP 402). |
| **Pro User (Subscribed)** | Authenticated; admin-activated or simulated-subscription Pro access for 1 year / 30 days. | Full feature access, including all AI, publishing, and scheduling endpoints. |
| **Admin** | Meveryx staff; `is_admin=true`. | Everything a Pro User can do, plus manual Pro activation and user administration. |
| **Operations / Support** | Meveryx operations staff. | Backend/monitoring access; e-mail administration. |

### Stakeholders

Meveryx is the development organization. Primary stakeholders and roles:

| Stakeholder | Role |
|-------------|------|
| **Maria Shafqat** | Founder / CEO & Lead Developer — product owner, technical authority. |
| **Zahra Imran** | Core operational & management team — operations and product coordination. |
| **Muskan Haroon** | Core operational & management team — quality, content, and user experience. |
| **Malika Akhbar** | Core operational & management team — marketing, growth, and SEO strategy. |

Stakeholders are the approval authority for requirements changes (see [Appendix D](#d-change-history)).

## 2.4 Operating Environment

**Frontend (Client):**

- Modern evergreen browsers (last 2 major versions of Chrome, Edge, Firefox, Safari).
- No native install; delivered as a web SPA over HTTPS.
- Network: standard broadband; the application performs better with stable connectivity given the media and 3D visual assets.

**Backend (Server):**

- Python 3.10+ runtime; FastAPI application served by an ASGI server (e.g., Uvicorn).
- Persistence: MongoDB (primary document store for users, activities, password resets, calendar notes) and SQLite (Postgres-compatible schema for scheduled posts).
- In-process scheduler (APScheduler) for the auto-publishing job loop.
- Third-party media storage: Cloudinary.

**Reference/local deployment specifics:** development runs the frontend on `http://localhost:5173` (Vite) and the backend on `http://localhost:8000` (Uvicorn), with the frontend proxying `/api` to the backend. Production origin is `https://brandaura.meveryx.com`.

## 2.5 Design and Implementation Constraints

1. **Single-page architecture**: the product SHALL be implemented as a React SPA using client-side routing (react-router-dom v6).
2. **ASGI backend**: all backend services SHALL be implemented with FastAPI and asynchronous I/O (Motor, `httpx`).
3. **Stateless API**: the backend SHALL be stateless with respect to session persistence, authenticating via JWT Bearer tokens.
4. **Proprietary orchestration**: the backend MUST be the only component that holds OAuth secrets and calls third-party APIs.
5. **Manual paywall**: in the current baseline, Pro access is activated manually by an admin (see [Appendix C](#c-current-implementation-status--known-gaps)); an automated payment gateway is NOT REQUIRED for this baseline but is a known enhancement.
6. **Multilingual baseline**: the interface SHALL ship the following fully-supported languages: English, Spanish, French, German, Arabic, Urdu, and Hindi.
7. **Security baseline**: bcrypt password hashing, JWT with a 7-day expiry, per-IP rate limiting on login and password-reset, and defense against CORS misuse.
8. **Static asset constraints**: media is stored off-platform (Cloudinary); the backend SHALL NOT persist local media files.

## 2.6 User Documentation

The following user documentation SHALL be produced and maintained:

- In-app help / onboarding copy (localized per supported language).
- A marketing site (landing, about, pricing, privacy, and terms).
- API reference for internal integration use.
- Operational runbook for Meveryx operations staff (environment variables, admin activation procedure).

## 2.7 Assumptions and Dependencies

**Assumptions:**

- A-1. Third-party services (Gemini, Pollinations.ai, Tavily, Meta, LinkedIn, Cloudinary, SMTP) remain available and within their respective terms and rate limits.
- A-2. Administrative Pro activation is performed by Meveryx staff on request (per the current manual-paywall model).
- A-3. The product operates within platform content policies of Facebook, Instagram, and LinkedIn.
- A-4. Users provide valid OAuth consent for the requested platform scopes.

**Dependencies:**

- D-1. MongoDB instance is reachable and configured with the `brandora` database.
- D-2. All external API keys and OAuth client credentials are provisioned in the backend environment.
- D-3. Google Search Console and domain verification are completed by Meveryx operations for SEO validation (external to this system).

---

# 3. Specific Requirements

## 3.1 External Interface Requirements

### 3.1.1 User Interfaces

- **EIR-UI-1:** The product SHALL provide a consistent, dark-themed, responsive web UI across desktop, tablet, and mobile viewports.
- **EIR-UI-2:** The product SHALL support the seven core languages with instantaneous switching and full RTL layout (Arabic and Urdu).
- **EIR-UI-3:** All user-facing text SHALL be routed through the internationalization (`i18n`) translation function; no user-facing string SHALL be hard-coded.
- **EIR-UI-4:** Screens SHALL map to routes: `/` (landing), `/about`, `/privacy`, `/terms`, `/login`, `/register`, `/forgot-password`, `/reset-password`, `/auth/callback/:platform` (OAuth return), and protected `/dashboard`, `/scheduler`, `/calendar`, `/history`, `/admin`.

### 3.1.2 Hardware Interfaces

- **EIR-HW-1:** No special client hardware is required beyond a standards-compliant, internet-connected device.
- **EIR-HW-2:** The system SHALL accept user-uploaded media files via standard multipart/form-data upload (see [FR-MED](#fr-med) for media storage requirements).

### 3.1.3 Software Interfaces

The following external software systems SHALL be integrated:

| Interface ID | System | Protocol / Style | Purpose | Requirement |
|--------------|--------|------------------|---------|-------------|
| **SWI-1** | Google Gemini API | HTTPS, OpenAI-compatible chat completions | AI text/content generation | FR-AI-1, FR-AI-2, FR-STR-1 |
| **SWI-2** | Pollinations.ai | HTTPS GET, image bytes | AI image/media generation | FR-AI-2 |
| **SWI-3** | Tavily Search API | HTTPS POST JSON | Live competitor & market search | FR-STR-1, FR-STR-2 |
| **SWI-4** | Meta Graph API v18.0 | HTTPS OAuth + REST | Facebook & Instagram OAuth + publishing | FR-SOC-1, FR-PUB-1 |
| **SWI-5** | LinkedIn API v2 | HTTPS OAuth + REST | LinkedIn OAuth + publishing | FR-SOC-1, FR-PUB-1 |
| **SWI-6** | Cloudinary | HTTPS | Media hosting/transformation | FR-MED |
| **SWI-7** | SMTP | SMTP + STARTTLS | Password reset e-mails | FR-AUTH-3 |
| **SWI-8** | MongoDB | MongoDB wire protocol (Motor) | Users, activities, resets, notes | FR-BRAND-1, FR-HIST-1 |
| **SWI-9** | SQLite | SQLAlchemy | Scheduled posts queue | FR-SCHED-1 |

*Note on SWI-3:* the requirement describes "real-time web scraping" for competitor analysis; the implemented mechanism uses the **Tavily Search API** (a live, managed web-search interface) rather than raw scraping. See [FR-STR-1](#fr-str-1) and [Appendix C](#c-current-implementation-status--known-gaps).

*Note on Formspree:* the original brief references Formspree for workflow integrations. Formspree is **not** present in the current implementation. It is captured here as an OPTIONAL enhancement interface (**SWI-10**) for future contact-form / lead capture workflows.

### 3.1.4 Communication Interfaces

- **EIR-COM-1:** The frontend SHALL communicate with the backend exclusively over HTTP(S) JSON via the `/api/*` namespace.
- **EIR-COM-2:** All authenticated requests SHALL carry a JWT in the `Authorization: Bearer <token>` header.
- **EIR-COM-3:** The backend SHALL support CORS for the frontend origins only.
- **EIR-COM-4:** The backend SHALL return standardized HTTP status codes, including **401** (unauthorized), **402** (paywall/subscription required), **429** (rate limited), and **503** (backend unavailable).

## 3.2 Functional Requirements

### 3.2.1 Authentication & Account Management

- **FR-AUTH-1:** The system SHALL allow a user to register with a unique username (3–50 chars), a valid e-mail address, and a password (8–128 chars). Passwords SHALL be hashed with bcrypt and SHALL NOT be stored or transmitted in plaintext.
- **FR-AUTH-2:** The system SHALL authenticate users via e-mail and password and issue a signed JWT (HS256) with a 7-day expiry.
- **FR-AUTH-3:** The system SHALL support password reset via a time-limited (15-minute) single-use token delivered by SMTP, with a development-mode fallback when no mail server is configured.
- **FR-AUTH-4:** The system SHALL enforce rate limiting on login (10 attempts/60 s per IP) and password-reset e-mail (5 requests/300 s per IP), returning HTTP 429 on exceed.
- **FR-AUTH-5:** The system SHALL distinguish **user** and **admin** roles and gate administrative endpoints accordingly.

### 3.2.2 Social Account Connection (OAuth)

- **FR-SOC-1:** The system SHALL support OAuth 2.0 connection for **Facebook**, **Instagram**, and **LinkedIn**, including the construction of provider authorization URLs and the exchange of authorization codes for access tokens.
- **FR-SOC-2:** For Facebook/Instagram the system SHALL exchange short-lived tokens for long-lived tokens and resolve the connected **Page** and **Instagram Business Account** identifiers.
- **FR-SOC-3:** The system SHALL enumerate connected accounts and report connection status and per-platform authorization URLs.
- **FR-SOC-4:** The system SHALL allow a user to disconnect a connected account.

### 3.2.3 AI Content & Image Studio

- **FR-AI-1:** Given a topic and tone, the system SHALL generate tailored, on-brand social copy using the Gemini text model.
- **FR-AI-2:** Given a prompt, the system SHALL generate a media asset using the image provider, honoring a free vs. Pro quality mode. *(Implementation: Pollinations.ai; "Pro" mode SHALL route to a higher-quality model.)*
- **FR-AI-3:** Generated text SHALL be combined with brand context (see [FR-BRAND-1](#fr-brand-1)) to produce on-brand output.
- **FR-STR-1:** The system SHALL perform competitor analysis for a given topic — conducting a live web/market search and producing a competitive teardown and positioning recommendation.
- **FR-STR-2:** The system SHALL generate an "elite strategy" (competitor set, positioning, and a viral engagement roadmap) from a topic, recording usage history.

### 3.2.4 Cross-Platform Publisher

- **FR-PUB-1:** The system SHALL publish text, image, and video content directly to connected **Facebook**, **Instagram**, and **LinkedIn** accounts via their respective Graph/API endpoints.
- **FR-PUB-2:** The system SHALL support **direct (synchronous) publishing** and **queued (automated) publishing**. Queued posts SHALL be executed by a background scheduler at their scheduled time.
- **FR-PUB-3:** The system SHALL track publishing status (pending, processing, published, failed) and persist outcomes per post.
- **FR-PUB-4:** For Instagram, the system SHALL first create a *media container*, poll its processing status, and then publish the container.

### 3.2.5 Content Calendar & Scheduling

- **FR-SCHED-1:** The system SHALL allow creation of scheduled posts, list them, and delete pending/failed posts.
- **FR-SCHED-2:** The system SHALL support **recurring** posts (daily/weekly/monthly) up to a bounded instance count and a **bulk** creation mode (up to 200 posts per request).
- **FR-SCHED-3:** The system SHALL support calendar **notes/reminders** (create, update, list, mark-notified, delete).
- **FR-SCHED-4:** The auto-publish scheduler SHALL run continuously (poll interval of 60 seconds) to claim and execute due posts.

### 3.2.6 Brand Kits & History

- **FR-BRAND-1:** The system SHALL persist custom brand settings (brand kit) per user so that generated content consistently reflects the user's brand voice and identity.
- **FR-HIST-1:** The system SHALL record a searchable **history/activity** log per user (up to 200 entries, newest first) covering generation, publishing, and scheduling events.
- **FR-HIST-2:** The system SHALL allow a user to clear their history (in bulk or specific records).

### 3.2.7 Subscription, Billing & Paywall

- **FR-BIL-1:** New registrations SHALL be granted a **30-day free trial** with full feature access; the trial end date SHALL be persisted.
- **FR-BIL-2:** The system SHALL compute a normalized subscription state (plan, subscribed flag, Pro status, trial status, days remaining, and access-active boolean).
- **FR-BIL-3:** Pro access (`$29/mo`) SHALL only be granted when the account is explicitly **subscribed** (or within an active trial).
- **FR-BIL-4:** Access to premium functionality (AI generation, competitive analysis, publishing, scheduling, calendar) SHALL be gated by the subscription state; denied requests SHALL return **HTTP 402** with a paywall message containing the admin contact (`meveryx@gmail.com`).
- **FR-BIL-5:** An **admin** SHALL be able to manually activate Pro access for a user (1-year activation) and to cancel subscriptions.
- **FR-BIL-6:** The system SHALL expose a read-only billing/subscription status endpoint.

### 3.2.8 Analytics (Planned)

- **FR-ANA-1:** *(Planned — not in current baseline)* The system SHALL provide per-account, per-post analytics (reach, impressions, engagement) aggregated from connected platforms.
- **FR-ANA-2:** *(Planned)* The system SHALL surface best-time-to-post recommendations derived from analytics and publish history.
- **FR-ANA-3:** *(Planned)* The system SHALL present analytics through the Dashboard and Calendar interfaces.

*Status note:* Analytics endpoints are **not implemented** in the current baseline. These requirements are recorded for a future release and are explicitly out of scope for baseline delivery (see [Appendix C](#c-current-implementation-status--known-gaps)).

### 3.2.9 Media Uploads

- **FR-MED-1:** The system SHALL accept image and video uploads as multipart/form-data.
- **FR-MED-2:** The system SHALL detect media type (image vs. video) by extension and route uploads accordingly.
- **FR-MED-3:** Uploaded media SHALL be stored in Cloudinary and referenced by a secure HTTPS URL; the backend SHALL NOT persist media locally.
- **FR-MED-4:** Video uploads SHALL use Cloudinary's `upload_large` chunked mechanism (6 MB chunk size).
- **FR-MED-5:** The system SHALL **support media files up to 5 GB** (see [NFR-SCAL-3](#nfr-scal-3) and [Appendix C](#c-current-implementation-status--known-gaps) — currently bounded by memory-based ingestion, not yet streaming).

### 3.2.10 Search Engine Optimization (SEO)

- **FR-SEO-1:** The system SHALL render dynamic, per-page metadata — `<title>`, `meta description`, canonical URL, and OCR/bot-relevant robots directives — for each public route using React Helmet.
- **FR-SEO-2:** The system SHALL emit full Open Graph and Twitter Card tags (including 1200×630 image dimensions) for public pages.
- **FR-SEO-3:** The system SHALL emit `JSON-LD` structured data, including `SoftwareApplication` and `Organization` schema, on the landing page.
- **FR-SEO-4:** The system SHALL expose a `sitemap.xml` covering all public routes and a `robots.txt` that allows public pages and disallows private/app routes.
- **FR-SEO-5:** Every public page SHALL declare a canonical URL pointing to the production origin (`https://brandaura.meveryx.com`).

### 3.2.11 Multilingual & RTL

- **FR-ML-1:** The interface SHALL support the seven core languages (English, Spanish, French, German, Arabic, Urdu, Hindi) with complete translation coverage.
- **FR-ML-2:** The system SHALL persist the user's language selection and apply it without reload.
- **FR-ML-3:** The system SHALL apply Right-to-Left layout for RTL languages (Arabic, Urdu).
- **FR-ML-4:** The language selector SHALL expose only languages with complete, real translation dictionaries.

## 3.3 Non-Functional Requirements

### 3.3.1 Performance

- **NFR-PERF-1:** The product SHALL satisfy Google **Core Web Vitals**: LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1 on the public landing page over a typical connection.
- **NFR-PERF-2:** Below-the-fold images SHALL be lazy-loaded (`loading="lazy"`, `decoding="async"`); heavy scenes/components SHALL be code-split via `React.lazy` + `Suspense`.
- **NFR-PERF-3:** The initial JavaScript bundle delivered for the public landing page SHALL NOT exceed an aggressive target (the baseline reduced the main bundle from ~1.5 MB to ~742 KB by isolating the Three.js scene into a lazily-loaded chunk).
- **NFR-PERF-4:** Interactive API calls SHALL respond within 500 ms (typ.) for non-AI endpoints; AI generation endpoints MAY take longer given the latency of third-party providers.

### 3.3.2 SEO (Performance-class Enabling)

- **NFR-SEO-1:** Titles SHALL be ≤ 60 characters and meta descriptions ≤ 155 characters.
- **NFR-SEO-2:** Structured data SHALL validate against schema.org and Google's Rich Results requirements.

### 3.3.3 Scalability

- **NFR-SCAL-1:** The system SHALL support a growing number of concurrent users with horizontal scaling of stateless API instances (see constraint 3).
- **NFR-SCAL-2:** The system SHALL handle **heavy media uploads up to 5 GB** without exhausting server memory; this REQUIRES streaming uploads to object storage (Cloudinary) — a known enhancement over the current in-memory ingestion (see [Appendix C](#c-current-implementation-status--known-gaps)).
- **NFR-SCAL-3:** The in-memory rate limiter SHALL be replaceable with a distributed store (e.g., Redis) for multi-instance correctness.

### 3.3.4 Security

- **NFR-SEC-1:** Passwords SHALL be hashed with bcrypt; OAuth tokens SHALL be stored securely (see [Appendix C](#c-current-implementation-status--known-gaps) for the current plaintext-JSON caveat).
- **NFR-SEC-2:** The backend SHALL enforce subscription and role-based access control on all premium and administrative endpoints.
- **NFR-SEC-3:** The system SHALL protect against brute-force via rate limiting and SHALL use a non-default secret key in production.
- **NFR-SEC-4:** CORS SHALL be restricted to trusted frontend origins; secrets SHALL never be exposed to the client.

### 3.3.5 Reliability & Maintainability

- **NFR-REL-1:** The system SHALL degrade gracefully when third-party services fail (e.g., AI providers), returning meaningful errors and continuing to operate.
- **NFR-MNT-1:** The codebase SHALL follow modular, layered organization (routers, schemas, dependencies, security) to support maintainability.
- **NFR-MNT-2:** All user-facing strings SHALL be centralized in the i18n translation module to enable low-cost localization.

### 3.3.6 Usability & Accessibility

- **NFR-USE-1:** The interface SHALL be keyboard- and screen-reader accessible, with semantic HTML landmarks (`header`, `main`, `nav`, `section`, `article`, `footer`).
- **NFR-USE-2:** All meaningful images SHALL carry descriptive alt text; decorative images SHALL use empty alt text.

### 3.3.7 Portability

- **NFR-PORT-1:** The frontend SHALL render in all modern evergreen browsers.
- **NFR-PORT-2:** The backend SHALL run on standard Python 3.10+ environments and be deployable to common hosting (VM or containerized).

## 3.4 System Architecture & Tech Stack

### 3.4.1 Logical Architecture

The system SHALL be deployed as a **three-tier** architecture: **Presentation** (React SPA) → **Application/Service** (FastAPI) → **Data** (MongoDB + SQLite) and **External** (AI, search, social, and media providers).

```
┌─────────────────────────── Presentation (React + Vite SPA) ───────────────────────────┐
│  Routes: Landing, About, Privacy, Terms, Login, Register, Forgot/Reset Password,      │
│          OAuth Callback, Dashboard, Scheduler, Calendar, History, Admin                │
│  Cross-cutting: LanguageProvider (i18n/RTL), SEO (<Helmet/>), UpgradeModal,           │
│          ErrorBoundary, Lenis smooth-scroll, Toaster                                   │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │ HTTPS JSON  /api/*
┌─────────────────────────── Application (FastAPI, ASGI) ────────────────────────────────┐
│  Routers: auth · social · content · strategy · schedule · user · billing (+admin)      │
│  Cross-cutting: deps (auth/subscription), security (JWT/bcrypt/rate-limit), usage/history│
│  Scheduler: APScheduler auto-publish loop (60s)                                        │
└──────────────┬──────────────────┬──────────────────┬─────────────────┬─────────────────┘
               │                  │                  │                 │
        ┌──────▼──────┐    ┌──────▼──────┐    ┌──────▼──────┐    ┌─────▼──────┐
        │  MongoDB    │    │  SQLite     │    │  Cloudinary │    │  External  │
        │  (Motor)    │    │ (SQLAlchemy)│    │  (media)    │    │  AI/Search/
        │ users,      │    │ scheduled_  │    │             │    │  Social    │
        │ activities, │    │ posts       │    │             │    │  providers │
        │ resets,     │    │             │    │             │    │  (Gemini,  │
        │ notes       │    │             │    │             │    │  Pollinations, Tavily,
        └─────────────┘    └─────────────┘    └─────────────┘    │  Meta, LinkedIn)
                                                                 └────────────┘
```

### 3.4.2 Frontend (React + Vite)

- **Framework:** React 18 with Vite 5 build tooling.
- **Routing:** react-router-dom v6 (BrowserRouter).
- **State/Utilities:** Axios (interceptors for 401/402/503), Framer Motion, GSAP, Lenis (smooth scroll), react-hot-toast, react-easy-crop.
- **3D/Visual:** react-three-fiber + drei (Hero/3D scenes), lazy-loaded to protect Core Web Vitals.
- **i18n:** custom `LanguageContext` + centralized translation dictionary with RTL support.
- **SEO:** `react-helmet-async` with a reusable `<SEO/>` component emitting title, description, canonical, Open Graph, Twitter Card, and JSON-LD.
- **Accessibility:** semantic HTML landmarks and structured alt text.
- **Performance:** `React.lazy` + `Suspense` code-splitting; lazy image loading.

### 3.4.3 Backend (FastAPI)

- **Framework:** FastAPI (ASGI), Uvicorn server.
- **Data Access:** Motor (async MongoDB driver); SQLAlchemy (SQLite) for the scheduled-post queue.
- **HTTP Client:** `httpx` (async) for all third-party calls.
- **Security:** python-jose (JWT/HS256), passlib/bcrypt, custom in-memory rate limiter.
- **Scheduling:** APScheduler (`AsyncIOScheduler`) for the 60-second auto-publish loop.
- **Modularity:** separate routers: `auth`, `social`, `content`, `strategy`, `schedule`, `user`, `billing`.

### 3.4.4 Workflow Orchestration

- **Formspree (OPTIONAL):** the brief references Formspree for workflow integration. It is captured as a recommended future interface (**SWI-10**) for lead-capture and contact workflows; it is **not** implemented in the current baseline.

## 3.5 User Roles & Use Cases

The following use cases define the standard user workflows. Each is identified as **UC-<n>**.

### UC-1 — Register and Begin Free Trial

- **Actors:** Visitor, System.
- **Precondition:** Visitor on `/register`.
- **Main Flow:**
  1. Visitor submits username, e-mail, and password.
  2. System validates uniqueness and password policy.
  3. System creates the account, hashes the password, and issues a JWT.
  4. System grants a **30-day free trial** (`plan=trial`).
  5. System redirects to `/dashboard`.
- **Postcondition:** Authenticated trial user with full feature access.

### UC-2 — Connect Social Accounts

- **Actors:** Registered/Pro User, System, Meta/LinkedIn.
- **Precondition:** User authenticated.
- **Main Flow:**
  1. User selects a platform (Facebook, Instagram, or LinkedIn) in the Dashboard.
  2. System returns the provider OAuth authorization URL.
  3. User consents on the provider; provider redirects to `/auth/callback/:platform?code=...`.
  4. System exchanges the code for an access token.
  5. For Facebook/Instagram, System resolves Page and Instagram Business Account IDs and extends the token's lifetime.
  6. System records the connected account and reports status.
- **Postcondition:** Account is connected and available for publishing.
- **Alternative Flow (disconnect):** User disconnects an account; System removes it.

### UC-3 — Generate AI Content

- **Actors:** Pro User, System, Gemini.
- **Precondition:** User subscribed or within trial.
- **Main Flow:**
  1. User provides a topic and tone in the Content Studio.
  2. System injects the user's **brand kit** context (FR-BRAND-1).
  3. System calls Gemini to produce tailored copy.
  4. System displays the generated copy for editing.
- **Postcondition:** On-brand content generated and editable.

### UC-4 — Generate AI Media

- **Actors:** Pro User, System, Image provider.
- **Main Flow:**
  1. User enters a media prompt and quality mode.
  2. System calls the image provider (`Pollinations.ai`; Pro mode uses a higher-quality model).
  3. System returns the generated image bytes/MIME.
- **Postcondition:** Media asset available for publishing or scheduling.

### UC-5 — Generate an AI-Driven Viral Strategy

- **Actors:** Pro User, System, Tavily, Gemini.
- **Main Flow:**
  1. User enters a topic.
  2. System performs a live web search (Tavily) scoped to social domains.
  3. Gemini produces a competitive teardown and an "elite strategy" with a viral engagement roadmap.
  4. System records the strategy in the user's history.
- **Postcondition:** User has an actionable, data-informed content strategy.

### UC-6 — Schedule and Auto-Publish

- **Actors:** Pro User, System, Meta/LinkedIn, Cloudinary.
- **Main Flow:**
  1. User composes a post (text, optionally media or AI image) and selects platforms and a scheduled time (and optional recurrence).
  2. System uploads media to Cloudinary and stores the scheduled post (status `pending`).
  3. At the scheduled time, the background scheduler claims the post (`processing`).
  4. System publishes to each selected platform via Graph/API.
  5. System records outcome (`published`/`failed`) in history.
- **Postcondition:** Post published automatically or outcome logged.

### UC-7 — Publish Immediately

- **Actors:** Pro User, System, Meta/LinkedIn.
- **Precondition:** Account(s) connected, subscription active.
- **Main Flow:** User elects direct publish; System posts immediately to selected platforms (FR-PUB-1).
- **Postcondition:** Content live on selected channels.

### UC-8 — Manage the Content Calendar

- **Actors:** Pro/Registered User, System.
- **Main Flow:** User creates, edits, and deletes scheduled/recurring posts and calendar notes; System persists changes and honors recurrence rules.
- **Postcondition:** Calendar reflects the user's plan.

### UC-9 — Access Subscription & Pro Activation

- **Actors:** Pro User, Admin, System.
- **Main Flow:**
  1. User views billing/subscription status.
  2. On trial expiry or Pro subscription, access to premium endpoints is gated (HTTP 402).
  3. User contacts admin (`meveryx@gmail.com`) who performs administrative Pro activation.
- **Alternative:** Admin invokes the admin activation endpoint to grant 1-year Pro access.
- **Postcondition:** User has activated Pro and full feature access.

### UC-10 — Review History

- **Actors:** Registered/Pro User, System.
- **Main Flow:** User reviews activity/history (generation, publishing, scheduling). User may clear specific records or all.
- **Postcondition:** History is displayed and manageable.

---

# 4. Appendix and Index

## A. Glossary

| Term | Definition |
|------|------------|
| **SaaS** | Software as a Service — centrally hosted software licensed on subscription. |
| **OAuth 2.0** | Authorization framework for delegated access used by Meta and LinkedIn connections. |
| **JWT** | JSON Web Token — signed access token used for API authentication. |
| **Graph API** | Meta's REST API used for Facebook and Instagram publishing. |
| **RTL** | Right-to-Left — text/layout direction for Arabic and Urdu. |
| **LCP / INP / CLS** | Google Core Web Vitals metrics (Largest Contentful Paint, Interaction to Next Paint, Cumulative Layout Shift). |
| **JSON-LD** | JavaScript Object Notation for Linked Data — a structured-data format consumed by search engines. |
| **Paywall** | Restriction of premium features until subscription/trial criteria are met. |
| **Brand Kit** | Persistent, user-definable brand settings that shape generated content. |
| **APScheduler** | Python job-scheduling library used for the auto-publish loop. |

## B. Analysis Models

### Requirements Traceability Matrix (primary functional areas)

| Requirement ID | Category | Class/Area | Third-party dependency |
|----------------|----------|------------|------------------------|
| FR-AUTH-1..5 | Functional | Authentication | SMTP (FR-AUTH-3) |
| FR-SOC-1..4 | Functional | Social Connection | Meta, LinkedIn |
| FR-AI-1..3, FR-STR-1..2 | Functional | AI Studio / Strategy | Gemini, Pollinations, Tavily |
| FR-PUB-1..4 | Functional | Publishing | Meta, LinkedIn, Cloudinary |
| FR-SCHED-1..4 | Functional | Scheduling | APScheduler (internal) |
| FR-BRAND-1, FR-HIST-1..2 | Functional | Brand Kits & History | MongoDB |
| FR-BIL-1..6 | Functional | Subscription/Billing | (manual admin) |
| FR-MED-1..5 | Functional | Media Uploads | Cloudinary |
| FR-SEO-1..5 | Functional | Search Engine Optimization | (external) |
| FR-ML-1..4 | Functional | Multilingual/RTL | (i18n module) |
| NFR-PERF-1..4 | Non-Functional | Performance/CWV | — |
| NFR-SCAL-1..3 | Non-Functional | Scalability | Cloudinary, (Redis) |
| NFR-SEC-1..4 | Non-Functional | Security | — |
| EIR-UI-1..4, EIR-HW, EIR-COM | Interface | UI/HW/COM | — |
| SWI-1..10 | Interface | Software Interfaces | External providers |

### Use Case / Requirement Coverage

- **UC-1 Register** → FR-AUTH-1, FR-BIL-1
- **UC-2 Connect Accounts** → FR-SOC-1..4
- **UC-3 Generate Content** → FR-AI-1, FR-AI-3, FR-BRAND-1
- **UC-4 Generate Media** → FR-AI-2
- **UC-5 Strategy** → FR-STR-1, FR-STR-2, FR-HIST-1
- **UC-6 Schedule & Auto-Publish** → FR-SCHED-1..4, FR-PUB-1..4, FR-MED
- **UC-7 Publish Immediately** → FR-PUB-1
- **UC-8 Calendar** → FR-SCHED-2..3
- **UC-9 Subscription** → FR-BIL-1..6
- **UC-10 History** → FR-HIST-1..2

## C. Current Implementation Status & Known Gaps

This appendix maps the SRS to the live codebase (`frontend/`, `backend/`) so stakeholders understand what is implemented vs. specified for future work. It is part of the SRS for traceability and should be updated by the change-control process in [Appendix D](#d-change-history).

| Area | Status | Notes |
|------|--------|-------|
| React + Vite SPA | **Implemented** | React 18, Vite 5, react-router-dom v6. |
| FastAPI backend | **Implemented** | Routers: `auth`, `social`, `content`, `strategy`, `schedule`, `user`, `billing`. |
| Gemini text generation | **Implemented** | OpenAI-compatible chat endpoint (`gemini-3.5-flash-lite`). |
| Image generation | **Implemented** | Pollinations.ai (`image.pollinations.ai/prompt/...`). |
| Competitor/market analysis | **Implemented** | Tavily Search API (live web search), not raw scraping. |
| Meta Graph API (FB + IG) | **Implemented** | OAuth + direct publishing, Graph v18.0. |
| LinkedIn API | **Implemented** | OAuth + ugcPosts/assets upload. |
| Cloudinary media hosting | **Implemented** | `upload` / `upload_large` (6 MB chunks). |
| Content calendar & scheduler | **Implemented** | APScheduler 60 s loop; recurring + bulk (200). |
| Brand kits (persistent) | **Partially specified** | Brand context exists conceptually; dedicated persisted brand-kit module is a gap. |
| History module | **Implemented** | `activities` collection; up to 200 entries. |
| Subscription gating | **Implemented** | `require_subscription` → HTTP 402 → admin contact. |
| Manual Pro activation | **Implemented** | `POST /api/admin/activate-user` (admin-only, 1-year). |
| Automated payment gateway | **Not implemented (enhancement)** | `billing/subscribe` is a simulation; real purchase via admin. |
| **Formspree integration** | **Not implemented (specified, OPTIONAL)** | SWI-10; absent from codebase. |
| **Analytics module** | **Not implemented (planned)** | FR-ANA-1..3; no analytics/positions/brand router exists. |
| **5 GB media upload** | **Not implemented (specified)** | NFR-SCAL-2; current uploads read into memory, not streamed. |
| **Secure OAuth token storage** | **Gap** | Tokens currently stored in plaintext `connected_accounts.json`; no per-user scoping/encryption. |
| SEO (Helmet, JSON-LD, meta) | **Implemented** | `<SEO/>` component; `sitemap.xml`, `robots.txt`, OG/Twitter, JSON-LD (SoftwareApplication, Organization). |
| Core Web Vitals / code-splitting | **Implemented** | `React.lazy`+`Suspense`; lazy images; main bundle ~742 KB. |
| Multilingual / RTL | **Implemented** | 7 core languages; RTL for ar/ur. |

## D. Change History

| Version | Date | Author | Description |
|---------|------|--------|-------------|
| 1.0 | 31 August 2026 | Meveryx Product & Architecture | Initial baseline per IEEE 830; includes current-implementation traceability (Appendix C). |

---

*End of SRS — BrandAura. Approved for development baseline.*
