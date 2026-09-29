# API Management as the AI gateway in front of the BFF: Entra ID JWT validation (when a tenant
# is configured), identity headers derived from claims, rate limiting, and a global kill switch
# driven by a named value (set `agents-enabled` to false -> every agent call returns 503).
locals {
  sku_name = var.sku == "Consumption" ? "Consumption_0" : "${var.sku}_1"

  jwt_policy = var.entra_tenant_id == "" ? "" : <<-XML
    <set-header name="x-user" exists-action="delete" />
    <set-header name="x-groups" exists-action="delete" />
    <validate-jwt header-name="Authorization" failed-validation-httpcode="401" output-token-variable-name="jwt">
      <openid-config url="https://login.microsoftonline.com/${var.entra_tenant_id}/v2.0/.well-known/openid-configuration" />
      <audiences><audience>${var.entra_audience}</audience></audiences>
    </validate-jwt>
    <set-header name="x-user" exists-action="override"><value>@(((Jwt)context.Variables["jwt"]).Claims.GetValueOrDefault("oid", ""))</value></set-header>
    <set-header name="x-tenant-id" exists-action="override"><value>@(((Jwt)context.Variables["jwt"]).Claims.GetValueOrDefault("tid", ""))</value></set-header>
    <set-header name="x-groups" exists-action="override"><value>@(string.Join(",", ((Jwt)context.Variables["jwt"]).Claims.GetValueOrDefault("roles", new string[0])))</value></set-header>
  XML
}

resource "azurerm_api_management" "this" {
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = var.tags
  sku_name            = local.sku_name
  publisher_name      = var.publisher_name
  publisher_email     = var.publisher_email

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_api_management_named_value" "kill_switch" {
  name                = "agents-enabled"
  resource_group_name = var.resource_group_name
  api_management_name = azurerm_api_management.this.name
  display_name        = "agents-enabled"
  value               = "true"
}

resource "azurerm_api_management_api" "this" {
  name                  = var.api_name
  resource_group_name   = var.resource_group_name
  api_management_name   = azurerm_api_management.this.name
  revision              = "1"
  display_name          = var.api_display_name
  path                  = var.api_path
  protocols             = ["https"]
  service_url           = var.backend_url
  subscription_required = var.subscription_required
}

resource "azurerm_api_management_api_operation" "this" {
  for_each            = var.operations
  operation_id        = each.key
  api_name            = azurerm_api_management_api.this.name
  api_management_name = azurerm_api_management.this.name
  resource_group_name = var.resource_group_name
  display_name        = each.key
  method              = each.value.method
  url_template        = each.value.url

  dynamic "template_parameter" {
    for_each = each.value.params
    content {
      name     = template_parameter.value
      type     = "string"
      required = true
    }
  }
}

resource "azurerm_api_management_api_policy" "this" {
  api_name            = azurerm_api_management_api.this.name
  api_management_name = azurerm_api_management.this.name
  resource_group_name = var.resource_group_name

  xml_content = <<-XML
    <policies>
      <inbound>
        <base />
        <choose>
          <when condition="@(&quot;{{agents-enabled}}&quot; != &quot;true&quot;)">
            <return-response><set-status code="503" reason="Agents disabled by kill switch" /></return-response>
          </when>
        </choose>
        ${local.jwt_policy}
        <rate-limit calls="${var.rate_limit_calls}" renewal-period="60" />
        <set-header name="traceparent" exists-action="skip">
          <value>@($"00-{Guid.NewGuid().ToString("N")}-{Guid.NewGuid().ToString("N").Substring(0,16)}-01")</value>
        </set-header>
      </inbound>
      <backend><base /></backend>
      <outbound><base /></outbound>
      <on-error><base /></on-error>
    </policies>
  XML

  depends_on = [azurerm_api_management_named_value.kill_switch]
}
