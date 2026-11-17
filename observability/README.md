# Observability: KQL and the operations workbook

Queries for the Application Insights workbook deployed by `infra/modules/workbook.bicep` and
`infra/terraform/modules/workbook`. Both tools load these files, so the dashboard and the
queries in Git stay the same text. Nothing here has been executed against a live workspace.

| File | What it shows |
|---|---|
| [`requests.kql`](requests.kql) | Request count, failures and p95 latency in 5-minute buckets. |
| [`dependencies.kql`](dependencies.kql) | Outbound calls (Foundry, AI Search, Cosmos, Service Bus) by target. |
| [`exceptions.kql`](exceptions.kql) | Exception types over 15-minute buckets. |
| [`cosmos-checkpoints.kql`](cosmos-checkpoints.kql) | Checkpoint and Cosmos dependency health. |
| [`canary.kql`](canary.kql) | Request split by the `prompt_ref` custom dimension the canary header is meant to log. |

After `azd up`, open Application Insights and the shared workbook **Agent platform operations**.
The same queries can be pasted into the Logs blade. Screenshots of a live workspace belong in
[`docs/go-live`](../docs/go-live/README.md) once a subscription has run the deployment.
