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
**Decision:** Per-event **Z** (target max registrations/owners), admin-configured alongside X and Y. Once reached, new signups are rejected with a friendly EN/ES "full" message. Gates only brand-new signups — existing owners may still add animals. **Z is a soft cap**: the capacity check + insert are not serialized, so concurrent signups at the boundary may push the count over Z — by at most the number of signups in flight at the boundary. This is **not a deterministic invariant** (no lock, no hard ≤Z) and is verified as **residual/load behavior** (TC-047), not a unit assertion; for human-paced submissions the in-flight count is small, so the SMS blast is ~Z, not exactly Z.
**Your answer:** ✅ Confirmed — per-event soft applicant cap Z.

---

## Decision 13 — Twilio budget + opt-out/consent wording (plan R-11)
**Decision:** ✅ **Confirmed.** Per event: a signup text and a result text go to each consenting registrant; the blast is **~Z** (Z plus a small concurrency overshoot per Decision 12 — not a hard ≤Z). The Admin approved the budget, and the opt-out/consent approach: a **signup consent checkbox (default on)** plus **"Reply STOP to opt out"** on every SMS, honored provider-side via the inbound STOP/START webhook (FR-43). Delivery is **at-most-once and best-effort** (not guaranteed — phones off, carrier blocks). Exact compliance copy ("Msg & data rates may apply", final checkbox label) is polished during build/UX review.
**Your answer:** ✅ Confirmed — budget OK; consent checkbox + STOP opt-out; best-effort delivery.

---

## Decision 14 — Owner status visibility + SMS consent (FR-41/FR-42)
**Decision:** The edit-link page **always shows the owner's current result** (AnimalID / "not selected" / "pending" / checked-in) — even after self-edit locks — so an owner can learn their outcome **without an SMS**. SMS consent is a **checkbox on the signup form, checked by default**; unchecking (or toggling later on the edit link) sets `sms_opt_out` and skips all SMS, while status stays viewable on the edit-link page. The result SMS still goes to **every** consenting registrant, including a courtesy text to not-selected (Decision 1 stands).
**Your answer:** ✅ Confirmed — edit-link shows result (FR-41); SMS consent checkbox default-on + opt-out (FR-42); result text to every consenting registrant (Decision 1 kept).

---

## Decision 15 — SMS delivery + provider-side STOP/START (FR-43)
**Decision:** SMS delivery is **at-most-once and best-effort**. Each send is a `sms.SmsAttempt` (carrying `purpose` ∈ signup/result) classified by what can be **proven** (per RFC 9110 §9.2.2, a non-idempotent POST's response does not prove no side effect): `sent` on a definitive acceptance (2xx + Message SID); `failed_permanent` on a 4xx documented as pre-acceptance (invalid number/body) or a `21610`; and **`unknown` on any 5xx / connection error / timeout / no-response / crashed worker** — a 5xx is a server error and does **not** prove the message was not created (it can be emitted after creation). **Nothing is auto-retried on a timer.** The initial send is an **atomic claim** — a unique `(registration, purpose) WHERE is_initial` constraint means only one worker creates the initial attempt; retry is a **one-consumer claim** via a unique `retry_of` + `retry_claimed_at`. Each attempt carries an opaque `callback_token` in its per-message `StatusCallback` URL; the callback reconciles the attempt by token (even with no captured SID), advances `provider_status` **monotonically**, and persists `provider_error_code`/`retryable`. `retry_sms` (scoped to `purpose='result'`) is **reconcile-gated**: it re-sends only an `unknown` a callback confirmed reached a terminal, **retryable** failure (the prior message is terminal and will never deliver, so re-sending cannot duplicate), under a per-(registration,purpose) attempt cap; an `unknown` with no reconciling callback is never retried (flagged). All SMS URLs come from one `PUBLIC_BASE_URL` (so they work from cron/retry, not just a request). Delivery is not guaranteed, backstopped by the edit-link status page (FR-41).

Opt-out is split into **two independent dimensions**: **application consent** (`sms_opt_out`, per-registration, owner-controlled via FR-42 — one owner's decline does not affect another registration) and a **phone-level provider block** (`sms.PhoneBlock`). A send requires the registration's own consent clear **and** no provider block. "Reply STOP to opt out" is made real provider-side over a **Messaging Service** (Advanced Opt-Out) with **two signature-validated webhooks**: inbound `/sms/inbound/` (`OptOutType` normalized to the uppercase values **`STOP`**→upsert `PhoneBlock`, **`START`**→delete it, **`HELP`**→no-op) is the **sole writer** of `PhoneBlock` (so START never grants application consent, and a stale/delayed callback can't re-block after START), and a per-message delivery-status `/sms/status/<token>/` callback (token-keyed reconciliation, monotonic status). A `21610` (sync or callback) is **not** an opt-out write — it marks the attempt `failed_permanent`/`retryable=False` and logs; only STOP/START change the block. The website toggle can't override a provider block; re-consent requires START.
**Your answer:** ✅ Confirmed — at-most-once/best-effort delivery (`SmsAttempt`, atomic claims, 5xx→unknown, reconcile-gated retry) + two-dimension opt-out via a Messaging Service, `PhoneBlock` written only by STOP/START (FR-43).

---

## Summary
Decisions 1–15 are all confirmed — **no open items remain for V1**. AnimalIDs start at **1** (Decision 4). The hybrid lottery trigger, event deletion, applicant cap Z (Decisions 10–12), owner status-visibility/SMS consent (Decision 14), and SMS delivery/STOP-START (Decision 15) are reflected in Requirements/Architecture/Traceability as **FR-38..FR-43**.
