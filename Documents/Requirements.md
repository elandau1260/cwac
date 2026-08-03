# Veterinary Clinic Pre-Registration — Requirements (V1)

**Status:** Draft for review
**Last updated:** 2026-08-03
**Source:** Email thread `communications/Re_Clinic_Pre-Registration.txt` + follow-up decisions (see `Decisions.md`)

---

## 1. Overview / Vision

A simple web app for the Admin's community vet clinics (City of Oakland). The clinics are
oversubscribed — people line up before 9am and still don't get seen. This app replaces
"first in line" with a **fair lottery**, and collects owner/pet information ahead of time so
that **check-in is fast and labels can be printed** instead of hand-written onto consent forms.

The end-to-end journey: owner pre-registers online during the open window (gets an immediate
confirmation + edit link) → the window **closes** at `close_at` → the admin runs a lottery that
randomly selects which people/animals are seen → all consenting owners are notified by SMS with the result
(selected/waitlisted receive a sequential **AnimalID**) → at the clinic a volunteer enters the
AnimalID, edits as needed, and **prints labels**.

---

## 2. Scope

### In scope (V1)
- Public pre-registration form (mobile-first, EN/ES toggle), open during a configured window
- **Immediate signup-confirmation SMS** (to owners who consent) with an edit link; owners can edit **and add** animals while the window is open
- Registration **closes automatically at `close_at`** — after that, owners can edit/remove but not add
- Admin "Create Event" with per-event configuration + unique sign-up URL + downloadable QR code
- Random lottery (selects whole registrations to fill X seen / Y waitlisted); **single run**; **lottery-result SMS** to all consenting registrants
- Owner self-edit via the SMS link (edit/remove always; **add only while open**)
- Clinic-side: volunteer looks up by AnimalID (or name/phone), **edits** (including **adding**
  animals), prints labels; printing tags the entry **`printed`** (attendance)
- Admin can **manually create registrations** and **assign AnimalIDs** for edge cases (walk-ins, etc.)
- Admin data export to Excel/CSV
- Two logins (admin + volunteer) with the **same privileges**

