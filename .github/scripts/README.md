# `.github/scripts`

Shell steps called by the deploy and teardown workflows, kept out of YAML so they can be read, linted and run by hand.

| File | What it does |
|---|---|
| [`deploy.sh`](deploy.sh) | `provision` (Terraform apply or Bicep `az deployment sub create`), `push` / `import` images, `roll` Container Apps, `smoke` test `/healthz`, `destroy`. Inputs come from environment variables set by the workflow. |
