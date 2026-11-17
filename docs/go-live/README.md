# Screenshots to add after the first live deployment

The root README [Go live](../../README.md#go-live) section is the runbook. This folder is where
the captures go once `azd up` has run against a subscription. They are not in the repo yet,
because this portfolio was built without Azure credentials.

Add these files beside this README:

| File | What to capture |
|---|---|
| `container-apps.png` | The Container Apps environment with the six apps. |
| `foundry.png` | The Foundry project and the chat deployment. |
| `workbook.png` | The Application Insights workbook **Agent platform operations**. |
| `live-eval.png` | The `live-report.json` summary (mock metrics, live judge metrics, USD per 1k tasks). |

Until those files exist, the README keeps the live URL as `https://<bff-fqdn>`.
