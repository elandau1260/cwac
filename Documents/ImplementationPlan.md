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
| Auth | `accounts.User(AbstractUser)` + `role` (admin/volunteer); **differentiated privileges** (FR-30/Decision 16): Admin-only = event create/configure/delete, run lottery, export; both roles = clinic ops (lookup/edit/add/remove/check-in/print/manual entry/assign AnimalID); session auth via `LoginRequiredMixin` + a `role == admin` mixin for Admin-only views |
| Timezone | `django-timezone-field` (per-event IANA select); custom admin form so `open_at`/`close_at` are entered **and** displayed in the event's tz (stored UTC, `USE_TZ=True`) — drives the per-event "noon" auto-lottery deadline |

**Window mechanism (FR-4/34) — read-time, no cron.** Source of truth = computed methods on `Event`,
never the `status` column. Render has no free cron; read-time is instantly correct and "no manual
lock" (Decision 8) fits a derived check. The `status` column stores only the **discrete admin-driven
stages** (draft / live / lottery_run / active / completed); the **displayed** open-vs-closed label is
computed live from `open_at`/`close_at` plus the `live` stage (open iff `status == 'live'` and
`open_at ≤ now < close_at`), so what the admin sees always matches reality (no drift, no cron). The
new-signup gate reads the time window (`open_at`/`close_at`) + the `live` stage + the applicant cap Z
(R-10) — nothing else (FR-4).

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
- `status` CharField(choices=draft/live/lottery_run/active/completed, default=draft) — the open↔closed distinction is a **computed display label** (open iff `status == 'live'` and `open_at ≤ now < close_at`), never stored (R-3). `status` is **forward-only and read-only outside `transition()`**: the admin form sets it `editable=False`, so an Admin cannot regress `lottery_run`/`completed → live` to reopen signups or re-enable mutations (FR-4/TC-058).
- `lottery_run_at` DateTimeField(null, blank) — durable **single-run guard** (the lottery sets it once; also the marker the auto-run check uses). It is **not** a signup gate — signups are time-window + `live`-status driven (FR-4)
- `next_staff_id` PositiveIntegerField(default=1000) — per-event counter for **staff walk-in/admit IDs (≥1000)**; incremented under the Event-row lock by `assign_next_walkin_id` (these IDs are not counted toward X/Y)
- `created_at`, `updated_at`
- **Methods (authoritative):** `@property services_offered`; `is_published()` = `status == 'live'`; `transition(target, *, by=None)` — the **only** way `status` changes: runs inside `transaction.atomic()`, **locks + reloads the Event row** (`select_for_update().get(pk=self.pk)`), validates **exactly one forward step** (`draft→live→lottery_run→active→completed`), `raise InvalidTransition` on a backward or skip move, then saves — so every transition (Publish, Run-lottery→`lottery_run`, Activate, Complete, **and the lottery's own `live→lottery_run`**) is atomic and one-step; `signup_open(now=None)` = `is_published() and lottery_run_at is None and open_at ≤ now < close_at` (**FR-4:** signups only during `[open_at, close_at)`; the `lottery_run_at is None` term is **defense-in-depth** — even if `status` were forced back to `live`, signups stay closed once the lottery has run; reopening `close_at` after the lottery cannot reopen signups); `at_capacity()` = `registrations.count() >= z_applicants` (**soft cap** — not locked; concurrent signups at the boundary may overshoot by a few, which is acceptable; R-10); `auto_run_deadline()` = noon (12:00 local) on the calendar day after `close_at`, computed in `self.timezone` (returns a tz-aware datetime for comparison against `timezone.now()`); `owner_can_add(reg)` = `signup_open() and reg.status != 'checked_in'`; `owner_can_edit(reg)` = `status != 'completed' and reg.status != 'checked_in'`. The **new-signup** view additionally requires `not at_capacity()` — Z gates only brand-new registrations, not an existing owner adding animals. The check + insert are deliberately **not serialized** (no Event-row lock): Z is a soft target and a few over is fine (R-10; TC-047). Displayed open/closed is computed live — no cached drift.

### `register.Registration`
- `event` FK(Event, related_name=registrations, CASCADE)
- `animal_id` PositiveIntegerField(null, blank) — **read-only outside the allocation services** (the lottery + the staff allocate service); `editable=False` in forms/admin. Lottery assigns **1..999**; staff walk-in/admit assigns **≥1000**.
- `id_source` CharField(null, choices lottery/staff) — set when `animal_id` is assigned; `clean()` cross-checks range↔source (`lottery` ⇒ 1..999, `staff` ⇒ ≥1000), because `1..999 ∪ ≥1000` covers every positive integer and the range alone cannot prove the allocator.
- `status` choices: registered/selected/waitlisted/not_selected/checked_in (default registered)
- `edit_token` CharField(unique, db_index, default=`generate_edit_token`) — 256-bit; `generate_edit_token`
  is a **module-level callable** (`def generate_edit_token(): return secrets.token_urlsafe(32)`) so each
  row gets a fresh secret — a bare `default=token_urlsafe(32)` would be evaluated once at import time and
  reuse one token (collision). The only auth for self-edit.
- `language` CharField(2, choices en/es, default en) — **chosen at signup, drives SMS**
- `printed_at`, `checked_in_at` DateTimeField(null, blank)
- `result_sms_state` CharField(null/sending/sent/failed/unknown, default null) — **fire-and-forget**
  result-SMS status for admin/export ("did this reg get its result SMS?"). Atomically claim
  `null→sending` before the send (only the claimant sends), then classify: `sent` = Twilio **accepted
  the API request** (2xx, queued — not delivered); `failed` on a **synchronous** rejection (4xx, e.g.
  invalid number `21211`); `unknown` on a **caught** ambiguous outcome (5xx / connection error /
  timeout / no response) — an exception the worker trapped and classified itself. **A process crash
  is NOT `unknown`**: a dead worker cannot write its own state, so it leaves `null` (if it died
  before the claim) or a persistent `sending` (if it died after). **Never retried** — one send per
  registration, so at-most-once is trivially true; `null` (zero attempts) and `sending` are both
  acceptable and **neither is ever resent**. Best-effort; the edit-link status page is the reliable
  channel (FR-41).
- `result_sms_sent_at` DateTimeField(null, blank, set only when state=`sent`)
- `sms_opt_out` BooleanField(default=False) — **application-level consent** (the only app-side SMS
  gate), registration-local. Changed only by the owner: the signup consent checkbox (FR-42) and the
  edit-link toggle. Provider-side STOP/START (Twilio Advanced Opt-Out) is **not** mirrored — a send to
  a STOP'd number is still **accepted** (`sent`); Twilio honors the opt-out asynchronously (`21610`,
  unobserved). When True, signup + result SMS are skipped; status is still shown on the edit-link
  page (FR-41).
