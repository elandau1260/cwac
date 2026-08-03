# Implementation Plan — CWAC (Community Wellness Animal Clinic) Pre-Registration, V1

**Status:** Approved for build (2026-08-02)
**Companion docs:** `Requirements.md`, `Architecture.md`, `Decisions.md`, `TraceabilityMatrix.md` (this folder)

## Context

The Admin's community vet clinics (City of Oakland) are oversubscribed — owners line up before 9am and
still aren't seen. This app replaces "first in line" with a **fair lottery** and collects owner/pet
info ahead of time so **check-in is fast and labels print** instead of being hand-written onto
consent forms.

End-to-end journey: owner pre-registers online during the open window (gets confirmation + edit
link) → window **closes automatically** at `close_at` → admin runs a single **random lottery** →
all owners are notified by SMS (selected/waitlisted receive a sequential **AnimalID**) → at the
clinic a volunteer enters the AnimalID, edits as needed, and **prints labels**.

This is a **greenfield Django app** in `/home/dev/cwac` (today: only `Documents/`
and `communications/`, no code, no git). Full spec lives in `Documents/` (Requirements,
Architecture, Decisions, TraceabilityMatrix). **43 FRs (FR-1..FR-43) + 4 NFRs.**

### Locked scoping (confirmed with user)
- **Backend-first.** This plan delivers the complete Django backend + a print-payload endpoint with
  a **browser stub** so the clinic flow is fully testable without the printer. The Flutter
  WebView-shell conversion + native label-layout rewrite is **Phase 12 (outline only)** — a
  separate follow-up.
- **Comprehensive, internally phased** — all FRs covered, ordered build phases.
- **AnimalID starts at 1** (max 999).

> **Resuming after a context clear:** read this file + the four companion docs. Pick the lowest
> phase not yet done (see the task list / git history), read its row in **Build phases** below, and
> continue. The session task list does NOT survive a context clear — this file is the durable record.

---

## Stack & cross-cutting decisions

| Concern | Decision |
|---|---|
| Runtime | Python 3.12, Django 5.2 LTS, psycopg[binary] 3.2, gunicorn 23 |
| Config | Settings split `config/settings/{base,dev,prod}.py`; `django-environ` + `dj-database-url` |
| Static/serving | WhiteNoise 6.7 (manifest storage) + gunicorn |
| SMS | `twilio` 9.x behind a pluggable **backend** (`console` / `locmem`-test / `twilio`), creds from env only |
| i18n | Django `gettext` catalogs `locale/{en,es}` — public form + 2 SMS bodies; admin/clinic UI English-only |
| QR | `qrcode` 7.4 + Pillow 10 → JPG for flyers |
| Export | stdlib `csv` (streaming) + `openpyxl` 3.1 (XLSX) |
| Phones | `phonenumbers` 8.13 — US-region validate + E.164 normalize (SMS deliverability) |
| Auth | `accounts.User(AbstractUser)` + `role` label; session auth via `LoginRequiredMixin` |
| Timezone | `django-timezone-field` (per-event IANA select); custom admin form so `open_at`/`close_at` are entered **and** displayed in the event's tz (stored UTC, `USE_TZ=True`) — drives the per-event "noon" auto-lottery deadline |

**Window mechanism (FR-4/34) — read-time, no cron.** Source of truth = computed methods on `Event`,
never the `status` column. Render has no free cron; read-time is instantly correct and "no manual
lock" (Decision 8) fits a derived check. The `status` column stores only the **discrete admin-driven
stages** (draft / live / lottery_run / active / completed); the **displayed** open-vs-closed label is
computed live from `open_at`/`close_at`/`lottery_run_at`, so what the admin sees always matches
reality (no drift, no cron). The new-signup gate reads timestamps + `lottery_run_at` + the
applicant cap Z (R-10) — nothing else.

**AnimalID.** Starts at 1, max 999. Unique-per-event via Postgres **partial unique index**
`(event_id, animal_id) WHERE animal_id IS NOT NULL`.

