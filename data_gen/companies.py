"""
Company generator for Placement Week.

Real placement seasons aren't uniform: a handful of mass recruiters anchor
Day 1 and interview hundreds of students quickly, a long tail of core/mid-tier
companies fill the middle days, and a small set of dream/niche companies show
up late with brutal CGPA cutoffs and long interviews for a tiny shortlist.
That shape is what makes the downstream scheduling problem realistically hard
-- not the raw company count.
"""
from __future__ import annotations
import random
from dataclasses import dataclass, field
from faker import Faker

fake = Faker()
Faker.seed(42)
random.seed(42)

DAY_MINUTES = 9 * 60  # 9 AM - 6 PM

# shortlist_size is NOT a flat random range -- it's an "overcommit factor"
# applied to the company's own (panels x slots-per-panel) capacity. This
# keeps the vast majority of companies able to fit their own shortlist in
# isolation (realistic: recruiters size shortlists to what they can actually
# interview), while a deliberate slice of each archetype overcommits --
# mirroring real companies that over-shortlist assuming dropouts/no-shows.
ARCHETYPES = {
    "mass_recruiter": dict(
        count=7,
        days=[1],
        panels=(4, 7),
        duration_min=(20, 25),
        cgpa_cutoff=(5.5, 6.5),
        priority_tier=3,          # dropped first if the schedule is infeasible
        overcommit=(0.75, 1.15),
        overcommit_outlier_chance=0.3,
        overcommit_outlier=(1.4, 1.9),
        weight_exponent=1.0,      # broad net -- volume hire, mild CGPA preference
    ),
    "core": dict(
        count=20,
        days=[1, 2, 3, 4],
        panels=(1, 2),
        duration_min=(30, 40),
        cgpa_cutoff=(6.5, 7.5),
        priority_tier=2,
        overcommit=(0.6, 1.0),
        overcommit_outlier_chance=0.15,
        overcommit_outlier=(1.2, 1.5),
        weight_exponent=1.8,      # moderate preference for stronger CGPA
    ),
    "dream": dict(
        count=8,
        days=[3, 4],
        panels=(1, 1),
        duration_min=(45, 60),
        cgpa_cutoff=(8.0, 9.0),
        priority_tier=1,          # dropped last -- protected in the objective
        overcommit=(0.5, 0.85),
        overcommit_outlier_chance=0.0,
        overcommit_outlier=(1.0, 1.0),
        weight_exponent=3.5,      # elitist -- pulls the same toppers onto every list
    ),
}


@dataclass
class Company:
    company_id: str
    name: str
    archetype: str
    day: int
    panels: int
    duration_min: int
    cgpa_cutoff: float
    priority_tier: int
    shortlist_size: int
    weight_exponent: float


def generate_companies(seed: int = 42) -> list[Company]:
    random.seed(seed)
    Faker.seed(seed)
    companies: list[Company] = []
    cid = 0
    for archetype, cfg in ARCHETYPES.items():
        for _ in range(cfg["count"]):
            cid += 1
            panels = random.randint(*cfg["panels"])
            duration_min = random.choice(range(cfg["duration_min"][0], cfg["duration_min"][1] + 1, 5))

            capacity = (DAY_MINUTES // duration_min) * panels
            if random.random() < cfg["overcommit_outlier_chance"]:
                factor = random.uniform(*cfg["overcommit_outlier"])
            else:
                factor = random.uniform(*cfg["overcommit"])
            shortlist_size = max(5, round(capacity * factor))

            companies.append(
                Company(
                    company_id=f"C{cid:03d}",
                    name=fake.company(),
                    archetype=archetype,
                    day=random.choice(cfg["days"]),
                    panels=panels,
                    duration_min=duration_min,
                    cgpa_cutoff=round(random.uniform(*cfg["cgpa_cutoff"]), 2),
                    priority_tier=cfg["priority_tier"],
                    shortlist_size=shortlist_size,
                    weight_exponent=cfg["weight_exponent"],
                )
            )
    return companies


if __name__ == "__main__":
    companies = generate_companies()
    print(f"Generated {len(companies)} companies")
    for c in companies[:5]:
        print(c)