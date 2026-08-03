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
- `languages` JSONField(default=list) — subset of `["en","es"]`
- `status` CharField(choices=draft/live/lottery_run/active/completed, default=draft) — the open↔closed distinction is a **computed display label** (open iff `status == 'live'` and `open_at ≤ now < close_at`), never stored (R-3)
- `lottery_run_at` DateTimeField(null, blank) — durable **single-run guard** (the lottery sets it once; also the marker the auto-run check uses). It is **not** a signup gate — signups are time-window + `live`-status driven (FR-4)
- `created_at`, `updated_at`
- **Methods (authoritative):** `@property services_offered`; `is_published()` = `status == 'live'`; `signup_open(now=None)` = `is_published() and open_at ≤ now < close_at` (**FR-4: signups are accepted only during `[open_at, close_at)`**; once the lottery runs, `status` advances past `live`, which also closes signups — so reopening `close_at` after the lottery cannot reopen signups); `at_capacity()` = `registrations.count() >= z_applicants` (**soft cap** — not locked; concurrent signups at the boundary may overshoot by a few, which is acceptable; R-10); `auto_run_deadline()` = noon (12:00 local) on the calendar day after `close_at`, computed in `self.timezone` (returns a tz-aware datetime for comparison against `timezone.now()`); `owner_can_add(reg)` = `signup_open() and reg.status != 'checked_in'`; `owner_can_edit(reg)` = `status != 'completed' and reg.status != 'checked_in'`. The **new-signup** view additionally requires `not at_capacity()` — Z gates only brand-new registrations, not an existing owner adding animals. The check + insert are deliberately **not serialized** (no Event-row lock): Z is a soft target and a few over is fine (R-10; TC-047). Displayed open/closed is computed live — no cached drift.

### `register.Registration`
- `event` FK(Event, related_name=registrations, CASCADE)
- `animal_id` PositiveIntegerField(null, blank)
- `status` choices: registered/selected/waitlisted/not_selected/checked_in (default registered)
- `edit_token` CharField(unique, db_index, default=`token_urlsafe(32)`) — 256-bit, only auth for self-edit
- `language` CharField(2, choices en/es, default en) — **chosen at signup, drives SMS**
- `printed_at`, `checked_in_at` DateTimeField(null, blank)
- `result_sms_state` CharField(null/sending/sent/failed/unknown, default null) — **fire-and-forget**
  result-SMS status for admin/export ("did this reg get its result SMS?"). Atomically claim
  `null→sending` before the send (only the claimant sends), then classify: `sent` on a definitive
  Twilio acceptance (2xx); `failed` on a definitive rejection (4xx / `21610` provider-blocked);
  `unknown` on an ambiguous outcome (5xx / connection error / timeout / crashed worker). **Never
  retried** — one send per registration, so at-most-once is trivially true. Best-effort; the
  edit-link status page is the reliable channel (FR-41).
- `result_sms_sent_at` DateTimeField(null, blank, set only when state=`sent`)
- `sms_opt_out` BooleanField(default=False) — **application-level consent** (the only app-side SMS
  gate), registration-local. Changed only by the owner: the signup consent checkbox (FR-42) and the
  edit-link toggle. Provider-side STOP/START (Twilio Advanced Opt-Out) is **not** mirrored — a send
  to a provider-blocked number simply returns `21610` → `failed` (FR-43). When True, signup + result
  SMS are skipped; status is still shown on the edit-link page (FR-41).
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
  the lottery/retry-free notification path (no `request` there). In **SMS #1 (every consenting
  registrant)** and **SMS #2 only for selected/waitlisted**; the not-selected courtesy text has no
  link (FR-17/FR-20, TC-018).
