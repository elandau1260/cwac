# Architecture — Veterinary Clinic Pre-Registration (V1)

**Status:** Draft for review
**Last updated:** 2026-08-03
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
- **Admin / Volunteer** — logged-in staff. **Admin-only:** create/configure/delete events, run lottery, export; **both roles:** all clinic operations (Decision 16).
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
|              print (sets printed_at); manual entry, both +    |
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
| `accounts` | Username/password login; **Admin-only** = event CRUD + lottery + export (`is_staff=True` → Django admin); **both roles** = clinic operations (Volunteer `is_staff=False`) | FR-30, FR-32 |
| `events` | Create/configure events; `open_at`/`close_at` window (auto close, no manual lock); per-event applicant cap Z; unique slug; QR/URL download; delete entire event; back-office via Django admin | FR-1..FR-4, FR-34, FR-38, FR-39 |
| `register` | Public form; EN/ES; per-animal dynamic fields; 6-animal cap (≥1 animal; edit-form max tracks current count); required owner fields; SMS-consent checkbox (default on); stores chosen language; confirmation; token edit (add-while-open, add-disabled-after-close); edit-link shows lottery result; SMS opt-out toggle | FR-5..FR-11, FR-20..FR-22, FR-33, FR-41, FR-42 |
| `lottery` | Random shuffle + select whole registrations to X/Y caps; assign sequential AnimalIDs; set statuses; single-run guard (manual click + noon auto-run) | FR-12..FR-15, FR-40 |
| `sms` | Send signup-confirmation + lottery-result SMS via Twilio (Messaging Service) in the registration's stored language; **fire-and-forget** (gate: `not sms_opt_out`; one send per reg, 2xx→`sent` (accepted) / 4xx→`failed` (sync) / 5xx→`unknown`, never retried); STOP/START handled provider-side by Advanced Opt-Out (not mirrored; async `21610` unobserved) | FR-16..FR-19, FR-42, FR-43 |
| `clinic` | Lookup by AnimalID/name/phone; edit; add; remove; check-in; print → sets `printed_at`; manual entry create + AnimalID assignment (both roles; assigning an ID to a `registered`/`not_selected` row admits it → `selected`) | FR-23..FR-28, FR-35..FR-37 |
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
  │            └── edit_token, animal_id, status, language, printed_at,
  │                sms_opt_out (app consent), result_sms_state/_sent_at (fire-and-forget)
  └── services_offered, x_seen, y_waitlist, z_applicants, open_at, close_at (auto close; no manual lock)