**Services modeling.** Event carries 4 booleans (`offers_flea_deworming`, `offers_microchip`,
`offers_vaccination`, `offers_vet`) + `@property services_offered`. `Animal.services_requested` is a
`JSONField` list (subset of the event's offered keys). The public per-animal form renders fields
dynamically from these.

---

## Project layout

```
cwac/                               (repo root → GitHub repo + Render service name)
  manage.py                         (DJANGO_SETTINGS_MODULE=config.settings.dev)
  config/{urls,wsgi,asgi}.py
  config/settings/{base,dev,prod}.py
  requirements/{base,dev,prod}.txt  runtime.txt   render.yaml   .env.example   .gitignore
  accounts/   events/   register/   lottery/   sms/   clinic/   printing/   export/
  templates/   static/   locale/{en,es}/LC_MESSAGES/
  Documents/   communications/      (existing spec — committed as context)
```

`base.py` must set `AUTH_USER_MODEL='accounts.User'` and `DEFAULT_AUTO_FIELD` **before** any
migration is made.

---

## Data model

### `events.Event`
- `slug` SlugField(unique, max 40) → `/r/<slug>/`; `name` CharField(200); `description` TextField(blank); `date` DateField; `location` CharField(200, blank)
- `open_at`, `close_at` DateTimeField(db_index); `x_seen`, `y_waitlist`, `z_applicants` PositiveIntegerField — **X** animals seen / **Y** waitlist animals / **Z** = soft applicant cap (target max registrations) per event: the point at which new signups stop; a small overshoot under concurrent signups is acceptable (R-10). All three are admin-configured per event (no hardcoded values).
- `timezone` CharField via `django-timezone-field` (IANA select, default `America/Los_Angeles`) — **per-event, admin-selectable**; sets when "noon" (the auto-lottery deadline) is **and the timezone in which `open_at`/`close_at` are entered and displayed**. `USE_TZ=True`; datetimes stored UTC; a custom admin form converts `open_at`/`close_at` to/from the event's `timezone` so the admin always sees/enters local times for that clinic.
- `offers_flea_deworming`, `offers_microchip`, `offers_vaccination`, `offers_vet` BooleanField(default=False)
- `languages` JSONField(default=list) — subset of `["en","es"]`
- `status` CharField(choices=draft/live/lottery_run/active/completed, default=draft) — the open↔closed distinction is a **computed display label** (from `open_at`/`close_at`/`lottery_run_at`), never stored (R-3)
- `lottery_run_at` DateTimeField(null, blank) — **durable** signal that permanently blocks signups
- `created_at`, `updated_at`
- **Methods (authoritative):** `@property services_offered`; `is_published()`; `signup_open(now=None)` = `is_published() and open_at ≤ now < close_at and lottery_run_at is None`; `at_capacity()` = `registrations.count() >= z_applicants` (**soft cap** — not locked; concurrent signups at the boundary may overshoot by a few, which is acceptable; R-10); `auto_run_deadline()` = noon (12:00 local) on the calendar day after `close_at`, computed in `self.timezone` (returns a tz-aware datetime for comparison against `timezone.now()`); `owner_can_add(reg)` = `signup_open() and reg.status != 'checked_in'`; `owner_can_edit(reg)` = `status != 'completed' and reg.status != 'checked_in'`. The **new-signup** view additionally requires `not at_capacity()` — Z gates only brand-new registrations, not an existing owner adding animals. The check + insert are deliberately **not serialized** (no Event-row lock): Z is a soft target and a few over is fine (R-10; TC-047). Displayed open/closed is computed live — no cached drift.

### `register.Registration`
- `event` FK(Event, related_name=registrations, CASCADE)
- `animal_id` PositiveIntegerField(null, blank)
- `status` choices: registered/selected/waitlisted/not_selected/checked_in (default registered)
- `edit_token` CharField(unique, db_index, default=`token_urlsafe(32)`) — 256-bit, only auth for self-edit
- `language` CharField(2, choices en/es, default en) — **chosen at signup, drives SMS**
- `printed_at`, `checked_in_at` DateTimeField(null, blank)
- `result_sms_state` CharField(null/sending/sent/failed_permanent/unknown, default null) —
  denormalized **rollup** of the registration's `sms.SmsAttempt`s (see below) for admin/export ("did
  this reg get its result SMS?"). `sent` once any attempt is accepted/delivered; otherwise reflects
  the latest attempt; set atomically on success. **There is no `failed_transient` value** — under
  at-most-once nothing is auto-retried on a timer (a 5xx is a server error, not proof of
  non-acceptance — see `SmsAttempt`).
- `result_sms_sent_at` DateTimeField(null, blank, set only when state=`sent`)
- `sms_opt_out` BooleanField(default=False) — **application-level consent only**, registration-local. Changed **only** by the owner: the signup consent checkbox (FR-42) and the edit-link toggle. It is **never** written by the inbound webhook or a provider block (FR-43). When True, signup + result SMS are skipped; status is still shown on the edit-link page (FR-41).
- `first_name`, `last_name` CharField(100); `phone` CharField(20) E.164; `email` EmailField; `address` CharField(300) — **all required**
- `created_by` choices self/admin (default self); `created_at`, `updated_at`
- **Meta.constraints:** `UniqueConstraint(fields=[event, animal_id], condition=Q(animal_id__isnull=False))`
- **classmethod** `next_animal_id(event)` = (max non-null animal_id in event)+1, else 1
- **property** `is_attended` = `printed_at is not None`

### `register.Animal`
- `registration` FK(Registration, related_name=animals, CASCADE); Meta `ordering=[id]` (stable print grouping)
- `name` CharField(100); `species` CharField(100); `age` CharField(30) — **free text** ("3 years"/"8 months")
- `breed`, `color` CharField(100, blank)
- `sex` choices **M/F/MN/FS** (Male / Female / Male-Neutered / Female-Spayed) — per the export spec
- `services_requested` JSONField(default=list); `last_vaccinated_date` DateField(null, blank); `medical_concern` TextField(blank)
- **No `weight` field** (FR-8/TC-009)

### `accounts.User`
`AbstractUser` + `role` choices admin/volunteer (default volunteer). **Same privileges V1** — role for logging only.

### `sms.PhoneBlock` (provider-side, phone-level opt-out)
- `phone` CharField(E.164, unique, db_index) — the **normalized** number (the inbound `From`, or the `To` of a send that returned `21610`)
- `blocked_at` DateTimeField(auto_now_add=True); `reason` CharField(choices: `stop` / `21610`)
- **One row = the number is blocked.** A `Registration` is eligible for SMS only when `not sms_opt_out` **and** no `PhoneBlock` exists for its normalized `phone` — **both** dimensions must be clear. **Only the inbound STOP/START webhook writes this model** (never `sms_opt_out`, and never a delivery callback — a `21610` is a send failure, not a block write; FR-43). START deletes the row; it does **not** change application consent, so a registration the owner explicitly declined stays opted out (TC-060). Keyed by phone (not registration), the block covers every registration sharing that number (R-2 duplicate phones) and any registration created after the STOP (TC-061).

### `sms.SmsAttempt` (one send try; Registration 1──* SmsAttempt)
The unit of a single Twilio send and the basis for **sound at-most-once** delivery + reconciliation.
- `registration` FK(Registration, related_name=sms_attempts, CASCADE); `purpose`
  CharField(choices: `signup` / `result`) — which message this attempt delivers. The rollup
  (`Registration.result_sms_state`) and the retry cap/sweep are scoped to `purpose='result'`; a
  signup attempt is a single best-effort send (not retried — the owner has the edit link on the
  confirmation page). `callback_token` SlugField(unique, db_index,
  default=`uuid4`/`token_urlsafe`) — an opaque token embedded in the **per-message** `StatusCallback`
  URL so a later callback can identify **this attempt** even when no response/SID was captured;
  `message_sid` CharField(null) — the Twilio Message SID, set on a 2xx response **or** the matching callback.
- **Atomic initial claim** — `is_initial` BooleanField(default=True), with
  `UniqueConstraint(fields=[registration, purpose], condition=Q(is_initial=True))`: the initial send
  is an atomic INSERT; a second worker that races (e.g. two notification workers) hits an
  `IntegrityError` and skips (TC-070). **One-consumer retry claim** — `retry_of` FK(self, null,
  related_name=retries) pointing at the reconciled-failed attempt being retried, with
  `UniqueConstraint(fields=[retry_of], condition=Q(retry_of__isnull=False))` (a source has at most
  one retry) plus `retry_claimed_at` DateTimeField(null); `retry_sms` atomically sets
  `retry_claimed_at` (`filter(pk=source.pk, retry_claimed_at__isnull=True).update(retry_claimed_at=now())`)
  before creating the child attempt — only the claimant proceeds (TC-071).
- `state` choices: `sending` / `sent` / `failed_permanent` / `unknown`. **No `failed_transient`** —
  classification is by what is **proven** (RFC 9110 §9.2.2: a non-idempotent POST's response does
  **not** prove no side effect): `sent` on a definitive acceptance (2xx + SID); `failed_permanent`
  on a 4xx that Twilio documents as a **pre-acceptance** rejection (invalid number/body) **or** a
  `21610` (blocked) — the message will not deliver, so it is terminal (it is **not** retried); an
  `unknown` on **5xx / connection error / timeout / no response / crashed worker** (a 5xx is a
  server error — it does **not** prove the message was not created).
- `provider_status` choices: null / `queued` / `sent` / `delivered` / `undelivered` / `failed`
  (written **only** by the delivery-status callback, **monotonic** — terminal states are sticky, so
  out-of-order callbacks cannot clobber them); `provider_error_code` CharField(null) — the Twilio
  `ErrorCode` from the callback; `retryable` BooleanField(null) — the persisted classification used
  by `retry_sms`: a terminal callback with a **non-permanent** code (`undelivered`/`failed` that is
  not `21610`/invalid-number) → `retryable=True`; a permanent code (`21610`, 21211 invalid number,
  …) → `retryable=False`. Persisted so selection survives a restart (TC-062/072). `reconciled`
  BooleanField(default=False) — set True once a callback reports a terminal provider status.
- `created_at`. The per-(registration,purpose) attempt count/cap are **derived from the set of
  `SmsAttempt` rows**, not from `updated_at` (which owner edits change).

---

## Key behavioral designs

### Lottery (`lottery/services.py`) — pure, injectable RNG
`run_lottery(event, *, rng=None, commit=True) → LotteryResult`. **Concurrency-safe single run:**
the whole body runs inside one `transaction.atomic()`. It first **locks and reloads the `Event`
row** (`Event.objects.select_for_update().get(pk=event.pk)`), then performs the single-run guard
on that locked row — `raise LotteryAlreadyRun if event.lottery_run_at is not None` (Decision 6).
Locking the Event row (not just the registrations) is what makes a manual click and the noon cron
unable to double-run: the second caller blocks until the first commits, re-reads a non-null
`lottery_run_at`, and exits (TC-050). Then `select_for_update()` on the event's `registered` rows:

0. Reload + lock the `Event` row; guard `lottery_run_at is None` (single run).
1. `rng.shuffle(regs)` — random, **not** signup order (TC-013). Default `rng = random.Random()`.
2. Single pass, tagging each reg's bucket: while `sel_total < x_seen` → `selected` (+n animals);
   elif `wl_total < y_waitlist` → `waitlisted` (+n); else `not_selected`.
   - **Overshoot proof:** the boundary reg is added only while the running total is still below the
     cap; before it the total was ≤ cap−1 and the reg has ≤ 6 animals → final ∈ `[cap, cap+5] ⊂
     [cap, cap+6)`. Satisfies FR-13/TC-012.
3. Second pass over **same shuffled order**: for each reg tagged selected/waitlisted, assign
   `animal_id = next_id` (from 1); raise `LotteryCapacityExceeded` if `next_id > 999` (FR-14).
   `not_selected` get no ID.
4. `bulk_update` statuses + animal_id; set `event.lottery_run_at = now()`, `event.status =
   'lottery_run'`; save. After this `signup_open()` is permanently False.

Admin trigger: a Django admin **action "Run lottery"** on the Event changelist (enabled only when
`lottery_run_at is None` and `now > close_at`). TC-013 runs ~2000 seeded iterations asserting roughly
uniform selection frequency and that different seeds differ.

**Hybrid trigger (R-4):** the lottery runs either (a) **manually** via the admin action above, or
(b) **automatically if not yet run by noon on the calendar day after `close_at`** (so the Admin
can't forget — and noon keeps result texts civilized). Both paths call the same `run_lottery(event)`,
whose Event-row lock + post-lock guard (above) mean a concurrent manual click and cron run
**cannot double-run** (TC-050). The auto path is a `manage.py run_due_lotteries` command that runs
every event past its `auto_run_deadline` (= noon in the **event's per-event `timezone` field**,
day after `close_at`; `USE_TZ=True`, store UTC) and not yet run. Wire it to a **Render Cron Job
(hourly)** as the reliable primary, plus an **admin "overdue lottery" warning + one-click run**
banner as a no-cron fallback.

### Window / open-close
All gating calls `event.signup_open()` / `owner_can_add()` / `owner_can_edit()` — never the raw
`status` column. After `close_at`: new signups rejected, owner **add** disabled, edit/remove still
allowed (FR-34/41/42). Admin can always add/edit.

### Token edit (`/r/<slug>/edit/<token>/`)
Public, no login (FR-20). `Registration.select_related('event').get(event__slug=slug,
edit_token=token)` (404 on miss). Guarded by `owner_can_edit(reg)` (FR-22/TC-024: after check-in or
event-complete → "locked"). Add control visibility + **server-side POST re-validation** against
`owner_can_add(reg)` (not just hiding the button) — TC-022/023/041/042. Renders in
`registration.language` via `translation.override`.

**Status banner (FR-41, TC-053):** always render the owner's current result — assigned AnimalID
(selected/waitlisted), "not selected" (once run), or "pending" (before) — plus checked-in/printed
state on clinic day. Shown **even when editing is locked**, so the owner can always learn their
outcome without an SMS.

**SMS-preference toggle (FR-42, TC-054):** a control on this page flips `sms_opt_out`; signup and
result-SMS steps then respect it.

### SMS abstraction (`sms/`)
Pluggable backends (`console`, `locmem` for tests, `twilio`) chosen by `settings.SMS_BACKEND`.
Templates are `gettext`-marked Python helpers, rendered under `translation.override(reg.language)`:
- **#1 signup** (sent on submit **only if `sms_consent` was checked** — FR-16/42/TC-016): "You're
  registered for [Event]. Edit here: [link]. We'll text you when the lottery runs." If unchecked,
  no SMS; the edit link is shown on the confirmation screen.
- **#2 result** (after lottery, to **every consenting** registrant — FR-17/19, TC-017/018/019):
  selected → "You're in! AnimalID is 7. [link]"; waitlisted → "Waitlist. AnimalID 7. [link]";
  not_selected → courtesy text, **no link**.
- Edit link: `absolute_url(reverse('register:edit', args=[slug, token]))` — a helper built from the
  `PUBLIC_BASE_URL` setting (see Deployment) so links are correct from a request context **and** from
  cron/retry commands. In **SMS #1 (every consenting registrant)** and **SMS #2 only for selected/waitlisted**; the not-selected courtesy text has no link (FR-17/FR-20, TC-018/074).
- Delivery is **at-most-once and best-effort**, tracked per attempt on `sms.SmsAttempt` (the
  `purpose='result'` attempts roll up to `Registration.result_sms_state`). A send is gated on **two
  independent dimensions**: `not reg.sms_opt_out` (application consent) **and** no `sms.PhoneBlock`
  for the normalized `reg.phone`. **Initial send** = an atomic INSERT of an `is_initial=True`
  `SmsAttempt(purpose=…, state='sending', callback_token=<new>)`; the unique `(registration, purpose)
  WHERE is_initial` constraint means a racing second worker gets an `IntegrityError` and skips
  (TC-070). POST to Twilio (Messaging Service) with a **per-message `StatusCallback`** of
  `absolute_url('/sms/status/<callback_token>/')` (built from `PUBLIC_BASE_URL`; supported under a
  Messaging Service, where it overrides the service-level callback) — the token lets the callback
  identify **this attempt** even with no captured SID. Classify the response by what is **proven**
  (RFC 9110 §9.2.2: a non-idempotent POST's response does **not** prove no side effect):
  - **HTTP 2xx + Message SID** → `state='sent'`, `message_sid=SID`; for `purpose='result'`, roll
    `Registration.result_sms_state='sent'`. Accepted ≠ delivered (best-effort); the callback may
    later confirm/deny it.
  - **4xx documented as pre-acceptance** (invalid number/body), or a `21610` (blocked) →
    `state='failed_permanent`. Terminal — not retried. A `21610` means the number is blocked at the
    provider; it is logged, and the durable block is owned by the inbound STOP webhook (below), not
    by the send response.
  - **5xx / connection error / timeout / no response / crashed worker** → `state='unknown'`. A 5xx
    does **not** prove the message was not created (it can be emitted *after* creation). `unknown`
    is **never** auto-retried on a timer; it is flagged and reconciled by the callback below.
  `retry_sms` (`manage.py retry_sms`, Render Cron Job ~every 5 min) is **reconcile-gated** and scoped
  to `purpose='result'`: for each `unknown` attempt whose callback set a terminal `provider_status`
  with `retryable=True`, it atomically claims the source (`retry_claimed_at__isnull=True → now()`,
  one consumer — TC-071) and creates a **fresh** child `SmsAttempt` (`retry_of=source`, new token),
  only while the registration has `< N` result attempts; it never selects `sent`/`failed_permanent`,
  an `unknown` with `retryable` falsy/null, or one with no reconciling callback. So the app makes
  **at most one** send it believes succeeded per registration (no double-texts); FR-17/19 are
  best-effort, backstopped by the edit-link status page (FR-41). Sends are concurrent (small pool);
  per-attempt try/except + logging. (TC-057/062/065/069/070/071/072.)
- **Opt-out + delivery webhooks (FR-43)** — two signature-validated, CSRF-exempt Twilio webhooks
  (the only public POSTs exempt from CSRF):
  - **Inbound `/sms/inbound/`** (Advanced Opt-Out on the **Messaging Service**, which posts
    `OptOutType`). Normalize to uppercase and switch on the **three documented values** —
    `STOP` (covers STOP/UNSUBSCRIBE/END/QUIT/…) → upsert `sms.PhoneBlock` for the normalized `From`;
    `START` (covers START/UNSTOP) → delete that `PhoneBlock`; `HELP` → no state change (Twilio
    replies with the configured help text). It writes **only** the provider block — **never**
    `sms_opt_out` — so START clears a provider block but does **not** grant application consent (a
    registration the owner declined stays opted out; TC-060). Keyed by phone, it covers every
    registration sharing that number (R-2) and any created after the STOP (TC-061). Authenticated by
    `twilio.request_validator.RequestValidator` against `X-Twilio-Signature`; forged/unsigned POSTs
    are rejected (TC-058/059). **This inbound webhook is the sole writer of `PhoneBlock`** — opt-out
    state is authoritative and chronologically ordered here, so a stale/delayed delivery callback
    cannot re-block a number after START (TC-073).
  - **Delivery-status `/sms/status/<callback_token>/`** (per-message callback) — looks up the
    `SmsAttempt` **by `callback_token`** (so an `unknown` with a null `message_sid` is still
    reconcilable, and a callback arriving *before* the 2xx handler stored the SID still matches).
    It sets `message_sid` from `MessageSid` if missing, advances `provider_status` **monotonically**
    (terminal states sticky — a late `queued`/`sent` cannot clobber them), sets `provider_error_code`
    from `ErrorCode` and the derived `retryable` flag, marks `reconciled=True` on a terminal status,
    and rolls a `purpose='result'` registration to `sent` on `delivered`. **It does not write
    `PhoneBlock`** — a `21610` in the callback only marks the attempt `failed_permanent` +
    `retryable=False` and logs (the block, if any, came from the authoritative STOP webhook). A
    duplicate callback is idempotent; an unmatched token returns 200 and is logged/alerted (not
    durably stored in V1 — TC-068/064/066/067). This is how delivery outcome is observed in
    production — `21610`/delivery is **not** assumed synchronous, so a synchronous `21610` on the
    send response is a fast-path hint only.
  The website toggle (FR-42) changes application consent only and **cannot** clear a provider block —
  re-consent of a blocked number requires START (TC-055/056).

### i18n
Public form markup uses `{% trans %}`; `makemessages -l es` → translate → `compilemessages`. EN/ES
toggle via `?lang=<code>` setting the `django_language` cookie; the chosen value is persisted to
`Registration.language` (TC-046) and selects the SMS catalog.

### Owner form (dynamic formset)
`OwnerForm` (all owner fields required — TC-007; phone validated/normalized) **+ an
`sms_consent` BooleanField(initial=True)** — "Send me updates by text"; submitting unchecked sets
`Registration.sms_opt_out=True` (FR-42; TC-054). `AnimalForm(event=…)`
conditionally shows `last_vaccinated_date` (if vaccination), `medical_concern` (if vet), and one
checkbox per offered service (TC-009/010). `formset_factory(AnimalForm, extra=1, min_num=1,
validate_min=True, max_num=N, validate_max=True)`:

- **`min_num=1, validate_min=True`** — a registration must contain **≥1 animal** (FR-7); a
  zero-animal submission is rejected (TC-051).
- **Owner self-signup/edit:** `N = max(6, existing_animal_count)`. New owners are capped at 6
  (FR-10; 7→blocked, 6→ok, TC-008), and the cap tracks the current count so an owner can still
  **edit/remove** a record a volunteer previously grew past 6 (TC-052) — only **additions beyond 6**
  are blocked.
- **Admin/volunteer:** `N=None` (cap not enforced — FR-10/36).

### Print payload + browser stub (`printing/`)
- `label_payload(event_slug, animal_id)` → JSON (login required): `registration` summary + `owner_label`
  {name, phone, email, address} + `pet_labels[]` each `{animals:[ …up to ANIMALS_PER_LABEL ]}` where
  each animal = {species, name, age, sex, breed, color}. `ANIMALS_PER_LABEL = 3` (constant — adjustable
  after print testing, Decision 9).
- `mark_printed(event_slug, animal_id)` → POST sets `printed_at = now()` (idempotent). Authoritative
  "showed up" signal (FR-35/TC-043).
- **Browser stub:** clinic "Print" button opens a printable HTML view / `window.print()`, then POSTs
  `mark_printed`. Lets the full clinic flow run without the printer. Phase 12 swaps the stub body for
  the JS-bridge call, then calls `mark_printed`.

### Export (`export/`) — CSV + XLSX
`export_event(event_slug, fmt)` (login required). CSV via `csv.writer` + `StreamingHttpResponse`;
XLSX via `openpyxl` → `BytesIO`. Columns: owner first/last name, phone, address, email; per animal
name, species, age, sex, breed, color, services; plus status, AnimalID, language, printed.
**Default = one row per animal** (owner + AnimalID repeated — best for the Admin's per-animal vaccine
notes; matches "per animal" in FR-29); `?per=registration` rollup optional (TC-032).

---

## Build phases

| Phase | Build | Key files | FRs / TCs |
|---|---|---|---|
| **0 Scaffolding** | `git init`; `.gitignore`; `startproject config .` + settings split; 8 app packages; requirements; `runtime.txt`; `render.yaml`; `.env.example`; `templates/` `static/` `locale/` | `manage.py`, `config/settings/base.py`, `config/urls.py`, `requirements/base.txt`, `render.yaml` | NFR-2 plumbing |
| **1 Models + admin** | All 6 models (`Event`, `Registration`, `Animal`, `User`, `sms.PhoneBlock`, `sms.SmsAttempt`), `makemigrations`, partial unique index, read-time window helpers + `z_applicants` soft cap + per-event `timezone` (IANA select) + `auto_run_deadline` + **tz-aware `open_at`/`close_at` entry/display**; SMS: `result_sms_state`/`_sent_at` rollup on Registration + `sms_opt_out` (app consent) + `sms.PhoneBlock` (phone-level provider block; written only by inbound STOP/START webhook) + `sms.SmsAttempt` (per-send try: `purpose`/`callback_token`/`message_sid`/`is_initial`+unique/`retry_of`+unique/`retry_claimed_at`/`state`/monotonic `provider_status`/`provider_error_code`/`retryable`/`reconciled`); full Django admin (back-office) with fieldsets, list_display/filter/search, `next_animal_id` | `events/models.py`, `register/models.py`, `accounts/models.py`, `sms/models.py`, `*/admin.py` | FR-1/2/8/14/37/38/43; TC-002, TC-009, TC-047 |
| **2 Auth + Event admin + QR/URL** | `accounts` login/logout (lean on `LoginView`); auto `slug` (slugify + uniqueness loop, retry on `IntegrityError`); flyer page with sign-up URL + "Download QR JPG" (`qrcode`→Pillow→`HttpResponse` jpg); admin **delete entire event** (cascade) behind a confirmation warning (R-9) | `accounts/views.py`, `events/admin.py`, `events/services_qr.py`, `events/views.py`, `templates/registration/login.html` | FR-1/2/3/30/32/39; TC-001/003/033/035/048 |
| **3 Public form + i18n + SMS #1** | `signup(slug)` guarded by `signup_open()` **and `not at_capacity()` (R-10: Z soft applicant cap → friendly full message; slight overshoot ok)**; `OwnerForm` (+ `sms_consent` checkbox, default on) + dynamic `AnimalFormSet(min_num=1, max_num=6)`; confirmation screen (no guaranteed time; shows the edit link even if SMS was declined); persist language; fire SMS #1 to consenters | `register/{views,forms,urls}.py`, `sms/{services,templates,backends/*}.py`, `locale/es/…django.po`, `templates/register/{signup,confirm}.html` | FR-5/6/7/8/9/10/11/16/18/31/33/38/42; TC-004/005/006/007/008/010/011/016/037/046/047/051/054 |
| **4 Token edit + window rules** | `edit_entry(slug, token)`; `owner_can_edit`/`owner_can_add` guards; add disabled post-close (server-validated); edit/remove always; **status banner (FR-41) + SMS-preference toggle (FR-42)**; atomic save | `register/views.py`, `templates/register/edit.html` | FR-20/21/22/34/41/42; TC-020/021/022/023/024/041/042/053/054 |
| **5 Lottery** | `run_lottery` service (Event-row lock + post-lock guard) + exceptions; admin "Run lottery" action; `run_due_lotteries` command for the **auto-fallback at noon day-after-close** (R-4/FR-40) | `lottery/{services,exceptions,admin}.py`, `lottery/management/commands/run_due_lotteries.py` | FR-12/13/14/15/40; TC-012/013/014/015/049/050 |
| **6 Lottery-result SMS #2** | `result_body` (3 branches); `notify_lottery_results` to every **consenting, unblocked** registrant in stored language (send gated on `not sms_opt_out` **and** no `sms.PhoneBlock`); atomic initial `SmsAttempt` INSERT (unique `(reg,purpose) WHERE is_initial`) with a per-message `StatusCallback` carrying an opaque token; classify 2xx→`sent`, 4xx-pre-acceptance/`21610`→`failed_permanent` (no `PhoneBlock` write), **5xx/conn/timeout/crash→`unknown`**; **inbound webhook** (signature-validated; `OptOutType` STOP/START/HELP uppercase; sole writer of `PhoneBlock`; FR-43); **delivery-status webhook** `/sms/status/<token>/` (token-keyed reconciliation, monotonic `provider_status`, `provider_error_code`→`retryable`; never writes `PhoneBlock`); **`retry_sms`** (reconcile-gated, `purpose='result'` only: one-consumer `retry_of` claim, fresh attempt, `<N` cap); URLs via `absolute_url`/`PUBLIC_BASE_URL` | `sms/templates.py`, `sms/views.py` (both webhooks), `sms/models.py`, `sms/management/commands/retry_sms.py`, `lottery/services.py` | FR-17/18/19/43; TC-017/018/019/055/056/057/058/059/060/061/062/064/065/066/067/068/069/070/071/072/073/074 |
| **7 Clinic check-in + lookup** | `LoginRequiredMixin` views: `select_event` (session), `lookup` (AnimalID exact / fuzzy name+phone, **event-scoped**), `detail` (editable, `max_num=None`), add/remove/save, `check_in`; ordered waitlist list (no promotion) | `clinic/{views,urls}.py`, `templates/clinic/*` | FR-23/24/25/26/27; TC-025/026/027/028/029/030/034/036 |
| **8 Print payload + stub + printed_at** | `label_payload`, `mark_printed`, browser print stub | `printing/{views,urls,serializers}.py`, `templates/clinic/print_stub.html` | FR-28/35 (backend half); TC-031/043 |
| **9 Export** | CSV streaming + XLSX builders | `export/{views,urls,exporters}.py` | FR-29; TC-032 |
| **10 Admin manual entry + AnimalID** | Admin create Registration (`created_by=admin`, no cap); "next available" AnimalID button; `clean()` + partial index enforce 1..999 + event-unique (catch `IntegrityError`) | `register/{admin,forms}.py` | FR-36/37; TC-044/045 |
| **11 Deploy to Render** | `render.yaml` (web service + Postgres); `prod.py` (DEBUG=False, SSL redirect, secure cookies, WhiteNoise, `dj_database_url` ssl); set **`PUBLIC_BASE_URL`** (canonical HTTPS origin for SMS edit-links + per-message callbacks); migrations in `preDeployCommand`, collectstatic at build; `ensure_admin` command; **Cron Job** running `manage.py run_due_lotteries` hourly (R-4/FR-40 auto-lottery); **Cron Job** running `manage.py retry_sms` ~every 5 min (FR-17); **provision a Twilio Messaging Service** (`TWILIO_MESSAGING_SERVICE_SID`) + sender pool, **enable Advanced Opt-Out**, and configure **one fixed service-level webhook** — the inbound `/sms/inbound/` (`OptOutType` STOP/START/HELP → `PhoneBlock`, sole writer; FR-43). The delivery-status path is **per-message** (`/sms/status/<token>/` passed at send), not a console-configured service callback | `render.yaml`, `config/settings/prod.py`, `config/wsgi.py`, `accounts/management/commands/ensure_admin.py` | NFR-1/2/3, FR-32/40/43; TC-038/039/049/055/056/058/059/060/061/062/063/064/065/066/067/068/069/070/071/072/073/074 |
| **12 (outline) Flutter print station** | Convert `/home/dev/vet_app` → WebView shell over the deployed site; JS bridge → existing `MethodChannel('com.example.vet_app/printer')`; **rewrite native TSC layout** in `MainActivity.kt::printLabel` to consume the grouped payload; Print button → bridge → `mark_printed`. | `/home/dev/vet_app/**` | NFR-4 (full); TC-040 |

---

## Testing strategy (maps to TraceabilityMatrix)

`pytest-django` + `factory_boy` for unit/integration; Playwright for E2E; manual + deploy before
each release. All Twilio-touching tests use the `locmem` backend; TC-039 additionally grep-asserts
no creds in source.

**Highest-value automation — the lottery core (Phase 5):** TC-012 (cap math), TC-013 (randomness
distribution over ~2000 seeded runs), TC-014 (statuses + unique IDs), TC-015 (sequential from 1,
contiguous, max 999). `run_lottery(event, rng=random.Random(seed))` makes these fully deterministic.

Other automatable: TC-002 (slug), TC-004 (window), TC-007/008 (validation + cap), TC-016/017/018/019
(SMS via locmem), TC-031 (payload shape), TC-032 (export columns), TC-039 (env creds), TC-041
(post-close add blocked), TC-043 (printed_at), TC-044/045 (manual entry + AnimalID), TC-046
(language stored), TC-047 (applicant cap Z), TC-048 (event deletion), TC-049 (noon auto-run),
TC-050 (no concurrent double-run), TC-051 (≥1 animal), TC-052 (over-cap owner edit), TC-053
(edit-link shows result), TC-054 (SMS consent checkbox / opt-out), TC-055 (STOP→phone-level block),
TC-056 (START clears block, not app consent; website toggle can't override provider block),
TC-057 (at-most-once: 5xx→unknown incl. after-creation; reconcile-gated retry), TC-058 (webhook
signature rejection, real `OptOutType` casing + HELP), TC-059 (duplicate-phone STOP),
TC-060 (START never grants application consent), TC-061 (registration created after STOP is blocked),
TC-062 (reconcile-gated retry_sms; permanent/unknown never retried), TC-064 (token-keyed delivery
callback), TC-065 (5xx after creation→unknown, no dup), TC-066 (callback before response),
TC-067 (out-of-order callbacks monotonic), TC-068 (duplicate/unmatched callback), TC-069
(reconcile-gated vs no-callback unknown), TC-070 (atomic initial-send claim), TC-071 (one-consumer
retry claim), TC-072 (retryability persists across restart), TC-073 (delayed 21610 can't undo START),
TC-074 (command-path absolute URLs via `PUBLIC_BASE_URL`). E2E/manual/deploy: TC-005/006/010/011/020–030/033/034/036/037/038/040/063.

---

## Security & access (FR-30..32, NFR-3)

- `LoginRequiredMixin` on every `clinic`/`printing`/`export`/event-admin view; public only on
  `register` signup + edit.
- Owner self-edit auth = the 256-bit `edit_token` + window/check-in state (FR-20..22). **No public
  index** of registrations — no list view, no enumeration (FR-32).
- CSRF on all POSTs (Django default); prod `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`,
  `CSRF_COOKIE_SECURE`; secrets only in env.
- **The two Twilio webhooks (`/sms/inbound/` for STOP/START and `/sms/status/` for delivery status)
  are the only public POSTs exempt from CSRF** (Twilio can't send a CSRF token); each is authenticated
  with `twilio.request_validator.RequestValidator` against the `X-Twilio-Signature` header —
  forged/unsigned requests are rejected (FR-43; TC-058/064).

---

## Deployment (Render)

`render.yaml`: one **web service** (`python` runtime; build = `pip install -r requirements/prod.txt
&& python manage.py collectstatic --noinput`; start = `gunicorn config.wsgi --log-file -`;
pre-deploy = `python manage.py migrate`) + one **Postgres** add-on (auto-injects `DATABASE_URL`).

**Env vars (never in code):** `DATABASE_URL`, `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS`,
**`PUBLIC_BASE_URL`** (the canonical `https://<host>` origin — validated HTTPS; the single source for
SMS edit-links and per-message `StatusCallback` URLs built by `absolute_url()`, so they are correct
from request context **and** from cron/retry commands), `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
**`TWILIO_MESSAGING_SERVICE_SID`** (the `MG…` Messaging Service — production sends go through it so
Advanced Opt-Out works; `TWILIO_FROM_NUMBER` is retained only for local-dev/console fallback), (+
bootstrap `ADMIN_USERNAME`/`ADMIN_PASSWORD`/`ADMIN_EMAIL`). **Twilio provisioning (once, in the
Console):** create the Messaging Service, add a SMS-capable number to its sender pool, **enable
Advanced Opt-Out**, and point its **inbound-SMS webhook** at `<PUBLIC_BASE_URL>/sms/inbound/` (the one
**fixed, service-level** webhook). The delivery-status callback is **not** a fixed service webhook —
each send passes its own tokenized `<PUBLIC_BASE_URL>/sms/status/<callback_token>/` per message
(supported under a Messaging Service; it overrides any service-level callback). Gotchas: link Postgres
before first boot; WhiteNoise above other middleware; no writable disk at runtime → collectstatic at
build.

---

## Risks & open items (dispositions from review)

- **R-1 Phone/SMS deliverability — RESOLVED.** Cell-phone-only is an accepted requirement. Keep
  `phonenumbers` validation + E.164 normalization; drop the Twilio-lookup idea.
- **R-2 Duplicate owners — RESOLVED (by design).** We deliberately do NOT enforce (event, owner)
  uniqueness. Each Registration has a unique PK (`registrantID`) + `animal_id` + `edit_token`; the
  edit URL carries the token. Two people with identical name/phone/pet simply create two rows —
  nothing breaks. Clinic lookup by name/phone may return multiple matches; narrowing by RegistrantID
  or AnimalID resolves it. (Acceptable per review.) **SMS opt-out has two independent dimensions
  (FR-43):** application consent (`sms_opt_out`) is **per-registration** — one owner declining does
  **not** affect another registration sharing the phone, so two duplicate-phone rows may legitimately
  differ in consent. The **provider block (`sms.PhoneBlock`)** is the only phone-level dimension: a
  STOP (inbound webhook) blocks the number and fans out to every registration sharing it, while a
  `21610` is a per-send failure (not a block). A send requires that registration's own consent clear
  **and** no provider block for its phone.
- **R-3 Status-display drift — ELIMINATED by design.** The `status` column stores only discrete
  admin-driven stages; the **displayed** open/closed label is computed live from
  `open_at`/`close_at`/`lottery_run_at`. So the admin always sees reality — no drift, no cron needed.
  (Never a correctness bug; now not even a cosmetic one.)
- **R-4 Lottery trigger — RESOLVED (hybrid).** Runs when the Admin clicks "Run lottery" **or**
  automatically if not yet run by **noon on the day after `close_at`** (so the Admin can't forget,
  and the result texts still go out at a civilized hour). Both paths call one `run_lottery` that
  **locks the Event row inside the transaction and re-checks `lottery_run_at` after the lock**, so a
  concurrent manual click and cron run cannot double-run (TC-050). Auto path = `run_due_lotteries`
  command on a Render Cron Job (hourly) + an admin "overdue lottery" warning/one-click-run banner as
  a no-cron fallback. Result SMS is **at-most-once** (per `SmsAttempt`: 2xx→`sent`,
  4xx-pre-acceptance/`21610`→`failed_permanent`, **5xx/conn/timeout/crash→`unknown`**; nothing is
  auto-retried on a timer — only a callback-confirmed terminal-transient failure is retried, so no
  double-texts), best-effort (not guaranteed), and sent concurrently so ~Z texts finish quickly.
- **R-5 Check-in concurrency — RESOLVED by design (verify at first busy event).** One volunteer/printer is the norm; two+ volunteers with
  two printers also work cleanly — that's exactly why Postgres (not SQLite). Duplicate AnimalIDs are
  blocked by the unique index; two volunteers editing the same registration is last-write-wins and
  idempotent for check-in/printed_at.
- **R-6 Phase 12 — CONFIRMED deferred.** Phase 12 is the Flutter WebView-shell + native label-layout
  work, a separate follow-up PR with interactive print testing. Not in this PR.
- **R-7 Doc accuracy — FIXED.** Corrected `Architecture.md`: printer link is **Bluetooth Classic/SPP**
  (not BLE); Web Bluetooth can't reach it; Android-only (not MFi). `Requirements.md` "Web-Bluetooth"
  future-vision notes left as-is (accurate).
- **R-8 vet_app / vet_app2 — REFRAMED as assets.** Both are proven, working print implementations —
  proof we can drive the 3nStar and lay out any format. For Phase 12 we reuse the proven
  `printLabel` pipe + TSC command approach (Decision 5 = Flutter WebView shell), just with the new
  owner+pet data. `vet_app2`'s TSPL-in-JS port stays a useful reference. No "canonical line"
  decision needed.
- **R-9 Event deletion — ADDED feature.** Admin can select an event and **delete the entire event**
  (cascade to all registrations/animals) behind a confirmation warning. Also covers retention (admin
  purges old clinics on demand). Served from the event selector / Django admin delete-confirmation.
- **R-10 Applicant cap "Z" — ADDED feature.** Per-event `z_applicants` field alongside X and Y = max
  registrations/owners allowed; **admin-configured per event (no hardcoded value)**. Once reached,
  new signups are rejected with a friendly EN/ES "registration is full" message. **Z is a soft cap:
  the capacity check + insert are not serialized, so concurrent signups at the boundary may push the
  count over Z — by at most the number of signups in flight at the boundary, not a fixed "few."**
  That overshoot is **not a deterministic invariant** and is verified as **residual/load behavior**
  (TC-047), not a unit assertion — there is no hard ≤Z guarantee (no lock). Gates only brand-new
  registrations (existing owners may still add animals).
- **R-11 Twilio cost/consent — RESOLVED.** ≈2 SMS/consenting-registrant × ~Z/event (Z is a soft
  cap; the final count is Z plus a concurrency overshoot bounded by in-flight signups, not a hard
  ≤Z) — budget approved by the Admin. Consent has two dimensions (FR-43): an application-level
  signup checkbox (default on) + "Reply STOP to opt out" on every SMS, and a provider-level block
  synced via the inbound STOP/START webhook. Sends go through a **Messaging Service** (Advanced
  Opt-Out). The Z cap (R-10) bounds the blast; exact compliance copy polished at build time.
  Delivery is at-most-once and best-effort (R-4 delivery state), not guaranteed.

---

## Verification (end-to-end)

1. **Local dev:** `pip install -r requirements/dev.txt`; `manage.py migrate`; create an admin via
   `createsuperuser`; `manage.py runserver`. Set `SMS_BACKEND=console` so SMS prints to terminal.
2. **Phase-by-phase smoke (mirrors TCs):** admin creates an event with open/close times around now →
   download QR (decodes to the signup URL). Open `/r/<slug>/` logged-out → form renders (EN/ES toggle
   works). Submit 6 animals → confirmation + a signup SMS in `console`. Submit 7 → blocked. Edit via
   the token link; after manually advancing `close_at`, confirm add is blocked but edit/remove work.
3. **Lottery:** seed ~30 registrations of varying animal counts; run the lottery action → statuses +
   sequential AnimalIDs from 1 appear; rerun is refused; result SMS bodies match outcome/language.
4. **Clinic:** log in as volunteer → look up by AnimalID and by partial name/phone → edit/add/remove
   → check-in → click Print (stub) → `printed_at` set; confirm cross-event lookup is denied.
5. **Export:** download CSV + XLSX; verify columns (one row per animal, AnimalID repeated, printed
   yes/no, language).
6. **Automated:** `pytest` — green across the unit/integration TCs above (esp. TC-012/013/014/015).
7. **Deploy:** push to GitHub → Render build/deploy → site reachable over HTTPS; confirm Twilio creds
   are absent from the repo (`git grep`).
8. **Phase 12 (later):** print real owner + grouped pet labels on the 3nStar PPT305BT (TC-040) and
   lock `ANIMALS_PER_LABEL`.