- **Delivery is fire-and-forget: best-effort, at-most-once, never retried.** SMS is a *convenience*
  channel; the edit-link status page (FR-41) is the reliable one, so the app sends each message
  **once** and moves on. Per result SMS: atomically claim `Registration.result_sms_state
  null→sending` (`filter(pk=reg.pk, result_sms_state__isnull=True).update(result_sms_state='sending')`
  — only the claimant sends, committed **before** the Twilio POST so a crash leaves a reconcileable
  `sending`), then call Twilio (Messaging Service) and classify:
  - **HTTP 2xx** → `result_sms_state='sent'` + `result_sms_sent_at`. (Accepted ≠ delivered; delivery
    is not tracked further — best-effort.)
  - **4xx / `21610`** (invalid number, or the number is provider-blocked via STOP) →
    `result_sms_state='failed'`. Logged; **not retried.**
  - **5xx / connection error / timeout / no response / crashed worker** → `result_sms_state='unknown'`.
    **Not retried** (a 5xx doesn't prove the message wasn't created — RFC 9110 §9.2.2); flagged for
    review. A stale `sending` row (crashed worker) is swept to `unknown` by a periodic check, never
    re-sent.
  No `retry_sms`, no delivery-status callback, no per-message `StatusCallback` URL. The signup SMS
  (#1) is the same fire-and-forget send (no state tracked — it's immediate on submit). Sends are
  concurrent (small pool) with per-reg try/except + logging. (TC-055/056.)
- **Opt-out (FR-43) — provider-side, not mirrored.** STOP/START/HELP are handled entirely by Twilio
  **Advanced Opt-Out** on the Messaging Service (enabled once in the Console): Twilio maintains the
  per-number blocklist, replies with the configured keyword text, and returns `21610` on sends to
  blocked numbers — which the app simply classifies as `failed` (above). **There is no inbound
  webhook and no `PhoneBlock` model** — the app does not mirror Twilio's blocklist, so there is no
  opt-out state to keep ordered or reconciled. The only app-side SMS gate is application consent
  (`sms_opt_out`, FR-42): a send goes out iff `not reg.sms_opt_out`. Re-consent of a provider-blocked
  number is by texting START (Twilio unblocks); the website toggle controls only application consent
  and is independent of Twilio's blocklist. (FR-42/43; TC-055/056.)

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
| **1 Models + admin** | All 4 models (`Event`, `Registration`, `Animal`, `User`), `makemigrations`, partial unique index, read-time window helpers + `z_applicants` soft cap + per-event `timezone` (IANA select) + `auto_run_deadline` + **tz-aware `open_at`/`close_at` entry/display**; SMS on `Registration`: `result_sms_state`/`_sent_at` (fire-and-forget) + `sms_opt_out` (application consent); no SMS-specific models; full Django admin (back-office) with fieldsets, list_display/filter/search, `next_animal_id` | `events/models.py`, `register/models.py`, `accounts/models.py`, `*/admin.py` | FR-1/2/8/14/37/38; TC-002, TC-009, TC-047 |
| **2 Auth + Event admin + QR/URL** | `accounts` login/logout (lean on `LoginView`); auto `slug` (slugify + uniqueness loop, retry on `IntegrityError`); flyer page with sign-up URL + "Download QR JPG" (`qrcode`→Pillow→`HttpResponse` jpg); admin **delete entire event** (cascade) behind a confirmation warning (R-9) | `accounts/views.py`, `events/admin.py`, `events/services_qr.py`, `events/views.py`, `templates/registration/login.html` | FR-1/2/3/30/32/39; TC-001/003/033/035/048 |
| **3 Public form + i18n + SMS #1** | `signup(slug)` guarded by `signup_open()` **and `not at_capacity()` (R-10: Z soft applicant cap → friendly full message; slight overshoot ok)**; `OwnerForm` (+ `sms_consent` checkbox, default on) + dynamic `AnimalFormSet(min_num=1, max_num=6)`; confirmation screen (no guaranteed time; shows the edit link even if SMS was declined); persist language; fire SMS #1 to consenters | `register/{views,forms,urls}.py`, `sms/{services,templates,backends/*}.py`, `locale/es/…django.po`, `templates/register/{signup,confirm}.html` | FR-5/6/7/8/9/10/11/16/18/31/33/38/42; TC-004/005/006/007/008/010/011/016/037/046/047/051/054 |
| **4 Token edit + window rules** | `edit_entry(slug, token)`; `owner_can_edit`/`owner_can_add` guards; add disabled post-close (server-validated); edit/remove always; **status banner (FR-41) + SMS-preference toggle (FR-42)**; atomic save | `register/views.py`, `templates/register/edit.html` | FR-20/21/22/34/41/42; TC-020/021/022/023/024/041/042/053/054 |
| **5 Lottery** | `run_lottery` service (Event-row lock + post-lock guard) + exceptions; admin "Run lottery" action; `run_due_lotteries` command for the **auto-fallback at noon day-after-close** (R-4/FR-40) | `lottery/{services,exceptions,admin}.py`, `lottery/management/commands/run_due_lotteries.py` | FR-12/13/14/15/40; TC-012/013/014/015/049/050 |
| **6 Lottery-result SMS #2** | `result_body` (3 branches); `notify_lottery_results` to every **consenting** registrant in stored language (gate: `not sms_opt_out`); **fire-and-forget** send — atomic `result_sms_state null→sending` claim committed before the POST, classify 2xx→`sent`, 4xx/`21610`→`failed`, 5xx/conn/timeout/crash→`unknown`; **never retried**, no callback, no webhook. STOP/START left to Twilio Advanced Opt-Out (not mirrored). Edit link via `absolute_url`/`PUBLIC_BASE_URL`; wired after lottery run | `sms/templates.py`, `sms/{services,backends/*}.py`, `lottery/services.py` | FR-17/18/19; TC-017/018/019/055/056 |
| **7 Clinic check-in + lookup** | `LoginRequiredMixin` views: `select_event` (session), `lookup` (AnimalID exact / fuzzy name+phone, **event-scoped**), `detail` (editable, `max_num=None`), add/remove/save, `check_in`; ordered waitlist list (no promotion) | `clinic/{views,urls}.py`, `templates/clinic/*` | FR-23/24/25/26/27; TC-025/026/027/028/029/030/034/036 |
| **8 Print payload + stub + printed_at** | `label_payload`, `mark_printed`, browser print stub | `printing/{views,urls,serializers}.py`, `templates/clinic/print_stub.html` | FR-28/35 (backend half); TC-031/043 |
| **9 Export** | CSV streaming + XLSX builders | `export/{views,urls,exporters}.py` | FR-29; TC-032 |
| **10 Admin manual entry + AnimalID** | Admin create Registration (`created_by=admin`, no cap); "next available" AnimalID button; `clean()` + partial index enforce 1..999 + event-unique (catch `IntegrityError`) | `register/{admin,forms}.py` | FR-36/37; TC-044/045 |
| **11 Deploy to Render** | `render.yaml` (web service + Postgres); `prod.py` (DEBUG=False, SSL redirect, secure cookies, WhiteNoise, `dj_database_url` ssl); set **`PUBLIC_BASE_URL`** (canonical HTTPS origin for SMS edit-links); migrations in `preDeployCommand`, collectstatic at build; `ensure_admin` command; **Cron Job** running `manage.py run_due_lotteries` hourly (R-4/FR-40 auto-lottery); **provision a Twilio Messaging Service** (`TWILIO_MESSAGING_SERVICE_SID`) + sender pool and **enable Advanced Opt-Out** (so STOP/START/HELP are handled provider-side; no webhooks to configure — FR-43) | `render.yaml`, `config/settings/prod.py`, `config/wsgi.py`, `accounts/management/commands/ensure_admin.py` | NFR-1/2/3, FR-32/40/43; TC-038/039/049/055/056 |
| **12 (outline) Flutter print station** | Convert `/home/dev/vet_app` → WebView shell over the deployed site; JS bridge → existing `MethodChannel('com.example.vet_app/printer')`; **rewrite native TSC layout** in `MainActivity.kt::printLabel` to consume the grouped payload; Print button → bridge → `mark_printed`. | `/home/dev/vet_app/**` | NFR-4 (full); TC-040 |

---

## Testing strategy (maps to TraceabilityMatrix)

`pytest-django` + `factory_boy` for unit/integration; Playwright for E2E; manual + deploy before
each release. All SMS-sending tests use the `locmem` backend; TC-039 additionally grep-asserts no
creds in source. **Concurrency/locking tests (TC-050 single-run, TC-047 soft-cap) require
PostgreSQL** — `select_for_update()` is a no-op on SQLite — so run them under a Postgres
`TransactionTestCase`/pytest-django job, not the default SQLite dev DB.

**Highest-value automation — the lottery core (Phase 5):** TC-012 (cap math), TC-013 (randomness
distribution over ~2000 seeded runs), TC-014 (statuses + unique IDs), TC-015 (sequential from 1,
contiguous, max 999). `run_lottery(event, rng=random.Random(seed))` makes these fully deterministic.

Other automatable: TC-002 (slug), TC-004 (window), TC-007/008 (validation + cap), TC-016/017/018/019
(SMS via locmem), TC-031 (payload shape), TC-032 (export columns), TC-039 (env creds), TC-041
(post-close add blocked), TC-043 (printed_at), TC-044/045 (manual entry + AnimalID), TC-046
(language stored), TC-047 (applicant cap Z — Postgres), TC-048 (event deletion), TC-049 (noon
auto-run), TC-050 (no concurrent double-run — Postgres), TC-051 (≥1 animal), TC-052 (over-cap owner
edit), TC-053 (edit-link shows result), TC-054 (SMS consent checkbox / opt-out), TC-055
(fire-and-forget delivery: one send, 2xx→sent / 4xx,21610→failed / 5xx→unknown, never retried),
TC-056 (provider-side STOP/START via Advanced Opt-Out; not mirrored; app-consent independent).
E2E/manual/deploy: TC-005/006/010/011/020–030/033/034/036/037/038/040/063.

---

## Security & access (FR-30..32, NFR-3)

- `LoginRequiredMixin` on every `clinic`/`printing`/`export`/event-admin view; public only on
  `register` signup + edit.
- Owner self-edit auth = the 256-bit `edit_token` + window/check-in state (FR-20..22). **No public
  index** of registrations — no list view, no enumeration (FR-32).
- CSRF on all POSTs (Django default); prod `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`,
  `CSRF_COOKIE_SECURE`; secrets only in env. (No Twilio webhooks in V1 — STOP/START are handled
  provider-side by Advanced Opt-Out — so there are **no** CSRF-exempt public POSTs beyond signup/edit.)

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
Console):** create the Messaging Service, add a SMS-capable number to its sender pool, and **enable
Advanced Opt-Out** — that's it; STOP/START/HELP are handled provider-side, so **no webhooks** need
configuring (FR-43). Gotchas: link Postgres before first boot; WhiteNoise above other middleware; no
writable disk at runtime → collectstatic at build.

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
  a send to a provider-blocked number simply returns `21610` → `failed`. A send goes out iff that
  registration's own `sms_opt_out` is clear.
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
  2xx→`sent`, 4xx/`21610`→`failed`, 5xx/conn/timeout/crash→`unknown`; **never retried**, so no
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
   are absent from the repo (`git grep`).
8. **Phase 12 (later):** print real owner + grouped pet labels on the 3nStar PPT305BT (TC-040) and
   lock `ANIMALS_PER_LABEL`.
