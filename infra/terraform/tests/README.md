# `infra/terraform/tests`

Offline plan tests. `terraform test` runs `plan` against mocked `azurerm` / `azapi` providers, so it needs no credentials and creates nothing; it catches unknown-at-plan `for_each` keys, naming drift and profile mistakes before a real plan.

| File | What it does |
|---|---|
| [`plan.tftest.hcl`](plan.tftest.hcl) | Offline `terraform test`: plans with mocked providers and asserts naming, tags, the per-profile shape, the alert rules and diagnostic settings, Defender off by default and the NSG under private link. No Azure credentials needed. |
