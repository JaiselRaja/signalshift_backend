# Booking experience redesign — design

**Status:** approved (ready for implementation)
**Date:** 2026-04-19
**Scope:** admin app + user-facing frontend; no backend changes

## Goal

Unblock slot-rule creation in the admin, then redesign the user-facing booking flow into a mobile-first ticket-booking experience, then polish the surrounding frontend pages. No backend or schema work — every endpoint the admin and frontend need already exists.

## Non-goals

- No new API endpoints; no schema changes
- No payments rework (Razorpay integration stays as-is)
- Not redesigning admin list pages beyond wiring them to the new turf detail page
- No visual test coverage tooling (Playwright screenshots etc.) — manual QA in browser

## Phase 1 — Admin Turf Detail page

### Route

New: `/dashboard/turfs/[id]` with four tabs — **Info · Slot Rules · Overrides · Pricing**.

From the existing turfs list, each turf card becomes a link to this detail page. The "Create New Turf" button keeps the current inline form (it's already working). Existing turfs will open into the detail page.

### Info tab

Edit form for the same fields already surfaced in the create form (`name`, `slug`, `city`, `address`, `sport_types`, plus existing `is_active` toggle). Adds `amenities` (comma-separated → string[]).

PATCH `/api/v1/turfs/{id}` is already wired via `updateTurf`.

Operating-hours JSON is out of scope for this phase — slot rules serve the same purpose more cleanly.

### Slot Rules tab

Backend endpoints already exist:
- `POST /api/v1/turfs/{turf_id}/slot-rules` — create
- `GET /api/v1/turfs/{turf_id}/slot-rules` — list
- `PATCH /api/v1/turfs/slot-rules/{rule_id}` — update
- `DELETE /api/v1/turfs/slot-rules/{rule_id}` — delete

UI:
- Table (or card list) of existing rules grouped by day-of-week.
- "Add Rule" button opens an inline form row:
  - Day-of-week multi-select (0=Monday … 6=Sunday)
  - Start time (HH:MM input)
  - End time (HH:MM input)
  - Duration (minutes, default 60)
  - Slot type (`regular` | `peak` | `offpeak`)
  - Base price (number, INR)
  - Max capacity (default 1)
  - Active toggle
- Submitting creates one rule per selected weekday (multi-select expands to multiple POSTs).
- Each existing rule has inline edit (toggle to edit mode) and delete.
- Helper: a "Quick-fill" dropdown with two presets — "All weekdays" (Mon–Fri) and "All days" (Mon–Sun).

Frontend `api.ts` will gain `listSlotRules`, `createSlotRule`, `updateSlotRule`, `deleteSlotRule`.

### Overrides tab

Backend endpoints already exist:
- `POST /api/v1/turfs/{turf_id}/overrides`
- `GET /api/v1/turfs/{turf_id}/overrides`
- `PATCH /api/v1/turfs/overrides/{override_id}` (assumed — verify at impl time)
- `DELETE /api/v1/turfs/overrides/{override_id}` (assumed — verify at impl time)

UI:
- List of upcoming overrides sorted by date
- "Add Override" form:
  - Date picker
  - Override type (`closed` | `custom_hours` | `custom_price`)
  - Start/end time (only when type is `custom_hours`)
  - Override price (only when type is `custom_price`)
  - Reason (short text — "Diwali", "Tournament", "Maintenance")
- Each override row has delete. Edit is optional; if the PATCH endpoint isn't actually present in the backend, skip inline edit and rely on delete+re-create.

### Pricing tab

Two options; we'll pick whichever is less work at impl time:
- **Option A (preferred):** move the content of `/dashboard/pricing` into this tab, scoped to the current turf. The existing pricing page becomes either (a) a turf picker that redirects to `/dashboard/turfs/[id]#pricing`, or (b) removed entirely.
- **Option B:** leave the existing pricing page untouched; the tab contains a small note + "Manage pricing on the Pricing page" link with the turf pre-selected.

Final call happens during implementation, after reading the pricing page's code more carefully.

### Non-breaking migration

Existing `/dashboard/pricing` and `/dashboard/turfs` pages keep working until the detail page replaces them. No URLs break.

## Phase 2 — Frontend booking flow redesign

Visual direction: **sports-app aesthetic (ClassPass / Playo)** with **calendar-picker simplicity (Calendly / OpenTable)**. Mobile-first — a turf customer books from their phone.

### Brand tokens (do not change)

- Primary dark green: `#004900`
- Accent lime: `#b2f746`
- Text: `#191c1d`
- Muted: `#707a6a`
- Surface: `#ffffff`, page bg `#f8f9fa`

### Turf detail page (`/turfs/[slug]`)

Layout (single column, stacks on all viewports):

1. **Hero** — turf image (or gradient placeholder with the Signal Shift logo mark), name, city, sport tags, amenity pills (AC / Floodlights / Parking / etc.)
2. **About** — short description + key info (address, phone if present, operating hours summary derived from slot rules — e.g. "Open Mon–Sun 6 am – 11 pm")
3. **Date strip** — horizontal scroll, 14 days. Each day chip shows day-of-week, date number, month, availability dot (green dot if slots, red if full, grey if closed). Selected date has brand-green fill with white text. Scroll-snap + left/right arrows on desktop.
4. **Slot picker** — time slots grouped into three sections:
   - **Morning** — before 12:00
   - **Afternoon** — 12:00 to 17:00
   - **Evening** — 17:00 onwards

   Each slot is a pill:
   ```
   ┌─────────────────────────┐
   │  06:00 – 07:00          │
   │  ₹600 · 60m  [Peak]     │
   └─────────────────────────┘
   ```
   States (Tailwind classes):
   - **Available**: `border border-[#bfcab7]/50 bg-white text-[#191c1d] hover:border-[#004900]/60 hover:shadow-sm`
   - **Selected**: `border-2 border-[#004900] bg-[#b2f746] text-[#121f00] shadow-md`
   - **Peak**: available styling + amber right-border accent + "Peak" chip. Price shown inline.
   - **Sold out**: `border border-[#bfcab7]/30 bg-slate-50 text-slate-400 line-through cursor-not-allowed` with small "Booked" label
   - **Past**: same as sold-out but label "Closed"

5. **Sticky bottom CTA (mobile ≤ md)** — full-width bar pinned to bottom when at least one slot is selected: `Selected 06:00 – 07:00 · ₹600  [Continue →]`. On desktop this CTA inlines below the slot picker.

### Multi-slot selection (added 2026-04-19)

Users can select **up to 3 consecutive time slots** in a single booking (e.g. tap 6–7 pm then 7–8 pm to book 2 hours). Requirements:
- Slots must be contiguous (start of slot B == end of slot A).
- Selecting a non-adjacent slot replaces the prior selection set.
- When N slots are selected, the combined booking spans `first.start_time` → `last.end_time`, price is the sum of `computed_price`, duration is the sum.
- UI shows all selected slots highlighted as one continuous run; sticky CTA shows range and total (e.g. `06:00 – 08:00 · ₹1,200 · 2 hrs  [Continue]`).
- Max 3 (MAX_SLOTS_PER_BOOKING = 3); attempting a 4th shows a subtle toast "Maximum 3 slots per booking".
- Backend booking create already accepts a single `(start_time, end_time)` — we just pass the merged range. No backend change needed.

Transitions use `transition-all duration-150 ease-out`. Selected state uses `scale-[1.02]` on tap. No heavy animations.

### Book page (`/book/[turf_id]`)

3-step vertical layout (stays single page):

1. **Your slot** — card showing turf, date, time range, duration. Non-editable here; "Change" link returns to the turf page.
2. **Your team (optional)** — dropdown of user's teams with "Play solo" option. Matches existing `getMyTeams()` behaviour.
3. **Payment** — price breakdown (base price, peak surcharge, discount from coupon, tax if applicable, **Total** highlighted), coupon input with "Apply" button inline, Razorpay "Pay ₹X" CTA.

Error states (invalid coupon, slot taken, payment failed) get inline toast-style banners, not full-page errors.

## Phase 3 — Broader frontend polish

In order of user traffic:

1. **Turfs list (`/turfs`)** — filter pills for city + sport (replace current dropdowns). Card redesign: image/gradient header, name, city, sport tags, primary action "Book now" → turf detail.
2. **My Bookings (`/bookings`)** — three sections with chips: **Upcoming · Past · Cancelled**. Each row shows turf, date, time, status badge, primary action (cancel for upcoming, rate/review for past — if endpoints exist, otherwise omit).
3. **Profile (`/profile`)** — minor cleanup: larger heading, group fields, better save button state.
4. **Teams / Tournaments** — polish pass only: spacing, typography, empty states. Skip if time-pressed.

No new components outside what Phase 2 creates.

## Implementation approach

- **No TDD for presentational components.** UI work is verified by running it in a browser. Any data-transformation logic that appears (grouping slots into Morning/Afternoon/Evening, for example) gets a small pure function with a unit test.
- **One phase at a time.** At the end of each phase I pause for user review (show via browser + screenshots as needed) before starting the next.
- **Don't break the existing pricing page.** Either fully replace it in Phase 1 (Option A above) or leave it alone. No half-migrated states.
- **Frontend `api.ts`** gains new functions before the admin pages that use them are built (so the compiler tells me if a call is wrong).

## Open questions

- Pricing page migration path (Option A vs B) — decide during Phase 1 coding, after reading the existing pricing page fully.
- Turf hero image — no field for this on the turf model (checked schemas). For now, use a gradient placeholder with the turf's first sport tag as an accent; adding an image upload is out of scope for this pass.
- Operating-hours edit on the Info tab — skipped; slot rules cover this.

## Success criteria

- Admin can create/edit/delete slot rules and overrides for any turf without leaving the admin
- User can land on a turf page, pick a date and slot, and reach the payment screen in ≤3 taps on mobile
- Every state in the slot grid (available, selected, sold-out, past, peak) renders correctly, verified manually in the browser
- No regressions on turfs list, turfs availability, bookings create, or payment callback
