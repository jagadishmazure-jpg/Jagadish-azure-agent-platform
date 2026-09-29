# prod: always-on replicas, Developer APIM (swap to StandardV2 for SLA), private endpoints,
# Key Vault purge protection. Review the cost estimate before applying.
environment                = "prod"
location                   = "eastus2"
instance                   = "001"
cost_profile               = "standard"
private_link               = true
key_vault_purge_protection = true
owner                      = "jagadish.meduri"
cost_center                = "portfolio"
