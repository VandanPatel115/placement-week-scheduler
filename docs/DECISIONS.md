# Decisions & Assumptions

## Assumptions (Day 0)
- 35 companies, 800 students, 4 days, 20 rooms, 9 AM–6 PM working hours — taken
  directly from the brief.
- Slot granularity: 5 minutes (evenly divides every interview duration in use:
  20, 25, 30, 35, 40, 45, 50, 55, 60).
- Company archetypes (not stated explicitly in the brief, but implied by
  "Day-1 companies are the mass recruiters"): 7 mass recruiters (Day 1 only),
  20 core companies (spread across all 4 days), 8 dream/niche companies
  (Days 3–4, high cutoffs, long interviews, small shortlists).
- A "panel" requires one room for as long as it's running interviews --
  panel count is effectively simultaneous-room demand for that company.

## Finding: the dataset is genuinely room-constrained, especially Day 1
Day 1 alone demands 228% of Day 1's room capacity (46 simultaneous panels
needed across 13 companies, but only 20 rooms exist), because mass recruiters
are concentrated there by design, matching the brief. **No scheduling
algorithm, however good, can fit every Day-1 shortlisted interview into Day
1.** This isn't a data generation flaw -- it's the "everything goes wrong on
the day itself" premise made concrete, and it directly motivates the
decisions below.

## What does a "good" schedule mean? (with real numbers)
- **Zero hard-constraint clashes** -- verified two independent ways: inside
  the CP-SAT model itself (AddNoOverlap/AddCumulative), and again by
  `scheduler/metrics.py` re-checking the committed schedule.json from
  scratch. Both report 0 student/room/panel clashes.
- **% scheduled**: 674/1354 overall (49.8%). By day: Day 1 393/1073 (36.6%),
  Day 2 55/55 (100%), Day 3 129/129 (100%), Day 4 97/97 (100%). The Day 1
  number looks low in isolation, but it's within a few points of the
  theoretical ceiling given room scarcity (see Day 1 finding above) --
  the other three days being 100% is the more meaningful signal that the
  algorithm isn't leaving capacity on the table where capacity exists.
- **Room utilization**: Day 1 98.5% (essentially saturated -- expected, given
  it's over-demanded), Day 2 16.5%, Day 3 49.3%, Day 4 36.2%. The low
  utilization on Days 2 and 4 is itself a finding: there's slack capacity on
  those days that Day 1's overflow structurally cannot use, since companies
  are tied to a single fixed day each.
- **Student wait time**: avg 136 min, 95th percentile 345 min between a
  student's back-to-back interviews. **Known limitation, stated plainly**:
  the objective currently only maximizes weighted scheduled count -- nothing
  rewards compact scheduling for a given student. A secondary objective term
  (penalize gaps) would improve this but wasn't prioritized, since maximizing
  scheduled interviews matters more given how constrained Day 1 already is.
- **Replan churn**: built out Day 4.

## When infeasible, which constraint bends first — and who decides?
- **Never bends:** a student in two places at once, a room or panel
  double-booked. Verified at 0 violations, always.
- **Bends first:** which *interviews* get dropped when demand exceeds
  capacity. Implemented as a weighted objective (dream=10x, core=3x,
  mass=1x) -- mass recruiters bend first, dream companies are protected
  hardest. Confirmed working: on Day 1, core-tier (2) interviews are
  scheduled at a meaningfully higher rate than mass-recruiter-tier (3)
  interviews (verified by
  `test_priority_tier_is_respected_when_capacity_forces_tradeoffs`).
- **Who decides:** the algorithm proposes this default drop order by tier,
  but a borderline case should surface to the coordinator as an explicit
  choice on the dashboard (Day 5), not be silently automated.
- **Reason codes for the 680 unscheduled interviews** (Day 1, heuristic, not
  formally proven per-pair): `company_over_capacity` (~354, the company's own
  shortlist exceeds its panel capacity even in isolation), `room_capacity_exceeded`
  (~213, global room scarcity), `student_day_conflict` (~113, the student had
  3+ shortlists competing for the same day). Documented as best-effort
  classification, not exact causal attribution -- worth saying explicitly in
  the defense rather than overclaiming precision.

## How much reshuffling is acceptable during a replan?
Proposed churn budget: a routine disruption should move **under 5% of that
day's schedule**. Tunable, exposed on the dashboard -- not a fixed law. A
severe disruption (the defense-session example: biggest Day-1 recruiter 3
hours late + a panel drop + 15 withdrawals) will legitimately need more
churn than that, and the system should say so rather than silently
under-fixing the schedule to stay under budget. Verified Day 4.