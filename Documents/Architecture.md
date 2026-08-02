# Architecture — Veterinary Clinic Pre-Registration (V1)

**Status:** Draft for review
**Last updated:** 2026-08-02
**Companion docs:** `Requirements.md` (requirements + Appendix A IDs), `TraceabilityMatrix.md`, `Decisions.md`

---

## 1. Purpose

Describes the components, deployment, data, and runtime flows for V1. V1 is intentionally
small: a single Django web application, a managed Postgres database, Twilio for SMS, and the
existing Flutter/Android app reused solely as the label-print station.

---

## 2. System Context

```
   +-----------------+                +-------------------+
   |  Owner (phone)  |                | Admin / Volunteer |
   |  public form    |                | (laptop/tablet)  |
   +--------+--------+                +--------+----------+
            |  HTTPS                           | HTTPS (login)
            |                                  |
            v                                  v
   +----------------------------------------------------+
   |            Django Web App  (PaaS: Render)          |
   |  public views | admin/volunteer views | lottery    |
   |  export (CSV/XLSX) | i18n (EN/ES)                 |
   +---+-----------------------+------------------------+
       |                       |
       | SQL                   | REST (label payload)
       v                       v
   +-----------+        +-------------------+
   | Postgres  |        | Flutter/Android   |
   | (managed) |        | print station     |
   +-----------+        | (3nStar bridge)   |
                        +---------+---------+
                                  | Bluetooth (Classic/SPP)
                                  v
                        +-------------------+
                        | 3nStar PPT305BT   |
                        | label printer     |
                        +-------------------+

   Django  --- HTTPS ---> Twilio API ---> Owner phone (SMS x2: signup + lottery result)
```

**Actors / external systems**
- **Owner** — uses the public form and the SMS edit link; no login.
- **Admin / Volunteer** — logged-in staff (same privileges in V1).
- **Twilio** — outbound SMS: signup confirmation + lottery results.
- **3nStar PPT305BT** — thermal label printer, reachable only via its Android SDK.
- **Flutter/Android app** (`../vet_app`) — the print station; wraps the 3nStar native bridge.

---

## 3. Component View

```
+---------------------------------------------------------------+
|                        Django Web App                         |
|                                                               |
|  accounts/   login (admin+volunteer), sessions (weak auth)    |
|  events/     Event CRUD, open/close window, QR/URL generation;|
|              back-office via Django admin                     |
|  register/   public owner form (EN/ES), validation, 6-animal  |
|              cap, edit-via-token (add-while-open rules)       |
|  lottery/    random selection, sequential AnimalID assignment |
|  sms/        Twilio integration, signup + result templates    |
|  clinic/     volunteer lookup/edit/add/remove, check-in,      |
|              print (sets printed_at); admin manual entry +    |
|              AnimalID assignment                              |
|  printing/   label-payload endpoint for the print station     |
|  export/     CSV/XLSX download of an event's registrations    |
+----------------------+----------------------------------------+
                       | ORM
                       v
                +--------------+
                |  PostgreSQL  |
                +--------------+
```

| Component | Responsibility | Satisfies |
|---|---|---|
| `accounts` | Username/password login; both roles share privileges | FR-30, FR-32 |
| `events` | Create/configure events; `open_at`/`close_at` window (auto close, no manual lock); unique slug; QR/URL download; back-office via Django admin | FR-1..FR-4, FR-34 |
| `register` | Public form; EN/ES; per-animal dynamic fields; 6-animal cap; required owner fields; stores chosen language; confirmation; token edit (add-while-open, add-disabled-after-close) | FR-5..FR-11, FR-20..FR-22, FR-33 |
| `lottery` | Random shuffle + select whole registrations to X/Y caps; assign sequential AnimalIDs; set statuses | FR-12..FR-15 |
| `sms` | Send signup-confirmation + lottery-result SMS via Twilio in the registration's stored language | FR-16..FR-19 |
| `clinic` | Lookup by AnimalID/name/phone; edit; add; remove; check-in; print → sets `printed_at`; admin manual entry create + AnimalID assignment | FR-23..FR-28, FR-35..FR-37 |
| `printing` | Serve label payload (owner + grouped pet labels) to the print station | FR-28, NFR-4 |
| `export` | CSV/XLSX export with the agreed columns | FR-29 |