- `first_name`, `last_name` CharField(100); `phone` CharField(20) E.164; `email` EmailField; `address` CharField(300) — **all required**
- `creation_source` CharField(choices public/staff, default public) — `public` (owner via the web form) or `staff` (admin/volunteer created it)
- `created_by_user` FK(`accounts.User`, null=True) — the staff User that created a `staff`-source row (null for `public`)
- `admitted_by_user` FK(`accounts.User`, null=True) + `admitted_at` DateTimeField(null=True) — set when staff **admit** an existing `public` row (assign a 1000+ ID); the row's `creation_source`/`created_by_user` are left untouched
- `created_at`, `updated_at`
- **Meta.constraints:** `UniqueConstraint(fields=[event, animal_id], condition=Q(animal_id__isnull=False))`
- **classmethod** `next_animal_id(event)` = (max non-null `animal_id` in event, **lottery range 1..999 only**)+1, else 1 — used by the lottery only
- **classmethod** `assign_next_walkin_id(event, reg)` — under `transaction.atomic()`, **locks + reloads the `Event` row then the `Registration` row (Event-first consistent order)**, reads `event.next_staff_id`, assigns it to `reg` (`id_source='staff'`), increments `event.next_staff_id`, saves both — atomic, so no `max()+1` race and no deleted-highest-ID reuse. It **rejects** (a) a `reg` from a **different event** (no cross-counter consumption), (b) a `reg` that is **already numbered** (already-assigned IDs are never edited — a duplicate/concurrent admit fails rather than overwriting), and (c) an unsaved `event`/`reg`. The caller's stale instances are refreshed from the committed rows.
- **property** `is_attended` = `printed_at is not None`

### `register.Animal`
- `registration` FK(Registration, related_name=animals, CASCADE); Meta `ordering=[id]` (stable print grouping)
- `name` CharField(100); `species` CharField(100); `age` CharField(30) — **free text** ("3 years"/"8 months")
- `breed`, `color` CharField(100, blank)
- `sex` choices **M/F/MN/FS/U** (Male / Female / Male-Neutered / Female-Spayed / **Unknown**) — per the export spec; **`blank=True`, `default=''`** (optional). Sex is not required — some animals' sex is unknown, especially babies (Decision 17).
- `services_requested` JSONField(default=list); `last_vaccinated_date` DateField(null, blank); `medical_concern` TextField(blank)
- **No `weight` field** (FR-8/TC-009)

