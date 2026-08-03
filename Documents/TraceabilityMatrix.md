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
| **FR-1** | Admin creates event with full configuration (incl. open/close times) | TC-001 |
| **FR-2** | Unique event sign-up URL/slug | TC-002 |
| **FR-3** | Download sign-up URL + QR-code JPG | TC-003 |
| **FR-4** | Lifecycle; signups only during [open_at, close_at) (auto, no manual lock) | TC-004 |
| **FR-34** | After close_at: owners edit/remove only (no add); admin can always add/edit | TC-041 |
| **FR-38** | Per-event applicant cap Z (soft) rejects new signups when full; slight concurrent overshoot ok | TC-047 |
| **FR-39** | Admin can delete an entire event (cascade) behind a confirmation | TC-048 |
| **FR-5** | Public form via event URL, no login | TC-005 |
| **FR-6** | EN/ES language toggle | TC-006 |
| **FR-7** | Owner info (all required) + ≥1 animal submitted | TC-007, TC-008, TC-051 |
| **FR-8** | Per-animal fields; no weight | TC-009 |
| **FR-9** | Per-animal services/questions from event config | TC-010 |
| **FR-10** | Max 6 animals enforced on owner additions during open window (edit-form max tracks current count) | TC-008, TC-052 |
| **FR-11** | Confirmation screen (no guaranteed time) | TC-011 |
| **FR-12** | Lottery randomly selects whole registrations (single run, after close; no double-run under concurrent manual+auto) | TC-012, TC-013, TC-050 |
| **FR-13** | X/Y caps (may overshoot ≤ max animals/person) | TC-012 |
| **FR-14** | AnimalID sequential from 1 (max 999) to selected + waitlisted | TC-014, TC-015 |
| **FR-15** | Statuses set correctly | TC-014 |
| **FR-40** | Lottery auto-runs at noon (event tz) day-after-close if not run manually (single-run) | TC-049, TC-050 |
| **FR-16** | Signup-confirmation SMS to consenters on register (with edit link) | TC-016 |
| **FR-17** | At-most-once/best-effort lottery-result SMS to all consenting; selected/waitlisted include AnimalID (5xx→unknown; atomic initial claim; reconcile-gated retry) | TC-017, TC-018, TC-057, TC-062, TC-065, TC-069, TC-070, TC-071, TC-072, TC-074 |
| **FR-18** | SMS in the language stored on the registration | TC-018, TC-046 |
| **FR-19** | Not-selected consenting courtesy SMS | TC-019 |
| **FR-42** | Signup SMS-consent checkbox (default on) = application consent; toggle via edit link; opted-out = no SMS, status still viewable (cannot clear a provider block — FR-43) | TC-054, TC-060 |
| **FR-43** | Two-dimension opt-out + delivery reconciliation: app consent (FR-42, per-reg) vs phone-level provider block (`sms.PhoneBlock`). Send needs the reg's own consent clear AND no block. `OptOutType` STOP/START/HELP (uppercase) inbound webhook is the **sole writer** of `PhoneBlock`; per-message delivery-status webhook (token-keyed) reconciles `SmsAttempt` only (no `PhoneBlock` write); 21610 = failed_permanent, not a block; START never grants app consent; re-consent via START; URLs via `PUBLIC_BASE_URL` | TC-055, TC-056, TC-058, TC-059, TC-060, TC-061, TC-063, TC-064, TC-065, TC-066, TC-067, TC-068, TC-069, TC-070, TC-071, TC-072, TC-073, TC-074 |
| **FR-20** | Token edit link opens entry, no login | TC-020 |
| **FR-21** | Owner edits; add+remove while open; add disabled after close_at | TC-022, TC-023, TC-042 |
| **FR-22** | Edit-link valid until check-in / event completion | TC-024 |
| **FR-41** | Edit-link page shows current result (AnimalID / not-selected / pending) even after edit locks | TC-053 |
| **FR-23** | Lookup by AnimalID or name/phone | TC-025, TC-026 |
| **FR-24** | Volunteer edits owner/animal info | TC-027 |
| **FR-25** | Volunteer adds animals | TC-028 |
| **FR-26** | Volunteer removes animals | TC-029 |
| **FR-27** | Mark checked_in (manual fallback) | TC-030 |
| **FR-28** | Print owner label + pet labels (grouping ~3 animals each) | TC-031 |
| **FR-35** | Printing sets printed_at (attendance) | TC-043 |
| **FR-36** | Admin manually creates a registration (owner + animals) | TC-044 |
| **FR-37** | Admin assigns/edits an AnimalID, unique within event | TC-045 |
| **FR-29** | Admin Excel/CSV export, agreed columns (incl. language) | TC-032 |
| **FR-30** | Admin+volunteer login, same privileges | TC-033, TC-034, TC-035 |
| **FR-31** | Owner pages no login (token-secured) | TC-005, TC-020 |
| **FR-32** | HTTPS; no public listing | TC-036, TC-038 |
| **FR-33** | EN/ES public form + SMS; chosen language stored (admin UI English-only) | TC-006, TC-018, TC-046 |
| **NFR-1** | Mobile-first/thumb-friendly UI | TC-037 |
| **NFR-2** | PaaS + managed Postgres + HTTPS | TC-038 |
| **NFR-3** | SMS via Twilio; creds from env | TC-039 |
| **NFR-4** | Printing via Flutter/3nStar bridge | TC-040 |

