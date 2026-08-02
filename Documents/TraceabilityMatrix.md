# Requirements → Tests Traceability Matrix (V1)

**Status:** Draft for review
**Last updated:** 2026-08-02
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
| **FR-5** | Public form via event URL, no login | TC-005 |
| **FR-6** | EN/ES language toggle | TC-006 |
| **FR-7** | Owner info (all required) + animals submitted | TC-007, TC-008 |
| **FR-8** | Per-animal fields; no weight | TC-009 |
| **FR-9** | Per-animal services/questions from event config | TC-010 |
| **FR-10** | Max 6 animals enforced during open window | TC-008 |
| **FR-11** | Confirmation screen (no guaranteed time) | TC-011 |
| **FR-12** | Lottery randomly selects whole registrations (single run, after close) | TC-012, TC-013 |
| **FR-13** | X/Y caps (may overshoot ≤ max animals/person) | TC-012 |
| **FR-14** | AnimalID sequential from 1 (max 999) to selected + waitlisted | TC-014, TC-015 |
| **FR-15** | Statuses set correctly | TC-014 |
| **FR-16** | Signup-confirmation SMS immediately on register (with edit link) | TC-016 |
| **FR-17** | Lottery-result SMS to all; selected/waitlisted include AnimalID | TC-017, TC-018 |
| **FR-18** | SMS in the language stored on the registration | TC-018, TC-046 |
| **FR-19** | Not-selected courtesy SMS | TC-019 |
| **FR-20** | Token edit link opens entry, no login | TC-020 |
| **FR-21** | Owner edits; add+remove while open; add disabled after close_at | TC-022, TC-023, TC-042 |
| **FR-22** | Edit-link valid until check-in / event completion | TC-024 |
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
| TC-016 | I | On signup (Twilio mocked) → a confirmation SMS is sent to the registrant containing an edit link. |
| TC-017 | I | On lottery (Twilio mocked) → a result SMS is sent to **every** registrant; selected/waitlisted bodies contain the AnimalID + edit link; not-selected bodies are the courtesy text; wording differs by outcome. |
| TC-018 | I | A registration whose owner chose ES → both SMS bodies rendered in Spanish; edit links in SMS #1 and #2 resolve to the entry. |
| TC-019 | I | A not-selected registrant receives exactly one courtesy lottery SMS (no AnimalID). |
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

---

## 3. Notes

- **Coverage:** every FR-1..FR-37 and NFR-1..NFR-4 has ≥1 test case (see §1).
- **Two-SMS flow:** signup confirmation (TC-016) and lottery result (TC-017/018/019) are tested
  separately; Twilio is mocked in integration tests.
- **Window/close semantics:** TC-004 (window boundary) and TC-041/TC-042 (after close: signups
  rejected, owner add disabled, edit/remove ok, admin can add) cover FR-4/FR-21/FR-34.
- **Random selection:** TC-013 verifies the lottery selects in random order, not signup order.
- **Language:** TC-046 verifies the chosen language is stored and drives SMS (FR-18/FR-33).
- **Attendance:** TC-043 verifies printing records attendance (FR-35).
- **Admin manual ops:** TC-044 (create entry) and TC-045 (assign AnimalID) cover the post-lottery
  edge-case handling in FR-36/FR-37.
- **Labels:** TC-031/TC-040 verify grouped pet labels (~3/label), not one-per-animal.
- **Test automation targets:** unit (TC-002, TC-009, TC-012, TC-013, TC-015) and integration
  (TC-004, TC-007, TC-008, TC-014, TC-016, TC-017, TC-018, TC-019, TC-031, TC-032, TC-039, TC-041,
  TC-043, TC-044, TC-045, TC-046) should be automated. E2E (browser) and manual/deploy tests are
  run before each release.
