# Address PR #1 round-7 audit (latest comment, `d51aa26` re-audit, 2026-08-04) — v2

> Amended implementation plan for the 2026-08-04 re-audit of PR #1 ("Phase 0: scaffolding"),
> incorporating all 10 review amendments. Source of the findings: the latest PR comment
> (re-audit of pushed head `d51aa26`).

## Context

PR #1 ("Phase 0: scaffolding") is on its 7th audit→fix round. The **latest** comment (2026-08-04,
re-audit of pushed head `d51aa26`) lists 8 findings. The unpushed local `a8f9bf5` already resolved
**finding 6** (removed per-event `languages`) and the TC-057-smoke + TC-021/057/049-traceability
parts of **7/8** — but it also encoded a **flawed TC-057 opt-out sequence** that amendment 7 fixes.
This change closes the rest: **findings 1–5, the Twilio config drift in 7, and doc remnants in 8**,
hardened per the 10 review amendments.

**What is real code now vs. spec (Phase 1+ hasn't been built — only `accounts.User` exists):**
- **Real code in this PR:** F1 (`accounts` manager + migration 0002 + `UserAdmin` + tests) and F7
  (`render.yaml`, `config/settings/base.py`, `.env.example`, **`config/settings/prod.py` fail-closed**).
- **Spec (docs, built in later phases):** F2 (Event lifecycle), F3 (lottery), F4 (walk-in/admit
  IDs), F5 (provenance fields), F8 (remnants), and the non-F1 test cases.

## Confirmed decisions (this session + amendments)

- **F1 — Admin = superuser; manager rejects every inconsistent combo (amendments 1, 2, 10).**
  `UserManager` subclasses Django's `UserManager` (preserves `acreate_user`/`acreate_superuser`/
  `with_perm`). `create_user` **rejects** any staff/superuser flag or `role=admin`; `create_superuser`
  **rejects** `is_staff=False`/`is_superuser=False`/`role=volunteer` and forces admin. Model + UserAdmin
  validation enforce the same on edit. Real pytest suite required.
