# Open Decisions (V1)

**Status:** Decisions recorded (2026-08-02) — folded into Requirements/Architecture/TraceabilityMatrix
**Companion docs:** `Requirements.md` (§13), `Architecture.md`, `TraceabilityMatrix.md`

Record of product decisions. ✅ = confirmed; 🔶 = recommended, awaiting your nod.

---

## Decision 1 — Not-selected notification (FR-19)
**Decision:** Send a courtesy SMS to not-selected registrants.
**Your answer:** ✅ Confirmed — A.

---

## Decision 2 — Owner edit-link window (FR-22)
**Decision:** Two contracts for the edit link (FR-22/FR-41): (a) the token-authenticated **GET/status view never expires** — it renders for as long as the event data exists, even after check-in/event-completion; (b) owner **mutation** (edit/add/remove animals) is accepted only **until the registration is checked-in or the event completes** (add is additionally limited to the open window). After check-in/completion, GET still renders (with a "locked" notice) but POST/mutation is rejected server-side. The link is sent at signup (no pre-lottery gap). Two SMS touchpoints total (signup confirmation + lottery result).
**Your answer:** ✅ Confirmed — two-text flow.

---

## Decision 3 — Waitlist promotion (no-shows)
**Decision:** No formal promotion in V1; the volunteer checks in whoever shows against remaining capacity (waitlist shown as an ordered list). Printing tags `printed_at` as the attendance signal.
**Your answer:** ✅ Confirmed — B, plus the `printed` attendance tag.

---