### Out of scope (V1 — explicitly excluded)
- Multi-tenant / multi-organization SaaS (single clinic only)
- PetPoint integration
- Inventory, multi-station queues, grooming, vet-prescription workflows (that's `vet_app` V2 territory)
- Web-Browser-based label printing (V1 uses the existing Flutter/Android print bridge; a future
  Web-Bluetooth-capable printer could remove the app download)
- Guaranteed appointment time slots (owners are told they'll be seen, but no booked time)
- Formal waitlist promotion / automated no-show re-lottery (volunteer checks in whoever shows; see §7.6)
- A manual "lock" button — registration open/close is timestamp-driven (Decision 8)

---

## 3. Users & Roles

| Role | Who | Can do |
|---|---|---|
| **Owner** (public, no login) | Pet owner registering on their phone | Register (during open window), edit own entry via SMS link |
| **Admin** | Admin | Create/configure events, run lottery, manually add entries & assign IDs, view & export data, edit any entry |
| **Volunteer** | Clinic staff at check-in | Look up, edit (incl. add animals), print labels, export |

> **Note:** In V1, Admin and Volunteer have the **same privileges**. The role label exists for
> clarity/logging only.

---

## 4. Key Concepts / Glossary

- **Event** — one clinic day. **Stored lifecycle (admin-driven stages):**
  `draft → live → lottery_run → active → completed`. Separately, whether the form is **open** or
  **closed** for new signups is a **computed, read-time label** derived from `open_at`/
  `close_at`/`lottery_run_at` (R-3) — it is **never stored**. The form accepts new signups only
  during `[open_at, close_at)`; running the lottery, activation, and
  completion are admin actions (timestamp-driven, **no manual lock** — Decision 8).
- **Open window** — the period `[open_at, close_at)` during which the public form accepts new
  signups **and** owners can add animals.
- **Close** — at `close_at` the form stops accepting new signups and owner animal-add is disabled
  (edit/remove still allowed). Automatic.
- **Registration (Entry)** — one owner's submission for an event. Contains owner info + animals.
- **Animal** — one pet within a registration.
- **AnimalID** — a sequential integer **starting at 1** (1, 2, 3, …, max **999**), assigned in the lottery's **shuffled** order to selected + waitlisted
  registrations, or **manually by an admin** (next available number). One per registration
  (identifies the owner + all their animals). The volunteer types it at check-in to pull the
  record. Sequential numbering makes it easy to hand out pre-numbered stickers and "call the next
  animal" on clinic day.
- **Lottery** — **random** selection of whole registrations (people) — explicitly **not** in
  signup order, so people who had to borrow a phone aren't disadvantaged. Selection fills the X/Y
  caps (may overshoot each by up to 6 animals). **Runs once.** IDs are then assigned sequentially.
- **Edit token** — an unguessable per-registration token in the SMS link that lets an owner edit
  their own entry without logging in.
- **Printed** — flag + timestamp set when labels are printed for a registration; the authoritative
  "the owner showed up" signal.

---

## 5. Data Model

### Event
| Field | Notes |
|---|---|
| `slug` / sign-up code | Unique, used in URL (e.g. `/r/OAK-AUG26`) |
| `name`, `description` | Shown on the form / flyer |
| `date`, `location` | |
| `open_at`, `close_at` | The signup window. Close is automatic; no manual lock. Admin may adjust these times. |
| `x_seen` | Number of animals to be seen |
| `y_waitlist` | Number of animals on the waitlist |
| `z_applicants` | Max registrations (owners) per event (FR-38); admin-configured. Gates only brand-new signups (existing owners may still add animals). |
| `services_offered` | Subset of: `flea_deworming`, `microchip`, `vaccination`, `vet` |
| `status` | Stored stages `draft` → `live` → `lottery_run` → `active` → `completed`; the **open↔closed** label is computed from `open_at`/`close_at`/`lottery_run_at`, never stored (R-3) |
| `languages` | `EN`, `ES` (which the public form offers) |

### Registration (one per owner per event)
| Field | Notes |
|---|---|
| `id` | Internal |
| `event` | FK |
| `animal_id` | Sequential from 1 (max 999); assigned by the lottery or manually by admin; nullable until then |
| `status` | `registered` → `selected` / `waitlisted` / `not_selected` → `checked_in` |
| `edit_token` | For the SMS edit link (created at signup) |
| `language` | **EN/ES the owner chose at signup — drives the SMS language** |
| `printed_at` | Set when labels print = owner showed up (nullable) |
| `sms_opt_out` | Boolean (default **false**) — **application-level consent only** (per-registration). Set by the signup consent checkbox or the edit-link toggle (FR-42). A *separate* phone-level provider block (`sms.PhoneBlock`, written only by inbound STOP/START) is the other dimension (FR-43); a send requires **both** this flag false **and** no provider block. When either blocks it, no SMS is sent — the owner tracks status via the edit link (FR-41) |
| `result_sms_state` / `result_sms_sent_at` | Denormalized rollup of the registration's `sms.SmsAttempt`s ("did this reg get its result SMS?") — `null`/`sending`/`sent`/`failed_permanent`/`unknown`; `sent_at` set on success (FR-17). |

**SMS delivery models (`sms` app):**
- `sms.PhoneBlock(phone, blocked_at, reason)` — phone-level provider block; one row = blocked. **Written only by the inbound STOP/START webhook** (never by a send/callback); a `21610` is a send failure, not a block. Twilio-only (FR-43).
- `sms.SmsAttempt(registration FK, purpose, callback_token, message_sid, is_initial, retry_of, retry_claimed_at, state, provider_status, provider_error_code, retryable, reconciled, created_at)` — one row per Twilio send try. `purpose` ∈ signup/result (rollup + retry scoped to result). Atomic initial claim via unique `(registration, purpose) WHERE is_initial`; one-consumer retry via unique `retry_of` + `retry_claimed_at`. `callback_token` is embedded in the per-message `StatusCallback` URL so a callback reconciles the attempt even with no captured SID; `provider_status` advances monotonically (terminal sticky); `provider_error_code`/`retryable` persist the callback's failure classification. State: `sending`/`sent`/`failed_permanent`/`unknown` (5xx→`unknown`; nothing auto-retried on a timer).
| **Owner fields (all required)** | first name, last name, phone, email, address |
| `created_at`, `updated_at`, `created_by` | owner (self) vs admin/volunteer |

### Animal
| Field | Notes |
|---|---|
| `registration` | FK |
| `name`, `species`, `age`, `breed`, `color` | |
| `sex` | Male / Female / Neutered Male / Spayed Female |
| `services_requested` | Flags for each service the event offers |
| `last_vaccinated_date` | Asked if vaccination offered |
| `medical_concern` | Free text, asked if vet offered |

> **No weight** in V1 (per the Admin). A registration requires **at least 1 animal** (FR-7), and
> **max 6 animals** is enforced for **owner** self-signup/edit during the open window. The cap
> blocks owner **additions** beyond 6 but never a volunteer/admin adding manually, and an owner
> may still edit/remove a record that a volunteer previously grew past 6 (the edit form's max
> tracks the current count). Services offered vary per event, so the per-animal form is built
> dynamically from `event.services_offered`.

### User (admin / volunteer)
`username`, hashed `password`, `role` (label only — same privileges in V1).

---

## 6. Event Configuration

When creating an event, the admin sets:
- Name, description, date, location
- **Open and close times** (`open_at`, `close_at`) — the signup window
- **X** (animals seen), **Y** (waitlist animals), and **Z** (max registrations/owners — FR-38)
- Services offered (checkboxes for flea/deworming, microchip, vaccination, vet — excludes
  grooming and spay/neuter, which are handled elsewhere)
- Languages offered (EN/ES)

The admin can then **download the sign-up URL and a QR-code image (JPG)** for flyers. Staff who
refer people (shelter front desk, animal control, HAPI, Project Pet) point owners at that URL/QR.
The admin may adjust the open/close times at any time (e.g., to close early).

---

## 7. User Flows

### 7.1 Admin creates & configures an event
Admin logs in → Create Event → fills config (incl. open/close times) → saves → downloads sign-up
URL + QR code for the flyer. The form is live during `[open_at, close_at)`.

### 7.2 Owner pre-registers → signup SMS
Owner opens the sign-up URL/QR (during the open window) → picks language → enters owner info
(name, phone, email, address — all required) + animals + per-animal services/questions →
**checks/unchecks an SMS-consent box ("Send me updates by text", checked by default — FR-42)** →
submits → sees a confirmation screen. If they left the box checked, they **immediately receive SMS
#1**: *"You're registered for [Event]. Edit your info/animals here: [edit link]. We'll text you when
the lottery runs."* (If unchecked, no SMS — the edit link is shown on-screen so they can still
return, and they can re-consent later via the edit link.) No guaranteed time is stated. The chosen
language is saved on the registration.

### 7.3 Registration closes (automatic)
At `close_at` the form stops accepting new signups. Owners can still **edit/remove** animals via
their edit link, but can no longer **add**. The admin can always add/edit.

### 7.4 Lottery runs → result SMS
The lottery runs **once**, after close. The admin runs it manually — **or**, if it hasn't been
run by **noon (in the event's timezone) on the calendar day after `close_at`**, it runs
**automatically** (FR-40) so it can't be forgotten and result texts still go out at a civilized
hour. Both paths call the same single-run routine and cannot double-run. The algorithm:
1. **Randomly shuffle** all registrations (selection is random, not signup order).
2. Walk the list assigning **selected** and accumulating the **animal count** (the sum of animals
   across the selected registrations — **not** the number of registrants) until it reaches **X**
   animals seen (may overshoot by up to 6 animals).
3. Keep walking assigning **waitlisted** until the **animal count** reaches **Y** waitlist animals
   (may overshoot).
4. Remaining = **not_selected**.
5. Assign **AnimalIDs sequentially from 1** (in the shuffled order) to each selected + waitlisted
   registration.

Then **SMS #2** goes to **every consenting** registrant **in the language they chose at signup**:
- **Selected:** *"You're in for [Event]! Your AnimalID is 7. Bring this. [edit link]"*
- **Waitlisted:** *"You're on the waitlist for [Event]. AnimalID 7. [edit link]"*
- **Not selected:** *"You were not selected for [Event]. Thank you for registering — please try
  again next time."* (courtesy, no link)

**Post-lottery (admin):** the lottery is not re-run. To handle edge cases (walk-ins, people who
couldn't register online), the admin can **manually create registrations** (owner + animals) and
**assign an AnimalID** (next available number) to any registration. AnimalIDs share one 1–999
sequence per event (the database enforces uniqueness within the event).

### 7.5 Owner edits via SMS link
The edit link (`/r/EVENT/edit/TOKEN`) — sent in **SMS #1 to every consenting registrant**, and in **SMS #2 only to selected/waitlisted** — opens their entry
without login. They can edit owner + animal fields and **remove** animals at any time. They can
**add** animals **only while the window is open** (disabled after `close_at`). Once the
registration is **checked-in** (or the event completes), self-edit locks.

The edit-link page also **shows the owner's current result** (FR-41): their assigned **AnimalID**
if selected/waitlisted, a **"not selected"** notice once the lottery has run (or "pending" before),
and the checked-in/printed state on clinic day — visible **even after editing locks**, so an owner
can always learn their outcome without an SMS (e.g., if they declined texts or a text didn't
deliver). The page also lets the owner **change their SMS preference** (FR-42): turn texts on/off,
which sets `sms_opt_out`.

### 7.6 Clinic check-in + print (volunteer)
Volunteer logs in → selects event → enters **AnimalID** (or searches by name/phone) → record
loads. Volunteer can:
- Edit owner + animal info
- **Add** animals (e.g. a pet that wasn't pre-registered)
- Remove animals
- Mark the registration **checked in** (manual fallback if the printer is down)
- **Print labels** (one owner label + pet labels grouping the animals — see §8) via the print
  station → this sets `printed_at` (the authoritative "showed up" signal)

> **No-shows / waitlist:** there is no formal promotion in V1. If selected owners don't show, the
> volunteer checks in waitlisted (or walk-in) owners against remaining capacity. The waitlist is
> shown as an ordered list for reference. (Admin can also manually assign an AnimalID to
> effectively admit someone.)

### 7.7 Admin export
Admin downloads all registrations for an event as **Excel/CSV** (columns: owner name, phone,
address, email; per animal: name, species, age, sex, breed, color, services; plus status,
AnimalID, language, and `printed`). The Admin uses this offline to cross-reference vaccines due in
PetPoint.

---

## 8. Label Printing

The existing **Flutter/Android app** (`../vet_app`) is reused as the **print station** because
the **3nStar PPT305BT** thermal printer is reached only through its native Android SDK (a browser
can't get to it). What we keep: the native `printLabel` platform channel + label layout. What
changes: the data source moves from on-device local storage to **lookup by AnimalID from the web
backend**, and printing now writes `printed_at` on the registration.

Label content:
- **Owner label** (one per registration): Owner Name, Phone, Email, Address
- **Pet labels:** animals are **grouped onto labels** — target ~3 animals per label (Species, Name,
  Age, Sex, Breed, Color each). The exact count per label will be set after **print testing** on
  the 3nStar; this is not one-label-per-animal.

V1 default is **~3 animals per pet label**, adjustable based on what actually fits legibly.

**Integration (decided — Option B):** the Flutter app is a thin WebView over the responsive
website and exposes the existing native `printLabel` channel to the page via a JS bridge — one UI
(the website); the page's "Print" button invokes the bridge. (`Architecture.md` §8.)

---

## 9. Internationalization (EN/ES)

- Public registration form + owner-facing SMS support EN/ES via a language toggle.
- The owner's chosen `language` is **stored on the registration** and drives the SMS language.
- Admin/volunteer UI: **English-only** in V1 (Decision 7).

---

## 10. Authentication & Access

- Admin + Volunteer logins, **username/password**, same privileges in V1.
- "Weak" authentication is acceptable per the agreed scope (single clinic, trusted users).
- Owner-facing pages (register, edit-via-token) need **no login** — secured by the unguessable
  edit token and the event's open/closed window.

---

## 11. Technology & Hosting

| Layer | Choice |
|---|---|
| Web framework | **Django** — recommended because its built-in **admin, auth, forms+validation, i18n, ORM, and CSV helpers map directly onto these requirements**, so we write little custom back-office code. Lean on Django's admin for event config, manual entry management, and export. |
| Database | **PostgreSQL** (concurrent writes at check-in rule out SQLite) |
| SMS | **Twilio** via a **Messaging Service** (pay-per-message, ~1¢/text; Advanced Opt-Out + STOP/START + delivery-status webhooks hang off the service — FR-43) |
| Hosting | **PaaS — Render** (managed Postgres add-on, auto-HTTPS, deploy from GitHub). Railway is an alternative. |
| Print station | Existing **Flutter/Android** app (`../vet_app`) reused for the 3nStar printer |

---

## 12. Privacy & Data

- Collects PII (name, phone, email, address). Keep behind HTTPS and the admin login.
- No public listing of registrations.
- Retention: the admin may **delete an entire event** (FR-39) — cascading to all of its
  registrations and animals — from the event selector / Django admin, behind a confirmation
  warning. Otherwise event data is retained for records; there is no automatic expiry.

---

## 13. Open Questions / To Decide

**Resolved — see `Decisions.md`:**
- ✅ Not-selected notification → courtesy SMS to all (Decision 1)
- ✅ Edit-link window → from signup until check-in/event close; two-SMS flow (Decision 2)
- ✅ Waitlist promotion → none in V1; `printed` tracks attendance (Decision 3)
- ✅ AnimalID → sequential, in shuffled order, max 999 (Decision 4)
- ✅ Print integration → Option B, Flutter WebView shell (Decision 5)
- ✅ Lottery → single run; admin can manually add registrations & assign AnimalIDs (Decision 6)
- ✅ Admin/volunteer UI → English-only in V1 (Decision 7)
- ✅ Registration open/close → **timestamp-driven (`open_at`/`close_at`); no manual lock** (Decision 8)
- ✅ Pet labels → grouped (~3/label, exact count set by print testing) (Decision 9)
- ✅ Track the owner's chosen language → stored on registration, drives SMS language
- ✅ Lottery trigger → **hybrid**: admin runs it, or it auto-runs at noon (event tz) the day
  after `close_at` if not yet run (FR-40; plan R-4)
- ✅ Event deletion → admin can delete an entire event behind a confirmation (FR-39; plan R-9)
- ✅ Applicant cap → per-event **Z** (max registrations) gates new signups (FR-38; plan R-10)
- ✅ Owner status visibility → the edit-link page always shows the lottery result (FR-41)
- ✅ SMS consent/opt-out → signup checkbox defaults to **on**; owner can uncheck or toggle later
  via the edit link (FR-42); status still viewable without texts
- ✅ Twilio budget + opt-out/consent wording → approved (Decision 13)
- ✅ SMS delivery + provider-side STOP/START → at-most-once/best-effort delivery; two-dimension
  opt-out (application consent vs phone-level provider block) via a Messaging Service with Advanced
  Opt-Out (Decision 15; FR-43)

---

## 14. Future (beyond V1)

- Web-Bluetooth-capable printer → drop the app download, print from the browser.
- Multi-tenant / multi-org (the `vet_app` V2 SaaS direction).
- PetPoint integration / master animal history across events.
- Inventory, multi-station queues, vet-prescription workflows.
- Formal waitlist promotion / automated no-show re-lottery.

---

## Appendix A — Functional Requirements Index (for traceability)

Referenced by `Architecture.md` and `TraceabilityMatrix.md`.

### Functional Requirements

**Event management (admin)**
- **FR-1** Admin can create an event with full configuration (name, description, date, location, open/close times, X, Y, services offered, languages).
- **FR-2** Each event has a unique sign-up URL/slug.
- **FR-3** Admin can download the sign-up URL and a QR-code JPG.
- **FR-4** Event stored lifecycle (`draft → live → lottery_run → active → completed`); the **open↔closed** label is computed from `open_at`/`close_at`/`lottery_run_at` and never stored (R-3). The form accepts new signups only during `[open_at, close_at)` (timestamp-driven, no manual lock).
- **FR-34** After `close_at`, owners can edit/remove but **not add** animals; the admin can always add/edit regardless of state.
- **FR-38** Per-event **applicant cap Z** (admin-configured target max registrations/owners). Once reached, **new** signups are rejected with a friendly EN/ES "registration full" message; existing owners may still add animals. **Z is a soft cap** — concurrent signups at the boundary may push the count a few over Z, which is acceptable (no hard limit).
- **FR-39** Admin can **delete an entire event** (cascade to all its registrations/animals) from the event selector / Django admin, behind a confirmation warning.

**Owner registration (public, no login)**
- **FR-5** Public form accessible via the event URL/QR (during the open window).
- **FR-6** EN/ES language toggle on the public form.
- **FR-7** Owner submits owner info — first/last name, phone, email, address (**all required**) — + animals.
- **FR-8** Per-animal data: name, species, age, sex (M/F/NM/SF), breed, color; **no weight**.
- **FR-9** Per-animal services + questions built dynamically from `event.services_offered`.
- **FR-10** Max **6 animals** per registration enforced during the open window.
- **FR-11** Confirmation screen on submit (received; SMS to follow; no guaranteed time).

**Lottery**
- **FR-12** Admin runs the lottery (single run) after close; **random** selection of whole registrations (not signup order).
- **FR-13** The selected **animal count** targets X, the waitlist **animal count** targets Y (each may overshoot by ≤ max animals/person). Selection is by whole registrations, but X/Y are caps on the total number of **animals**, not registrants.
- **FR-14** **AnimalID assigned sequentially from 1** (max 999), in shuffled order, to each selected + waitlisted registration; unique within the event.
- **FR-15** Statuses set: `selected` / `waitlisted` / `not_selected`.
- **FR-40** If the lottery has not been run manually, it **runs automatically at noon (in the event's timezone) on the calendar day after `close_at`** (single-run; cannot double-run with a manual run).

**SMS (Twilio)**
- **FR-16** Send a **signup-confirmation SMS immediately on registration** to owners who consented (FR-42), containing an edit link.
- **FR-17** After the lottery, send a **result SMS to every consenting registrant** in their chosen language; selected/waitlisted include the AnimalID + edit link; not-selected receive a courtesy text with **no link**. Delivery is **at-most-once and best-effort**: each send is a `SmsAttempt` classified by what is proven — 2xx→`sent`, a pre-acceptance 4xx/`21610`→`failed_permanent`, and **5xx/timeout/connection-loss/crash→`unknown`** (a 5xx does not prove the message was not created). Nothing is auto-retried on a timer; only a callback-confirmed terminal-transient failure is retried, so each registrant gets at most one send the app believes succeeded (no double-texts). Not guaranteed, backstopped by the edit-link status page (FR-41).
- **FR-18** SMS language follows the owner's chosen language (stored on the registration).
- **FR-19** **Not-selected** consenting registrants receive a courtesy result SMS (Decision 1).
- **FR-42** The signup form has an **SMS-consent checkbox (checked by default)**; unchecking it (or toggling later via the edit link) sets the **application-consent** flag `sms_opt_out` and skips SMS for that registration. This toggle is **application-level only** — it cannot clear a phone-level provider block (FR-43). The signup confirmation is still shown on-screen; status remains viewable on the edit-link page (FR-41). Opt-out/consent wording confirmed: checkbox + "Reply STOP to opt out" on every SMS (Decision 13).
- **FR-43** **Provider-side opt-out + delivery reconciliation — two independent dimensions.** Application consent (`sms_opt_out`, FR-42) is **per-registration and owner-controlled**. The **provider block** is a **separate, phone-level** record (`sms.PhoneBlock`) written **only** by Twilio, never by the website toggle. A send requires **both** clear. Concretely:
  - **STOP/START/HELP** arrive via an inbound-SMS webhook on the **Messaging Service** (Twilio Advanced Opt-Out, which posts `OptOutType` — the three documented values are uppercase **`STOP`** / **`START`** / **`HELP`**; the handler normalizes to uppercase), **authenticated by `X-Twilio-Signature`** (`RequestValidator`) — one of the two public POSTs exempt from CSRF. `STOP` upserts a `PhoneBlock` for the normalized `From`; `START` deletes it; `HELP` is a no-op (Twilio replies with its help text). The webhook writes **only** the provider block — **`START` never grants application consent**, so a registration the owner explicitly declined stays opted out.
  - A per-message **delivery-status callback** (`/sms/status/<callback_token>/`, the second signature-validated webhook) carries each attempt's opaque token in the URL, so it reconciles the matching `SmsAttempt` **even when no response/SID was captured** (the `unknown` case) and even if it arrives before the send handler finished. It advances `provider_status` **monotonically** (terminal states sticky; callbacks can arrive out of order) and records `provider_error_code`/`retryable`. **It does not write `PhoneBlock`** — a `21610` it carries only marks the attempt `failed_permanent` and logs (the block, if any, came from the authoritative STOP webhook). `21610` is **not** assumed synchronous, so it is a best-effort secondary signal; the inbound STOP/START webhook is the sole, authoritative opt-out writer.
  - Because the block is keyed by phone, it covers every registration sharing that number (R-2) and any created after the STOP. Re-consent of a blocked number requires START (the website toggle cannot override a provider block).

**Owner edit (token)**
- **FR-20** Edit link `/r/EVENT/edit/TOKEN` opens the entry without login (link sent in the signup SMS to every consenting registrant, and shown on the confirmation page to those who declined SMS; in the lottery-result SMS only to selected/waitlisted — never to not-selected).
- **FR-21** Owner can edit fields; **add and remove** animals while the window is open; **after `close_at`, add is disabled** (edit/remove still allowed); admin can always add.
- **FR-22** Edit link valid from signup **until the registration is checked-in or the event completes**.
- **FR-41** The edit-link page displays the owner's current result (assigned AnimalID for selected/waitlisted; "not selected" once the lottery has run; "pending" before; checked-in/printed state on clinic day) — visible even after self-edit locks, so SMS is not the only status channel.

**Clinic check-in (volunteer/admin)**
- **FR-23** Lookup by **AnimalID** or search by name/phone (fuzzy).
- **FR-24** Edit owner + animal info.
- **FR-25** **Add** animals.
- **FR-26** **Remove** animals.
- **FR-27** Mark registration `checked_in` (manual fallback).
- **FR-28** Print **owner label** + **pet labels (grouping ~3 animals each; exact count set by print testing)** via the print station.
- **FR-35** Printing labels sets `printed_at` (records the owner showed up).

**Admin manual entry management**
- **FR-36** Admin can manually create a registration (owner + animals), e.g. for walk-ins or people who couldn't register online (`created_by` = admin; the 6-animal cap is not enforced for admin/volunteer).
- **FR-37** Admin can assign/edit an **AnimalID** (sequential, max 999) on any registration, unique within the event (including manually-created entries).

**Data export**
- **FR-29** Admin downloads all registrations for an event as **Excel/CSV** with specified columns (incl. chosen language).

**Authentication & access**
- **FR-30** Admin + volunteer login (username/password), **same privileges** in V1.
- **FR-31** Owner public pages require **no login** (token-secured).
- **FR-32** HTTPS enforced; registrations not publicly listed.

**Internationalization**
- **FR-33** Public form + SMS available in EN/ES; the owner's chosen language is stored and used for SMS (admin/volunteer UI is English-only).

### Non-Functional Requirements
- **NFR-1** Mobile-first, thumb-friendly public UI.
- **NFR-2** Hosted on PaaS (Render) with managed Postgres, auto-HTTPS, minimal ops.
- **NFR-3** SMS via Twilio (credentials from environment, never hardcoded).
- **NFR-4** Label printing via the existing Flutter/Android 3nStar bridge.