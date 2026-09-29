# Partial backend config for prod. Create the state storage once (see infra/terraform/README.md),
# then:  terraform init -backend-config=envs/prod.backend.hcl
# resource_group_name  = "rg-tfstate-shared-eus2-001"
# storage_account_name = "sttfstateshared001"
# container_name       = "tfstate"
key              = "azure-agent-platform/prod.tfstate"
use_azuread_auth = true
