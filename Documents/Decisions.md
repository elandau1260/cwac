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
**Decision:** Edit link valid from the signup SMS until the registration is checked-in (or the event completes); no pre-lottery gap because the link is sent at signup. Two SMS touchpoints total (signup confirmation + lottery result).
**Your answer:** ✅ Confirmed — two-text flow.

---

## Decision 3 — Waitlist promotion (no-shows)
**Decision:** No formal promotion in V1; the volunteer checks in whoever shows against remaining capacity (waitlist shown as an ordered list). Printing tags `printed_at` as the attendance signal.
**Your answer:** ✅ Confirmed — B, plus the `printed` attendance tag.

---

## Decision 4 — AnimalID assignment (FR-14)
**Decision:** The lottery **randomly selects** people (not in signup order, so people who borrowed a phone aren't disadvantaged), then assigns **sequential AnimalIDs starting at 1** (1, 2, 3, …), **max 999**, to selected + waitlisted. Manual admin additions take the next available number. Sequential numbering makes it easy to hand out pre-numbered stickers and "call the next animal." Uniqueness is DB-enforced.
**Your answer:** ✅ Confirmed — random selection + sequential IDs.
✅ **Confirmed:** start value is **1** (sequential 1, 2, 3, …; max 999). Resolved 2026-08-02 — matches the Implementation Plan, Requirements, and the data model (`next_animal_id` = max+1 else 1).

---

## Decision 5 — Print station integration (Architecture §8)
**Decision:** Option B — the Flutter app is a thin WebView over the responsive site and exposes the existing native `printLabel` channel via a JS bridge. One UI.
**Your answer:** ✅ Confirmed — B.

---

## Decision 6 — Lottery re-run / edge cases (FR-12, FR-36, FR-37)
**Decision:** The lottery is a **single run**; it is not re-run or tweaked. For edge cases (walk-ins, people who couldn't register online), the admin can manually create registrations and assign an AnimalID (next in the 1–999 sequence). Uniqueness is DB-enforced.
**Your answer:** ✅ Confirmed — single run; admin manual add + assign IDs.

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
**Decision:** Per-event **Z** (target max registrations/owners), admin-configured alongside X and Y. Once reached, new signups are rejected with a friendly EN/ES "full" message. Gates only brand-new signups — existing owners may still add animals. **Z is a soft cap**: the capacity check + insert are not serialized, so concurrent signups at the boundary may push the count a few over Z — acceptable (no lock, no hard limit). The overshoot is bounded by the number of in-flight signups at the boundary (small for human-paced submissions), so the SMS blast is ~Z, not exactly Z.
**Your answer:** ✅ Confirmed — per-event soft applicant cap Z.

---

## Decision 13 — Twilio budget + opt-out/consent wording (plan R-11)
**Decision:** ✅ **Confirmed.** Per event: a signup text and a result text go to each consenting registrant; the blast is **~Z** (Z plus a small concurrency overshoot per Decision 12 — not a hard ≤Z). The Admin approved the budget, and the opt-out/consent approach: a **signup consent checkbox (default on)** plus **"Reply STOP to opt out"** on every SMS, honored provider-side via the inbound STOP/START webhook (FR-43). Delivery is **at-most-once and best-effort** (not guaranteed — phones off, carrier blocks). Exact compliance copy ("Msg & data rates may apply", final checkbox label) is polished during build/UX review.
**Your answer:** ✅ Confirmed — budget OK; consent checkbox + STOP opt-out; best-effort delivery.

---

## Decision 14 — Owner status visibility + SMS consent (FR-41/FR-42)
**Decision:** The edit-link page **always shows the owner's current result** (AnimalID / "not selected" / "pending" / checked-in) — even after self-edit locks — so an owner can learn their outcome **without an SMS**. SMS consent is a **checkbox on the signup form, checked by default**; unchecking (or toggling later on the edit link) sets `sms_opt_out` and skips all SMS, while status stays viewable on the edit-link page. The result SMS still goes to **every** consenting registrant, including a courtesy text to not-selected (Decision 1 stands).
**Your answer:** ✅ Confirmed — edit-link shows result (FR-41); SMS consent checkbox default-on + opt-out (FR-42); result text to everyone (Decision 1 kept).

---

## Decision 15 — SMS delivery + provider-side STOP/START (FR-43)
**Decision:** SMS delivery is **at-most-once and best-effort** (a delivery state tracks each send; only transient failures are retried — never a `sent` or an ambiguous `unknown`, so no double-texts) — not guaranteed, backstopped by the edit-link status page (FR-41). "Reply STOP to opt out" is made real provider-side: a **signature-validated inbound STOP/START webhook** (Twilio Advanced Opt-Out) syncs `sms_opt_out` phone-level; outbound treats a Twilio `21610` block as a durable opt-out, and re-consent requires START (the website toggle can't override a provider block).
**Your answer:** ✅ Confirmed — best-effort delivery + STOP/START webhook (FR-43).

---

## Summary
Decisions 1–15 are all confirmed — **no open items remain for V1**. AnimalIDs start at **1** (Decision 4). The hybrid lottery trigger, event deletion, applicant cap Z (Decisions 10–12), owner status-visibility/SMS consent (Decision 14), and SMS delivery/STOP-START (Decision 15) are reflected in Requirements/Architecture/Traceability as **FR-38..FR-43**.