### `accounts.User`
`AbstractUser` + `role` choices admin/volunteer (default volunteer) + a custom **`UserManager`** (subclasses the contrib `UserManager`, `use_in_migrations=True`) that keeps `role` consistent with the privilege flags. **Differentiated privileges (FR-30/Decision 16):** Admin-only = create/configure/delete events, run the lottery, export data (an Admin additionally does everything a volunteer can); **both roles** do clinic operations — lookup, edit, add, remove, check-in, print, walk-in add, admit. **Provisioning:** an Admin is a Django **superuser** — `is_staff=True` + `is_superuser=True` + `role=admin` (full Django-admin access; via `createsuperuser`/`ensure_admin`); a Volunteer is `is_staff=False`/`is_superuser=False`/`role=volunteer`. **The manager (sync + async) and `User.clean()` reject every inconsistent combination** — `create_user`/`acreate_user` raise on any staff/superuser flag or `role=admin`; `create_superuser`/`acreate_superuser` raise on `is_staff`/`is_superuser=False` or `role=volunteer`. **Enforcement:** Admin-only custom views use a `role == admin` mixin; the Django admin requires `is_staff` to enter and an Admin's model access comes from superuser status. (Migration `0002_manager_and_repair` swaps the manager and repairs any pre-existing volunteer-role superuser to `role=admin`.)

---

## Key behavioral designs

### Lottery (`lottery/services.py`) — pure, injectable RNG
`run_lottery(event, *, rng=None, commit=True) → LotteryResult`. **Concurrency-safe single run:**
the whole body runs inside one `transaction.atomic()`. It first **locks and reloads the `Event`
row** (`Event.objects.select_for_update().get(pk=event.pk)`), then performs the single-run guard
on that locked row — `raise LotteryAlreadyRun if event.lottery_run_at is not None`, and
`raise LotteryNotEligible if event.status != 'live' or now <= event.close_at` (**FR-12:** the
lottery runs only on a **live** event and only **after close** — this is the authoritative guard,
under the Event-row lock; the admin action's `status == 'live'` / `now > close_at` checks are just
UX pre-filtering). This gates out drafts, non-live events, and before-close calls (TC-049). Locking the Event row (not just the registrations)
is what makes a manual click and the noon cron unable to double-run: the second caller blocks until
the first commits, re-reads a non-null `lottery_run_at`, and exits (TC-050). Then
`select_for_update()` on the event's `registered` rows:

0. Reload + lock the `Event` row; guard `lottery_run_at is None` **and** `status == 'live'` **and** `now > close_at` (FR-12).
1. `rng.shuffle(regs)` — random, **not** signup order (TC-013). Default `rng = random.Random()`.
2. **Two buckets, each computed on the *remainder* after the prior** (a selected-bucket overshoot
   reduces the pool available for the waitlist — so "total between X and X+Y" is not the rule). For
   each bucket with target `T` (selected `T = x_seen`, then waitlist `T = y_waitlist`): walk the
   remaining regs accumulating the animal count; **include** a reg while the running total is still
   `< T` (the reg that crosses `T` is included — that is the overshoot). **If the regs run out before
   `T` is reached, assign all remaining to that bucket and allow the total to fall below `T`**
   (short demand — the bucket is simply under-filled). Regs left after the waitlist bucket →
   `not_selected`.
   - **Per-bucket overshoot bound:** let **M** = the largest animal count among the regs eligible for
     *that* bucket. If enough animals exist to reach `T`, the bucket total ∈ `[T, T+M)` (the boundary
     reg is added only while the running total was `< T`, i.e. ≤ `T−1` before it, and has ≤ M animals
     → final ∈ `[T, T+M−1] ⊂ [T, T+M)`). If not enough animals exist, the total is just `< T` (all
     remaining regs taken). For a typical all-owner bucket M ≤ 6; a staff-grown >6 row is possible
     via FR-25/TC-052, in which case M is that row's count. Satisfies FR-13/TC-012.
   - **Low / zero demand:** if there are **0 registrations**, no statuses change and no IDs are
     assigned, but the lottery still **completes** (`lottery_run_at` set, `status='lottery_run'`).
     **X or Y may each be 0:** `X=0` skips the selected bucket (regs flow to waitlist / `not_selected`);
     `Y=0` skips the waitlist bucket; `X=Y=0` ⇒ every reg `not_selected`. (Staff-added 1000+ rows are
     post-lottery and are never in `regs`.)
3. Second pass over **same shuffled order**: for each reg tagged selected/waitlisted, assign
   `animal_id = next_id` (from 1, **lottery range 1..999 only**); raise `LotteryCapacityExceeded` if
   `next_id > 999` (FR-14). `not_selected` get no ID. (`id_source='lottery'`.)
