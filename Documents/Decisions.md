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
🔶 **Open sub-point:** start value — you said "1" earlier and "0" most recently. Docs currently use **1**. Confirm 0 or 1?

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

## Summary
All decisions confirmed except the **AnimalID start value (0 vs 1)** under Decision 4 — awaiting your nod.
