# Requirements → Tests Traceability Matrix (V1)

**Status:** Draft for review
**Last updated:** 2026-08-03
**Companion docs:** `Requirements.md` (Appendix A = requirement IDs), `Architecture.md`, `Decisions.md`

Requirement IDs (FR-x / NFR-x) are defined in `Requirements.md` Appendix A. Test case details
are in §2.

---

## 1. Traceability Matrix

| Req ID | Requirement (short) | Test Cases |
|---|---|---|
| **FR-1** | Admin creates event with full configuration (incl. open/close times) — **Admin-only** (Decision 16) | TC-001 |
| **FR-2** | Unique event sign-up URL/slug | TC-002 |
| **FR-3** | Download sign-up URL + QR-code JPG | TC-003 |
| **FR-4** | Lifecycle; signups only during [open_at, close_at) (auto, no manual lock); forward-only `status` + `signup_open` also requires lottery not run | TC-004, TC-058 |
| **FR-34** | After close_at: owners edit/remove only (no add); admin can always add/edit | TC-041 |
| **FR-38** | Per-event applicant cap Z (soft) rejects new signups when full; slight concurrent overshoot ok | TC-047 |
| **FR-39** | Admin can delete an entire event (cascade) behind a confirmation — **Admin-only** (Decision 16) | TC-048 |
| **FR-5** | Public form via event URL, no login | TC-005 |
| **FR-6** | EN/ES language toggle | TC-006 |
| **FR-7** | Owner info (all required) + ≥1 animal submitted | TC-007, TC-008, TC-051 |
| **FR-8** | Per-animal fields (name/species/age required; sex/breed/color optional incl. "Unknown"); no weight | TC-009 |
| **FR-9** | Per-animal services/questions from event config | TC-010 |
| **FR-10** | Max 6 animals enforced on owner additions during open window (edit-form max tracks current count) | TC-008, TC-052 |
| **FR-11** | Confirmation screen (no guaranteed time) | TC-011 |
| **FR-12** | Lottery randomly selects whole registrations (single run, after close; the shared service guards `now > close_at` under the Event-row lock; no double-run under concurrent manual+auto) | TC-012, TC-013, TC-049, TC-050 |
| **FR-13** | X/Y caps **per bucket** (waitlist on the remainder after selected; each may overshoot ≤ **M** = largest eligible reg's animal count in that bucket; if short, the bucket is under-filled; ≤6 normally, more only if staff grew a record past 6 — TC-052) | TC-012 |
| **FR-14** | Lottery AnimalIDs sequential 1..999 to selected + waitlisted; staff walk-in/admit IDs ≥1000 (not counted toward X/Y) | TC-014, TC-015 |
| **FR-15** | Statuses set correctly | TC-014 |
| **FR-40** | Lottery auto-runs at noon (event tz) day-after-close if not run manually (single-run) | TC-049, TC-050 |
| **FR-16** | Signup-confirmation SMS to consenters on register (with edit link) | TC-016 |
| **FR-17** | Fire-and-forget lottery-result SMS to all consenting; selected/waitlisted include AnimalID (`sent`=accepted; 2xx→sent / 4xx→failed / 5xx→unknown; never retried; at-most-one) | TC-017, TC-018, TC-055 |
| **FR-18** | SMS in the language stored on the registration | TC-018, TC-046 |
| **FR-19** | Not-selected consenting courtesy SMS | TC-019 |
| **FR-42** | Signup SMS-consent checkbox (default on) = application consent; toggle via edit link; opted-out = no SMS, status still viewable | TC-054 |
| **FR-43** | Provider-side opt-out (not mirrored): STOP/START/HELP handled by Twilio Advanced Opt-Out on the Messaging Service (no inbound webhook, no `PhoneBlock`); a send to a blocked number is accepted (`sent`) — the async `21610` is unobserved; app-side gate is `sms_opt_out` only; re-consent via START | TC-055, TC-056, TC-057 |
| **FR-20** | Token edit link opens entry, no login | TC-020 |
| **FR-21** | Owner edits; add+remove while open; add disabled after close_at | TC-021, TC-022, TC-023, TC-042 |
| **FR-22** | **Two contracts:** token GET/status **never expires**; mutation (edit/add/remove) until check-in/event-completion (add additionally while open) | TC-024 |
| **FR-41** | Edit-link page shows current result (AnimalID / not-selected / pending) even after edit locks | TC-053 |
| **FR-23** | Lookup by AnimalID or name/phone | TC-025, TC-026 |
| **FR-24** | Volunteer edits owner/animal info | TC-027 |
| **FR-25** | Volunteer adds animals | TC-028 |
| **FR-26** | Volunteer removes animals | TC-029 |
| **FR-27** | Mark checked_in (manual fallback) | TC-030 |
| **FR-28** | Print owner label + pet labels (grouping ~3 animals each) | TC-031 |
| **FR-35** | Printing sets printed_at (attendance) | TC-043 |
| **FR-36** | Staff add a walk-in registration (owner + animals); system assigns next 1000+ ID, `status` → `selected` (post-lottery; not counted toward X/Y) | TC-044 |
| **FR-37** | Staff admit an existing `registered`/`not_selected` row; system assigns next 1000+ ID (unique in event), `status` → `selected`; provenance untouched; post-lottery only | TC-045 |
| **FR-29** | Admin Excel/CSV export, agreed columns (incl. language) — **Admin-only** (Decision 16) | TC-032 |
| **FR-30** | Admin+volunteer login; **Admin-only** = event create/configure/delete + run lottery + export; **both roles** = all clinic operations (Decision 16). Provisioning (Admin=superuser; volunteer-role superuser repaired) | TC-033, TC-034, TC-035, TC-059 |
| **FR-31** | Owner pages no login (token-secured) | TC-005, TC-020 |
| **FR-32** | HTTPS; no public listing | TC-036, TC-038 |
| **FR-33** | EN/ES public form + SMS; chosen language stored (admin UI English-only) | TC-006, TC-018, TC-046 |
| **NFR-1** | Mobile-first/thumb-friendly UI | TC-037 |
| **NFR-2** | PaaS + managed Postgres + HTTPS | TC-038 |
| **NFR-3** | SMS via Twilio; creds from env | TC-039, TC-057 |
| **NFR-4** | Printing via Flutter/3nStar bridge | TC-040 |

---

## 2. Test Case Catalog

Types: **U**nit, **I**ntegration, **E2E** (browser/end-to-end), **M**anual, **D**eploy.

| ID | Type | Scenario & expected result |
|---|---|---|
| TC-001 | E2E | Admin creates an event with all config fields (incl. open/close times) → saved with status `draft`. |
| TC-002 | U | Slug generation yields a unique code; a duplicate is rejected. |
| TC-003 | E2E | Admin downloads sign-up URL + QR JPG → file downloads and the QR decodes to the event URL. |
| TC-004 | I | Submit before `open_at` or after `close_at` → rejected; submit during the window on a **`live`** event → accepted. **A `draft` (or any non-`live`) event rejects signups even within `[open_at, close_at)`** — the `live` stage is required, not just the time window (FR-4). (No manual lock.) |
| TC-005 | E2E | Open the sign-up URL (during the window) while logged out → form renders (no login wall). |
| TC-006 | E2E | Toggle to ES → every public label renders in Spanish; toggle back to EN. |
| TC-007 | I | Submit with a missing required owner field (name/phone/email/address) → blocked with validation errors. |
| TC-008 | I | Submit 7 animals → blocked at 6; submit 6 → accepted. |
| TC-009 | I | Per-animal required/optional fields enforced; no "weight" field present anywhere in the form or model. **Required:** name, species, age. **Optional (blank allowed):** breed, color, and sex — sex choices are M/F/MN/FS/U (Male/Female/Male-Neutered/Female-Spayed/**Unknown**); sex may be blank or "Unknown" because some animals' sex is not known, especially babies (Decision 17). |
| TC-010 | E2E | Event offers only `vaccination`+`vet` → form shows only those service checkboxes + last-vaccinated + medical-concern; hides flea/microchip. |
| TC-011 | E2E | Valid submission → confirmation screen appears and states no guaranteed time. |
| TC-012 | U | **Per-bucket lottery bounds.** With seeded registrations/animal-counts, let **M_s** = the largest animal count among the selected-bucket's eligible regs and **M_w** = the largest among the waitlist bucket's remainder. If enough animals exist to reach a cap: selected sum ∈ [X, X+M_s), waitlist sum ∈ [Y, Y+M_w) — the waitlist is computed on the **remainder after the selected bucket's overshoot**. If not enough animals exist, that bucket takes all remaining and the total is **below** the cap. Cases: (a) empty event (0 regs) → no assignments, lottery still completes; (b) total animals < X → all selected (selected < X, waitlist empty); (c) total between X and ~X+Y → selected fills to X (overshoot), waitlist gets the remainder; (d) **X=0** → selected bucket skipped; (e) **Y=0** → waitlist bucket skipped. Include a staff-grown >6-animal reg (TC-052); assert the bound holds with M = that count (typical all-owner rows M=6 ⇒ < X+6 / < Y+6). |
| TC-013 | U | Lottery selection is random (not signup order): shuffle is invoked and selection changes across runs (distribution check over many seeded runs). |
| TC-014 | I | After lottery, every selected+waitlisted registration has a unique AnimalID and the correct status; `not_selected` have no AnimalID. |
| TC-015 | U | AnimalIDs are sequential starting at 1 (1..N), contiguous, max 999, unique within the event. |
| TC-016 | I | On signup with consent (Twilio mocked) → a confirmation SMS is sent to the consenting registrant containing an edit link. |
| TC-017 | I | On lottery (Twilio mocked) → a result SMS is sent to **every consenting** registrant; selected/waitlisted bodies contain the AnimalID + edit link; not-selected bodies are the courtesy text; wording differs by outcome. |
| TC-018 | I | A registration whose owner chose ES → both SMS bodies rendered in Spanish; the edit link appears in SMS #1 (and in SMS #2 for selected/waitlisted only); links resolve to the entry. |
| TC-019 | I | A consenting not-selected registrant receives exactly one courtesy lottery SMS (no AnimalID). |
| TC-020 | E2E | Open a valid edit-token link while logged out → entry loads (no login). |
| TC-021 | E2E | Owner edits an owner field + saves → change persists on reload. |
| TC-022 | E2E | While the window is **open**, the owner can **add** an animal via the edit link + save → it persists. |
| TC-023 | E2E | Owner removes an animal + saves → animal is gone; count decreased; persists. |
| TC-024 | E2E | Open the edit link after the registration is checked-in (or after the event completes): the page **still renders** (status banner + a "locked" notice — FR-41), but **POST/mutation is rejected** (add/edit/remove disabled server-side). Assert both halves: GET readable, POST blocked. |
| TC-025 | E2E | Volunteer enters a valid AnimalID → matching registration+animals load. |
| TC-026 | E2E | Search by partial name or phone → matching registrations returned (fuzzy). |
| TC-027 | E2E | Volunteer edits an owner/animal field + saves → persists. |
| TC-028 | E2E | Volunteer adds an animal + saves → it appears in the record and in the print set. |
| TC-029 | E2E | Volunteer removes an animal + saves → gone. |
| TC-030 | E2E | Volunteer marks checked-in (manual) → status becomes `checked_in` and shows in the admin list. |
| TC-031 | I | Volunteer triggers print → print station receives a label payload = 1 owner label + pet labels that group the record's animals (~3 each). |
| TC-032 | I | Admin exports an event → CSV/XLSX downloads with the agreed columns and every registration+animal (incl. status, AnimalID, language, printed). |
| TC-033 | M | Admin login with correct creds → access; wrong creds → denied. |
| TC-034 | E2E | **Privilege contract (Decision 16):** a volunteer can perform every clinic operation (lookup, edit, add, remove, check-in, print, manual entry, assign AnimalID) but is **denied** each Admin-only capability — create/configure/delete event, run lottery, export — and cannot enter the Django admin (`is_staff=False`). An admin can do all of the above. Assert each Admin-only action is rejected for the volunteer role. |
| TC-035 | E2E | Unauthenticated request to any admin/volunteer page → redirected to login. |
| TC-036 | E2E | A direct URL to another event's data without selecting it → denied/redirect (no cross-event leak). |
| TC-037 | M | Public form is usable one-handed on a phone: tap-target sizes, font sizes, no horizontal scroll. |
| TC-038 | D | App deploys to Render; Postgres provisioned; site reachable over HTTPS. |
| TC-039 | I | SMS send uses Twilio credentials from the environment; none are present in source. |
| TC-040 | M | Print station (Flutter app) prints correct owner + grouped pet labels on the 3nStar PPT305BT. |
| TC-041 | I | After `close_at`: new signups rejected; an owner's add-animal is blocked (edit/remove still work); the admin can still add/edit. |
| TC-042 | E2E | After `close_at`, the owner edit page shows no working add-animal control (remove/edit still function). |
| TC-043 | I | Printing labels for a registration sets `printed_at`; the registration then reports as attended/printed in admin + export. |
| TC-044 | I | **Walk-in add (staff, post-lottery).** Staff (admin or volunteer) add a walk-in registration (owner + animals) → saved with `creation_source=staff`, `created_by_user`=the actor; the 6-animal cap is not enforced; lookup-able by name/phone. The system **auto-assigns the next 1000+ ID** (`assign_next_walkin_id`) and sets `status='selected'` atomically — the owner's status banner then shows the ID. **Rejected before the lottery has run.** The 1000+ ID is **not counted toward X/Y**. |
| TC-045 | I | **Admit (staff, post-lottery).** Staff admit an existing `registered`/`not_selected` row → the system auto-assigns the next 1000+ ID (unique in event) and atomically sets `status='selected'`; provenance (`creation_source`/`created_by_user`) is **untouched** (`admitted_by_user`/`admitted_at` set); a duplicate ID is rejected; the entry is lookup-able by that ID; export reflects the admitted status. A `selected`/`waitlisted`/`checked_in` row **keeps its ID and status** (staff never edit an ID on a numbered row). **Pre-lottery walk-in/admit is rejected.** 1000+ IDs are not counted toward X/Y. At the model layer, `assign_next_walkin_id` locks the **Event then the Registration** (Event-first order) and **rejects an already-numbered row or a cross-event call**, so a duplicate/concurrent admit cannot overwrite an assigned ID or consume another event's counter. The `1..999` (lottery) / `>=1000` (staff) range↔source invariant is **DB-enforced** by a `CheckConstraint` on `Registration` (a backstop to `clean()`, which `save()`/`create()`/`update()` bypass). |
| TC-046 | I | The owner's chosen language (EN/ES) is persisted on the registration and is the language used for both SMS touchpoints. |
| TC-047 | I | **Deterministic:** at `count == Z`, a new signup is rejected with an EN/ES "registration full" message; at `Z-1`, a single new signup is accepted; an existing owner at the event can still add an animal regardless of Z. **Soft-cap race (residual/load, not a unit assertion):** Z is a soft cap — the check + insert are not serialized, so concurrent signups at `Z-1` may overshoot by up to the number of requests in flight at the boundary. There is no hard ≤Z invariant; the overshoot is observed/verified under load, not asserted as a deterministic bound (R-10/Decision 12). |
| TC-048 | I | Admin deletes an event → all of its registrations + animals are gone; a confirmation was shown first; unrelated events are untouched. |
| TC-049 | I | `run_due_lotteries` runs a **`live`** event whose noon deadline (event tz, day after `close_at`) has passed but that isn't yet run; an event not yet at its deadline is left untouched; and an **expired `draft`** (or any non-`live` event) past its deadline is **not** run; and a **direct call to `run_lottery` on a `live` event before `close_at` raises `LotteryNotEligible`** (FR-12 — the shared service guards `now > close_at` under the Event-row lock, not just the admin action). (TC requires Postgres for the row lock.) |
| TC-050 | I | A manual "Run lottery" and the cron auto-run fired concurrently on the same `live` event → exactly one run wins (statuses/IDs set once); each registrant gets **at most one** result SMS (fire-and-forget: a crash can mean zero, never two). Requires Postgres. |
| TC-051 | I | Submitting a registration with zero animals → blocked (≥1 animal required); submit with 1 → accepted. |
| TC-052 | I | An owner record a volunteer grew to 8 animals can still be edited/removed by the owner (max tracks current count); an owner at 6 cannot add a 7th. |
| TC-053 | I | Open the edit link after the lottery: selected/waitlisted → shows their AnimalID; not-selected → shows a "not selected" notice; before the lottery → "pending". Status **still renders after the edit locks** (check-in / event complete) — GET shows the banner + "locked"; only mutation is blocked. |
| TC-054 | I | Signup form shows an SMS-consent checkbox checked by default. Submit with it unchecked → `sms_opt_out=True`, no SMS sent (signup or result); status still visible on the edit-link page. Leave checked (or re-check via the edit link) → SMS sends normally. |
| TC-055 | I | **Fire-and-forget result SMS:** a consenting registrant's result SMS is sent **at most once** — atomic `result_sms_state null→sending` claim (committed before the POST), then 2xx→`sent` (accepted), a sync 4xx→`failed`, a *caught* 5xx/timeout/connection-loss/no-response→`unknown`. **Distinct crash windows (neither is `unknown` nor ever resent):** a worker killed *before* the `null→sending` claim commits leaves `null` (zero attempts); killed *after* leaves a persistent `sending`. **Never retried** (no double-text); `result_sms_sent_at` set only on `sent`. |
| TC-056 | I | **Provider-side opt-out (not mirrored):** STOP/START/HELP are handled by Twilio Advanced Opt-Out on the Messaging Service; the app has **no** inbound webhook and **no** `PhoneBlock`. A send to a STOP'd number is still **accepted** (`sent`); the async `21610` is unobserved (correct — they opted out). Texting START (to Twilio) lets later sends deliver again. Application consent (`sms_opt_out`, FR-42) is independent — one of two duplicate-phone registrations can decline while the other still receives SMS. |
| TC-057 | D | **SMS deploy smoke — sender registration + Advanced Opt-Out (FR-43/NFR-3):** against the production Messaging Service whose US sender is registered (A2P 10DLC Brand+Campaign, or verified toll-free), verify on a **real US handset** before declaring SMS deployable — using a **fresh registration for each probe send** (the app sends at most one result-SMS per registration): (1) **HELP first** → confirm the configured HELP auto-reply (an opted-out number may not receive the HELP reply, so test HELP *before* STOP); (2) send one live result-SMS (reg A) → accepted (2xx) and arrives (catches unregistered-sender blocking, which surfaces only against real US carriers); (3) text **STOP** → confirm the configured STOP auto-reply, then send another result-SMS (reg B, fresh) and assert it is **blocked** (does not arrive — the provider honored the opt-out); (4) text **START** → confirm the configured START reply, then send another result-SMS (reg C, fresh) and assert **delivery is restored**. SMS is not deployable until all pass. |
| TC-058 | I | **Event lifecycle is forward-only (FR-4).** A backward move (`completed → live`) and a skip move (`draft → active`) via `Event.transition()` are rejected (`InvalidTransition`); valid one-step forward moves succeed. The raw `status` field is read-only in the admin (`editable=False`). And `signup_open()` is **False** once `lottery_run_at` is set, even if `status` is forced back to `live`. (Requires Postgres for the row lock.) |
| TC-059 | I | **Provisioning integration (FR-30).** `createsuperuser` yields a full Admin (`is_staff` + `is_superuser` + `role=admin`); `create_user`/`acreate_user` yield a Volunteer and **reject** any privileged flag or `role=admin`; `create_superuser`/`acreate_superuser` **reject** `is_staff`/`is_superuser=False` or `role=volunteer`; the 0002 data migration repairs an existing volunteer-role superuser to `role=admin`; model + admin-form validation reject an inconsistent combination on edit. |

---

## 3. Notes

- **Coverage:** every FR-1..FR-43 and NFR-1..NFR-4 has ≥1 test case (see §1).
- **Two-SMS flow:** signup confirmation (TC-016) and lottery result (TC-017/018/019) are tested
  separately; Twilio is mocked in integration tests.
- **Window/close semantics:** TC-004 (window boundary) and TC-041/TC-042 (after close: signups
  rejected, owner add disabled, edit/remove ok, admin can add) cover FR-4/FR-21/FR-34; **TC-058**
  covers the forward-only lifecycle guard (status read-only; `signup_open` also requires lottery not run).
- **Random selection:** TC-013 verifies the lottery selects in random order, not signup order.
- **Language:** TC-046 verifies the chosen language is stored and drives SMS (FR-18/FR-33).
- **Attendance:** TC-043 verifies printing records attendance (FR-35).
- **Walk-in add & admit (both roles, post-lottery):** TC-044 (walk-in add) and TC-045 (admit an
  existing `registered`/`not_selected` row) cover FR-36/FR-37; both auto-assign the next **1000+ ID**
  (`assign_next_walkin_id`; not counted toward X/Y) and set `status='selected'`, post-lottery only;
  available to admin **and** volunteer.
- **Privileges (Decision 16):** TC-034 verifies the differentiated contract — volunteer can do all
  clinic operations but is denied each Admin-only capability (event create/configure/delete, run
  lottery, export; no Django-admin access). **TC-059** verifies provisioning — an Admin is a superuser,
  and the manager/migration reject and repair a volunteer-role superuser.
- **Applicant cap / deletion / auto-lottery:** TC-047 (cap Z), TC-048 (event deletion), and
  TC-049/TC-050 (noon auto-run + no concurrent double-run) cover FR-38..FR-40.
- **Formset invariant:** TC-051 (≥1 animal required) and TC-052 (over-cap owner edit) cover
  FR-7/FR-10/FR-21.
- **Status visibility & SMS consent:** TC-053 (edit-link shows result) and TC-054 (signup consent
  checkbox + opt-out) cover FR-41/FR-42.
- **SMS delivery & provider opt-out:** TC-055 (fire-and-forget: one send, 2xx→sent (accepted) /
  4xx→failed / 5xx→unknown, never retried; at-most-one) and TC-056 (STOP/START handled provider-side
  by Advanced Opt-Out — not mirrored; async `21610` unobserved; app-consent independent) cover FR-17
  and FR-43. TC-057 is the live SMS deploy smoke: registered US sender + verifies Advanced Opt-Out is
  actually enabled (**HELP before STOP**, then STOP→blocked, START→restored on a real handset, a fresh
  registration per probe send), mapped to FR-43/NFR-3.
- **Labels:** TC-031/TC-040 verify grouped pet labels (~3/label), not one-per-animal.
- **Test automation targets:** unit (TC-002, TC-009, TC-012, TC-013, TC-015) and integration
  (TC-004, TC-007, TC-008, TC-014, TC-016, TC-017, TC-018, TC-019, TC-031, TC-032, TC-039, TC-041,
  TC-043, TC-044, TC-045, TC-046, TC-047, TC-048, TC-049, TC-050, TC-051, TC-052, TC-053, TC-054,
  TC-055, TC-056, TC-058, TC-059) should be automated. The locking tests (TC-047, TC-049, TC-050,
  TC-058) require PostgreSQL. The row-lock guarantees in `assign_next_walkin_id` (unique monotonic
  staff allocation; duplicate/concurrent-admit serialization) and `Event.transition()` (locked
  lifecycle change) are likewise only provable on PostgreSQL — the SQLite suite verifies their
  *logic* serially only. This concurrency coverage is a **known, business-accepted testing gap**
  (Decision 18), to be closed when a PostgreSQL CI job is added. E2E (browser) and manual/deploy
  tests (incl. TC-057) are run before each release.
