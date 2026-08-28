from replanner.disruptions import apply_disruptions, company_late, panel_drop, student_withdraw
import json
from collections import Counter

schedule = json.loads(open('data/schedule.json').read())
interviews = json.loads(open('data/interviews.json').read())
from data_gen.companies import generate_companies
companies_by_id = {c.company_id: c for c in generate_companies(seed=42)}
day1_interviews = [i for i in interviews if companies_by_id[i['company_id']].day == 1]

counts = Counter(iv['company_id'] for iv in schedule if iv['day'] == 1)
biggest_cid = counts.most_common(1)[0][0]          # pick by ACTUAL scheduled count
other_cid = [c for c in counts if c != biggest_cid][0]
day1_students = list({i['student_id'] for i in day1_interviews})
withdrawn = day1_students[:15]

result = apply_disruptions(
    day=1,
    disruptions=[
        company_late(biggest_cid, 180),
        panel_drop(other_cid, 1),
        student_withdraw(withdrawn),
    ],
    time_limit_s=30.0,
)
print(result['diff']['summary'])