(no SMS-specific models — delivery is fire-and-forget; STOP/START are Twilio's, not mirrored)

User (admin/volunteer)  ── standalone; differentiated privileges (Decision 16)
```

Notes:
- `AnimalID` is a sequential integer **from 1** (max 999), unique within the event, assigned to a
  **Registration** (identifies the owner + all their animals); **not** the DB primary key. It is
  assigned by the lottery (in shuffled order) or **manually by staff (admin or volunteer)** (next
  available number; assigning an ID to a `registered`/`not_selected` row admits it → `status='selected'`).
  Uniqueness is enforced by a DB constraint.
- `language` (EN/ES) chosen at signup is stored on the Registration and selects the SMS template.
- `edit_token` is an unguessable random value created at signup; the only auth for owner
  self-edit (FR-20).
- `printed_at` is set when labels print — the authoritative "showed up" signal (FR-35).
- `services_offered` on the Event drives which per-animal fields/checkboxes render (FR-9).
- Open/close is governed by `open_at`/`close_at`; there is no manual "lock" (Decision 8). The
  app treats the event as **open for signups iff `status == 'live'` and `open_at ≤ now < close_at`**
  (the `live` stage is required — a `draft`/non-live event rejects signups even inside the window;
  once the lottery runs, `status` advances past `live`, which also closes signups). **The stored
  `status` column holds only discrete admin stages
  (`draft`/`live`/`lottery_run`/`active`/`completed`); "open" vs "closed" is a computed read-time
  label, never stored (R-3).**

---

## 6. Deployment

```
GitHub repo  --(push)-->  Render Web Service (Django + gunicorn)
                            |
                            +--> Render Postgres (managed, daily backups)

Environment variables (never in code):
  DATABASE_URL, SECRET_KEY, DEBUG=False, ALLOWED_HOSTS, PUBLIC_BASE_URL (canonical HTTPS origin
  for SMS edit-links), TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
  TWILIO_MESSAGING_SERVICE_SID (MG…; sends + Advanced Opt-Out), TWILIO_FROM_NUMBER (dev fallback only)
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
Owner submits --> validate (required owner fields, ≥1..≤6 animals) --> save Registration+Animals
              (+language; +sms_opt_out from consent checkbox, default False = consent)
              --> confirmation screen (FR-11)
              --> if consented: sms app sends signup-confirmation SMS #1 with edit link, in chosen language (FR-16/18)
              --> if declined: no SMS; edit link shown on-screen so they can return (FR-42)
```

### 7.2 Window closes → lottery → result SMS
```
At close_at:  events: window closed (auto) ; owner animal-add disabled (edit/remove still ok)

Trigger (single run — cannot double-run):
  Admin --> "Run lottery"                                   (FR-12)
    OR
  Render Cron Job (hourly) runs `run_due_lotteries`, firing each event past its
  noon deadline (event tz, day after `close_at`) that is not yet run   (FR-40)

lottery app: inside transaction.atomic(): lock + reload the Event row (select_for_update),
            then re-check `lottery_run_at is None`; RANDOMLY shuffle registrations
            (not signup order)
            select whole people until X animals (selected)
            continue until Y animals (waitlisted)
            assign sequential AnimalIDs (1..) in shuffled order; set statuses
            set `event.lottery_run_at = now` (the durable single-run guard)
            enqueue result SMS per registrant (all outcomes, in stored language)
sms app:   fire-and-forget: atomically claim `result_sms_state null→sending` (committed before the
           POST), then classify 2xx→`sent` (accepted), 4xx→`failed` (sync), **5xx/conn/timeout/no-response→`unknown` (process crash leaves `null`/`sending`)**
           (never retried). Render EN/ES template --> Twilio (Messaging Service) --> owner phone
           (FR-17/18/19). Send gated on `not sms_opt_out` only (FR-42); STOP/START/HELP handled
           provider-side by Advanced Opt-Out (not mirrored, no webhook — a blocked number is accepted
           `sent`; the async `21610` is unobserved). URLs via `absolute_url`/`PUBLIC_BASE_URL`

Post-lottery (staff, ad-hoc — both roles):
clinic app: staff (admin or volunteer) creates a registration (owner+animals) and/or assigns the next AnimalID
            (assigning an ID to a registered/not_selected row admits it: status → selected);
            (DB enforces unique 1..999 within the event)         (FR-36/37)
```

### 7.3 Owner edit (token)
```
Owner --> /r/EVENT/edit/TOKEN (from SMS #1 or #2)
register app: validate token + window/check-in state
            --> render entry (add enabled only if window open; remove/edit until check-in/event-completion)
            --> always show status banner: AnimalID / "not selected" / "pending" / checked-in (FR-41)
            --> SMS-preference toggle -> sets sms_opt_out (FR-42)
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

- Admin/volunteer: Django session auth, username/password. **Admin-only:** event create/configure/delete, run lottery, export — enforced via a `role == admin` mixin on custom views plus `is_staff` gating on the Django admin (Admin provisioned `is_staff=True`, Volunteer `is_staff=False`) (FR-30/Decision 16). **Both roles:** all clinic operations (lookup, edit, add, remove, check-in, print, manual entry, assign AnimalID).
- Owner self-edit: **no login**; gated by the unguessable `edit_token` and the window/check-in
  state (FR-20, FR-21, FR-22). Tokens are scoped to one registration.
- HTTPS everywhere (NFR-2); no public listing of registrations (FR-32).
- Twilio credentials and `SECRET_KEY` come from environment variables, never the repo (NFR-3).
- There are **no Twilio webhooks** in V1 — STOP/START/HELP are handled provider-side by Advanced
  Opt-Out on the Messaging Service, so every POST (signup/edit) uses normal CSRF protection.
- V1 accepts "weak" auth by design (single clinic, trusted users).

---

## 10. Internationalization

- Django translation catalogs for EN/ES cover the public form and both SMS templates (FR-33).
- The owner's chosen `language` is stored on the Registration and drives the SMS language (FR-18).
- Admin/volunteer UI is **English-only** in V1 (Decision 7).

---

## 11. Configuration & Secrets

All environment-driven (see §6). No credentials in code or in git. Event-level config (open/close
times, X, Y, Z, services, languages) is set per event by the admin (FR-1, FR-38).

---

## 12. Observability (light, V1)

- Django logging of lottery runs, SMS send attempts/outcomes (sent/failed/unknown), and print
  requests. (Delivery is fire-and-forget; no delivery-status webhook is received — `result_sms_state`
  reflects only the send response.)

---

## 13. Decisions & Open Items

**Resolved (see `Decisions.md`):**
1. ✅ Print integration → **Option B** (Flutter WebView shell) (§8).
2. ✅ Edit-link window → from signup until check-in/event close; two-SMS flow.
3. ✅ SMS → two touchpoints (signup confirmation + lottery results); courtesy text to not-selected.
4. ✅ AnimalID → **sequential from 1, max 999** (in shuffled order; start value confirmed = 1).
5. ✅ Waitlist promotion → none in V1; `printed_at` tracks attendance.
6. ✅ Lottery → single run; **staff (admin or volunteer)** can manually add entries & assign AnimalIDs (assigning an ID to a `registered`/`not_selected` row admits it → `selected`).
7. ✅ Admin/volunteer UI → English-only.
8. ✅ Registration open/close → **timestamp-driven (`open_at`/`close_at`); no manual lock**.
9. ✅ Pet labels → grouped (~3/label, exact count by print testing).
10. ✅ Lottery trigger → **hybrid**: admin-run, or auto-run at noon (event tz) day-after-`close_at` (FR-40; plan R-4).
11. ✅ Event deletion → admin can delete an entire event behind a confirmation (FR-39; plan R-9).
12. ✅ Applicant cap → per-event **Z** (max registrations) gates new signups (FR-38; plan R-10).
13. ✅ Owner status visibility + SMS consent → edit-link page always shows the result; signup consent checkbox defaults on, toggleable via the edit link (FR-41/FR-42).
14. ✅ Twilio budget + opt-out/consent wording → approved: signup consent checkbox (default on) + "Reply STOP to opt out" (Decision 13).
15. ✅ SMS delivery → **fire-and-forget** (one send per registration: 2xx→`sent` (accepted), 4xx→`failed` (sync), 5xx/conn/timeout/no-response→`unknown` (process crash leaves `null`/`sending`); **never retried**, so at-most-once is trivially true); STOP/START handled provider-side by Twilio Advanced Opt-Out (not mirrored, no webhook; async `21610` unobserved). Send gated on `not sms_opt_out`; URLs via `PUBLIC_BASE_URL` (FR-42/43).
16. ✅ Admin/volunteer privileges → **differentiated**: Admin-only = event create/configure/delete + run lottery + export; both roles = all clinic operations. Admin `is_staff=True`, Volunteer `is_staff=False`; enforced via a `role == admin` mixin + Django-admin `is_staff` gate (FR-30/Decision 16).

**Residual verification risks (not open decisions):**
- Check-in concurrency — resolved by design (Postgres + the unique AnimalID index); verify under
  load at the first busy event.
- SMS delivery — best-effort by nature (phones off, carrier blocks); fire-and-forget (one send per
  registration, never retried) cannot guarantee delivery — backstopped by the edit-link status page.