---

## 4. Technology Stack

| Layer | Choice | Rationale |
|---|---|---|
| Web framework | **Django** | Built-in admin, auth, forms+validation, i18n, ORM, CSV helpers map directly onto the requirements → least custom code. Lean on Django admin for back-office CRUD. |
| DB | **PostgreSQL** | Concurrent check-in writes rule out SQLite |
| SMS | **Twilio** REST API | Simple, cheap, pay-per-message |
| Hosting | **Render** (PaaS) | Managed Postgres, auto-HTTPS, deploy-from-GitHub, minimal ops |
| WSGI | gunicorn | Standard for Django on Render |
| Print station | Existing **Flutter/Android** app | Only path to the 3nStar printer (Bluetooth Classic/SPP — Web Bluetooth can't reach it) |
| i18n | Django translation + per-owner language on SMS | EN/ES |
| QR generation | `qrcode` (Python) → JPG/PNG | For flyer downloads |

---

## 5. Data Architecture

Entities (full field lists in `Requirements.md` §5). Relationships:

```
Event 1──* Registration 1──* Animal
  │            │
  │            └── edit_token, animal_id, status, language, printed_at
  └── services_offered, x_seen, y_waitlist, open_at, close_at (auto close; no manual lock)

User (admin/volunteer)  ── standalone, role label only (same priv)
```

Notes:
- `AnimalID` is a sequential integer **from 1** (max 999), unique within the event, assigned to a
  **Registration** (identifies the owner + all their animals); **not** the DB primary key. It is
  assigned by the lottery (in shuffled order) or **manually by an admin** (next available
  number). Uniqueness is enforced by a DB constraint.
- `language` (EN/ES) chosen at signup is stored on the Registration and selects the SMS template.
- `edit_token` is an unguessable random value created at signup; the only auth for owner
  self-edit (FR-20).
- `printed_at` is set when labels print — the authoritative "showed up" signal (FR-35).
- `services_offered` on the Event drives which per-animal fields/checkboxes render (FR-9).
- Open/close is governed by `open_at`/`close_at`; there is no manual "lock" (Decision 8). The
  app treats the event as open for signups when `open_at ≤ now < close_at` and the lottery
  hasn't run.

---

## 6. Deployment

```
GitHub repo  --(push)-->  Render Web Service (Django + gunicorn)
                            |
                            +--> Render Postgres (managed, daily backups)

Environment variables (never in code):
  DATABASE_URL, SECRET_KEY, DEBUG=False, ALLOWED_HOSTS,
  TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER
```

Render provides: auto-HTTPS, health check, restart-on-crash, deploys from `prod`
(this repo uses dev → staging → prod; `prod` is the only live deployment source).
Managed Postgres provides: backups, scaling, no manual maintenance. This keeps the volunteer's
ops burden near zero (NFR-2).

---

## 7. Runtime Flows

### 7.1 Registration → signup SMS
```
Owner --> /r/EVENT (during [open_at, close_at)) --> register app renders form (lang toggle)
Owner submits --> validate (required owner fields, ≤6 animals) --> save Registration+Animals (+language)
              --> confirmation screen (FR-11)
              --> sms app: send signup-confirmation SMS #1 with edit link, in chosen language (FR-16/18)
```

### 7.2 Window closes → lottery → result SMS
```
At close_at:  events: window closed (auto) ; owner animal-add disabled (edit/remove still ok)

Admin --> "Run lottery" (single run)
lottery app: RANDOMLY shuffle registrations (not signup order)
            select whole people until X animals (selected)
            continue until Y animals (waitlisted)
            assign sequential AnimalIDs (1..) in shuffled order; set statuses
            enqueue result SMS per registrant (all outcomes, in stored language)
sms app:   render EN/ES template per outcome --> Twilio --> owner phone  (FR-17/18/19)

Post-lottery (admin, ad-hoc):
clinic app: admin creates a registration (owner+animals) and/or assigns the next AnimalID
            (DB enforces unique 1..999 within the event)         (FR-36/37)
```

### 7.3 Owner edit (token)
```
Owner --> /r/EVENT/edit/TOKEN (from SMS #1 or #2)
register app: validate token + window/check-in state
            --> render entry (add enabled only if window open; remove/edit always)
Owner edits/adds(while open)/removes --> save
```

### 7.4 Check-in + print
```
Volunteer (in Flutter app = WebView of site) --> enter AnimalID or search
clinic app: load Registration+Animals --> volunteer edits/adds/removes/checks-in
          --> "Print" button --> JS bridge --> native printLabel channel
                                 --> set printed_at on the registration (FR-35)
Flutter native --> 3nStar SDK --> labels (1 owner + pet labels grouping ~3 animals each)
```

---

## 8. Print Station Integration (decided — Option B)

The browser cannot reach the 3nStar printer (it speaks Bluetooth Classic/SPP, which Web
Bluetooth cannot address — and it isn't iOS/MFi-certified, so the station is Android-only), so the
Flutter/Android app is required for
printing. **Decision 5 = Option B (WebView shell):** the Flutter app is a thin wrapper over the
responsive website and exposes the existing native `printLabel` platform channel to the page via
a JS bridge. **One UI** (the website); the page's "Print" button invokes the bridge.

All clinic-side UI lives in Django; the Flutter app only contributes the native print capability
and reuses the existing 3nStar bridge + label layout from `../vet_app` (NFR-4). Printing writes
`printed_at` on the registration (FR-35).

**Label layout:** one owner label + **pet labels that group ~3 animals each** (exact count set
after print testing) — not one label per animal.

(Option A — Flutter app as a standalone API client with its own UI — was rejected to avoid a
second UI.)

---

## 9. Security & Authentication

- Admin/volunteer: Django session auth, username/password, **same privileges** (FR-30).
- Owner self-edit: **no login**; gated by the unguessable `edit_token` and the window/check-in
  state (FR-20, FR-21, FR-22). Tokens are scoped to one registration.
- HTTPS everywhere (NFR-2); no public listing of registrations (FR-32).
- Twilio credentials and `SECRET_KEY` come from environment variables, never the repo (NFR-3).
- V1 accepts "weak" auth by design (single clinic, trusted users).

---

## 10. Internationalization

- Django translation catalogs for EN/ES cover the public form and both SMS templates (FR-33).
- The owner's chosen `language` is stored on the Registration and drives the SMS language (FR-18).
- Admin/volunteer UI is **English-only** in V1 (Decision 7).

---

## 11. Configuration & Secrets

All environment-driven (see §6). No credentials in code or in git. Event-level config (open/close
times, X, Y, services, languages) is set per event by the admin (FR-1).

---

## 12. Observability (light, V1)

- Django logging of lottery runs, SMS send attempts/successes, and print requests.
- Twilio delivery status can be logged from its webhook (optional in V1).

---

## 13. Decisions & Open Items

**Resolved (see `Decisions.md`):**
1. ✅ Print integration → **Option B** (Flutter WebView shell) (§8).
2. ✅ Edit-link window → from signup until check-in/event close; two-SMS flow.
3. ✅ SMS → two touchpoints (signup confirmation + lottery results); courtesy text to not-selected.
4. ✅ AnimalID → **sequential from 1, max 999** (in shuffled order; start value confirmed = 1).
5. ✅ Waitlist promotion → none in V1; `printed_at` tracks attendance.
6. ✅ Lottery → single run; admin can manually add entries & assign AnimalIDs.
7. ✅ Admin/volunteer UI → English-only.
8. ✅ Registration open/close → **timestamp-driven (`open_at`/`close_at`); no manual lock**.
9. ✅ Pet labels → grouped (~3/label, exact count by print testing).

**Still open:**
- Concurrency at check-in — Postgres chosen to absorb concurrent volunteer writes; verify with a
  load check at one busy event.