4. `bulk_update` statuses + `animal_id` + `id_source`; set `event.lottery_run_at = now()` and advance
   `event.status` to `'lottery_run'` **via `event.transition('lottery_run')`** (the atomic one-step
   `live→lottery_run` move, under the held Event-row lock). After this `signup_open()` is permanently
   False (status is past `live` **and** `lottery_run_at` is set).

Admin trigger: a Django admin **action "Run lottery"** on the Event changelist (enabled only when
`status == 'live'`, `lottery_run_at is None`, and `now > close_at`). TC-013 runs ~2000 seeded
iterations asserting roughly uniform selection frequency and that different seeds differ.

**Hybrid trigger (R-4):** the lottery runs either (a) **manually** via the admin action above, or
(b) **automatically if not yet run by noon on the calendar day after `close_at`** (so the Admin
can't forget — and noon keeps result texts civilized). Both paths call the same `run_lottery(event)`,
whose Event-row lock + post-lock guard (above) mean a concurrent manual click and cron run
**cannot double-run** (TC-050). The auto path is a `manage.py run_due_lotteries` command that selects
events past their `auto_run_deadline` (= noon in the **event's per-event `timezone` field**, day
after `close_at`; `USE_TZ=True`, store UTC) **with `status == 'live'`** and `lottery_run_at is None`
— an abandoned draft whose timestamps pass is **not** selected (and `run_lottery` re-checks `live`
under the lock, so a race/status change can't sneak it through; TC-049). Wire it to a **Render Cron
Job (hourly)** as the reliable primary, plus an **admin "overdue lottery" warning + one-click run**
banner as a no-cron fallback.

### Window / open-close
All gating calls `event.signup_open()` / `owner_can_add()` / `owner_can_edit()` — never the raw
`status` column. After `close_at`: new signups rejected, owner **add** disabled, **edit/remove still
allowed until check-in/event-completion** (after that, mutation locks — POST rejected — but GET
still renders: FR-41). Admin can always add/edit.

### Token edit (`/r/<slug>/edit/<token>/`)
Public, no login (FR-20). `Registration.select_related('event').get(event__slug=slug,
edit_token=token)` (404 on miss). **Read and mutate are separate** (this page is the reliable status
fallback — FR-41): a **GET always renders** the entry + status banner, even after check-in/event
completion, showing a "locked" notice when `owner_can_edit(reg)` is false; **POST/mutation
(add/edit/remove) is rejected server-side** unless `owner_can_edit(reg)` (and, for add,
`owner_can_add(reg)`) hold — TC-022/023/024/041/042. Renders in `registration.language` via
`translation.override`.

**Status banner (FR-41, TC-053):** always render the owner's current result — assigned AnimalID
(selected/waitlisted), "not selected" (once run), or "pending" (before) — plus checked-in/printed
state on clinic day. Shown **even when editing is locked** (GET still renders it), so the owner can
always learn their outcome without an SMS.

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
  the lottery/retry-free notification path (no `request` there). In **SMS #1 (every consenting
  registrant)** and **SMS #2 only for selected/waitlisted**; the not-selected courtesy text has no
  link (FR-17/FR-20, TC-018).
- **Delivery is fire-and-forget: best-effort, at-most-once, never retried.** SMS is a *convenience*
  channel; the edit-link status page (FR-41) is the reliable one. `sent` means **Twilio accepted the
  API request** (HTTP 2xx, message queued) — it does **not** mean delivered, and the app makes **no**
  promise to observe provider-side outcomes (see opt-out below). Per result SMS: atomically claim
  `Registration.result_sms_state null→sending`
  (`filter(pk=reg.pk, result_sms_state__isnull=True).update(result_sms_state='sending')` — only the
  claimant sends, committed **before** the Twilio POST), then classify the **synchronous response**:
  - **HTTP 2xx** → `result_sms_state='sent'` + `result_sms_sent_at` (accepted/queued; not tracked further).
  - **4xx** (synchronous rejection, e.g. invalid number `21211`) → `result_sms_state='failed`. Logged.
  - **5xx / connection error / timeout / no response** (a *caught* exception the worker classified) → `result_sms_state='unknown'`. **Process crash / hard kill is not `unknown`** — a dead worker cannot update its own row: it leaves `null` (died before the claim) or a persistent `sending` (died after); neither is resent.
  Nothing is ever retried, so there are **no double-texts** ("at most one" send per registration —
  not "exactly one": best-effort means a crash between the lottery commit and notification can leave
  a registration at **zero attempts** (`null`), and a crash after the claim can leave a persistent
  `sending`; both are acceptable — the status page still works — and **neither triggers a resend**).
  No `retry_sms`, no delivery-status callback, no per-message `StatusCallback`. The signup SMS (#1)
  is the same fire-and-forget send (no state tracked). Sends are concurrent (small pool) with per-reg
  try/except + logging. (TC-055/056.)
- **Opt-out (FR-43) — provider-side, not mirrored.** STOP/START/HELP are handled entirely by Twilio
  **Advanced Opt-Out** on the Messaging Service (enabled once in the Console): Twilio maintains the
  per-number blocklist and replies with the configured keyword text. A subsequent send to a blocked
  number is still **accepted** by the API (2xx → `sent`); Twilio then fails it asynchronously with
  `21610`, which the app does **not** observe (no callback) — and that is the desired outcome for an
  opted-out number. So the app makes no `21610`/`failed`-classification claim. **There is no inbound
  webhook and no `PhoneBlock` model** — nothing to keep ordered or reconciled. The only app-side SMS
  gate is application consent (`sms_opt_out`, FR-42): a send goes out iff `not reg.sms_opt_out`.
  Re-consent of a provider-blocked number is by texting START (Twilio unblocks); the website toggle
  controls only application consent and is independent of Twilio's blocklist. (FR-42/43; TC-055/056.)

### i18n
Public form markup uses `{% trans %}`; `makemessages -l es` → translate → `compilemessages`. The
form **always offers both EN and ES** — there is no per-event language config (FR-6/FR-33), so every
event's public form exposes the same EN/ES toggle. The `?lang=en|es` toggle sets the
`django_language` cookie (any other value is ignored, falling back to the current language), and the
chosen value is persisted to `Registration.language` (TC-006/046) and selects the SMS catalog.

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
`export_event(event_slug, fmt)` (**Admin-only, role-gated — FR-29/Decision 16**). CSV via `csv.writer` + `StreamingHttpResponse`;
XLSX via `openpyxl` → `BytesIO`. Columns: owner first/last name, phone, address, email; per animal
name, species, age, sex, breed, color, services; plus status, AnimalID, language, printed.
**Default = one row per animal** (owner + AnimalID repeated — best for the Admin's per-animal vaccine
notes; matches "per animal" in FR-29); `?per=registration` rollup optional (TC-032).

---

## Build phases

| Phase | Build | Key files | FRs / TCs |
|---|---|---|---|
| **0 Scaffolding** | `git init`; `.gitignore`; `startproject config .` + settings split; 8 app packages; requirements; `runtime.txt`; `render.yaml`; `.env.example`; `templates/` `static/` `locale/` | `manage.py`, `config/settings/base.py`, `config/urls.py`, `requirements/base.txt`, `render.yaml` | NFR-2 plumbing |
| **1 Models + admin** | All 4 models (`Event`, `Registration`, `Animal`, `User`), `makemigrations`, partial unique index, read-time window helpers + `z_applicants` soft cap + per-event `timezone` (IANA select) + `auto_run_deadline` + **tz-aware `open_at`/`close_at` entry/display**; SMS on `Registration`: `result_sms_state`/`_sent_at` (fire-and-forget) + `sms_opt_out` (application consent); no SMS-specific models; full Django admin (back-office) with fieldsets, list_display/filter/search, `next_animal_id` + `assign_next_walkin_id`; forward-only `Event.transition()` (`status` `editable=False`; `signup_open` also requires `lottery_run_at is None`); `Event.next_staff_id` + `Registration.id_source`; provenance `creation_source`/`created_by_user`/`admitted_by_user`/`admitted_at`; custom `UserManager` + `User.clean()` (Admin = superuser) | `events/models.py`, `register/models.py`, `accounts/models.py`, `*/admin.py` | FR-1/2/4/8/14/30/37/38; TC-002, TC-009, TC-047, TC-058, TC-059 |
| **2 Auth + Event admin + QR/URL** | `accounts` login/logout (lean on `LoginView`); auto `slug` (slugify + uniqueness loop, retry on `IntegrityError`); flyer page with sign-up URL + "Download QR JPG" (`qrcode`→Pillow→`HttpResponse` jpg); admin **delete entire event** (cascade, **Admin-only**) behind a confirmation warning (R-9); event create/configure are likewise **Admin-only** (role-gated — Decision 16) | `accounts/views.py`, `events/admin.py`, `events/services_qr.py`, `events/views.py`, `templates/registration/login.html` | FR-1/2/3/30/32/39; TC-001/003/033/035/048 |
| **3 Public form + i18n + SMS #1** | `signup(slug)` guarded by `signup_open()` **and `not at_capacity()` (R-10: Z soft applicant cap → friendly full message; slight overshoot ok)**; `OwnerForm` (+ `sms_consent` checkbox, default on) + dynamic `AnimalFormSet(min_num=1, max_num=6)`; confirmation screen (no guaranteed time; shows the edit link even if SMS was declined); persist language; fire SMS #1 to consenters | `register/{views,forms,urls}.py`, `sms/{services,templates,backends/*}.py`, `locale/es/…django.po`, `templates/register/{signup,confirm}.html` | FR-5/6/7/8/9/10/11/16/18/31/33/38/42; TC-004/005/006/007/008/010/011/016/037/046/047/051/054 |
| **4 Token edit + window rules** | `edit_entry(slug, token)`; `owner_can_edit`/`owner_can_add` guards; add disabled post-close (server-validated); **edit/remove until check-in/event-completion** (mutation locks after that; GET always renders — FR-41); **status banner (FR-41) + SMS-preference toggle (FR-42)**; atomic save | `register/views.py`, `templates/register/edit.html` | FR-20/21/22/34/41/42; TC-020/021/022/023/024/041/042/053/054 |
| **5 Lottery** | `run_lottery` service (Event-row lock + post-lock guard) + exceptions; admin "Run lottery" action (**Admin-only**; the cron auto-run is system-level, not a user privilege — Decision 16); `run_due_lotteries` command for the **auto-fallback at noon day-after-close** (R-4/FR-40) | `lottery/{services,exceptions,admin}.py`, `lottery/management/commands/run_due_lotteries.py` | FR-12/13/14/15/40; TC-012/013/014/015/049/050 |
| **6 Lottery-result SMS #2** | `result_body` (3 branches); `notify_lottery_results` to every **consenting** registrant in stored language (gate: `not sms_opt_out`); **fire-and-forget** send — atomic `result_sms_state null→sending` claim committed before the POST, classify 2xx→`sent` (accepted), 4xx→`failed` (sync, e.g. invalid number), 5xx/conn/timeout/no-response→`unknown` (process crash leaves `null`/`sending`); **never retried**, no callback, no webhook. STOP/START left to Twilio Advanced Opt-Out (not mirrored, async `21610` unobserved). Edit link via `absolute_url`/`PUBLIC_BASE_URL`; wired after lottery run | `sms/templates.py`, `sms/{services,backends/*}.py`, `lottery/services.py` | FR-17/18/19; TC-017/018/019/055/056 |
| **7 Clinic check-in + lookup** | `LoginRequiredMixin` views: `select_event` (session), `lookup` (AnimalID exact / fuzzy name+phone, **event-scoped**), `detail` (editable, `max_num=None`), add/remove/save, `check_in`; ordered waitlist list (no promotion) | `clinic/{views,urls}.py`, `templates/clinic/*` | FR-23/24/25/26/27; TC-025/026/027/028/029/030/034/036 |
| **8 Print payload + stub + printed_at** | `label_payload`, `mark_printed`, browser print stub | `printing/{views,urls,serializers}.py`, `templates/clinic/print_stub.html` | FR-28/35 (backend half); TC-031/043 |
| **9 Export (Admin-only)** | CSV streaming + XLSX builders (role-gated: admin only — FR-29/Decision 16) | `export/{views,urls,exporters}.py` | FR-29; TC-032 |
| **10 Walk-in add + admit (both roles, post-lottery)** | **Add walk-in** (clinic UI, both admin & volunteer): create Registration (`creation_source=staff`, `created_by_user`=actor, no 6-animal cap — FR-36); **admit** an existing `registered`/`not_selected` row (FR-37). Both **auto-assign the next 1000+ ID via `assign_next_walkin_id`** (locks `Event.next_staff_id`) and atomically set `status='selected'` (admit leaves `creation_source`/`created_by_user` untouched; records `admitted_by_user`/`admitted_at`); the system assigns the number — **no manual ID entry, no editing IDs on numbered rows**; 1000+ IDs are **not counted toward X/Y**; both rejected before the lottery has run. `clean()` + partial index enforce 1..999/≥1000 + event-unique (catch `IntegrityError`) | `clinic/views.py`, `register/{admin,forms}.py` | FR-36/37; TC-044/045 |
| **11 Deploy to Render** | `render.yaml` (web service + Postgres); `prod.py` (DEBUG=False, SSL redirect, secure cookies, WhiteNoise, `dj_database_url` ssl); set **`PUBLIC_BASE_URL`** (canonical HTTPS origin for SMS edit-links); migrations in `preDeployCommand`, collectstatic at build; `ensure_admin` command (creates the initial **Admin** as a Django superuser — `is_staff=True` + `is_superuser=True` + `role=admin`; **volunteers** are provisioned later as `is_staff=False`/`is_superuser=False`/`role=volunteer` — Decision 16); **Cron Job** running `manage.py run_due_lotteries` hourly (R-4/FR-40 auto-lottery); **provision a Twilio Messaging Service** (`TWILIO_MESSAGING_SERVICE_SID`) + a **US sender registered for A2P 10DLC** (Brand + Campaign) **or a verified toll-free number** — a one-time approval with **days of lead time**, required for US application-to-person messaging (complete *before* deploy; Oakland recipients are US); enable **Advanced Opt-Out** (STOP/START/HELP provider-side; off by default, no webhooks — FR-43); **deploy smoke (TC-057, FR-43/NFR-3)** — on a real US handset, using a **fresh registration for each probe send** (the app sends at most one result-SMS per registration): **HELP first** → confirm the HELP reply (an opted-out number may not receive it, so test HELP before STOP); then send a live result-SMS → accepted (2xx) + arrives; then STOP → STOP reply + next send blocked; then START → START reply + delivery restored. SMS is not deployable until TC-057 passes. | `render.yaml`, `config/settings/prod.py`, `config/wsgi.py`, `accounts/management/commands/ensure_admin.py` | NFR-1/2/3, FR-32/40/43; TC-038/039/049/055/056/057 |
| **12 (outline) Flutter print station** | Convert `/home/dev/vet_app` → WebView shell over the deployed site; JS bridge → existing `MethodChannel('com.example.vet_app/printer')`; **rewrite native TSC layout** in `MainActivity.kt::printLabel` to consume the grouped payload; Print button → bridge → `mark_printed`. | `/home/dev/vet_app/**` | NFR-4 (full); TC-040 |

---

## Testing strategy (maps to TraceabilityMatrix)

`pytest-django` + `factory_boy` for unit/integration; Playwright for E2E; manual + deploy before
each release. All SMS-sending tests use the `locmem` backend; TC-039 additionally grep-asserts no
creds in source. **Locking tests (TC-049 before-close lottery guard, TC-050 single-run, TC-047
soft-cap) require PostgreSQL** — `select_for_update()` is a no-op on SQLite — so run them under a
Postgres `TransactionTestCase`/pytest-django job, not the default SQLite dev DB.

**Highest-value automation — the lottery core (Phase 5):** TC-012 (cap math), TC-013 (randomness
distribution over ~2000 seeded runs), TC-014 (statuses + unique IDs), TC-015 (sequential from 1,
contiguous, max 999). `run_lottery(event, rng=random.Random(seed))` makes these fully deterministic.

Other automatable: TC-002 (slug), TC-004 (window), TC-007/008 (validation + cap), TC-016/017/018/019
(SMS via locmem), TC-031 (payload shape), TC-032 (export columns), TC-039 (env creds), TC-041
(post-close add blocked), TC-043 (printed_at), TC-044/045 (manual entry + AnimalID), TC-046
(language stored), TC-047 (applicant cap Z — Postgres), TC-048 (event deletion), TC-049 (noon
auto-run), TC-050 (no concurrent double-run — Postgres), TC-051 (≥1 animal), TC-052 (over-cap owner
edit), TC-053 (edit-link shows result), TC-054 (SMS consent checkbox / opt-out), TC-055
(fire-and-forget delivery: one send, 2xx→sent / 4xx→failed / 5xx→unknown, never retried),
TC-056 (provider-side STOP/START via Advanced Opt-Out; not mirrored; app-consent independent).
E2E/manual/deploy: TC-005/006/010/011/020–030/033/034/036/037/038/040/057.

---

## Security & access (FR-30..32, NFR-3)

- `LoginRequiredMixin` on every `clinic`/`printing`/`export`/event-admin view; public only on
  `register` signup + edit.
- Owner self-edit auth = the 256-bit `edit_token` + window/check-in state (FR-20..22). **No public
  index** of registrations — no list view, no enumeration (FR-32).
- CSRF on all POSTs (Django default) — including signup/edit; prod `SECURE_SSL_REDIRECT`,
  `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`; secrets only in env. (No Twilio webhooks in V1 —
  STOP/START are handled provider-side by Advanced Opt-Out — so there are **no** CSRF exemptions.)

---

## Deployment (Render)

`render.yaml`: one **web service** (`python` runtime; build = `pip install -r requirements/prod.txt
&& python manage.py collectstatic --noinput`; start = `gunicorn config.wsgi --log-file -`;
pre-deploy = `python manage.py migrate`) + one **Postgres** add-on (auto-injects `DATABASE_URL`).

**Env vars (never in code):** `DATABASE_URL`, `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS`,
**`PUBLIC_BASE_URL`** (the canonical `https://<host>` origin — validated HTTPS; the single source
for SMS edit-links built by `absolute_url()`, so they are correct from request context **and** from
the lottery notification path), `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
**`TWILIO_MESSAGING_SERVICE_SID`** (the `MG…` Messaging Service — production sends go through it so
Advanced Opt-Out works; `TWILIO_FROM_NUMBER` is retained only for local-dev/console fallback), (+
bootstrap `ADMIN_USERNAME`/`ADMIN_PASSWORD`/`ADMIN_EMAIL`). **Twilio provisioning (once, in the
Console — allow days of lead time):** create the Messaging Service; **register a US sender** — either
a local 10-digit number registered to an approved **A2P 10DLC Brand + Campaign**, or a **verified
toll-free number** (unverified toll-free/10DLC senders are blocked from US/Canada A2P traffic) — add
it to the sender pool; and **enable Advanced Opt-Out** (STOP/START/HELP provider-side; **no webhooks**
to configure — FR-43). Gotchas: link Postgres before first boot; WhiteNoise above other middleware;
no writable disk at runtime → collectstatic at build.

---

## Risks & open items (dispositions from review)

- **R-1 Phone/SMS deliverability — RESOLVED.** Cell-phone-only is an accepted requirement. Keep
  `phonenumbers` validation + E.164 normalization; drop the Twilio-lookup idea.
- **R-2 Duplicate owners — RESOLVED (by design).** We deliberately do NOT enforce (event, owner)
  uniqueness. Each Registration has a unique PK (`registrantID`) + `animal_id` + `edit_token`; the
  edit URL carries the token. Two people with identical name/phone/pet simply create two rows —
  nothing breaks. Clinic lookup by name/phone may return multiple matches; narrowing by RegistrantID
  or AnimalID resolves it. (Acceptable per review.) **SMS opt-out (FR-42/43):** application consent
  (`sms_opt_out`) is **per-registration** — one owner declining does **not** affect another
  registration sharing the phone, so two duplicate-phone rows may legitimately differ in consent.
  Provider-side STOP/START is handled by Twilio Advanced Opt-Out (the app does **not** mirror it);
  a send to a STOP'd number is still **accepted** (`sent`) — Twilio honors the opt-out asynchronously
  (`21610`, unobserved). A send goes out iff that registration's own `sms_opt_out` is clear.
- **R-3 Status-display drift — ELIMINATED by design.** The `status` column stores only discrete
  admin-driven stages; the **displayed** open/closed label is computed live from
  `open_at`/`close_at` (+ the `live` stage). So the admin always sees reality — no drift, no cron
  needed. (Never a correctness bug; now not even a cosmetic one.)
- **R-4 Lottery trigger — RESOLVED (hybrid).** Runs when the Admin clicks "Run lottery" **or**
  automatically if not yet run by **noon on the day after `close_at`** (so the Admin can't forget,
  and the result texts still go out at a civilized hour). Both paths call one `run_lottery` that
  **locks the Event row inside the transaction and re-checks `lottery_run_at` after the lock**, so a
  concurrent manual click and cron run cannot double-run (TC-050). Auto path = `run_due_lotteries`
  command on a Render Cron Job (hourly) + an admin "overdue lottery" warning/one-click-run banner as
  a no-cron fallback. Result SMS is **fire-and-forget: at-most-once** (one send per registration —
  2xx→`sent` (accepted), 4xx→`failed` (sync), 5xx/conn/timeout/no-response→`unknown` (process crash leaves `null`/`sending`); **never retried**, so no
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
  ≤Z) — budget approved by the Admin. Consent = an application-level signup checkbox (default on) +
  "Reply STOP to opt out" on every SMS; STOP/START are honored **provider-side** by Twilio Advanced
  Opt-Out on the Messaging Service (not mirrored in-app). The Z cap (R-10) bounds the blast; exact
  compliance copy polished at build time. Delivery is fire-and-forget / best-effort, not guaranteed.

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
   are absent from the repo (`git grep`). **Run the SMS deploy smoke (TC-057):** on a real US handset,
   using a **fresh registration per probe send** (at-most-one result-SMS per registration) — **HELP
   first** (an opted-out number may not receive the HELP reply), then send a live result-SMS (accepted
   2xx + arrives), then STOP → next send blocked, then START → delivery restored — to confirm Advanced
   Opt-Out is enabled. Do not declare SMS deployable until TC-057 passes.
8. **Phase 12 (later):** print real owner + grouped pet labels on the 3nStar PPT305BT (TC-040) and
   lock `ANIMALS_PER_LABEL`.