## Decision 4 — AnimalID assignment (FR-14)
**Decision:** The lottery **randomly selects** people (not in signup order, so people who borrowed a phone aren't disadvantaged), then assigns **sequential AnimalIDs starting at 1** (1, 2, 3, …, **max 999**) to selected + waitlisted. **Staff additions are a separate sequence starting at 1000** (walk-ins / admissions, added at the clinic after the lottery) and are **not counted toward X or Y** — so a staff-added row can never displace a lottery outcome. Assigning a 1000+ ID to a `registered`/`not_selected` row admits it (`status` → `selected`); the system assigns the next number (staff never type one, and IDs on already-numbered rows are never edited). Sequential numbering makes it easy to hand out pre-numbered stickers and "call the next animal." Uniqueness is DB-enforced. *(Round-7 revision: staff IDs move from "next in 1–999" to a dedicated 1000+ sequence so they cannot bypass the X/Y caps; see FR-14/FR-36/FR-37.)*
**Your answer:** ✅ Confirmed — random selection + sequential IDs.
✅ **Confirmed:** start value is **1** (sequential 1, 2, 3, …; max 999). Resolved 2026-08-02 — matches the Implementation Plan, Requirements, and the data model (`next_animal_id` = max+1 else 1).

---

## Decision 5 — Print station integration (Architecture §8)
**Decision:** Option B — the Flutter app is a thin WebView over the responsive site and exposes the existing native `printLabel` channel via a JS bridge. One UI.
**Your answer:** ✅ Confirmed — B.

---

## Decision 6 — Lottery re-run / edge cases (FR-12, FR-36, FR-37)
**Decision:** The lottery is a **single run**; it is not re-run or tweaked. For edge cases (walk-ins, people who couldn't register online), **staff (admin or volunteer)** add the registration at the clinic (after the lottery) and the system assigns the **next ID in the 1000+ staff sequence** (not counted toward X/Y); admitting a `registered`/`not_selected` row sets `status='selected'` atomically with the ID. No ID is typed or edited on an already-numbered row. Uniqueness is DB-enforced. *(Round-7 revision: staff IDs move to a dedicated 1000+ sequence.)*
**Your answer:** ✅ Confirmed — single run; **staff (admin or volunteer)** add walk-ins / admit existing rows; the system assigns the next 1000+ ID (not counted toward X/Y); admit sets `status='selected'`.

---

## Decision 7 — Admin/volunteer UI language
**Decision:** Admin and volunteer UI is **English-only** in V1. Only the public form and owner SMS are EN/ES.
**Your answer:** ✅ Confirmed — English-only.

---

## Decision 8 — Registration open/close (timestamp-driven; no manual lock)
**Decision:** Keep **`open_at` / `close_at`** timestamps. The form opens at `open_at`, closes automatically at `close_at`, and after close owners can edit/remove but not add. **There is no manual "lock" button.** The admin may adjust the open/close times (e.g., to close early). The lottery is then run manually after close.
**Your answer:** ✅ Confirmed — keep timestamps, drop manual lock.

---

## Decision 9 — Pet label layout (FR-28)
**Decision:** Pet labels are **not** one-per-animal. Animals are **grouped onto labels** (target ~3 animals per label); the exact count is set after print testing on the 3nStar.
**Your answer:** ✅ Confirmed — grouped, ~3/label, exact count TBD by testing.

---

## Decision 10 — Lottery trigger (FR-40; plan R-4)
**Decision:** **Hybrid.** The admin runs the lottery manually, **or** it runs automatically at noon (in the event's timezone) on the calendar day after `close_at` if not yet run — so it can't be forgotten and result texts stay civilized. Both paths call one concurrency-safe `run_lottery` (Event-row lock + post-lock guard) that cannot double-run.
**Your answer:** ✅ Confirmed — hybrid (manual + noon auto-run).

---

## Decision 11 — Event deletion / retention (FR-39; plan R-9)
**Decision:** The admin may **delete an entire event** (cascade to all registrations/animals) from the event selector / Django admin, behind a confirmation warning. Otherwise event data is retained; there is no automatic expiry.
**Your answer:** ✅ Confirmed — admin delete behind a confirmation.

---

## Decision 12 — Applicant cap Z (FR-38; plan R-10)
**Decision:** Per-event **Z** (target max registrations/owners), admin-configured alongside X and Y. Once reached, new signups are rejected with a friendly EN/ES "full" message. Gates only brand-new signups — existing owners may still add animals. **Z is a soft cap**: the capacity check + insert are not serialized, so concurrent signups at the boundary may push the count over Z — by at most the number of signups in flight at the boundary. This is **not a deterministic invariant** (no lock, no hard ≤Z) and is verified as **residual/load behavior** (TC-047), not a unit assertion; for human-paced submissions the in-flight count is small, so the SMS blast is ~Z, not exactly Z.
**Your answer:** ✅ Confirmed — per-event soft applicant cap Z.

---

## Decision 13 — Twilio budget + opt-out/consent wording (plan R-11)
**Decision:** ✅ **Confirmed.** Per event: a signup text and a result text go to each consenting registrant; the blast is **~Z** (Z plus a small concurrency overshoot per Decision 12 — not a hard ≤Z). The Admin approved the budget, and the opt-out/consent approach: a **signup consent checkbox (default on)** plus **"Reply STOP to opt out"** on every SMS, honored **provider-side by Twilio Advanced Opt-Out** on the Messaging Service (FR-43). Delivery is **fire-and-forget / best-effort** (not guaranteed — phones off, carrier blocks; the edit-link status page is the reliable channel). Exact compliance copy ("Msg & data rates may apply", final checkbox label) is polished during build/UX review.
**Your answer:** ✅ Confirmed — budget OK; consent checkbox + STOP opt-out; best-effort delivery.

---

## Decision 14 — Owner status visibility + SMS consent (FR-41/FR-42)
**Decision:** The edit-link page **always shows the owner's current result** (AnimalID / "not selected" / "pending" / checked-in) — **GET renders it even after mutation locks** (check-in / event complete); only POST/edit is blocked — so an owner can learn their outcome **without an SMS**. SMS consent is a **checkbox on the signup form, checked by default**; unchecking (or toggling later on the edit link) sets `sms_opt_out` and skips all SMS, while status stays viewable on the edit-link page. The result SMS still goes to **every** consenting registrant, including a courtesy text to not-selected (Decision 1 stands).
**Your answer:** ✅ Confirmed — edit-link shows result (FR-41); SMS consent checkbox default-on + opt-out (FR-42); result text to every consenting registrant (Decision 1 kept).

---

## Decision 15 — SMS delivery: fire-and-forget; STOP/START provider-side (FR-43)
**Decision (revised — see note):** SMS is a **convenience** channel; the edit-link status page (FR-41) is the reliable one, so delivery is **fire-and-forget: best-effort, at-most-once, never retried.** `sent` means Twilio **accepted** the API request (2xx, queued) — not delivered. Each result SMS is sent **at most once** — atomically claim `result_sms_state null→sending` (committed before the Twilio POST), then classify the synchronous response: **2xx → `sent`**; **4xx (e.g. invalid number) → `failed`**; **5xx / connection error / timeout / no response → `unknown` (a *caught* exception — a process crash is **not** `unknown`; a dead worker cannot write its own state, so it leaves `null` before the claim or `sending` after)** (not retried). Because nothing is ever re-sent, at-most-once is trivially true (no double-texts); a crash can leave zero attempts or a persistent `sending`, neither resent. There is no `retry_sms`, no delivery-status callback, no per-message `StatusCallback`, and no `SmsAttempt`/`PhoneBlock` model. All SMS edit-links are built from one `PUBLIC_BASE_URL`. Delivery is not guaranteed, backstopped by the edit-link status page.

**STOP/START are handled provider-side** by Twilio **Advanced Opt-Out** on the Messaging Service (Twilio maintains the per-number blocklist and replies with the keyword text). A send to a blocked number is still **accepted** (`sent`); Twilio fails it **asynchronously** with `21610`, which the app does **not** observe (no callback) — the desired outcome for an opted-out number. The app does **not** receive an inbound webhook and does **not** mirror Twilio's blocklist, so there is no opt-out state to keep ordered or reconciled. The only app-side SMS gate is application consent (`sms_opt_out`, FR-42): a send goes out iff that registration's consent is clear. Re-consent of a provider-blocked number is by texting START (Twilio unblocks).

> **Note on the revision:** an earlier version of this decision specified an at-most-once delivery state machine with a mirrored `PhoneBlock`, an inbound STOP/START webhook, a per-message delivery-status callback, and reconcile-gated `retry_sms`. Repeated review showed that design fought Twilio's actual API (no idempotency key; webhooks that retry and arrive out of order; error codes Twilio says are unstable) and grew to 7 models for a 2-text-per-clinic feature. Per the Admin's direction ("it's a lottery — folks can always check the link; fire and forget"), it was collapsed to the fire-and-forget model above. (FR-42/FR-43.)

**Your answer:** ✅ Confirmed — fire-and-forget / best-effort / never-retried delivery; STOP/START handled provider-side by Twilio Advanced Opt-Out (not mirrored) (FR-43).

---

## Decision 16 — Admin vs volunteer privileges (FR-30)
**Decision:** **Differentiated privileges** (supersedes the earlier "same privileges" wording). **Admin-only** capabilities: create / configure / delete events (FR-1/FR-39), run the lottery (FR-12 — the noon auto-run via cron is system-level, not a user privilege — FR-40), and export data (FR-29). **Both roles** perform all clinic-day operations: look up, edit, add, remove, check-in, print, manual entry, and assign AnimalID (FR-23..FR-28, FR-35..FR-37). **Provisioning:** an Admin is a Django **superuser** — `is_staff=True`, `is_superuser=True`, `role=admin` (full Django-admin access; created via `createsuperuser`/`ensure_admin`); a Volunteer is `is_staff=False`, `is_superuser=False`, `role=volunteer` (clinic views only). The custom `UserManager` (and `User.clean()`) **reject every inconsistent combination**, so there is no path that provisions a volunteer-role superuser or a privileged volunteer. **Enforcement:** Admin-only custom views use a `role == admin` mixin; entering the Django admin requires `is_staff`, and an Admin's full model access comes from its superuser status.
**Your answer:** ✅ Confirmed — Admin-only = event create/configure/delete + run lottery + export; both roles = all clinic operations.

---

## Decision 17 — Animal sex is optional (FR-8)
**Decision:** `Animal.sex` is **not a required field**. Some animals' sex is not known — **especially babies** — so the owner/staff may leave it blank or choose **"Unknown"**. The model keeps the export-spec choices **M/F/MN/FS** (Male / Female / Male-Neutered / Female-Spayed) and adds **U = "Unknown"**; the field is `blank=True, default=''`. Required per-animal fields remain **name, species, age**; **breed, color, and sex are optional**. This **reverses the Phase-1 audit's finding that sex must be required** (that finding was predicated on the old "all per-animal fields required" wording; the Admin confirmed sex is genuinely optional in practice). Reflected in `Requirements.md` §5/§7.7/§8 + FR-8, `ImplementationPlan.md` (`register.Animal`), and `TraceabilityMatrix.md` (FR-8/TC-009). Export shows blank/"Unknown" where sex was not known.
**Your answer:** ✅ Confirmed — sex optional; "Unknown" (U) is a first-class choice (not just a blank).

---

## Summary
Decisions 1–17 are all confirmed — **no open items remain for V1**. AnimalIDs start at **1** (Decision 4). The hybrid lottery trigger, event deletion, applicant cap Z (Decisions 10–12), owner status-visibility/SMS consent (Decision 14), SMS delivery/STOP-START (Decision 15), and the Admin/volunteer privilege split (Decision 16) are reflected in Requirements/Architecture/Traceability as **FR-30, FR-38..FR-43**. Animal sex is optional (Decision 17) is reflected as **FR-8/TC-009**.