- **F2 — atomic one-step `transition()` + defense-in-depth (amendment 3).** `transition()` locks +
  reloads the Event row and moves exactly one step; **all** status writes (incl. the lottery) go
  through it. `signup_open()` additionally requires `lottery_run_at is None` (read-only admin alone
  isn't enough).
- **F3 — per-bucket low-demand math (amendment 4).** Selected (target X) and waitlist (target Y)
  are computed independently on the actual remainder (selected overshoot reduces the waitlist pool);
  each bucket falls back to "all remaining, total below target" when demand is short; empty input
  still completes; X and Y may each be 0.
- **F4 — 1000+ allocation via a per-event counter; `id_source` field (amendment 5).** Lottery IDs
  1..999; staff/walk-in IDs from `Event.next_staff_id` (default 1000), incremented under the
  Event-row lock (no `max()+1`). `animal_id` read-only outside the allocation services. Add
  `Registration.id_source` (lottery/staff) so `clean()` can enforce range↔source (since
  `1..999 ∪ ≥1000` is every positive int). Post-lottery only; no re-assigning IDs on numbered rows.
- **F5 — two-value provenance + separate admission fields (amendment 6).** `creation_source` =
  public/staff; `created_by_user` nullable FK. Admitting an existing public row does **not** touch
  its provenance — set `admitted_by_user` + `admitted_at` instead.
- **F7 — fail-closed prod + corrected smoke order (amendments 7, 8).** `prod.py` rejects
  `SMS_BACKEND=twilio` unless `PUBLIC_BASE_URL` (valid https) and `TWILIO_MESSAGING_SERVICE_SID`
  (`MG…`) are set. TC-057 tests HELP **before** STOP (or after START) and uses a fresh registration
  per probe send.

## Per-finding changes

### F1 — Admin provisioning (real code + tests + docs)
- **`accounts/models.py`** — `class UserManager(UserManager)` with `use_in_migrations = True`:
  - `create_user(..., role=VOLUNTEER, is_staff=False, is_superuser=False)`: **raise `ValueError`** if
    `is_staff`/`is_superuser` is True or `role == ADMIN` ("use create_superuser for an admin").
  - `create_superuser(...)`: **raise** unless `is_staff and is_superuser`; **raise** if
    `role not in (ADMIN, None)`; default+force `role=ADMIN`.
  - Inherits `acreate_user`/`acreate_superuser`/`with_perm` from the contrib manager.
  - Assign `objects = UserManager()` on `User`; add `User.clean()` rejecting inconsistent combos
    (superuser ⇒ role=admin & is_staff; volunteer ⇒ not staff/superuser). Update the docstring.
- **`accounts/admin.py`** — real `UserAdmin(UserAdmin)` with a form whose `clean()` enforces the same
  invariants on edit; register `User`.
- **`accounts/migrations/0002_manager_and_repair.py`** (new; 0001 left intact — dev DB already has it
  applied): `AlterModelManagers` → custom manager + `RunPython(repair_superuser_roles, noop)` that
  sets `role=admin` (and `is_staff=True`) on every `is_superuser=True` user. Idempotent; reversible.
- **`accounts/tests.py`** — real pytest-django suite (sqlite, isolated DB), covering: sync
  `create_user`/`create_superuser`; async `acreate_*`; contradictory-arg rejection both ways;
  `with_perm` still works; the `createsuperuser` management command → admin; model + UserAdmin form
  validation rejecting inconsistent edits; and the **0002 repair** of an existing volunteer-role
  superuser → admin (build a superuser with role=volunteer directly, run the migration's function,
  assert role flipped).
- **Docs** — rewrite "is_staff=True / is_superuser=False / gates on is_staff" → "Admin is a
  superuser (`is_staff`+`is_superuser`+`role=admin` via `createsuperuser`/`ensure_admin`); volunteers
  `is_staff=False`; custom views gate on `role==admin`": `Requirements.md:143,282,412`;
  `Architecture.md:87,257,309`; `Decisions.md:107`; `ImplementationPlan.md:143,316`;
  `TraceabilityMatrix.md:105`; `README.md:20,34`.

### F2 — forward-only, atomic lifecycle (spec; Event is Phase 1)
- **`ImplementationPlan.md`** data model (`:95`) + methods (`:98`): `Event.transition(target,
  *, by=None)` — `transaction.atomic()` + `select_for_update().get(pk=self.pk)` reload; validate
  exactly one forward step (`draft→live→lottery_run→active→completed`); `raise InvalidTransition`
  on backward/skip; save. **All** status writes (Publish, Run-lottery, Activate, Complete, and the
  lottery's `live→lottery_run`) go through it. `status` is `editable=False` in the admin form.
  Defense-in-depth: `signup_open()` = `is_published() and lottery_run_at is None and open_at ≤ now <
  close_at` (so even a regressed `status` can't reopen signups once `lottery_run_at` is set).
- **`Requirements.md`** §4 (`:68-73`), FR-4 (`:360`); **`Architecture.md`** §5 (`:140-146`); Phase 1
  row (`ImplementationPlan.md:306`): state the atomic transition + `signup_open` hardening.
- **TC-058 (new, I)** — backward and skip transitions rejected; forward succeed; raw `status`
  read-only in admin; `signup_open()` is False once `lottery_run_at` is set even if `status` is
  forced back to `live`. (Postgres, for the row lock.) Map to FR-4; register in §3.

### F3 — per-bucket low-demand lottery (spec; lottery is Phase 5)
- **`ImplementationPlan.md`** algorithm (`:163-171`): define per bucket (selected target X,
  waitlist target Y), each operating on the **remainder** after the prior bucket:
  - If enough animals remain to reach the target → bucket total ∈ `[target, target+M)` (M = largest
    animal count among that bucket's eligible regs).
  - Otherwise → assign **all** remaining regs to that bucket; total may fall **below** target.
  - **Empty input (0 registrations):** no assignments, no IDs, but `lottery_run_at` set and
    `status='lottery_run'` (lottery completes).
  - **X and Y may each be 0:** X=0 skips selected (all go to waitlist/not_selected); Y=0 skips
    waitlist; X=Y=0 ⇒ all `not_selected`. Staff-added 1000+ rows are post-lottery and never eligible.
- **`Requirements.md`** §7.4 (`:188-196`), §4 Lottery (`:85-87`), FR-13 (`:376`): state the same.
- **TC-012 (extended)** — replace the unconditional `≥X`/`≥Y` with per-bucket bounds; add empty,
  below-X, between, `X=0`, and `Y=0` cases.

### F4 — walk-in/admit 1000+ scheme (spec; models are Phase 1/10)
- **`ImplementationPlan.md`** data model: add `Event.next_staff_id` PositiveIntegerField(default=1000)
  and `Registration.id_source` choices `lottery`/`staff` (null until ID assigned); `animal_id`
  read-only outside the lottery service and the staff allocate service; `next_animal_id` (lottery)
  considers only IDs 1..999; new `allocate_staff_animal_id(event)` locks the Event row, reads
  `next_staff_id`, assigns it, increments, saves (atomic — no `max()+1` race or deleted-highest
  reuse). `clean()` cross-checks `id_source`↔range (lottery ⇒ 1..999; staff ⇒ ≥1000). Update Phase 10
  row (`:315`) and the Registration block (`:102,131`).
- **`Requirements.md`** §5 (`:115-116`), §4 AnimalID (`:80-84`), §7.4 post-lottery (`:204-209`),
  §7.6 rewrite (`:236-240` — drop the waitlist→selected claim), FR-14 (`:377`), FR-36 (`:405`),
  FR-37 (`:406`): the two post-lottery actions (Add walk-in; Admit existing) both auto-allocate the
  next ≥1000 ID and set `status='selected'`; IDs not counted toward X/Y; no editing numbered rows.
- **`Decisions.md`** 4 (`:29`), 6 (`:42-43`); **`Architecture.md`** §5 (`:130-134`), §7.2
  (`:207-210`), component `clinic` (`:92`): align.
- **TC-044 (revised)** — walk-in add ⇒ `creation_source=staff` + `created_by_user` + next ≥1000 ID +
  `status=selected`; **TC-045 (revised)** — admit an existing row ⇒ next ≥1000 ID + `status=selected`
  + provenance untouched (admitted_by_user/admitted_at); pre-lottery attempt **rejected**; selected/
  waitlisted/checked_in keep their ID; 1000+ IDs excluded from X/Y.

### F5 — provenance + admission fields (spec; Registration is Phase 1)
- **`ImplementationPlan.md`** Registration (`:129`): `creation_source` choices `public`/`staff`
  (default `public`); `created_by_user` FK(`accounts.User`, null=True); `admitted_by_user`
  FK(`accounts.User`, null=True); `admitted_at` DateTimeField(null=True).
- **`Requirements.md`** §5 (`:123`), FR-36 (`:405`); **`TraceabilityMatrix.md`** TC-044 (`:115`):
  align; admit does not overwrite `creation_source`/`created_by_user`.

### F7 — Twilio config drift + fail-closed + smoke order (config + docs)
- **`render.yaml`** (`:30-37`): add `PUBLIC_BASE_URL` (sync:false) and `TWILIO_MESSAGING_SERVICE_SID`
  (sync:false); keep `TWILIO_FROM_NUMBER` (dev fallback).
- **`config/settings/base.py`** (`:128-131`): add `PUBLIC_BASE_URL = env("PUBLIC_BASE_URL",
  default="")` and `TWILIO_MESSAGING_SERVICE_SID = env("TWILIO_MESSAGING_SERVICE_SID", default="")`.
- **`config/settings/prod.py`** (amendment 8): fail closed — if `SMS_BACKEND == "twilio"`, require
  `PUBLIC_BASE_URL` to be a non-empty `https://` URL and `TWILIO_MESSAGING_SERVICE_SID` to be non-empty
  and start with `MG`; else `raise ImproperlyConfigured(...)`.
- **`.env.example`** (`:14-21`): document both new vars (commented), `TWILIO_FROM_NUMBER` as dev-only.
- **TC-057 (amendment 7)** — fix the flawed order introduced by `a8f9bf5`. New sequence on a real US
  handset, **fresh registration per probe send** (respects at-most-once): (1) **HELP first** → confirm
  HELP reply; (2) send result-SMS (reg A) → accepted + arrives; (3) **STOP** → STOP auto-reply; (4)
  send result-SMS (reg B, fresh) → blocked (doesn't arrive); (5) **START** → START reply; (6) send
  result-SMS (reg C, fresh) → delivered. Apply the same corrected order to the Phase 11 deploy row
  (`ImplementationPlan.md:316`) and Verification §7 (`:455-459`).

### F8 — doc/traceability remnants
- **`TraceabilityMatrix.md`** FR-12 row (`:30`): add **TC-049**. FR-22 row (`:43`): two-contract
  summary (GET/status never expires; mutation until check-in/completion).
- **`Architecture.md`** §13.2 (`:295`) + **`Requirements.md`** §13 Decision-2 summary (`:315`): note
  GET never expires.
- **`Requirements.md`** §5 `animal_id` (`:115`): "manually by admin" → "by the lottery, or by staff
  via the 1000+ walk-in/admit sequence".
- **`ImplementationPlan.md`** Export (`:293`): "(login required)" → "(Admin-only, role-gated)".

## New / changed test cases (amendment 9 — keep them focused)
- **TC-058 (new)** — lifecycle forward-only (F2). **TC-059 (new)** — provisioning integration (F1):
  `createsuperuser`→admin; `create_user`→volunteer; contradictory args rejected both ways;
  volunteer-role superuser repaired to admin. **Not** folded into TC-034 (which stays privilege E2E).
- **TC-012** (per-bucket low-demand), **TC-044/045** (walk-in/admit 1000+), **TC-057** (smoke order)
  revised as above. **TC-049 stays auto-lottery only** (before-close guard, expired draft not run,
  noon auto-run); pre-lottery manual rejection lives in **TC-045**.
- Register TC-058/TC-059 in TraceabilityMatrix §3 and map to FR-4 / FR-30.

## Verification
1. `cd /home/dev/cwac && source .venv/bin/activate`.
2. **F1 tests (amendment 10):** `.venv/bin/pytest accounts/tests.py -v` → green (sync+async manager,
  contradictions, `createsuperuser`, `with_perm`, 0002 repair, model/UserAdmin validation).
3. **prod fail-closed (amendment 8):** a focused test (settings override) asserting `prod` raises
  `ImproperlyConfigured` when `SMS_BACKEND=twilio` + missing/malformed `PUBLIC_BASE_URL`/SID.
4. **Migration/model consistency:** `.venv/bin/python manage.py makemigrations --check --dry-run` →
   no changes; **`0002` applies cleanly on the existing dev DB** (it currently has `accounts.0001`).
5. `.venv/bin/python manage.py check` and `check --deploy` (prod settings, audit-only key) → no issues.
6. **Grep sweeps return empty:** `self/admin`, `manually by admin`, export `login required`,
   `is_superuser=False`/`gates on is_staff` (on Admin), `valid until check-in` (FR-22 row), orphan
   TCs, the flawed `STOP … HELP … START` order; and `PUBLIC_BASE_URL`+`TWILIO_MESSAGING_SERVICE_SID`
   present in `render.yaml`/`base.py`/`.env.example`/`prod.py`.
7. `git diff --check` clean.

## Commit / push
Commit as round-7 remediation on top of `a8f9bf5` (still unpushed). **Push only on your go-ahead** —
the audit re-reviews the pushed head, so pushing is what surfaces these fixes.