---

## 2. Test Case Catalog

Types: **U**nit, **I**ntegration, **E2E** (browser/end-to-end), **M**anual, **D**eploy.

| ID | Type | Scenario & expected result |
|---|---|---|
| TC-001 | E2E | Admin creates an event with all config fields (incl. open/close times) → saved with status `draft`. |
| TC-002 | U | Slug generation yields a unique code; a duplicate is rejected. |
| TC-003 | E2E | Admin downloads sign-up URL + QR JPG → file downloads and the QR decodes to the event URL. |
| TC-004 | I | Submit before `open_at` or after `close_at` → rejected; submit during the window → accepted. (No manual lock.) |
| TC-005 | E2E | Open the sign-up URL (during the window) while logged out → form renders (no login wall). |
| TC-006 | E2E | Toggle to ES → every public label renders in Spanish; toggle back to EN. |
| TC-007 | I | Submit with a missing required owner field (name/phone/email/address) → blocked with validation errors. |
| TC-008 | I | Submit 7 animals → blocked at 6; submit 6 → accepted. |
| TC-009 | I | Per-animal required fields enforced; no "weight" field present anywhere in the form or model. |
| TC-010 | E2E | Event offers only `vaccination`+`vet` → form shows only those service checkboxes + last-vaccinated + medical-concern; hides flea/microchip. |
| TC-011 | E2E | Valid submission → confirmation screen appears and states no guaranteed time. |
| TC-012 | U | With seeded registrations/animal-counts, lottery selects whole people; selected animal sum ≥ X and < X + max-per-person; waitlist sum ≥ Y and < Y + max-per-person. |
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
| TC-024 | E2E | Open the edit link after the registration is checked-in (or after the event completes) → blocked with a message. |
| TC-025 | E2E | Volunteer enters a valid AnimalID → matching registration+animals load. |
| TC-026 | E2E | Search by partial name or phone → matching registrations returned (fuzzy). |
| TC-027 | E2E | Volunteer edits an owner/animal field + saves → persists. |
| TC-028 | E2E | Volunteer adds an animal + saves → it appears in the record and in the print set. |
| TC-029 | E2E | Volunteer removes an animal + saves → gone. |
| TC-030 | E2E | Volunteer marks checked-in (manual) → status becomes `checked_in` and shows in the admin list. |
| TC-031 | I | Volunteer triggers print → print station receives a label payload = 1 owner label + pet labels that group the record's animals (~3 each). |
| TC-032 | I | Admin exports an event → CSV/XLSX downloads with the agreed columns and every registration+animal (incl. status, AnimalID, language, printed). |
| TC-033 | M | Admin login with correct creds → access; wrong creds → denied. |
| TC-034 | E2E | Volunteer login → can edit/export the same as admin (same privileges). |
| TC-035 | E2E | Unauthenticated request to any admin/volunteer page → redirected to login. |
| TC-036 | E2E | A direct URL to another event's data without selecting it → denied/redirect (no cross-event leak). |
| TC-037 | M | Public form is usable one-handed on a phone: tap-target sizes, font sizes, no horizontal scroll. |
| TC-038 | D | App deploys to Render; Postgres provisioned; site reachable over HTTPS. |
| TC-039 | I | SMS send uses Twilio credentials from the environment; none are present in source. |
| TC-040 | M | Print station (Flutter app) prints correct owner + grouped pet labels on the 3nStar PPT305BT. |
| TC-041 | I | After `close_at`: new signups rejected; an owner's add-animal is blocked (edit/remove still work); the admin can still add/edit. |
| TC-042 | E2E | After `close_at`, the owner edit page shows no working add-animal control (remove/edit still function). |
| TC-043 | I | Printing labels for a registration sets `printed_at`; the registration then reports as attended/printed in admin + export. |
| TC-044 | I | Admin creates a registration manually (owner + animals) → saved with `created_by`=admin; lookup-able by name/phone; the 6-animal cap is not enforced. |
| TC-045 | I | Admin assigns an AnimalID to a registration → accepted if unique within the event (1..999); a duplicate is rejected; the entry is then lookup-able by that AnimalID. |
| TC-046 | I | The owner's chosen language (EN/ES) is persisted on the registration and is the language used for both SMS touchpoints. |
| TC-047 | I | **Deterministic:** at `count == Z`, a new signup is rejected with an EN/ES "registration full" message; at `Z-1`, a single new signup is accepted; an existing owner at the event can still add an animal regardless of Z. **Soft-cap race (residual/load, not a unit assertion):** Z is a soft cap — the check + insert are not serialized, so concurrent signups at `Z-1` may overshoot by up to the number of requests in flight at the boundary. There is no hard ≤Z invariant; the overshoot is observed/verified under load, not asserted as a deterministic bound (R-10/Decision 12). |
| TC-048 | I | Admin deletes an event → all of its registrations + animals are gone; a confirmation was shown first; unrelated events are untouched. |
| TC-049 | I | `run_due_lotteries` runs an event whose noon deadline (event tz, day after `close_at`) has passed but that isn't yet run; an event not yet at its deadline is left untouched. |
| TC-050 | I | A manual "Run lottery" and the cron auto-run fired concurrently on the same event → exactly one run wins (statuses/IDs set once); each registrant gets exactly one result SMS (idempotent). |
| TC-051 | I | Submitting a registration with zero animals → blocked (≥1 animal required); submit with 1 → accepted. |
| TC-052 | I | An owner record a volunteer grew to 8 animals can still be edited/removed by the owner (max tracks current count); an owner at 6 cannot add a 7th. |
| TC-053 | I | Open the edit link after the lottery: selected/waitlisted → shows their AnimalID; not-selected → shows a "not selected" notice; before the lottery → "pending". Status still shows after the edit locks (check-in / event complete). |
| TC-054 | I | Signup form shows an SMS-consent checkbox checked by default. Submit with it unchecked → `sms_opt_out=True`, no SMS sent (signup or result); status still visible on the edit-link page. Leave checked (or re-check via the edit link) → SMS sends normally. |
| TC-055 | I | An owner texts STOP → the inbound webhook with `OptOutType=STOP` (uppercase; also exercises `HELP`→no-op and lowercase→normalized) upserts a phone-level `sms.PhoneBlock` (never touches `sms_opt_out`); the next result-SMS send to that number is skipped. They text START (`OptOutType=START`) → the `PhoneBlock` is deleted; sends to a still-consenting registration resume. |
| TC-056 | I | A synchronous `21610` on an outbound send → the attempt is marked `failed_permanent`/`retryable=False` and logged (**not** a `PhoneBlock` write — only the inbound STOP webhook creates a block; any block on that number came from a prior STOP). A website toggle-on (clearing `sms_opt_out`) alone does **not** resume delivery while a `PhoneBlock` exists — START is required; START clears the block but does not change application consent. (Real production path verified by TC-063; the mocked synchronous `21610` here is the fast-path hint only.) |
| TC-057 | I | Result-SMS delivery is at-most-once, classified by what is **proven** (RFC 9110 §9.2.2): (a) 2xx+SID → `sent`; (b) a 4xx documented as pre-acceptance (invalid number) → `failed_permanent`, never retried; (c) **any 5xx — including one emitted *after* Twilio created the message — / timeout / connection loss / crashed worker** → `unknown`, **never** auto-retried on a timer (the message may exist). `retry_sms` re-sends only an `unknown` a callback later confirmed reached a terminal-transient failure (TC-069); a confirmed `sent` is never re-sent. No double-texts. |
| TC-058 | I | The `/sms/inbound/` and `/sms/status/<token>/` webhooks reject a POST with a missing/invalid `X-Twilio-Signature` (no state change); a properly signed `OptOutType` of `STOP`/`START`/`HELP` (and status callback) with the **real uppercase casing** is accepted. |
| TC-059 | I | Two registrations share one phone; one owner texts STOP → a single phone-level `PhoneBlock` is created; a later result SMS to that number is skipped for **both** registrations (the block is keyed by phone, not registration — no contradictory consent), including a registration created after the STOP. |
| TC-060 | I | Application consent is independent of the provider block: a registration whose owner unchecked the website box (`sms_opt_out=True`) stays opted out after a START (START deleted the `PhoneBlock` but left `sms_opt_out`); a send is still skipped. Conversely, clearing `sms_opt_out` via the toggle while a `PhoneBlock` exists still skips the send. |
| TC-061 | I | A registration created **after** an earlier STOP on its phone is blocked at send time — the `PhoneBlock` is durable and phone-level (not carried by any single registration), so a brand-new row inherits the existing block. |
| TC-062 | I | `retry_sms` (scoped to `purpose='result'`) is reconcile-gated: it re-sends only an `unknown` `SmsAttempt` whose callback set a terminal `provider_status` with `retryable=True`, atomically claiming the source (`retry_claimed_at` null→now, one consumer) and creating a fresh child attempt (`retry_of=source`, new token), respecting the per-(registration,purpose) attempt cap; it never selects `sent`/`failed_permanent`, an `unknown` with `retryable` falsy/null, or one with no reconciling callback. After a restart the selection/cap are unchanged (state in `SmsAttempt` rows, not `updated_at`). |
| TC-063 | D | Deploy smoke: with the Messaging Service provisioned (sender pool + Advanced Opt-Out enabled) and the **inbound** STOP/START webhook pointed at the site (the status callback is per-message), a live STOP → `/sms/inbound/` creates a `PhoneBlock`, a subsequent send to that number is skipped, and a live START deletes it and resumes — verifying the real Twilio path (not a mocked `21610`). |
| TC-064 | I | The `/sms/status/<token>/` callback (signature-validated) reconciles the `SmsAttempt` **by `callback_token`** (even when `message_sid` is null), sets `message_sid` from `MessageSid` if missing, advances `provider_status` **monotonically**, and records `provider_error_code`/`retryable`; a callback carrying `21610` marks the attempt `failed_permanent`/`retryable=False` — it does **not** write `PhoneBlock` (only inbound STOP does). |
| TC-065 | I | A send returns **5xx after Twilio already created the message** → `SmsAttempt.state='unknown'` (not retried); a later delivery callback reports `delivered` → the registration rolls to `sent`, and **no** retry/re-send occurs (no duplicate). |
| TC-066 | I | A delivery-status callback arrives **before** the send handler stored its 2xx/SID → it still matches the attempt by `callback_token` and is applied (no lost update); the subsequent 2xx handler does not clobber the reconciled state. |
| TC-067 | I | Out-of-order callbacks: a terminal `failed`/`undelivered`/`delivered` already set, a later `queued`/`sent` callback is **ignored** (monotonic precedence) — a stale callback cannot resurrect or clobber a terminal provider status. |
| TC-068 | I | A **duplicate** callback is applied idempotently (no double state change); a callback whose `callback_token` matches **no** `SmsAttempt` returns HTTP 200 and is logged/alerted (not durably stored in V1 — an operational signal, not a reconciliation inbox) — no crash, no state corruption. |
| TC-069 | I | Reconcile-gated retry contrast: an `unknown` whose callback later shows terminal-transient `undelivered`/`failed` (non-permanent) → `retry_sms` re-sends (fresh attempt, new token); an `unknown` with **no** callback ever → never re-sent, flagged for manual review (at-most-once preserved). |
| TC-070 | I | **Atomic initial-send claim:** two notification workers race to send the same registration's result SMS → exactly one creates the initial `SmsAttempt` (unique `(registration, purpose) WHERE is_initial`); the other hits `IntegrityError` and skips → exactly one result SMS (no double-send). |
| TC-071 | I | **One-consumer retry claim:** two `retry_sms` workers select the same reconciled-failed attempt → exactly one atomically sets `retry_claimed_at` and creates the retry child; the other sees it claimed and skips → one retry, no duplicate. |
| TC-072 | I | **Retryability persists:** after a callback sets `provider_error_code`/`retryable`, a `retry_sms` restart selects only `retryable=True` terminal attempts and never `retryable=False` (e.g. `21610`/invalid-number); the classification survives the restart (durable fields). |
| TC-073 | I | **STOP → START → delayed 21610:** STOP creates `PhoneBlock`; START deletes it; a later (replayed/delayed) delivery callback carrying `21610` for a pre-START attempt → the attempt is marked `failed_permanent`/`retryable=False` and logged, but the number is **not** re-blocked (callbacks don't write `PhoneBlock`). |
| TC-074 | I | **Command-path URLs:** a result send and a `retry_sms` run from a cron command (no request) build the edit link and the per-message `StatusCallback` URL from `PUBLIC_BASE_URL` via `absolute_url()` — both resolve to the canonical HTTPS origin (no `None`/relative URL). |

---

## 3. Notes

- **Coverage:** every FR-1..FR-43 and NFR-1..NFR-4 has ≥1 test case (see §1).
- **Two-SMS flow:** signup confirmation (TC-016) and lottery result (TC-017/018/019) are tested
  separately; Twilio is mocked in integration tests.
- **Window/close semantics:** TC-004 (window boundary) and TC-041/TC-042 (after close: signups
  rejected, owner add disabled, edit/remove ok, admin can add) cover FR-4/FR-21/FR-34.
- **Random selection:** TC-013 verifies the lottery selects in random order, not signup order.
- **Language:** TC-046 verifies the chosen language is stored and drives SMS (FR-18/FR-33).
- **Attendance:** TC-043 verifies printing records attendance (FR-35).
- **Admin manual ops:** TC-044 (create entry) and TC-045 (assign AnimalID) cover the post-lottery
  edge-case handling in FR-36/FR-37.
- **Applicant cap / deletion / auto-lottery:** TC-047 (cap Z), TC-048 (event deletion), and
  TC-049/TC-050 (noon auto-run + no concurrent double-run) cover FR-38..FR-40.
- **Formset invariant:** TC-051 (≥1 animal required) and TC-052 (over-cap owner edit) cover
  FR-7/FR-10/FR-21.
- **Status visibility & SMS consent:** TC-053 (edit-link shows result) and TC-054 (signup consent
  checkbox + opt-out) cover FR-41/FR-42.
- **SMS delivery & provider opt-out:** TC-055 (STOP → `PhoneBlock`, uppercase `OptOutType` + HELP),
  TC-056 (`21610`/START), TC-057 (at-most-once: 5xx→unknown incl. after-creation), TC-058 (webhook
  signature rejection, real casing), TC-059 (duplicate-phone STOP), TC-060 (app consent independent
  of provider block), TC-061 (new registration after STOP), TC-062 (reconcile-gated `retry_sms`),
  TC-063 (deploy smoke on the real Messaging Service), TC-064 (token-keyed delivery callback),
  TC-065 (5xx after creation → unknown, no dup), TC-066 (callback before response), TC-067
  (out-of-order callbacks monotonic), TC-068 (duplicate/unmatched callback), TC-069 (reconcile-gated
  vs no-callback unknown), TC-070 (atomic initial-send claim), TC-071 (one-consumer retry claim),
  TC-072 (retryability persists across restart), TC-073 (delayed 21610 can't undo START), and TC-074
  (command-path URLs via `PUBLIC_BASE_URL`) cover FR-43 and the at-most-once/best-effort delivery
  model (FR-17).
- **Labels:** TC-031/TC-040 verify grouped pet labels (~3/label), not one-per-animal.
- **Test automation targets:** unit (TC-002, TC-009, TC-012, TC-013, TC-015) and integration
  (TC-004, TC-007, TC-008, TC-014, TC-016, TC-017, TC-018, TC-019, TC-031, TC-032, TC-039, TC-041,
  TC-043, TC-044, TC-045, TC-046, TC-047, TC-048, TC-049, TC-050, TC-051, TC-052, TC-053,
  TC-054, TC-055, TC-056, TC-057, TC-058, TC-059, TC-060, TC-061, TC-062, TC-064, TC-065, TC-066,
  TC-067, TC-068, TC-069, TC-070, TC-071, TC-072, TC-073, TC-074) should be automated. E2E (browser)
  and manual/deploy tests (incl. TC-063) are run before each release.
