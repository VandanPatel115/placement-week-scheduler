"""
Day 1 realism regression tests. These encode the sanity checks so a future
change (e.g. tuning an archetype parameter) can't silently flatten the
distribution back to unrealistic uniform noise without a test failing.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_gen.companies import generate_companies
from data_gen.students import generate_students, assign_shortlists


def _dataset():
    companies = generate_companies(seed=42)
    students = generate_students(seed=42)
    assign_shortlists(students, companies, seed=42)
    return companies, students


def test_company_count_and_archetype_split():
    companies, _ = _dataset()
    assert len(companies) == 35
    archetypes = [c.archetype for c in companies]
    assert archetypes.count("mass_recruiter") == 7
    assert archetypes.count("core") == 20
    assert archetypes.count("dream") == 8


def test_cgpa_cutoffs_are_respected():
    companies, students = _dataset()
    cutoff = {c.company_id: c.cgpa_cutoff for c in companies}
    for s in students:
        for cid in s.shortlists:
            assert s.cgpa >= cutoff[cid], (
                f"{s.student_id} (CGPA {s.cgpa}) shortlisted by {cid} "
                f"below its cutoff {cutoff[cid]}"
            )


def test_shortlist_distribution_is_right_skewed_not_flat():
    """Top students should be shortlisted far more than the median student --
    if this ever fails, the weighting logic has regressed to uniform sampling."""
    _, students = _dataset()
    counts = sorted((len(s.shortlists) for s in students), reverse=True)
    top10_avg = sum(counts[:10]) / 10
    median = counts[len(counts) // 2]
    assert top10_avg > median * 2, "top students aren't meaningfully more shortlisted than the median"


def test_most_companies_can_fit_their_own_shortlist():
    """A handful of companies overcommitting is realistic; most shouldn't be
    structurally impossible even in isolation from cross-company clashes."""
    companies, students = _dataset()
    demand = {}
    for s in students:
        for cid in s.shortlists:
            demand[cid] = demand.get(cid, 0) + 1

    over_capacity = 0
    for c in companies:
        day_minutes = 9 * 60
        capacity = (day_minutes // c.duration_min) * c.panels
        if demand.get(c.company_id, 0) > capacity:
            over_capacity += 1

    assert over_capacity <= len(companies) * 0.25, (
        f"{over_capacity}/{len(companies)} companies can't fit their own shortlist -- "
        "check overcommit factors, this shouldn't be the majority"
    )


def test_generation_is_deterministic_given_a_seed():
    companies_a, students_a = _dataset()
    companies_b, students_b = _dataset()
    assert [c.company_id for c in companies_a] == [c.company_id for c in companies_b]
    assert [s.shortlists for s in students_a] == [s.shortlists for s in students_b]