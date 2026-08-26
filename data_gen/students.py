"""
Student generator for Placement Week.

Two things make this realistic instead of uniform noise:
1. CGPA follows a right-of-center distribution (most students cluster
   6.5-8.5, a thin tail above 9) instead of uniform.
2. Shortlist assignment is CGPA-weighted, not random-uniform, within each
   company's eligible (CGPA >= cutoff) pool. High-CGPA students get pulled
   onto many company lists simultaneously -- exactly the overlapping-
   shortlist chaos that makes the scheduling problem hard.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from faker import Faker

from data_gen.companies import Company

fake = Faker()

BRANCH_WEIGHTS = {
    "CSE": 0.28, "ISE": 0.14, "ECE": 0.16, "EEE": 0.10,
    "Mech": 0.12, "Civil": 0.08, "Chem": 0.06, "Aero": 0.06,
}


@dataclass
class Student:
    student_id: str
    name: str
    cgpa: float
    branch: str
    shortlists: list[str] = field(default_factory=list)  # company_ids


def generate_students(num_students: int = 800, seed: int = 42) -> list[Student]:
    rng = np.random.default_rng(seed)
    Faker.seed(seed)

    cgpas = rng.normal(loc=7.3, scale=0.85, size=num_students)
    cgpas = np.clip(cgpas, 5.0, 9.85).round(2)

    branches = rng.choice(
        list(BRANCH_WEIGHTS.keys()), size=num_students, p=list(BRANCH_WEIGHTS.values())
    )

    students = [
        Student(
            student_id=f"S{i:04d}",
            name=fake.name(),
            cgpa=float(cgpas[i]),
            branch=str(branches[i]),
        )
        for i in range(num_students)
    ]
    return students


def assign_shortlists(students: list[Student], companies: list[Company], seed: int = 42) -> None:
    """Mutates students in place, filling in .shortlists."""
    rng = np.random.default_rng(seed + 1)

    for company in companies:
        eligible = [s for s in students if s.cgpa >= company.cgpa_cutoff]
        if not eligible:
            continue
        k = min(company.shortlist_size, len(eligible))

        # Weighting exponent is company-specific: mass recruiters cast a
        # broad net (exponent ~1) so most eligible students have a real
        # shot, while dream companies use a steep exponent (~3.5) that
        # keeps pulling the same toppers onto every elite list.
        weights = np.array([s.cgpa for s in eligible], dtype=float) ** company.weight_exponent
        weights = weights / weights.sum()

        chosen_idx = rng.choice(len(eligible), size=k, replace=False, p=weights)
        for idx in chosen_idx:
            eligible[idx].shortlists.append(company.company_id)


if __name__ == "__main__":
    from data_gen.companies import generate_companies

    companies = generate_companies()
    students = generate_students()
    assign_shortlists(students, companies)

    counts = sorted((len(s.shortlists) for s in students), reverse=True)
    print(f"Generated {len(students)} students")
    print(f"Top 10 shortlist counts: {counts[:10]}")
    print(f"Median shortlist count: {counts[len(counts)//2]}")
    print(f"Students with 0 shortlists: {sum(1 for c in counts if c == 0)}")