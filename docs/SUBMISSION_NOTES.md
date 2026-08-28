# Submission Notes

## What this is
A CP-SAT-based scheduler for a 4-day campus placement week (35 companies,
800 students, 20 rooms), with disruption-aware replanning and a coordinator
dashboard. Built over 6 days per the assignment's four required pieces:
realistic data, a feasible initial schedule, replanning under disruption,
and a usable dashboard.

## Headline metrics (seed=42, reproducible via `python3 -m data_gen.generate`)
- 1,354 interviews to schedule out of a ~1,660 theoretical ceiling given the
  brief's own room/day constraints (82% of max possible capacity).
- Initial schedule: 674/1,354 (49.8%) overall. Days 2-4 solve to **proven
  optimal, 100%**. Day 1 (36.6%) is structurally over capacity by design
  (228% of room demand) -- documented in `docs/DECISIONS.md`, not a bug.
- Zero clashes, independently re-verified from the committed schedule file,
  not just trusted from the solver's own constraints.
- Replanning: 0% churn for a routine single disruption; 20-60% churn for the
  severe combined scenario from the brief (a late recruiter + a panel drop +
  15 withdrawals at once) -- correctly exceeding the routine budget, since
  severity should cost more churn, not be silently capped.

## The three decisions (full reasoning in `docs/DECISIONS.md`)

**What does a good schedule mean?** Zero hard-constraint clashes (always),
then % scheduled weighted by company priority tier, then room utilization
and student wait time as secondary, reported-but-not-optimized metrics.

**When infeasible, which constraint bends first, and who decides?**
Never: a student/room/panel double-booking. First to bend: mass-recruiter
interviews (lowest priority tier), verified empirically to be dropped at a
higher rate than higher-tier companies when capacity forces trade-offs. The
algorithm proposes a default drop order; borderline cases are meant to
surface to the coordinator on the dashboard as an explicit choice, not be
silently automated.

**How much reshuffling is acceptable during a replan?** A routine disruption
should move under 5% of that day's schedule (validated empirically at 0% in
testing); a severe disruption should be allowed to cost more churn than that,
and the system should say so rather than hide it.

## Known limitations (stated honestly, not hidden)
- Student wait time between interviews isn't optimized (avg ~117 min) --
  the objective maximizes scheduled count, not schedule compactness.
- Room-label stability after a replan is a greedy heuristic, not a proven-
  optimal matching -- ~46% of previously-scheduled interviews keep their
  exact room after a disruption; a full fix would need bipartite matching,
  which wasn't built given the timeline.
- Reason codes for why an interview couldn't be scheduled are best-effort
  heuristic classification (company-over-capacity / room-capacity-exceeded /
  student-day-conflict), not a formally proven cause for each pair.
- CP-SAT's parallel search isn't fully deterministic under a time limit, so
  exact replan numbers vary a few percent run to run on the hardest day.

## What I'd build next with more time
A proper min-cost bipartite matching for room/panel relabeling after a
replan (to push room-label stability well above the current ~46%), and a
secondary objective term that penalizes student wait-time gaps directly,
traded off explicitly against the primary scheduled-count objective.