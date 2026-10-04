# `knowledge/data/`: synthetic corpora

Synthetic corpora loaded by name by `load_corpus()` (`DATA / "<name>.json"`), so this README is
never read as data. Each chunk carries validity dates and `allowed_groups` so temporal and ACL
filtering can be exercised. None of this is real investor or HR text.

| File | What it does |
|---|---|
| [`guidelines.json`](guidelines.json) | 16 versioned investor-guideline chunks (for example `GL-DTI-200.v1` in force until `2025-06-30` and `.v2` from `2025-07-01`), with `effective_from` / `effective_to`, `allowed_groups`, `program` and machine-readable `params`. Includes a confidential overlay (`GL-OVL-900`, `underwriting-senior` only) and a deliberately injected passage (`GL-MISC-999`) that the context builder must screen out. |
| [`hr_policies.json`](hr_policies.json) | 5 HR policy chunks for the single-agent HR demo, with validity dates and `allowed_groups`. |
