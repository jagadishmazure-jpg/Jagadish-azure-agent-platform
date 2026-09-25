# `evals/golden/`: golden sets

Golden cases loaded by name (`load_golden("mortgage_conditions")`, `load_golden("hr_policy")`),
so only these `.jsonl` files are read; this README is ignored by the loader.

| File | What it does |
|---|---|
| [`hr_policy.jsonl`](hr_policy.jsonl) | 5 HR questions with `query`, `as_of`, `groups`, `expected_citations` and `must_contain`; includes the same question at different dates to test temporal retrieval. |
| [`mortgage_conditions.jsonl`](mortgage_conditions.jsonl) | 4 mortgage cases with `loan_id`, `groups`, `expected_recommendation`, `must_include` and `must_exclude` condition ids, including an ACL case (confidential overlay visible only to senior underwriters). |
