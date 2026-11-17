# `modules/workbook`

Shared Application Insights workbook **Agent platform operations**. The KQL is loaded from
[`observability/`](../../../../observability/README.md), the same files `workbook.bicep` deploys,
so a Bicep deployment and a Terraform deployment show the same tiles.

| File | What it does |
|---|---|
| [`main.tf`](main.tf) | `azurerm_application_insights_workbook` with the five checked-in queries. |
| [`outputs.tf`](outputs.tf) | Workbook id and display name. |
| [`variables.tf`](variables.tf) | Resource group, location, tags, Application Insights id. |
| [`versions.tf`](versions.tf) | Terraform and provider version constraints. |

The workbook id is a fixed GUID so re-apply updates one workbook. It has not been deployed.
